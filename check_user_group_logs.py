import sqlite3
import json
from datetime import datetime

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT * FROM audit_logs 
    WHERE object_type='user_group' 
    AND created_at > '2026-05-09 22:05:50'
    ORDER BY created_at DESC 
    LIMIT 10
''')

logs = cursor.fetchall()
cols = [desc[0] for desc in cursor.description]

print(f"找到 {len(logs)} 条审计日志:\n")
for log in logs:
    log_dict = dict(zip(cols, log))
    print(json.dumps(log_dict, indent=2, ensure_ascii=False))
    print("-" * 80)

conn.close()
