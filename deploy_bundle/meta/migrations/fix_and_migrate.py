import sqlite3, os, shutil

src = r'd:\filework\excel-to-diagram\meta\architecture.db'
tmp = r'd:\filework\excel-to-diagram\meta\architecture_tmp.db'

shutil.copy2(src, tmp)
shutil.copy2(src + '-wal', tmp + '-wal')
shutil.copy2(src + '-shm', tmp + '-shm')

try:
    conn = sqlite3.connect(tmp)
    conn.execute('PRAGMA journal_mode=DELETE')
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    cur = conn.cursor()
    cur.execute('PRAGMA quick_check')
    r = cur.fetchone()
    print(f'Check: {r}')
    if r[0] == 'ok':
        conn.execute('ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0')
        conn.commit()
        print('Migration OK')
        conn.close()
        shutil.copy2(tmp, src)
        os.remove(tmp)
        os.remove(src + '-wal')
        os.remove(src + '-shm')
        os.remove(tmp + '-wal' if os.path.exists(tmp + '-wal') else '')
        os.remove(tmp + '-shm' if os.path.exists(tmp + '-shm') else '')
        print('DB replaced successfully')
    else:
        print(f'DB corrupted: {r}')
        conn.close()
except Exception as e:
    print(f'Error: {e}')
    try:
        conn.close()
    except:
        pass
