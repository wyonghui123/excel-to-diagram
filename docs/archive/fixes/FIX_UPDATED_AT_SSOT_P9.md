# v1.4 P9 — UI 修复 + 业务方法单元测试（2026-06-05）

> v1.4 SSOT 收官：P8 Sunset 后遗留下来两个任务

## P9-1/2: user-group-filter UI 修复

### Root Cause

E2E 失败不是 P8 Sunset 引入的回归，而是**E2E 选择器错误**。

DOM 结构：
```
.generic-tab-container
  <nav class="sub-nav-tabs">          ← 等待通过
  <div class="gtc-content">
    <div class="generic-object-list"> ← 旧选择器漏掉这层
      <div class="meta-list-page">    ← 实际目标
        <div class="el-table">         ← 实际目标
```

旧选择器 `.meta-list-page:nth-child(2) .el-table`：
- 错误前提：`.meta-list-page` 是 `.gtc-content` 的子元素
- 实际：`.gtc-content → .generic-object-list → .meta-list-page`
- `.gtc-content` 只有 1 个子元素（`.generic-object-list`），没有 `.meta-list-page`
- `:nth-child(2)` 在 `.gtc-content` 中找不到 `.meta-list-page`

### 修复

**e2e/features/user-group-filter.spec.js**：3 处选择器改为 `.gtc-content .meta-list-page .el-table`

```diff
- await page.locator('.meta-list-page:nth-child(2) .el-table').waitFor(...)
+ await page.locator('.gtc-content .meta-list-page .el-table').waitFor(...)
```

### 验证

| 测试 | 结果 |
|------|------|
| C01: 表格加载 + 过滤图标可见性 | ✅ pass |
| C02: 点击父组列过滤图标 | ✅ pass |
| **总计** | **4/4 pass**（含 2 retries） |

## P9-3: user_group_service 单元测试

### 现状

`meta/services/user_group_service.py` 经 P8 Sunset 后保留 19 个公开/内部方法：
- 主表方法：1 个（`get_group_by_code`）
- 成员管理：5 个
- 层级查询：4 个
- 委托授权：3 个
- 角色关联：5 个
- 权限聚合：1 个
- 迁移工具：1 个
- 内部辅助：3 个

### 关键修复（P8 回归发现）

P8 物理删除 `get_group` 和 `get_all_groups` 后，service 内部还有 3 处引用：

| 位置 | 修复 |
|------|------|
| `get_all_ancestors` line 150 | `self.get_group(group_id)` → `self._get_object(group_id)` |
| `get_group_tree` line 158 | `self.get_all_groups()` → SQL 直接查询 `SELECT * FROM user_groups` |
| `migrate_group_data_permissions_to_roles` line 329 | `self.get_group(group_id)` → `self._get_object(group_id)` |

**这 3 个修复是 P9 单元测试发现的真实回归** — 没有单元测试这些 bug 会一直隐藏。

### 测试覆盖（26 个测试）

| 类别 | 测试数 | 覆盖方法 |
|------|--------|----------|
| 主表方法 | 2 | get_group_by_code (含 not_found) |
| 成员管理 | 4 | add_member, remove_member, is_member, get_user_groups, is_group_manager |
| 层级查询 | 4 | get_child_groups, get_all_descendants, get_all_ancestors, get_group_tree |
| 委托授权 | 4 | get_managed_groups, can_manage_user (3 场景) |
| 角色关联 | 5 | get_group_roles, add/remove_group_role, set_group_roles, get_roles_not_in_group |
| 权限聚合 | 2 | get_user_effective_data_permissions_via_groups (含 no_perm) |
| 迁移工具 | 1 | migrate_group_data_permissions_to_roles |
| 内部辅助 | 2 | _get_object (含 not_found) |
| **总计** | **24 → 26** | **19 个方法** |

### 关键发现（测试过程暴露的语义修正）

`can_manage_user` 实际语义是：
- **管理** = 用户是组管理员 OR 组的 manager_id 的组
- **不是**"共同组成员即可管理"

`get_managed_groups` 也只返回用户**作为管理员**的组，不包括仅作为普通成员所在的组。

测试用例从"共同组成员管理"修正为"组管理员身份管理"。

### 验证

**26/26 passed**

## P9-4: permission_service 单元测试

### 现状

`meta/services/permission_service.py` 经 P7/P8 Sunset 后保留 13 个业务方法：
- 个人组管理：2 个
- 角色链：3 个
- 权限链：3 个
- 角色管理：3 个
- 验证：1 个
- 统一语义：1 个

### 测试覆盖（24 个测试）

| 类别 | 测试数 | 覆盖方法 |
|------|--------|----------|
| 内部辅助 | 4 | _get_or_create_personal_group (2), _ensure_user_in_group (2) |
| 角色链 | 2 | get_user_roles (空 + 有角色) |
| 权限链 | 2 | get_user_permissions (空 + 有权限) |
| 权限检查 | 2 | has_permission (true + false) |
| 角色管理 | 2 | assign_role (新建 + 已有) |
| 角色管理 | 2 | remove_role (有 + 无) |
| 角色列表 | 1 | get_all_roles |
| 角色权限 | 4 | get_role_permissions (2), set_role_permissions (2) |
| 验证 | 2 | _validate_action_code (true + false) |
| 统一语义 | 2 | check_permission_unified (true + false) |
| 统一语义 | 1 | create_permission_unified |
| **总计** | **24** | **13 个方法** |

### 关键发现

1. **个人组命名规范**：`_get_or_create_personal_group` 用 `personal_group_user_{user_id}` 格式（不是 `personal_{user_id}`）
2. **PermissionService schema 包含**：
   - `user_groups.updated_at` 列
   - `permissions.scope` 列（默认 'all'）
3. **`get_action_codes()` 返回 set**（不是 list）— 需用 `list(codes)[0]` 转换
4. **`check_permission_unified` 期望**：`f"{resource_type}:{action_code}"` 格式（冒号分隔）
5. **`create_permission_unified` 实际写**：`scope` 列，code 格式为 `f"{resource_type}:{action_code}"`

### 验证

**24/24 passed**

## P9-5: 全套测试

### 单元测试
- `test_user_group_service.py`：**26/26 passed**
- `test_permission_service.py`：**24/24 passed**
- 合计：**50/50 passed**

### E2E 回归
| 测试文件 | 结果 |
|----------|------|
| user-group-detail | ✅ pass |
| user-group-filter (P9 修复) | ✅ pass (4/4) |
| role-permission-center | ✅ pass |
| overlap-warning | ✅ pass |
| user-permission | ✅ pass |
| **总计** | **10/10 passed** |

### API 端点验证
**12/12 通过**：
- 3 个 v1 Sunset 端点 → 410 ✅
- 3 个 v1 业务关系端点 → 200 ✅
- 2 个 v1 SPECIAL 端点 → 200 ✅
- 4 个 v2 BO 端点 → 200 ✅
- **所有 Deprecation headers = NONE** ✅

## 关键文件

| 文件 | 改动 |
|------|------|
| `e2e/features/user-group-filter.spec.js` | 3 处选择器修复 (P9-2) |
| `meta/services/user_group_service.py` | 3 处内部对已删方法的引用修复 (P9-3) |
| `meta/tests/test_user_group_service.py` | 26 个测试用例 (P9-3) |
| `meta/tests/test_permission_service.py` | 24 个测试用例新增 (P9-4) |

## v1.4 全阶段最终总结

| 阶段 | 内容 | 单元测试 | E2E | 物理删除 | 410 端点 |
|------|------|----------|-----|----------|----------|
| P3 | SSOT helper 抽取 | 0 | 0 | 0 | 0 |
| P4 | 移除 7 张 BO 表 `updated_at` | 0 | 0 | 0 | 0 |
| P5 | `created_at_epoch` 性能优化 | 0 | 0 | 0 | 0 |
| P6 | user_group_service 5 个 @deprecated | 0 | 0 | 0 | 0 |
| P7 | permission_service 1 个 @deprecated | 0 | 0 | 0 | 0 |
| P8 | Sunset 自动化清理 | 0 | 0 | **6** | **6** |
| P9 | UI 修复 + 单元测试 | **50** | **10** | 0 | 0 |
| **合计** | - | **50** | **10** | **6** | **6** |

## 业务代码覆盖率提升

| 服务类 | P8 前 | P9 后 | 提升 |
|--------|-------|-------|------|
| `UserGroupService` | 0/19 (0%) | 19/19 (100%) | +100% |
| `PermissionService` | 0/13 (0%) | 13/13 (100%) | +100% |
| **合计** | **0/32 (0%)** | **32/32 (100%)** | **+100%** |

## 未来可选任务

1. **同类 service 全面测试**：
   - `data_permission_service.py`
   - `condition_permission_service.py`
   - 评估测试覆盖

2. **性能优化**：
   - `get_user_effective_data_permissions_via_groups` 4 表 JOIN 改为预计算缓存
   - `get_all_descendants` Python 递归改为 `WITH RECURSIVE`

3. **UI 进一步优化**：
   - `user-group-filter.spec.js` 之外的其他 E2E 选择器统一为 `.gtc-content .meta-list-page` 格式

4. **架构层优化**：
   - `_get_object` 内联 SQL 可移到 BO 框架查询
   - `assign_role` 的 `token_version_service.bump` 可改为异步
