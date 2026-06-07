"""探 v2 真正路径 + 提取 overlap 异常 traceback"""
import urllib.request
import urllib.error
import json
import http.cookiejar

BASE = 'http://localhost:3010'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# dev-login
resp = opener.open(f'{BASE}/api/v1/auth/dev-login?username=admin')
print(f'login: {resp.status}')

# 探 v2 真正路径
paths = [
    ('POST', '/api/v2/bo/permissions/explain', {'user_id': 1, 'bo_id': 'business_object', 'action_id': 'read'}),
    ('POST', '/api/v2/bo/permissions/check', {'user_id': 1, 'bo_id': 'business_object', 'action_id': 'read'}),
    ('POST', '/api/v2/bo/permissions/check_intent', {'user_id': 1, 'bo_id': 'business_object', 'action_name': 'read'}),
    ('GET', '/api/v2/bo/bos', None),
    ('GET', '/api/v2/bo/bos/business_object/actions', None),
    ('GET', '/api/v1/roles/1/overlaps/summary', None),  # 看 500 traceback
    ('GET', '/api/v1/roles/1/overlaps', None),
]

for entry in paths:
    method = entry[0]
    path = entry[1]
    body = entry[2] if len(entry) > 2 else None
    try:
        if method == 'GET':
            req = urllib.request.Request(BASE + path, method='GET')
        else:
            data = json.dumps(body).encode('utf-8') if body else b'{}'
            req = urllib.request.Request(BASE + path, data=data, method=method)
            req.add_header('Content-Type', 'application/json')
        resp = opener.open(req)
        status = resp.status
        text = resp.read(300).decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read(500).decode('utf-8', errors='replace')
    except Exception as e:
        status = 'ERR'
        text = str(e)[:200]
    print(f'\n=== {method} {path}: {status} ===')
    print(text[:500])
