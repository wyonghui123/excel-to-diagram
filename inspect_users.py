import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(users)")
cols = cur.fetchall()
print('users columns:')
for c in cols:
    print(f'  {c}')
