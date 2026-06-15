import requests
import time

# 测试 audit retry worker API
API_BASE = "http://localhost:3010"

# 1. 检查 retry worker 是否启动
print("=== 1. Check retry worker status ===")
try:
    r = requests.get(f"{API_BASE}/api/v1/audit/retry/status", timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")
except Exception as e:
    print(f"Error: {e}")

# 2. 手动触发 retry
print("\n=== 2. Trigger retry manually ===")
try:
    r = requests.post(f"{API_BASE}/api/v1/audit/retry/trigger", timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")
except Exception as e:
    print(f"Error: {e}")

# 3. 等待 5 秒后再次检查状态
print("\n=== 3. Check status after retry ===")
time.sleep(5)
try:
    r = requests.get(f"{API_BASE}/api/v1/audit/retry/status", timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")
except Exception as e:
    print(f"Error: {e}")

# 4. 检查数据库中 AUDIT_WRITE_FAILED 数量
print("\n=== 4. Check AUDIT_WRITE_FAILED count in DB ===")
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED' AND status='failed'")
failed_count = cur.fetchone()[0]
print(f"Failed (pending retry): {failed_count}")

cur = conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED' AND status='retried'")
retried_count = cur.fetchone()[0]
print(f"Retried: {retried_count}")
conn.close()
