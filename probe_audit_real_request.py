import requests
r = requests.post('http://localhost:3010/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
cookies = {'auth_token': r.json()['data']['token']}

# 模拟前端真实请求 - 关键: 带着 parent_object_id
for ot, oid in [('domain', 683), ('sub_domain', 68), ('relationship', 35)]:
    url = f'http://localhost:3010/api/v1/audit/logs?page=1&page_size=20&object_type={ot}&object_id={oid}&parent_object_id={oid}'
    r = requests.get(url, cookies=cookies, timeout=5)
    data = r.json()
    items = data.get('data', [])
    total = data.get('total')
    print(f'  {ot}/{oid} parent={oid}: status={r.status_code} total={total} items_count={len(items)}')

print()
print('=== 不带 parent_object_id ===')
for ot, oid in [('domain', 683), ('sub_domain', 68), ('relationship', 35)]:
    url = f'http://localhost:3010/api/v1/audit/logs?page=1&page_size=20&object_type={ot}&object_id={oid}'
    r = requests.get(url, cookies=cookies, timeout=5)
    data = r.json()
    items = data.get('data', [])
    total = data.get('total')
    print(f'  {ot}/{oid}: status={r.status_code} total={total} items_count={len(items)}')
