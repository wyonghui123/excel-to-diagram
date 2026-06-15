#!/usr/bin/env python3
"""[BMRD 2026-06-14 BUG-V006 真实复现] NEWTEST33 + V10 唯一性"""
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

print('=== BUG-V006 真实复现 ===\n')

# 1. 看 NEWTEST33 + V10 现状
status, data = get('http://localhost:3010/api/v2/bo/version?product_id=323&name=V10')
v_data = json.loads(data)
v10_versions = v_data['data']['items']
print(f'1. NEWTEST33 (id=323) 当前 V10 versions: {len(v10_versions)}')
for v in v10_versions:
    print(f'   - {v["id"]} / {v["name"]} / is_current={v.get("is_current")}')

# 2. 关键测试: deep_insert NEWTEST_NEW + V10 (NEW product + 重复 version name)
# 模拟用户: "我新建 NEWTEST33产品，V10版本" -> 用户以为是 NEW product, 但其实 NEWTEST33 已存在 + V10 已存在
ts = str(int(time.time()))

# 先创建 NEWTEST33 的 V10 一次 (模拟当前数据库状态)
print(f'\n2. 确认 V10 已存在: 给 323 创建 V10 (NEW name first time)')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'NEWV10_{ts}', 'name': 'V10', 'product_id': 323, 'is_current': 1
})
print(f'   POST /version: {status} body: {data[:200]}')

# 3. 关键: 重复创建 V10 (应触发唯一性约束)
print(f'\n3. 重复创建 V10 (期望唯一性冲突 400)')
status, data = post('http://localhost:3010/api/v2/bo/version', {
    'id': f'NEWV10_DUP_{ts}', 'name': 'V10', 'product_id': 323, 'is_current': 0
})
print(f'   POST /version 2nd: {status}')
print(f'   body: {data[:300]}')

# 4. BUG-V006 关键测试: deep_insert 应在同一事务中处理
# 用户在 NEWTEST33 详情页新建 V10, 后端走的是 version 直接 POST (不 deep)
# 假设: 前端点击"新建产品 + V10"按钮 -> 后端用 deep_insert
# 但 NEWTEST33 已存在 -> 应该走 update 不是 create
# 用户问题: "NEWTEST33产品创建成功了" - 意味着 deep_insert 走了 update + 新增 version
# 但 V10 重复 -> version 创建失败 -> product 已被 update/创建 -> 但用户说产品"创建成功"意味着 product 已存在

# 5. 现在直接测 deep_insert: 新 product + V10 (全新 V10)
print(f'\n4. deep_insert 全新 product + V10_NEW (应成功)')
status, data = post('http://localhost:3010/api/v2/bo/product/deep', {
    'parent': {'id': f'NEWPROD_{ts}', 'name': f'NEWPROD_{ts}'},
    'children': {'version': [
        {'id': f'ver_v10_new_{ts}', 'name': 'V10_NEW', 'is_current': 1}
    ]}
})
print(f'   POST /product/deep: {status}')
print(f'   body: {data[:300]}')

# 6. deep_insert + 同 product_id + V10 (期望 400 唯一性 + product 回滚)
print(f'\n5. deep_insert 全新 product_2 + 重复 V10_NEW (期望失败 + product 回滚)')
status, data = post('http://localhost:3010/api/v2/bo/product/deep', {
    'parent': {'id': f'NEWPROD_2_{ts}', 'name': f'NEWPROD_2_{ts}'},
    'children': {'version': [
        # product_id=NEWPROD_1 (已存在 V10_NEW)
        {'id': f'ver_v10_dup_{ts}', 'name': 'V10_NEW', 'product_id': f'NEWPROD_{ts}', 'is_current': 0}
    ]}
})
print(f'   POST /product/deep (DUP): {status}')
print(f'   body: {data[:500]}')

# 7. 验证: NEWPROD_2 不应存在 (回滚)
print(f'\n6. 检查 NEWPROD_2 是否回滚')
status, data = get(f'http://localhost:3010/api/v2/bo/product/NEWPROD_2_{ts}')
print(f'   GET NEWPROD_2_{ts}: {status}')
print(f'   body: {data[:200]}')
if status == 404:
    print('   ✅ 事务回滚 PASS')
else:
    print('   ❌ 事务回滚 FAIL: 父产品存在!')
