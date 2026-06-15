#!/usr/bin/env python3
"""[BMRD 2026-06-14] 复现 TEST888121+V10 用户场景"""
import urllib.request, http.cookiejar, json, time, urllib.error

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                  method='POST', headers={'Content-Type': 'application/json'})
    try:
        r = opener.open(req, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

ts = str(int(time.time()))

# 模拟用户场景: 新建 NEWTEST888999 product + V10 version
# 用户说"一起 save" - 走 deep_insert 还是单独 POST?
print('=== 场景 1: 单独 POST product (前端 UI 默认) ===')
print('用户先在产品新建页 save product 本身:')
status, data = post('http://localhost:3010/api/v2/bo/product', {
    'id': f'TEST_USER_{ts}',
    'name': f'TEST_USER_{ts}'
})
print(f'  POST /product: {status} body: {data[:200]}')

print('\n=== 场景 2: 然后单独 POST version V10 ===')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_{ts}',
    'name': 'V10',
    'product_id': f'TEST_USER_{ts}',
    'is_current': 1
})
print(f'  POST /version: {status} body: {data[:300]}')

print('\n=== 场景 3: deep_insert 一体化 ===')
status, data = post('http://localhost:3010/api/v2/bo/product/deep', {
    'parent': {'id': f'TEST_DEEP_{ts}', 'name': f'TEST_DEEP_{ts}'},
    'children': {'version': [
        {'id': f'ver_d_{ts}', 'name': 'V10', 'is_current': 1}
    ]}
})
print(f'  POST /product/deep: {status} body: {data[:400]}')
