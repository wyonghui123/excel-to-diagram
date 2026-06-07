import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/tests/architecture.db')
cur = conn.cursor()
cur.execute('SELECT name FROM sqlite_master WHERE type=?', ('table',))
tables = cur.fetchall()
print("Tables in architecture.db:")
for t in tables:
    print(f"  - {t[0]}")
conn.close()
