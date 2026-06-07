"""批量测 v1/v2 路径 + 提取 dev-login cookie"""
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

# 测试路径
paths = [
    ('GET', '/api/v1/management-dimensions'),
    ('GET', '/api/v1/roles/1/intents'),
    ('GET', '/api/v1/roles/1/overlaps/summary'),
    ('GET', '/api/v1/bos'),
    ('GET', '/api/v1/bos/business_object/actions'),
    ('POST', '/api/v1/permissions/explain', {'user_id': 1, 'bo_id': 'business_object', 'action_id': 'read'}),
    ('POST', '/api/v1/permissions/check', {'user_id': 1, 'bo_id': 'business_object', 'action_id': 'read'}),
    ('POST', '/api/v1/permissions/check_intent', {'user_id': 1, 'bo_id': 'business_object', 'action_name': 'read'}),
    ('GET', '/api/v2/bo/permissions', None),  # 错路径，仅测
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
        text = resp.read(200).decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read(200).decode('utf-8', errors='replace')
    except Exception as e:
        status = 'ERR'
        text = str(e)[:100]
    print(f'{method} {path}: {status} {text[:120]}')
