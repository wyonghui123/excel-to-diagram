import sqlite3

db_path = 'D:/filework/excel-to-diagram/meta/architecture.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 查询所有 ASSOCIATE 审计日志
cursor.execute('''
    SELECT id, object_type, object_id, action, field_name, new_value, user_name, created_at
    FROM audit_logs
    WHERE action = 'ASSOCIATE'
    ORDER BY created_at DESC
    LIMIT 10
''')

rows = cursor.fetchall()
print(f'ASSOCIATE logs count: {len(rows)}')
for row in rows:
    print(f'  ID={row[0]}, Object={row[1]}/{row[2]}, Action={row[3]}, Field={row[4]}, NewValue={row[5]}, User={row[6]}, Time={row[7]}')

# 查询最近的审计日志
cursor.execute('''
    SELECT id, object_type, object_id, action, field_name, user_name, created_at
    FROM audit_logs
    ORDER BY created_at DESC
    LIMIT 10
''')

rows = cursor.fetchall()
print(f'\nRecent logs:')
for row in rows:
    print(f'  ID={row[0]}, Object={row[1]}/{row[2]}, Action={row[3]}, Field={row[4]}, User={row[5]}, Time={row[6]}')

conn.close()
