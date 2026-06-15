import requests
import json
s = requests.Session()
s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')

# Get product list
r = s.get('http://localhost:3010/api/v2/bo/product?page_size=20')
data = r.json()
items = data.get('data', {}).get('items', data.get('data', []))
print(f"Found {len(items)} products:")
for p in items[:20]:
    print(f"  {p.get('id')}: name={p.get('name')}, code={p.get('code')}, child_count={p.get('child_count')}")

# Get version 1 details
r = s.get('http://localhost:3010/api/v2/bo/version/1')
data = r.json()
v = data.get('data', {})
print(f"\nVersion 1 details: id={v.get('id')}, name={v.get('name')}, product_id={v.get('product_id')}")
