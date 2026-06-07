import sqlite3

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 查找包含 user 的菜单
cursor.execute('''
    SELECT menu_code, menu_name, menu_path, page_type, primary_object_type
    FROM menus
    WHERE menu_code LIKE '%user%' OR menu_name LIKE '%用户%'
    ORDER BY sort_order
''')
rows = cursor.fetchall()

print("User-related menus:")
print("-" * 120)
for r in rows:
    print(f"code={r[0]:25} name={r[1]:20} path={r[2] or 'NULL':25} type={r[3]:20} object={r[4] or 'NULL'}")

conn.close()
