"""重置 admin 账户的 rate limit 锁定状态"""
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
# 查看所有可能存 rate limit 状态的表
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
for row in cur.fetchall():
    name = row[0]
    if 'rate' in name.lower() or 'login' in name.lower() or 'lock' in name.lower() or 'attempt' in name.lower():
        print(f'Found: {name}')
        try:
            cur.execute(f"SELECT * FROM {name} LIMIT 5")
            print(f'  Sample: {cur.fetchall()}')
        except Exception as e:
            print(f'  ERR: {e}')
conn.close()
