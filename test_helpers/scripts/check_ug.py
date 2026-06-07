import sqlite3
conn = sqlite3.connect(r'd:\filework\excel-to-diagram\meta\architecture.db')
cur = conn.cursor()
cur.execute("SELECT id, name, parent_id, manager_id FROM user_groups ORDER BY id LIMIT 10")
for r in cur.fetchall():
    print(r)
