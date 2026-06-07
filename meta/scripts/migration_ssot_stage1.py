# -*- coding: utf-8 -*-
"""
SSOT 阶段 1 migration: audit_logs 添加 created_at_epoch + 复合索引

【背景 2026-06-05】
v1.4 SSOT helper 当前用 MAX(created_at) TEXT 聚合，性能不佳。
项目原计划阶段 1（meta/database/migration_ssot_updated_at.sql）添加
created_at_epoch (BIGINT) 列 + 复合索引 (object_type, object_id, action, created_at_epoch DESC)
本脚本执行阶段 1，为阶段 2（已部分执行）提供高性能支持。
"""
import sqlite3
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def main():
    db_path = r'd:\filework\excel-to-diagram\meta\architecture.db'

    if not os.path.exists(db_path):
        logger.error('DB not found: %s', db_path)
        return False

    # Backup
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{db_path}.bak.stage1.{ts}'
    import shutil
    shutil.copy2(db_path, backup_path)
    logger.info('Backed up to: %s', backup_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Check if column already exists
    cur.execute('PRAGMA table_info(audit_logs)')
    cols = [r[1] for r in cur.fetchall()]
    if 'created_at_epoch' in cols:
        logger.info('created_at_epoch column already exists, skip')
    else:
        # Add column
        try:
            cur.execute('ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT')
            logger.info('Added created_at_epoch column')
        except Exception as e:
            logger.error('Failed to add column: %s', e)
            conn.close()
            return False

    # 2. Backfill existing rows
    cur.execute("SELECT COUNT(*) FROM audit_logs WHERE created_at_epoch IS NULL AND created_at IS NOT NULL")
    null_count = cur.fetchone()[0]
    logger.info('Backfilling %d rows with epoch value...', null_count)
    if null_count > 0:
        cur.execute("""
            UPDATE audit_logs
            SET created_at_epoch = (strftime('%s', created_at) * 1000)
            WHERE created_at_epoch IS NULL AND created_at IS NOT NULL
        """)
        logger.info('Backfilled %d rows', null_count)

    # 3. Create index
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated
        ON audit_logs(object_type, object_id, action, created_at_epoch DESC)
    """)
    logger.info('Created idx_audit_ssot_updated index')

    conn.commit()

    # 4. Verify
    cur.execute('PRAGMA table_info(audit_logs)')
    cols = [(r[1], r[2]) for r in cur.fetchall()]
    print('\naudit_logs columns:')
    for c in cols:
        print(f'  {c[0]:25s} {c[1]}')

    cur.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND tbl_name='audit_logs' AND name='idx_audit_ssot_updated'
    """)
    idx = cur.fetchone()
    print(f'\nidx_audit_ssot_updated index: {"[DECORATIVE] exists" if idx else "[DECORATIVE] missing"}')

    # Sample epoch values
    cur.execute("""
        SELECT id, object_type, object_id, action, created_at, created_at_epoch
        FROM audit_logs
        WHERE created_at_epoch IS NOT NULL
        LIMIT 5
    """)
    print('\nSample rows with epoch:')
    for r in cur.fetchall():
        print(f'  {r}')

    conn.close()
    return True


if __name__ == '__main__':
    success = main()
    import sys
    sys.exit(0 if success else 1)
