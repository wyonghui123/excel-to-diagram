"""Inspect backend returned associations."""
import urllib.request, json

req = urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin')
resp = urllib.request.urlopen(req)
cookie = resp.headers.get('Set-Cookie').split(';')[0]

req2 = urllib.request.Request('http://localhost:3010/api/v2/meta/role/view-config/default')
req2.add_header('Cookie', cookie)
r2 = json.loads(urllib.request.urlopen(req2).read())

print('=== Top-level keys ===')
print(list(r2.get('data', {}).keys()))

associations = r2.get('data', {}).get('associations', [])
print(f'\n=== {len(associations)} associations ===')
for a in associations:
    name = a.get('name') or a.get('key') or '?'
    if 'group' in name.lower() or 'role' in name.lower():
        print(f'\n--- {name} ---')
        print(json.dumps(a, ensure_ascii=False, indent=2))

# Also check detail.tabs
detail = r2.get('data', {}).get('detail') or {}
print(f'\n=== detail keys: {list(detail.keys())} ===')
print(f'=== detail.tabs: {len(detail.get("tabs", []))} ===')
for t in detail.get('tabs', []):
    print(json.dumps(t, ensure_ascii=False, indent=2))