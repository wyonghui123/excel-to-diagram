"""Find correct sub_domain path."""
import requests

BASE = 'http://localhost:3010'

a = requests.Session()
a.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)

# What is the correct way to list sub_domain?
# Try meta endpoint
r = a.get(f'{BASE}/api/v2/meta/sub_domain/full', timeout=5)
print(f'/api/v2/meta/sub_domain/full: {r.status_code}')
if r.status_code == 200:
    d = r.json().get('data', {})
    print(f'  data keys: {list(d.keys())[:5]}')

# Try list as no id
for path in [
    '/api/v2/bo/sub_domain',
    '/api/v2/meta/sub_domain/list',
    '/api/v2/meta/sub_domain',
]:
    r = a.get(f'{BASE}{path}', timeout=5)
    print(f'{path}: {r.status_code} {r.text[:120]}')

# Look at routes
print()
print("--- routes containing sub_domain ---")
import sys
sys.path.insert(0, '.')
import logging
logging.disable(logging.CRITICAL)
from meta.server import create_app
app = create_app()
with app.app_context():
    for r in sorted(app.url_map.iter_rules(), key=lambda x: x.rule):
        if 'sub_domain' in r.rule:
            print(f'  {list(r.methods - {"HEAD", "OPTIONS"})}  {r.rule}  -> {r.endpoint}')

# Try the actual call with sub_domain_id=1 filter
print()
print("--- /api/v1/relationships?version_id=1&sub_domain_id=1 ---")
r = a.get(f'{BASE}/api/v1/relationships', params={'version_id': 1, 'sub_domain_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f'  admin: {len(items) if isinstance(items, list) else "?"} items')

t = requests.Session()
t.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)
r = t.get(f'{BASE}/api/v1/relationships', params={'version_id': 1, 'sub_domain_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f'  TEST60: {len(items) if isinstance(items, list) else "?"} items')
