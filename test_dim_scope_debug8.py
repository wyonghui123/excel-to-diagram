import requests, json, time
s = requests.Session()

# dev-login as TEST888
r = s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST888'})
print('Login:', r.json().get('success'))

# Query product
r = s.get('http://localhost:3010/api/v2/bo/product', params={'page_size': 5})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
print(f'Products: {len(items)} items')

# Query domain
r = s.get('http://localhost:3010/api/v2/bo/domain', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
print(f'Domains: {len(items)} items')
if not items:
    print(f'  Full response: {json.dumps(data, indent=2, ensure_ascii=False)[:500]}')

# Query version
r = s.get('http://localhost:3010/api/v2/bo/version', params={'page_size': 1000})
data = r.json()
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
print(f'Versions: {len(items)} items')
for v in items[:3]:
    print(f'  id={v.get("id")} name={v.get("name","")} product_id={v.get("product_id")}')
