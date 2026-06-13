"""
硬编码 ID 修复示例 (Phase 2)
==============================

按 ID 类型 (fake_id / url_id / invalid_id / 实际硬编码) 给出修复模板。
供 Agent 在 Phase 2 修复 30 个高危硬编码 ID 时参考。

TBD-6 采纳: high 自动 fix, 其他只检测
"""

# ============================================================
# 1. fake_id = 999999999 (sentinel) - 3 处
# ============================================================

# [X] 反例: test_audit_parent_object_and_extract.py:293
"""
fake_id = 999999999
resp = requests.get(f'{BASE_URL}/api/v2/audit/{fake_id}', headers=auth_headers)
assert resp.status_code == 404
"""

# [OK] 正例 1: 用 unique_id() 生成动态 sentinel
"""
from meta.tests.factories import unique_id

fake_id = unique_id()  # 每次跑都不同
resp = requests.get(f'{BASE_URL}/api/v2/audit/{fake_id}', headers=auth_headers)
assert resp.status_code == 404
"""

# [OK] 正例 2: 用 fixture 追踪清理
"""
def test_audit_with_fake_id(test_audit_logs):
    fake_id = test_audit_logs()['id'] + 999999999  # 不存在的 ID
    resp = requests.get(f'{BASE_URL}/api/v2/audit/{fake_id}', headers=auth_headers)
    assert resp.status_code == 404
"""


# ============================================================
# 2. url_id = 999999999 (URL 中的大数) - 25 处
# ============================================================

# [X] 反例: test_relationship_crud.py:253
"""
response = requests.delete(f'{BASE_URL}/api/v2/bo/relationship/999999999', headers=auth_headers)
"""

# [OK] 正例: 用 unique_id() 或 fixture
"""
def test_delete_nonexistent_relationship(test_relationships):
    fake_id = unique_id()  # 动态 sentinel
    response = requests.delete(
        f'{BASE_URL}/api/v2/bo/relationship/{fake_id}',
        headers=auth_headers
    )
    assert response.status_code == 404
"""


# ============================================================
# 3. invalid_id = 999999999 - 2 处
# ============================================================

# [X] 反例: test_transaction_consistency.py:264
"""
invalid_id = 999999999
resp = requests.get(f'{BASE_URL}/api/v2/version/{invalid_id}')
assert resp.status_code == 404
"""

# [OK] 正例:
"""
def test_get_invalid_version(test_versions):
    invalid_id = unique_id()  # 动态
    resp = requests.get(f'{BASE_URL}/api/v2/version/{invalid_id}')
    assert resp.status_code == 404
"""


# ============================================================
# 4. 真实存在的硬编码 ID (10+ 处) - 必须替换为 factory.create()
# ============================================================

# [X] 反例: 硬编码真实 user_id
"""
def test_user_update():
    user_id = 1456  # 假设存在
    resp = requests.put(f'/api/v2/user/{user_id}', json={...})
    assert resp.status_code == 200
"""

# [OK] 正例: 用 test_users fixture
"""
def test_user_update(test_users):
    user = test_users()  # 创建并自动清理
    resp = requests.put(f'/api/v2/user/{user["id"]}', json={...})
    assert resp.status_code == 200
"""


# ============================================================
# 通用修复步骤
# ============================================================

GENERIC_FIX_STEPS = """
1. 检测: 运行 `python scripts/migrate_hardcoded_ids.py --severity high --report`
2. 定位: 查看 report 中的 file/line/id/context
3. 替换:
   - fake_id / invalid_id → unique_id() (动态 sentinel)
   - url 中的 ID → f-string + fixture.create()['id'] 或 unique_id()
   - 实际业务 ID → test_users() / test_roles() / test_bos() 等 fixture
4. 验证: `python d:\\filework\\test.py --single <test_id>`
5. 提交: `git commit -m "fix: replace hardcoded id {old_id} with {fixture}"`
"""


# ============================================================
# 30 个高危硬编码 ID 修复列表
# ============================================================

TOP_30_FIX_LIST = """
# Phase 2 W4 D1-3 修复任务 (Agent D)

## 文件级任务
| # | 文件 | 处数 | 修复方式 |
|---|------|------|---------|
| 1 | test_bo_api.py | 10 | unique_id() + test_bos |
| 2 | test_notification_api.py | 3 | unique_id() + test_subscriptions |
| 3 | test_manage_api.py | 2 | unique_id() + test_users |
| 4 | test_role_menu_dim_api.py | 2 | unique_id() + test_roles |
| 5 | test_bo_api_granular.py | 2 | unique_id() + test_bos |
| 6 | test_audit_parent_object_and_extract.py | 1 | unique_id() |
| 7 | test_relationship_crud.py | 1 | unique_id() |
| 8 | test_transaction_consistency.py | 1 | unique_id() |
| 9 | test_annotation_api.py | 1 | unique_id() |
| 10 | test_annotation_routes_api.py | 1 | unique_id() |
| 11 | test_audit_api_endpoints.py | 1 | unique_id() |
| 12 | test_overlap_api.py | 1 | unique_id() |
| 13 | api/test_extended_apis.py | 1 | unique_id() |
| 14 | _consolidated/test_p1_api_domains.py | 1 | unique_id() |
| 15 | test_action_api.py | 1 | unique_id() |
| 16 | test_auth_api_optimized.py | 1 | unique_id() |

## 修复模板 (4 种)

### 模板 A: fake_id sentinel
```python
# 改前
fake_id = 999999999

# 改后
from meta.tests.factories import unique_id
fake_id = unique_id()
```

### 模板 B: URL 中的大数
```python
# 改前
resp = api_client.get(f'/api/v2/bo/user/9999999', headers=admin_headers)

# 改后
fake_id = unique_id()
resp = api_client.get(f'/api/v2/bo/user/{fake_id}', headers=admin_headers)
```

### 模板 C: 实际业务 ID (需 factory)
```python
# 改前
def test_x():
    user_id = 1456
    resp = requests.put(f'/api/v2/user/{user_id}', json={...})

# 改后
def test_x(test_users):
    user = test_users()
    resp = requests.put(f'/api/v2/user/{user["id"]}', json={...})
```

### 模板 D: JSON 中的 ID
```python
# 改前
data = {'id': 99999, 'name': 'test'}

# 改后
data = {'id': unique_id(), 'name': 'test'}
```
"""


if __name__ == '__main__':
    print(TOP_30_FIX_LIST)
    print()
    print(GENERIC_FIX_STEPS)
