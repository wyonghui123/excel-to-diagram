"""Quick E2E test for WriteScopeDenied v1.2.30"""
import sys, requests

BASE = 'http://localhost:5000'

# 1. Login as TEST333
s = requests.Session()
r = s.get(f'{BASE}/api/v2/auth/dev-login', params={'username': 'TEST333'}, allow_redirects=False)
print(f'Login TEST333: {r.status_code}')

# 2. Update relationship 21 (source BO not in TEST333 scope -> denied)
r = s.put(f'{BASE}/api/v2/manage/update/relationship/21', json={
    'fields': {'description': 'test'}
})
d = r.json()
msg = d.get('message', '')
print(f'Test1 (rel 21 update): HTTP {r.status_code} | success={d.get("success")}')
print(f'  msg: {msg[:200]}')

# 3. Create relationship (should be denied)
r = s.post(f'{BASE}/api/v2/manage/create/relationship', json={
    'fields': {
        'code': 'TEST_CREATE_REL',
        'name': '\u6d4b\u8bd5\u65b0\u5efa\u5173\u7cfb',
        'source_bo_id': 7,
        'target_bo_id': 6,
        'relationship_type': 'composition'
    }
})
d = r.json()
msg = d.get('message', '')
print(f'Test2 (rel create): HTTP {r.status_code} | success={d.get("success")}')
print(f'  msg: {msg[:200]}')

# 4. Admin login (control)
s2 = requests.Session()
r = s2.get(f'{BASE}/api/v2/auth/dev-login', params={'username': 'admin'}, allow_redirects=False)
print(f'Admin login: {r.status_code}')

# 5. Admin update relationship 21 (should pass)
r = s2.put(f'{BASE}/api/v2/manage/update/relationship/21', json={
    'fields': {'description': 'admin test'}
})
d = r.json()
print(f'Test3 (admin rel 21): HTTP {r.status_code} | success={d.get("success")}')
print(f'  msg: {d.get("message", "")[:200]}')
