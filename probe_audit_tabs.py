"""
测试 domain / sub_domain / relationship 详情页操作日志 tab API
"""
import requests
base = 'http://localhost:3010'
r = requests.post(f'{base}/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
token = r.json()['data']['token']
cookies = {'auth_token': token}
print('Login OK')

# 1. 查找一个 domain
r = requests.get(f'{base}/api/v2/bo/domain?page=1&page_size=3', cookies=cookies, timeout=5)
print(f'\n=== /api/v2/bo/domain ===')
print(f'status: {r.status_code}')
if r.status_code == 200 and r.json().get('data', {}).get('items'):
    items = r.json()['data']['items']
    print(f'items count: {len(items)}')
    if items:
        domain_id = items[0]['id']
        print(f'first domain: id={domain_id} code={items[0].get("code")}')
    else:
        domain_id = None
else:
    print(f'body: {r.text[:300]}')
    domain_id = None

# 2. 查找一个 sub_domain
r = requests.get(f'{base}/api/v2/bo/sub_domain?page=1&page_size=3', cookies=cookies, timeout=5)
print(f'\n=== /api/v2/bo/sub_domain ===')
print(f'status: {r.status_code}')
if r.status_code == 200 and r.json().get('data', {}).get('items'):
    items = r.json()['data']['items']
    print(f'items count: {len(items)}')
    if items:
        sub_domain_id = items[0]['id']
        print(f'first sub_domain: id={sub_domain_id} code={items[0].get("code")}')
    else:
        sub_domain_id = None
else:
    print(f'body: {r.text[:300]}')
    sub_domain_id = None

# 3. 查找一个 relationship
r = requests.get(f'{base}/api/v2/bo/relationship?page=1&page_size=3', cookies=cookies, timeout=5)
print(f'\n=== /api/v2/bo/relationship ===')
print(f'status: {r.status_code}')
if r.status_code == 200 and r.json().get('data', {}).get('items'):
    items = r.json()['data']['items']
    print(f'items count: {len(items)}')
    if items:
        relationship_id = items[0]['id']
        print(f'first relationship: id={relationship_id} code={items[0].get("code")}')
    else:
        relationship_id = None
else:
    print(f'body: {r.text[:300]}')
    relationship_id = None

# 4. 测 audit_logs API (前端 HistorySection 调用的)
print(f'\n=== audit_logs API ===')
for ot, oid in [
    ('domain', domain_id),
    ('sub_domain', sub_domain_id),
    ('relationship', relationship_id),
]:
    if oid is None:
        print(f'  SKIP {ot} (no id)')
        continue
    r = requests.get(f'{base}/api/v1/audit/logs?object_type={ot}&object_id={oid}&page=1&page_size=5', cookies=cookies, timeout=5)
    print(f'  GET /audit/logs?object_type={ot}&object_id={oid}')
    print(f'    status: {r.status_code} body[:200]: {r.text[:200]}')
