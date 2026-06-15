"""直接测试 v2 BO 创建 domain/sub_domain 并验证审计日志"""
import requests
import time

r = requests.post('http://localhost:3010/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
cookies = {'auth_token': r.json()['data']['token']}
print(f'Login: {r.status_code}')

ts = int(time.time())
# 创建 domain
r = requests.post('http://localhost:3010/api/v2/bo/domain',
    cookies=cookies,
    json={'code': f'TEST_AUDIT_{ts}', 'name': 'TEST', 'version_id': 1},
    timeout=5)
print(f'POST domain: {r.status_code}')
if r.status_code in (200, 201):
    domain_id = r.json()['data']['id']
    print(f'  domain_id: {domain_id}')

# 创建 sub_domain
r = requests.post('http://localhost:3010/api/v2/bo/sub_domain',
    cookies=cookies,
    json={'code': f'TEST_SD_{ts}', 'name': 'TEST', 'domain_id': 1, 'version_id': 1},
    timeout=5)
print(f'POST sub_domain: {r.status_code}')

# 等待 1 秒让 async audit writer 完成
time.sleep(2)

# 验证 audit log
for ot, oid in [('domain', 1), ('sub_domain', 1)]:
    r = requests.get(f'http://localhost:3010/api/v1/audit/logs?object_type={ot}&object_id={oid}&parent_object_id={oid}&page=1&page_size=3', cookies=cookies, timeout=5)
    data = r.json()
    print(f'  /audit/logs {ot}/{oid} parent={oid}: status={r.status_code} total={data.get("total")} items={len(data.get("data", []))}')

# AUDIT_WRITE_FAILED 计数
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED' AND status='failed'")
print(f'\nAUDIT_WRITE_FAILED (status=failed): {cur.fetchone()[0]}')
conn.close()
