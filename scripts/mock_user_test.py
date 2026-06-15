#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实模拟用户在 UI 手动创建 TEST888122 + V10
看: UI 走的什么 endpoint, payload 是什么, 触发了什么
"""
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

# 你手动 UI 走的路径推测:
# 1) DetailPage 调 POST /api/v2/bo/product (因为 hasChildChanges=false)
#    payload: { code: 'TEST888122', name: 'TEST888122', ... }
#    (前端表单字段, 没有 product.id, 因为新建)
# 2) 子表 V10 完全没被序列化 (因为 detailPageRef 是 null, hasChildChanges 永远 false)

ts = str(int(time.time()))
print('=== 模拟 UI 手动创建 TEST888122 ===')

# 1. 用户填的 product 字段 (前端表单, code 必填)
print('\n1. 模拟前端 POST /api/v2/bo/product (无 product.id, code 必填):')
status, data = post('http://localhost:3010/api/v2/bo/product', {
    'code': f'TEST888122_{ts}',
    'name': f'TEST888122_{ts}',
    'description': 'user manual test'
})
print(f'   status: {status}')
print(f'   body: {data[:300]}')

# 2. 模拟前端 POST /api/v2/bo/version (单独, 因为子表没走 deep_insert)
print('\n2. 模拟前端 POST /api/v2/bo/version (子表数据丢失后, 单独 POST):')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_{ts}',
    'name': 'V10',
    'product_id': 342,  # 用 TEST888122 (342)
    'is_current': 1
})
print(f'   status: {status}')
print(f'   body: {data[:300]}')
