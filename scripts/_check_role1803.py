# -*- coding: utf-8 -*-
"""[Debug] 查 role 1803 详情"""
import sqlite3
import os

db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'architecture.db')
conn = sqlite3.connect(db)
cursor = conn.cursor()

cursor.execute("SELECT id, name, code FROM roles WHERE id = 1803")
r = cursor.fetchone()
print(f'Role 1803: {r}')

# role 1803 perms
cursor.execute('''SELECT p.code FROM permissions p
                  JOIN role_permissions rp ON rp.permission_id = p.id
                  WHERE rp.role_id = 1803''')
perms = [r[0] for r in cursor.fetchall()]
print(f'Role 1803 perms ({len(perms)}):')
for p in sorted(perms):
    print(f'  - {p}')

# role 1803 menus
cursor.execute("SELECT menu_code FROM role_menu_permissions WHERE role_id = 1803")
menus = [r[0] for r in cursor.fetchall()]
print(f'Role 1803 menus: {menus}')

# menu perm details
for menu_code in menus:
    cursor.execute("SELECT required_permissions FROM menu_permissions WHERE menu_code = ?", [menu_code])
    m = cursor.fetchone()
    print(f'  {menu_code} required_perms: {m[0] if m else None}')

# Check if user_group_roles is empty
cursor.execute("SELECT COUNT(*) FROM user_group_roles")
print(f'\nuser_group_roles total rows: {cursor.fetchone()[0]}')

# Check schema
cursor.execute("PRAGMA table_info(user_group_roles)")
print(f'user_group_roles columns: {[r[1] for r in cursor.fetchall()]}')

# Check all groups -> roles links
cursor.execute("SELECT * FROM user_group_roles LIMIT 5")
print(f'Sample user_group_roles: {cursor.fetchall()}')

conn.close()
