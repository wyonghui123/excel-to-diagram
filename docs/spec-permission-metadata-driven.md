## 目录

1. [1. 背景与目标 {#sec1}](#1-背景与目标-sec1)
2. [2. 需求类型总览 {#sec2}](#2-需求类型总览-sec2)
3. [3. 功能需求 {#sec3}](#3-功能需求-sec3)
4. [4. 非功能需求 {#sec4}](#4-非功能需求-sec4)
5. [5. 外部接口需求 {#sec5}](#5-外部接口需求-sec5)
6. [6. 过渡需求 {#sec6}](#6-过渡需求-sec6)
7. [7. 约束与假设 {#sec7}](#7-约束与假设-sec7)
8. [8. 优先级与里程碑建议 {#sec8}](#8-优先级与里程碑建议-sec8)
9. [9. 变更/设计提案 (RFC) {#sec9}](#9-变更设计提案-(rfc)-sec9)

---
# Spec + RFC: 权限体系元数据驱动化

> 版本：v1.0  
> 日期：2026-05-16  
> 状态：待确认 (Pending Confirmation)  
> 作者：Architecture Team  
> 前置研究：
> - [竞品架构分析_元数据驱动与权限模型.md](./competitive-analysis-metadata-permission.md)
> - [权限体系元数据驱动化_细化方案设计.md](./permission-metadata-driven-design.md)
> - [权限体系_单一事实源补充分析.md](./permission-ssot-analysis.md)
> - [权限配置流程优化_维度驱动vs菜单驱动.md](./permission-config-optimization.md)
> - [用友BIP权限模型研究补充.md](./yonyou-bip-permission-research.md)

---

## 1. 背景与目标 {#sec1}

### 1.1 背景

当前系统基于 YAML + BO Framework 实现了元数据驱动的"事务分析一体"架构。BO（Business Object）的 YAML Schema 已经是系统的唯一事实源，涵盖了字段定义、关联关系（Association/Composition）、业务操作（ACTIONS）、UI 视图配置（ui_view_config）等完整语义。

然而，权限体系尚未完全纳入这个元数据驱动闭环。经过深入诊断，发现以下核心问题：

**断裂点1：权限表与 YAML 定义脱节。** `permissions` 表的内容由 `init_auth.py` 中 `seed_permissions()` 函数硬编码生成，与 BO YAML 的 `actions` 和 `category_config` 定义无关。新增 BO 时需手动修改初始化脚本。

**断裂点2：菜单与 BO 的关系是硬编码的。** `init_menu_permissions.py` 中每个菜单的 `required_permissions` 是手动维护的 JSON 列表，与 BO schema 的 `actions` 之间没有自动推导链路。

**断裂点3：前端存在5套并行菜单定义。** `menuConfig.js`、`init_menu_permissions.py`、`useMenuPermissions.js`（menuIconMap + getDefaultMenus）共5套菜单配置，key 命名不一致（如 `arch-data` vs `archdata` vs `data`）。

**断裂点4：权限配置入口与业务语言背离。** 当前管理员必须先"勾选菜单"再"配置数据条件"，但业务语言是"给某人华东区架构师权限"而非"给某人开5个菜单"。SAP、Salesforce、Power Platform、用友BIP 四家头部企业全部将"组织/管理维度"作为权限配置的第一入口。

**断裂点5：存在10+处违反"单一事实源"原则的硬编码。** 包括 `PERMISSION_LABELS`（30+条）、`MENU_DISPLAY_NAMES`（5条）、`_resource_name()`、`_action_name()`、`_get_resource_name()`、`menuIconMap` 等，这些信息全部可以从 YAML 的 `name` 字段和 `MetaRegistry` 动态获取。

**断裂点6：ManagementDimension 已建模但未成为配置入口。** 项目已有完善的 `management_dimensions` 表、`ManagementDimensionEngine`（影响范围计算）、`ConditionRuleDialog`（维度条件编辑），但维度仅用于 condition 表达式内部，未成为角色定义的第一级概念。

### 1.2 业务目标

- **BO-001**：实现权限体系的完全元数据驱动——YAML Schema 作为权限定义的唯一事实源，消除所有硬编码映射
- **BO-002**：将权限配置入口从"菜单中心"改为"管理维度中心"，对齐行业最佳实践（SAP组织级别、Salesforce角色层级、Power Platform业务单元、用友BIP主隔离维度）
- **BO-003**：消除前端5套并行菜单定义，统一为后端 API 驱动的单一菜单源
- **BO-004**：支持"派生角色"模式（SAP 风格），一个功能角色模板 × 不同维度范围 = 多个运行时角色

### 1.3 用户/涉众目标

- **UO-001 系统管理员**：通过维度范围声明一次性完成角色配置（选维度范围 → 系统自动推导菜单+权限+数据规则），减少配置步骤和出错概率
- **UO-002 业务管理员**：使用业务语言（"华东区领域架构师"）而非技术语言（"勾选 arch-data 菜单并配 domain_id IN (1,2)"）定义角色
- **UO-003 开发者**：新增 BO 后权限自动生成，无需修改任何初始化脚本或硬编码映射

---

## 2. 需求类型总览 {#sec2}

| 类型 | 是否适用 | 来源 |
|------|---------|------|
| 业务需求 | 是 | 用户对话 / 行业对标研究 |
| 用户/涉众需求 | 是 | 管理员和开发者角色分析 |
| 方案需求 | 是 | 竞品分析 + 代码诊断 |
| 功能需求 | 是 | 见第3节 |
| 非功能需求 | 是 | 见第4节 |
| 外部接口需求 | 是 | 见第5节 |
| 过渡需求 | 是 | 见第6节 |

---

## 3. 功能需求 {#sec3}

### 3.1 维度驱动权限配置（优先级：Must）

#### FR-001: 角色维度范围声明

- **描述**：系统必须支持在角色定义中声明管理维度范围（`role_dimension_scopes`），作为权限配置的第一入口。管理员选择产品(Product)、版本(Version)、领域(Domain)等维度的具体值，并可指定是否包含下级（inherit_children）。
- **验收标准**：
  - [AC-001.1] 管理员可通过 UI 为角色选择多个维度的值范围
  - [AC-001.2] 支持 `inherit_children=true`，选中 domain 后自动包含其子领域和下级层次
  - [AC-001.3] 数据存储于 `role_dimension_scopes` 表
  - [AC-001.4] 支持 scope_mode（include/exclude）以支持黑名单场景
- **优先级**：Must
- **类型映射**：功能需求 / 用户需求
- **来源**：竞品分析（SAP组织级别、Salesforce角色层级、用友BIP主隔离维度）

#### FR-002: 维度范围自动推导数据条件

- **描述**：DimensionScopeEngine 必须根据角色的维度范围声明，自动为所有适用的 resource_type 生成数据条件表达式。
- **验收标准**：
  - [AC-002.1] 输入 `version: [3], domain: [1,2,5]` 后，系统自动生成 `version_id = 3 AND domain_id IN (1,2,5,及子级ID...)` 的条件
  - [AC-002.2] 自动将生成的 condition 写入 `permission_rules` 表
  - [AC-002.3] 处理 inherit_children，递归展开所有子级 ID
  - [AC-002.4] 条件适用于所有在维度元数据中声明了 `resource_types` 的资源类型
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：方案设计 / 代码分析

#### FR-003: 维度范围自动推导推荐菜单

- **描述**：DimensionScopeEngine 必须根据维度范围自动推荐菜单列表。推荐逻辑：菜单关联的 BO（primary_object_type 或 object_types）在维度范围内存在数据，则推荐该菜单。
- **验收标准**：
  - [AC-003.1] 遍历所有 `auto_generated=true` 的菜单
  - [AC-003.2] 检查每个菜单关联的 BO 表在维度范围内是否有 `COUNT(*) > 0` 的记录
  - [AC-003.3] 返回推荐的菜单 code 列表
  - [AC-003.4] 管理员可增减推荐结果
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：方案设计

#### FR-004: 维度范围自动推导功能权限

- **描述**：从推荐菜单的 `required_permissions` 自动提取功能权限列表。
- **验收标准**：
  - [AC-004.1] 从推荐菜单的 `required_permissions` JSON 字段提取所有权限编码
  - [AC-004.2] 同时从 BO 的 `category_config` 提取额外权限
  - [AC-004.3] 去重后生成 `role_permissions` 记录
  - [AC-004.4] 管理员可增减
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：方案设计

#### FR-005: 一键同步（维度范围 → 菜单 + 权限 + 数据规则）

- **描述**：`DimensionScopeEngine.auto_sync_all()` 方法必须一次性完成从维度范围到所有权限表（role_menu_permissions、role_permissions、permission_rules）的同步。
- **验收标准**：
  - [AC-005.1] 调用一次方法完成三表同步
  - [AC-005.2] 返回推导结果摘要供管理员确认
  - [AC-005.3] 支持增量同步（新增的维度值被追加，移除的维度值被清理）
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：方案设计

### 3.2 权限从 BO Actions 自动同步（优先级：Must）

#### FR-006: PermissionSyncService

- **描述**：系统必须提供 `PermissionSyncService`，在系统启动或 YAML 变更时自动扫描所有已注册的 MetaObject，从其 `actions` 和 `category_config` 中提取权限编码并同步到 `permissions` 表。
- **验收标准**：
  - [AC-006.1] 替代 `init_auth.py` 的 `seed_permissions()` 硬编码
  - [AC-006.2] 自动扫描 `MetaRegistry.get_all()` 迭代所有 BO
  - [AC-006.3] 权限编码格式：`{object_type}:{action_suffix}`，如 `domain:create`
  - [AC-006.4] 系统内部 BO（以 `_` 开头）和纯关联表（user_role 等）被自动跳过
  - [AC-006.5] `permission.name` 从 YAML 的 `action.name` 自动填充（如 "创建领域"）
  - [AC-006.6] 支持增量更新：仅创建缺失的权限，不删除已有权限
- **优先级**：Must
- **类型映射**：方案需求 / 功能需求
- **来源**：代码诊断 / 单一事实源分析

#### FR-007: 唯一映射的集中管理

- **描述**：`action_id → permission_suffix` 的唯一映射表必须定义在 `MetaAction.ACTION_SUFFIX_MAP` 类常量中，且在整个代码库中只存在这一处。
- **验收标准**：
  - [AC-007.1] `MetaAction.ACTION_SUFFIX_MAP = {'crud_create': 'create', 'crud_read': 'read', 'crud_update': 'update', 'crud_delete': 'delete'}`
  - [AC-007.2] 提供 `MetaAction.get_permission_suffix()` 实例方法
  - [AC-007.3] 提供 `MetaAction.get_permission_code(object_id)` 实例方法
  - [AC-007.4] `PermissionSyncService`、`MenuAutoGenerator`、`DimensionScopeEngine` 均通过此方法获取映射，不各自维护本地副本
- **优先级**：Must
- **类型映射**：方案需求
- **来源**：单一事实源补充分析（违规9）

### 3.3 Menu BO 元数据化（优先级：Must）

#### FR-008: 新建 menu.yaml Schema

- **描述**：菜单必须成为一等 BO，通过 `meta/schemas/menu.yaml` 定义。
- **验收标准**：
  - [AC-008.1] 表名 `menus`，包含字段：menu_code, menu_name, menu_path, page_type, primary_object_type, object_types, page_config, parent_menu, icon, color, description, sort_order, is_active, auto_generated
  - [AC-008.2] `page_type` 枚举值：object_list, object_detail, multi_object_hub, custom_page, dashboard
  - [AC-008.3] `object_types` 为 JSON 数组，关联 BO ID 列表
  - [AC-008.4] `auto_generated` 字段标记是否由引擎自动生成
  - [AC-008.5] `color` 和 `description` 字段支持前端菜单卡片展示
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：方案设计 / 单一事实源分析

#### FR-009: MenuAutoGenerator 引擎

- **描述**：`MenuAutoGenerator` 必须能够为所有已注册的 BO 自动生成 `auto_generated=true` 的菜单记录。
- **验收标准**：
  - [AC-009.1] `generate_object_list_menu(meta_object)` 为单个 BO 生成 object_list 菜单
  - [AC-009.2] 菜单的 `required_permissions` 从 BO 的 `actions` 自动推导
  - [AC-009.3] `generate_all()` 为所有 BO 批量生成菜单（跳过以 `_` 开头的模板和纯关联表）
  - [AC-009.4] 自动生成的菜单标记 `auto_generated=true`，手动配置的标记 `false`
- **优先级**：Must
- **类型映射**：功能需求
- **来源**：方案设计

### 3.4 消除硬编码冗余（优先级：Must）

#### FR-010: 消除 PERMISSION_LABELS 硬编码

- **描述**：`role_menu_api.py` 中的 `PERMISSION_LABELS` 字典（30+条）必须替换为从 MetaRegistry 动态获取。
- **验收标准**：
  - [AC-010.1] 实现 `_get_permission_label(perm_code)` 函数，从 `MetaRegistry.get(resource_type).get_action_by_suffix(suffix).name` 获取
  - [AC-010.2] 特殊处理 `*` 权限（返回 "超级权限"）
  - [AC-010.3] 所有使用 `PERMISSION_LABELS.get(p, p)` 的位置替换为 `_get_permission_label(p)`
- **优先级**：Must
- **类型映射**：方案需求
- **来源**：单一事实源分析（违规1）

#### FR-011: 消除 MENU_DISPLAY_NAMES 硬编码

- **描述**：`role_menu_api.py` 中的 `MENU_DISPLAY_NAMES` 字典必须移除，直接使用数据库中的 `menu_name` 字段。
- **验收标准**：
  - [AC-011.1] `display_name` 直接使用 `menu.get('menu_name', code)`
  - [AC-011.2] 不再需要 `MENU_DISPLAY_NAMES.get()` 降级
- **优先级**：Must
- **类型映射**：方案需求
- **来源**：单一事实源分析（违规2）

#### FR-012: 消除 menuIconMap 和 getDefaultMenus

- **描述**：`useMenuPermissions.js` 中的 `menuIconMap` 和 `getDefaultMenus()` 硬编码必须移除。菜单的所有展示属性（icon, color, name, description）从后端 API 获取。
- **验收标准**：
  - [AC-012.1] `menuIconMap` 字典被完全移除
  - [AC-012.2] `getDefaultMenus()` 降级逻辑改为从 localStorage 读取缓存的菜单配置
  - [AC-012.3] 最终降级为空列表（用户需登录或刷新）
- **优先级**：Must
- **类型映射**：方案需求
- **来源**：单一事实源分析（违规3,4）

#### FR-013: 消除 init_auth.py 硬编码映射

- **描述**：`_resource_name()` 和 `_action_name()` 函数移除，`seed_permissions()` 委托给 `PermissionSyncService`。
- **验收标准**：
  - [AC-013.1] `seed_permissions()` 改为调用 `PermissionSyncService.sync_all()`
  - [AC-013.2] 资源名称从 `MetaObject.name` 获取（如 "领域"）
  - [AC-013.3] 权限名称从 `actions[].name` 获取（如 "创建领域"）
- **优先级**：Must
- **类型映射**：方案需求
- **来源**：单一事实源分析（违规6,7）

#### FR-014: 消除 data_permission_api.py 中的重复映射

- **描述**：`_get_resource_name()` 改为使用 `MetaRegistry` 统一查询资源显示名称。
- **验收标准**：
  - [AC-014.1] 通过 `MetaRegistry.get(resource_type)` 获取 BO 信息
  - [AC-014.2] 通过 `bo_framework.read()` 获取具体记录的 display_name
- **优先级**：Must
- **类型映射**：方案需求
- **来源**：单一事实源分析（违规8）

### 3.5 前端统一（优先级：Should）

#### FR-015: 统一菜单 API

- **描述**：新增 `GET /api/v1/menu/visible` 端点，返回当前用户可见的菜单（含层级结构和完整展示属性）。
- **验收标准**：
  - [AC-015.1] 按用户角色过滤菜单
  - [AC-015.2] 构建基于 `parent_menu` 的层级树结构
  - [AC-015.3] 返回 menu_code, menu_name, menu_path, icon, color, description, page_type, primary_object_type, children
- **优先级**：Should
- **类型映射**：外部接口需求 / 功能需求
- **来源**：方案设计

#### FR-016: 废弃 menuConfig.js 静态配置

- **描述**：前端菜单完全由后端 API 驱动，`menuConfig.js` 标记为 deprecated。
- **验收标准**：
  - [AC-016.1] `menuConfig.js` 被移除或标记 deprecated
  - [AC-016.2] 菜单数据从 `/api/v1/menu/visible` 加载
  - [AC-016.3] 支持 API 失败时的降级（localStorage 缓存 + 空列表）
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：方案设计

### 3.6 数据权限声明化（优先级：Should）

#### FR-017: BO YAML 增加 data_permission_dimensions

- **描述**：在 BO YAML 中支持 `data_permission_dimensions` 字段，声明该 BO 支持的数据权限维度类型。
- **验收标准**：
  - [AC-017.1] 支持维度类型：owner_scope（所有者范围）、context_scope（上下文范围）、field_filter（字段值过滤）、organization_scope（组织范围）
  - [AC-017.2] `models.py` 的 `MetaObject` 增加 `data_permission_dimensions: List[DataPermissionDimension]` 字段
  - [AC-017.3] ImpactPreview 可利用此信息自动展示权限影响范围
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：竞品分析（SAP CAP @restrict, Mendix Access Rules）

#### FR-018: 字段级 PermissionAnnotation 激活

- **描述**：激活 `models.py` 中现存的 `PermissionAnnotation`，在 BOFramework 的 `get_ui_config()` 中叠加字段级可见/编辑控制。
- **验收标准**：
  - [AC-018.1] 字段 YAML 支持 `permission.readable` / `permission.writable` / `permission.roles`
  - [AC-018.2] `bo_framework.get_ui_config()` 叠加权限判断
  - [AC-018.3] 前端 ObjectPage 的字段编辑状态与权限联动
- **优先级**：Should
- **类型映射**：功能需求
- **来源**：方案设计

### 3.7 增强能力（优先级：Could）

#### FR-019: ManagementDimension 支持维度树结构

- **描述**：ManagementDimension 增加 `tree_code` 和 `tree_level` 字段，支持同一实体属于多棵维度树（参考用友BIP 多维组织树）。
- **验收标准**：
  - [AC-019.1] 增加 `tree_code`（所属维度树编码）
  - [AC-019.2] 增加 `tree_level`（树中的层级深度）
  - [AC-019.3] DimensionScopeEngine 的 `_get_all_child_ids()` 利用 tree 结构而非硬编码 hierarchy_chain
- **优先级**：Could
- **类型映射**：功能需求
- **来源**：用友BIP 多维组织树参考

#### FR-020: BO actions 增加 action_group 字段

- **描述**：支持将 actions 按业务活动组打包（如 standard / readonly / maintain），角色分配时可一次性授予整组权限（参考用友BIP 业务活动）。
- **验收标准**：
  - [AC-020.1] YAML actions 支持 `action_group` 字段
  - [AC-020.2] 前端 PermissionConfigPanel 支持按 action_group 批量勾选
- **优先级**：Could
- **类型映射**：功能需求
- **来源**：用友BIP 业务活动参考

#### FR-021: 权限分析中心（用户视角）

- **描述**：RolePermissionCenter 增加"用户权限总览"视图，支持一键查看任一用户的完整权限清单（功能权限 + 组织权限 + 数据权限）。
- **验收标准**：
  - [AC-021.1] 输入用户 → 展示其所有角色的权限全景
  - [AC-021.2] 支持按资源类型过滤
  - [AC-021.3] 支持智能诊断（给定"服务 + 活动"，判断用户是否有权）
- **优先级**：Could
- **类型映射**：功能需求
- **来源**：用友BIP 权限分析中心参考

---

## 4. 非功能需求 {#sec4}

### NFR-001: 性能

- **描述**：DimensionScopeEngine 的 `expand_dimension_values()` 方法处理 inherit_children 时，递归查询子级 ID 必须在合理时间内完成。
- **测量方法**：6层深度（product→version→domain→sub_domain→service_module→business_object）的递归展开应在 500ms 内完成
- **优先级**：Must

### NFR-002: 向后兼容

- **描述**：所有改造必须向后兼容。现有角色的权限关系不受影响，管理员可以继续使用现有的菜单驱动配置流程。
- **测量方法**：现有角色的 `role_permissions`、`role_menu_permissions`、`permission_rules` 记录在执行改造后保持不变且功能正常
- **优先级**：Must

### NFR-003: 单一事实源

- **描述**：权限名称、资源名称、菜单名称等任何展示文本，必须从 YAML Schema 或 MetaRegistry 动态获取，代码中不得存在硬编码的名称映射字典。
- **测量方法**：代码库中不存在 `PERMISSION_LABELS`、`MENU_DISPLAY_NAMES`、`_resource_name()`、`_action_name()`、`menuIconMap`、`resource_names`、`action_names` 等硬编码映射字典
- **优先级**：Must

### NFR-004: 可测试性

- **描述**：`PermissionSyncService`、`MenuAutoGenerator`、`DimensionScopeEngine` 必须可独立进行单元测试，不依赖完整的服务器上下文。
- **测量方法**：三个引擎类接受 `data_source` 注入，可在测试中使用内存 SQLite 实例
- **优先级**：Should

### NFR-005: 可观测性

- **描述**：权限同步操作必须记录日志（log level: INFO），包含创建/更新/删除的权限数量。
- **测量方法**：每次 `sync_all()` 调用输出 `[PermissionSync] Created N permissions, Synced M existing`
- **优先级**：Should

---

## 5. 外部接口需求 {#sec5}

### IF-001: GET /api/v1/menu/visible

- **类型**：API
- **方法/路径**：`GET /api/v1/menu/visible`
- **认证**：需要登录
- **请求**：无特殊参数
- **响应**：
  ```json
  {
    "menus": [
      {
        "menu_code": "domain-list",
        "menu_name": "领域管理",
        "menu_path": "/domain",
        "icon": "folder",
        "color": "blue",
        "description": "管理领域数据",
        "page_type": "object_list",
        "primary_object_type": "domain",
        "sort_order": 1,
        "children": []
      }
    ]
  }
  ```
- **错误码**：401（未登录）
- **来源**：FR-015

### IF-002: GET /api/v2/roles/{roleId}/dimension-scopes

- **类型**：API
- **方法/路径**：`GET /api/v2/roles/{roleId}/dimension-scopes`
- **认证**：管理员
- **响应**：返回该角色的维度范围声明及推导结果
  ```json
  {
    "scopes": [
      {"dimension_code": "domain", "values": [1,2,5], "inherit_children": true}
    ],
    "expanded_values": {"domain": [1,2,5,10,11,12,...]},
    "recommended_menus": ["domain-list", "sub-domain-list", "arch-data"],
    "derived_permissions": ["domain:read", "domain:update", "sub_domain:read"],
    "data_conditions": {"domain": "domain_id IN (1,2,5,10,11,12)", ...}
  }
  ```
- **来源**：FR-005

### IF-003: PUT /api/v2/roles/{roleId}/dimension-scopes

- **类型**：API
- **方法/路径**：`PUT /api/v2/roles/{roleId}/dimension-scopes`
- **认证**：管理员
- **请求体**：
  ```json
  {
    "scopes": [
      {"dimension_code": "domain", "values": [1,2,5], "inherit_children": true}
    ],
    "auto_sync": true
  }
  ```
- **响应**：同步结果摘要
- **来源**：FR-005

### IF-004: 维度范围配置面板（UI）

- **类型**：UI
- **入口**：RolePermissionCenter.vue 新增 Step 1（维度范围）
- **交互**：
  - 级联选择器：Product → Version → Domain → SubDomain → …
  - 支持多选 + 下级自动包含开关
  - 实时显示数据访问预览（预估影响的数据记录数）
  - "自动推导菜单和权限" 按钮
- **来源**：FR-001, FR-002, FR-003

### IF-005: POST /api/v1/permission-sync

- **类型**：API
- **方法/路径**：`POST /api/v1/permission-sync`
- **认证**：管理员
- **描述**：手动触发权限同步（开发/调试用）
- **响应**：`{"created": [...], "existing": [...], "orphaned": [...]}`
- **来源**：FR-006

---

## 6. 过渡需求 {#sec6}

### TR-001: 现有角色向后兼容

- **描述**：维度驱动方案作为增强而非替换。现有通过菜单驱动配置的角色不受影响，两种模式共存。
- **策略**：两种模式写入同一套底层表（role_menu_permissions, role_permissions, permission_rules），维度驱动作为"快速配置层"，菜单驱动保留作为"精细调整层"
- **回滚方案**：如出现问题，移除维度面板组件即可恢复到纯菜单驱动模式
- **来源**：NFR-002

### TR-002: 数据迁移

- **描述**：提供从现有 `permission_rules` 反向提取维度范围的工具，用于将现有角色的数据条件转换为 `role_dimension_scopes` 记录。
- **策略**：
  1. 解析 `permission_rules.condition` 字符串
  2. 提取 `field = value` 和 `field IN (...)` 子句
  3. 匹配到对应的 `management_dimensions.code`
  4. 生成 `role_dimension_scopes` 记录
  5. 管理员确认后迁移
- **回滚方案**：迁移工具不修改原 `permission_rules` 表，只生成新的 `role_dimension_scopes` 记录
- **来源**：分析

### TR-003: 前端渐进式改造

- **描述**：前端菜单从静态配置迁移到 API 驱动的过程必须渐进进行。
- **策略**：
  1. 先实现 `GET /api/v1/menu/visible` 并加载
  2. 同时保留 `menuConfig.js` 作为降级方案
  3. 稳定运行后标记 `menuConfig.js` deprecated
  4. 2-4周观察期后移除静态配置
- **回滚方案**：若 API 加载失败，自动降级到 `menuConfig.js` 或 localStorage 缓存
- **来源**：分析

### TR-004: 初始化脚本保留

- **描述**：`init_auth.py` 和 `init_menu_permissions.py` 保留但功能委托给新的同步服务。
- **策略**：
  1. `seed_permissions()` 内部委托给 `PermissionSyncService.sync_all()`
  2. 标记原有硬编码函数为 deprecated
  3. 2个版本后评估是否完全移除
- **回滚方案**：无需回滚，兼容策略保证了原有流程
- **来源**：NFR-002

---

## 7. 约束与假设 {#sec7}

### 7.1 技术约束

- **TC-001**：`management_dimensions` 表已存在，结构稳定，不允许破坏性变更（允许增量添加字段）
- **TC-002**：现有 `role_menu_api.py`、`role_api.py`、`permission_service.py` 的 API 契约保持不变，新增端点而非修改现有端点
- **TC-003**：`MetaRegistry` 是运行时单例，任何服务可直接访问 `registry.get_all()` 和 `registry.get(object_id)`
- **TC-004**：数据库使用 SQLite（当前）或可替换为 PostgreSQL（未来），引擎层的 SQL 使用参数化查询
- **TC-005**：前端框架为 Vue 3 + Vite，使用 Composition API 模式

### 7.2 业务约束

- **BC-001**：权限模型保持 Union（累积）模式，不引入 Deny 机制（与现有 RBAC 一致）
- **BC-002**：`*` 超级权限的存在保持不变，超管跳过所有权限检查

### 7.3 假设

- **A-001**：所有 BO 的 YAML Schema 中 `actions[].name` 字段已正确填写了中文显示名称 — 来源：已验证（domain.yaml, role.yaml 等均已填写）
- **A-002**：`hierarchies.yaml` 中定义的 product→version→domain→sub_domain→service_module→business_object 六层关系是稳定的业务层级 — 来源：已验证
- **A-003**：前端 Vue 组件可改为从 API 加载菜单配置 — 来源：已验证（useMenuPermissions 已有 API 调用路径）

---

## 8. 优先级与里程碑建议 {#sec8}

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-006 | PermissionSyncService | Must | 消除权限表硬编码，是元数据驱动的前提 |
| FR-007 | ACTION_SUFFIX_MAP 集中化 | Must | 单一事实源核心，所有推导引擎依赖 |
| FR-008 | menu.yaml Schema | Must | 菜单元数据化的基础 |
| FR-009 | MenuAutoGenerator | Must | 菜单自动生成入口 |
| FR-010~014 | 消除硬编码冗余 | Must | 根本目标，消除所有名称映射字典 |
| FR-001~005 | 维度驱动配置 | Must | 权限配置入口重构，行业最佳实践对齐 |
| NFR-001 | 性能 | Must | inherit_children 递归不能成为瓶颈 |
| NFR-002 | 向后兼容 | Must | 不能破坏现有权限体系 |
| NFR-003 | 单一事实源 | Must | 核心质量属性 |
| FR-015~016 | 前端菜单统一 | Should | 依赖 Phase 1 基础设施 |
| FR-017~018 | 数据权限声明化 | Should | 依赖维度驱动的完成 |
| NFR-004~005 | 可测试性/可观测性 | Should | 质量保障 |
| FR-019~021 | 增强能力 | Could | 锦上添花，优先级较低 |

### 建议里程碑

| 里程碑 | 范围 | 预估工期 | 依赖 |
|--------|------|---------|------|
| **M1: 基础设施** | FR-006, FR-007, FR-008, FR-009, FR-010~014 | 2周 | — |
| **M2: 维度驱动** | FR-001~005, IF-002, IF-003, IF-004, TR-001~004 | 2周 | M1 |
| **M3: 前端统一** | FR-015, FR-016, IF-001 | 1周 | M1 |
| **M4: 增强能力** | FR-017~021, NFR-004, NFR-005 | 2周 | M2 |

总预估工期：7周（含测试和过渡期）

---

## 9. 变更/设计提案 (RFC) {#sec9}

### 9.1 当前状态分析

#### 当前架构

```
meta/schemas/*.yaml (BO 定义)
    ↓ YAMLLoader
MetaRegistry (运行时元数据镜像)
    ↓
┌────────────────────────────────────────────────────────┐
│ 权限层（当前：与 YAML 脱节）                              │
│                                                        │
│ init_auth.py (seed_permissions)                         │
│   → 硬编码5个BO的资源列表 + _resource_name() + _action_name() │
│   → 写入 permissions 表                                  │
│                                                        │
│ init_menu_permissions.py                                │
│   → 硬编码每个菜单的 required_permissions                │
│   → 写入 menu_permissions 表                             │
│                                                        │
│ role_menu_api.py                                        │
│   → PERMISSION_LABELS (30+条硬编码)                      │
│   → MENU_DISPLAY_NAMES (5条硬编码)                       │
│   → get_role_unified_permissions()                      │
│                                                        │
│ 前端                                                    │
│   → menuConfig.js (静态菜单树，第1套)                    │
│   → useMenuPermissions.js (menuIconMap + getDefaultMenus) │
│     (第2-3套菜单定义，key命名不一致：archdata vs arch-data) │
└────────────────────────────────────────────────────────┘
```

#### 问题总结

| 问题 | 代码位置 | 严重度 |
|------|---------|-------|
| 权限表硬编码 | init_auth.py:188-310 | 高 |
| 菜单权限硬编码 | init_menu_permissions.py | 高 |
| PERMISSION_LABELS | role_menu_api.py:152-174 | 高 |
| MENU_DISPLAY_NAMES | role_menu_api.py:176-182 | 中 |
| menuIconMap | useMenuPermissions.js:13-50 | 中 |
| getDefaultMenus | useMenuPermissions.js:91-136 | 中 |
| menuConfig.js | menuConfig.js | 中 |
| _resource_name/_action_name | init_auth.py:289-310 | 高 |
| _get_resource_name | data_permission_api.py:189-220 | 中 |
| 配置入口反直觉 | PermissionConfigPanel.vue | 高 |

### 9.2 目标状态

```
meta/schemas/*.yaml (唯一事实源)
    │
    ├── [BO.id + name] ────────→ 资源名称（零硬编码）
    ├── [actions[].id + name] ──→ ACTION_SUFFIX_MAP（唯一映射）
    │       │                      ↓
    │       │               PermissionSyncService
    │       │                      ↓
    │       │               permissions 表（自动同步）
    │       │
    ├── [ui_view_config] ───────→ MenuAutoGenerator
    │       │                      ↓
    │       │               menus 表（自动生成）
    │       │
    └── [data_permission_dimensions] → 数据权限维度声明
    │
    ├── management_dimensions 表（维度元数据）
    │       │
    │   role_dimension_scopes（角色维度范围声明）
    │       │
    │   DimensionScopeEngine
    │       ├──→ 数据条件推导
    │       ├──→ 菜单推荐
    │       └──→ 权限推导
    │
    └── 消费者（零硬编码）
            ├── role_menu_api.py（无 PERMISSION_LABELS / MENU_DISPLAY_NAMES）
            ├── 前端（无 menuIconMap / getDefaultMenus / menuConfig.js）
            └── 所有 API（统一从 MetaRegistry 获取名称）
```

#### 关键变更

1. **新增 `MetaAction.ACTION_SUFFIX_MAP`** — 全局唯一的 action_id→permission_suffix 映射
2. **新增 `MetaObject.get_permission_label()` / `get_action_by_suffix()`** — 便利方法
3. **新增 `PermissionSyncService`** — 替代 init_auth.py 硬编码
4. **新增 `MenuAutoGenerator`** — 菜单从 BO 元数据自动生成
5. **新增 `menu.yaml` Schema** — 菜单成为一等 BO，增加 color/description 字段
6. **新增 `role_dimension_scopes` 表** — 角色的维度范围声明
7. **新增 `DimensionScopeEngine`** — 维度范围 → 一切自动推导
8. **消除 10+ 处硬编码映射** — 全部改为从 MetaRegistry 动态获取
9. **新增 `GET /api/v1/menu/visible`** — 统一前端菜单加载
10. **新增维度范围配置面板 UI** — RolePermissionCenter 新增 Step 1

### 9.3 方案选择

#### 方案 A：维度驱动优先（本 Spec 选定的方案）

| 优点 | 缺点 |
|------|------|
| 对齐 SAP/Salesforce/用友BIP 行业最佳实践 | 需要新增 role_dimension_scopes 表和新组件 |
| 配置流符合业务语言 | 需要提供现有角色迁移工具 |
| 天然支持派生角色 | 实施周期较长 |
| 数据权限声明式 | |

#### 方案 B：菜单驱动增强（保守方案）

| 优点 | 缺点 |
|------|------|
| 改动最小，风险最低 | 配置入口仍然是反直觉的 |
| 不改变管理员操作习惯 | 不支持派生角色 |
| | 与行业最佳实践不一致 |

**决策**：选择方案 A，但两种模式共存。维度驱动作为主入口，菜单驱动保留作为精细调整入口。

### 9.4 详细设计

#### 9.4.1 模块/组件设计

```
新增模块：
  meta/services/permission_sync_service.py    ← PermissionSyncService
  meta/services/menu_auto_generator.py        ← MenuAutoGenerator
  meta/services/dimension_scope_engine.py     ← DimensionScopeEngine
  
  meta/schemas/menu.yaml                      ← Menu BO Schema
  meta/schemas/role_dimension_scope.yaml      ← Role Dimension Scope Schema

修改模块：
  meta/core/models.py                         ← MetaAction.ACTION_SUFFIX_MAP
                                                MetaObject.get_permission_label()
                                                MetaObject.data_permission_dimensions
  
  meta/scripts/init_auth.py                   ← seed_permissions() 委托给 PermissionSyncService
  
  meta/scripts/init_menu_permissions.py       ← 委托给 MenuAutoGenerator
  
  meta/api/role_menu_api.py                   ← 移除 PERMISSION_LABELS / MENU_DISPLAY_NAMES
                                                新增 _get_permission_label()
  
  meta/api/data_permission_api.py             ← 移除 _get_resource_name()

前端新增/修改：
  src/views/SystemManagement/RolePermissionCenter.vue  ← 新增 Step 1 (维度范围面板)
  src/config/menuConfig.js                              ← Deprecated
  src/composables/useMenuPermissions.js                 ← 移除 menuIconMap / getDefaultMenus
```

#### 9.4.2 数据模型

**role_dimension_scopes 表**：
```
id (INTEGER, PK)
role_id (INTEGER, FK→roles.id)
dimension_code (STRING)          -- 如 'domain', 'version', 'product'
dimension_values (JSON)          -- 如 [1, 2, 5]
inherit_children (BOOLEAN)       -- 默认 true
scope_mode (STRING)               -- 'include' | 'exclude', 默认 'include'
```

**menus 表（menu.yaml 定义）**：
```
id (INTEGER, PK)
menu_code (STRING, UNIQUE)
menu_name (STRING)
menu_path (STRING)
page_type (STRING)               -- 'object_list' | 'object_detail' | 'multi_object_hub' | 'custom_page'
primary_object_type (STRING)
object_types (JSON)
page_config (JSON)
parent_menu (STRING)              -- 父菜单 code
icon (STRING)
color (STRING)                    -- ← 新增
description (STRING)              -- ← 新增
sort_order (INTEGER)
is_active (BOOLEAN)
auto_generated (BOOLEAN)          -- ← 新增：true=引擎生成, false=手动配置
```

**management_dimensions 表（新增字段）**：
```
tree_code (STRING)                -- ← 新增：所属维度树编码（如 'business_tree'）
tree_level (INTEGER)              -- ← 新增：在