import requests, json
s = requests.Session()

# dev-login as TEST888
r = s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST888'})
print('Login:', r.json().get('success'))

# Query product with large page_size to see total
r = s.get('http://localhost:3010/api/v2/bo/product', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
total = data.get('data', {}).get('total', 'N/A') if isinstance(data.get('data'), dict) else 'N/A'
print(f'Products: {len(items)} items, total={total}')
for p in items[:10]:
    print(f'  id={p.get("id")} name={p.get("name","")}')

# Query domain
r = s.get('http://localhost:3010/api/v2/bo/domain', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
total = data.get('data', {}).get('total', 'N/A') if isinstance(data.get('data'), dict) else 'N/A'
print(f'\nDomains: {len(items)} items, total={total}')
for d in items[:10]:
    print(f'  id={d.get("id")} name={d.get("name","")} version_id={d.get("version_id")}')

# Query sub_domain
r = s.get('http://localhost:3010/api/v2/bo/sub_domain', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
total = data.get('data', {}).get('total', 'N/A') if isinstance(data.get('data'), dict) else 'N/A'
print(f'\nSub_domains: {len(items)} items, total={total}')
for sd in items[:10]:
    print(f'  id={sd.get("id")} name={sd.get("name","")} domain_id={sd.get("domain_id")}')

# Query service_module
r = s.get('http://localhost:3010/api/v2/bo/service_module', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
total = data.get('data', {}).get('total', 'N/A') if isinstance(data.get('data'), dict) else 'N/A'
print(f'\nService_modules: {len(items)} items, total={total}')
for sm in items[:5]:
    print(f'  id={sm.get("id")} name={sm.get("name","")} sub_domain_id={sm.get("sub_domain_id")}')

# Query business_object
r = s.get('http://localhost:3010/api/v2/bo/business_object', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
total = data.get('data', {}).get('total', 'N/A') if isinstance(data.get('data'), dict) else 'N/A'
print(f'\nBusiness_objects: {len(items)} items, total={total}')
for bo in items[:5]:
    print(f'  id={bo.get("id")} name={bo.get("name","")} service_module_id={bo.get("service_module_id")}')
