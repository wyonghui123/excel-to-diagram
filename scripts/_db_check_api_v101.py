"""直接 verify role 1803 unified-permissions API 返回什么"""
import requests
import sqlite3

BASE = 'http://localhost:3010'
DB = r'D:\filework\excel-to-diagram\meta\architecture.db'

# 1. 查 DB role 1803 权限
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("""
    SELECT p.code FROM role_permissions rp
    JOIN permissions p ON p.id = rp.permission_id
    WHERE rp.role_id = 1803
    ORDER BY p.code
""")
db_perms = [r[0] for r in cur.fetchall()]
print(f'DB role 1803 权限 ({len(db_perms)}):')
for p in db_perms:
    print(f'  {p}')
print(f'  含 version:create: {"version:create" in db_perms}')
print(f'  含 version:read: {"version:read" in db_perms}')
conn.close()

# 2. 调 API 看返回
sess = requests.Session()
sess.get(f'{BASE}/api/v1/auth/dev-login?username=admin', allow_redirects=False)
r = sess.get(f'{BASE}/api/v1/roles/1803/unified-permissions')
data = r.json()['data']
print()
for m in data['menus']:
    if m['menu_code'] == 'product-management':
        print(f'API 返回 product-management 菜单:')
        for p in m['required_permissions']:
            print(f'  {p["code"]:30s} granted={p["granted"]} source={p["source"]}')
        break
