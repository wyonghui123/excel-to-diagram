import requests
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=TEST333', allow_redirects=True)
print('login status:', r.status_code)
print('login response:', r.text[:300])

# 试 product list, 拿返回的 user context
r2 = s.get('http://localhost:3010/api/v2/bo/product?page=1&page_size=5')
print()
print('product status:', r2.status_code)
data = r2.json()
print('total:', data.get('data', {}).get('total', '?'))
items = data.get('data', {}).get('items', [])
print('returned:', len(items), 'items')

# 找 current_user info
import sqlite3
conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
print()
print('=== TEST333 user_id 链 (5个表) ===')
for tbl in ('user_group_members', 'user_roles', 'role_data_permissions', 'data_permissions'):
    rows = list(conn.execute(f'SELECT * FROM {tbl} WHERE user_id=3385'))
    print(f'  {tbl}: {len(rows)} rows')
    for r in rows[:3]:
        print(' ', r)
