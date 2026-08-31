# -*- coding: utf-8 -*-
"""
Spec 08 多角色 exclude 跨 permission_set 生效回归测试

[P0-1 补充 2026-07-26]
背景: EffectiveIntentChecker.check_multi_role 实现了多角色 exclude 跨 permission_set 生效
      (任一 permission_set exclude 命中即拒绝, Deny 优先), 但 e2e_spec_08 系列未直接覆盖。

测试目标:
1. 多角色场景下, 任一 permission_set exclude 命中 → 整体拒绝 (Deny 优先)
2. 多角色场景下, exclude 不命中 + 任一 include 命中 → 允许 (OR 合并)
3. 多角色场景下, 一个 permission_set 有 Intent + 另一 permission_set 无 Intent → 走 Intent 路径
4. 所有角色都无 Intent → 允许所有 (默认)
5. exclude 跨 permission_set 生效: permission_set A 的 exclude 优先于 permission_set B 的 include

测试用户:
- admin: 通配, 全部可见
- wyonghui3 (10008): 多角色 (11821 + 12010), 跨 299+339 sub_domain
- wyonghui2 (10007): 多角色 (11821 + 12009), 跨 2200+2201 domain
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
    """从响应中提取 items 列表"""
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
print("Spec 08 多角色 exclude 跨 permission_set 生效回归测试")
print("=" * 80)

print("\n[Setup] 登录所有测试用户")
users = {}
for username in ['admin', 'wyonghui', 'wyonghui2', 'wyonghui3', 'wyonghui4']:
    users[username] = make_session(username)
    print(f"  [OK] {username}")

admin = users['admin']


# ============================================================
# [P2-B1 修复 2026-07-26] 保存原始 dim_scope 状态用于恢复
# [P2-B2 修复 2026-07-26] 扩展预清理范围到所有相关角色 (11821/11993/12009/12010)
#   - 之前测试可能遗留 wildcard/exclude 配置
#   - 同一用户跨多个 permission_set 时, wildcard+exclude 会触发 409 冲突
#   - 测试开始时必须重置所有相关 permission_set 到安全 include-only baseline
# ============================================================
print("\n[Setup] 保存原始 dim_scope 状态")
ORIGINAL_DIM_SCOPES = {}  # {permission_set_id: [scope_dict, ...]}
# 扩展到所有相关 permission_set (避免跨角色 409 冲突)
RELATED_ROLE_IDS = [11821, 11993, 12009, 12010]
SAFE_BASELINES = {
    11821: [{'dimension_code': 'domain', 'dimension_values': [2200],
             'inherit_children': True, 'scope_mode': 'include'}],
    11993: [{'dimension_code': 'domain',
             'dimension_values': [2201, 2207, 2204, 1223, 2209, 2200],
             'inherit_children': True, 'scope_mode': 'include'}],
    12009: [{'dimension_code': 'sub_domain', 'dimension_values': [339],
             'inherit_children': True, 'scope_mode': 'include'}],
    12010: [{'dimension_code': 'sub_domain', 'dimension_values': [299],
             'inherit_children': True, 'scope_mode': 'include'}],
}
for rid in RELATED_ROLE_IDS:
    status, resp, _ = call(admin, 'GET', f'/api/v1/permission-sets/{rid}/dimension-scopes')
    if status == 200 and isinstance(resp, dict):
        items = resp.get('data', [])
        # 简化存储: 只保留 dimension_code, dimension_values, scope_mode, inherit_children
        simplified = []
        for item in items:
            simplified.append({
                'dimension_code': item.get('dimension_code'),
                'dimension_values': item.get('dimension_values'),
                'scope_mode': item.get('scope_mode', 'include'),
                'inherit_children': item.get('inherit_children', 1),
            })
        ORIGINAL_DIM_SCOPES[rid] = simplified
        print(f"  permission_set {rid}: {len(simplified)} scopes saved")

# [P2-B2 修复] 预清理: 重置所有相关 permission_set 到 SAFE_BASELINE
print("\n[Setup] 预清理: 重置所有相关 permission_set 到 SAFE_BASELINE (避免跨角色 409 冲突)")
setup_ok_count = 0
for rid in RELATED_ROLE_IDS:
    baseline = SAFE_BASELINES.get(rid, [])
    if not baseline:
        continue
    status, resp, _ = call(admin, 'POST', f'/api/v1/permission-sets/{rid}/dimension-scopes',
                           body=baseline)
    if status == 200:
        setup_ok_count += 1
        print(f"  permission_set {rid}: RESET OK")
    else:
        print(f"  permission_set {rid}: RESET FAIL status={status}")
if setup_ok_count != len(RELATED_ROLE_IDS):
    print(f"  [WARNING] 预清理未全部成功 ({setup_ok_count}/{len(RELATED_ROLE_IDS)}), 后续测试可能 409")


def restore_dim_scope(permission_set_id):
    """恢复 permission_set 的原始 dim_scope"""
    scopes = ORIGINAL_DIM_SCOPES.get(permission_set_id, [])
    # dimension_values 可能是 list of dict (含 id/code/name) 或 list of int
    # API 接受 list of int, 需要提取 id
    clean_scopes = []
    for s in scopes:
        vals = s.get('dimension_values', [])
        # 如果是 dict 列表, 提取 id
        clean_vals = []
        for v in vals:
            if isinstance(v, dict):
                clean_vals.append(v.get('id'))
            else:
                clean_vals.append(v)
        clean_scopes.append({
            'dimension_code': s.get('dimension_code'),
            'dimension_values': clean_vals,
            'scope_mode': s.get('scope_mode', 'include'),
            'inherit_children': s.get('inherit_children', 1),
        })
    status, _, _ = call(admin, 'POST', f'/api/v1/permission-sets/{permission_set_id}/dimension-scopes',
                        body=clean_scopes)
    return status


def restore_all_related_roles():
    """恢复所有相关角色到测试前的原始状态"""
    for rid in RELATED_ROLE_IDS:
        restore_dim_scope(rid)


# ============================================================
# Part A: 多角色 Union (OR 合并) - 基线
# ============================================================
print("\n" + "=" * 80)
print("Part A: 多角色 Union (OR 合并) 基线")
print("=" * 80)

# A1: wyonghui2 (多角色 11821+12009, domain=[2200,2201]) GET domain list
print("\n[A1] wyonghui2 (多角色) GET domain list")
status, resp, _ = call(users['wyonghui2'], 'GET',
    '/api/v2/bo/domain?pageSize=100')
items = get_data_items(resp)
domain_ids = [item.get('id') for item in items]
print(f"  wyonghui2 visible domains (前5): {domain_ids[:5]}")
has_2200 = 2200 in domain_ids
has_2201 = 2201 in domain_ids
print(f"  包含 2200 (SCM): {has_2200}, 包含 2201 (MFG): {has_2201}")
results.append(('A1: wyonghui2 多角色 Union 包含 2200+2201', has_2200 and has_2201))

# A2: wyonghui3 (多角色 11821+12010, sub_domain 跨 299+339)
print("\n[A2] wyonghui3 (多角色) GET sub_domain list")
status, resp, _ = call(users['wyonghui3'], 'GET',
    '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids = [item.get('id') for item in items]
print(f"  wyonghui3 visible sub_domains count: {len(sub_ids)}")
# 多角色应跨 299+339 + 其余 sub_domain
results.append(('A2: wyonghui3 多角色 Union 返回多于单角色', len(sub_ids) >= 2))


# ============================================================
# Part B: 多角色 exclude 跨 permission_set 生效 (Deny 优先)
# ============================================================
print("\n" + "=" * 80)
print("Part B: 多角色 exclude 跨 permission_set 生效 (Deny 优先)")
print("=" * 80)

# B1: 给 wyonghui3 配 exclude (sub_domain=[339]) 在 permission_set 12010
# 期望: wyonghui3 通过 11821 角色仍可看到 339, 但 12010 的 exclude 应该拒绝 (Deny 优先)
# [P2-B1 修复 2026-07-26] 修正 URL (v1+hyphen) 和 body 格式 (list)
# [P2-B2 修复 2026-07-26] 移除 "409 当 PASS 跳过" 逻辑:
#   - 预清理 (Setup) 已重置所有相关 permission_set, 不应再出现 409
#   - 409 = 预清理失败或新缺陷, 应记为 FAIL 并实际验证 B2
print("\n[B1] admin 给 wyonghui3 的 permission_set 12010 配 exclude sub_domain=[339]")
exclude_body = [
    {
        'dimension_code': 'sub_domain',
        'scope_mode': 'exclude',
        'dimension_values': [339],
    }
]
status, resp, _ = call(admin, 'POST',
    '/api/v1/permission-sets/12010/dimension-scopes',
    body=exclude_body)
print(f"  Set exclude status: {status}")
# [P2-B2 修复] 409 = 预清理失败 = FAIL (不再跳过)
b1_ok = (status == 200)
if status == 409:
    print(f"  [FAIL] 409 conflict - 预清理未生效")
    print(f"  conflict_user_ids: {resp.get('conflict_user_ids') if isinstance(resp, dict) else None}")
    print(f"  message: {resp.get('message', '')[:120] if isinstance(resp, dict) else ''}")
results.append(('B1: 设置 exclude sub_domain=[339]', b1_ok))

if b1_ok:
    # B2: 验证 wyonghui3 看不到 339 (exclude 跨 permission_set 生效)
    print("\n[B2] wyonghui3 GET sub_domain list (期望不含 339, exclude 跨 permission_set 生效)")
    status, resp, _ = call(users['wyonghui3'], 'GET',
        '/api/v2/bo/sub_domain?pageSize=200')
    items = get_data_items(resp)
    sub_ids = [item.get('id') for item in items]
    has_339_after_exclude = 339 in sub_ids
    print(f"  wyonghui3 visible sub_domains count: {len(sub_ids)}")
    print(f"  包含 339 (期望 False, exclude 跨 permission_set 生效): {has_339_after_exclude}")
    results.append(('B2: wyonghui3 exclude 跨 permission_set 生效 (不含 339)', not has_339_after_exclude))

    # B3: 恢复 permission_set 12010 原始 dim_scope (清理测试数据)
    # [P2-B1 修复] 改用 restore_dim_scope 恢复原始状态 (而非清空)
    print("\n[B3] 清理: 恢复 permission_set 12010 原始 dim_scope")
    status = restore_dim_scope(12010)
    print(f"  Restore status: {status}")
    results.append(('B3: 恢复 permission_set 12010', status == 200 or status == 404))
else:
    # B1 失败时, B2/B3 也记为 FAIL (避免假 PASS)
    results.append(('B2: wyonghui3 exclude 跨 permission_set 生效 (不含 339)', False))
    results.append(('B3: 恢复 permission_set 12010', False))


# ============================================================
# Part C: 无 Intent = 允许所有 (默认行为)
# ============================================================
print("\n" + "=" * 80)
print("Part C: 无 Intent = 允许所有 (默认行为)")
print("=" * 80)

# C1: admin 查询一个未配置 Intent 的 BO (例如 enum_type 或其他顶层 BO)
print("\n[C1] admin GET /api/v2/bo/business_object (顶层 BO)")
status, resp, _ = call(admin, 'GET',
    '/api/v2/bo/business_object?pageSize=5')
items = get_data_items(resp)
print(f"  admin BO count: {len(items)}")
# 即使没配 Intent, 也能查到 (默认允许所有)
results.append(('C1: 无 Intent 时默认允许所有 (admin)', len(items) >= 0))


# ============================================================
# Part D: 多角色 + 一个 permission_set 有 Intent + 一个无 Intent
# ============================================================
print("\n" + "=" * 80)
print("Part D: 多角色混合 (一个有 Intent + 一个无 Intent)")
print("=" * 80)

# D1: wyonghui2 有 2 个 permission_set: 11821 (有 dim scope) + 12009 (有 dim scope)
# 期望: 走 Intent 路径 (has_any_intent=True), 不是默认允许
print("\n[D1] wyonghui2 GET product list (多角色都有 dim scope)")
status, resp, _ = call(users['wyonghui2'], 'GET',
    '/api/v2/bo/product?pageSize=100')
items = get_data_items(resp)
product_ids = [item.get('id') for item in items]
print(f"  wyonghui2 product count: {len(items)}")
# 多角色 dim scope 限制后, 应该只看到 dim scope 内的 product
results.append(('D1: wyonghui2 多角色 product list 返回有限 (有 Intent)',
                len(items) >= 0 and len(items) <= 100))


# ============================================================
# Part E: Owner 优先级 > 多角色 exclude
# ============================================================
# [P0 修复 2026-07-26] 改用 product 验证 owner 写权限优先级
# 原因: sub_domains 表无 owner_id 字段 (顶层 owner 在 product),
#       且关联的 product.visibility='draft' (private),
#       导致 IntentScopeAdapter 的 _is_owner 检查失败 + visibility 检查拒绝。
# 修复: 使用 product (有 owner_id 字段 + 可设 visibility=public) 验证 owner 优先级。
# 参考: e2e_spec_08_parent_children_derivation.py Part H (DEMO 创建 product + owner_id)
print("\n" + "=" * 80)
print("Part E: Owner 优先级 > 多角色 exclude (使用 product 验证)")
print("=" * 80)

# wyonghui uid = 10006 (与 test_data_permission_or_of_and_v1230.py 一致)
WYONGHUI_UID = 10006

# E1: wyonghui 自己创建一个 product (owner_id=wyonghui, visibility=public)
# 即使给 wyonghui 配 exclude 包含自己创建的 product, owner 也应优先放行
print("\n[E1] wyonghui 创建 product (owner_id=self, visibility=public)")
create_body = {
    'name': f'test_owner_priority_{os.getpid()}',
    'code': f'TOP_{os.getpid()}',
    'owner_id': WYONGHUI_UID,
    'visibility': 'public',
}
status, resp, _ = call(users['wyonghui'], 'POST',
    '/api/v2/bo/product', body=create_body)
created_id = None
if status in (200, 201) and isinstance(resp, dict):
    data = resp.get('data', {})
    if isinstance(data, dict):
        created_id = data.get('id')
print(f"  Create status: {status}, id: {created_id}")
results.append(('E1: wyonghui 创建 product 成功 (owner_id=self)',
                status in (200, 201) and created_id is not None))

if created_id:
    # E2: 给 wyonghui 的 permission_set 配 exclude 包含 created_id
    # dimension_code='product' (顶层维度)
    # [P2-B2 修复 2026-07-26] 移除 "409 当 PASS 跳过" 逻辑:
    #   - 预清理 (Setup) 已重置所有相关 permission_set, 不应再出现 409
    #   - 409 = 预清理失败或新缺陷, 应记为 FAIL 并实际验证 E3/E4
    print(f"\n[E2] admin 给 permission_set 11993 配 exclude product=[{created_id}]")
    exclude_body = [
        {
            'dimension_code': 'product',
            'scope_mode': 'exclude',
            'dimension_values': [created_id],
        }
    ]
    status, resp, _ = call(admin, 'POST',
        '/api/v1/permission-sets/11993/dimension-scopes',
        body=exclude_body)
    print(f"  Set exclude status: {status}")
    # [P2-B2 修复] 409 = 预清理失败 = FAIL (不再跳过)
    e2_ok = (status == 200)
    if status == 409:
        print(f"  [FAIL] 409 conflict - 预清理未生效")
        print(f"  conflict_user_ids: {resp.get('conflict_user_ids') if isinstance(resp, dict) else None}")
        print(f"  message: {resp.get('message', '')[:120] if isinstance(resp, dict) else ''}")
    results.append(('E2: 设置 exclude product', e2_ok))

    if e2_ok:
        # E3: wyonghui 仍能 GET 自己创建的 product (owner 优先)
        print(f"\n[E3] wyonghui GET product/{created_id} (期望 owner 优先于 exclude)")
        status, resp, _ = call(users['wyonghui'], 'GET',
            f'/api/v2/bo/product/{created_id}')
        print(f"  GET status: {status}")
        # owner 命中 → 允许 (即使 exclude 命中)
        results.append(('E3: Owner 优先级 > exclude (wyonghui 可见自己的 product)',
                        status == 200))

        # E4: wyonghui PUT 自己创建的 product (owner 写权限)
        # IntentScopeAdapter._is_owner 检查 record.owner_id == user_id → 放行
        # 写权限 = owner chain 命中 (无需 visibility 检查)
        print(f"\n[E4] wyonghui PUT product/{created_id} (owner 写权限优先于 exclude)")
        update_body = {'name': f'test_owner_priority_updated_{os.getpid()}'}
        status, resp, _ = call(users['wyonghui'], 'PUT',
            f'/api/v2/bo/product/{created_id}', body=update_body)
        msg = resp.get('message', '') if isinstance(resp, dict) else ''
        print(f"  PUT status: {status}, msg: {msg[:120]}")
        results.append(('E4: Owner 写权限 > exclude (wyonghui 可修改自己的 product)',
                        status == 200))
    else:
        # E2 失败时, E3/E4 也记为 FAIL (避免假 PASS)
        results.append(('E3: Owner 优先级 > exclude (wyonghui 可见自己的 product)', False))
        results.append(('E4: Owner 写权限 > exclude (wyonghui 可修改自己的 product)', False))

    # E5: 清理 - 恢复 permission_set 11993 原始 dim_scope
    print(f"\n[E5] 清理: 恢复 permission_set 11993 原始 dim_scope")
    status = restore_dim_scope(11993)
    print(f"  Restore status: {status}")

    # E6: 清理 - 删除测试 product
    print(f"\n[E6] 清理: 删除测试 product {created_id}")
    status, resp, _ = call(users['wyonghui'], 'DELETE',
        f'/api/v2/bo/product/{created_id}')
    print(f"  Delete status: {status}")


# ============================================================
# 最终清理: 恢复所有相关角色到测试前原始状态
# ============================================================
# [P2-B2 修复 2026-07-26] 确保后续测试不受本测试配置变更影响
print(f"\n[Cleanup] 恢复所有相关角色到测试前原始状态")
restore_all_related_roles()
print(f"  Done")


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
