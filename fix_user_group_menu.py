import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 更新 user_group-list 菜单的 show_in_sidebar
cursor.execute('''
    UPDATE menus
    SET show_in_sidebar = 1
    WHERE menu_code = 'user_group-list'
''')

print(f"Updated rows: {cursor.rowcount}")

# 验证
cursor.execute('SELECT menu_code, menu_name, menu_path, show_in_sidebar FROM menus WHERE menu_code = ?', ['user_group-list'])
row = cursor.fetchone()
print(f"After update: code={row[0]}, name={row[1]}, path={row[2]}, show_in_sidebar={row[3]}")

conn.commit()
conn.close()
