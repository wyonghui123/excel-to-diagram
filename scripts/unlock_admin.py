# -*- coding: utf-8 -*-
"""
[DECORATIVE] v3.14: Admin Unlock 脚本
==============================

当 admin 账号被锁 (5+ 失败登录) 时, 自动/手动解锁。
可被 cron / Task Scheduler / CI 定期调用。

Usage:
    # 手动 (一次性)
    python scripts/unlock_admin.py

    # 监控模式 (每 N 秒检查一次)
    python scripts/unlock_admin.py --watch 60

    # Dry run (看状态但不修改)
    python scripts/unlock_admin.py --dry-run

    # 自定义 DB 路径
    python scripts/unlock_admin.py --db path/to/architecture.db

Exit codes:
    0 - 成功 (admin 已解锁 / 已 active)
    1 - 失败 (DB 不存在 / 解锁失败)
    2 - admin 已被禁用 (status != active, 不自动解锁)
"""
import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# [DECORATIVE] v3.14: 找项目根 (从 scripts/ 跑时)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT_ROOT)

# 默认 DB 路径
DEFAULT_DB = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')


def check_admin_status(db_path: str) -> dict:
    """检查 admin 状态"""
    if not os.path.exists(db_path):
        return {'exists': False, 'error': f'DB 不存在: {db_path}'}

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        # 表 schema 可能不同, 尝试多种列
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'status' in columns:
            # [DECORATIVE] v3.14: 实际 columns 是 status, status_entered_at, last_login_at
            row = conn.execute(
                "SELECT username, status, status_entered_at, last_login_at FROM users WHERE username = 'admin'"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT username FROM users WHERE username = 'admin'"
            ).fetchone()
            if row:
                # 旧 schema, 没有 status 字段, 假定 active
                return {'exists': True, 'username': row[0], 'status': 'active', 'schema': 'old'}
            return {'exists': False}

        if not row:
            return {'exists': False, 'error': 'admin 用户不存在'}

        return {
            'exists': True,
            'username': row[0],
            'status': row[1] or 'active',
            'status_entered_at': row[2] if len(row) > 2 else None,
            'last_login_at': row[3] if len(row) > 3 else None,
        }
    finally:
        conn.close()


def unlock_admin(db_path: str, dry_run: bool = False) -> bool:
    """解锁 admin (如果被锁)"""
    status = check_admin_status(db_path)
    if not status.get('exists'):
        print(f'[X] {status.get("error", "未知错误")}')
        return False

    admin_status = status.get('status', 'active')

    if admin_status == 'active':
        print(f'[OK] admin 已 active, 无需解锁 (last_login: {status.get("last_login_at", "N/A")})')
        return True

    if admin_status == 'disabled':
        print(f'[WARN] admin 已被禁用 (disabled), 不会自动解锁 (需人工介入)')
        return False

    if admin_status in ('locked', 'failed', 'suspended'):
        if dry_run:
            print(f'[DRY-RUN] 需解锁 admin (status={admin_status})')
            return True

        conn = sqlite3.connect(db_path, timeout=5)
        try:
            # [DECORATIVE] v3.15: 同时写入 audit_logs (security 事件)
            admin_id = conn.execute(
                "SELECT id FROM users WHERE username = 'admin'"
            ).fetchone()
            admin_id_value = admin_id[0] if admin_id else None

            conn.execute("UPDATE users SET status = 'active' WHERE username = 'admin'")
            conn.commit()
            print(f'[OK] admin 已解锁 (status: {admin_status} -> active) at {datetime.now().isoformat()}')

            # [DECORATIVE] v3.15: 写 audit log (记录谁、何时、何动作)
            try:
                _write_audit_log(
                    conn,
                    object_type='user',
                    object_id=admin_id_value,
                    action='unlock',
                    field_name='status',
                    old_value=admin_status,
                    new_value='active',
                    user_name='admin_unlock_script',
                    log_category='security',
                    log_level='WARN',
                )
                print(f'  [INFO] audit log 已记录 (log_category=security)')
            except Exception as e:
                # Audit log 失败不影响主流程
                print(f'  [WARN] audit log 写入失败: {e}')

            return True
        finally:
            conn.close()

    print(f'[WARN] admin 状态未知: {admin_status}')
    return False


def _write_audit_log(
    conn: sqlite3.Connection,
    object_type: str,
    object_id: Optional[int],
    action: str,
    field_name: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    user_id: str = 'system',
    user_name: str = 'admin_unlock_script',
    log_category: str = 'security',
    log_level: str = 'WARN',
) -> int:
    """[DECORATIVE] v3.15: 写 audit_logs 表 (记录 admin unlock 等安全事件)

    实际 columns: object_type, object_id, action, field_name, old_value, new_value,
                  user_id, user_name, ip_address, user_agent, created_at, extra_data,
                  log_category, log_level, status, status_entered_at, ...
    """
    now = datetime.now().isoformat()
    cursor = conn.execute(
        """
        INSERT INTO audit_logs (
            object_type, object_id, action, field_name, old_value, new_value,
            user_id, user_name, user_agent, created_at,
            log_category, log_level, status, status_entered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            object_type, object_id, action, field_name, old_value, new_value,
            user_id, user_name, 'admin_unlock_script/1.0', now,
            log_category, log_level, 'written', now,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def watch_mode(db_path: str, interval: int):
    """监控模式 - 每 N 秒检查一次"""
    print(f'[REFRESH] 监控模式启动 (每 {interval}s 检查, Ctrl+C 退出)')
    while True:
        try:
            unlock_admin(db_path)
        except Exception as e:
            print(f'[X] 异常: {e}')
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description='Admin Unlock - 解锁被锁的 admin 账号',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--db',
        default=DEFAULT_DB,
        help=f'数据库路径 (默认: {DEFAULT_DB})',
    )
    parser.add_argument(
        '--watch',
        type=int,
        metavar='SECONDS',
        help='监控模式, 每 N 秒检查一次 (e.g. --watch 60)',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只看状态, 不修改',
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='仅显示状态',
    )
    args = parser.parse_args()

    if args.watch:
        watch_mode(args.db, args.watch)
    else:
        if args.status or args.dry_run:
            status = check_admin_status(args.db)
            print(f'admin 状态: {status}')

        if not args.status:
            ok = unlock_admin(args.db, dry_run=args.dry_run)
            sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
