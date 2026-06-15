"""Check correct sub_domain path."""
import requests

BASE = 'http://localhost:3010'

a = requests.Session()
a.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)

# Try v1 paths
for path in [
    '/api/v1/sub_domain/list',
    '/api/v1/sub_domains',
    '/api/v2/sub_domain/list',
    '/api/v2/bo/sub_domain/list',
    '/api/v1/products',  # test v1 generic
]:
    r = a.get(f'{BASE}{path}', params={'page': 1, 'page_size': 100}, timeout=5)
    print(f'{path}: {r.status_code} {r.text[:150]}')
    print()

# Check relationships via v2 path
r = a.get(f'{BASE}/api/v1/relationships', params={'version_id': 1, 'page_size': 100}, timeout=5)
data = r.json()
items = data.get('data', [])
if isinstance(items, dict):
    items = items.get('items', [])
print(f'admin /api/v1/relationships v1: {len(items) if isinstance(items, list) else "?"}')

# Check sample item to see what bo_ids are present
if isinstance(items, list) and items:
    bo_ids = set()
    for r in items[:10]:
        bo_ids.add(r.get('source_bo_id'))
        bo_ids.add(r.get('target_bo_id'))
    print(f'  Sample bo_ids: {sorted(bo_ids)[:10]}')

    # Check sub_domain_id of source_bo
    sample_bo_id = items[0].get('source_bo_id')
    r2 = a.get(f'{BASE}/api/v2/bo/business_object/{sample_bo_id}', timeout=5)
    if r2.status_code == 200:
        b = r2.json()
        bd = b.get('data', b)
        print(f'  Sample BO {sample_bo_id}: name={bd.get("name")}, sd_id={bd.get("sub_domain_id")}, version_id={bd.get("version_id")}')

# Check sub_domain via direct DB query using relationships bo_ids
