# -*- coding: utf-8 -*-
"""
Spec 08 Stale 自动重推导机制 e2e 测试 (P1-B3 / C1)

[P1-B3 补充 2026-07-26]
背景:
  derivation_pipeline.derive() 已在 dim_scope 变更时自动触发
  (见 role_dimension_scope_api.py L497-L516)
  但缺少 e2e 测试直接验证:
    1. 配置变更后 role_effective_intents 表数据自动更新 (stale 标记 → 0)
    2. IntentScopeAdapter 行为反映新配置 (排除项立即生效)
    3. 配置恢复后 Intent 自动恢复 (重新 derive)

测试目标:
  1. (C1) stale 标记机制: dim_scope 变更 → mark_stale → derive → clear_stale
  2. (C2) Intent 一致性: 配置变更后 API 行为立即反映新 Intent
  3. (C3) 恢复测试: 配置恢复后 API 行为恢复原状

测试方法:
  通过观察 wyonghui4 的 sub_domain 可见性变化, 间接验证:
    - dim_scope POST → derivation_pipeline 自动触发 → role_effective_intents 更新
    - IntentScopeAdapter 读取最新 effective_intents → SQL 过滤反映新 exclude

测试用户:
  - admin: 配置 dim_scope
  - wyonghui4: 持有 role 12010 (sub_domain 配置), 验证 API 行为
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
print("Spec 08 Stale 自动重推导机制 e2e 测试 (P1-B3 / C1)")
print("=" * 80)

print("\n[Setup] 登录所有测试用户")
users = {}
for username in ['admin', 'wyonghui4']:
    users[username] = make_session(username)
    print(f"  [OK] {username}")

admin = users['admin']
wyonghui4 = users['wyonghui4']


# ============================================================
# Part A: 保存原始 dim_scope (用于恢复) + 预清理相关角色
# ============================================================
# [P2-B2 修复 2026-07-26]
# 问题: 之前测试 (e2e_spec_08_wildcard_exclude.py 等) 可能遗留 wildcard/exclude
#       配置在 role 11821/12009 上, 导致本测试给 12010 加 exclude 时
#       触发跨角色冲突 (409 DIM_SCOPE_CONFLICT), 测试被当作 PASS 跳过。
# 修复:
#   1. 测试开始时, 主动重置所有相关测试角色 (11821/11993/12009/12010) 到
#      安全的 include-only baseline, 确保没有遗留的 wildcard/exclude。
#   2. 移除 "409 当 PASS 跳过" 的逻辑, 409 表示预清理失败, 应记为 FAIL。
#   3. 实际执行 stale 重推导验证 (C2/C3/C4) 而非跳过。
# ============================================================
print("\n" + "=" * 80)
print("Part A: 保存原始 dim_scope 状态 + 预清理相关角色")
print("=" * 80)

# [P2-B2 修复 2026-07-26] 修正 ROLE_ID: wyonghui4 (10009) 实际持有 role 12009
# (原测试误用 12010, 而 12010 由 wyonghui3 持有, 导致测试目标错位)
ROLE_ID = 12009  # wyonghui4 (10009) 实际持有的 role, dim=sub_domain[339]
# 所有需要预清理的相关测试角色 (这些角色可能被同一用户持有, 触发跨角色冲突)
# wyonghui3 (10008) 持有 11993 + 12009 + 12010, wyonghui4 (10009) 持有 12009,
# wyonghui2 (10007) 持有 11821 + 11993, wyonghui (10006) 持有 11821.
# 给 12009 加 exclude 时, 同持有 12009 的 wyonghui3 的其他 role (11993/12010)
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

# A0: 保存所有相关角色的原始 dim_scope (用于恢复)
print(f"\n[A0] 保存所有相关角色的原始 dim_scope")
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

# A1: 预清理 - 重置所有相关角色到安全的 include-only baseline
print(f"\n[A1] 预清理: 重置所有相关角色到 include-only baseline")
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
results.append(('A1: 预清理所有相关角色到 include-only baseline',
                reset_ok_count == len(RELATED_ROLE_IDS)))


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
# Part B: 基线 - wyonghui4 当前可见的 sub_domain (含 339)
# ============================================================
# [P2-B2 修复 2026-07-26]
# A1 已将 role 12009 重置为 sub_domain include [339],
# 所以 wyonghui4 基线应该看到 339.
# 如果基线不含 339, 说明 A1 预清理失败, 后续 C2/C4 验证无意义.
# ============================================================
print("\n" + "=" * 80)
print("Part B: 基线 - wyonghui4 当前可见的 sub_domain (含 339)")
print("=" * 80)

print("\n[B1] wyonghui4 GET sub_domain list (基线, 期望含 339)")
status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
items = get_data_items(resp)
sub_ids_baseline = [item.get('id') for item in items]
has_339_baseline = 339 in sub_ids_baseline
print(f"  wyonghui4 visible sub_domains count: {len(sub_ids_baseline)}")
print(f"  包含 339 (基线, 期望 True): {has_339_baseline}")
results.append(('B1: wyonghui4 基线含 339 (A1 预清理生效)', has_339_baseline))


# ============================================================
# Part C: 配置变更 - admin 给 role 12009 添加 exclude sub_domain=[339]
# 期望: derivation_pipeline 自动触发, Intent 更新, wyonghui4 立即看不到 339
# ============================================================
# [P2-B2 修复 2026-07-26]
# 1. 使用 SAFE_BASELINE (而非 ORIGINAL_DIM_SCOPES) + exclude [339]
#    避免 ORIGINAL_DIM_SCOPES 含 wildcard 时触发自冲突 409.
# 2. 移除 "409 当 PASS 跳过" 逻辑: 409 = 预清理失败 = FAIL.
# 3. 实际执行 C2/C3/C4 验证 (不再因 409 跳过).
# ============================================================
print("\n" + "=" * 80)
print("Part C: 配置变更触发自动重推导 (stale → derive → clear)")
print("=" * 80)

print(f"\n[C1] admin POST /api/v1/roles/{ROLE_ID}/dimension-scopes (添加 exclude [339])")
# 构造新的 dim_scope: include [339] + exclude [339] (Cartesian + exclude 共存)
# 注: 同一 role 内 include + exclude 不触发自冲突 (仅 wildcard + exclude 才冲突)
# IntentScopeAdapter 应判定 exclude 优先 (Deny 优先), 即 339 不可见.
new_scopes = [
    {'dimension_code': 'sub_domain', 'dimension_values': [339],
     'inherit_children': True, 'scope_mode': 'include'},
    {'dimension_code': 'sub_domain', 'dimension_values': [339],
     'inherit_children': True, 'scope_mode': 'exclude'},
]

status, resp = call(admin, 'POST',
    f'/api/v1/roles/{ROLE_ID}/dimension-scopes', body=new_scopes)
print(f"  POST status: {status}, response: {str(resp)[:200]}")
# [P2-B2 修复] 409 = 预清理失败, 记为 FAIL (不再跳过)
c1_ok = (status == 200)
if status == 409:
    print(f"  [FAIL] 409 conflict - 预清理未生效, 检查 A1 是否成功")
    print(f"  conflict_user_ids: {resp.get('conflict_user_ids') if isinstance(resp, dict) else None}")
results.append(('C1: 配置变更 (添加 exclude) 触发 derivation', c1_ok))

if c1_ok:
    # C2: 验证 wyonghui4 立即看不到 339 (Intent 已更新)
    print("\n[C2] wyonghui4 GET sub_domain list (期望不含 339, 自动重推导生效)")
    status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
    items = get_data_items(resp)
    sub_ids_after_exclude = [item.get('id') for item in items]
    has_339_after_exclude = 339 in sub_ids_after_exclude
    print(f"  wyonghui4 visible sub_domains count: {len(sub_ids_after_exclude)}")
    print(f"  包含 339 (期望 False, 自动重推导生效): {has_339_after_exclude}")
    results.append(('C2: 配置变更后 Intent 立即生效 (不含 339)',
                    not has_339_after_exclude))

    # C3: 恢复 dim_scope 到 SAFE_BASELINE (触发新一轮 derive)
    print(f"\n[C3] admin 恢复 role {ROLE_ID} 到 SAFE_BASELINE (触发新一轮 derive)")
    restore_status = call(admin, 'POST',
        f'/api/v1/roles/{ROLE_ID}/dimension-scopes',
        body=SAFE_BASELINES[ROLE_ID])[0]
    print(f"  Restore status: {restore_status}")
    results.append(('C3: 恢复 dim_scope (触发新一轮 derive)', restore_status == 200))

    # C4: 验证 wyonghui4 再次看到 339 (Intent 已恢复)
    print("\n[C4] wyonghui4 GET sub_domain list (期望恢复含 339)")
    status, resp = call(wyonghui4, 'GET', '/api/v2/bo/sub_domain?pageSize=200')
    items = get_data_items(resp)
    sub_ids_after_restore = [item.get('id') for item in items]
    has_339_after_restore = 339 in sub_ids_after_restore
    print(f"  wyonghui4 visible sub_domains count: {len(sub_ids_after_restore)}")
    print(f"  包含 339 (期望 True, 恢复后 Intent 已更新): {has_339_after_restore}")
    results.append(('C4: 恢复后 Intent 立即恢复 (含 339)', has_339_after_restore))
else:
    # C1 失败时, C2/C3/C4 也记为 FAIL (避免假 PASS)
    for label in ['C2: 配置变更后 Intent 立即生效 (不含 339)',
                  'C3: 恢复 dim_scope (触发新一轮 derive)',
                  'C4: 恢复后 Intent 立即恢复 (含 339)']:
        results.append((label, False))


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
