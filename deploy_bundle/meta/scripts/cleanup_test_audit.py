#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cleanup_test_audit.py — 清理 1601 条测试脏数据 (FR-007, TBD-4 决策)

按 TBD-4 决策: 包含 admin 角色的测试数据全删, 仅保留真 admin (id=1)
按 FR-007: 默认 --dry-run, 显式 --apply 才删
回滚: 备份表 audit_logs_backup_20260612
"""
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "architecture.db"

# 测试数据识别模式
TEST_USER_PATTERNS = [
    "V3.17 Test%",
    "test_%",
    "audit_%",
]

# users 表识别条件 (display_name 或 username 匹配, 但保留 id=1 真 admin)
USERS_WHERE_SQL = """
    (display_name LIKE 'V3.17 Test%'
     OR username LIKE 'test_%'
     OR username LIKE 'audit_%')
    AND id != 1
"""

# audit_logs 表识别条件 (user_name 匹配, 多模式)
AUDIT_WHERE_SQL = """
    user_name LIKE 'V3.17 Test%'
    OR user_name LIKE 'test_%'
    OR user_name LIKE 'audit_%'
"""


def get_test_data_stats(conn) -> dict:
    """统计测试脏数据规模"""
    stats = {"audit_count": 0, "user_count": 0, "patterns": {}}
    for pat in TEST_USER_PATTERNS:
        cur = conn.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE user_name LIKE ?", (pat,)
        )
        c = cur.fetchone()[0]
        stats["patterns"][pat] = c
        stats["audit_count"] += c
    # user 表
    cur = conn.execute(f"SELECT COUNT(*) FROM users WHERE {USERS_WHERE_SQL}")
    stats["user_count"] = cur.fetchone()[0]
    # audit 残留 (AUDIT_WHERE_SQL 总数)
    cur = conn.execute(f"SELECT COUNT(*) FROM audit_logs WHERE {AUDIT_WHERE_SQL}")
    stats["audit_count_total"] = cur.fetchone()[0]
    return stats


def backup(conn, apply: bool) -> bool:
    """备份 audit_logs + users 测试数据到 backup 表"""
    backup_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_audit = f"audit_logs_backup_{backup_ts}"
    backup_user = f"users_backup_{backup_ts}"
    try:
        if apply:
            conn.execute(f"CREATE TABLE {backup_audit} AS "
                         f"SELECT * FROM audit_logs WHERE {AUDIT_WHERE_SQL}")
            conn.execute(f"CREATE TABLE {backup_user} AS "
                         f"SELECT * FROM users WHERE {USERS_WHERE_SQL}")
            conn.commit()
            print(f"  [BACKUP] audit_logs -> {backup_audit}")
            print(f"  [BACKUP] users      -> {backup_user}")
        else:
            print(f"  [DRY]     would backup audit to {backup_audit}")
            print(f"  [DRY]     would backup users  to {backup_user}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] backup failed: {e}")
        return False


def cleanup(conn, apply: bool) -> dict:
    """删测试数据 (audit_logs + users)"""
    result = {"audit_deleted": 0, "user_deleted": 0}
    try:
        if apply:
            cur = conn.execute(f"DELETE FROM audit_logs WHERE {AUDIT_WHERE_SQL}")
            result["audit_deleted"] = cur.rowcount
            cur = conn.execute(f"DELETE FROM users WHERE {USERS_WHERE_SQL}")
            result["user_deleted"] = cur.rowcount
            conn.commit()
        else:
            cur = conn.execute(f"SELECT COUNT(*) FROM audit_logs WHERE {AUDIT_WHERE_SQL}")
            result["audit_deleted"] = cur.fetchone()[0]
            cur = conn.execute(f"SELECT COUNT(*) FROM users WHERE {USERS_WHERE_SQL}")
            result["user_deleted"] = cur.fetchone()[0]
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] cleanup failed: {e}")
        raise
    return result


def vacuum(conn, apply: bool):
    if apply:
        conn.execute("VACUUM")
        print("  [VACUUM] 物理释放空间")
    else:
        print("  [DRY] would VACUUM")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="真删 (默认 dry-run)")
    p.add_argument("--vacuum", action="store_true", help="删完跑 VACUUM (释放空间)")
    p.add_argument("--no-backup", action="store_true", help="跳过备份 (生产慎用)")
    args = p.parse_args()

    print(f"DB: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    try:
        # 1. 统计
        stats = get_test_data_stats(conn)
        print(f"\n[STATS] 测试脏数据规模:")
        for pat, c in stats["patterns"].items():
            print(f"        {pat:20s} : {c:5d} 条")
        print(f"        {'合计 audit_logs (OR)':20s} : {stats['audit_count_total']:5d} 条")
        print(f"        {'users 表':20s} : {stats['user_count']:5d} 个")

        # 2. 备份 (默认开启)
        if not args.no_backup:
            if not backup(conn, args.apply):
                return 1

        # 3. 删
        if args.apply:
            print(f"\n[APPLY] 开始删除...")
        else:
            print(f"\n[DRY-RUN] 预览删除范围 (--apply 才真删):")
        result = cleanup(conn, args.apply)
        print(f"  audit_logs: {result['audit_deleted']:5d} 条 {'被删' if args.apply else '将被删'}")
        print(f"  users     : {result['user_deleted']:5d} 个 {'被删' if args.apply else '将被删'}")

        # 4. VACUUM
        if args.vacuum:
            vacuum(conn, args.apply)

        # 5. 验证
        if args.apply:
            after = get_test_data_stats(conn)
            print(f"\n[AFTER] 残留: {after['audit_count_total']} 条 audit_logs, {after['user_count']} 个 users")
            if after['audit_count_total'] == 0:
                print("[OK] 清理完成")
            else:
                print(f"[WARN] 还有 {after['audit_count_total']} 条残留, 检查 LIKE 模式")

        mode = "APPLIED" if args.apply else "DRY-RUN"
        print(f"\n{'='*50}\n  [{mode}] 完成\n{'='*50}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
