#!/usr/bin/env python3
"""[BMRD 2026-06-14 BUG-V006 验证] 测试 deep_insert 事务回滚"""
import urllib.request, http.cookiejar, json, time

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                  method='POST',
                                  headers={'Content-Type': 'application/json'})
    try:
        r = opener.open(req, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def get(url):
    try:
        r = opener.open(url, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

ts = str(int(time.time()))
product_id = f'TX_TEST_{ts}'

print(f'=== 事务回滚测试: 创建新 product {product_id} + 重复 V10 ===')

# 第一次: 全新 product + V1 (NEW)
body = {
    'parent': {'id': product_id, 'name': f'TX_TEST_{ts}'},
    'children': {'version': [{'id': f'v_{ts}_1', 'name': 'V1', 'is_current': 1}]}
}
status, data = post('http://localhost:3010/api/v2/bo/product/deep', body)
print(f'1st deep: {status}')
print(f'  body: {data[:200]}')

# 第二次: 新 product + 同名 version (应失败)
print(f'\n=== 2nd: 同 product_id+name=V10 (force product_id=parent1) ===')
body2 = {
    'parent': {'id': f'{product_id}_2', 'name': f'TX_TEST_2_{ts}'},
    'children': {'version': [{'id': f'v_{ts}_2', 'name': 'V1', 'product_id': product_id, 'is_current': 0}]}
}
status, data = post('http://localhost:3010/api/v2/bo/product/deep', body2)
print(f'2nd deep: {status}')
print(f'  body: {data[:500]}')

# 验证事务回滚
print(f'\n=== 验证事务回滚: parent_2 ({product_id}_2) 应不存在 ===')
status, data = get(f'http://localhost:3010/api/v2/bo/product/{product_id}_2')
print(f'GET parent_2: {status}')
print(f'  body: {data[:300]}')

if status == 404:
    print('\n✅ 事务回滚 PASSED: parent_2 不存在, deep_insert 在子创建失败时回滚父创建')
else:
    print('\n❌ 事务回滚 FAILED: parent_2 仍存在, deep_insert 事务隔离有问题')
