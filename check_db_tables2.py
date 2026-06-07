import sqlite3
import os

# Check both locations
locations = [
    'd:/filework/excel-to-diagram/meta/tests/architecture.db',
    'd:/filework/excel-to-diagram/meta/architecture.db',
]

for loc in locations:
    if os.path.exists(loc):
        print(f"\nTables in {loc}:")
        conn = sqlite3.connect(loc)
        cur = conn.cursor()
        cur.execute('SELECT name FROM sqlite_master WHERE type=?', ('table',))
        tables = cur.fetchall()
        for t in tables:
            print(f"  - {t[0]}")
        conn.close()
    else:
        print(f"\n{loc}: NOT FOUND")
