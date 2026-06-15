import requests
import json

# 创建 session 用于保持登录状态
session = requests.Session()

# 先登录
print("=== 0. Login ===")
login_resp = session.post(
    "http://localhost:3010/api/v1/auth/login",
    json={"username": "admin", "password": "admin123"}
)
print(f"Login status: {login_resp.status_code}")
print(f"Login response: {login_resp.json()}")

if login_resp.status_code != 200:
    print("Login failed, cannot test retry worker")
    exit(1)

base_url = "http://localhost:3010/api/v1/audit"

# 1. 检查 retry worker 状态
print("\n=== 1. Check retry worker status ===")
resp = session.get(f"{base_url}/retry/status")
print(f"Status: {resp.status_code}")
print(f"Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")

# 2. 手动触发 retry
print("\n=== 2. Trigger retry worker ===")
resp = session.post(f"{base_url}/retry/trigger")
print(f"Status: {resp.status_code}")
print(f"Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")

# 3. 再次检查状态
print("\n=== 3. Check status after trigger ===")
resp = session.get(f"{base_url}/retry/status")
print(f"Status: {resp.status_code}")
print(f"Response: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")

# 4. 检查数据库中 AUDIT_WRITE_FAILED 的变化
print("\n=== 4. Check database changes ===")
import sqlite3
conn = sqlite3.connect('meta/architecture.db')

# 统计各状态的数量
cursor = conn.execute("""
    SELECT status, COUNT(*) as count
    FROM audit_logs
    WHERE action='AUDIT_WRITE_FAILED'
    GROUP BY status
""")
print("AUDIT_WRITE_FAILED by status:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]}")

# 查看是否有 retried 状态的记录
cursor = conn.execute("""
    SELECT id, object_type, object_id, action, status, created_at
    FROM audit_logs
    WHERE status='retried'
    ORDER BY id DESC
    LIMIT 5
""")
print("\nLatest retried records:")
for row in cursor.fetchall():
    print(f"  ID={row[0]}, obj={row[1]}#{row[2]}, action={row[3]}, status={row[4]}, time={row[5]}")

conn.close()
