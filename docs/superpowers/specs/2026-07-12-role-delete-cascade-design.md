# SPEC: 角色级联删除 (Role Delete Cascade Fix)

> 日期: 2026-07-12
> 状态: Draft → 待用户审阅
> 触发问题: 角色删除报错"无法删除：角色权限 的 角色ID 引用了此记录（28条）"
> 修复策略: **静默级联**（在 yaml associations.relations[].cascade_delete 声明） + 系统角色保护

---

## TL;DR

| 项目 | 内容 |
|------|------|
| **Bug** | 删角色遇 28+ 条 FK 引用就拒绝，无法静默清理 |
| **根因** | `role.yaml` 的 `associations` 没声明 `cascade_delete: true`，导致 `_check_reverse_fk_references` 走限制分支 |
| **修复** | 6 个 yaml 字段 + `is_system` 保护 |
| **影响面** | 仅 role.yaml（user_group.yaml 不动）|
| **副作用** | `deletion_policy.cascade_delete` 字段保留但与 associations.cascade_delete 不冲突（前者是历史 list, 后者是 action_executor 真查）|

---

## 一、问题描述

### 1.1 用户场景

```
1. 超级管理员登录
2. 角色管理 → 选 `test_role`（已分配 N 个权限给业务对象）
3. 点删除
4. ❌ 提示："无法删除：角色权限 的 角色ID 引用了此记录（28条）"
```

### 1.2 报错链路（已定位）

1. 用户点删除 → 前端 `/api/v1/roles/{id}` DELETE
2. 后端 `MetaActionExecutor.execute_action("crud_delete")`
3. 走 `_do_delete` ([action_executor.py:2036](file:///d:/filework/worktrees/release-prep/meta/core/action_executor.py#L2036-L2050))
4. **先调 `_check_reverse_fk_references`** ([action_executor.py:1993](file:///d:/filework/worktrees/release-prep/meta/core/action_executor.py#L1993))
5. 遍历所有其他实体的字段，找引用此角色 (`target_object == 'role'`)
6. **检查 `other_obj.relations[].cascade_delete == True`** ([action_executor.py:1131](file:///d:/filework/worktrees/release-prep/meta/core/action_executor.py#L1127-L1136))
7. 当前 role.yaml 的 relations = `[]`（空数组）→ cascade_delete 永远 False
8. → COUNT(*) > 0 → 报错（[validation_messages.py:59](file:///d:/filework/worktrees/release-prep/meta/core/validation_messages.py#L59)）

### 1.3 实际 DB 结构（本地查证）

引用 `roles.id` 的子表：

| 子表 | FK 严格模式 | 总记录数 |
|------|:--------:|:-----:|
| `user_roles` | ❌ 无 | 2 |
| `role_permissions` | ❌ 无 | 189 |
| `role_menu_permissions`（不是 `role_menus`） | ❌ 无 | 83 |
| `role_data_permissions` | ❌ 无 | 0 |
| `role_dimension_scopes` | ❌ 无 | 14 |
| `permission_rules` | ❌ 无 | 350 |
| `group_roles` | ✅ `ON DELETE CASCADE` 已设 | 31 |

> 注: `role_menus` 是 yaml SQL 里写错的名字，实际 DB 表叫 `role_menu_permissions`

---

## 二、修复方案

### 2.1 yaml 改动（role.yaml）

在 `associations:` 节（已存在 6 个引用 role 的关联 + 1 个 reverse）每条加 `cascade_delete: true`：

```yaml
associations:
  # 角色 ↔ 用户 (M:N, 通过 user_roles)
  users:
    name: users
    type: many_to_many
    through: user_roles
    source_key: role_id
    target_entity: user
    target_key: user_id
    cascade_delete: true           # ← 新增
    description: 用户↔角色关联

  # 角色 ↔ 权限 (M:N, 通过 role_permissions) - 已存在 permissions association
  permissions:
    cascade_delete: true           # ← 新增

  # 角色 ↔ 菜单 (M:N, 通过 role_menu_permissions)
  menus:
    name: menus
    type: many_to_many
    through: role_menu_permissions   # 用真实表名，不是 role_menus
    source_key: role_id
    target_entity: menu
    target_key: menu_code
    cascade_delete: true           # ← 新增
    description: 角色菜单权限关联

  # 角色 ↔ 数据权限条件规则 (1:N)
  data_permission_rules:
    name: data_permission_rules
    type: one_to_many
    target_entity: permission_rule
    target_key: role_id
    cascade_delete: true           # ← 新增

  # 角色 ↔ 角色数据权限 (1:N)
  role_data_permissions:
    cascade_delete: true           # ← 新增

  # 角色 ↔ 角色维度范围 (1:N)
  role_dimension_scopes:
    cascade_delete: true           # ← 新增

  # 角色 ↔ 用户组 (M:N reverse, 通过 group_roles)
  # group_roles 已有 DB ON DELETE CASCADE, 但仍需要 yaml 声明保持一致
  assigned_groups:
    cascade_delete: true           # ← 新增
```

### 2.2 系统角色保护（action_executor.py）

`_do_delete` 前增加：

```python
# [FIX BUG-V061 2026-07-12] 系统角色保护
if meta_object.id == 'role':
    original = self._read_original(meta_object, id_value)
    if original and original.get('is_system'):
        return ActionResult.fail(
            error="SYSTEM_ROLE_PROTECTED",
            message=f"系统角色 '{original.get('name')}' 不能删除"
        )
    if original and original.get('code') == 'super_admin':
        return ActionResult.fail(
            error="SUPER_ADMIN_PROTECTED",
            message="Super Admin 角色不能删除"
        )
```

### 2.3 不改动 user_group.yaml

理由：
- `group_roles` DB 层已有 `ON DELETE CASCADE`
- 删除角色 → `group_roles` 自动清
- 但反向保护（删除 user_group 检查 member）的逻辑不在本次范围

### 2.4 `deletion_policy.cascade_delete` 处理

- **保留现有 `deletion_policy.cascade_delete: [user_roles, role_permissions]`**
- 不动它（其他模块或审计可能要读）
- **改为与 associations.cascade_delete 一致**：加 `role_menu_permissions, role_data_permissions, role_dimension_scopes, permission_rules, group_roles`

---

## 三、验证（SOP）

### 3.1 集成测试脚本（test_role_cascade_delete.py）

```python
"""集成测试: 删除角色时自动级联清理子表."""
import requests, time

def test_role_delete_with_cascade(base_url, admin_token):
    # 1. 创建一个测试角色
    role = requests.post(f'{base_url}/api/v1/roles', json={
        'code': f'cascade_test_{int(time.time())}',
        'name': '级联删除测试',
        'is_active': 1,
    }, headers={'Authorization': f'Bearer {admin_token}'}).json()
    role_id = role['data']['id']

    # 2. 给它分配一些权限 + 菜单
    requests.post(f'{base_url}/api/v1/roles/{role_id}/permissions',
        json={'permissions': ['product:read', 'product:write']},
        headers={'Authorization': f'Bearer {admin_token}'})
    requests.post(f'{base_url}/api/v1/roles/{role_id}/menus',
        json={'menu_codes': ['product-management']},
        headers={'Authorization': f'Bearer {admin_token}'})

    # 3. 验证子表有记录
    assert count(role_id, 'role_permissions') >= 2
    assert count(role_id, 'role_menu_permissions') >= 1

    # 4. 删除角色 - 应该成功（静默级联）
    resp = requests.delete(f'{base_url}/api/v1/roles/{role_id}',
                           headers={'Authorization': f'Bearer {admin_token}'})
    assert resp.json()['success']
    assert resp.json()['data'].get('cascade')  # 显示级联了

    # 5. 子表记录全为 0
    assert count(role_id, 'role_permissions') == 0
    assert count(role_id, 'role_menu_permissions') == 0
    assert count(role_id, 'role_data_permissions') == 0

def test_system_role_protected(base_url, admin_token):
    # Super Admin 角色 ID=1 - 删除应该失败
    resp = requests.delete(f'{base_url}/api/v1/roles/1',
                           headers={'Authorization': f'Bearer {admin_token}'})
    assert not resp.json()['success']
    assert 'SYSTEM_ROLE' in resp.json()['error'] or 'SUPER_ADMIN' in resp.json()['error']
```

### 3.2 验收 checklist

- [ ] 本地 e2e：创建测试角色 + 分配权限 → 成功删除（不再报错"无法删除"）
- [ ] 创建测试角色 + 分配菜单 → 成功删除
- [ ] `data_permissions` 含条件规则 → 成功删除
- [ ] Super Admin (id=1) 仍拒绝删除 ✓ 系统角色保护
- [ ] 删除后 `user_count`, `permission_count`, `menu_count` 都=0 (缓存刷新)

---

## 四、风险评估

| 风险 | 概率 | 缓解 |
|------|:--:|------|
| 误删产品级业务数据 | 低 | 仅删 role 的引用，不删 product 本身 |
| 用户误删角色 | 低 | UI 上已有二次确认弹窗 |
| cascade_delete 字段不解析 | 中 | 已有 _check_reverse_fk_references 实现解析此字段 ([action_executor.py:1131](file:///d:/filework/worktrees/release-prep/meta/core/action_executor.py#L1131))，仅 yaml 变更 |
| 缓存不刷新 | 中 | 删除后 `menu_count/permission_count` 计算字段 cache TTL=600s，下次访问自动失效 |

---

## 五、不在范围内

- ✗ 不实现删除前预览（用户主动选择级联子表）—— YAGNI
- ✗ 不修改 user_group.yaml
- ✗ 不改 SQLite FK `ON DELETE CASCADE` DB 模式（仅 yaml 层）

---

## 六、待用户确认

- [ ] **用户审阅本 spec**
- [ ] **同意后**进入 implementation（写 plan → 改 yaml → 集成测试 → commit）
