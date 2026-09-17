# Spec 16: 角色→权限集 + 用户组→组织 重命名迁移设计

> 文档编号: 16 | 状态: 准备稿（待评审） | 更新: 2026-08-28
> 主题: 把当前 `role / user_group` 命名升级到 `permission_set / org`，与 spec 13/14/15 业务模型对齐
> 前置: `13_organization_model_integration.md` / `14_org_management_dimension_and_migration.md` / `15_permission_config_unification.md`
> 范围: **仅文档 + 迁移设计稿，不改动代码**（执行由后续 `writing-plans` skill 输出实施计划后再分批 commit）

---

## TL;DR

| 项目 | 内容 |
|------|------|
| **目标 1** | `roles` 表重命名为 `permission_sets`，表结构、字段、外键、API 路径、UI 组件名全链路升级。语义不变（不引入 Salesforce-style 可堆叠权限集，留作二期）。 |
| **目标 2** | `user_groups` 表重命名为 `orgs`，同时新增 `org_functions` 表（多职能视图：行政/采购/成本中心），对齐 spec 13 §5.1d。`user_group_members` → `org_members`。 |
| **不做** | 不引入 `person / user / org_relationship`（外层 Party 模型）——留二期；不引入可堆叠权限集能力——留二期。 |
| **策略** | 纯重命名 + 全面升级（用户决策）。一次性完成全链路迁移，所有引用同步切换；不留 DB alias / API alias（旧名不再可访问）。 |
| **范围** | DB schema(13 表) + 后端 API/服务/迁移脚本(56 文件) + 前端组件/路由/i18n(29 文件) + 测试用例(20 文件) + 文档(11 文件) ≈ 130+ 文件 |
| **回滚** | Phase 0 全量快照 + Feature Flag `permission_set_refactor_enabled` 双轨 + 旧代码 git tag 永久保留。 |
| **下一步** | 用户审阅本设计稿 → 通过后由 `writing-plans` skill 输出分阶段实施计划。 |

---

## 1. 背景与决策记录

### 1.1 为什么现在做

1. spec 13/14/15 已确立"组织 = 一等管理维度"、"权限集 = 角色升级名"的目标模型。
2. 当前代码 `roles / user_groups` 命名与 spec 不一致，导致新人阅读代码需做一次"语义翻译"（role ≠ 业务岗位，而是"权限集合"）。
3. `permission_set_service.py` 已部分存在（Phase 13 P13-T3 写入），但与 `role_service.py` 并存未合并——历史债务累积。
4. UI 大量 `RolePermissionCenter / RoleDetail / GroupRoleDialog` 组件命名也需对齐。

### 1.2 关键决策（用户已确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 范围 | 仅准备文档 + 迁移设计稿 | 改动面 130+ 文件，分批执行更稳 |
| 权限集语义 | 表名重命名 `roles → permission_sets`，语义不变 | 不引入 Salesforce Profile 拆分的双层（role + permission_set）复杂度；二期再叠加 |
| 组织边界 | 狭义+中层：重命名 + `org_functions` 多职能视图 | 对齐 spec 13 §5.1d，但不引入外部企业 / Party 模型 |
| 迁移策略 | 纯重命名 + 全面升级（不留 alias） | 用户决策；避免 alias 长期遗留 |
| 文档交付物 | 概念映射表 + 影响面清单 + 迁移步骤 + 回滚/Feature Flag | 用户决策 |
| 文档位置 | `docs/spec_权限体系升级/16_*.md` | 与 13/14/15 同系列 |

### 1.3 非目标（明确不做）

- ❌ 不引入 `person / user / org_relationship`（spec 13 §5.1c/§5.2a/d）—— 留二期
- ❌ 不引入可堆叠 `user_permission_set_assignments` 多对多表 —— 留二期
- ❌ 不做数据行 `owning_org_id` 加列（spec 13 §5.3 路线 B）—— 默认路线 A 不变
- ❌ 不改 derivation_pipeline 算法 —— 仅字段名/表名同步
- ❌ 不改前端 UI 视觉 —— 仅文件/路由/组件名 + i18n 文案同步

---

## 2. 概念映射表（旧 → 新）

### 2.1 DB 表 / 视图

| 旧名 | 新名 | 备注 |
|------|------|------|
| `roles` | `permission_sets` | 主表重命名；保留所有列 |
| `role_permissions` | `permission_set_permissions` | 关联表 |
| `role_data_permissions` | `permission_set_data_permissions` | 关联表 |
| `role_dimension_scopes` | `permission_set_dimension_scopes` | 关联表 |
| `role_menus`（实际表 `role_menu_permissions`） | `permission_set_menu_permissions` | 关联表 |
| `role_effective_intents` | `permission_set_effective_intents` | 事实表 |
| `permission_rules` (role_id 列) | `permission_rules` (permission_set_id 列) | 仅列名重命名 |
| `user_roles` | `user_permission_sets` | 关联表 |
| `user_groups` | `orgs` | 主表重命名 |
| `user_group_members` | `org_members` | 关联表 |
| `group_roles` | `org_permission_sets` | 关联表 |
| `group_data_permissions` | `org_data_permissions` | 关联表 |
| —（新增） | `org_functions` | 多职能视图（org × function_type） |
| `department_id / organization_id`（users 表） | 保留为兼容列，新增 `primary_org_id` | 一次性数据回填 |

### 2.2 字段

| 旧字段 | 新字段 | 备注 |
|--------|--------|------|
| `roles.id` | `permission_sets.id` | 主键列名不变（仅表名变） |
| `roles.code / name / desc` | `permission_sets.code / name / desc` | 不变 |
| `roles.is_system` | `permission_sets.is_system` | 不变 |
| `user_groups.id` | `orgs.id` | |
| `user_groups.parent_id` | `orgs.parent_id` | 树层级保留 |
| `user_groups.code / name` | `orgs.code / name` | |
| `user_groups.is_personal` | `orgs.is_personal` | 兼容 personal_group_user_* 命名 |
| — | `orgs.org_type` (新) | enum: department/team/division/company，对齐 spec 13 §5.1a |
| — | `orgs.org_scope` (新) | enum: internal/external，默认 internal（保留扩展位） |
| `user_group_members.role_id` | `org_members.permission_set_id` | 兼容旧名 |

### 2.3 新增表 `org_functions` schema

```yaml
# meta/schemas/org_function.yaml (新)
org_function:
  fields:
    - { name: id, type: INTEGER, primary_key: true }
    - { name: org_id, type: INTEGER, foreign_key: orgs.id, not_null: true }
    - { name: function_type, type: TEXT, not_null: true }  # administrative/legal_entity/management_unit/procurement/accounting/profit_center/cost_center
    - { name: is_primary, type: BOOLEAN, default: false }
    - { name: effective_from, type: TIMESTAMP }
    - { name: effective_to, type: TIMESTAMP }
  indexes:
    - { columns: [org_id, function_type], unique: true }
```

### 2.4 API 路由

| 旧路径 | 新路径 |
|--------|--------|
| `/api/v1/roles` | `/api/v1/permission-sets` |
| `/api/v1/roles/{id}` | `/api/v1/permission-sets/{id}` |
| `/api/v1/roles/{id}/menus` | `/api/v1/permission-sets/{id}/menus` |
| `/api/v1/roles/{id}/dimension-scopes` | `/api/v1/permission-sets/{id}/dimension-scopes` |
| `/api/v1/user-groups` | `/api/v1/orgs` |
| `/api/v1/user-groups/{id}/members` | `/api/v1/orgs/{id}/members` |
| — | `/api/v1/orgs/{id}/functions` (新) |
| `/api/v1/user-group-roles` (或 `group-roles`) | `/api/v1/org-permission-sets` |

### 2.5 前端路由 / 组件

| 旧名 | 新名 |
|------|------|
| `/system/role-management` (或类似) | `/system/permission-set-management` |
| `/system/group-management` | `/system/org-management` |
| `RolePermissionCenter.vue` | `PermissionSetCenter.vue` |
| `RoleDetail.vue` / `RoleDetailDrawer.vue` | `PermissionSetDetail.vue` / `PermissionSetDetailDrawer.vue` |
| `RolePermissionDetail.vue` | `PermissionSetDetailContent.vue` |
| `GroupRoleDialog.vue` | `OrgPermissionSetDialog.vue` |
| — | `OrgFunctionPanel.vue` (新) |

### 2.6 Python 服务 / 类 / 函数

| 旧名 | 新名 |
|------|------|
| `meta/services/permission_service.py` 中 `RoleXxx` | `PermissionSetXxx` |
| `meta/services/user_group_service.py` | `meta/services/org_service.py` |
| `meta/api/role_api.py` | `meta/api/permission_set_api.py` |
| `meta/api/user_group_api.py` | `meta/api/org_api.py` |
| `meta/services/permission_set_service.py`（已存在） | 保留，作为核心实现 |
| `Role` / `UserGroup` 类名 | `PermissionSet` / `Org` |

### 2.7 i18n 文案

| 旧 key | 新 key |
|--------|--------|
| `permission.role.*` | `permission.permissionSet.*` |
| `permission.userGroup.*` | `permission.org.*` |
| `permission.roleCenter.title` | `permission.permissionSetCenter.title` |
| `permission.role.name` | `permission.permissionSet.name` |
| `permission.userGroup.name` | `permission.org.name` |

---

## 3. 影响面清单（全量文件）

### 3.1 DB Schema 层（13 文件）

| 文件 | 变更类型 |
|------|---------|
| `meta/schemas/generated_schema.sql` | CREATE TABLE 改名（11 张）+ 新增 `org_functions` |
| `meta/schemas/role.yaml` | 删除（或归档），引用全部改 `permission_set.yaml` |
| `meta/schemas/permission_set.yaml`（新） | 新建 |
| `meta/schemas/role_permission.yaml` | 删除，改 `permission_set_permission.yaml` |
| `meta/schemas/role_data_permission.yaml` | 同上 |
| `meta/schemas/role_dimension_scope.yaml` / `role_dimension_scopes.yaml` | 改名 |
| `meta/schemas/user_group.yaml` | 删除，改 `org.yaml` |
| `meta/schemas/user_group_member.yaml` | 改名 |
| `meta/schemas/group_data_permission.yaml` | 改名 |
| `meta/schemas/org.yaml`（新） | 新建 |
| `meta/schemas/org_member.yaml`（新） | 新建 |
| `meta/schemas/org_permission_set.yaml`（新） | 新建 |
| `meta/schemas/org_data_permission.yaml`（新） | 新建 |
| `meta/schemas/org_function.yaml`（新） | 新建 |

### 3.2 后端 Python 层（56 文件）

#### 3.2.1 API 端点（10 文件）

```
meta/api/role_api.py                     → meta/api/permission_set_api.py
meta/api/role_menu_api.py               → meta/api/permission_set_menu_api.py
meta/api/role_dimension_scope_api.py    → meta/api/permission_set_dimension_scope_api.py
meta/api/user_group_api.py              → meta/api/org_api.py
meta/api/user_api.py                    (内部角色引用改名)
meta/api/bo_api.py                      (内部角色引用改名)
meta/api/special_routes_api.py          (内部角色引用改名)
meta/api/permission_dimension_api.py    (内部角色引用改名)
meta/api/overlap_api.py                 (内部角色引用改名)
meta/api/intent_api.py                  (内部角色引用改名)
```

#### 3.2.2 Service 层（15 文件）

```
meta/services/permission_service.py     (RoleXxx → PermissionSetXxx)
meta/services/user_group_service.py     → meta/services/org_service.py
meta/services/data_permission_service.py (内部角色引用改名)
meta/services/permission_set_service.py (已存在，作为核心实现; 合并 RoleXxx 逻辑)
meta/services/permission_bundle_service.py (内部角色引用改名)
meta/services/role_consistency_audit.py → meta/services/permission_set_consistency_audit.py
meta/services/import_export_service.py  (内部角色引用改名)
meta/services/menu_auto_generator.py    (内部角色引用改名)
meta/services/menu_permission_service.py (内部角色引用改名)
meta/services/condition_permission_service.py (内部角色引用改名)
meta/services/permission_resolver.py    (内部角色引用改名)
meta/services/permission_audit_service.py (内部角色引用改名)
meta/services/permission_migration.py   (内部角色引用改名)
meta/services/query_service.py          (内部角色引用改名)
meta/services/auth_provider.py          (内部角色引用改名)
meta/services/structured_logger.py      (内部角色引用改名)
```

#### 3.2.3 Core 层（8 文件）

```
meta/core/action_executor.py            (RoleXxx/UserGroupXxx 全部改名)
meta/core/derivation_pipeline.py        (内部角色引用改名)
meta/core/intent_resolver.py            (内部角色引用改名)
meta/core/effective_intent_dao.py       (内部角色引用改名)
meta/core/dim_scope_overlap_detector.py (内部角色引用改名)
meta/core/runtime_dimension_resolver.py (内部角色引用改名)
meta/core/interceptors/data_permission_interceptor.py (内部角色引用改名)
meta/core/interceptors/write_scope_interceptor.py     (内部角色引用改名)
```

#### 3.2.4 Migration 脚本（5 文件）

```
meta/migrations/add_role_dim_scope_bo_id_2026.py        (历史归档)
meta/migrations/add_role_intents_2026.py               (历史归档)
meta/migrations/add_role_permissions_granted.py        (历史归档)
meta/migrations/drop_user_roles_table.py               (历史归档)
meta/migrations/drop_user_group_member_count.py        (历史归档)
# + 新增
meta/migrations/2026_08_28_rename_roles_to_permission_sets.py
meta/migrations/2026_08_28_rename_user_groups_to_orgs.py
meta/migrations/2026_08_28_create_org_functions.py
```

#### 3.2.5 Scripts 层（3 文件）

```
meta/scripts/migrate_role_to_permission_set.py   (历史归档 — 已无意义，旧角色被新表取代)
meta/scripts/init_menu_permissions.py            (内部角色引用改名)
meta/scripts/migrate_system_admin.py             (内部角色引用改名)
```

### 3.3 前端 Vue/TS 层（29 文件）

#### 3.3.1 视图组件（10 文件）

```
src/views/SystemManagement/RolePermissionCenter.vue     → PermissionSetCenter.vue
src/views/SystemManagement/RoleDetail.vue                → PermissionSetDetail.vue
src/views/SystemManagement/RoleDetailDrawer.vue          → PermissionSetDetailDrawer.vue
src/views/SystemManagement/RolePermissionDetail.vue      → PermissionSetDetailContent.vue
src/views/SystemManagement/GroupRoleDialog.vue           → OrgPermissionSetDialog.vue
src/views/SystemManagement/composables/useMenuPermission.ts  (内部角色引用改名)
src/views/SystemManagement/components/DimensionScopePanel.vue (内部角色引用改名)
src/views/SystemManagement/components/PermissionConfigPanel.vue (内部角色引用改名)
src/views/SystemManagement/components/ResourceActionMatrix.vue  (内部角色引用改名)
src/views/SystemManagement/components/MenuPermissionMatrix.vue  (内部角色引用改名)
```

#### 3.3.2 ObjectPage 通用组件（5 文件）

```
src/components/common/ObjectPage/ObjectPageContent.vue
src/components/common/ObjectPage/ObjectPageShell.vue
src/components/common/ObjectPage/HistorySection.vue
src/views/ObjectDetailPage.vue
src/composables/useAssociationNavigation.js
```

#### 3.3.3 路由（2 文件）

```
src/router/modules/system.js
src/router/dynamicRoutes.js
```

#### 3.3.4 Services / Utils（4 文件）

```
src/services/permissionService.js       (内部角色引用改名)
src/services/objectTypeService.js
src/services/graphqlClient.js
src/router/detailRouteGuard.js
src/composables/useNavigation.js
src/components/common/FkLinkField/FkLinkField.vue  (FK 链接配置)
src/components/common/MetaListPage/MetaListPage.vue (列表页配置)
src/utils/auditLogFormat.js
src/config/menuConfig.js                (菜单配置中"角色管理"/"用户组管理"改名)
```

#### 3.3.5 i18n（2 文件）

```
src/i18n/locales/zh-CN.json (或 index.json)
src/i18n/locales/en-US.json (或 index.json)
```

#### 3.3.6 测试（6 文件）

```
src/views/SystemManagement/__tests__/RolePermissionCenter.spec.js
src/views/SystemManagement/__tests__/RolePermissionCenter.features.spec.js
src/views/SystemManagement/__tests__/RoleDetailDrawer.spec.js
src/views/SystemManagement/__tests__/GroupRoleDialog.spec.js
src/services/__tests__/v2ApiIntegration.spec.js
src/services/__tests__/graphqlClient.spec.js
```

### 3.4 测试用例层（20 文件）

```
meta/tests/test_role_api.py                          → test_permission_set_api.py
meta/tests/test_role_v1_cleanup.py                   → test_permission_set_v1_cleanup.py
meta/tests/test_role_delete_cascade_v061.py          → test_permission_set_delete_cascade_v061.py
meta/tests/test_role_menu_dim_api.py                 → test_permission_set_menu_dim_api.py
meta/tests/api/test_role_permission_apis.py          → test_permission_set_apis.py
meta/tests/test_audit_role_parent_query_e2e.py       (内部角色引用改名)
meta/tests/test_object_adaptation_role.py            (内部角色引用改名)
meta/tests/test_product_version_user_role_export_import.py (内部角色引用改名)
meta/tests/e2e_spec_08_multi_role_exclude.py         (内部角色引用改名)
meta/tests/test_user_group_api.py                    → test_org_api.py
meta/tests/test_user_group_api_extended.py           → test_org_api_extended.py
meta/tests/test_user_group_associate_audit.py        → test_org_associate_audit.py
meta/tests/test_object_adaptation_user_group.py      → test_object_adaptation_org.py
meta/tests/test_user_group_service.py                → test_org_service.py
meta/tests/test_user_group_service_edge.py           → test_org_service_edge.py
meta/tests/test_association_audit_e2e.py             (内部角色引用改名)
meta/tests/test_permission_migration_p44.py          (内部角色引用改名)
meta/tests/test_unified_permission_api.py            (内部角色引用改名)
meta/tests/test_p3_p4_integration.py                 (内部角色引用改名)
meta/tests/test_interceptor_phase2_hook.py           (内部角色引用改名)
```

### 3.5 文档与 i18n（11 文件）

```
docs/superpowers/specs/2026-07-12-role-delete-cascade-design.md (历史归档)
docs/superpowers/plans/2026-07-12-role-delete-cascade.md         (历史归档)
docs/lessons-learned/permission/*.md                             (历史归档)
docs/spec_权限体系升级/13_organization_model_integration.md       (引用更新)
docs/spec_权限体系升级/14_org_management_dimension_and_migration.md (引用更新)
docs/spec_权限体系升级/15_permission_config_unification.md       (引用更新)
# + 新增
docs/superpowers/specs/2026-08-28-role-to-permission-set-org-refactor-design.md (本文件)
docs/superpowers/plans/2026-08-28-role-to-permission-set-org-refactor-plan.md (writing-plans 输出)
```

---

## 4. 迁移步骤（Phase 0 → Phase 6）

### Phase 0 — 准备与快照（不改行为，1d）

- [ ] 全量备份 `meta/architecture.db` → `meta/architecture.db.snapshot_20260828`
- [ ] git tag `pre-permission-set-refactor` 留历史回滚点
- [ ] 创建 Feature Flag `permission_set_refactor_enabled = False`（默认关闭）
- [ ] 创建迁移专用分支（建议 `feat/permission-set-org-refactor`），不在主工作树提交
- [ ] 输出迁移前快照报告（roles 数量 / user_groups 数量 / 外键引用统计）

### Phase 1 — DB schema 迁移（双轨对账关键节点，1d）

**目标**：表改名 + 新增 `org_functions`，旧代码继续读旧表。

- [ ] 新增 migration `2026_08_28_rename_roles_to_permission_sets.py`：
  ```sql
  ALTER TABLE roles RENAME TO permission_sets;
  ALTER TABLE role_permissions RENAME TO permission_set_permissions;
  -- ... (11 张表)
  -- 索引/触发器/约束名同步
  ```
- [ ] 新增 migration `2026_08_28_rename_user_groups_to_orgs.py`：
  ```sql
  ALTER TABLE user_groups RENAME TO orgs;
  ALTER TABLE user_group_members RENAME TO org_members;
  -- ...
  ALTER TABLE orgs ADD COLUMN org_type TEXT DEFAULT 'department';
  ALTER TABLE orgs ADD COLUMN org_scope TEXT DEFAULT 'internal';
  ```
- [ ] 新增 migration `2026_08_28_create_org_functions.py`：建新表
- [ ] 数据回填：现有 `user_groups` 数据迁移时 `org_type` 根据 `code` 启发式归类
  - `personal_group_user_*` → `org_type='personal'`, `is_personal=true`
  - 含 "部门/部/处/科" → `org_type='department'`
  - 含 "组/团队" → `org_type='team'`
  - 其它 → `org_type='team'` (默认)
  - 人工 review 后纠正
- [ ] **双轨对账**：开启只读模式，新旧双读 SQL 一致性校验脚本

### Phase 2 — 后端层迁移（核心风险点，3d）

**目标**：服务/拦截器/DAO 全部读新表，旧 API 路由可临时保留重定向。

- [ ] 拆分 `permission_set_service.py` 与 `role_service.py`：
  - `permission_set_service.py` 已存在 → 合并 `role_service.py` 全部方法
  - 删除 `role_service.py` 重复实现
- [ ] 重命名 `user_group_service.py` → `org_service.py`，新增 `OrgFunctionService`
- [ ] 改 `permission_service.py` / `data_permission_service.py` / `menu_permission_service.py` 内所有 `role_*` / `user_group_*` 引用
- [ ] 改 `action_executor.py` / `derivation_pipeline.py` / `intent_resolver.py` 内所有 SQL 与类名引用
- [ ] 改所有 `interceptor` 的 SQL / 字段引用
- [ ] **Feature Flag 灰度**：开启 `permission_set_refactor_enabled = True` 时使用新表 SQL；关闭时回退旧名 SQL（用 `if FLAG:` 守卫）
- [ ] **双轨对账**：新旧两套 SQL 在同一请求中执行，断言结果一致；不一致时报警并回滚到旧路径

### Phase 3 — API 路由迁移（2d）

**目标**：所有 `/api/v1/roles/*` 与 `/api/v1/user-groups/*` 路由改名。

- [ ] 改 `meta/api/role_api.py` → `permission_set_api.py`，Blueprint 名 + 路由前缀改名
- [ ] 改 `meta/api/user_group_api.py` → `org_api.py`
- [ ] 改 `meta/api/role_menu_api.py` → `permission_set_menu_api.py`
- [ ] 改 `meta/api/role_dimension_scope_api.py` → `permission_set_dimension_scope_api.py`
- [ ] 新增 `meta/api/org_function_api.py`（GET/POST/PUT/DELETE）
- [ ] 改 `meta/server.py` 注册新 Blueprint
- [ ] 旧路由**不保留**重定向（用户决策）——前端一次性切换即可

### Phase 4 — 前端迁移（3d）

**目标**：组件、路由、i18n 全部同步。

- [ ] 改 Vue 组件名 + 文件名（10 文件，git mv 保留历史）
- [ ] 改 router 路径 + 菜单配置（src/router/modules/system.js + src/config/menuConfig.js）
- [ ] 改 `src/services/permissionService.js` 内部 API 路径
- [ ] 改 `src/services/objectTypeService.js` 的 object_type 配置（roles → permission_sets）
- [ ] 改 i18n 文案（2 文件）
- [ ] 改 ObjectPage / FkLinkField / MetaListPage 的配置（FK 引用配置 + 列表页 bo_type）
- [ ] 改测试用例路径与 import（6 文件）
- [ ] **前端双轨对账**：dev 环境旧前端 + 新后端 → 新前端 + 新后端 → 跨浏览器对比 UI

### Phase 5 — 测试与文档同步（2d）

- [ ] 全量回归（meta/tests 150+ 测试 + frontend 测试 30+ 测试）
- [ ] 改测试用例文件名与 import（20 文件）
- [ ] 改 docs 引用（更新 spec 13/14/15 引用旧名处）
- [ ] 新增 `docs/superpowers/specs/2026-08-28-role-to-permission-set-org-refactor-design.md`（本文件）
- [ ] 更新 `docs/lessons-learned/permission/` 历史 lessons 标记 "（pre-refactor）"
- [ ] 更新 README.md 中相关 API 文档

### Phase 6 — 灰度切换与清理（1d）

- [ ] 灰度开关：先开 50% 流量 → 观察 24h → 100%
- [ ] Feature Flag `permission_set_refactor_enabled` 默认值改为 `True`（已硬切换）
- [ ] 清理 Phase 0 快照（保留 7 天后删除）
- [ ] 清理 git tag 软引用
- [ ] 删 `meta/services/role_service.py` / `user_group_service.py`（已被合并/重命名）
- [ ] 输出迁移后报告（权限集/组织数量对比、外键引用一致性）

---

## 5. 回滚预案

### 5.1 双轨对账机制（核心）

- **DB 层**：迁移后保留原表 7 天（rename 后旧表名仍可访问靠 SQLite 的 `sqlite_master` 还原）
- **后端层**：Feature Flag `permission_set_refactor_enabled` 控制新旧两套 SQL 路径，**不一致时报警 + 自动回退到旧路径**
- **前端层**：组件文件名保留 git mv 历史，`git revert` 即可回滚

### 5.2 回滚触发条件

| 触发条件 | 检测方式 | 自动行为 |
|---------|---------|---------|
| 新表数据丢失 / 主键冲突 | DB 双轨对账脚本每 5min 跑一次 | 报警 + 自动禁用 FF |
| API 5xx 错误率 > 1% | 监控面板 | 报警 + 人工决定 |
| 关键 e2e 测试失败 | CI 流水线 | 阻断合并 |
| 用户反馈"看不到角色"等 | 客服渠道 | 紧急 FF 切换 |

### 5.3 回滚步骤

```
1. Feature Flag: permission_set_refactor_enabled = False (1 次 DB UPDATE)
2. 重启 backend (新代码读旧表 SQL)
3. 前端: git revert commit_id (回滚到旧组件)
4. DB: 7 天内可执行 reverse migration (rename 回原名)
5. 7 天后: 从 snapshot_20260828 还原
```

### 5.4 不可回滚点

- Phase 1 的 SQL rename 执行后，如果超过 7 天，snapshot 是唯一回滚手段
- 因此 Phase 0 的 snapshot 必须保留至少 14 天（2 倍回滚窗口）

---

## 6. Feature Flag 设计

### 6.1 标志位定义

```python
# meta/services/permission_flags.py
PERMISSION_FLAGS = {
    # ... 现有 flags
    'permission_set_refactor_enabled': False,  # Phase 2 启用新表 SQL 读取
    'permission_set_refactor_write_enabled': False,  # Phase 2 启用新表 SQL 写入
    'org_function_panel_enabled': False,  # Phase 4 启用 org_function 多职能视图 UI
}
```

### 6.2 灰度策略

| 阶段 | `permission_set_refactor_enabled` | `permission_set_refactor_write_enabled` | 验证项 |
|------|:--:|:--:|------|
| Phase 1 完成 | `False` | `False` | DB rename 成功 |
| Phase 2 开始 | `True` (读) | `False` (写) | 读路径双轨对账通过 |
| Phase 2 中期 | `True` | `True` (灰度 50%) | 写路径双轨对账通过 |
| Phase 4 完成 | `True` | `True` | 前端 e2e 通过 |
| Phase 6 完成 | `True` (默认) | `True` (默认) | 全量回归通过 |

### 6.3 Feature Flag 监控

- 在 `meta/services/structured_logger.py` 中记录 FF 切换事件
- 在 `meta/api/stats_api.py` 增加 `/api/v1/admin/flag-status` 端点供运维查询

---

## 7. 风险与决策记录

| # | 风险/决策 | 应对 |
|---|-----------|------|
| 1 | 130+ 文件一次性改完风险高 | 双轨对账 + FF 灰度 + Phase 0 全量快照 |
| 2 | `role_effective_intents` 等 SQL 跨多表 join 改名连锁多 | Phase 2 单元测试覆盖每个 join SQL；FF 双轨对账 |
| 3 | `personal_group_user_*` 命名迁移后含义不清 | 启发式归 `org_type='personal'`；迁移报告人工 review |
| 4 | org_function 数据回填可能误分类 | Phase 1 数据回填后必须人工 review + 修正 |
| 5 | 前端菜单路径硬编码多处 | Phase 4 用 i18n + 菜单配置统一入口 |
| 6 | 旧 e2e 测试可能依赖旧的 mock 角色数据 | Phase 5 同步更新 fixture |
| 7 | spec 13/14/15 文档中大量旧名引用 | Phase 5 文档同步（11 个文件） |
| 8 | 用户历史操作日志含旧名 | 审计日志不改名（保留历史），新增字段标识新旧 |
| 9 | 部署脚本 deploy-v*.zip 引用旧 API 路径 | 部署脚本同步更新 |
| 10 | 第三方集成（如有）依赖旧 API | Phase 3 前通知；无第三方依赖（项目自检） |

---

## 8. 验证清单

执行完成后必须全部 ✅：

- [ ] `git grep -n "user_group\|role_api\|group_role\|/api/v1/roles\|/api/v1/user_groups"` 返回 0 行（仅历史归档文件例外）
- [ ] DB 中 11 张旧表全部重命名为新名
- [ ] DB 中 `org_functions` 表存在且有索引
- [ ] `python d:\filework\test.py --file tests/integration/test_permission_dimension_meta_matrix.py` 通过
- [ ] `python d:\filework\test.py --file tests/integration/test_permission_dimension_meta_scope.py` 通过
- [ ] `python d:\filework\test.py --file tests/integration/test_permission_matrix_association_derive.py` 通过
- [ ] meta/tests/ 全量回归通过
- [ ] src/views/SystemManagement/__tests__/ 全量通过
- [ ] 浏览器手动验证：登录 → 权限配置 → 角色管理（旧 UI）/权限集管理（新 UI）→ 菜单权限、数据权限、维度范围 CRUD 正常
- [ ] 浏览器手动验证：用户组管理 → 组织管理 → 创建部门 → 创建子部门 → 添加成员 → 绑定权限集 → 删除级联正常
- [ ] 浏览器手动验证：新增 `org_function` 多职能视图 UI 可见
- [ ] i18n 切换中英文无遗漏的旧名残留
- [ ] 后端日志无 SQL 错误（rename 后 24h）
- [ ] 监控面板无 5xx 异常（rename 后 24h）

---

## 9. 时间估算

| Phase | 任务 | 估时 |
|-------|------|-----|
| 0 | 准备与快照 | 1d |
| 1 | DB schema 迁移 | 1d |
| 2 | 后端层迁移 | 3d |
| 3 | API 路由迁移 | 2d |
| 4 | 前端迁移 | 3d |
| 5 | 测试与文档同步 | 2d |
| 6 | 灰度切换与清理 | 1d |
| **合计** | | **13d ≈ 2.5 周** |

---

## 10. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|---------|
| 2026-08-28 | AI Assistant | 创建：角色→权限集 + 用户组→组织 重命名迁移设计稿。本稿仅文档，未动代码。基于用户决策：仅准备文档；权限集=表名重命名；组织=狭义+中层；纯重命名 + 全面升级；4 件交付物（映射表/影响面/迁移步骤/回滚-FF）。 |

---

## 11. 下一步

1. **用户审阅本设计稿**：审阅概念映射、影响面、迁移步骤、回滚预案是否完备
2. **审阅通过后**：由 `writing-plans` skill 输出分阶段可执行实施计划（含每个 Phase 的精确步骤、验收测试、回滚检查点）
3. **实施阶段**：建议在独立 worktree 分批提交，每 Phase 一个或多个 commit，按 Phase 边界做 tag 标记以便回滚
