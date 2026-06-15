"""Reproduce 400 BAD REQUEST with EXACT user parameters."""
import urllib.request, json
import sys

sys.path.insert(0, 'd:/filework/excel-to-diagram')

# Get token
login = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
req = urllib.request.Request('http://localhost:3010/api/v1/auth/login', data=login, headers={'Content-Type': 'application/json'})
r = json.loads(urllib.request.urlopen(req, timeout=3).read())
token = r['data']['token']

# Test with EXACT user page_size params
test_cases = [
    ('domain',         '?version_id=764&page_size=1000'),
    ('sub_domain',     '?version_id=764&page_size=1000'),
    ('service_module', '?version_id=764&page_size=5000'),
    ('business_object','?version_id=764&page_size=10000'),
    ('relationship',   '?page=1&page_size=20&version_id=764'),
]
for ep, qs in test_cases:
    url = f'http://localhost:3010/api/v2/bo/{ep}{qs}'
    try:
        req2 = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        resp = urllib.request.urlopen(req2, timeout=10)
        body = resp.read().decode()
        data = json.loads(body)
        items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
        print(f'  {ep:18s} {qs[:50]:50s} -> {resp.status} items={len(items)} total={data.get("data", {}).get("total", "?") if isinstance(data.get("data"), dict) else "?"}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'  {ep:18s} {qs[:50]:50s} -> ERR {e.code}')
        print(f'    body: {body[:500]}')
    except Exception as e:
        print(f'  {ep:18s} {qs[:50]:50s} -> EXC {e}')

# Now try with Vite proxy (port 3004)
print("\n=== Via Vite proxy (3004) ===")
for ep, qs in test_cases[:2]:
    url = f'http://localhost:3004/api/v2/bo/{ep}{qs}'
    try:
        req2 = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        resp = urllib.request.urlopen(req2, timeout=10)
        body = resp.read().decode()
        data = json.loads(body)
        items = data.get('data', {}).get('items', []) if isinstance(data.get('data'), dict) else []
        print(f'  {ep:18s} -> {resp.status} items={len(items)}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'  {ep:18s} -> ERR {e.code} body={body[:300]}')
    except Exception as e:
        print(f'  {ep:18s} -> EXC {e}')

# Check if the "incomplete input" error comes from BROWSER side
# Try with a session and read full response
print("\n=== With cookie session ===")
import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
# Login
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin', timeout=5)

# Try the relationship endpoint
url = 'http://localhost:3010/api/v2/bo/relationship?page=1&page_size=20&version_id=764'
try:
    resp = opener.open(url, timeout=10)
    body = resp.read().decode()
    print(f'  relationship (cookie): {resp.status} len={len(body)}')
    # Check first 500 chars
    print(f'  body[:300]: {body[:300]}')
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f'  relationship (cookie): ERR {e.code}')
    print(f'  body: {body[:500]}')
