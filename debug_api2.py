import sqlite3
import urllib.request
import json

conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cur = conn.cursor()

# 看 products
cur.execute('SELECT id, code, name FROM products ORDER BY id LIMIT 10')
print('=== products ===')
for r in cur.fetchall():
    print(' ', r)

# 看 versions
cur.execute('SELECT id, code, name, product_id FROM versions ORDER BY id LIMIT 10')
print('\n=== versions ===')
for r in cur.fetchall():
    print(' ', r)

# 关联: versions 的 product_id
cur.execute('SELECT v.id, v.code, v.name, v.product_id, p.code, p.name FROM versions v LEFT JOIN products p ON v.product_id = p.id ORDER BY v.id LIMIT 10')
print('\n=== versions join products ===')
for r in cur.fetchall():
    print(' ', r)

# Login and query API
print('\n=== API: GET /api/v2/bo/product ===')
req = urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin')
with urllib.request.urlopen(req) as r:
    cookie = dict(r.headers).get('Set-Cookie', '').split(';')[0]
print(f'  cookie: {cookie[:30]}')

req = urllib.request.Request('http://localhost:3010/api/v2/bo/product?page=1&page_size=5')
req.add_header('Cookie', cookie)
data = json.loads(urllib.request.urlopen(req).read())
items = data.get('data', {}).get('items', [])
print(f'  /api/v2/bo/product 返回 {len(items)} 条:')
for it in items:
    print(f'    id={it.get("id")} code={it.get("code")} name={it.get("name")}')

print('\n=== API: GET /api/v2/bo/version (no product_id) ===')
req = urllib.request.Request('http://localhost:3010/api/v2/bo/version?page=1&page_size=10')
req.add_header('Cookie', cookie)
data = json.loads(urllib.request.urlopen(req).read())
items = data.get('data', {}).get('items', [])
print(f'  /api/v2/bo/version 返回 {len(items)} 条:')
for it in items:
    print(f'    id={it.get("id")} code={it.get("code")} name={it.get("name")} product_id={it.get("product_id")}')

# 用 product_id=1 查
print('\n=== API: GET /api/v2/bo/version?product_id=1 ===')
req = urllib.request.Request('http://localhost:3010/api/v2/bo/version?product_id=1&page=1&page_size=10')
req.add_header('Cookie', cookie)
data = json.loads(urllib.request.urlopen(req).read())
items = data.get('data', {}).get('items', [])
print(f'  product_id=1 返回 {len(items)} 条:')
for it in items:
    print(f'    id={it.get("id")} code={it.get("code")} name={it.get("name")}')

conn.close()
