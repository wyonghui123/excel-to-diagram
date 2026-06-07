import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.execute("PRAGMA table_info(user_groups)")
print("user_groups 表字段:")
for r in cur.fetchall():
    print(f"  {r}")
conn.close()
