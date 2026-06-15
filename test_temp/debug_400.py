"""Reproduce 400 BAD REQUEST with incomplete input error."""
import urllib.request, json
import sys

sys.path.insert(0, 'd:/filework/excel-to-diagram')

# Get token
login = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
req = urllib.request.Request('http://localhost:3010/api/v1/auth/login', data=login, headers={'Content-Type': 'application/json'})
r = json.loads(urllib.request.urlopen(req, timeout=3).read())
token = r['data']['token']

# Find an actual version_id
print("=== Finding actual version_ids ===")
req2 = urllib.request.Request('http://localhost:3010/api/v2/meta/version/view-config/default', headers={'Authorization': f'Bearer {token}'})
try:
    resp = urllib.request.urlopen(req2, timeout=5)
    data = json.loads(resp.read().decode())
    print('versions view-config OK')
except Exception as e:
    print('versions view-config ERR:', e)

# Try with a real version
req3 = urllib.request.Request('http://localhost:3010/api/v2/bo/version?page_size=10', headers={'Authorization': f'Bearer {token}'})
try:
    resp = urllib.request.urlopen(req3, timeout=5)
    data = json.loads(resp.read().decode())
    if data.get('data'):
        items = data['data'].get('items', data['data']) if isinstance(data['data'], dict) else data['data']
        if items and len(items) > 0:
            real_vid = items[0].get('id')
            print(f'Real version_id found: {real_vid}')
            # Test endpoints with this real version
            for ep in ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']:
                url = f'http://localhost:3010/api/v2/bo/{ep}?version_id={real_vid}&page_size=10'
                try:
                    req4 = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
                    resp4 = urllib.request.urlopen(req4, timeout=5)
                    body = resp4.read().decode()
                    print(f'  {ep} (vid={real_vid}): status={resp4.status}, items={len(json.loads(body).get("data", {}).get("items", [])) if json.loads(body).get("data") else 0}')
                except urllib.error.HTTPError as e:
                    body = e.read().decode()
                    print(f'  {ep} (vid={real_vid}): ERR {e.code} body={body[:500]}')
except Exception as e:
    print('bo/version ERR:', e)

# Now check if version_id 764 exists
print("\n=== Checking version_id 764 ===")
for ep in ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']:
    url = f'http://localhost:3010/api/v2/bo/{ep}?version_id=764&page_size=5'
    try:
        req4 = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
        resp4 = urllib.request.urlopen(req4, timeout=5)
        body = resp4.read().decode()
        data = json.loads(body)
        if data.get('data') and isinstance(data['data'], dict):
            items = data['data'].get('items', [])
            print(f'  {ep} (vid=764): status={resp4.status}, items={len(items)}, total={data["data"].get("total", "?")}')
        else:
            print(f'  {ep} (vid=764): status={resp4.status}, data type={type(data.get("data"))}')
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'  {ep} (vid=764): ERR {e.code} body={body[:500]}')
    except Exception as e:
        print(f'  {ep} (vid=764): EXC {e}')
