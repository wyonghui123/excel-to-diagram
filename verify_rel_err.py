import requests
BASE = 'http://localhost:3010'
admin = requests.Session()
admin.get(f'{BASE}/api/v1/auth/dev-login', params={'username': 'admin', 'password': 'admin'}, timeout=5)
r = admin.post(f'{BASE}/api/v2/bo/relationship/list', json={'version_id': 1, 'page_size': 5}, timeout=10)
print('status:', r.status_code)
print('body:', r.text[:1500])