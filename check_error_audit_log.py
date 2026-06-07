import sqlite3
import json

conn = sqlite3.connect('meta/architecture.db')
cursor = conn.cursor()

# 查询那条错误的审计日志
cursor.execute('''
    SELECT * FROM audit_logs 
    WHERE object_type='user_group' 
    AND object_id='True'
    ORDER BY created_at DESC 
    LIMIT 1
''')

log = cursor.fetchone()
if log:
    cols = [desc[0] for desc in cursor.description]
    log_dict = dict(zip(cols, log))
    
    print("错误的审计日志详情:")
    print(json.dumps(log_dict, indent=2, ensure_ascii=False))
    print("\n" + "=" * 80 + "\n")
    
    # 查询同一时间段的其他审计日志
    cursor.execute('''
        SELECT * FROM audit_logs 
        WHERE created_at >= ? AND created_at <= ?
        AND object_type='user_group'
        ORDER BY created_at ASC
    ''', (log_dict['created_at'], log_dict['created_at']))
    
    related_logs = cursor.fetchall()
    print(f"同一时间段的相关审计日志（共 {len(related_logs)} 条）:")
    for related_log in related_logs:
        related_dict = dict(zip(cols, related_log))
        print(f"  - ID: {related_dict['id']}, Action: {related_dict['action']}, "
              f"Field: {related_dict['field_name']}, ObjectID: {related_dict['object_id']}")

conn.close()
