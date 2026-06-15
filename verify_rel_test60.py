import requests
BASE = 'http://localhost:3010'

admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)
test60 = requests.Session()
test60.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)

# Real scenario: TEST60 selects scope=采购管理 (sub_domain_id=1) in version=1
for label, sess in [('admin', admin), ('TEST60', test60)]:
    print(f'--- {label} ---')
    # /api/v1/relationships
    r = sess.get(f'{BASE}/api/v1/relationships', params={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    print(f'  /api/v1/relationships v=1: status={r.status_code}, count={len(items) if isinstance(items, list) else "?"}')

    # /api/v2/bo/relationship/list
    r = sess.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f'  /api/v2/bo/relationship/list v=1: status={r.status_code}, count={len(items) if isinstance(items, list) else "?"}')

    # /api/v2/bo/relationship/list with sub_domain filter (TEST60 选了采购管理)
    r = sess.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'sub_domain_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f'  /api/v2/bo/relationship/list v=1 sd=1: status={r.status_code}, count={len(items) if isinstance(items, list) else "?"}')

    # /api/v1/relationships with sub_domain filter
    r = sess.get(f'{BASE}/api/v1/relationships', params={'version_id': 1, 'sub_domain_id': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    print(f'  /api/v1/relationships v=1 sd=1: status={r.status_code}, count={len(items) if isinstance(items, list) else "?"}')
    print()