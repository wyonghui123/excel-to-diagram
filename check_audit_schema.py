import sqlite3
import time
conn = sqlite3.connect('meta/architecture.db')

# 1. 查看 audit_logs 表是否有 status 列
cur = conn.execute("PRAGMA table_info(audit_logs)")
columns = [row[1] for row in cur.fetchall()]
print("audit_logs columns:", columns)
print("Has 'status' column:", 'status' in columns)

# 2. 查看最新的几条 audit_logs，看是否有 retry worker 创建的记录
cur = conn.execute("""
    SELECT id, action, status, created_at, extra_data
    FROM audit_logs
    ORDER BY id DESC
    LIMIT 10
""")

print("\nLatest 10 audit_logs:")
for row in cur.fetchall():
    print(f"ID={row[0]}, action={row[1]}, status={row[2]}, time={row[3]}")
    if row[4]:
        print(f"  extra_data: {row[4][:150]}")

conn.close()
