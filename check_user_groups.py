# -*- coding: utf-8 -*-
import sqlite3

db_path = r'd:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== Admin 用户 ===')
cursor.execute("SELECT id, username, display_name FROM users WHERE username = 'admin'")
admin = cursor.fetchone()
print(f'Admin: {admin}')

print('\n=== 所有用户组 ===')
cursor.execute('SELECT id, code, name FROM user_groups')
groups = cursor.fetchall()
for g in groups:
    print(f'  {g}')

print('\n=== Admin 用户组成员关系 ===')
if admin:
    cursor.execute('''
        SELECT ug.id, ug.code, ug.name, ugm.is_manager
        FROM user_group_members ugm
        JOIN user_groups ug ON ugm.group_id = ug.id
        WHERE ugm.user_id = ?
    ''', (admin[0],))
    memberships = cursor.fetchall()
    if memberships:
        for m in memberships:
            print(f'  {m}')
    else:
        print('  (无关联)')
else:
    print('  (Admin 用户不存在)')

print('\n=== 所有用户组成员关系 ===')
cursor.execute('''
    SELECT u.username, ug.code, ug.name
    FROM user_group_members ugm
    JOIN users u ON ugm.user_id = u.id
    JOIN user_groups ug ON ugm.group_id = ug.id
''')
all_members = cursor.fetchall()
if all_members:
    for m in all_members:
        print(f'  {m}')
else:
    print('  (无关联)')

conn.close()
