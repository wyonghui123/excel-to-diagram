import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
# 看 TEST888 user
cur.execute("SELECT id, username FROM users WHERE username LIKE '%TEST%'")
for r in cur.fetchall():
    print(f'user: {r}')

# 看所有产品
cur.execute("SELECT id, name, code FROM products ORDER BY id DESC LIMIT 15")
print('\n=== Products ===')
for r in cur.fetchall():
    print(f'  product {r[0]}: {r[1]} (code: {r[2]})')

# 看所有版本
cur.execute("SELECT id, name, code, product_id FROM versions ORDER BY id DESC LIMIT 15")
print('\n=== Versions ===')
for r in cur.fetchall():
    print(f'  version {r[0]}: {r[1]} (code: {r[2]}) product_id={r[3]}')

# 看 TEST888 的 user_id
cur.execute("SELECT id FROM users WHERE username='TEST888'")
user = cur.fetchone()
if user:
    print(f'\nTEST888 user_id: {user[0]}')
conn.close()
