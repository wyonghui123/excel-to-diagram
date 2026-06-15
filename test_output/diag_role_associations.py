"""Verify _ui_config_builder returns associations for role."""
import urllib.request, json

req = urllib.request.Request('http://localhost:3010/api/v1/auth/dev-login?username=admin')
resp = urllib.request.urlopen(req)
cookie = resp.headers.get('Set-Cookie').split(';')[0]

req2 = urllib.request.Request('http://localhost:3010/api/v2/meta/role/ui-config')
req2.add_header('Cookie', cookie)
r2 = json.loads(urllib.request.urlopen(req2).read())

print('=== /api/v2/bo/role/ui-config ===')
print('Top keys:', list(r2.get('data', {}).keys()))
associations = r2.get('data', {}).get('associations', [])
print(f'\n=== {len(associations)} associations ===')
for a in associations:
    name = a.get('name') or a.get('key') or '?'
    if 'group' in name.lower() or 'role' in name.lower():
        print(f'\n--- {name} ---')
        print(json.dumps(a, ensure_ascii=False, indent=2))