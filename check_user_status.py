import sqlite3

conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')

# 检查用户状态
print("=== 检查 no_pwd 用户 ===")
cur = conn.execute("SELECT id, username, display_name, status FROM users WHERE username LIKE '%no_pwd%'")
for r in cur.fetchall():
    print(f'id={r[0]}, username={r[1]}, display_name={r[2]}, status={r[3]}')

# 检查 status 枚举值
print("\n=== 用户状态枚举值 ===")
cur = conn.execute("SELECT DISTINCT status FROM users LIMIT 10")
for r in cur.fetchall():
    print(f'status = {r[0]}')

conn.close()
