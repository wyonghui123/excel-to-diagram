import requests
s = requests.Session()

# 1. dev-login as TEST888 (GET request with username param)
r = s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST888'})
print('Login:', r.status_code, r.json().get('success'))

# 2. 查询 product 列表
r = s.get('http://localhost:3010/api/v2/bo/product', params={'page_size': 1000})
data = r.json()
products = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else data.get('data', [])
print(f'Products: {len(products)} items')
for p in products[:5]:
    pid = p.get('id')
    pname = p.get('name', '')
    print(f'  id={pid} name={pname}')

# 3. 查询 domain 列表
r = s.get('http://localhost:3010/api/v2/bo/domain', params={'page_size': 1000})
data = r.json()
domains = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else data.get('data', [])
print(f'Domains: {len(domains)} items')
for d in domains[:5]:
    did = d.get('id')
    dname = d.get('name', '')
    print(f'  id={did} name={dname}')

# 4. 查询 sub_domain 列表
r = s.get('http://localhost:3010/api/v2/bo/sub_domain', params={'page_size': 1000})
data = r.json()
sub_domains = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else data.get('data', [])
print(f'Sub_domains: {len(sub_domains)} items')
for sd in sub_domains[:5]:
    sid = sd.get('id')
    sname = sd.get('name', '')
    sdomain = sd.get('domain_id')
    print(f'  id={sid} name={sname} domain_id={sdomain}')
