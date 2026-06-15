"""Test TEST60 with the EXACT scenario you described."""
import requests

BASE = 'http://localhost:3010'

admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)
test60 = requests.Session()
test60.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)

print("=== TEST60 with v=1, sd_id=1 (采购需求) ===")
for label, sess in [('admin', admin), ('TEST60', test60)]:
    print(f"--- {label} ---")
    r = sess.get(f'{BASE}/api/v1/relationships',
                 params={'version_id': 1, 'sub_domain_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  /api/v1/relationships?version_id=1&sub_domain_id=1: {len(items) if isinstance(items, list) else '?'}")

    r = sess.get(f'{BASE}/api/v1/relationships',
                 params={'version_id': 1, 'domain_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  /api/v1/relationships?version_id=1&domain_id=1: {len(items) if isinstance(items, list) else '?'}")

    r = sess.get(f'{BASE}/api/v1/relationships',
                 params={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  /api/v1/relationships?version_id=1 (no filter): {len(items) if isinstance(items, list) else '?'}")
    print()

# Test direct v2 endpoint
print("=== TEST60 via v2 ===")
r = test60.post(f'{BASE}/api/v2/bo/relationship/list',
                json={'version_id': 1, 'sub_domain_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f"  v2 bo/relationship/list v1 sd=1: {len(items) if isinstance(items, list) else '?'}")

r = test60.post(f'{BASE}/api/v2/bo/relationship/list',
                json={'version_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f"  v2 bo/relationship/list v1 (no filter): {len(items) if isinstance(items, list) else '?'}")

# Try business_object list to confirm v1 has data
print()
print("=== Direct v2/bo/business_object list (no filter) ===")
for label, sess in [('admin', admin), ('TEST60', test60)]:
    r = sess.post(f'{BASE}/api/v2/bo/business_object/list',
                  json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  {label}: {len(items) if isinstance(items, list) else '?'} BOs")
