# -*- coding: utf-8 -*-
"""
[DECORATIVE] v3.16: DB 自动备份脚本
============================

Usage:
    # 一次性备份
    python scripts/backup_db.py

    # 定时 (cron) - 每小时备份 1 次, 保留 24 个
    python scripts/backup_db.py --watch 3600 --keep 24

    # 手动指定保留数量
    python scripts/backup_db.py --keep 7

    # 仅检查, 不备份
    python scripts/backup_db.py --check

Exit codes:
    0 - 成功
    1 - 失败
    2 - 警告 (备份 OK 但清理失败)
"""
import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

# [DECORATIVE] v3.16: 找项目根 (从 scripts/ 跑时)
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _PROJECT_ROOT)

# 默认配置
DEFAULT_DB = os.path.join(_PROJECT_ROOT, 'meta', 'architecture.db')
DEFAULT_BACKUP_DIR = os.path.join(_PROJECT_ROOT, 'meta', 'backups')


def _format_size(size_bytes: int) -> str:
    """格式化为可读 size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f'{size_bytes:.1f}{unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f}TB'


def _ensure_dir(path: str) -> None:
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)


def backup_db(db_path: str = DEFAULT_DB,
              backup_dir: str = DEFAULT_BACKUP_DIR,
              keep: int = 24) -> dict:
    """执行一次 DB 备份

    Returns: dict with keys {success, filename, size_bytes, duration_ms, integrity}
    """
    if not os.path.exists(db_path):
        return {'success': False, 'error': f'DB 不存在: {db_path}'}

    _ensure_dir(backup_dir)
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_name = f'architecture.db.backup-{timestamp}.bak'
    backup_path = os.path.join(backup_dir, backup_name)

    start = datetime.now()
    try:
        # SQLite 在线备份 API (不锁表)
        source = sqlite3.connect(db_path, timeout=30)
        dest = sqlite3.connect(backup_path, timeout=30)
        try:
            source.backup(dest)
        finally:
            source.close()
            dest.close()

        # 验证完整性
        check_conn = sqlite3.connect(backup_path, timeout=5)
        try:
            integrity = check_conn.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            check_conn.close()

        duration_ms = (datetime.now() - start).total_seconds() * 1000
        size_bytes = os.path.getsize(backup_path)

        if integrity != 'ok':
            os.remove(backup_path)
            return {
                'success': False,
                'error': f'备份后 integrity_check 失败: {integrity}',
                'integrity': integrity,
            }

        return {
            'success': True,
            'filename': backup_name,
            'path': backup_path,
            'size_bytes': size_bytes,
            'size': _format_size(size_bytes),
            'duration_ms': round(duration_ms, 1),
            'integrity': integrity,
            'created_at': start.isoformat(),
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def cleanup_old_backups(backup_dir: str = DEFAULT_BACKUP_DIR, keep: int = 24) -> int:
    """清理旧备份, 保留最新的 N 个

    Returns: 删除数量
    """
    if not os.path.exists(backup_dir):
        return 0

    backups = sorted(
        [f for f in os.listdir(backup_dir) if f.endswith('.bak')],
        key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)),
    )

    to_delete = len(backups) - keep
    if to_delete <= 0:
        return 0

    deleted = 0
    for old in backups[:to_delete]:
        try:
            os.remove(os.path.join(backup_dir, old))
            deleted += 1
        except Exception as e:
            print(f'  [WARNING] 删除失败 {old}: {e}')

    return deleted


def list_backups(backup_dir: str = DEFAULT_BACKUP_DIR) -> list:
    """列出所有备份"""
    if not os.path.exists(backup_dir):
        return []

    backups = []
    for f in sorted(os.listdir(backup_dir)):
        if not f.endswith('.bak'):
            continue
        full = os.path.join(backup_dir, f)
        backups.append({
            'filename': f,
            'size': _format_size(os.path.getsize(full)),
            'mtime': datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
        })
    return backups


def watch_mode(interval: int, keep: int, db_path: str, backup_dir: str):
    """守护进程模式 - 每 N 秒备份 1 次"""
    print(f'[REFRESH] 监控模式启动 (每 {interval}s 备份, 保留 {keep} 个)')
    while True:
        try:
            result = backup_db(db_path, backup_dir, keep)
            if result.get('success'):
                print(f'[OK] [{datetime.now().isoformat()}] {result["filename"]} '
                      f'({result["size"]}, {result["duration_ms"]}ms, integrity={result["integrity"]})')
            else:
                print(f'[X] [{datetime.now().isoformat()}] 备份失败: {result.get("error")}')
        except Exception as e:
            print(f'[X] [{datetime.now().isoformat()}] 异常: {e}')
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(
        description='DB 自动备份 - DB 损坏预防方案 2/3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--db', default=DEFAULT_DB, help=f'数据库路径 (默认: {DEFAULT_DB})')
    parser.add_argument('--backup-dir', default=DEFAULT_BACKUP_DIR, help=f'备份目录 (默认: {DEFAULT_BACKUP_DIR})')
    parser.add_argument('--keep', type=int, default=24, help='保留最新 N 个备份 (默认: 24)')
    parser.add_argument('--watch', type=int, metavar='SECONDS', help='监控模式, 每 N 秒备份 1 次')
    parser.add_argument('--list', action='store_true', help='列出所有备份')
    parser.add_argument('--check', action='store_true', help='仅检查 DB 完整性, 不备份')
    parser.add_argument('--no-cleanup', action='store_true', help='不清理旧备份')
    args = parser.parse_args()

    if args.list:
        backups = list_backups(args.backup_dir)
        print(f'备份列表 ({len(backups)} 个):')
        for b in backups:
            print(f'  {b["filename"]:50s} {b["size"]:>10s}  {b["mtime"]}')
        return 0

    if args.check:
        if not os.path.exists(args.db):
            print(f'[X] DB 不存在: {args.db}')
            return 1
        conn = sqlite3.connect(args.db, timeout=5)
        try:
            integrity = conn.execute('PRAGMA integrity_check').fetchone()[0]
        finally:
            conn.close()
        if integrity == 'ok':
            print(f'[OK] DB integrity OK: {args.db} ({_format_size(os.path.getsize(args.db))})')
            return 0
        else:
            print(f'[X] DB integrity 失败: {integrity}')
            return 1

    if args.watch:
        watch_mode(args.watch, args.keep, args.db, args.backup_dir)
        return 0

    # 一次性备份
    print(f'开始备份: {args.db}')
    result = backup_db(args.db, args.backup_dir, args.keep)

    if not result.get('success'):
        print(f'[X] 备份失败: {result.get("error")}')
        return 1

    print(f'[OK] 备份成功:')
    print(f'  文件名: {result["filename"]}')
    print(f'  大小:   {result["size"]} ({result["size_bytes"]:,} bytes)')
    print(f'  耗时:   {result["duration_ms"]}ms')
    print(f'  完整性: {result["integrity"]}')

    # 清理旧备份
    if not args.no_cleanup:
        deleted = cleanup_old_backups(args.backup_dir, args.keep)
        if deleted:
            print(f'  [SYMBOL]️ 清理 {deleted} 个旧备份 (保留最新 {args.keep} 个)')

    # 列出所有备份
    backups = list_backups(args.backup_dir)
    print(f'\n当前备份数: {len(backups)}')
    for b in backups[-3:]:
        print(f'  {b["filename"]:50s} {b["size"]:>10s}  {b["mtime"]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
