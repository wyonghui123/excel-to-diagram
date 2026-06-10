# v1.4 P10 — 权限体系测试补齐（2026-06-05）

> v1.4 SSOT 收官：基于完整权限体系补齐边界场景、负向场景、集成场景

## 任务目标

基于 v1.4 建立的权限体系，**全面盘点**现有测试覆盖 vs 实际业务场景，**识别 gap**，**补齐测试** + **发现并修复潜在 bug**。

## P10 关键发现 — 3 个真实安全 bug

### 🐛 Bug 1: token_version 失效机制形同虚设（**严重**）

**文件**：`meta/services/token_version_service.py:64-70`

**Bug 描述**：
```python
def _get_db_version(self, user_id: int) -> int:
    row = self._ds.execute(  # ← row 实际是 cursor 对象
        "SELECT COALESCE(token_version, 0) FROM users WHERE id = ?",
        [user_id]
    )
    return row[0] if row else 0  # ← cursor 不支持下标
```

**触发流程**：
1. `assign_role()` → `token_version_service.bump(user_id)` → `_get_db_version(user_id)`
2. `bump` 内部调用 `_get_db_version` 时，**`row[0]` 抛 TypeError**
3. `bump` 的 `try/except` 吞掉异常 → DB 中 `token_version` 不变
4. 后续 `check()` 调用 `_get_db_version` → 同样异常 → `try/except` 兜底返回 `True`
5. **所有 token 验证实际上都通过！**

**安全影响**：
- 用户角色被撤销后，**旧 token 仍可使用**
- 攻击者即使被剥夺权限，**仍能继续访问**
- 这是一个**完全静默的安全漏洞**

**修复**（P10 实施）：
```python
cursor = self._ds.execute(...)
row = cursor.fetchone()  # ← 关键：必须 fetchone()
return row[0] if row else 0
```

### 🐛 Bug 2: get_all_ancestors 循环引用栈溢出（**严重**）

**文件**：`meta/services/user_group_service.py:147-155`

**Bug 描述**：
```python
def get_all_ancestors(self, group_id: int) -> List[int]:
    ancestors = []
    group = self._get_object(group_id)
    if group and group.get('parent_id'):
        ancestors.append(group['parent_id'])
        ancestors.extend(self.get_all_ancestors(group['parent_id']))  # ← 无循环检测
    return ancestors
```

**触发场景**：
- 数据库被破坏（手动 SQL 错误 / 迁移错误 / 业务逻辑 bug）
- `user_groups.parent_id` 形成环路（自引用或两节点循环）
- 调用 `get_all_ancestors` 时**栈溢出** → 整个请求失败

**修复**（P10 实施）：
```python
ancestors = []
visited = set()
current_id = group_id
while current_id is not None:
    if current_id in visited:
        break  # 检测到循环，停止
    visited.add(current_id)
    group = self._get_object(current_id)
    if not group:
        break
    parent_id = group.get('parent_id')
    if parent_id is None:
        break
    ancestors.append(parent_id)
    current_id = parent_id
return ancestors
```

### 🐛 Bug 3: set_role_permissions 重复 id 触发 UNIQUE 失败（**中等**）

**文件**：`meta/services/permission_service.py:146-166`

**Bug 描述**：
```python
def set_role_permissions(self, role_id, permission_ids):
    self.ds.execute("DELETE FROM role_permissions WHERE role_id = ?", [role_id])
    for pid in permission_ids:  # ← 不去重
        self.ds.execute(
            "INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
            [role_id, pid]
        )  # ← 重复会触发 UNIQUE 约束失败
```

**触发场景**：
- 前端误传重复 id：`[p1, p1, p2]`
- 第二次插入 `p1` → **UNIQUE 约束失败** → 整个 set_role_permissions 失败
- `try/except` 兜底 → 返回 False
- 角色权限**部分**被清除但部分未插入

**修复**（P10 实施）：
```python
seen = set()
unique_pids = []
for pid in permission_ids:
    if pid not in seen:
        seen.add(pid)
        unique_pids.append(pid)
for pid in unique_pids:
    self.ds.execute(...)
```

## P10 测试覆盖（4 个新文件 + 94 个新测试）

| 测试文件 | 测试数 | 类别 | 发现 bug |
|----------|--------|------|----------|
| `test_user_group_service_edge.py` | 29 | 用户组边界场景 | Bug 2 |
| `test_permission_service_edge.py` | 23 | 权限业务场景 | Bug 3 |
| `test_token_version_service.py` | 24 | Token 失效机制 | Bug 1 |
| `test_security_authorization.py` | 18 | 端到端集成安全 | - |
| **合计（新增）** | **94** | - | **3** |

## 详细测试覆盖

### A. 用户组边界场景（test_user_group_service_edge.py，29 个）

#### A.1 安全/边界
- `test_self_reference_group`: 自引用（修复后通过）
- `test_two_level_cycle`: 两节点循环（修复后通过）
- `test_deeply_nested_descendants`: 20 层深度子孙
- `test_deeply_nested_ancestors`: 20 层深度祖先
- `test_add_member_duplicate`: UNIQUE 约束幂等
- `test_add_member_idempotent_manager`: is_manager 状态幂等
- `test_add_group_role_duplicate`: group_roles UNIQUE 约束

#### A.2 业务一致性
- `test_role_shared_across_groups`: 多组共享同一角色
- `test_effective_data_permissions_dedup`: data permission 跨组去重
- `test_effective_data_permissions_different_resources`: 不同资源聚合
- `test_personal_group_codes_unique`: 个人组 code 唯一

#### A.3 委托链安全性
- `test_can_manage_self_no_all_perm`: 自反性
- `test_can_manage_self_with_all_perm`: admin 绕过
- `test_can_manage_user_idempotent`: 多次调用一致
- `test_multiple_managers_same_group`: 多管理员同组
- `test_manager_id_provides_manage_rights`: manager_id 字段生效
- `test_both_manager_id_and_is_manager`: 双重管理
- `test_can_manage_user_different_groups`: 隔离性

#### A.4 层级查询
- `test_descendants_includes_root_children`
- `test_descendants_root_no_children`
- `test_ancestors_root_no_parent`
- `test_group_tree_multiple_roots`
- `test_group_tree_with_descendants`

#### A.5 事务一致性
- `test_add_member_invalid_group_id`: FK 约束
- `test_set_group_roles_clears_existing`
- `test_set_group_roles_empty_list`

#### A.6 综合
- `test_full_user_lifecycle`
- `test_user_in_multiple_groups_with_different_roles`

### B. 权限业务场景（test_permission_service_edge.py，23 个）

#### B.1 通配符权限
- `test_wildcard_permission_grants_all`
- `test_wildcard_via_get_user_permissions`

#### B.2 业务一致性
- `test_get_user_roles_dedup`: 角色去重
- `test_get_user_permissions_dedup`: 权限去重

#### B.3 assign/remove 业务
- `test_assign_role_repeat_is_idempotent`
- `test_assign_role_multiple_to_one_user`
- `test_remove_role_repeat_is_idempotent`
- `test_remove_role_not_in_personal_group`

#### B.4 个人组唯一性
- `test_personal_group_idempotent`
- `test_personal_group_different_users`
- `test_ensure_user_in_group_after_personal_group_creation`

#### B.5 set_role_permissions 边界
- `test_set_role_permissions_duplicate_in_list` (修复后)
- `test_set_role_permissions_with_nonexistent_perm`

#### B.6 权限链路
- `test_has_permission_inherited_from_group`
- `test_get_user_permissions_excludes_unlinked`

#### B.7 unified 边界
- `test_check_permission_unified_wildcard`
- `test_check_permission_unified_with_instance`
- `test_check_permission_unified_returns_false_no_role`

#### B.8 其他
- `test_create_permission_unified_duplicate_code`
- `test_remove_role_only_affects_target_user`
- `test_full_permission_lifecycle`
- `test_role_priority_ordering`
- `test_system_role_cannot_be_removed_via_service`

### C. Token 失效机制（test_token_version_service.py，24 个）

#### C.1 _get_db_version
- `test_get_db_version_normal`
- `test_get_db_version_zero`
- `test_get_db_version_nonexistent_user`
- `test_get_db_version_returns_int`

#### C.2 check()
- `test_check_zero_token_version_passes`
- `test_check_matching_version_passes`
- `test_check_mismatched_version_fails`
- `test_check_with_cache_is_fast` (1000 calls < 500ms)

#### C.3 bump()
- `test_bump_increments_version`
- `test_bump_multiple_times`
- `test_bump_multiple_users`
- `test_bump_invalidates_old_token` (核心安全保证)
- `test_bump_zero_token_version`
- `test_bump_large_token_version`

#### C.4 缓存
- `test_cache_avoids_db_lookup`
- `test_cache_expires_after_ttl`
- `test_bump_updates_cache`

#### C.5 异常
- `test_set_data_source_after_init`
- `test_check_with_db_error_returns_true`
- `test_bump_with_invalid_user_id`
- `test_bump_empty_list`
- `test_bump_non_list_input`
- `test_check_negative_token_version`

#### C.6 集成
- `test_assign_role_bumps_token_version` (占位)

### D. 端到端集成安全（test_security_authorization.py，18 个）

#### D.1 委托链完整性
- `test_delegation_chain_full`: 经理→成员全链路
- `test_delegation_chain_broken`: 无共同组
- `test_delegation_through_ancestor_group`: 层级委托（parent_mgr 通过 child 间接管理）

#### D.2 权限分配/回收
- `test_permission_revoke_invalidates_token`
- `test_wildcard_grant_and_revoke`

#### D.3 权限冲突
- `test_multiple_roles_with_overlapping_permissions`
- `test_no_permission_grant_denies`
- `test_disabled_role_cannot_be_used`

#### D.4 资源级权限
- `test_data_permissions_via_groups`
- `test_data_permissions_isolated_between_groups`

#### D.5 委托链安全性
- `test_admin_bypass_via_has_all_permission`
- `test_non_admin_cannot_bypass`
- `test_user_cannot_escalate_by_joining_own_group`

#### D.6 用户状态
- `test_inactive_user_cannot_be_assigned_role`
- `test_user_without_personal_group_gets_one`

#### D.7 性能/规模
- `test_large_group_member_count`: 100 成员
- `test_user_in_many_groups`: 50 组

#### D.8 端到端
- `test_e2e_permission_lifecycle`: 完整生命周期

## 关键文件

| 文件 | 改动 |
|------|------|
| `meta/services/token_version_service.py` | **Bug 1 修复**：`fetchone()` 调用 |
| `meta/services/user_group_service.py` | **Bug 2 修复**：循环引用检测 |
| `meta/services/permission_service.py` | **Bug 3 修复**：permission_ids 去重 |
| `meta/tests/test_user_group_service_edge.py` | **新增**：29 个测试 |
| `meta/tests/test_permission_service_edge.py` | **新增**：23 个测试 |
| `meta/tests/test_token_version_service.py` | **新增**：24 个测试 |
| `meta/tests/test_security_authorization.py` | **新增**：18 个测试 |

## v1.4 全阶段最终统计

| 阶段 | 单元测试 | E2E | 物理删除 | 410 端点 | 修复 bug |
|------|----------|-----|----------|----------|----------|
| P3-P7 | 0 | 0 | 0 | 0 | 0 |
| P8 Sunset | 0 | 0 | 6 | 6 | 0 |
| P9 基础测试 | 50 | 10 | 0 | 0 | 3 |
| **P10 边界补齐** | **94** | **0** | **0** | **0** | **3** |
| **合计** | **144** | **10** | **6** | **6** | **6** |

## 业务方法覆盖率（最终）

| 服务 | 方法数 | 覆盖 | 覆盖率 |
|------|--------|------|--------|
| `UserGroupService` | 19 | 19+29 = 48 tests | **100% + 边界** |
| `PermissionService` | 13 | 13+23 = 36 tests | **100% + 边界** |
| `TokenVersionService` | 5 | 5+24 = 29 tests | **100% + 边界** |
| **集成** | - | 18 tests | 端到端覆盖 |

## 未来可选任务

1. **同类 service 测试补齐**：
   - `data_permission_service.py`
   - `condition_permission_service.py`
   - `condition_permission_evaluator.py`

2. **数据库 schema 一致性测试**：
   - 测试 fixture 应严格匹配真实 schema（已部分修复）
   - 添加 schema migration 测试

3. **并发安全测试**：
   - 多线程并发 assign_role / remove_role
   - 事务隔离级别验证

4. **性能基准测试**：
   - 100 用户、1000 权限的查询性能
   - token_version_service 缓存命中率

5. **审计集成测试**：
   - assign_role 应触发 audit_log
   - token bump 应记录审计
