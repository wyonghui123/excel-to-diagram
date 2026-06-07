import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cursor = conn.cursor()
cursor.execute("SELECT id, name, created_at, updated_at FROM user_groups ORDER BY id")
for row in cursor.fetchall():
    print(f'ID={row[0]}, name={row[1]}, created_at={repr(row[2])}, updated_at={repr(row[3])}')
conn.close()
