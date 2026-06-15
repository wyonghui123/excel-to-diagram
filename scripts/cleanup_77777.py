#!/usr/bin/env python3
"""清理重复的 TEST77777 (id=353)，并验证"""
import urllib.request, http.cookiejar, json, urllib.parse

def api(method, path, data=None):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

    url = f'http://localhost:3010{path}'
    if data:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
            headers={'Content-Type': 'application/json'}, method=method)
    else:
        req = urllib.request.Request(url, method=method)
    try:
        r = op.open(req)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {'error': e.code, 'body': e.read().decode()}

# 清理 TEST77777
print('=== 清理 TEST77777 (id=353) ===')
r = api('DELETE', '/api/v2/bo/product/353?reason=test_cleanup&reason_text=cleanup_for_retest')
print(f'  DELETE /api/v2/bo/product/353: {r}')

# 验证已清理
r = api('GET', '/api/v2/bo/product?name=TEST77777')
products = r.get('data', {}).get('items', [])
print(f'  TEST77777: {len(products)} found')
