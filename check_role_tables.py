import sqlite3
conn = sqlite3.connect('meta/architecture.db')

# Check role_menu_permissions table structure
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='role_menu_permissions'")
result = cursor.fetchone()
if result:
    print('[OK] role_menu_permissions table structure:')
    print(result[0])
    print()

# Check data_permissions table structure
cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='data_permissions'")
result = cursor.fetchone()
if result:
    print('[OK] data_permissions table structure:')
    print(result[0])

conn.close()
