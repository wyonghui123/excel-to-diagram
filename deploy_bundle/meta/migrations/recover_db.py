import sqlite3, os

src = r'd:\filework\excel-to-diagram\meta\architecture.db'
dst = r'd:\filework\excel-to-diagram\meta\architecture_recovered.db'

# Try .recover command (SQLite 3.50+)
try:
    conn = sqlite3.connect(src)
    # Force delete mode to close WAL
    conn.execute('PRAGMA journal_mode=DELETE')
except Exception as e:
    print(f'Cannot open at all: {e}')
    # Last resort: try without WAL
    wal = src + '-wal'
    shm = src + '-shm'
    wal_bak = src + '-wal.corrupt'
    shm_bak = src + '-shm.corrupt'
    try:
        if os.path.exists(wal):
            os.rename(wal, wal_bak)
        if os.path.exists(shm):
            os.rename(shm, shm_bak)
        conn = sqlite3.connect(src)
        cur = conn.cursor()
        cur.execute('PRAGMA quick_check')
        result = cur.fetchone()
        print(f'Without WAL - check: {result}')
        if result[0] == 'ok':
            cur.execute('ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0')
            conn.commit()
            conn.execute('PRAGMA journal_mode=DELETE')
            conn.commit()
            print('Migration OK')
            conn.close()
        else:
            print('Still broken, need full recovery')
            conn.close()
            # restore WAL
            if os.path.exists(wal_bak):
                os.rename(wal_bak, wal)
            if os.path.exists(shm_bak):
                os.rename(shm_bak, shm)
    except PermissionError as pe:
        print(f'Permission error (still locked): {pe}')
    except Exception as e2:
        print(f'Recovery failed: {e2}')
