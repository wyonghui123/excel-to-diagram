# -*- coding: utf-8 -*-
"""e2e 测试脚本: Spec 08 维度范围通配符和 Exclude (wyonghui 系列用户)"""
import json
import sys
import os

import urllib.request
import urllib.error
import http.cookiejar


BASE_URL = os.environ.get('BASE_URL', 'http://localhost:3011')


def make_session(username='admin'):
    """创建带 cookie 的 session 并登录"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    url = f"{BASE_URL}/api/v1/auth/dev-login?username={username}"
    try:
        opener.open(url, timeout=10)
    except Exception as e:
        raise RuntimeError(f"Login failed: {e}")
    return opener


def call(opener, method, path, body=None, expect_status=None):
    """调用 API"""
    url = BASE_URL + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        resp = opener.open(req, timeout=15)
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
        print(f"  [FAIL] Expected status {expect_status}, got {status}")
        print(f"  Response: {json.dumps(parsed, ensure_ascii=False, indent=2)[:500]}")
        return status, parsed, False
    return status, parsed, True


# ============ 测试场景 ============
results = []

print("=" * 70)
print("Spec 08 e2e 测试: 维度范围通配符 (*) 与 Exclude 黑名单")
print("=" * 70)

# 登录
print("\n[Setup] Login admin")
admin = make_session('admin')
print("  [OK] Admin logged in")

# ========== 场景 1: admin 配置 wildcard ==========
print("\n[Scenario 1] admin 配置 wildcard (role 11821 product)")
status, resp, ok = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                        body=[{"dimension_code": "product", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
status, resp, ok = call(admin, 'GET', '/api/v1/roles/11821/dimension-scopes')
data = resp.get('data', [])
hint_ok = data and data[0].get('_ui_hint', {}).get('is_wildcard') is True
val_ok = data and data[0].get('dimension_values') == [{'id': '*', 'name': '全维度可见', 'code': '*'}]
print(f"  GET _ui_hint.is_wildcard={hint_ok}, dimension_values={val_ok}")
results.append(('Scenario 1: wildcard 配置', ok and hint_ok and val_ok))

# ========== 场景 2: admin 配置 exclude ==========
print("\n[Scenario 2] admin 配置 exclude (role 12009 sub_domain)")
# 先重置 role 11993 为 include (清掉 scenario 1 留下的 wildcard 状态)
status, _, _ = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2201, 2207, 2204, 1223, 2209, 2200],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                              "inherit_children": True, "scope_mode": "exclude"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
status, resp, ok = call(admin, 'GET', '/api/v1/roles/12009/dimension-scopes')
data = resp.get('data', [])
mode_ok = data and data[0].get('scope_mode') == 'exclude'
hint_ok = data and data[0].get('_ui_hint', {}).get('is_exclude') is True
print(f"  GET scope_mode={data[0].get('scope_mode') if data else 'N/A'}, _ui_hint.is_exclude={hint_ok}")
results.append(('Scenario 2: exclude 配置', ok and mode_ok and hint_ok))

# ========== 场景 3: 非 admin 尝试配置 wildcard ==========
print("\n[Scenario 3] 非 admin 用户 (wyonghui) 配置 wildcard -> 403")
wy = make_session('wyonghui')
status, resp, ok = call(wy, 'POST', '/api/v1/roles/5970/dimension-scopes',
                        body=[{"dimension_code": "product", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=403)
print(f"  POST status={status}, error_code={resp.get('error_code')}")
print(f"  message: {resp.get('message', '')[:80]}")
# 注: 403 可能来自 admin_required 装饰器 (前端提示"需要管理员权限")
# 或来自 FR-010 的 DIM_SCOPE_PERMISSION_DENIED, 两者都达到"拒绝非 admin"目标
denied = status == 403
results.append(('Scenario 3: 非 admin 拒绝 (403)', denied))

# ========== 场景 4: 同一角色 wildcard + exclude 冲突 ==========
print("\n[Scenario 4] 同一角色内 wildcard + exclude 冲突")
# 先重置 role 11821 为 include, 然后单独 POST wildcard, 然后冲突测试
status, _, _ = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2200],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                        body=[{"dimension_code": "product", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                        body=[{"dimension_code": "product", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"},
                              {"dimension_code": "domain", "dimension_values": [2200],
                              "inherit_children": True, "scope_mode": "exclude"}],
                        expect_status=409)
print(f"  POST status={status}, error_code={resp.get('error_code')}")
print(f"  message: {resp.get('message', '')[:80]}")
results.append(('Scenario 4: 同一角色 wildcard+exclude 冲突', ok and resp.get('error_code') == 'DIM_SCOPE_CONFLICT'))

# ========== 场景 5: 多角色 wildcard + exclude 冲突 (wyonghui2) ==========
print("\n[Scenario 5] 多角色 wildcard + exclude 冲突 (wyonghui2=10007)")
# 前置: role 11821 已 wildcard (scenario 4 保留), role 11993 重置为 include
status, _, _ = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2201, 2207, 2204, 1223, 2209, 2200],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# role 11993 是 wyonghui2 持有, 给它配 exclude -> 冲突 (11821 是 wildcard)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                        body=[{"dimension_code": "domain", "dimension_values": [2201],
                              "inherit_children": True, "scope_mode": "exclude"}],
                        expect_status=409)
print(f"  POST status={status}, error_code={resp.get('error_code')}")
print(f"  conflict_user_ids={resp.get('conflict_user_ids')}")
print(f"  message: {resp.get('message', '')[:100]}")
results.append(('Scenario 5: 多角色 wildcard+exclude 冲突 (wyonghui2)',
                ok and resp.get('error_code') == 'DIM_SCOPE_CONFLICT'
                and 10007 in (resp.get('conflict_user_ids') or [])))

# ========== 场景 6: 多角色 exclude + wildcard 反向冲突 (wyonghui3) ==========
print("\n[Scenario 6] 多角色 exclude + wildcard 反向冲突 (wyonghui3=10008)")
# 前置: role 12009 已 exclude (scenario 2 保留), role 12010 是 wyonghui3 持有
# 给 12010 配 wildcard -> 冲突 (wyonghui3 同时持有 12009 exclude + 12010 wildcard)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12010/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=409)
print(f"  POST status={status}, error_code={resp.get('error_code')}")
print(f"  conflict_user_ids={resp.get('conflict_user_ids')}")
print(f"  message: {resp.get('message', '')[:100]}")
results.append(('Scenario 6: 多角色 exclude+wildcard 反向冲突 (wyonghui3)',
                ok and resp.get('error_code') == 'DIM_SCOPE_CONFLICT'
                and 10008 in (resp.get('conflict_user_ids') or [])))

# ========== 场景 7: feature flag endpoint ==========
print("\n[Scenario 7] GET /api/v2/_feature_flags")
status, resp, ok = call(admin, 'GET', '/api/v2/_feature_flags', expect_status=200)
data = resp.get('data', {})
print(f"  status={status}, wildcard_enabled={data.get('dim_scope_wildcard_enabled')}, exclude_enabled={data.get('dim_scope_exclude_enabled')}")
results.append(('Scenario 7: feature flag endpoint',
                ok and 'dim_scope_wildcard_enabled' in data and 'dim_scope_exclude_enabled' in data))

# ========== 场景 8: diagnostics dim_scope stats ==========
print("\n[Scenario 8] GET /api/v2/action/_diagnostics -> dim_scope 统计")
status, resp, ok = call(admin, 'GET', '/api/v2/action/_diagnostics', expect_status=200)
ds = resp.get('data', {}).get('dim_scope', {})
print(f"  status={status}, wildcard_count={ds.get('wildcard_count')}, exclude_count={ds.get('exclude_count')}")
print(f"  wildcard_roles count={len(ds.get('wildcard_roles', []))}")
print(f"  exclude_roles count={len(ds.get('exclude_roles', []))}")
print(f"  conflict_users={ds.get('conflict_users')}")
print(f"  feature_flags={ds.get('feature_flags')}")
results.append(('Scenario 8: diagnostics dim_scope 统计',
                ok and 'wildcard_count' in ds and 'exclude_count' in ds))

# ========== 场景 9: 同一用户多角色都是 wildcard (不冲突) ==========
print("\n[Scenario 9] 同一用户多角色都是 wildcard (不冲突)")
# 先重置所有相关 role 为非 wildcard/exclude 状态
# role 12009 重置 include (清掉 scenario 2 留下的 exclude)
status, _, _ = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# role 12010 重置 include (清掉 scenario 6 残留)
status, _, _ = call(admin, 'POST', '/api/v1/roles/12010/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": [299],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# role 11821 设 wildcard
status, _, _ = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                    body=[{"dimension_code": "product", "dimension_values": ["*"],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# role 11993 重置为 include (wyonghui2 持有, 不与 11821 wildcard 冲突)
status, _, _ = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2201],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# 给 11993 也配 wildcard (同类型不冲突, 都给 wyonghui2 是 wildcard + wildcard)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                        body=[{"dimension_code": "domain", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('Scenario 9: 多角色都是 wildcard 不冲突', ok))

# ========== 场景 10: 同一用户多角色 include + wildcard 不冲突 ==========
print("\n[Scenario 10] 同一用户多角色 include + wildcard 不冲突")
# 前置: role 11821 已是 wildcard (scenario 9 设置), role 11993 已是 wildcard
# 给 11993 配 include (wildcard + include 不冲突, 因为 include 是 widening)
status, resp, ok = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                        body=[{"dimension_code": "domain", "dimension_values": [2201, 2207],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('Scenario 10: 多角色 include + wildcard 不冲突', ok))

# ========== 场景 11: wyonghui4 单角色非 admin 拒绝 (FR-010 第二样本) ==========
print("\n[Scenario 11] wyonghui4 (10009) 配 wildcard -> 403 (单角色非 admin)")
wy4 = make_session('wyonghui4')
status, resp, ok = call(wy4, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=403)
print(f"  POST status={status}, message: {resp.get('message', '')[:60]}")
results.append(('Scenario 11: 单角色非 admin 拒绝', status == 403))

# ========== 场景 12: 单角色 exclude 不与多用户冲突 (wyonghui4 单角色) ==========
print("\n[Scenario 12] 给 wyonghui4 的 12009 配 exclude (单角色, 无冲突)")
# 重置: 11821/11993/12010 全部 include, 12009 重置 include
status, _, _ = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2200],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
status, _, _ = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2201, 2207, 2204, 1223, 2209, 2200],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
status, _, _ = call(admin, 'POST', '/api/v1/roles/12010/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": [299],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# wyonghui4 (10009) 只持有 12009, 不与其他多角色用户冲突
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                              "inherit_children": True, "scope_mode": "exclude"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
results.append(('Scenario 12: 单角色 exclude 不冲突', ok))

# ========== 场景 13: DEMO 空配置用户访问 GET ==========
print("\n[Scenario 13] DEMO (10010) GET role 12020 (空配置路径)")
demo = make_session('DEMO')
status, resp, ok = call(demo, 'GET', '/api/v1/roles/12020/dimension-scopes', expect_status=200)
data = resp.get('data', [])
print(f"  GET status={status}, data count={len(data) if data else 0}, _ui_hint={data[0].get('_ui_hint') if data else 'N/A'}")
results.append(('Scenario 13: 空配置用户 GET', ok and isinstance(data, list)))

# ========== 场景 14: admin 给 DEMO 角色配 wildcard ==========
print("\n[Scenario 14] admin 给 DEMO role 12020 配 wildcard")
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12020/dimension-scopes',
                        body=[{"dimension_code": "product", "dimension_values": ["*"],
                              "inherit_children": True, "scope_mode": "include"}],
                        expect_status=200)
print(f"  POST status={status}, success={resp.get('success')}")
status, resp, ok = call(admin, 'GET', '/api/v1/roles/12020/dimension-scopes', expect_status=200)
data = resp.get('data', [])
hint_ok = data and data[0].get('_ui_hint', {}).get('is_wildcard') is True
print(f"  GET _ui_hint.is_wildcard={hint_ok}")
results.append(('Scenario 14: DEMO 角色 wildcard', ok and hint_ok))

# ========== 场景 15: 跨用户影响传播 (wyonghui3 + wyonghui4) ==========
print("\n[Scenario 15] 跨用户冲突传播 (wyonghui3=10008 持有 12009, wyonghui4=10009 持有 12009)")
# 重置 12009 为 include (清掉 scenario 12 留下的 exclude)
status, _, _ = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# 给 12010 配 wildcard (wyonghui3 持有 12010)
status, _, _ = call(admin, 'POST', '/api/v1/roles/12010/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": ["*"],
                          "inherit_children": True, "scope_mode": "include"}],
                    expect_status=200)
# 给 12009 配 exclude -> wyonghui3 (持有 12010 wildcard + 12009) 冲突 + wyonghui4 (持有 12009) 不冲突
# 但 spec 检测同一用户维度, 应只报告 wyonghui3
status, resp, ok = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                        body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                              "inherit_children": True, "scope_mode": "exclude"}],
                        expect_status=409)
print(f"  POST status={status}, error_code={resp.get('error_code')}")
print(f"  conflict_user_ids={resp.get('conflict_user_ids')} (期望: 含 10008, 不含 10009)")
conflict_users = resp.get('conflict_user_ids') or []
ok_15 = (resp.get('error_code') == 'DIM_SCOPE_CONFLICT'
         and 10008 in conflict_users and 10009 not in conflict_users)
results.append(('Scenario 15: 跨用户冲突精确识别', ok and ok_15))

# ========== 清理: 重置角色为原始状态 ==========
print("\n[Cleanup] 重置角色为原始状态")
# role 11821: domain=[2200] include
status, _, _ = call(admin, 'POST', '/api/v1/roles/11821/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2200],
                          "inherit_children": True, "scope_mode": "include"}])
# role 12009: sub_domain=[339] include
status, _, _ = call(admin, 'POST', '/api/v1/roles/12009/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": [339],
                          "inherit_children": True, "scope_mode": "include"}])
# role 11993: domain=[2201,2207,2204,1223,2209,2200] include
status, _, _ = call(admin, 'POST', '/api/v1/roles/11993/dimension-scopes',
                    body=[{"dimension_code": "domain", "dimension_values": [2201, 2207, 2204, 1223, 2209, 2200],
                          "inherit_children": True, "scope_mode": "include"}])
# role 12010: sub_domain=[299] include
status, _, _ = call(admin, 'POST', '/api/v1/roles/12010/dimension-scopes',
                    body=[{"dimension_code": "sub_domain", "dimension_values": [299],
                          "inherit_children": True, "scope_mode": "include"}])
# role 12020 (DEMO): 清空配置 (scenario 14 配了 wildcard)
status, _, _ = call(admin, 'POST', '/api/v1/roles/12020/dimension-scopes',
                    body=[])
print("  [OK] Roles reset")

# ========== 汇总 ==========
print("\n" + "=" * 70)
print("测试结果汇总")
print("=" * 70)
passed = sum(1 for _, ok in results if ok)
total = len(results)
for name, ok in results:
    status_str = "[PASS]" if ok else "[FAIL]"
    print(f"  {status_str} {name}")
print(f"\n总计: {passed}/{total} 通过")

sys.exit(0 if passed == total else 1)
