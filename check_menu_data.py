import sqlite3
import json

conn = sqlite3.connect('d:/filework/excel-to-diagram/architecture.db')
cursor = conn.cursor()

print("=== 现有菜单数据 ===")
cursor.execute("""
    SELECT id, menu_code, menu_name, menu_path, required_permissions 
    FROM menu_permissions 
    ORDER BY sort_order
""")
menus = cursor.fetchall()

for menu in menus:
    mid, code, name, path, perms = menu
    print(f"\n[{mid}] {name} ({code})")
    print(f"  路径: {path}")
    
    if perms:
        try:
            perm_list = json.loads(perms)
            print(f"  关联权限: {len(perm_list)} 个")
            for p in perm_list[:5]:
                print(f"    • {p}")
            if len(perm_list) > 5:
                print(f"    ... 还有 {len(perm_list) - 5} 个")
        except Exception as e:
            print(f"  权限数据格式错误: {e}")
            print(f"  原始值: {perms}")
    else:
        print(f"  [WARNING]  权限字段为空!")

conn.close()
