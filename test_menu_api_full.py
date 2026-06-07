import requests
import json

# 使用 session 来保持 cookie
session = requests.Session()

# 1. dev-login
resp = session.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
print(f"Login status: {resp.status_code}")
data = resp.json()
token = data.get('data', {}).get('user', {}).get('user_id')

# 2. 获取可见菜单
resp = session.get('http://localhost:3010/api/v1/menu-permission/visible')
print(f"\nMenu status: {resp.status_code}")
data = resp.json()
menus = data.get('menus', [])
print(f"Menu count: {len(menus)}")

# 打印所有菜单
for m in menus:
    print(f"\n{m['menu_code']}:")
    print(f"  name: {m['menu_name']}")
    print(f"  path: {m['menu_path']}")
    print(f"  page_type: {m['page_type']}")
    print(f"  primary_object_type: {m.get('primary_object_type', '')}")
    print(f"  parent_menu: {m.get('parent_menu', '')}")
    print(f"  children: {len(m.get('children', []))}")
    if m.get('children'):
        for c in m['children']:
            print(f"    - {c['menu_code']}: {c['menu_name']} ({c.get('menu_path', '')})")
