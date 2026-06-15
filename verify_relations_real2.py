"""Hit server endpoint, observe registry state via response."""
import requests, json

BASE = 'http://localhost:3010'
test60 = requests.Session()
r = test60.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)
print(f'login: {r.status_code}')

# 1. Check if TEST60 can see ANY object with version filter
print()
print('=== service_module list ===')
r = test60.post(f'{BASE}/api/v2/bo/service_module/list', json={'version_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f'  TEST60 v=1: {len(items) if isinstance(items, list) else "?"} SMs')

print()
print('=== relationship list (v2) ===')
r = test60.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f'  TEST60 v=1: {len(items) if isinstance(items, list) else "?"} relationships')

# Check the diagnostic endpoint
print()
print('=== diagnostics (admin) ===')
admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)
r = admin.get(f'{BASE}/api/v2/action/_diagnostics', timeout=5)
data = r.json()
if data.get('success'):
    d = data['data']
    print(f'  keys: {list(d.keys())[:5]}')
