## 目录

1. [1. Background & Objectives](#1-background-objectives)
2. [2. Requirement Type Overview](#2-requirement-type-overview)
3. [3. Functional Requirements](#3-functional-requirements)
4. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
5. [5. External Interface Requirements](#5-external-interface-requirements)
6. [6. Transition Requirements](#6-transition-requirements)
7. [7. Constraints & Assumptions](#7-constraints-assumptions)
8. [8. Priorities & Milestone Suggestions](#8-priorities-milestone-suggestions)
9. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
10. [10. TBD List](#10-tbd-list)
11. [11. 实施状态追踪（2026-05-19 更新）](#11-实施状态追踪（2026-05-19-更新）)

---
# Spec: 元数据驱动平台 Hardcode 风险消除

## 1. Background & Objectives

### 1.1 Background

平台已构建元数据驱动的企业应用核心架构，实现 YAML 单一事实语义，包括 BOF、API 服务、权限体系、菜单体系、动态 UI 组件、Log 等模块。然而，经全面审计发现，多个关键路径仍存在 hardcode，破坏了"YAML 单一事实语义"原则：

- **Admin 角色判断**：前后端至少 8 个文件硬编码 `"admin"` 字符串
- **权限级别枚举**：`PERMISSION_LEVELS` 中 `value: 'admin'` 在 4 处独立定义
- **菜单排除集合**：`menu_auto_generator.py` 硬编码 9 个跳过对象
- **Fallback 导航**：`AppRootLayout.vue` 硬编码完整导航结构
- **层级配置 Fallback**：`hierarchyFilterBuilder.js` 硬编码层级配置
- **废弃组件残留**：
  - `EditForm.vue`（无生产引用）
  - `DomainManagement.vue` 等 4 个 SystemManagement 组件（已被 GenericObjectList 替代）
  - `ArchDataManageApp` 整目录（已被 RelationshipManagement 替代，路由已标记 legacy）

### 1.2 Business Objectives

- **BO-001**: 实现"YAML 单一事实源"——所有业务逻辑判断均从 YAML 元数据推导
- **BO-002**: 降低维护成本——新增业务对象或修改权限模型时，仅需修改 YAML
- **BO-003**: 提升系统一致性——前后端配置自动同步，消除人工同步风险

### 1.3 User / Stakeholder Objectives

- **平台开发者**：新增业务对象时无需修改代码，仅编辑 YAML 即可上线
- **系统管理员**：角色/权限模型变更时无需发版，仅修改配置即可生效
- **运维人员**：API 不可用时系统优雅降级，用户仍可使用基础功能

## 2. Requirement Type Overview

| Type               | Applicable | Evidence (Source)      |
| ------------------ | ---------- | ---------------------- |
| Business           | Yes        | BO-001, BO-002, BO-003 |
| User/Stakeholder   | Yes        | 开发者、管理员、运维需求           |
| Solution           | Yes        | YAML schema 扩展、缓存机制    |
| Functional         | Yes        | FR-001 \~ FR-010       |
| Nonfunctional      | Yes        | NFR-001 \~ NFR-003     |
| External Interface | Yes        | IF-001 \~ IF-003       |
| Transition         | Yes        | TR-001 \~ TR-004       |

## 3. Functional Requirements

### FR-001: Admin 角色判断元数据化

- **Description**: 系统必须从 YAML role schema 中读取超级管理员角色标识，而非硬编码 `"admin"` 字符串。
- **Acceptance Criteria**:
  - AC-001-1: `role.yaml` 新增 `is_super_admin: boolean` 字段，默认 `false`
  - AC-001-2: 后端 `is_admin()` 函数从数据库查询 `is_super_admin=true` 的角色，而非检查 `code='admin'`
  - AC-001-3: 前端 `authStore.isAdmin` 从后端 API 返回的 `is_super_admin` 字段判断
  - AC-001-4: 现有 `admin` 角色数据迁移时自动设置 `is_super_admin=true`
- **Priority**: Must
- **Type Mapping**: Functional, Solution
- **Source**: 代码审计 H1, H2

### FR-002: 权限级别枚举统一化

- **Description**: `PERMISSION_LEVELS` 枚举必须统一定义在单一位置，所有使用处引用同一常量。
- **Acceptance Criteria**:
  - AC-002-1: `src/constants/permissionLevels.js` 作为唯一权威定义源
  - AC-002-2: `ConditionRuleEditor/types.js` 从上述文件导出
  - AC-002-3: `ConditionRuleEditor.vue`、`ConditionRuleDialog.vue`、`BatchDataPermDialog.vue` 引用统一常量
  - AC-002-4: 枚举值（read/write/admin）与后端 `permission_rule` 表的 `permission_level` 字段一致
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码审计 H2 相关

### FR-003: 菜单排除集合元数据化

- **Description**: 菜单自动生成时跳过的业务对象列表必须从 YAML 元数据读取。
- **Acceptance Criteria**:
  - AC-003-1: 各业务对象 YAML schema 的 `ui_view_config` 中新增 `skip_auto_menu: boolean` 字段
  - AC-003-2: `menu_auto_generator.py` 从 YAML loader 读取 `skip_auto_menu=true` 的对象列表
  - AC-003-3: 删除 `menu_auto_generator.py` 中的硬编码 `skip` 集合
  - AC-003-4: 现有跳过对象（`user_role`, `role_permission` 等）在 YAML 中标记 `skip_auto_menu: true`
- **Priority**: Must
- **Type Mapping**: Functional, Solution
- **Source**: 代码审计 H7

### FR-004: Fallback 导航缓存化

- **Description**: 当菜单 API 不可用时，系统必须从 localStorage 缓存恢复上次成功加载的菜单，而非使用硬编码 fallback。
- **Acceptance Criteria**:
  - AC-004-1: 菜单 API 成功响应时，自动存储到 `localStorage.menuCache`（含 timestamp）
  - AC-004-2: API 失败时，优先从缓存恢复，显示"(离线模式)"标识
  - AC-004-3: 缓存超过 24 小时或不存在时，显示"无法加载菜单，请刷新重试"提示
  - AC-004-4: 删除 `AppRootLayout.vue` 中的 `fallbackNavigationItems` 硬编码数组
- **Priority**: Must
- **Type Mapping**: Functional, Solution
- **Source**: 代码审计 H4，参考 Salesforce SmartStore、SaaS 缓存最佳实践

### FR-005: 层级配置 Fallback 缓存化

- **Description**: 当层级配置 API 不可用时，系统必须从 localStorage 缓存恢复，而非使用硬编码 fallback。
- **Acceptance Criteria**:
  - AC-005-1: 层级配置 API 成功响应时，存储到 `localStorage.hierarchyConfigCache`
  - AC-005-2: API 失败时优先从缓存恢复
  - AC-005-3: 删除 `hierarchyFilterBuilder.js` 中的 `getFallbackConfig()` 硬编码
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码审计 H11

### FR-006: 删除废弃组件 EditForm.vue

- **Description**: `EditForm.vue` 已被 `DynamicForm.vue`（元数据驱动）替代，仅被测试文件引用，应删除。
- **Acceptance Criteria**:
  - AC-006-1: 删除 `src/views/ArchDataManageApp/components/EditForm.vue`
  - AC-006-2: 删除测试文件 `src/views/ArchDataManageApp/__tests__/EditForm.spec.js`
  - AC-006-3: 确认 `DynamicForm.vue` 已完全覆盖所有对象类型的表单编辑功能
- **Priority**: Must
- **Type Mapping**: Functional, Transition
- **Source**: 代码审计确认 EditForm.vue 无生产代码引用

### FR-007: DynamicForm 层级只读字段元数据化

- **Description**: `DynamicForm.vue` 中的层级只读字段判断应从 YAML hierarchy 配置推导（如有硬编码）。
- **Acceptance Criteria**:
  - AC-007-1: 检查 `DynamicForm.vue` 中是否存在层级只读字段的硬编码判断
  - AC-007-2: 如存在，改为从 `/api/v1/meta/hierarchies/config` 获取层级关系配置
  - AC-007-3: 根据 `hierarchy.parent_key` 字段语义自动推导只读字段
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码审计 H9，需验证 DynamicForm.vue 是否有此问题

### FR-008: 删除废弃组件

- **Description**: 已被 `GenericObjectList.vue` 或 `DynamicForm.vue` 替代的组件及其路由必须删除。
- **Acceptance Criteria**:
  - AC-008-1: 删除 `src/views/SystemManagement/DomainManagement.vue`
  - AC-008-2: 删除 `src/views/SystemManagement/SubDomainManagement.vue`
  - AC-008-3: 删除 `src/views/SystemManagement/ServiceModuleManagement.vue`
  - AC-008-4: 删除 `src/views/SystemManagement/BusinessObjectManagement.vue`
  - AC-008-5: 删除 `router/index.js` 中对应的路由定义（第 166-185 行）
  - AC-008-6: 删除对应的测试文件（`__tests__/` 目录下）
- **Priority**: Must
- **Type Mapping**: Functional, Transition
- **Source**: 用户确认

### FR-009: 删除废弃应用 ArchDataManageApp

- **Description**: `ArchDataManageApp` 已被 `RelationshipManagement.vue` 替代，路由已标记为 `archdata-legacy`，应删除整个目录。
- **Acceptance Criteria**:
  - AC-009-1: 迁移 `AnnotationList.vue` 到 `src/components/common/AnnotationList/`
  - AC-009-2: 迁移 `hierarchyFilterBuilder.js` 到 `src/utils/hierarchyFilterBuilder.js`
  - AC-009-3: 更新 `ObjectPage.vue` 和 `archDataConverter.js` 的引用路径
  - AC-009-4: 删除 `/system/archdata-legacy` 路由定义
  - AC-009-5: 删除整个 `src/views/ArchDataManageApp/` 目录（含 18 个组件、5 个 composables、1 个 store、1 个 utils、24 个测试文件）
- **Priority**: Must
- **Type Mapping**: Functional, Transition
- **Source**: 用户确认，路由已标记 legacy

### FR-010: Page Type 路由映射元数据化

- **Description**: `page_type` 到路由 path 的映射规则必须从 YAML menu schema 推导。
- **Acceptance Criteria**:
  - AC-010-1: `deriveRoutePath()` 函数从 `menu.page_type` 和 `menu.page_config.route_template` 推导
  - AC-010-2: YAML menu schema 新增 `route_template` 可选字段，如 `/objects/{primary_object_type}`
  - AC-010-3: 删除 `AppRootLayout.vue` 中的 `switch (menu.page_type)` 硬编码
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 代码审计 H5

## 4. Nonfunctional Requirements

### NFR-001: 性能 — 缓存命中率

- **Description**: 菜单和层级配置的 localStorage 缓存命中率必须 ≥ 95%（正常网络条件下）。
- **Measurement**: 监控 `menuCache.hit` / `menuCache.total` 比率，通过埋点统计
- **Priority**: Should
- **Source**: SaaS 缓存最佳实践

### NFR-002: 可观测性 — Fallback 事件监控

- **Description**: 所有 fallback 降级事件必须记录日志并支持监控告警。
- **Measurement**:
  - 每次从缓存恢复时记录 `info` 级别日志：`menu_loaded_from_cache`
  - 缓存过期或不存在时记录 `warn` 级别日志：`menu_cache_miss`
  - 监控面板展示 fallback 事件趋势
- **Priority**: Should
- **Source**: Resilience Engineering 最佳实践

### NFR-003: 兼容性 — 向后兼容

- **Description**: 新增 YAML 字段（`is_super_admin`, `skip_auto_menu`, `route_template`）必须向后兼容，缺失时使用合理默认值。
- **Measurement**:
  - `is_super_admin` 缺失时默认 `false`
  - `skip_auto_menu` 缺失时默认 `false`
  - `route_template` 缺失时使用现有 `deriveRoutePath` 逻辑作为默认
- **Priority**: Must
- **Source**: YAML schema 演进原则

## 5. External Interface Requirements

### IF-001: 超级管理员角色 API

- **Type**: API
- **Endpoint**: `GET /api/v1/roles?is_super_admin=true`
- **Request/Response**:

```json
{
  "data": [
    { "id": 1, "code": "admin", "name": "管理员", "is_super_admin": true }
  ]
}
```

- **Error Handling**: 500 错误时，前端从 `authStore.user.roles` 中检查 `is_super_admin` 字段（登录时已获取）
- **Source**: FR-001

### IF-002: 表单配置 API

- **Type**: API
- **Endpoint**: `GET /api/v1/meta/forms/{object_type}`
- **Request/Response**:

```json
{
  "object_type": "product",
  "form": {
    "title": "产品信息",
    "layout": "vertical",
    "groups": [...],
    "fields": { ... }
  }
}
```

- **Error Handling**: 404 时使用 `ui_view_config.form` 作为 fallback
- **Source**: FR-006

### IF-003: localStorage 缓存结构

- **Type**: UI Storage
- **Entry**:
  - `localStorage.menuCache`: `{ data: Menu[], timestamp: number, version: string }`
  - `localStorage.hierarchyConfigCache`: `{ data: HierarchyConfig, timestamp: number }`
- **TTL**: 24 小时
- **Source**: FR-004, FR-005

## 6. Transition Requirements

### TR-001: 数据迁移 — Admin 角色标记

- **Description**: 现有 `admin` 角色需要设置 `is_super_admin=true`
- **Strategy**:
  1. 部署新 YAML schema（含 `is_super_admin` 字段）
  2. 执行迁移脚本：`UPDATE roles SET is_super_admin = true WHERE code = 'admin'`
  3. 部署新代码
- **Rollback Plan**: 回滚代码后，`is_super_admin` 字段被忽略，恢复硬编码判断
- **Source**: FR-001

### TR-002: 数据迁移 — Skip Auto Menu 标记

- **Description**: 现有跳过对象需要在 YAML 中标记
- **Strategy**:
  1. 在以下 YAML schema 的 `ui_view_config` 中添加 `skip_auto_menu: true`：
     - `user_role.yaml`, `role_permission.yaml`, `role_menu_permissions.yaml`
     - `role_data_permissions.yaml`, `group_data_permission.yaml`, `user_group_member.yaml`
     - `business_object.yaml`, `version.yaml`, `_template.yaml`
  2. 部署 YAML 更新
  3. 部署新代码（删除硬编码 `skip` 集合）
- **Rollback Plan**: 回滚代码后，硬编码 `skip` 集合恢复生效
- **Source**: FR-003

### TR-003: 废弃组件删除

- **Description**: 删除四个废弃组件及相关文件
- **Strategy**: 
  1. 确认 `GenericObjectList.vue` 已完全覆盖功能
  2. 删除组件文件、路由定义、测试文件
  3. 执行 E2E 测试验证路由跳转正常
- **Rollback Plan**: Git revert 删除的文件
- **Source**: FR-008

### TR-004: 废弃应用 ArchDataManageApp 删除

- **Description**: 删除整个 ArchDataManageApp 目录及相关路由
- **Strategy**: 
  1. 迁移外部依赖的组件：
     - `AnnotationList.vue` → `src/components/common/AnnotationList/`
     - `hierarchyFilterBuilder.js` → `src/utils/hierarchyFilterBuilder.js`
  2. 更新引用路径：
     - `ObjectPage.vue` 更新 AnnotationList 引用
     - `archDataConverter.js` 更新 hierarchyFilterBuilder 引用
  3. 删除 `/system/archdata-legacy` 路由
  4. 删除整个 `src/views/ArchDataManageApp/` 目录
  5. 执行 E2E 测试验证：
     - `/system/archdata` 正常工作
     - ObjectPage 的 AnnotationList 功能正常
- **Rollback Plan**: Git revert 删除的文件和目录
- **Source**: FR-009

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- **TC-001**: localStorage 存储限制约 5MB，菜单和层级配置数据量 < 100KB，满足约束
- **TC-002**: BO 框架 API 已稳定，可替代 `EditForm.vue` 中的硬编码表单定义（用户确认）
- **TC-003**: 现有数据库支持 `is_super_admin` 字段新增（SQLite/PostgreSQL 均支持）

### 7.2 Business Constraints

- **BC-001**: Admin 角色判断逻辑变更需通知所有租户（如有 SaaS 多租户场景）
- **BC-002**: 废弃组件删除需确认无外部系统直接引用对应 URL

### 7.3 Assumptions

- **A-001**: 用户登录时获取的角色信息包含 `is_super_admin` 字段 — Source: 待验证
- **A-002**: 现有测试覆盖废弃组件删除后的路由跳转 — Source: 待验证

## 8. Priorities & Milestone Suggestions

| ID     | Requirement        | Priority | Reason        |
| ------ | ------------------ | -------- | ------------- |
| FR-001 | Admin 角色判断元数据化     | Must     | 核心权限逻辑，影响安全   |
| FR-002 | 权限级别枚举统一化          | Must     | 数据一致性风险       |
| FR-003 | 菜单排除集合元数据化         | Must     | 新增对象时易遗漏      |
| FR-004 | Fallback 导航缓存化     | Must     | 用户体验关键路径      |
| FR-005 | 层级配置 Fallback 缓存化  | Must     | 与 FR-004 一致   |
| FR-006 | 删除废弃组件 EditForm.vue | Must     | 代码清理，无生产引用     |
| FR-007 | DynamicForm 层级只读字段元数据化 | Should   | 需先验证是否有此问题   |
| FR-008 | 删除废弃组件（SystemManagement） | Must     | 代码清理，用户确认     |
| FR-009 | 删除废弃应用 ArchDataManageApp | Must     | 代码清理，路由已标记 legacy |
| FR-010 | Page Type 路由映射元数据化 | Should   | 新增页面类型时才需修改   |

- **Suggested Milestones**:
  - **Milestone 1 (Week 1)**: FR-001, FR-002, FR-003 — YAML schema 扩展 + 数据迁移
  - **Milestone 2 (Week 2)**: FR-004, FR-005, FR-010 — Fallback 机制重构
  - **Milestone 3 (Week 3)**: FR-006, FR-007, FR-008, FR-009 — 废弃组件/应用清理
  - **Milestone 4 (Week 4)**: NFR-001, NFR-002 — 监控 + 验证

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:
  - Admin 判断：前后端各自硬编码 `"admin"` 字符串比较
  - 菜单 Fallback：硬编码 `fallbackNavigationItems` 数组
  - 层级配置 Fallback：硬编码 `getFallbackConfig()` 函数
  - 废弃组件残留：`EditForm.vue`、`DomainManagement.vue` 等 5 个组件未删除
  - 废弃应用残留：`ArchDataManageApp` 整个目录（18 组件 + 5 composables + 1 store + 24 测试）

- **Current Issues**:
  1. 新增业务对象需同时修改 YAML + 多处代码
  2. Admin 角色重命名需修改 8+ 文件
  3. Fallback 导航与实际菜单不同步风险
  4. 废弃组件/应用残留导致代码膨胀和维护混乱

- **Relevant Code Paths**:
  - `meta/services/auth_middleware.py:L127-L131` — `is_admin()` 函数
  - `src/stores/authStore.js:L21-L26` — `isAdmin` computed
  - `meta/services/menu_auto_generator.py:L87-L92` — `skip` 集合
  - `src/components/common/AppRootLayout.vue:L90-L99` — `fallbackNavigationItems`
  - `src/views/ArchDataManageApp/utils/hierarchyFilterBuilder.js:L32-L65` — `getFallbackConfig()`
  - `src/views/ArchDataManageApp/` — 整个废弃应用目录
  - `src/views/SystemManagement/DomainManagement.vue` 等 4 个 — 废弃组件

### 9.2 Target State

- **Proposed Architecture**:
  ```
  YAML Schema (单一事实源)
       │
       ▼
  ┌─────────────────────────────────────┐
  │  Backend: YAML Loader + BO Framework │
  │  - is_super_admin from role.yaml     │
  │  - skip_auto_menu from each BO yaml  │
  │  - form config from ui_view_config   │
  └─────────────────────────────────────┘
       │
       ▼
  ┌─────────────────────────────────────┐
  │  Frontend: API + Cache Layer         │
  │  - Fetch from /api/v1/meta/*         │
  │  - Cache to localStorage             │
  │  - Fallback: cache → error UI        │
  └─────────────────────────────────────┘
  ```
- **Key Changes**:
  1. `role.yaml` 新增 `is_super_admin` 字段
  2. 各 BO YAML 新增 `ui_view_config.skip_auto_menu` 字段
  3. `menu.yaml` 新增 `route_template` 可选字段
  4. 前端新增 `useMetaCache` composable 统一缓存逻辑
  5. 删除 4 个废弃组件 + 硬编码 fallback 数组

### 9.3 Detailed Design

#### 9.3.1 Module/Component Design

**Backend Changes**:

| Module                   | Change | Description                               |
| ------------------------ | ------ | ----------------------------------------- |
| `role.yaml`              | 新增字段   | `is_super_admin: boolean` 字段，默认 `false`   |
| `auth_middleware.py`     | 重构     | `is_admin()` 查询 `is_super_admin=true` 的角色 |
| `menu_auto_generator.py` | 重构     | 从 YAML loader 读取 `skip_auto_menu` 列表      |
| `bo_*.yaml`              | 新增字段   | `ui_view_config.skip_auto_menu: true`     |

**Frontend Changes**:

| Module                | Change | Description                                  |
| --------------------- | ------ | -------------------------------------------- |
| `authStore.js`        | 重构     | `isAdmin` 从 `user.roles[].is_super_admin` 判断 |
| `useMetaCache.js`     | 新增     | 统一的 localStorage 缓存 composable               |
| `AppRootLayout.vue`   | 重构     | 删除 `fallbackNavigationItems`，使用缓存            |
| `hierarchyFilterBuilder.js` | 重构     | 删除 `getFallbackConfig()`，使用缓存                |
| `permissionLevels.js` | 新增     | 权限级别枚举唯一权威定义                                 |
| `EditForm.vue`        | 删除     | 废弃组件，无生产引用                                    |
| `DomainManagement.vue` 等 4 个 | 删除     | 废弃组件，已被 GenericObjectList 替代                  |
| `ArchDataManageApp/` 整目录 | 删除     | 废弃应用，已被 RelationshipManagement 替代             |
| `AnnotationList.vue`  | 迁移     | 迁移到 `src/components/common/AnnotationList/`    |
| `hierarchyFilterBuilder.js` | 迁移     | 迁移到 `src/utils/`（保留功能供 archDataConverter 使用）  |

#### 9.3.2 Data Model

**role 表新增字段**:

```sql
ALTER TABLE roles ADD COLUMN is_super_admin BOOLEAN DEFAULT FALSE;
UPDATE roles SET is_super_admin = TRUE WHERE code = 'admin';
```

**localStorage 缓存结构**:

```typescript
interface MenuCache {
  data: MenuItem[];
  timestamp: number;  // Unix timestamp
  version: string;    // Schema version for invalidation
}

interface HierarchyConfigCache {
  data: HierarchyConfig;
  timestamp: number;
}
```

#### 9.3.3 API Design

| Endpoint                            | Method | Description       |
| ----------------------------------- | ------ | ----------------- |
| `/api/v1/roles?is_super_admin=true` | GET    | 获取超级管理员角色列表       |
| `/api/v1/meta/forms/{object_type}`  | GET    | 获取对象表单配置          |
| `/api/v1/meta/hierarchies/config`   | GET    | 获取层级配置（已有）        |
| `/api/v1/menu-permission/visible`   | GET    | 获取可见菜单（已有，需增加缓存头） |

#### 9.3.4 Main Flows

**Admin 判断流程（改造后）**:

```
用户登录 → 获取用户角色列表（含 is_super_admin 字段）
         → authStore.isAdmin = roles.some(r => r.is_super_admin)
         → 后端 is_admin() 查询数据库 is_super_admin=true 的角色
```

**菜单加载流程（改造后）**:

```
AppRootLayout mounted
    │
    ├─► API: /api/v1/menu-permission/visible
    │       │
    │       ├─► 成功 → 存储到 localStorage.menuCache → 渲染菜单
    │       │
    │       └─► 失败 → 检查 localStorage.menuCache
    │                   │
    │                   ├─► 存在且 < 24h → 渲染缓存 + 显示"(离线模式)"
    │                   │
    │                   └─► 不存在或过期 → 显示"无法加载菜单，请刷新重试"
```

### 9.4 Alternatives Considered

| Option                                             | Pros                 | Cons              | Decision     |
| -------------------------------------------------- | -------------------- | ----------------- | ------------ |
| **A: role.yaml 新增 is\_super\_admin 字段**            | 语义清晰，符合 YAML 单一事实源原则 | 需数据迁移             | **Selected** |
| B: system\_config.yaml 定义 super\_admin\_role\_code | 配置集中                 | 与角色实体分离，查询效率低     | Rejected     |
| C: 通过权限 `*` 判断超级管理员                                | 无需新增字段               | 语义模糊，`*` 可能用于其他场景 | Rejected     |
| **D: localStorage 缓存 + 过期提示**                      | 用户体验好，符合 SaaS 最佳实践   | 需管理缓存一致性          | **Selected** |
| E: 完全删除 fallback，API 失败即空白                         | 实现简单                 | 用户体验差             | Rejected     |
| F: 构建时从 YAML 生成静态 fallback JSON                    | 无运行时依赖               | 需重新构建才能更新         | Rejected     |

### 9.5 Implementation & Migration Plan

#### Implementation Order

1. **Phase 1: YAML Schema 扩展** (Day 1-2)
   - 更新 `role.yaml` 新增 `is_super_admin` 字段
   - 更新各 BO YAML 新增 `skip_auto_menu` 字段
   - 执行数据库迁移脚本

2. **Phase 2: 后端重构** (Day 3-4)
   - 重构 `auth_middleware.py` 的 `is_admin()` 函数
   - 重构 `menu_auto_generator.py` 的 skip 逻辑
   - 新增 `/api/v1/roles?is_super_admin=true` 查询支持

3. **Phase 3: 前端重构 — 权限** (Day 5-6)
   - 创建 `src/constants/permissionLevels.js`
   - 重构 `authStore.js` 的 `isAdmin`
   - 更新所有权限级别引用点

4. **Phase 4: 前端重构 — 缓存** (Day 7-8)
   - 创建 `useMetaCache.js` composable
   - 重构 `AppRootLayout.vue` 菜单加载逻辑
   - 重构 `hierarchyFilterBuilder.js`

5. **Phase 5: 清理废弃组件/应用** (Day 9-12)
   - 迁移 `AnnotationList.vue` 到公共组件目录
   - 迁移 `hierarchyFilterBuilder.js` 到公共 utils 目录
   - 删除 `EditForm.vue` 及其测试文件
   - 删除 4 个 SystemManagement 废弃组件及路由
   - 删除整个 `ArchDataManageApp` 目录及路由
   - 删除 `menuConfig.js`（已标记 @deprecated）
   - 执行全量测试

#### Risk Mitigation

| Risk                 | Mitigation                               |
| -------------------- | ---------------------------------------- |
| Admin 判断逻辑变更导致权限绕过   | 1. 先在测试环境验证 2. 灰度发布 3. 增加权限审计日志          |
| 缓存数据与服务器不一致          | 1. 缓存带版本号 2. 菜单变更时主动清除缓存 3. 显示"(离线模式)"提示 |
| 废弃组件删除后路由 404        | 1. 检查所有路由引用 2. E2E 测试验证                  |
| DynamicForm 未覆盖所有表单场景 | 1. 先验证 DynamicForm 功能完整性 2. E2E 测试覆盖所有对象类型 |
| ArchDataManageApp 删除后外部引用失效 | 1. 先迁移 AnnotationList 和 hierarchyFilterBuilder 2. 更新所有引用路径 3. E2E 测试验证 ObjectPage 功能 |

#### Testing Strategy

- **Unit Tests**:
  - `is_admin()` 函数测试：mock 不同角色数据
  - `useMetaCache` composable 测试：缓存存取、过期判断
  - `permissionLevels` 常量测试：与后端枚举一致性
- **Integration Tests**:
  - 菜单 API 失败 → 缓存恢复流程
  - Admin 用户登录 → 权限判断流程
  - 新增 BO（YAML only）→ 菜单自动生成流程
- **E2E Tests**:
  - 用户登录 → 菜单渲染 → 页面跳转
  - API 不可用 → 离线模式 → 恢复在线
  - 所有对象类型的表单创建/编辑

#### Rollback Plan

1. **代码回滚**: Git revert 对应 commit
2. **数据回滚**: `ALTER TABLE roles DROP COLUMN is_super_admin`（如需）
3. **缓存清理**: 清除 localStorage 中的缓存数据
4. **验证**: 执行回归测试确认功能正常

## 10. TBD List

| ID    | Item                                     | Missing Information           | Next Step                           |
| ----- | ---------------------------------------- | ----------------------------- | ----------------------------------- |
| TBD-1 | 验证 A-001：登录 API 是否返回 `is_super_admin` 字段 | 需检查 `/api/v1/auth/login` 响应结构 | 检查 `auth_api.py` 登录响应               |
| TBD-2 | 验证 A-002：现有测试是否覆盖废弃组件删除后的路由              | 需检查 E2E 测试覆盖范围                | 检查 `tests/e2e/` 目录                  |
| TBD-3 | 确认 BC-002：是否有外部系统直接引用废弃组件 URL            | 需运维确认访问日志                     | 检查 Nginx/API Gateway 日志             |
| TBD-4 | 缓存版本号策略：如何定义 `menuCache.version`         | 需确定版本号来源                      | 建议：使用 YAML schema 的 git commit hash |
| TBD-5 | 确认 RelationshipManagement.vue 功能完整性    | 是否完全覆盖 ArchDataManageApp 功能   | E2E 测试对比两个页面功能                      |

---

## 11. 实施状态追踪（2026-05-19 更新）

### 11.1 功能需求状态

| ID | 需求 | 优先级 | 状态 | 完成日期 | 实施文件 |
|----|------|--------|------|----------|---------|
| FR-001 | Admin 角色判断元数据化 | Must | ✅ 已完成 | 2026-05-19 | role.yaml + auth_middleware.py |
| FR-002 | 权限级别枚举统一化 | Must | ✅ 已完成 | 2026-05-19 | src/constants/permissionLevels.js |
| FR-003 | 菜单排除集合元数据化 | Must | ✅ 已完成 | 2026-05-19 | 各 BO yaml (skip_auto_menu) |
| FR-004 | Fallback 导航缓存化 | Must | ✅ 已完成 | 2026-05-19 | useMetaCache.js + AppRootLayout.vue |
| FR-005 | 层级配置 Fallback 缓存化 | Must | ✅ 已完成 | 2026-05-19 | hierarchyFilterBuilder.js 重构 |
| FR-006 | 删除废弃组件 EditForm.vue | Must | 🚧 进行中 | - | - |
| FR-007 | DynamicForm 层级只读字段元数据化 | Should | 🚧 进行中 | - | - |
| FR-008 | 删除废弃组件（DomainManagement.vue 等） | Must | 🚧 进行中 | - | - |
| FR-009 | 删除废弃应用 ArchDataManageApp | Must | 🚧 进行中 | - | - |
| FR-010 | Page Type 路由映射元数据化 | Should | ✅ 已完成 | 2026-05-19 | dynamicRoutes.js |

**总体进度**: 50% (5/10) | **待完成**: FR-006 ~ FR-009

### 11.2 Phase 21 增强需求状态

| ID | 需求 | 状态 | 完成日期 | 实施文件 |
|----|------|------|----------|---------|
| FR-011 | BO YAML authorization 增强 | ✅ 已完成 | 2026-05-19 | 7个BO yaml 添加 auto_owner/auto_permission |
| FR-012 | OwnerTransferService | ✅ 已完成 | 2026-05-19 | owner_transfer_service.py |
| FR-013 | Owner 转移 API | ✅ 已完成 | 2026-05-19 | owner_transfer_api.py (4端点) |
| FR-014 | 动态路由生成 | ✅ 已完成 | 2026-05-19 | dynamicRoutes.js |
| FR-015 | DataPermissionGenerator | ✅ 已完成 | 2026-05-19 | data_permission_generator.py |
| FR-016 | PermissionSyncService 重写 | ✅ 已完成 | 2026-05-19 | permission_sync_service.py |
| FR-017 | 权限同步 API | ✅ 已完成 | 2026-05-19 | permission_sync_api.py |
| FR-018 | 服务层测试 | ✅ 已完成 | 2026-05-19 | 14个测试用例 |

**Phase 21 进度**: 100% (8/8)

### 11.3 测试用例状态

| ID | 范围 | 总数 | 已完成 | 待完成 |
|----|------|------|--------|--------|
| 后端测试 | meta/tests/ | 1731+ | 1731+ | 0 |
| 新增权限同步测试 | permission_sync_service | 8 | 8 | 0 |
| 新增 Owner 转移测试 | owner_transfer_service | 6 | 6 | 0 |
| 拦截器细粒度测试 | interceptors/ | 80+ | 0 | 80+ |

---

**Spec + RFC 完整性检查**:

- Section count: 11
- Last section name: "实施状态追踪"
- Content: Complete
- 最后更新: 2026-05-19

