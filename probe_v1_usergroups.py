import requests
base = 'http://localhost:3010'
r = requests.post(f'{base}/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
token = r.json()['data']['token']
cookies = {'auth_token': token}

print('=== GET /api/v1/user-groups ===')
r = requests.get(f'{base}/api/v1/user-groups', cookies=cookies, timeout=5)
print(f'  status: {r.status_code}')
print(f'  body:   {r.text[:500]}')
print(f'  trace_id: {r.headers.get("X-Trace-Id")}')

print()
print('=== POST /api/v1/user-groups (empty body) ===')
r = requests.post(f'{base}/api/v1/user-groups', cookies=cookies, json={}, timeout=5)
print(f'  status: {r.status_code}')
print(f'  body:   {r.text[:500]}')

print()
print('=== PUT /api/v1/user-groups/1 (empty body) ===')
r = requests.put(f'{base}/api/v1/user-groups/1', cookies=cookies, json={}, timeout=5)
print(f'  status: {r.status_code}')
print(f'  body:   {r.text[:500]}')

print()
print('=== DELETE /api/v1/user-groups/1 ===')
r = requests.delete(f'{base}/api/v1/user-groups/1', cookies=cookies, timeout=5)
print(f'  status: {r.status_code}')
print(f'  body:   {r.text[:500]}')
