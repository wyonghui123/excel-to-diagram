import requests

# 使用 session 来保持 cookie
session = requests.Session()

# 1. dev-login
resp = session.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
print(f"Login status: {resp.status_code}")
print(f"Login response: {resp.json()}")

# 2. 获取可见菜单
resp = session.get('http://localhost:3010/api/v1/menu-permission/visible')
print(f"\nMenu status: {resp.status_code}")
data = resp.json()
print(f"Menu count: {len(data.get('menus', []))}")
print(f"Menus: {[m['menu_code'] for m in data.get('menus', [])]}")
