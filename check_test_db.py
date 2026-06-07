import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/tests/test.db')
cur = conn.cursor()
cur.execute('SELECT name FROM sqlite_master WHERE type=?', ('table',))
tables = cur.fetchall()
print("Tables in test.db:")
for t in tables[:10]:
    print(f"  - {t[0]}")
print(f"... and {len(tables)-10} more tables" if len(tables) > 10 else "")

# Check if users table exists
if any(t[0] == 'users' for t in tables):
    cur.execute('SELECT id, username FROM users LIMIT 5')
    users = cur.fetchall()
    print("\nUsers in test.db:")
    for u in users:
        print(f"  - id={u[0]}, username={u[1]}")
conn.close()
