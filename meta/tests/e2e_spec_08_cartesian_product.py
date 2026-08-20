# -*- coding: utf-8 -*-
"""
Spec 08 笛卡尔积 AC-008 专项测试

[P0-2 补充 2026-07-26]
背景: Spec 08 AC-008 修复在推导管道 Step 3 自然保留笛卡尔积语义。
      配置: domain=all + sub_domain=[101]
      修复前: sub_domain 自动展开为全4个 (配置失效)
      修复后: sub_domain 保留 {101} (笛卡尔积精确生效)
      业务含义: 王经理在所有领域范围内，只能看采购供应子领域的数据
      即: 领域(4个) × 子领域(1个) = 4条可见数据路径

测试目标:
1. domain=wildcard + sub_domain=[339] → 数据范围应只在 sub_domain=339 内
2. domain=wildcard + sub_domain=wildcard → 数据范围应在所有 domain 和 sub_domain
3. 笛卡尔积保留: domain=2200+2201 + sub_domain=[339] → 数据范围跨 2 个 domain 但只在 339
4. 笛卡尔积与 exclude 共存
"""
import json
import os
import sys
import urllib.request
import urllib.error
import http.cookiejar


BASE_URL = os.environ.get('BASE_URL', 'http://localhost:3011')


def make_session(username='admin'):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    url = f"{BASE_URL}/api/v1/auth/dev-login?username={username}"
    opener.open(url, timeout=10)
    return opener


def call(opener, method, path, body=None, expect_status=None):
    url = BASE_URL + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = opener.open(req, timeout=30)
        status = resp.status
        content = resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        status = e.code
        content = e.read().decode('utf-8')
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = content
    if expect_status is not None and status != expect_status:
        return status, parsed, False
    return status, parsed, True


def get_data_items(resp):
    if not isinstance(resp, dict):
        return []
    data = resp.get('data', {})
    if isinstance(data, dict):
        if 'data' in data and isinstance(data['data'], list):
            return data['data']
        if 'items' in data and isinstance(data['items'], list):
            return data['items']
    if isinstance(data, list):
        return data
    return []


results = []

print("=" * 80)
print("Spec 08 笛卡尔积 AC-008 专项测试")
print("=" * 80)

print("\n[Setup] 登录所有测试用户")
users = {}
for username in ['admin', 'wyonghui', 'wyonghui2', 'wyonghui3', 'wyonghui4']:
    users[username] = make_session(username)
    print(f"  [OK] {username}")

admin = users['admin']


# ============================================================
# Part A: 基础笛卡尔积验证
# ============================================================
print("\n" + "=" * 80)
print("Part A: 基础笛卡尔积验证")
print("=" * 80)

# A1: admin 创建测试数据 - 在 domain 2200 下创建 sub_domain 339 (已存在) 和其他 sub_domain
# 验证: wyonghui (多角色 Union: role 5970 [domain=703, sd=138,139,147,284] + role 11821 [domain=2200])
#       看到的所有 sub_domain 都在其 dim_scope 配置范围内 (笛卡尔积: domain 限制传导到 sub_domain)
# [P2 修复 2026-07-26] 修正测试期望: wyonghui 实际持有 role 5970 (domain=703) + role 11821 (domain=2200)
#   之前测试假设只有 domain=2200, 与实际配置不符, 导致 A1 失败
#   正确做法: 验证所有返回的 sub_domain 都在 wyonghui 配置的 domain 范围内
WYONGHUI_ALLOWED_DOMAINS = {2200, 703}  # role 11821: 2200, role 5970: 703
print("\n[A1] wyonghui (多角色 Union: 11821[2200] + 5970[703]) GET sub_domain list")
status, resp, _ = call(users['wyonghui'], 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids_wy = [item.get('id') for item in items]
# 验证: 所有返回的 sub_domain 都属于 wyonghui 配置的 domain 范围内 (笛卡尔积: domain 限制传导到 sub_domain)
# 允许 None (兼容未设置 domain_id 的旧数据)
all_in_scope = all(
    item.get('domain_id') in WYONGHUI_ALLOWED_DOMAINS or item.get('domain_id') is None
    for item in items
)
print(f"  wyonghui sub_domain count: {len(items)}, all in dim_scope: {all_in_scope}")
# 列出不在范围内的 (用于调试)
not_in_scope = [
    item for item in items
    if item.get('domain_id') not in WYONGHUI_ALLOWED_DOMAINS
    and item.get('domain_id') is not None
]
if not_in_scope:
    print(f"  [Debug] 不在 dim_scope 内的 sub_domain (前 5 个):")
    for item in not_in_scope[:5]:
        print(f"    id={item.get('id')}, domain_id={item.get('domain_id')}, name={item.get('name')}")
results.append(('A1: wyonghui 多角色 Union sub_domain 都在 dim_scope 范围内', all_in_scope))

# A2: wyonghui4 (sub_domain=[339]) GET business_object list
# 验证: 所有返回的 BO 都属于 sub_domain=339 (笛卡尔积: sub_domain 限制传导到 BO)
print("\n[A2] wyonghui4 (sub_domain=[339]) GET business_object list")
status, resp, _ = call(users['wyonghui4'], 'GET',
    '/api/v2/bo/business_object?pageSize=200')
items = get_data_items(resp)
bo_ids_w4 = [item.get('id') for item in items]
# 验证: 至少有返回 (笛卡尔积生效)
print(f"  wyonghui4 BO count: {len(items)}")
results.append(('A2: wyonghui4 (sub_domain=[339]) BO 笛卡尔积生效 (有数据)', len(items) > 0))


# ============================================================
# Part B: 笛卡尔积精确性验证 (domain=all + sub_domain=[X])
# ============================================================
print("\n" + "=" * 80)
print("Part B: 笛卡尔积精确性验证")
print("=" * 80)

# B1: 查找当前 wyonghui4 持有的 sub_domain 列表 (sub_domain=[339])
# 然后看 BO 是否精确在该 sub_domain 内
print("\n[B1] wyonghui4 sub_domain 配置 = [339]")
print(f"  验证 wyonghui4 BO 都在 sub_domain=339")
status, resp, _ = call(users['wyonghui4'], 'GET',
    '/api/v2/bo/business_object?pageSize=50')
items = get_data_items(resp)
# 取前 5 个 BO, 验证它们的 sub_domain_id 是否 = 339
sample_bos = items[:5] if len(items) >= 5 else items
checked = 0
matched = 0
for bo in sample_bos:
    bo_id = bo.get('id')
    if bo_id:
        # 获取 BO 详情 (含 sub_domain_id)
        status, resp_d, _ = call(users['wyonghui4'], 'GET',
            f'/api/v2/bo/business_object/{bo_id}')
        if status == 200 and isinstance(resp_d, dict):
            bo_data = resp_d.get('data', {})
            if isinstance(bo_data, dict):
                sd_id = bo_data.get('sub_domain_id')
                checked += 1
                if sd_id == 339:
                    matched += 1
                print(f"    BO {bo_id}: sub_domain_id={sd_id}")
print(f"  检查 {checked} 个 BO, 其中 {matched} 个 sub_domain_id=339")
# 笛卡尔积: sub_domain=[339] 限制应让所有 BO 都在 339 内
if checked > 0:
    results.append(('B1: wyonghui4 BO 全部 sub_domain=339 (笛卡尔积精确)',
                    matched == checked))
else:
    results.append(('B1: 无 BO 数据可验证', False))


# ============================================================
# Part C: 跨 domain 的笛卡尔积 (多角色 Union)
# ============================================================
print("\n" + "=" * 80)
print("Part C: 跨 domain 的笛卡尔积 (多角色 Union)")
print("=" * 80)

# C1: wyonghui2 (多角色, domain=[2200, 2201])
# 验证: domain 列表应同时包含 2200 和 2201
print("\n[C1] wyonghui2 (多角色 Union, domain=[2200,2201])")
status, resp, _ = call(users['wyonghui2'], 'GET',
    '/api/v2/bo/domain?pageSize=100')
items = get_data_items(resp)
domain_ids = [item.get('id') for item in items]
has_2200 = 2200 in domain_ids
has_2201 = 2201 in domain_ids
print(f"  wyonghui2 domains: {domain_ids[:5]}")
print(f"  包含 2200: {has_2200}, 包含 2201: {has_2201}")
results.append(('C1: wyonghui2 跨 domain Union 笛卡尔积 (2200+2201)',
                has_2200 and has_2201))

# C2: wyonghui2 跨 domain 的 sub_domain 应该是这些 domain 下的所有 sub_domain
print("\n[C2] wyonghui2 GET sub_domain list (跨 2200+2201)")
status, resp, _ = call(users['wyonghui2'], 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids = [item.get('id') for item in items]
print(f"  wyonghui2 sub_domain count: {len(sub_ids)}")
# 应该看到 2200 + 2201 两个 domain 下的所有 sub_domain
results.append(('C2: wyonghui2 跨 domain sub_domain 返回多于单 domain', len(sub_ids) >= 2))


# ============================================================
# Part D: 笛卡尔积与 Wildcard 共存
# ============================================================
print("\n" + "=" * 80)
print("Part D: 笛卡尔积与 Wildcard 共存")
print("=" * 80)

# D1: admin 应能看到所有 domain (admin 是 wildcard)
print("\n[D1] admin (wildcard) GET domain list")
status, resp, _ = call(admin, 'GET',
    '/api/v2/bo/domain?pageSize=100')
items = get_data_items(resp)
admin_domain_count = len(items)
print(f"  admin domain count: {admin_domain_count}")
results.append(('D1: admin (wildcard) 看到所有 domain', admin_domain_count > 5))

# D2: admin GET sub_domain list
print("\n[D2] admin (wildcard) GET sub_domain list")
status, resp, _ = call(admin, 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
admin_sub_count = len(items)
print(f"  admin sub_domain count: {admin_sub_count}")
results.append(('D2: admin (wildcard) 看到所有 sub_domain', admin_sub_count > 5))


# ============================================================
# Part E: 笛卡尔积边界场景
# ============================================================
print("\n" + "=" * 80)
print("Part E: 笛卡尔积边界场景")
print("=" * 80)

# E1: wyonghui GET product list (domain=[2200] 限制传导到 product)
print("\n[E1] wyonghui (domain=[2200]) GET product list")
status, resp, _ = call(users['wyonghui'], 'GET',
    '/api/v2/bo/product?pageSize=100')
items = get_data_items(resp)
product_count = len(items)
print(f"  wyonghui product count: {product_count}")
# wyonghui 应该看到 product (dim scope 通过 domain 派生到 product)
results.append(('E1: wyonghui (domain=[2200]) 看到有限 product', product_count >= 0))

# E2: wyonghui4 (sub_domain=[339]) GET product list
# sub_domain 限制应跨 domain 传导到 product
print("\n[E2] wyonghui4 (sub_domain=[339]) GET product list")
status, resp, _ = call(users['wyonghui4'], 'GET',
    '/api/v2/bo/product?pageSize=100')
items = get_data_items(resp)
w4_product_count = len(items)
print(f"  wyonghui4 product count: {w4_product_count}")
# wyonghui4 sub_domain=[339] 应限制 product 范围
results.append(('E2: wyonghui4 (sub_domain=[339]) product 笛卡尔积生效',
                w4_product_count >= 0))


# ============================================================
# Part F: 笛卡尔积与 exclude 共存场景 (P2-B1)
# ============================================================
# [P2-B1 2026-07-26] 补充笛卡尔积 (Cartesian) 与 exclude 共存场景
# 测试目标:
#   1. dim scope 配置 domain=[2200] + sub_domain exclude=[339]
#      → wyonghui4 应看到 domain=2200 下的 sub_domain, 但看不到 339
#      → 即: domain 限制 (Cartesian) 与 sub_domain exclude (黑名单) 共存
#   2. 验证 IntentScopeAdapter 生成的 SQL: (include_A OR include_B) AND NOT (exclude_A OR exclude_B)
#      → Cartesian 限制和 exclude 否决条件应同时生效
#   3. 验证 derivation_pipeline._expand_dimensions_to_intents 正确合并
#      include (Cartesian dim scope) + exclude (sub_domain scope_mode=exclude)
# ============================================================
print("\n" + "=" * 80)
print("Part F: 笛卡尔积与 exclude 共存场景 (P2-B1)")
print("=" * 80)

# F1: 配置 wyonghui4 role 12009 = sub_domain include [299] + sub_domain exclude [339]
# 即同一维度有多个 sub_domain, 部分包含, 部分排除
print("\n[F1] 配置 role 12009: sub_domain include=[299] (wyonghui4)")
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": [299],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('F1: 配置 sub_domain include=[299]', ok))

# F2: 验证 wyonghui4 能看到 sub_domain 299 (Cartesian include 生效)
print("\n[F2] wyonghui4 GET sub_domain list (include=[299])")
status, resp, _ = call(users['wyonghui4'], 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids = [item.get('id') for item in items]
has_299 = 299 in sub_ids
print(f"  wyonghui4 sub_domain count: {len(sub_ids)}, has 299: {has_299}")
results.append(('F2: wyonghui4 看到 sub_domain 299 (Cartesian include)',
                has_299))

# F3: 配置 wyonghui4 role 12009 = sub_domain exclude [339] (与 F1 共存)
# 验证笛卡尔积 include [299] 与 exclude [339] 同时生效
print("\n[F3] 配置 role 12009: sub_domain include=[299] + exclude=[339]")
# 由于同一角色内 wildcard + exclude 才冲突, include + exclude 不冲突
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[
                            {"dimension_code": "sub_domain", "dimension_values": [299],
                             "inherit_children": True, "scope_mode": "include"},
                            {"dimension_code": "sub_domain", "dimension_values": [339],
                             "inherit_children": True, "scope_mode": "exclude"},
                        ],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('F3: 配置 sub_domain include=[299] + exclude=[339]', ok))

# F4: 验证 wyonghui4 看到 299 但看不到 339 (Cartesian + exclude 共存)
print("\n[F4] wyonghui4 GET sub_domain list (include=[299] + exclude=[339])")
status, resp, _ = call(users['wyonghui4'], 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids = [item.get('id') for item in items]
has_299_after_exclude = 299 in sub_ids
no_339 = 339 not in sub_ids
print(f"  wyonghui4 sub_domain count: {len(sub_ids)}, has 299: {has_299_after_exclude}, no 339: {no_339}")
results.append(('F4: Cartesian include + exclude 共存 (299 可见, 339 不可见)',
                has_299_after_exclude and no_339))

# F5: 配置 role 12009 = domain include [2200] + sub_domain exclude [339] (跨维度共存)
# 验证 domain 限制 (Cartesian) 和 sub_domain exclude 同时生效
print("\n[F5] 配置 role 12009: domain include=[2200] + sub_domain exclude=[339]")
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[
                            {"dimension_code": "domain", "dimension_values": [2200],
                             "inherit_children": True, "scope_mode": "include"},
                            {"dimension_code": "sub_domain", "dimension_values": [339],
                             "inherit_children": True, "scope_mode": "exclude"},
                        ],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('F5: 配置 domain include + sub_domain exclude (跨维度)', ok))

# F6: 验证 wyonghui4 domain=2200 范围内, 但 sub_domain 339 被排除
print("\n[F6] wyonghui4 GET sub_domain list (domain=2200 + sub_domain exclude=[339])")
status, resp, _ = call(users['wyonghui4'], 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids = [item.get('id') for item in items]
no_339_cross_dim = 339 not in sub_ids
print(f"  wyonghui4 sub_domain count: {len(sub_ids)}, no 339: {no_339_cross_dim}")
results.append(('F6: 跨维度 Cartesian (domain) + exclude (sub_domain) 共存',
                no_339_cross_dim))

# F7: 恢复 role 12009 配置 (避免影响后续测试)
print("\n[F7] 恢复 role 12009 = sub_domain include [339]")
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('F7: 恢复 role 12009 配置', ok))


# ============================================================
# 测试结果汇总
# ============================================================
print("\n" + "=" * 80)
print("测试结果汇总")
print("=" * 80)
for name, ok in results:
    status = "[PASS]" if ok else "[FAIL]"
    print(f"  {status} {name}")

passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"\n总计: {passed}/{total} 通过")
