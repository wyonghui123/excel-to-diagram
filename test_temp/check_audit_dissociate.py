# -*- coding: utf-8 -*-
"""检查审计日志关联表 + ASSOCIATE 详情"""
import sqlite3
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'meta', 'architecture.db'
)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

print('=== ASSOCIATE 全部记录详情 ===')
c.execute("""
SELECT id, object_type, object_id, user_name, field_name, old_value, new_value, created_at
FROM audit_logs
WHERE action='ASSOCIATE'
ORDER BY id DESC LIMIT 20
""")
for row in c.fetchall():
    print(f'  {row}')

print()
print('=== ASSOCIATE_OBJECT 全部记录详情 ===')
c.execute("""
SELECT id, object_type, object_id, user_name, field_name, old_value, new_value, created_at
FROM audit_logs
WHERE action='ASSOCIATE_OBJECT'
ORDER BY id DESC LIMIT 20
""")
for row in c.fetchall():
    print(f'  {row}')

print()
print('=== user_group 的所有 action ===')
c.execute("""
SELECT action, COUNT(*) FROM audit_logs
WHERE object_type='user_group'
GROUP BY action
""")
for row in c.fetchall():
    print(f'  {row}')

print()
print('=== 用户组成员关联表记录数 ===')
c.execute("SELECT COUNT(*) FROM user_group_members")
print(f'  user_group_members: {c.fetchone()[0]}')

print()
print('=== DELETE_OBJECT 全部记录 ===')
c.execute("""
SELECT id, object_type, object_id, user_name, field_name, old_value, new_value, created_at
FROM audit_logs
WHERE action IN ('DELETE_OBJECT','DELETE')
ORDER BY id DESC LIMIT 10
""")
for row in c.fetchall():
    print(f'  {row}')

print()
print('=== 列出所有 action 类型 (确认是否有 DISSOCIATE_*) ===')
c.execute("SELECT DISTINCT action FROM audit_logs ORDER BY action")
for row in c.fetchall():
    print(f'  {row[0]}')

conn.close()
