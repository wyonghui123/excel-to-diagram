# -*- coding: utf-8 -*-
"""
Spec 08 Manual Intent 优先级 e2e 测试 (P2-B8 / FR-013)

[P2-B8 补充 2026-07-26]
背景:
  FR-013 manual intent 优先级最高, 覆盖 derived/template source
  derivation_pipeline._merge_manual_intents 已实现:
    - granted=true  → 强制加入 (若无), data_scope = 空 include (全允许)
    - granted=false → 强制排除 (覆盖为永假条件, id=-1 永不匹配)
  intent_api.grant_or_deny_intent / revoke_intent 已补充:
    - 变更后自动触发 derivation_pipeline.derive(role_id) 重推导
  缺少 e2e 测试直接验证 manual intent 优先级生效

测试目标:
  1. (A) manual granted=false 强制排除 (覆盖 derived intent)
       - baseline: wyonghui4 可见 sub_domain list (derived intent 允许部分)
       - admin 设置 manual granted=false (sub_domain:read)
       - derivation 自动触发, manual intent 覆盖 derived
       - wyonghui4 GET sub_domain list → 应该看不到任何 (永假条件 id=-1 生效)
       - 清理后恢复

  2. (B) manual granted=true 强制加入 (即使 derived 没推导出)
       - admin 设置 manual granted=true (某个未配置的 BO, 如 enum_type:read)
       - wyonghui4 GET enum_type list → 应该看到 (manual 强制加入)
       - 清理后恢复

测试用户:
  - admin: 配置 manual intent
  - wyonghui4: 持有 role 12010, 验证 API 行为
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


def call(opener, method, path, body=None):
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
    return status, parsed


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
print("Spec 08 Manual Intent 优先级 e2e 测试 (P2-B8 / FR-013)")
print("=" * 80)

print("\n[Setup] 登录所有测试用户")
users = {}
for username in ['admin', 'wyonghui4']:
    users[username] = make_session(username)
    print(f"  [OK] {username}")

admin = users['admin']
wyonghui4 = users['wyonghui4']


# ============================================================
# [P2-B8 修复 2026-07-26] 修正 ROLE_ID + 添加预清理
# 问题:
#   1. 原测试 ROLE_ID=12010, 但 wyonghui4 (10009) 实际持有 role 12009
#      (12010 由 wyonghui3 持有), 导致 A2 设置 manual intent 在错误 role 上,
#      wyonghui4 的 role 12009 未受影响 → A3 失败.
#   2. 同一用户跨多个 role 时, 遗留的 wildcard/exclude 配置会触发 409 冲突.
# 修复:
#   1. 修正 ROLE_ID = 12009 (wyonghui4 实际持有的 role)
#   2. 预清理所有相关 role (11821/11993/12009/12010) 到 SAFE_BASELINE
#   3. 测试结束恢复所有相关 role 到原始状态
# 参考: e2e_spec_08_stale_rederive.py 同样修复模式
# ============================================================
ROLE_ID = 12009  # wyonghui4 (10009) 实际持有的 role, dim=sub_domain[339]
# 所有需要预清理的相关测试角色 (这些角色可能被同一用户持有, 触发跨角色冲突)
# wyonghui3 (10008) 持有 11993 + 12009 + 12010, wyonghui4 (10009) 持有 12009,
# wyonghui2 (10007) 持有 11821 + 11993, wyonghui (10006) 持有 11821.
# 给 12009 加 manual granted=false 时, 同持有 12009 的 wyonghui3 的其他 role (11993/12010)
# 若有 wildcard 会触发 409 冲突 → 必须先重置所有相关 role.
RELATED_ROLE_IDS = [11821, 11993, 12009, 12010]
# 安全的 include-only baseline (避免 wildcard/exclude 冲突)
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
ORIGINAL_DIM_SCOPES = {}  # {role_id: [scope_dict, ...]}


def restore_dim_scope(role_id):
    """恢复 role 的原始 dim_scope"""
    scopes = ORIGINAL_DIM_SCOPES.get(role_id, [])
    clean_scopes = []
    for s in scopes:
        vals = s.get('dimension_values', [])
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
    status, _ = call(admin, 'POST', f'/api/v1/roles/{role_id}/dimension-scopes',
                    body=clean_scopes)
    return status


def restore_all_related_roles():
    """恢复所有相关角色到测试前的原始状态"""
    for rid in RELATED_ROLE_IDS:
        restore_dim_scope(rid)


# ============================================================
# Part A0: 保存原始 dim_scope + 预清理相关角色
# ============================================================
print("\n" + "=" * 80)
print("Part A0: 保存原始 dim_scope + 预清理相关角色")
print("=" * 80)

print(f"\n[A0.1] 保存所有相关角色的原始 dim_scope")
for rid in RELATED_ROLE_IDS:
    status, resp = call(admin, 'GET', f'/api/v1/roles/{rid}/dimension-scopes')
    scopes = []
    if status == 200 and isinstance(resp, dict):
        items = resp.get('data', [])
        if isinstance(items, list):
            for item in items:
                scopes.append({
                    'dimension_code': item.get('dimension_code'),
                    'dimension_values': item.get('dimension_values'),
                    'scope_mode': item.get('scope_mode', 'include'),
                    'inherit_children': item.get('inherit_children', 1),
                })
    ORIGINAL_DIM_SCOPES[rid] = scopes
    print(f"  role {rid}: {len(scopes)} scopes saved")

print(f"\n[A0.2] 预清理: 重置所有相关角色到 SAFE_BASELINE (避免跨角色 409 冲突)")
reset_ok_count = 0
for rid in RELATED_ROLE_IDS:
    baseline = SAFE_BASELINES.get(rid, [])
    if not baseline:
        continue
    status, resp = call(admin, 'POST', f'/api/v1/roles/{rid}/dimension-scopes',
                       body=baseline)
    if status == 200:
        reset_ok_count += 1
        print(f"  role {rid}: RESET OK")
    else:
        print(f"  role {rid}: RESET FAIL status={status}")
results.append(('A0.2: 预清理所有相关角色到 SAFE_BASELINE',
                reset_ok_count == len(RELATED_ROLE_IDS)))


# ============================================================
# Part A: manual granted=false 强制排除 (覆盖 derived intent)
# ============================================================
print("\n" + "=" * 80)
print("Part A: manual granted=false 强制排除 (覆盖 derived)")
print("=" * 80)

# A1: 基线 - wyonghui4 GET sub_domain list
# 预清理后 role 12009 dim_scope = sub_domain include [339]
# → wyonghui4 应该看到 339 (及其子节点)
print("\n[A1] wyonghui4 GET sub_domain list (基线, 期望含 339)")
status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
baseline_count = len(items)
baseline_has_339 = any(item.get('id') == 339 for item in items)
print(f"  wyonghui4 baseline sub_domain count: {baseline_count}, 含 339: {baseline_has_339}")
results.append(('A1: wyonghui4 基线 sub_domain 查询成功 (含 339)',
                baseline_count >= 0 and baseline_has_339))

# A2: admin 设置 manual granted=false (sub_domain:read)
# 通过 PUT /api/v2/roles/{role_id}/intents/{bo_id}/{action_name}
# body: {"granted": false, "source": "manual"}
# [P2-B8 修复] 使用正确的 ROLE_ID=12009 (wyonghui4 实际持有的 role)
print(f"\n[A2] admin PUT /api/v2/roles/{ROLE_ID}/intents/sub_domain/read (granted=false)")
status, resp = call(admin, 'PUT',
    f'/api/v2/roles/{ROLE_ID}/intents/sub_domain/read',
    body={'granted': False, 'source': 'manual'})
print(f"  PUT status: {status}")
manual_deny_set = (status in (200, 201))
results.append(('A2: 设置 manual granted=false (sub_domain:read)', manual_deny_set))

if manual_deny_set:
    # A3: wyonghui4 GET sub_domain list → 应该看不到任何 (永假条件 id=-1 生效)
    # IntentScopeAdapter 会生成 SQL: WHERE id = -1 (永不匹配)
    # [P2-B8 修复] 现在使用正确的 ROLE_ID=12009, manual intent 真正作用于 wyonghui4 的 role
    print("\n[A3] wyonghui4 GET sub_domain list (期望空, manual granted=false 生效)")
    status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
    items = get_data_items(resp)
    after_deny_count = len(items)
    after_deny_has_339 = any(item.get('id') == 339 for item in items)
    print(f"  wyonghui4 sub_domain count (期望 0): {after_deny_count}, 含 339: {after_deny_has_339}")
    # 期望: 0 (永假条件生效, derived intent 被覆盖)
    # 注意: 如果有 owner 命中, 仍可能可见 (但 wyonghui4 不太可能是 sub_domain owner)
    results.append(('A3: manual granted=false 强制排除生效 (sub_domain 不可见)',
                    after_deny_count == 0))

    # A4: 清理 - DELETE manual intent
    print(f"\n[A4] admin DELETE /api/v2/roles/{ROLE_ID}/intents/sub_domain/read")
    status, resp = call(admin, 'DELETE',
        f'/api/v2/roles/{ROLE_ID}/intents/sub_domain/read')
    print(f"  DELETE status: {status}")
    results.append(('A4: 清理 manual intent (DELETE)', status == 200))

    # A5: wyonghui4 GET sub_domain list → 应该恢复
    print("\n[A5] wyonghui4 GET sub_domain list (期望恢复含 339)")
    status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
    items = get_data_items(resp)
    after_restore_count = len(items)
    after_restore_has_339 = any(item.get('id') == 339 for item in items)
    print(f"  wyonghui4 sub_domain count (期望恢复): {after_restore_count}, 含 339: {after_restore_has_339}")
    # 期望: 恢复含 339 (manual intent 已 DELETE, derived 重新生效)
    results.append(('A5: 恢复后 sub_domain 可见性恢复 (含 339)',
                    after_restore_has_339))


# ============================================================
# Part B: manual granted=true 强制加入 (即使 derived 没推导出)
# ============================================================
# [P2-B8 改进 2026-07-26] 重新设计 Part B 测试逻辑
# 原设计问题:
#   - B2 设置 export action, B3 检查 list (read) → 测试无效
#   - export 在 read LEVEL_BUNDLE 中, derived 已生成 → 无法验证 "强制加入"
# 新设计:
#   - B1: 先设置 manual granted=false (sub_domain:read) → wyonghui4 不可见
#   - B2: 再设置 manual granted=true (sub_domain:read) → 覆盖 granted=false
#   - B3: 验证 wyonghui4 可见 (manual granted=true 优先级生效)
#   - B4: 清理
# 这样能真正验证 "manual granted=true 强制加入 (覆盖 granted=false)"
# ============================================================
print("\n" + "=" * 80)
print("Part B: manual granted=true 强制加入 (覆盖 manual granted=false)")
print("=" * 80)

# B1: 先设置 manual granted=false (sub_domain:read)
print(f"\n[B1] admin PUT /api/v2/roles/{ROLE_ID}/intents/sub_domain/read (granted=false)")
status, resp = call(admin, 'PUT',
    f'/api/v2/roles/{ROLE_ID}/intents/sub_domain/read',
    body={'granted': False, 'source': 'manual'})
print(f"  PUT status: {status}")
b1_ok = (status in (200, 201))
results.append(('B1: 设置 manual granted=false (sub_domain:read)', b1_ok))

if b1_ok:
    # B1.1: 验证 wyonghui4 看不到 sub_domain (granted=false 生效)
    print("\n[B1.1] wyonghui4 GET sub_domain list (期望空, granted=false 生效)")
    status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
    items_b1 = get_data_items(resp)
    b1_count = len(items_b1)
    print(f"  wyonghui4 sub_domain count (期望 0): {b1_count}")
    results.append(('B1.1: granted=false 生效 (sub_domain 不可见)', b1_count == 0))

# B2: 设置 manual granted=true (覆盖 granted=false)
# 同一 (role, bo, action) 的 manual intent 应该被覆盖为 granted=true
print(f"\n[B2] admin PUT /api/v2/roles/{ROLE_ID}/intents/sub_domain/read (granted=true)")
status, resp = call(admin, 'PUT',
    f'/api/v2/roles/{ROLE_ID}/intents/sub_domain/read',
    body={'granted': True, 'source': 'manual'})
print(f"  PUT status: {status}")
b2_ok = (status in (200, 201))
results.append(('B2: 设置 manual granted=true (覆盖 granted=false)', b2_ok))

if b2_ok:
    # B3: 验证 wyonghui4 可以看到 sub_domain (manual granted=true 强制加入)
    # manual granted=true → data_scope = {include:[], exclude:[]} (空 include = 全允许)
    # → IntentScopeAdapter 不加 WHERE → 允许所有
    print("\n[B3] wyonghui4 GET sub_domain list (期望 > 0, manual granted=true 生效)")
    status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
    items_b3 = get_data_items(resp)
    after_grant_count = len(items_b3)
    after_grant_has_339 = any(item.get('id') == 339 for item in items_b3)
    print(f"  wyonghui4 sub_domain count (期望 > 0): {after_grant_count}, 含 339: {after_grant_has_339}")
    # 期望: > 0 (manual granted=true 强制加入, data_scope=空 include=全允许)
    results.append(('B3: manual granted=true 后 sub_domain 可见', after_grant_count > 0))

    # B4: 清理 - DELETE manual intent
    print(f"\n[B4] admin DELETE /api/v2/roles/{ROLE_ID}/intents/sub_domain/read")
    status, resp = call(admin, 'DELETE',
        f'/api/v2/roles/{ROLE_ID}/intents/sub_domain/read')
    print(f"  DELETE status: {status}")
    results.append(('B4: 清理 manual intent (DELETE)', status == 200))


# ============================================================
# 最终清理: 恢复所有相关角色到测试前原始状态
# ============================================================
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
    status_str = "[PASS]" if ok else "[FAIL]"
    print(f"  {status_str} {name}")

passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"\n总计: {passed}/{total} 通过")
