import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 检查 user_group-list 的完整信息
cursor.execute('''
    SELECT menu_code, menu_name, menu_path, page_type, parent_menu, show_in_sidebar, is_active, bo_bindings, primary_object_type
    FROM menus
    WHERE menu_code = 'user_group-list'
''')
row = cursor.fetchone()

print("user_group-list 完整信息:")
if row:
    for i, col in enumerate(['menu_code', 'menu_name', 'menu_path', 'page_type', 'parent_menu', 'show_in_sidebar', 'is_active', 'bo_bindings', 'primary_object_type']):
        print(f"  {col}: {row[i]}")

# 检查父菜单
if row[4]:  # parent_menu
    cursor.execute('''
        SELECT menu_code, menu_name, menu_path, page_type, parent_menu, show_in_sidebar
        FROM menus
        WHERE menu_code = ?
    ''', [row[4]])
    parent = cursor.fetchone()
    if parent:
        print(f"\n父菜单 ({row[4]}):")
        for i, col in enumerate(['menu_code', 'menu_name', 'menu_path', 'page_type', 'parent_menu', 'show_in_sidebar']):
            print(f"  {col}: {parent[i]}")

conn.close()
