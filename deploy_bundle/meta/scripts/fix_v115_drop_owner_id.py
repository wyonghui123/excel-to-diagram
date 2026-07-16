"""V1.1.5: DROP 各子表的 owner_id DB 列

数据状态:
- versions/domains/sub_domains/service_modules/business_objects:
  owner_id 全是 NULL (V1.1.1 已清空数据), 可以安全 DROP
- products:
  owner_id 保留 (顶层 owner 真实数据)

[V1.1.5 2026-06-11] 硬清理: 不再保留 DB 物理列
"""
import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = r'd:\filework\excel-to-diagram\meta\architecture.db'
BACKUP_DIR = r'd:\filework\excel-to-diagram\meta\backups'

# 要 DROP 的表
TABLES_TO_CLEAN = [
    'versions',
    'domains',
    'sub_domains',
    'service_modules',
    'business_objects',
]


def backup_db():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'architecture.db.bak.{ts}')
    shutil.copy2(DB_PATH, backup_path)
    for ext in ['-wal', '-shm']:
        src = DB_PATH + ext
        if os.path.exists(src):
            shutil.copy2(src, backup_path + ext)
    print(f'[BACKUP] {backup_path}')
    return backup_path


def drop_owner_id_column():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print('[CHECKPOINT] WAL flush...')
    c.execute('PRAGMA wal_checkpoint(FULL)')

    for table in TABLES_TO_CLEAN:
        # Step 1: 检查列是否存在
        c.execute(f'PRAGMA table_info({table})')
        cols = {r[1] for r in c.fetchall()}
        if 'owner_id' not in cols:
            print(f'[SKIP] {table}.owner_id already absent')
            continue

        # Step 2: 数据校验（必须全 NULL）
        c.execute(f'SELECT COUNT(*) FROM {table} WHERE owner_id IS NOT NULL')
        non_null = c.fetchone()[0]
        if non_null > 0:
            print(f'[ERROR] {table}.owner_id has {non_null} non-null values, refusing to drop')
            conn.close()
            return False

        c.execute(f'SELECT COUNT(*) FROM {table}')
        total = c.fetchone()[0]
        print(f'[DATA] {table}.owner_id: total={total}, non_null={non_null}')

        # Step 3: DROP COLUMN
        try:
            c.execute(f'ALTER TABLE {table} DROP COLUMN owner_id')
            conn.commit()
            print(f'[OK] ALTER TABLE {table} DROP COLUMN owner_id')
        except Exception as e:
            print(f'[ERROR] {table}: {e}')
            conn.rollback()
            conn.close()
            return False

    # 验证
    print('\n=== Verification ===')
    for table in TABLES_TO_CLEAN:
        c.execute(f'PRAGMA table_info({table})')
        cols = [r[1] for r in c.fetchall()]
        has = 'owner_id' in cols
        print(f'  {table:18s} owner_id: {has}  (expect False)')

    # products 应该保留
    c.execute('PRAGMA table_info(products)')
    cols = [r[1] for r in c.fetchall()]
    print(f'  {"products":18s} owner_id: {"owner_id" in cols}  (expect True)')

    c.execute('PRAGMA wal_checkpoint(FULL)')
    conn.close()
    return True


def rollback(backup_path):
    print(f'[ROLLBACK] restoring from {backup_path}')
    shutil.copy2(backup_path, DB_PATH)
    for ext in ['-wal', '-shm']:
        src = backup_path + ext
        if os.path.exists(src):
            shutil.copy2(src, DB_PATH + ext)
    print('[OK] rollback complete')


if __name__ == '__main__':
    import sys
    if '--rollback' in sys.argv and len(sys.argv) > 2:
        rollback(sys.argv[2])
    else:
        bp = backup_db()
        ok = drop_owner_id_column()
        if ok:
            print(f'\n[SUCCESS]')
            print(f'[BACKUP] {bp}')
            print('[NEXT]   python scripts/service_manager.ps1 restart')
        else:
            print(f'\n[FAILED]  rollback: python meta/scripts/fix_v115_drop_owner_id.py --rollback {bp}')