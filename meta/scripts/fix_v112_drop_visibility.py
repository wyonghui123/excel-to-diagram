"""V1.1.3: 彻底删除 versions.visibility 列

清理逻辑:
1. 备份 DB
2. 检查数据分布
3. DROP COLUMN versions.visibility
4. 验证

[V1.1.3 2026-06-11] 硬清理: 不再保留 DB 物理列
"""
import os
import shutil
import sqlite3
from datetime import datetime

DB_PATH = r'meta/architecture.db'
BACKUP_DIR = r'meta/backups'


def backup_db() -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f'architecture.db.bak.{ts}')
    shutil.copy2(DB_PATH, backup_path)
    print(f'[BACKUP] {backup_path}')
    # 也备份 WAL/SHM
    for ext in ['-wal', '-shm']:
        src = DB_PATH + ext
        if os.path.exists(src):
            shutil.copy2(src, backup_path + ext)
            print(f'[BACKUP] {backup_path}{ext}')
    return backup_path


def drop_visibility_column() -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Step 1: 确认列存在
    c.execute('PRAGMA table_info(versions)')
    cols = [r[1] for r in c.fetchall()]
    if 'visibility' not in cols:
        print('[INFO] versions.visibility already absent, nothing to do')
        conn.close()
        return True

    # Step 2: 检查数据
    c.execute('SELECT visibility, COUNT(*) FROM versions GROUP BY visibility')
    distribution = c.fetchall()
    print('[DATA] visibility distribution before drop:')
    for val, cnt in distribution:
        print(f'  {val}: {cnt}')

    c.execute('SELECT COUNT(*) FROM versions')
    total = c.fetchone()[0]
    print(f'[DATA] total versions: {total}')

    # Step 3: 强制 flush WAL
    c.execute('PRAGMA wal_checkpoint(FULL)')
    print('[CHECKPOINT] WAL flushed')

    # Step 4: DROP COLUMN
    try:
        c.execute('ALTER TABLE versions DROP COLUMN visibility')
        conn.commit()
        print('[OK] ALTER TABLE versions DROP COLUMN visibility')
    except Exception as e:
        print(f'[ERROR] DROP COLUMN failed: {e}')
        conn.rollback()
        conn.close()
        return False

    # Step 5: 验证
    c.execute('PRAGMA table_info(versions)')
    cols_after = [r[1] for r in c.fetchall()]
    print(f'[VERIFY] columns after: {cols_after}')
    assert 'visibility' not in cols_after, 'verification failed'
    print('[OK] verified: visibility is gone')

    # Step 6: 再次 flush
    c.execute('PRAGMA wal_checkpoint(FULL)')
    conn.close()
    return True


def rollback(backup_path: str):
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
        success = drop_visibility_column()
        if success:
            print(f'\n[SUCCESS] cleanup done')
            print(f'[BACKUP]  {bp}')
            print('[NEXT]    python scripts/service_manager.ps1 restart')
        else:
            print(f'\n[FAILED]  use --rollback {bp} to restore')
