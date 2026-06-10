# v1.4 P6 重构 — user_group_service 主表 CRUD 方法标记 @deprecated（2026-06-05）

> v1.4 SSOT 落地最终阶段：明确元数据驱动 BO 框架 vs 业务领域服务的边界

## 背景

### 关键认识（v1.4 多次迭代后的修正）
元数据驱动原则下，**业务领域服务（user_group_service）不是反模式**：

- `user_group` / `role` / `user` / `permission` 等元数据 **已**走 BO 框架（yaml schema + 拦截器链）
- `user_group_service` 中**真正冗余**的方法是**主表 CRUD**（v2/bo 端点已覆盖）
- `user_group_service` 中**应保留**的方法是**业务关系**（成员、角色、委托、迁移、树形结构）
- 这是合理的**领域服务分层**，不是反模式

## 范围

### 标记为 @deprecated 的方法（5 个）

| 方法 | 替代方案 | 保留原因 |
|------|----------|----------|
| `get_all_groups` | v2/bo/user_group 端点 | v1 支持业务过滤（member_count range, __in, __like）v2 尚未完全覆盖 |
| `get_group` | v2/bo/user_group/{id} 端点 | BO 框架自动应用 SSOT 派生 + 字段展示增强 |
| `create_group` | v2/bo/user_group POST | BO 框架统一拦截器链 |
| `update_group` | v2/bo/user_group/{id} PUT | BO 框架统一拦截器链 |
| `delete_group` | `DeletionService`（已在 user_group_api.py:216 使用） | DeletionService 走 yaml schema 的 cascade_delete |

### 保留的方法（25 个，业务关系）

- 成员管理（5 个）：`get_group_members` / `add_member` / `remove_member` / `is_member` / `is_group_manager`
- 层级结构（4 个）：`get_child_groups` / `get_all_descendants` / `get_all_ancestors` / `get_group_tree`
- 委托管理（4 个）：`get_managed_groups` / `can_manage_user` / `get_manageable_users` / `get_user_groups`
- 数据权限（1 个）：`get_user_effective_data_permissions_via_groups`
- 角色管理（5 个）：`get_group_roles` / `add_group_role` / `remove_group_role` / `set_group_roles` / `get_roles_not_in_group`
- 工具（2 个）：`get_group_by_code` / `migrate_group_data_permissions_to_roles`

## 实现

### P6-1: 调用点分析

`meta/api/user_group_api.py` 中 10 处 `service.method()` 调用：
- `get_all_groups` (1) - 主表 CRUD
- `delete` (1) - 走 DeletionService（不是 UserGroupService）
- `get_group_members` (1) - 业务关系
- `get_group_data_permissions` (1) - 业务关系
- `add_group_data_permission` (1) - 业务关系
- `remove_group_data_permission` (1) - 业务关系
- `get_group_roles` (1) - 业务关系
- `get_group_tree` (1) - 业务关系
- `get_roles_not_in_group` (1) - 业务关系
- `migrate_group_data_permissions_to_roles` (1) - 业务关系

### P6-2: @deprecated 注释

为 5 个主表 CRUD 方法添加清晰的弃用说明：
- 指出推荐的 BO 框架替代方案
- 解释保留方法的原因（v1 API 兼容性、业务过滤差异）

### P6-3: Deprecation Headers

由 **v1.4 P2** 阶段已实现（`meta/server.py:573-584`）：

```python
@app.after_request
def add_v1_deprecation_headers(response):
    if getattr(g, 'v1_deprecated', False):
        response.headers['Deprecation'] = 'true'
        response.headers['Sunset'] = '2026-08-14'
        response.headers['Link'] = f'</api/v2/{first}>; rel="successor-version"'
```

**RFC 8594 Deprecation** + **RFC 8288 Sunset** 双重标准。

### P6-4: 验证

#### Deprecation Headers 验证
| 端点 | 状态 | Deprecation | Sunset | Link |
|------|------|-------------|--------|------|
| /api/v1/user-groups | 200 | true | 2026-08-14 | `</api/v2/user-groups>; rel="successor-version"` |
| /api/v2/bo/user_group | 200 | NONE | NONE | NONE |
| /api/v1/roles/1/overlaps | 200 | true | 2026-08-14 | `</api/v2/roles>; rel="successor-version"` |
| /api/v2/roles/1/overlaps | 200 | NONE | NONE | NONE |

#### E2E 回归
- business-object-crud: 1/1 ✅
- product-crud: 2/2 ✅
- user-group-detail: 1/1 ✅
- role-permission-center: 2/2 ✅
- overlap-warning: 1/1 ✅
- user-permission: 3/3 ✅

**总计 10/10 passed**

## 关键文件

| 文件 | 改动 |
|------|------|
| `meta/services/user_group_service.py` | 5 个主表 CRUD 方法添加 P6 @deprecated 注释 |
| `meta/server.py` | 已有 v1 deprecation 中间件（v1.4 P2） |
| `meta/schemas/user_group.yaml` | 已有完整 BO schema |
| `meta/api/user_group_api.py` | 使用 UserGroupService 业务关系方法（10 处） |

## 架构原则总结（v1.4 落地后）

### 元数据驱动 BO 框架
- yaml schema 描述 object
- 拦截器链（`PersistenceInterceptor` / `AuditInterceptor` / `PermissionInterceptor` / `OwnerAutoPermissionInterceptor` 等）
- 适用：标准 CRUD + 横切关注点
- 端点：v2/bo/{type}

### 业务领域服务
- 实现复杂业务规则（树形、委托、聚合、迁移）
- 适用：BO 框架无法表达的领域逻辑
- 方法：领域服务（`UserGroupService`）直接调用

### v1 API 兼容性
- v1 路径自动加 Deprecation headers
- 6 个月过渡期（至 2026-08-14）
- Sunset 后开始 410

## 未来 P7 任务（可选）

1. **前端迁移到 v2/bo**：
   - `src/api/userGroup.js` 等文件改用 v2 端点
   - Sunset 倒计时

2. **删除冗余 service 方法**：
   - 2026-08-14 后 Sunset 自动化清理
   - 移除 `user_group_service` 的 5 个 deprecated 方法
   - 调用方迁移到 v2/bo 或 DeletionService

3. **业务过滤能力迁移到 v2**：
   - v1 的 `member_count range` 过滤应作为 v2 端点能力
   - 让 v2 端点能完全替代 v1 业务

4. **同类重构**：
   - `permission_service.py` 类似模式
   - `role_service.py`（如存在）
   - 标记 + 文档说明

## Sunset 倒计时

- 当前日期：2026-06-05
- Sunset 日期：2026-08-14
- 剩余：约 10 周
