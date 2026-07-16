# -*- coding: utf-8 -*-
"""
V1.1 owner_id 列清理 - 使用 SQLite 3.35+ 原生 ALTER TABLE DROP COLUMN
=============================================================

相比 12-step 复制表法, 直接 DROP COLUMN:
- 不丢数据 (如果有)
- 速度快
- 不需要解析 CREATE TABLE SQL
- 风险低

变更:
1. versions 删除 owner_id 和 visibility
2. domains, sub_domains, service_modules, business_objects 删除 owner_id 和 visibility
3. products 保留 owner_id 和 visibility

回滚: 从 backups/architecture.db.bak.<timestamp> 恢复
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / 'meta' / 'backups'

_env_db = os.environ.get('MIGRATION_TARGET_DB')
SOURCE_DB = Path(_env_db) if _env_db else PROJECT_ROOT / 'meta' / 'architecture.db'

# [表, 要删除的列]
COLUMNS_TO_DROP = [
    ('versions', ['owner_id', 'visibility']),
    ('domains', ['owner_id', 'visibility']),
    ('sub_domains', ['owner_id', 'visibility']),
    ('service_modules', ['owner_id', 'visibility']),
    ('business_objects', ['owner_id', 'visibility']),
]


def log(msg, level='INFO'):
    ts = datetime.now().strftime('%Y%m%d %H:%M:%S')
    print(f'[{ts}] [{level}] {msg}', flush=True)


def get_columns(conn, table):
    cur = conn.execute(f'PRAGMA table_info({table})')
    return [r[1] for r in cur.fetchall()]


def backup_database():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'architecture.db.bak.{timestamp}'

    conn = sqlite3.connect(SOURCE_DB)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()

    shutil.copy2(SOURCE_DB, backup_path)
    for ext in ('-wal', '-shm'):
        src = Path(str(SOURCE_DB) + ext)
        if src.exists():
            shutil.copy2(src, str(backup_path) + ext)

    log(f'Backup created: {backup_path}')
    return backup_path


def dry_run():
    log('=== DRY-RUN MODE (no changes) ===')
    conn = sqlite3.connect(SOURCE_DB)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    for table, cols_to_drop in COLUMNS_TO_DROP:
        existing = get_columns(conn, table)
        to_drop = [c for c in cols_to_drop if c in existing]
        if to_drop:
            log(f'  {table}: WILL drop {to_drop}')
        else:
            log(f'  {table}: nothing to drop')

    log('  products: KEEP owner_id, KEEP visibility (V1.1 design)')
    log('\nDry-run complete. Use without --dry-run to actually migrate.')
    conn.close()
    return 0


def run_migration():
    log('=== MIGRATION START ===')
    backup_path = backup_database()

    conn = sqlite3.connect(SOURCE_DB)
    try:
        conn.execute('PRAGMA foreign_keys=OFF')

        for table, cols_to_drop in COLUMNS_TO_DROP:
            existing = get_columns(conn, table)
            for col in cols_to_drop:
                if col in existing:
                    log(f'  {table}: DROP COLUMN {col}')
                    conn.execute(f'ALTER TABLE {table} DROP COLUMN {col}')
                else:
                    log(f'  {table}: {col} not exists, skip')

        conn.commit()
        log('  Commit done')

    except Exception as e:
        log(f'MIGRATION FAILED: {e}', level='ERROR')
        log(f'Restore from backup: {backup_path}', level='ERROR')
        raise
    finally:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.close()

    # Checkpoint WAL 确保持久化
    conn = sqlite3.connect(SOURCE_DB)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()

    # 验证
    log('=== Post-migration verification ===')
    verify_conn = sqlite3.connect(SOURCE_DB)
    for table, cols_to_drop in COLUMNS_TO_DROP:
        cols = get_columns(verify_conn, table)
        for col in cols_to_drop:
            assert col not in cols, f'FAIL: {table}.{col} still exists'
        log(f'  {table}: {cols_to_drop} removed OK')

    # products 应保留 owner_id, visibility
    cols = get_columns(verify_conn, 'products')
    assert 'owner_id' in cols, 'FAIL: products.owner_id should be kept'
    assert 'visibility' in cols, 'FAIL: products.visibility should be kept'
    log('  products: owner_id + visibility kept OK')

    verify_conn.close()

    log(f'=== MIGRATION COMPLETE. Backup: {backup_path} ===')
    return 0


def rollback(backup_file=None):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if backup_file:
        backup_path = Path(backup_file)
    else:
        backups = sorted(BACKUP_DIR.glob('architecture.db.bak.*'))
        if not backups:
            log('No backup found', level='ERROR')
            return 1
        backup_path = backups[-1]

    log(f'Restoring from {backup_path}')

    if SOURCE_DB.exists():
        SOURCE_DB.unlink()
    for ext in ('-wal', '-shm'):
        f = Path(str(SOURCE_DB) + ext)
        if f.exists():
            f.unlink()

    shutil.copy2(backup_path, SOURCE_DB)
    for ext in ('-wal', '-shm'):
        src = Path(str(backup_path) + ext)
        if src.exists():
            shutil.copy2(src, str(SOURCE_DB) + ext)

    log(f'Restored from {backup_path}')
    return 0


def main():
    parser = argparse.ArgumentParser(description='Drop owner_id + visibility columns')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--backup-file', type=str)
    args = parser.parse_args()

    if args.rollback:
        return rollback(args.backup_file)
    if args.dry_run:
        return dry_run()
    return run_migration()


if __name__ == '__main__':
    sys.exit(main())
