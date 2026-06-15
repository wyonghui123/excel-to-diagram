import requests
import json

s = requests.Session()
login_resp = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
print('Login:', login_resp.status_code)

# Query product list to see child_count value
resp = s.post('http://localhost:3010/api/v1/search', json={
    'object_type': 'product',
    'page': 1,
    'page_size': 5
})
print('Status:', resp.status_code)
if resp.status_code == 200:
    result = resp.json()
    print('Success:', result.get('success'))
    data = result.get('data', {}).get('data', [])
    for row in data:
        print(f"  id={row.get('id')}, name={row.get('name')}, code={row.get('code')}, child_count={row.get('child_count')}, is_active={row.get('is_active')}")
