#!/usr/bin/env python3
"""[BMRD 2026-06-14 BUG-V006] 测试 deep_insert 唯一性冲突时的事务回滚"""
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

ts = str(int(time.time()))
ver_id_1 = f'ver_a_{ts}'

print('=== BUG-V006 真实复现: deep_insert 唯一性冲突事务回滚 ===\n')

# Step 1: 直接创建 product_1 + version_a (V1) 成功
print(f'1. 创建 product_1 + V1 (NEW):')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': ver_id_1, 'name': 'V1', 'product_id': 'TX_P1_' + ts, 'is_current': 1
})
print(f'   POST /version: {status} -> {data[:200]}\n')

# Step 2: 通过 deep_insert 创建新 product_2 + 重复 V1 (相同 product_id)
print(f'2. deep_insert 触发唯一性冲突 (新 product_2 + version.name=V1, product_id=parent1 的):')
body2 = {
    'parent': {'id': 'TX_P2_' + ts, 'name': f'TX_P2_{ts}'},
    'children': {'version': [
        {'id': f'ver_b_{ts}', 'name': 'V1', 'product_id': 'TX_P1_' + ts, 'is_current': 0}
    ]}
}
status, data = post('http://localhost:3010/api/v2/bo/product/deep', body2)
print(f'   POST /product/deep: {status}')
print(f'   body: {data[:500]}\n')

# Step 3: 验证: product_2 应回滚 (但 deep_insert 实际会覆盖 product_id)
# 改为: 直接测 product_2 是否存在
import urllib.request
r = opener.open('http://localhost:3010/api/v2/bo/product?page_size=50')
data = json.loads(r.read().decode())
ids = [p['id'] for p in data['data']['items']]
print(f'3. product_2 (TX_P2_{ts}) 是否在 product 列表: {"TX_P2_" + ts in ids}')

# Step 4: 真实 BUG 场景: 找现有 NEWTEST33 (323) 看是否有 V10
print(f'\n4. NEWTEST33 (id=323) 真实 V10 versions:')
r2 = opener.open('http://localhost:3010/api/v2/bo/version?product_id=323&page_size=10')
v_data = json.loads(r2.read().decode())
for v in v_data['data']['items']:
    print(f'   - {v["id"]} / {v["name"]}')

# Step 5: 真实 BUG - 用 NEWTEST33 + V10 deep_insert
print(f'\n5. 模拟用户场景: deep_insert NEWTEST_NEW + V10 (NEW product+NEW version name, 不应冲突)')
body3 = {
    'parent': {'id': 'TX_NEW33_' + ts, 'name': f'TX_NEW33_{ts}'},
    'children': {'version': [
        {'id': f'ver_c_{ts}', 'name': 'V10_NEW', 'is_current': 1}  # NEW name V10_NEW
    ]}
}
status, data = post('http://localhost:3010/api/v2/bo/product/deep', body3)
print(f'   POST /product/deep: {status}')
print(f'   body: {data[:400]}')
