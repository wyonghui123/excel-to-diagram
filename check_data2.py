import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.execute("SELECT id, name, code, parent_id, manager_id, description FROM user_groups LIMIT 3")
for r in cur.fetchall():
    print(r)
conn.close()
