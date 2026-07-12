# 角色删除级联 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复角色删除报错"无法删除：角色权限 的 角色ID 引用了此记录（N条）"——通过 yaml associations.cascade_delete 静默级联 + is_system 保护。

**Architecture:**
- 在 `meta/schemas/role.yaml` 的 6 个 associations + 1 个 reverse 加 `cascade_delete: true`
- 在 `meta/core/action_executor.py` 的 `_do_delete` 前加 `is_system` / `code == 'super_admin'` 保护
- 更新 `deletion_policy.cascade_delete` 列表与 associations 一致（虽然 Python 检查只读 associations，但保留字段同步）
- 集成测试 + commit

**Tech Stack:** Python 3.x, SQLite, pytest, yaml

---

## File Structure

| 文件 | 作用 |
|------|------|
| `meta/schemas/role.yaml` | 修改：7 个 associations 加 cascade_delete；1 个 deletion_policy list 扩 |
| `meta/core/action_executor.py` | 修改：`_do_delete` 前加 `is_system`/`super_admin` 保护 |
| `meta/tests/test_role_delete_cascade.py` | 新建：集成测试（创建角色→授权→级联删除→断言子表清零） |
| `meta/tests/test_role_delete_system_protected.py` | 新建：测试系统角色拒绝删除 |

---

## Task 1: 集成测试 - 静默级联

**Files:**
- Create: `meta/tests/test_role_delete_cascade.py`

- [ ] **Step 1: 写失败测试**

```python
"""集成测试: 删除角色时自动级联清理子表.

[Bug-V061 2026-07-12]
"""
import pytest
from tests.helpers.db_helper import DbHelper, ApiHelper, AuthHelper
from tests.helpers.role_helper import RoleTestHelper


@pytest.fixture
def setup_test_role(admin_token, base_url, db):
    """创建一个测试角色并分配权限/菜单/数据范围."""
    helper = RoleTestHelper(base_url, admin_token, db)
    role_id = helper.create_test_role(f'cascade_test_{int(time.time())}')

    # 分配: role_permissions + role_menu_permissions + permission_rules
    helper.grant_permission(role_id, 'product:read')
    helper.grant_permission(role_id, 'product:write')
    helper.attach_menu(role_id, 'product-management')
    helper.add_condition_rule(role_id, "product_id = 1")

    yield role_id, helper

    # cleanup（如果还没删）
    helper.delete_role(role_id, ignore_errors=True)


def test_role_delete_cascades_child_tables(setup_test_role):
    """删除角色 → role_permissions/role_menu_permissions/permission_rules 全清."""
    role_id, helper = setup_test_role

    # 1. 验证子表有记录
    assert helper.count('role_permissions', role_id) >= 2
    assert helper.count('role_menu_permissions', role_id) >= 1
    assert helper.count('permission_rules', role_id) >= 1

    # 2. 删除角色 - 应成功（静默级联）
    result = helper.delete_role(role_id)
    assert result['success'] is True
    assert result.get('data', {}).get('cascade') is True  # 显示级联了

    # 3. 子表记录全为 0
    assert helper.count('role_permissions', role_id) == 0
    assert helper.count('role_menu_permissions', role_id) == 0
    assert helper.count('permission_rules', role_id) == 0
```

- [ ] **Step 2: 创建 RoleTestHelper (test fixture)**

```python
# meta/tests/helpers/role_helper.py
"""[NEW 2026-07-12] 测试用: 创建角色 + 授权 + 级联删除 helper."""
import time
import requests


class RoleTestHelper:
    def __init__(self, base_url, token, db):
        self.base_url = base_url
        self.token = token
        self.db = db  # sqlite3 connection

    def _headers(self):
        return {'Authorization': f'Bearer {self.token}'}

    def create_test_role(self, code):
        resp = requests.post(f'{self.base_url}/api/v1/roles',
                             json={'code': code, 'name': 'Cascade Test',
                                   'is_active': 1, 'is_system': 0},
                             headers=self._headers())
        data = resp.json()
        assert data['success'], f'create_test_role failed: {data}'
        return data['data']['id']

    def grant_permission(self, role_id, perm_code):
        resp = requests.post(f'{self.base_url}/api/v1/roles/{role_id}/permissions',
                             json={'permissions': [perm_code]},
                             headers=self._headers())
        return resp.json()

    def attach_menu(self, role_id, menu_code):
        resp = requests.post(f'{self.base_url}/api/v1/roles/{role_id}/menus',
                             json={'menu_codes': [menu_code]},
                             headers=self._headers())
        return resp.json()

    def add_condition_rule(self, role_id, condition):
        # 直接 SQL 写 permission_rules
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO permission_rules (role_id, resource_type, condition, permission_level, is_enabled, inherit_to_children, created_at) VALUES (?, 'product', ?, 'read', 1, 1, datetime('now'))",
            (role_id, condition))
        self.db.commit()

    def count(self, table, role_id):
        cur = self.db.cursor()
        cur.execute(f'SELECT COUNT(*) FROM {table} WHERE role_id = ?', (role_id,))
        return cur.fetchone()[0]

    def delete_role(self, role_id, ignore_errors=False):
        resp = requests.delete(f'{self.base_url}/api/v1/roles/{role_id}',
                               headers=self._headers())
        data = resp.json()
        if not data['success'] and not ignore_errors:
            pytest.fail(f'delete_role failed: {data}')
        return data
```

- [ ] **Step 3: 运行测试 → 确认它失败**

Run: `pytest meta/tests/test_role_delete_cascade.py -v`
Expected: FAIL "role_menus → role_menu_permissions table not found" 或者 "28 条错误"

- [ ] **Step 4: 不写 implementation，测试先失败**

---

## Task 2: yaml 改动 - 6 个 associations + 1 个 reverse 加 cascade_delete

**Files:**
- Modify: `meta/schemas/role.yaml`

- [ ] **Step 1: 看 role.yaml 的 associations 节现有 6 个 association**

跑: `grep -n "associations:" meta/schemas/role.yaml`
预期: 第 191 行附近

- [ ] **Step 2: 加 cascade_delete: true 到 6 个 association + 1 个 reverse**

修改 `meta/schemas/role.yaml` 的 `associations:` 节:

```yaml
associations:
  # 原 1: 角色 ↔ 权限 (M:N, role_permissions)
  permissions:
    name: permissions
    label: 权限
    plural_label: 权限列表
    type: many_to_many
    through: role_permissions
    source_key: role_id
    target_entity: permission
    target_key: permission_id
    cascade_delete: true              # [FIX BUG-V061 2026-07-12] ← 新增
    description: 角色权限关联
    # ... (保留 display/actions 等其他字段不变)

  # 原 2 (新增补): 角色 ↔ 用户 (M:N, user_roles)
  users:
    name: users
    label: 用户
    plural_label: 用户列表
    type: many_to_many
    through: user_roles
    source_key: role_id
    target_entity: user
    target_key: user_id
    cascade_delete: true              # [FIX BUG-V061] ← 新增
    description: 持有此角色的用户
    display:
      label: 用户
      target_display_field: username
      columns:
        - id: username
          label: 用户名

  # 原 3 (新增补): 角色 ↔ 菜单 (M:N, role_menu_permissions)
  menus:
    name: menus
    label: 菜单
    plural_label: 菜单列表
    type: many_to_many
    through: role_menu_permissions    # [FIX BUG-V061] 真实表名 (不是 role_menus)
    source_key: role_id
    target_entity: menu
    target_key: menu_code
    cascade_delete: true              # ← 新增
    description: 角色可访问的菜单

  # 原 4 (新增补): 角色 ↔ 条件规则 (1:N)
  data_permission_rules:
    name: data_permission_rules
    label: 条件权限规则
    type: one_to_many
    target_entity: permission_rule
    target_key: role_id
    cascade_delete: true              # ← 新增
    description: 角色的条件型数据权限规则

  # 原 5 (新增补): 角色 ↔ 角色数据权限 (1:N)
  role_data_permissions:
    name: role_data_permissions
    type: one_to_many
    target_entity: data_permission
    target_key: role_id
    cascade_delete: true              # ← 新增
    description: 角色级数据权限

  # 原 6 (新增补): 角色 ↔ 角色维度范围 (1:N)
  role_dimension_scopes:
    name: role_dimension_scopes
    type: one_to_many
    target_entity: role_dimension_scope
    target_key: role_id
    cascade_delete: true              # ← 新增
    description: 角色的维度管理范围

  # 原 7: assigned_groups (reverse many_to_many, group_roles)
  assigned_groups:
    name: assigned_groups
    label: 用户组
    plural_label: 用户组列表
    target_type: user_group
    type: reverse_many_to_many
    through: group_roles
    source_key: role_id
    target_key: group_id
    cascade_delete: true              # [FIX BUG-V061] DB FK 已有 ON DELETE CASCADE, yaml 也声明
    description: 分配了此角色的用户组
```

- [ ] **Step 3: 同步扩展 deletion_policy.cascade_delete 列表**

修改 `meta/schemas/role.yaml`:

```yaml
deletion_policy:
  cascade_delete:
    - user_roles
    - role_permissions
    - role_menu_permissions          # [FIX BUG-V061] 加 (不是 role_menus)
    - permission_rules               # [FIX BUG-V061] 加 (数据权限条件规则)
    - role_data_permissions          # [FIX BUG-V061] 加
    - role_dimension_scopes          # [FIX BUG-V061] 加
    - group_roles                    # [FIX BUG-V061] 加 (DB FK 已有)
```

- [ ] **Step 4: 加 is_system 字段（保护用）**

修改 `meta/schemas/role.yaml`，fields 区加：

```yaml
  - id: is_system
    name: 系统角色
    type: boolean
    db_column: is_system
    description: 系统内置角色（不可删除）
    default: 0
    semantics:
      meaning: 标记系统内置角色
      immutable_after_create: true
    ui:
      show_in_form: false
      show_in_table: true
```

- [ ] **Step 5: 验证 yaml syntax**

跑: `python -c "import yaml; yaml.safe_load(open('meta/schemas/role.yaml'))"`
预期: 无异常

- [ ] **Step 6: Commit**

```bash
git add meta/schemas/role.yaml
git commit -m "fix(role.yaml): cascade_delete associations + is_system 字段 [BUG-V061]"
```

---

## Task 3: action_executor.py - 加 is_system/super_admin 保护

**Files:**
- Modify: `meta/core/action_executor.py`

- [ ] **Step 1: 找到 _do_delete 内 `_check_reverse_fk_references` 调用前的位置**

跑: `grep -n "_check_reverse_fk_references" meta/core/action_executor.py`
预期: 1993 行附近

- [ ] **Step 2: 在 _do_delete 入口加系统角色保护**

修改 `meta/core/action_executor.py`, 在 `_do_delete` 入口（_check_reverse_fk_references 之前）插入:

```python
        if meta_object.id == 'role':
            # [FIX BUG-V061 2026-07-12] 系统角色保护
            original_role = self._read_original(meta_object, id_value)
            if original_role:
                if original_role.get('is_system'):
                    self._write_delete_blocked_audit(
                        meta_object, id_value, original_role,
                        action_label="DELETE_BLOCKED",
                        error_code="SYSTEM_ROLE_PROTECTED",
                        message=f"系统角色 '{original_role.get('name', id_value)}' 不能删除"
                    )
                    return ActionResult.fail(
                        error="SYSTEM_ROLE_PROTECTED",
                        message=f"系统角色 '{original_role.get('name', id_value)}' 不能删除"
                    )
                if original_role.get('code') == 'super_admin':
                    self._write_delete_blocked_audit(
                        meta_object, id_value, original_role,
                        action_label="DELETE_BLOCKED",
                        error_code="SUPER_ADMIN_PROTECTED",
                        message="Super Admin 角色不能删除"
                    )
                    return ActionResult.fail(
                        error="SUPER_ADMIN_PROTECTED",
                        message="Super Admin 角色不能删除"
                    )
```

- [ ] **Step 3: 测试本地 yaml 加载是否 OK**

跑: `python -c "from meta.core.action_executor import MetaActionExecutor; e = MetaActionExecutor(...); print('import OK')"`
预期: import OK

- [ ] **Step 4: Commit**

```bash
git add meta/core/action_executor.py
git commit -m "fix(action_executor): 加 is_system/super_admin 角色保护 [BUG-V061]"
```

---

## Task 4: 重跑 Task 1 的集成测试 - 应该过

**Files:**
- Modify: `meta/tests/test_role_delete_cascade.py`

- [ ] **Step 1: 运行测试 - 应该过**

跑: `pytest meta/tests/test_role_delete_cascade.py -v`
预期: PASS (yaml 和 python 改动生效)

- [ ] **Step 2: 如果失败 - 调整 yaml 或 python 直到过**

---

## Task 5: 系统角色保护测试

**Files:**
- Create: `meta/tests/test_role_delete_system_protected.py`

- [ ] **Step 1: 写测试**

```python
"""测试: 系统角色 / Super Admin 不能删."""
import pytest
import requests
import time


def test_super_admin_delete_blocked(base_url, admin_token):
    """Super Admin (code='super_admin') 拒绝删除."""
    # 找 super_admin 的 id
    resp = requests.get(f'{base_url}/api/v1/roles', headers={'Authorization': f'Bearer {admin_token}'})
    roles = resp.json()['data']['items']
    super_admin = next((r for r in roles if r.get('code') == 'super_admin'), None)
    if not super_admin:
        pytest.skip("super_admin role not found in test env")

    delete_resp = requests.delete(f'{base_url}/api/v1/roles/{super_admin["id"]}',
                                   headers={'Authorization': f'Bearer {admin_token}'})
    data = delete_resp.json()
    assert data['success'] is False
    assert 'SUPER_ADMIN' in data.get('error', '')


def test_is_system_role_delete_blocked(base_url, admin_token, db):
    """is_system=1 的角色拒绝删除."""
    # 直接 SQL 标记 super_admin 为 is_system=1 (并已经做过)
    # 通用流程: 确保任意 is_system=1 角色拒绝
    cur = db.cursor()
    cur.execute("SELECT id, code, name FROM roles WHERE is_system = 1 LIMIT 1")
    row = cur.fetchone()
    if not row:
        pytest.skip("no is_system=1 role in test env")

    role_id, code, name = row
    resp = requests.delete(f'{base_url}/api/v1/roles/{role_id}',
                           headers={'Authorization': f'Bearer {admin_token}'})
    data = resp.json()
    assert data['success'] is False
    assert 'SYSTEM_ROLE' in data.get('error', '')
```

- [ ] **Step 2: 运行测试 - 应该过**

跑: `pytest meta/tests/test_role_delete_system_protected.py -v`
预期: PASS (super_admin 拒删, is_system=1 拒删)

- [ ] **Step 3: Commit**

```bash
git add meta/tests/
git commit -m "test(role-delete): 系统角色/Super Admin 保护测试 [BUG-V061]"
```

---

## Task 6: 跨服务重启验证

**Files:**
- 验证: 部署流程由打包部署智能体执行

- [ ] **Step 1: 重启本地 meta_server**

跑: 

```bash
# 找 meta_server PID
ps -ef | grep server.py | grep -v grep
# kill
kill -9 <PID>
# 启动
nohup python3 -u server.py > /tmp/server.log 2>&1 &
```

- [ ] **Step 2: 验证 GUI 操作能复现修复后的行为**

- 角色管理 → 创建一个测试角色 (例如 `cascade_test`)
- 分配"产品管理"菜单 + `product:read` 权限
- 添加一条条件规则 `product_id = 1`
- **删除** → 应顺利成功
- 进入数据库/列表 → 验证子表记录全为 0

- [ ] **Step 3: 验证 Super Admin 不能删**

- 尝试删除 Super Admin → 应报错"SUPER_ADMIN_PROTECTED"

---

## Self-Review

### 1. Spec coverage

| Spec 项 | Task |
|---------|------|
| 修改 6 个 association + 1 reverse | Task 2 |
| deletion_policy.cascade_delete 同步 | Task 2 |
| is_system 字段 | Task 2 |
| _do_delete 加 is_system/super_admin 保护 | Task 3 |
| 集成测试 | Task 1, 4 |
| 系统角色测试 | Task 5 |
| 跨服务重启验证 | Task 6 |

### 2. Placeholder scan
- 无 "TBD"/"fill in"
- 错误代码 SUPER_ADMIN_PROTECTED/SYSTEM_ROLE_PROTECTED 已具体定义
- yaml 字段名与 [action_executor.py:1131](file:///d:/filework/release-prep-worktree/meta/core/action_executor.py#L1127-L1136) 期待的 `cascade_delete` 对应

### 3. Type consistency

| 名 | 定义处 | 引用处 |
|---|-------|-------|
| `is_system` | role.yaml fields | action_executor.py `original_role.get('is_system')` |
| `code == 'super_admin'` | role.yaml seed | action_executor.py 直接对比 |
| `cascade_delete: true` | yaml | action_executor.py Python 解析 `rel.get('cascade_delete', False)` |

一致 ✓
