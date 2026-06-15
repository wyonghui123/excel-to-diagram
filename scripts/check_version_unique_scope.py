#!/usr/bin/env python3
"""[BMRD 2026-06-14] 确认 version 唯一性范围 (product 内 vs 跨 product)"""
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

# 用现有 product (NEWTEST33=323) 和 TEST1101=326
product_a = 323  # NEWTEST33
product_b = 326  # TEST1101

# 找不重复的 V name
ver_name = f'V_UNIQUE_TEST_{ts}'

print(f'=== 确认 version 唯一性范围: {ver_name} ===\n')

# 1. 在 product_A (323) 创建 V name
print(f'1. product_A ({product_a}) 创建 {ver_name}:')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_a_{ts}', 'name': ver_name, 'product_id': product_a, 'is_current': 1
})
print(f'   status: {status}')
print(f'   body: {data[:200]}\n')

# 2. 在 product_B (326) 创建同名 V (期望: 如果跨 product 不唯一, 应失败)
print(f'2. product_B ({product_b}) 创建同名 {ver_name} (跨 product):')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_b_{ts}', 'name': ver_name, 'product_id': product_b, 'is_current': 1
})
print(f'   status: {status}')
print(f'   body: {data[:200]}')
print()

# 3. 在 product_A 再创建同名 V (期望: 应失败 - product 内唯一)
print(f'3. product_A ({product_a}) 再创建同名 {ver_name} (同 product):')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_a2_{ts}', 'name': ver_name, 'product_id': product_a, 'is_current': 0
})
print(f'   status: {status}')
print(f'   body: {data[:300]}')
