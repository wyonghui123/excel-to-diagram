#!/usr/bin/env python3
"""[BMRD 2026-06-14 BUG-V006] 真实复现: 唯一性冲突 + 事务回滚"""
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

def get(url):
    try:
        r = opener.open(url, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

ts = str(int(time.time()))

# Step 1: 找两个有 V10 的真实 product + version
print('=== Step 1: 查 NEWTEST33 (323) 真实 V10 versions ===')
status, data = get('http://localhost:3010/api/v2/bo/version?product_id=323&page_size=20')
v_data = json.loads(data)
for v in v_data['data']['items']:
    print(f'   - {v["id"]} / {v["name"]}')

# Step 2: 真实 BUG 场景: 模拟产品新建后立即在同一请求中尝试重复创建 version
# 关键: 不依赖现有数据, 我们自己创建 product_A + version_A (V1), 然后 deep_insert
# 尝试创建 product_B + version_B (name=V1, product_id=product_A.id)
# 期望: 唯一性冲突, product_B 应回滚
print(f'\n=== Step 2: 创建 product_A + V1 (基础数据) ===')
prod_a = None
# 找现有可用 product
r = opener.open('http://localhost:3010/api/v2/bo/product?page_size=5')
prods = json.loads(r.read())['data']['items']
for p in prods:
    if p['name'].startswith('TX_BUG_') or 'NEWTEST' in str(p['name']):
        prod_a = p['id']
        break
print(f'   使用现有 product: {prod_a}')

# Step 3: 实际触发 - 模拟用户 NEWTEST33 + V10 场景
# 直接 POST /version 用已存在 product_id + name=V10
print(f'\n=== Step 3: 模拟用户场景 - 给 product 323 (NEWTEST33) 创建 V10 version ===')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_test_v10_{ts}', 'name': 'V10_TEST_BUG', 'product_id': 323, 'is_current': 1
})
print(f'   POST /version: {status}')
print(f'   body: {data[:300]}')

# 重复同名
print(f'\n=== Step 4: 再次创建 V10_TEST_BUG (期望冲突) ===')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'ver_test_v10_dup_{ts}', 'name': 'V10_TEST_BUG', 'product_id': 323, 'is_current': 0
})
print(f'   POST /version 2nd: {status}')
print(f'   body: {data[:300]}')

# Step 5: 通过 deep_insert 触发冲突, 检查 product 是否回滚
# 找两个不同的 NEW product
print(f'\n=== Step 5: deep_insert NEW + version (NEW name, 应成功) ===')
# 创建新 product (先创建, 然后 deep_insert)
status, data = post('http://localhost:3010/api/v2/bo/product', {
    'id': f'TX_NEW_{ts}', 'name': f'TX_NEW_{ts}'
})
print(f'   POST /product: {status}')
print(f'   body: {data[:200]}')

# 试 deep_insert
status, data = post('http://localhost:3010/api/v2/bo/product/deep', {
    'parent': {'id': f'TX_DEEP_{ts}', 'name': f'TX_DEEP_{ts}'},
    'children': {'version': [
        {'id': f'ver_deep_{ts}', 'name': 'V_TEST', 'is_current': 1}
    ]}
})
print(f'   POST /product/deep (NEW): {status}')
print(f'   body: {data[:300]}')

# Step 6: 用同一 name 重复 deep_insert (期望 product 回滚)
print(f'\n=== Step 6: deep_insert (同 version name) (期望冲突 + product 回滚) ===')
status, data = post('http://localhost:3010/api/v2/bo/product/deep', {
    'parent': {'id': f'TX_DEEP_2_{ts}', 'name': f'TX_DEEP_2_{ts}'},
    'children': {'version': [
        # 强 product_id=first parent, 期望冲突
        {'id': f'ver_deep_dup_{ts}', 'name': 'V_TEST', 'product_id': f'TX_DEEP_{ts}', 'is_current': 0}
    ]}
})
print(f'   POST /product/deep (DUP): {status}')
print(f'   body: {data[:500]}')

# Step 7: 验证 product 回滚
status, data = get(f'http://localhost:3010/api/v2/bo/product/TX_DEEP_2_{ts}')
print(f'\n=== Step 7: GET TX_DEEP_2_{ts} 应 404 (回滚) ===')
print(f'   status: {status}, body: {data[:200]}')
if status == 404:
    print('   ✅ 事务回滚 PASS')
else:
    print('   ❌ 事务回滚 FAIL: 父产品存在!')
