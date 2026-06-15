# -*- coding: utf-8 -*-
import sqlite3

db_path = r'D:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('--- All audit_logs for user_group 403 ---')
cursor.execute("""
    SELECT id, action, field_name, old_value, new_value, created_at, trace_id
    FROM audit_logs
    WHERE object_type = 'user_group' AND object_id = '403'
    ORDER BY id ASC
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- Total counts by action ---')
cursor.execute("""
    SELECT action, COUNT(*) FROM audit_logs WHERE object_type = 'user_group' AND object_id = '403'
    GROUP BY action
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- DISSOCIATE audit_logs for any user_group ---')
cursor.execute("""
    SELECT id, action, object_type, object_id, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE action = 'DISSOCIATE' OR action = 'DISASSOCIATE'
    LIMIT 10
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- ASSOCIATE audit_logs for user_group 403 ---')
cursor.execute("""
    SELECT id, action, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE object_type = 'user_group' AND object_id = '403' AND action = 'ASSOCIATE'
    ORDER BY id ASC
""")
for row in cursor.fetchall():
    print(row)
print()

conn.close()
