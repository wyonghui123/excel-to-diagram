# -*- coding: utf-8 -*-
import sqlite3

db_path = r'D:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('--- User 1378 ---')
cursor.execute("SELECT id, username, display_name FROM users WHERE id = 1378")
row = cursor.fetchone()
print(row)
print()

print('--- All DISSOCIATE audit logs ---')
cursor.execute("""
    SELECT id, action, object_type, object_id, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE action IN ('DISASSOCIATE', 'DISSOCIATE')
    ORDER BY id DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- user_group_members for group 403 ---')
cursor.execute("""
    SELECT group_id, user_id FROM user_group_members WHERE group_id = 403
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- group_roles for group 403 ---')
cursor.execute("""
    SELECT group_id, role_id FROM group_roles WHERE group_id = 403
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- All CREATE/UPDATE on user_group with field_name != _record ---')
cursor.execute("""
    SELECT id, action, field_name, old_value, new_value
    FROM audit_logs
    WHERE object_type = 'user_group' AND action IN ('CREATE','UPDATE') AND field_name != '_record'
    ORDER BY id DESC LIMIT 10
""")
for row in cursor.fetchall():
    print(row)
print()

conn.close()
