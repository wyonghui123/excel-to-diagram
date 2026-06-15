import sqlite3
conn = sqlite3.connect('meta/architecture.db')

# 查看最新的 AUDIT_WRITE_FAILED 记录
cur = conn.execute("""
    SELECT id, object_type, object_id, action, status, created_at, extra_data
    FROM audit_logs
    WHERE action='AUDIT_WRITE_FAILED'
    ORDER BY id DESC
    LIMIT 5
""")

print("Latest AUDIT_WRITE_FAILED records:")
for row in cur.fetchall():
    print(f"ID={row[0]}, obj={row[1]}#{row[2]}, action={row[3]}, status={row[4]}, time={row[5]}")
    print(f"  extra_data: {row[6][:200] if row[6] else 'None'}")
    print()

conn.close()
