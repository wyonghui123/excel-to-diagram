"""Check TEST60's actual menu grants in DB and via API"""
import sqlite3
import requests

# 1. Check DB directly
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("""
    SELECT rmp.menu_code
    FROM role_menu_permissions rmp
    JOIN roles r ON rmp.role_id = r.id
    JOIN user_group_members ugm ON r.id = 1803
    WHERE rmp.role_id IN (SELECT role_id FROM group_roles WHERE group_id IN (SELECT group_id FROM user_group_members WHERE user_id = 1223))
    GROUP BY rmp.menu_code
""")
db_menus = [r[0] for r in cur.fetchall()]
print(f"DB role_menu_permissions for TEST60: {db_menus}")

# 2. Check via API as TEST60
s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST60'})

r = s.get('http://localhost:3010/api/v1/menu-permission/visible')
data = r.json().get('data', {})
leafs = [m['menu_code'] for m in data.get('leaf_menus', [])]
menus = [m['menu_code'] for m in data.get('menus', [])]
print(f"API leaf_menus for TEST60: {leafs}")
print(f"API menus for TEST60: {menus}")

# 3. Check user permissions
r = s.get('http://localhost:3010/api/v1/users/me')
perms = r.json().get('data', {}).get('permissions', [])
print(f"TEST60 permissions ({len(perms)}): {perms}")
