"""Direct test: hit service_module list, watch log."""
import requests, time
BASE = 'http://localhost:3010'

# Watch server log
import subprocess
import os
log_file = r'D:\filework\excel-to-diagram\logs\app.jsonl'

# Login
test60 = requests.Session()
r = test60.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)
print(f'login: {r.status_code}')

# Call service_module
print()
print('=== service_module list v=1 ===')
r = test60.post(f'{BASE}/api/v2/bo/service_module/list', json={'version_id': 1, 'page_size': 100}, timeout=10)
print(f'status: {r.status_code}')
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f'count: {len(items) if isinstance(items, list) else "?"}')
if isinstance(items, list) and items:
    print(f'sample: {items[0]}')
print()
print('--- response ---')
print(r.text[:500])
