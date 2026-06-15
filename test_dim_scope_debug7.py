import requests, json
s = requests.Session()

# dev-login as TEST888
r = s.get('http://localhost:3010/api/v1/auth/dev-login', params={'username': 'TEST888'})
print('Login:', r.json().get('success'))

# Query product with page_size=5
r = s.get('http://localhost:3010/api/v2/bo/product', params={'page_size': 5})
data = r.json()
print(f'\nProduct API response:')
print(f'  success: {data.get("success")}')
items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
print(f'  items count: {len(items)}')
if items:
    for p in items[:3]:
        print(f'    id={p.get("id")} name={p.get("name","")}')

# Also check the _do_list debug log
import os
log_path = r'D:\filework\excel-to-diagram\logs\_dbg_do_list.log'
if os.path.exists(log_path):
    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Get last 2000 chars
    print(f'\n_do_list debug log (last 2000 chars):')
    print(content[-2000:])
