"""Check why TEST60 gets 0 BOs."""
import requests

BASE = 'http://localhost:3010'

admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)
test60 = requests.Session()
test60.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)

# bo list with version_id (filter)
print("=== POST /api/v2/bo/business_object/list v=1 ===")
for label, sess in [('admin', admin), ('TEST60', test60)]:
    r = sess.post(f'{BASE}/api/v2/bo/business_object/list',
                  json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  {label}: {len(items) if isinstance(items, list) else '?'} BOs")
    if isinstance(items, list) and items:
        print(f"    sample: id={items[0].get('id')}, name={items[0].get('name')}")

# bo list with version_id query
print()
print("=== GET /api/v2/bo/business_object/list?version_id=1 ===")
for label, sess in [('admin', admin), ('TEST60', test60)]:
    r = sess.get(f'{BASE}/api/v2/bo/business_object/list',
                 params={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  {label}: {len(items) if isinstance(items, list) else '?'} BOs")

# No version_id
print()
print("=== POST /api/v2/bo/business_object/list (no version) ===")
for label, sess in [('admin', admin), ('TEST60', test60)]:
    r = sess.post(f'{BASE}/api/v2/bo/business_object/list',
                  json={'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  {label}: {len(items) if isinstance(items, list) else '?'} BOs")

# relationship test
print()
print("=== POST /api/v2/bo/relationship/list v=1 ===")
for label, sess in [('admin', admin), ('TEST60', test60)]:
    r = sess.post(f'{BASE}/api/v2/bo/relationship/list',
                  json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f"  {label}: {len(items) if isinstance(items, list) else '?'} relationships")
