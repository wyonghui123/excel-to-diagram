# Spec: 菜单/导航元数据驱动统一 — 单一事实源架构

## 1. 背景与目标

### 1.1 背景

当前系统的菜单和导航体系由 **4 套并行定义** 构成，互不感知，形成严重的"多源头数据不一致"问题：

| # | 定义位置 | 驱动对象 | 与 BO 元数据的关系 |
|---|---------|---------|-------------------|
| ① | `AppRootLayout.vue` `navigationItems`（硬编码数组） | **侧边栏渲染** | 零关系，纯硬编码 |
| ② | `menuConfig.js`（3处定义：`items`/`navigationItems`/`tabGroupConfigs`） | `items`→**无消费方（死代码）**；`navigationItems`→**无消费方（死代码）**；`tabGroupConfigs`→`GenericTabContainer` Tab 渲染 | `tabGroupConfigs` 以字符串 `objectType` 松散关联 BO |
| ③ | `menu_permissions` 表（DB） | 权限检查（`check_menu_visibility`） | 字段不全：缺少 `page_type`、`object_types`、`primary_object_type` |
| ④ | `MenuAutoGenerator`（Python） | **无消费方（死代码）** | 可从 BO 元数据自动推导菜单，但从未被任何生产流程调用 |

此外，`menu.yaml` Schema 定义了 `menus` 表，但该表和 `menu_permissions` 表是两张独立表，后端 API `/api/v1/menu-permission/visible` 仅读取旧表，旧表缺少驱动 Tab 容器的关键字段 `page_type` 和 `object_types`。

**新增一个 BO 需要改 3 处**（`AppRootLayout.vue` + `menuConfig.js` + `init_menu_permissions.py`），这正是 [权限体系升级 Spec](file:///d:/filework/excel-to-diagram/docs/spec_权限体系升级/02_fr.md) 中 FR-007 和 FR-008 要消除的病根。

### 1.2 业务目标

- **单一事实源**：菜单/导航/权限的所有定义从 `menu.yaml` Schema → `menus` 表 → API → 前端渲染 一条链路穿透到底
- **零代码新增**：注册一个新 BO 后，菜单、侧边栏、Tab 容器自动可见，无需改任何前端代码
- **消除死代码**：删除 `menuConfig.js`、`AppRootLayout.vue` 中的硬编码导航数组、`MenuAutoGenerator` 未接入的孤立状态

### 1.3 用户 / 涉众目标

| 涉众 | 目标 |
|------|------|
| **开发者** | 不再需要为每个新 BO 手动修改侧边栏、菜单配置、权限初始化脚本 |
| **系统管理员** | 通过统一的菜单管理界面（`menus` BO）管理菜单可见性和权限 |
| **最终用户** | 侧边栏菜单始终与数据权限一致，不会出现"菜单可见但无数据"的不一致 |

---

## 2. 需求类型概览

| 类型 | 是否适用 | 证据（来源） |
|------|---------|-------------|
| 业务需求 | 是 | 权限体系升级 Spec FR-007/FR-008；元数据驱动架构总体目标 |
| 用户/涉众需求 | 是 | 开发效率、管理一致性 |
| 解决方案需求 | 是 | 后端补齐字段 + API 增强 + 前端统一消费 |
| 功能需求 | 是 | FR-001 ~ FR-006 |
| 非功能需求 | 是 | NFR-001 ~ NFR-003 |
| 外部接口需求 | 是 | IF-001 ~ IF-002 |
| 过渡需求 | 是 | TR-001 ~ TR-002 |

---

## 3. 功能需求

### FR-001: menus 表字段补齐（后端）

- **描述**：系统 MUST 确保 `menus` 表（`menu.yaml` Schema 对应的 DB 表）包含以下字段，且与 Schema 定义一致：
  - `page_type`（VARCHAR, NOT NULL）：枚举值 `object_list`｜`multi_object_hub`｜`custom_page`｜`dashboard`
  - `object_types`（JSON/TEXT, NULLABLE）：JSON 数组，如 `["user", "role", "user_group"]`
  - `primary_object_type`（VARCHAR, NULLABLE）：主 BO 类型
  - `color`（VARCHAR, NULLABLE）：菜单颜色
  - `description`（VARCHAR, NULLABLE）：菜单描述
- **验收标准**：
  - AC-001.1：`menus` 表包含上述所有列
  - AC-001.2：`menu.yaml` 中定义的字段全部在 DB 中存在
  - AC-001.3：已有 `menu_permissions` 表的数据通过迁移脚本同步到 `menus` 表
- **优先级**：Must
- **类型映射**：解决方案需求 / 功能需求
- **来源**：权限体系升级 Spec FR-007 AC-007.2 ~ AC-007.4；本 Spec 分析

### FR-002: 菜单种子数据补齐（后端）

- **描述**：系统 MUST 在 `init_menu_permissions.py` 中为每条菜单记录写入完整的 `page_type` 和 `object_types` 字段。
- **验收标准**：
  - AC-002.1：`user-permission`（用户权限）包含 `page_type: multi_object_hub`, `object_types: ["user","role","user_group"]`
  - AC-002.2：`business-config`（业务配置）包含 `page_type: multi_object_hub`, `object_types: ["enum_type"]`
  - AC-002.3：`product-version`（产品版本管理）包含 `page_type: object_list`, `primary_object_type: product`
  - AC-002.4：`arch-data`（架构数据管理）包含 `page_type: multi_object_hub`, `object_types: ["domain","sub_domain","service_module"]`
  - AC-002.5：`audit-log`（日志管理）包含 `page_type: object_list`, `primary_object_type: audit_log`
  - AC-002.6：`system`（系统管理）包含 `page_type: custom_page`
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：权限体系升级 Spec FR-007 AC-007.5

### FR-003: MenuAutoGenerator 接入生产流程（后端）

- **描述**：系统 MUST 在 BO 注册完成后自动调用 `MenuAutoGenerator.generate_all()`，为新注册的 BO 自动 INSERT OR IGNORE 菜单记录到 `menus` 表和 `menu_permissions` 表。
- **验收标准**：
  - AC-003.1：在 `server.py` 启动流程中（BO 注册完成后）调用 `generate_all()`
  - AC-003.2：已存在的菜单记录不会被覆盖（INSERT OR IGNORE 语义）
  - AC-003.3：自动生成的菜单包含正确的 `page_type`、`object_types`、`primary_object_type`、`required_permissions`、`data_permission_hint`
  - AC-003.4：内部关联表（如 `user_role`、`role_permission`、`role_menu_permissions` 等）的菜单不会被自动生成
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：本 Spec 分析；`MenuAutoGenerator` 代码已存在但未接入

### FR-004: API 增强 — `/api/v1/menu-permission/visible` 返回完整菜单字段（后端）

- **描述**：系统 MUST 在 `/api/v1/menu-permission/visible` 的响应中包含每条菜单的 `page_type`、`object_types`、`primary_object_type`、`icon`、`color`、`description` 字段。
- **验收标准**：
  - AC-004.1：响应 JSON 中每个菜单节点包含 `page_type` 字段
  - AC-004.2：响应 JSON 中每个菜单节点包含 `object_types` 字段（数组）
  - AC-004.3：响应 JSON 中每个菜单节点包含 `primary_object_type` 字段
  - AC-004.4：响应 JSON 中每个菜单节点包含 `children` 数组（层级结构）
  - AC-004.5：`children` 按当前用户权限过滤（已有逻辑，不退化）
- **优先级**：Must
- **类型映射**：外部接口需求 / 功能需求
- **来源**：本 Spec 分析

### FR-005: 前端侧边栏 API 化（前端）

- **描述**：系统 MUST 将 `AppRootLayout.vue` 中的硬编码 `navigationItems` 替换为从 `useMenuPermissions().accessibleMenus` API 数据驱动的动态渲染。
- **验收标准**：
  - AC-005.1：`AppRootLayout.vue` 中不再存在硬编码的 `navigationItems` 数组
  - AC-005.2：侧边栏菜单项由 `GET /api/v1/menu-permission/visible` 返回的顶层 `children` 驱动
  - AC-005.3：菜单项按 `sort_order` 排序
  - AC-005.4：菜单项的 `icon`、`color`、`label`（`menu_name`）从 API 响应读取
  - AC-005.5：`page_type=custom_page` 的菜单项点击后路由到其 `menu_path`
  - AC-005.6：`page_type=object_list` 的菜单项点击后路由到 `/objects/{primary_object_type}`
  - AC-005.7：`page_type=multi_object_hub` 的菜单项点击后路由到 `/admin/{menu_code}`
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：权限体系升级 Spec FR-007 AC-007.5；本 Spec 分析

### FR-006: GenericTabContainer API 化（前端）

- **描述**：系统 MUST 将 `GenericTabContainer.vue` 中的 `getGroupTabs()`（从 `menuConfig.js` 读取）替换为从菜单 API 数据驱动。
- **验收标准**：
  - AC-006.1：`GenericTabContainer` 接受 `menuNode` prop（来自 API 返回的菜单节点）替代 `group` prop
  - AC-006.2：Tab 项由 `menuNode.children` 驱动，三级渲染引擎不变：
    - Level 1: 命名插槽 `tab-{key}`
    - Level 2: `tab.component` 自定义 Vue 组件（通过配置注入）
    - Level 3: `tab.objectType` → `<GenericObjectList>`
  - AC-006.3：`objectType` 从 API 返回的 `children[].primary_object_type` 推导
  - AC-006.4：原有 `group` prop 的向后兼容路由保留（过渡期用 `tabGroupConfigs` 映射旧版 `group` → API 数据）
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：本 Spec 分析

---

## 4. 非功能需求

### NFR-001: 性能 — 菜单 API 响应时间

- **描述**：`GET /api/v1/menu-permission/visible` 响应时间（P99）MUST ≤ 200ms（不含网络延迟）
- **测量方法**：后端 middleware 记录请求耗时；前端 `useMenuPermissions` 已支持 LocalStorage 24h 缓存
- **优先级**：Must
- **来源**：系统分析（菜单数据量小，~30 条记录，DB 查询 + 权限过滤应在 50ms 内完成）

### NFR-002: 可靠性 — 菜单 API 降级策略

- **描述**：当 `/api/v1/menu-permission/visible` 不可用时，前端 MUST 降级使用 LocalStorage 缓存（已有实现），或降级为仅显示首页
- **测量方法**：E2E 测试模拟 API 失败场景
- **优先级**：Must
- **来源**：已有的 `useMenuPermissions.js` 降级逻辑

### NFR-003: 可维护性 — 删除死代码

- **描述**：实施完成后，系统中 MUST 不再存在以下死代码：
  - `menuConfig.js`（完整文件删除）
  - `AppRootLayout.vue` 中的硬编码 `navigationItems` 数组
  - `MenuAutoGenerator` 未接入状态（接入到 `server.py` 生命周期）
- **测量方法**：grep 全量搜索确认
- **优先级**：Must
- **来源**：权限体系升级 Spec FR-007 AC-007.5；本 Spec 分析

---

## 5. 外部接口需求

### IF-001: 菜单 API 响应增强

- **类型**：API
- **端点**：`GET /api/v1/menu-permission/visible`
- **请求/响应**：

```json
// 响应增强（在原响应基础上新增字段）
{
  "code": 0,
  "data": {
    "menus": [
      {
        "menu_code": "user-permission",
        "menu_name": "用户与权限管理",
        "menu_path": "/admin/user-permission",
        "page_type": "multi_object_hub",        // ★新增
        "primary_object_type": "user",           // ★新增
        "object_types": ["user","role","user_group"], // ★新增
        "icon": "Users",
        "color": "#3b82f6",
        "description": "管理用户、角色和用户组",
        "sort_order": 30,
        "is_active": true,
        "children": [                            // ★已有，字段补齐
          {
            "menu_code": "user-list",
            "menu_name": "用户管理",
            "page_type": "object_list",
            "primary_object_type": "user",
            "object_types": null,
            "icon": null,
            "color": null
          }
        ]
      }
    ]
  }
}
```

- **错误处理**：
  - 500: 数据库查询失败 → 降级策略（见 NFR-002）
  - 401: 未登录 → 前端跳转登录页
- **来源**：FR-004

### IF-002: 前端菜单数据消费者接口

- **类型**：UI
- **消费者**：`AppRootLayout.vue`（侧边栏）、`GenericTabContainer.vue`（Tab 容器）
- **数据结构**：由 `useMenuPermissions().accessibleMenus` 提供，类型定义：

```typescript
interface MenuNode {
  menu_code: string
  menu_name: string
  menu_path: string
  page_type: 'object_list' | 'multi_object_hub' | 'custom_page' | 'dashboard'
  primary_object_type: string | null
  object_types: string[] | null
  icon: string | null
  color: string | null
  description: string | null
  sort_order: number
  is_active: boolean
  children: MenuNode[] | null
}
```

- **来源**：FR-005、FR-006

---

## 6. 过渡需求

### TR-001: 表结构迁移

- **描述**：`menu_permissions` 表需扩容字段以对齐 `menus` 表 Schema。通过 ALTER TABLE 完成。
- **策略**：
  1. 执行 `ALTER TABLE menu_permissions ADD COLUMN page_type ...`、`object_types`、`primary_object_type`
  2. 执行迁移脚本，将已有 `menu_permissions` 数据同步写入 `menus` 表
  3. 执行 `init_menu_permissions.py` 补齐 `page_type`/`object_types` 字段
  4. 最终统一读取 `menus` 表
- **回滚方案**：ALTER TABLE 可逆（DROP COLUMN）；`init_menu_permissions.py` 修改可 git revert
- **来源**：FR-001、FR-002

### TR-002: 前端渐进式迁移

- **描述**：前端一次性切换风险较高，采用 Feature Flag 控制的渐进式迁移。
- **策略**：
  1. 新增 `useMenuPermissions.js` 中的 `accessibleMenus` 计算属性
  2. `AppRootLayout.vue` 增加 Feature Flag：`const USE_API_MENU = true`
  3. 当 `USE_API_MENU=true` 且 API 数据可用时，使用 API 数据；否则降级为旧版硬编码
  4. 稳定运行一周后，删除 Feature Flag 和旧版硬编码分支
  5. 最后删除 `menuConfig.js`
- **回滚方案**：将 Feature Flag 改为 `false` 即回到旧版
- **来源**：FR-005、FR-006

---

## 7. 约束与假设

### 7.1 技术约束

- **数据库**：SQLite（开发/测试），需确认 JSON 类型字段的兼容性（SQLite 3.9+ 支持 JSON 函数）
- **后端框架**：Flask + 自定义 BO Framework，`menu_permission_api.py` 使用 Blueprint
- **前端框架**：Vue 3 + Vite + Pinia + Vue Router
- **菜单数据量**：< 50 条，无需分页优化
- **已有缓存**：`useMenuPermissions.js` 已实现 LocalStorage 24h 缓存

### 7.2 业务约束

- 菜单权限检查逻辑已在 `MenuPermissionService.check_menu_visibility()` 中实现，不可退化
- 角色-菜单关联（`role_menu_permissions` 表）不受本次变更影响
- 已有的 `init_menu_permissions.py` 中 8 条系统菜单需保持向后兼容

### 7.3 假设

- 假设 `MenuAutoGenerator.generate_all()` 的逻辑已充分测试并可直接接入 — 来源：待验证
- 假设 `menu_permissions` 表和 `menus` 表可通过 `menu_code` 字段关联 — 来源：已验证（两表均有 `menu_code`）
- 假设前端 `useMenuPermissions.js` 的缓存机制稳定（LocalStorage 24h） — 来源：已验证
- 假设 SQLite JSON 函数兼容 `object_types` 字段的读写 — 来源：待验证（SQLite 3.9+）
- 假设 `EnumValueManagement.vue`、`SystemAdmin/index.vue` 等保留页面不受本次变更影响 — 来源：已验证（它们不消费菜单 API）

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-001 | menus 表字段补齐 | Must | 所有后续需求的基础 |
| FR-002 | 菜单种子数据补齐 | Must | 确保已有菜单数据完整 |
| FR-003 | MenuAutoGenerator 接入 | Must | 实现零代码新增 BO 菜单 |
| FR-004 | API 增强 | Must | 前端消费的必要前提 |
| FR-005 | 侧边栏 API 化 | Must | 消除硬编码 |
| FR-006 | Tab 容器 API 化 | Must | 消除 `tabGroupConfigs` |
| TR-001 | 表结构迁移 | Must | FR-001 的前置条件 |
| TR-002 | 前端渐进式迁移 | Should | 降低风险，非阻塞 |

**建议里程碑：**

| 里程碑 | 范围 | 预估 |
|--------|------|------|
| M1: 后端补齐 | FR-001 + FR-002 + TR-001 | DB 迁移 + 数据补齐 |
| M2: API + 自动化 | FR-003 + FR-004 | MenuAutoGenerator 接入 + API 增强 |
| M3: 前端统一 | FR-005 + FR-006 + TR-002 | 侧边栏/Tab 容器 API 化 + Feature Flag |
| M4: 清理 | NFR-003 | 删除 `menuConfig.js`、硬编码、死代码 |

---

## 9. 变更/设计方案（RFC）

### 9.1 现状分析

#### 当前架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    4 套并行菜单定义（互不感知）                      │
├───────────────┬───────────────┬───────────────┬───────────────────┤
│ ①AppRootLayout│ ②menuConfig.js│ ③menu_permiss-│ ④MenuAutoGenerator│
│   .vue        │  tabGroupCfg  │   ions 表     │   （死代码）        │
│   (硬编码)     │   (JS配置)     │   (DB字段不全) │                    │
├───────┼───────┼───────┼───────┼───────┼───────┼─────────┼─────────┤
│   ↓   │       │   ↓   │       │   ↓   │       │   ↓     │         │
│ 侧边栏 │       │Tab容器 │       │权限检查│       │  无     │         │
│ 渲染   │       │ 渲染   │       │ API   │       │ 消费方  │         │
└───────┴───────┴───────┴───────┴───────┴───────┴─────────┴─────────┘
```

#### 当前问题

1. **5 处重复定义**（Spec 问题 #4）：`AppRootLayout.vue` 硬编码、`menuConfig.items`（死代码）、`menuConfig.tabGroupConfigs`、`menu_permissions` 表、`init_menu_permissions.py`
2. **字段断裂**：`menu_permissions` 表无 `page_type`/`object_types` 字段，无法驱动 Tab 容器
3. **死代码**：`MenuAutoGenerator` 写了但从未接入，`menuConfig.items` 无人引用
4. **新增 BO 改 3 处**：违反元数据驱动原则

#### 相关文件路径

- [AppRootLayout.vue](file:///d:/filework/excel-to-diagram/src/components/common/AppRootLayout.vue) — 侧边栏硬编码导航
- [menuConfig.js](file:///d:/filework/excel-to-diagram/src/config/menuConfig.js) — 菜单/导航 JS 配置
- [GenericTabContainer.vue](file:///d:/filework/excel-to-diagram/src/views/GenericTabContainer.vue) — Tab 容器组件
- [menu.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/menu.yaml) — 菜单 BO Schema
- [menu_permission.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/menu_permission.yaml) — 菜单权限 BO Schema（旧表）
- [menu_auto_generator.py](file:///d:/filework/excel-to-diagram/meta/services/menu_auto_generator.py) — 菜单自动生成器
- [menu_permission_api.py](file:///d:/filework/excel-to-diagram/meta/api/menu_permission_api.py) — 菜单 API
- [menu_permission_service.py](file:///d:/filework/excel-to-diagram/meta/services/menu_permission_service.py) — 菜单权限服务
- [init_menu_permissions.py](file:///d:/filework/excel-to-diagram/meta/scripts/init_menu_permissions.py) — 菜单种子数据
- [useMenuPermissions.js](file:///d:/filework/excel-to-diagram/src/composables/useMenuPermissions.js) — 前端菜单权限 composable

### 9.2 目标状态

#### 目标架构

```
menu.yaml (Schema) ─── BO 元数据唯一真相源
       │
       ▼
MenuAutoGenerator.generate_all()  ←── 接入 server.py 启动流程
  ┌─ for each BO → object_list 菜单
  └─ 手动配置 multi_object_hub 菜单
       │
       ▼
menus 表 (DB)
  page_type, object_types, primary_object_type
  icon, color, description, sort_order...
       │
       ▼
GET /api/v1/menu-permission/visible
  返回完整菜单树（含层级、page_type、object_types）
  按用户权限过滤 children
       │
  ┌────┼────────────────┐
  ▼    ▼                ▼
侧边栏  Tab容器         路由守卫
(page_  (page_type=     (required_
type=   multi_object_   permissions)
object_ hub→children
list/   →Tab items)
custom_
page)
```

#### 关键变更

1. **后端**：`menus` 表补齐字段 → 种子数据补齐 → `MenuAutoGenerator` 接入 `server.py` → API 返回完整字段
2. **前端**：`AppRootLayout.vue` 和 `GenericTabContainer.vue` 改为从 `useMenuPermissions()` API 数据驱动
3. **清理**：删除 `menuConfig.js`、`AppRootLayout.vue` 硬编码导航

### 9.3 详细设计

#### 9.3.1 数据模型

##### menus 表（menu.yaml Schema → DB）

| 字段 | 类型 | 说明 | 新增/已有 |
|------|------|------|----------|
| `id` | INTEGER PK | 自增主键 | 已有 |
| `menu_code` | VARCHAR NOT NULL UNIQUE | 菜单编码 | 已有 |
| `menu_name` | VARCHAR NOT NULL | 菜单名称 | 已有 |
| `menu_path` | VARCHAR | 前端路由路径 | 已有 |
| `page_type` | VARCHAR NOT NULL | `object_list`｜`multi_object_hub`｜`custom_page`｜`dashboard` | **新增** |
| `object_types` | JSON/TEXT | JSON 数组，`["user","role","user_group"]` | **新增** |
| `primary_object_type` | VARCHAR | 主 BO 类型 | **新增** |
| `parent_menu` | VARCHAR FK→menu_code | 父菜单编码 | 已有 |
| `icon` | VARCHAR | 图标名称 | 已有 |
| `color` | VARCHAR | 菜单颜色 | 已有 |
| `description` | VARCHAR | 菜单描述 | 已有 |
| `sort_order` | INTEGER | 排序权重 | 已有 |
| `is_active` | BOOLEAN | 是否激活 | 已有 |
| `auto_generated` | BOOLEAN | 是否由 MenuAutoGenerator 生成 | 已有 |

##### menu_permissions 表（权限表，独立于 menus）

保持现有结构不变。`page_type`/`object_types` 等导航字段仅在 `menus` 表维护。

#### 9.3.2 组件设计

##### AppRootLayout.vue 改造

```vue
<!-- 旧：硬编码 navigationItems -->
<script setup>
const navigationItems = [
  { key: 'user-permission', label: '用户与权限管理', icon: 'Users', to: '/admin/user-permission' },
  // ... 更多硬编码
]
</script>

<!-- 新：API 驱动 -->
<script setup>
const { accessibleMenus } = useMenuPermissions()

const navigationItems = computed(() => {
  return (accessibleMenus.value || []).map(menu => ({
    key: menu.menu_code,
    label: menu.menu_name,
    icon: menu.icon || 'Folder',
    color: menu.color,
    to: deriveRoutePath(menu),
    pageType: menu.page_type,
    children: menu.children
  })).sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
})

function deriveRoutePath(menu) {
  switch (menu.page_type) {
    case 'object_list':
      return `/objects/${menu.primary_object_type}`
    case 'multi_object_hub':
      return `/admin/${menu.menu_code}`
    case 'custom_page':
      return menu.menu_path
    default:
      return menu.menu_path
  }
}
</script>
```

##### GenericTabContainer.vue 改造

```vue
<!-- 旧：getGroupTabs(group) 从 menuConfig.js 读取 -->
<script setup>
import { getGroupTabs, getGroupTitle } from '@/config/menuConfig'
const allTabs = computed(() => getGroupTabs(props.group))
</script>

<!-- 新：从 API 菜单节点提取 children -->
<script setup>
const { accessibleMenus } = useMenuPermissions()

const menuNode = computed(() => {
  return accessibleMenus.value?.find(m => m.menu_code === props.group)
    || accessibleMenus.value?.flatMap(m => m.children || []).find(c => c.menu_code === props.group)
})

const allTabs = computed(() => {
  if (!menuNode.value?.children) return []
  return menuNode.value.children.map(child => ({
    key: child.menu_code,
    label: child.menu_name,
    objectType: child.page_type === 'object_list' ? child.primary_object_type : null,
    ...child.page_config
  }))
})

const title = computed(() => menuNode.value?.menu_name || props.group)
</script>
```

#### 9.3.3 API 设计

##### `GET /api/v1/menu-permission/visible` 增强

在 `menu_permission_api.py` 的 `get_visible_menus()` 函数中：

1. 从 `menus` 表（而非仅 `menu_permissions` 表）JOIN 查询
2. 返回 `page_type`、`object_types`、`primary_object_type`、`color`、`description` 字段
3. 构建 `children` 层级树（利用 `parent_menu` 字段）

```python
# 伪代码
def get_visible_menus():
    # 1. 从 menus 表获取所有激活的菜单
    all_menus = db.query("SELECT * FROM menus WHERE is_active = 1 ORDER BY sort_order")
    
    # 2. 按当前用户权限过滤（已有逻辑，扩展返回字段）
    visible_menus = []
    for menu in all_menus:
        if check_menu_visibility(current_user_id, menu.menu_code):
            visible_menus.append({
                "menu_code": menu.menu_code,
                "menu_name": menu.menu_name,
                "menu_path": menu.menu_path,
                "page_type": menu.page_type,          # ★新增返回
                "primary_object_type": menu.primary_object_type,  # ★新增返回
                "object_types": json.loads(menu.object_types) if menu.object_types else None,  # ★新增返回
                "icon": menu.icon,
                "color": menu.color,                   # ★新增返回
                "description": menu.description,        # ★新增返回
                "sort_order": menu.sort_order,
                "parent_menu": menu.parent_menu
            })
    
    # 3. 构建层级树
    return build_tree(visible_menus)
```

#### 9.3.4 主要流程

##### 新增 BO 的端到端流程

```
1. 开发者在 menu.yaml Schema 的注册列表中增加新 BO
2. server.py 启动 → BO 注册 → MenuAutoGenerator.generate_all()
3. MenuAutoGenerator 为新 BO 生成 object_list 菜单记录 → INSERT INTO menus
4. 管理员访问 /api/v1/menu-permission/visible
5. API 返回包含新 BO 的菜单树
6. 前端 useMenuPermissions 缓存菜单数据
7. AppRootLayout 自动渲染新菜单项（无需改任何代码）
8. GenericTabContainer 自动渲染新 Tab（如属 multi_object_hub）
```

##### 用户访问流程

```
1. 用户登录 → useMenuPermissions.loadMenuPermissions()
2. GET /api/v1/menu-permission/visible（仅返回该用户可见的菜单）
3. AppRootLayout 渲染侧边栏（已按权限过滤）
4. 用户点击 "用户与权限管理"（page_type=multi_object_hub）
5. 路由到 /admin/user-permission
6. GenericTabContainer 从 accessibleMenus 中找到 user-permission 节点
7. 渲染 children 为 Tab：用户管理(object_list:user) | 角色权限(object_list:role) | 用户组(object_list:user_group)
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A: 完全 API 驱动**（本 Spec） | 单一事实源；零代码新增 BO；消除所有死代码 | 需要后端补齐 + 前端一次性切换 | ✅ **选定** |
| B: 仅提取 tabGroupConfigs 到独立文件 | 改动小；快速 | 仍然有两套定义（文件 vs DB）；不解决根本问题 | ❌ 拒绝（治标不治本） |
| C: 仅 API 化侧边栏，Tab 容器保持 JS 配置 | 侧边栏部分改善 | 仍有两套定义；tabGroupConfigs 仍需手动维护 | ❌ 拒绝（半吊子方案） |

### 9.5 实施与迁移计划

#### 实施顺序

1. **DB 迁移**（TR-001）
   - 为 `menus` 表增加 `page_type`、`object_types`、`primary_object_type` 列
   - 同步 `menu_permissions` 数据到 `menus` 表

2. **种子数据补齐**（FR-002）
   - 更新 `init_menu_permissions.py`，为每条记录写入 `page_type`/`object_types`

3. **MenuAutoGenerator 接入**（FR-003）
   - 在 `server.py` 启动流程中调用 `generate_all()`

4. **API 增强**（FR-004）
   - 修改 `menu_permission_api.py` `/visible` 端点返回完整字段

5. **前端改造**（FR-005 + FR-006）
   - `AppRootLayout.vue`：Feature Flag + API 驱动侧边栏
   - `GenericTabContainer.vue`：API 驱动 Tab 项

6. **清理**（NFR-003）
   - 删除 `menuConfig.js`
   - 删除 `AppRootLayout.vue` 硬编码导航
   - 删除 Feature Flag

#### 风险缓解

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| DB 字段迁移失败 | 菜单 API 不可用 | 在独立终端执行迁移，验证后继续；ALTER TABLE 可回滚 |
| `MenuAutoGenerator` 逻辑有 bug | 生成错误菜单 | 先 dry-run 模式输出日志，确认无误后再入库 |
| 前端 API 化后样式不一致 | 用户体验下降 | Feature Flag 双轨运行，对比验证 |
| `menu_permissions` 和 `menus` 表数据不一致 | 权限判断错误 | 迁移脚本做一致性校验 |

#### 测试策略

| 层级 | 范围 | 工具 |
|------|------|------|
| 单元测试 | `MenuAutoGenerator._derive_permissions()`、`get_visible_menus()` 返回字段 | pytest |
| 单元测试 | `useMenuPermissions.js` `accessibleMenus` 计算属性 | vitest |
| 单元测试 | `AppRootLayout.vue` `deriveRoutePath()` | vitest |
| 集成测试 | `/api/v1/menu-permission/visible` 返回 `page_type`/`object_types` | pytest + requests |
| E2E 测试 | 登录 → 侧边栏渲染 → 点击菜单 → Tab 容器渲染 | Playwright |

#### 回滚方案

1. **后端**：git revert API 变更 + `server.py` 变更 + 种子数据变更
2. **DB**：ALTER TABLE DROP COLUMN（逆迁移）
3. **前端**：Feature Flag 设为 `false` 回到旧版硬编码
4. **恢复**：`menuConfig.js` 在 git 中可恢复

---

## 10. TBD 列表

| ID | 事项 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-1 | `menus` 表当前是否存在于 DB 中？ | 需确认 DB 实际表结构 | 检查 DB schema / 执行 `PRAGMA table_info(menus)` |
| TBD-2 | `menu_permissions` 和 `menus` 两表的数据一致性 | 需确认两表当前数据是否重叠 | 执行 SELECT 对比两表 `menu_code` |
| TBD-3 | SQLite JSON 字段兼容性 | 需确认 SQLite 版本是否支持 JSON 函数 | 检查 SQLite 版本 ≥ 3.9 |
| TBD-4 | `MenuAutoGenerator` 的单元测试 | 需确认生成器逻辑是否有已有测试覆盖 | 检查 `meta/tests/` 目录 |
| TBD-5 | `menu_permissions` 表的 `page_type` 字段是否需要与 `menus` 表同步 | 两表关系设计决策 | 确认：①两表完全合并为 `menus` 表 ②保持两表独立但字段对齐 ③仅 `menus` 表有导航字段 |

---

Spec 包含 10 个章节，最后一章为"TBD 列表"，内容完整。
