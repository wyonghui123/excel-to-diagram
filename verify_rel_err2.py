import requests
BASE = 'http://localhost:3010'
admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)

# Direct /api/v1/relationships (special routes)
print('--- direct /api/v1/relationships ---')
r = admin.get(f'{BASE}/api/v1/relationships', params={'version_id': 1, 'page_size': 5}, timeout=10)
print('status:', r.status_code)
print('body:', r.text[:500])

print()
print('--- POST /api/v1/relationships ---')
r = admin.post(f'{BASE}/api/v1/relationships', json={'version_id': 1, 'page_size': 5}, timeout=10)
print('status:', r.status_code)
print('body:', r.text[:500])

print()
print('--- POST /api/v2/bo/relationship/list ---')
r = admin.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'page_size': 5}, timeout=10)
print('status:', r.status_code)
print('body:', r.text[:1500])