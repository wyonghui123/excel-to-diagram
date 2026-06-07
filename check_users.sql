import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(users)")
rows = cursor.fetchall()
print('users table schema:')
for row in rows:
    print(f'  {row}')
conn.close()
