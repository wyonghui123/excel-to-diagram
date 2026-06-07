import sqlite3
import json

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 查询错误审计日志前后的所有审计日志
cursor.execute('''
    SELECT * FROM audit_logs 
    WHERE created_at >= '2026-05-09T22:05:51.000000'
    AND created_at <= '2026-05-09T22:05:52.000000'
    ORDER BY created_at ASC
''')

logs = cursor.fetchall()
cols = [desc[0] for desc in cursor.description]

print(f"找到 {len(logs)} 条审计日志:\n")
for log in logs:
    log_dict = dict(zip(cols, log))
    print(f"ID: {log_dict['id']}")
    print(f"  Object Type: {log_dict['object_type']}")
    print(f"  Object ID: {log_dict['object_id']}")
    print(f"  Action: {log_dict['action']}")
    print(f"  Field: {log_dict['field_name']}")
    print(f"  User: {log_dict['user_name']}")
    print(f"  Trace ID: {log_dict['trace_id']}")
    print(f"  Transaction ID: {log_dict['transaction_id']}")
    print("-" * 80)

conn.close()
