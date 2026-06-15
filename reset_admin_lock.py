import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
# 查看 admin user
cur.execute("SELECT id, username, status, failed_login_count, locked_until FROM users WHERE username='admin'")
row = cur.fetchone()
print(f'admin user: {row}')
# 重置 failed_login_count
cur.execute("UPDATE users SET failed_login_count=0, locked_until=NULL, status='active' WHERE username='admin'")
conn.commit()
cur.execute("SELECT id, username, status, failed_login_count, locked_until FROM users WHERE username='admin'")
print(f'after reset: {cur.fetchone()}')
conn.close()
