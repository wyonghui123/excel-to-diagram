# -*- coding: utf-8 -*-
import sqlite3
import os

db_path = r'D:\filework\excel-to-diagram\meta\architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT sql FROM sqlite_master WHERE name='audit_logs'")
print('--- audit_logs DDL ---')
row = cursor.fetchone()
print(row[0] if row else 'NOT FOUND')
print()

print('--- Last 10 audit_logs for user_group ---')
cursor.execute("""
    SELECT id, action, object_type, object_id, field_name, old_value, new_value, created_at, trace_id
    FROM audit_logs
    WHERE object_type = 'user_group'
    ORDER BY id DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(row)
print()

print('--- Users with null/empty display_name ---')
cursor.execute("SELECT id, username, display_name FROM users WHERE display_name IS NULL OR display_name='' LIMIT 5")
for row in cursor.fetchall():
    print(row)
print()

print('--- Sample audit log with action=ASSOCIATE/DISSOCIATE ---')
cursor.execute("""
    SELECT id, action, object_type, object_id, field_name, old_value, new_value, created_at
    FROM audit_logs
    WHERE action IN ('ASSOCIATE', 'DISSOCIATE')
    ORDER BY id DESC
    LIMIT 5
""")
for row in cursor.fetchall():
    print(row)
print()

conn.close()
