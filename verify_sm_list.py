import requests
BASE = 'http://localhost:3010'

admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)
test60 = requests.Session()
test60.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)

for label, sess in [('admin', admin), ('TEST60', test60)]:
    print(f'--- {label} ---')
    # service_module
    r = sess.post(f'{BASE}/api/v2/bo/service_module/list', json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f'  service_module v=1: {len(items) if isinstance(items, list) else "?"}')
    # business_object
    r = sess.post(f'{BASE}/api/v2/bo/business_object/list', json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f'  business_object v=1: {len(items) if isinstance(items, list) else "?"}')
    # relationship
    r = sess.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f'  relationship v=1: {len(items) if isinstance(items, list) else "?"}')
    # Check error
    r = sess.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'page_size': 1}, timeout=5)
    print(f'  relationship v=1 sample response: {r.text[:200]}')
