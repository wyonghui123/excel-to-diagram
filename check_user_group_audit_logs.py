import sqlite3
import json

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 查询最新的审计日志
cursor.execute('''
    SELECT * FROM audit_logs 
    WHERE object_type='user_group'
    ORDER BY created_at DESC 
    LIMIT 20
''')

logs = cursor.fetchall()
cols = [desc[0] for desc in cursor.description]

print(f"找到 {len(logs)} 条用户组审计日志:\n")
for log in logs:
    log_dict = dict(zip(cols, log))
    print(f"ID: {log_dict['id']}")
    print(f"  Object ID: {log_dict['object_id']}")
    print(f"  Action: {log_dict['action']}")
    print(f"  Field: {log_dict['field_name']}")
    print(f"  User: {log_dict['user_name']}")
    print(f"  Time: {log_dict['created_at']}")
    print("-" * 80)

conn.close()
