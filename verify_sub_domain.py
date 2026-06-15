"""Quick check sub_domain for admin vs TEST60."""
import requests

BASE = 'http://localhost:3010'

a = requests.Session()
a.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)

t = requests.Session()
t.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'TEST60', 'password': 'TEST60'}, timeout=5)

for label, sess in [('admin', a), ('TEST60', t)]:
    r = sess.get(f'{BASE}/api/v2/bo/sub_domain/list', params={'page': 1, 'page_size': 100}, timeout=5)
    data = r.json()
    items = data.get('data', [])
    if isinstance(items, dict):
        items = items.get('items', [])
    print(f'{label} sub_domains: {len(items)}')
    for sd in items[:5]:
        print(f'  id={sd.get("id")}, name={sd.get("name")}, version_id={sd.get("version_id")}')
    print()
