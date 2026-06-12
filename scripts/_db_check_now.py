"""直接查 DB 当前状态"""
import sqlite3

DB = r'D:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
    SELECT p.code FROM role_permissions rp
    JOIN permissions p ON p.id = rp.permission_id
    WHERE rp.role_id = 1803
    ORDER BY p.code
""")
perms = [r[0] for r in cur.fetchall()]
print(f'role 1803 当前权限 ({len(perms)}):')
for p in perms:
    print(f'  {p}')
print()
print(f'  version:read: {"version:read" in perms}')
print(f'  version:create: {"version:create" in perms}')

conn.close()
