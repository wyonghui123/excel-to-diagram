#!/usr/bin/env python3
"""查 user_id=3371 是哪个用户, 确认是 TEST888 用户的 user_id"""
import sqlite3
import urllib.request, http.cookiejar, json

# 1. 查 DB
db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print('=== user_id=3371 ===')
cur.execute("SELECT id, username, display_name, email, created_at FROM users WHERE id=3371")
row = cur.fetchone()
if row:
    print(f'  id={row[0]} username={row[1]} display_name={row[2]} email={row[3]}')

# 2. 查 TEST888 相关
print('\n=== 名字含 TEST888 的用户 ===')
cur.execute("SELECT id, username, display_name FROM users WHERE username LIKE '%TEST888%'")
for row in cur.fetchall():
    print(f'  id={row[0]} username={row[1]} display_name={row[2]}')

# 3. 查 user_id=1
print('\n=== user_id=1 (admin) ===')
cur.execute("SELECT id, username, display_name FROM users WHERE id=1")
row = cur.fetchone()
if row:
    print(f'  id={row[0]} username={row[1]} display_name={row[2]}')

conn.close()

# 4. 查 user agent
print('\n=== audit log 中的 user_agent (product:353 这次创建) ===')
conn2 = sqlite3.connect(db_path)
cur2 = conn2.cursor()
cur2.execute("SELECT id, user_agent, ip_address FROM audit_logs WHERE object_id=353 AND action='CREATE'")
for row in cur2.fetchall():
    print(f'  id={row[0]} user_agent="{row[1]}" ip={row[2]}')
conn2.close()
