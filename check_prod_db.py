import os, sqlite3

db = r'd:\filework\excel-to-diagram\meta\architecture.db'
wal = db + '-wal'
shm = db + '-shm'

print(f'DB size: {os.path.getsize(db)} bytes')
print(f'WAL size: {os.path.getsize(wal) if os.path.exists(wal) else "N/A"} bytes')
print(f'SHM size: {os.path.getsize(shm) if os.path.exists(shm) else "N/A"} bytes')

try:
    conn = sqlite3.connect(db)
    r = conn.execute('PRAGMA quick_check').fetchone()[0]
    print(f'quick_check: {r}')
    r = conn.execute('PRAGMA integrity_check').fetchone()[0]
    print(f'integrity_check: {r}')
    conn.close()
except Exception as e:
    print(f'ERROR: {e}')
