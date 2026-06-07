import sqlite3, os

for db_path in [
    r'd:\filework\excel-to-diagram\architecture.db',
    r'd:\filework\excel-to-diagram\meta\architecture.db',
]:
    print(f'\n=== {os.path.basename(os.path.dirname(db_path))}/{os.path.basename(db_path)} ===')
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute('PRAGMA quick_check')
        print(f'Check: {cur.fetchone()}')
        cur.execute('SELECT name FROM sqlite_master WHERE type="table" ORDER BY name')
        tables = [r[0] for r in cur.fetchall()]
        print(f'Tables ({len(tables)}): {", ".join(tables[:15])}...')
        cur.execute('SELECT COUNT(*) FROM users')
        print(f'users: {cur.fetchone()[0]}')
        cols = [r[1] for r in cur.execute('PRAGMA table_info(users)')]
        print(f'user cols: {cols}')
        conn.close()
    except Exception as e:
        print(f'Error: {e}')
