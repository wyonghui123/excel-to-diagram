import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 查询 user_group_members 表
cursor.execute('SELECT * FROM user_group_members ORDER BY created_at DESC LIMIT 5')
members = cursor.fetchall()

print(f"找到 {len(members)} 条用户组成员记录:")
for member in members:
    print(f"  - User ID: {member[0]}, Group ID: {member[1]}")

conn.close()
