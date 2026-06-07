import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 查找 user-permission 及其子菜单
cursor.execute('''
    SELECT menu_code, menu_name, menu_path, page_type, parent_menu
    FROM menus
    WHERE menu_code = 'user-permission' 
       OR parent_menu = 'user-permission'
    ORDER BY sort_order
''')
rows = cursor.fetchall()

print("user-permission 菜单及其子菜单:")
print("-" * 120)
for r in rows:
    print(f"code={r[0]:25} name={r[1]:20} path={r[2] or 'NULL':25} type={r[3]:20} parent={r[4] or 'NULL'}")

# 检查是否有 show_in_sidebar 标志
cursor.execute('''
    SELECT menu_code, menu_name, menu_path, show_in_sidebar, is_active
    FROM menus
    WHERE menu_code = 'user_group-list'
''')
row = cursor.fetchone()
if row:
    print(f"\nuser_group-list 详情:")
    print(f"  code={row[0]} name={row[1]} path={row[2]} show_in_sidebar={row[3]} is_active={row[4]}")

conn.close()
