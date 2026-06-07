# Spec: MultiObjectManagementPage 通用多对象管理页面组件

## 概述

本文档定义 `MultiObjectManagementPage` 通用组件的架构设计，将当前 `RelationshipManagement.vue`（即架构数据管理页面 `/system/relationships`）抽象为配置驱动的通用页面级组件。

**核心目标**：单一输入 `objectTypes` 数组，系统自动生成完整的多对象管理页面。

---

## 1. Background & Objectives

### 1.1 Background

当前 `RelationshipManagement.vue` 页面通过 5 个 Tab（领域/子领域/服务模块/业务对象/关系）实现多对象类型统一管理。该页面的核心逻辑分为两部分：

1. **通用框架能力**：Tab 管理、filterFlow 注册、MetaListPage 渲染、MasterDetailLayout 布局、GlobalToolbar
2. **页面特定能力**：左侧 RelationScopeTree（对象范围+关系范围+过滤条件）、combinedFilters 过滤策略映射

该页面与 DomainManagement、SubDomainManagement、ServiceModuleManagement、BusinessObjectManagement 是不同的页面类型。后者是**单对象层级钻取页面**，各有独立路由；而 RelationshipManagement 是**多对象统一入口**，一个路由管理所有对象类型。

**本项目有已存在的独立路由页面**（不是本次抽象目标）：
| 路由 | 页面 | 特征 |
|------|------|------|
| `/system/domains` | DomainManagement | 单对象 + ObjectTreePanel + 层级钻取 |
| `/system/sub-domains` | SubDomainManagement | 单对象 + ObjectTreePanel + 层级钻取 |
| `/system/service-modules` | ServiceModuleManagement | 单对象 + ObjectTreePanel + 层级钻取 |
| `/system/business-objects` | BusinessObjectManagement | 单对象 + ObjectTreePanel + 层级钻取 |
| `/system/relationships` | **RelationshipManagement** | **多对象 + RelationScopeTree + Tab 切换 → 本次目标** |

### 1.2 Objectives

- 通过配置驱动消除硬编码的 combinedFilters switch-case
- 支持通过 `objectTypes` + `pageConfig` 生成完整页面
- 基于 `hierarchies.yaml` 作为层级关系单一事实源
- 为未来类似的多对象管理场景提供复用能力

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 消除硬编码，提高可维护性 |
| User / Stakeholder | Yes | 开发者配置化需求 |
| Solution | Yes | Composable + 插槽扩展架构 |
| Functional | Yes | FR-001 ~ FR-008 |
| Nonfunctional | Yes | NFR-001 ~ NFR-003 |
| External Interface | Yes | hierarchies.yaml 配置接口 |
| Transition | Yes | 现有页面渐进迁移 |

---

## 3. Functional Requirements

### FR-001: 单一输入依赖

- **Description**: 系统必须支持通过 `objectTypes` 数组生成完整页面。
- **Acceptance Criteria**:
  - 输入 `['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']`
  - 自动生成 5 个 Tab，每个对应一种对象类型
  - Tab label 从 `useHierarchyTypes.getLabel(type)` 获取
- **Priority**: Must
- **Source**: 用户需求分析

### FR-002: 配置驱动的 Tab → Filter 映射

- **Description**: 系统必须基于配置自动生成各 Tab 的过滤策略，消除硬编码 switch-case。
- **Acceptance Criteria**:
  - `strategy: 'hierarchy'`：从 `hierarchies.yaml` 自动推导层级对象过滤映射
  - `strategy: 'custom'`：支持自定义过滤规则（如 relationship 的 merge/intersection）
- **Priority**: Must
- **Source**: RelationshipManagement.vue combinedFilters 分析

### FR-003: 全局过滤支持

- **Description**: 系统必须支持对所有 Tab 生效的全局过滤字段。
- **Acceptance Criteria**:
  - `pageConfig.globalFilters` 中定义的字段对所有 Tab 生效
  - 示例：`annotation_category__in` 全局生效
- **Priority**: Must
- **Source**: 备注类型全局过滤需求

### FR-004: 动态侧边栏配置

- **Description**: 系统必须支持根据配置选择不同的侧边栏组件。
- **Acceptance Criteria**:
  - `sidebar.type: 'scope-tree'` → RelationScopeTree
  - `sidebar.type: 'object-tree'` → ObjectTreePanel
  - `sidebar.type: 'none'` → 隐藏侧边栏
- **Priority**: Should
- **Source**: 现有组件分析

### FR-005: 动态工具栏配置

- **Description**: 系统必须支持根据配置选择不同的工具栏组件。
- **Acceptance Criteria**:
  - `toolbar.type: 'global'` → GlobalToolbar（产品/版本 + 全局操作）
  - `toolbar.type: 'version-selector'` → 单独的版本选择器
  - `toolbar.type: 'none'` → 无工具栏
- **Priority**: Should
- **Source**: GlobalToolbar 组件分析

### FR-006: 过滤条件面板配置

- **Description**: 系统必须支持通过配置定义过滤条件面板中的过滤组。
- **Acceptance Criteria**:
  - 每个过滤组支持 `scope` 定义（`global` / `tab:xxx`）
  - 每个过滤组支持 `enumType` 定义枚举来源
  - 支持 disabled 状态（非适用 Tab 时禁用）
- **Priority**: Must
- **Source**: RelationFilterSection 分析

### FR-007: 插槽扩展

- **Description**: 系统必须提供插槽机制支持页面特定自定义。
- **Acceptance Criteria**:
  - `#tabsExtra` → Tab 行右侧自定义内容（状态信息、清空按钮）
  - `#cell-{objectType}-{fieldName}` → 自定义单元格渲染（如 relationship 的 source_bo_name）
  - `#empty` → 自定义空状态
- **Priority**: Should
- **Source**: RelationshipManagement.vue 自定义渲染

### FR-008: 层级过滤自动推导

- **Description**: 对于 `strategy: 'hierarchy'` 的对象类型，过滤映射必须从 `hierarchies.yaml` 自动推导。
- **Acceptance Criteria**:
  - `effectiveDomainIds` → `id__in`（domain 自身的 filter_field=id）
  - `service_module_id__in`（business_object 的 filter_param=service_module_id）
- **Priority**: Must
- **Source**: hierarchies.yaml 分析

---

## 4. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: 组件初始化性能与当前 RelationshipManagement 相当。
- **Measurement**: 页面加载时间不增加超过 50ms
- **Priority**: Should

### NFR-002: 可维护性

- **Description**: 新增对象类型仅需修改 `objectTypes` 数组和 `pageConfig` 配置。
- **Measurement**: 无需编写新页面文件
- **Priority**: Must

### NFR-003: 向后兼容

- **Description**: 迁移过程不影响现有功能表现。
- **Measurement**: UI 表现完全一致，路由不变
- **Priority**: Must

---

## 5. External Interface Requirements

### IF-001: hierarchies.yaml

- **Type**: Configuration
- **Source**: `meta/schemas/hierarchies.yaml`
- **Interaction**: 
  - `levels[].object` → 对象类型元数据
  - `levels[].filter_field` → 自身过滤字段
  - `levels[].filter_param` → 父级过滤字段（用于向下追溯）
  - `dimensions[].filter_param` → 维度过滤参数

### IF-002: useHierarchyTypes

- **Type**: Composable
- **Source**: `src/composables/useHierarchyTypes.js`
- **Interaction**:
  - `getLabel(type)` → Tab 标签
  - `getIcon(type)` → Tab 图标
  - `getParentType(type)` → 父类型

---

## 6. Transition Requirements

### TR-001: 渐进迁移

- **Description**: 将 RelationshipManagement 重构为使用 MultiObjectManagementPage。
- **Strategy**:
  1. 创建 `useMultiObjectPage` composable
  2. 创建 `MultiObjectManagementPage` 组件
  3. 提取 `pageConfig` 配置
  4. 重构 RelationshipManagement 为配置驱动
  5. 构建验证
  6. 功能测试
- **Rollback Plan**: 通过 Git 回退

### TR-002: 旧代码清理

- **Description**: 保留原 RelationshipManagement.vue 中特定于架构数据管理但非通用的逻辑。
- **Strategy**: 通过插槽和配置保留特定逻辑，不在通用组件中硬编码

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- Vue 3 Composition API
- Element Plus 组件库
- 复用现有 composables（useHierarchyTypes、useVersionContext、useFilterFlow）
- 基于 `hierarchies.yaml` 作为层级关系单一事实源

### 7.2 Assumptions

- `useHierarchyTypes` 已正确配置所有对象类型 – Verified
- `hierarchies.yaml` 已定义完整层级关系 – Verified
- 现有 filterFlow 架构不需要调整 – Assumed

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|------------|---------|--------|
| FR-001 | 单一输入依赖 | Must | 核心设计目标 |
| FR-002 | Tab→Filter 映射 | Must | 消除硬编码 |
| FR-003 | 全局过滤 | Must | 核心功能 |
| FR-006 | 过滤条件面板配置 | Must | 核心功能 |
| FR-008 | 层级过滤自动推导 | Must | 配置驱动关键 |
| FR-004 | 动态侧边栏 | Should | 提升灵活性 |
| FR-005 | 动态工具栏 | Should | 提升灵活性 |
| FR-007 | 插槽扩展 | Should | 支持自定义 |

- **Milestone 1**: `useMultiObjectPage` composable 实现
- **Milestone 2**: `MultiObjectManagementPage` 组件实现
- **Milestone 3**: RelationshipManagement 迁移
- **Milestone 4**: 构建验证与功能测试

---

## 9. Change / Design Proposal (RFC)

### 9.0 行业研究：头部产品多对象管理模式分析

在制定本方案前，我们对 7 个头部产品的多对象管理组件模式进行了横向研究：

#### 9.0.1 产品对比总览

| 维度 | SAP Fiori | Salesforce Lightning | Palantir Foundry | ServiceNow | Airtable | Notion | Refine/React Admin |
|------|-----------|---------------------|------------------|------------|----------|--------|-------------------|
| **核心模式** | Floorplan + Annotation-driven | Tab-driven Apps + Dynamic Related Lists | Ontology-driven Workspace | List-Form 二态 + Related Lists | Table-Switching + Views | Database Views + Linked Database | Resource-based CRUD |
| **多对象切换** | SideNavigation + FlexibleColumnLayout | App Tab + List View Tab | Workspace 内多 Widget | Application Navigator | Table Tab Bar（顶部） | Sidebar + Linked Database 引用 | Sidebar Menu（URL-driven） |
| **过滤传递** | OData sap-filter + Intent Navigation | 父子上下文隐式传递 + URL param | Object Set 交叉过滤 | Dot-walking + Breadcrumbs | View 级 Filter + Linked Record 查找 | Relation + Rollup Filter | URL state + useNavigation params |
| **配置 vs 代码** | Annotation 元数据驱动，低代码 | UI 配置 + Custom Metadata，低代码 | Ontology Manager 无代码 | Dictionary + UI Policy，低代码 | 100% 无代码 UI 配置 | 100% UI 配置驱动 | 声明式 JSX 代码配置 |
| **目标用户** | 企业管理员 + 开发者 | 企业管理员 + 开发者 | 数据分析师 + 开发者 | IT 管理员 + 开发者 | 业务用户 | 个人/团队 | 前端开发者 |
| **状态持久化** | SmartFilterBar Variant | List View 保存为命名视图 | Object Set 命名保存 | Filter 保存为 Favorite | View 自动保存 | View 自动保存 | URL query parameters |

#### 9.0.2 与本项目最相关的 5 个核心模式

**① Palantir Foundry — Ontology-driven Multi-Object Workspace**（最相似）

Palantir 的架构与本项目架构高度对应：

| Palantir 概念 | 本项目对应 | 说明 |
|--------------|-----------|------|
| Ontology | `hierarchies.yaml` + ObjectType | 业务对象元数据定义 |
| Object Type | `domain` / `sub_domain` / `business_object` / `relationship` | 对象类型 |
| Object Set | `scopeSelection` | 可复用的过滤结果抽象 |
| Workspace | `MultiObjectManagementPage` | 多对象管理容器 |
| Cross-filter | `combinedFilters` | 跨 Widget 过滤联动 |
| Search Around | `useHierarchyTypes.getParentType()` | 沿关系图导航 |

**关键启示 — Object Set 抽象**：Palantir 将"过滤后的对象集合"提升为一等公民（Object Set），可命名保存、跨 Widget 共享。这启示我们：
- `scopeSelection` 可以演化为一个"命名视图"概念
- 未来可支持保存/恢复过滤状态（类似 SAP Fiori 的 SmartFilterBar Variant）

**② SAP Fiori — Floorplan + SmartFilterBar Variant**

SAP 的核心设计理念是 **Floorplan（楼层平面图）**——每一种标准业务场景对应一个 Floorplan 模板：

| SAP 概念 | 本项目对应 |
|----------|-----------|
| List Report Floorplan | `MetaListPage` |
| Object Page Floorplan | DetailPage / Drawer |
| FlexibleColumnLayout | `MasterDetailLayout` |
| SmartFilterBar | 列头过滤 + 高级过滤面板 |
| SmartFilterBar Variant | 过滤条件面板的 enum 选项 |
| Intent-based Navigation | 版本选择 → 列表刷新 |

**关键启示 — Variant 机制**：SAP 的 Variant 允许用户保存一组过滤条件（含视图选择），可跨用户共享或私有。我们的 `pageConfig.globalFilters` 和 `pageConfig.filterSection` 可以借鉴这个思想——过滤条件不仅由开发者配置，未来也可由用户自定义保存。

**③ Salesforce Lightning — Tab-driven Apps + Dynamic Related Lists**

Salesforce 的多对象管理模式最贴近我们的需求：

| Salesforce 概念 | 本项目对应 |
|----------------|-----------|
| App → Tab → List View | `MultiObjectManagementPage` → Tabs → `MetaListPage` |
| Dynamic Related List | 关系 Tab 的关联过滤 |
| Parent Context Implicit Filter | 层级对象的 `id__in` 过滤 |
| Enhanced Related List | Tab 内嵌的单元格渲染（source_bo_name 等） |

**关键启示 — 父子上下文隐式传递**：Salesforce 的 Related List 自动使用 `reference_field = parent_record_id` 作为隐式过滤条件。这正是我们 `strategy: 'hierarchy'` 应该实现的效果——从 hierarchies.yaml 自动推导过滤映射。

**④ Refine / React Admin — Resource-based CRUD**

Refine/React Admin 采用 **代码即配置** 的声明式模式：

```tsx
// Refine: 声明式 Resource 配置
<Resource name="users" list={UserList} edit={UserEdit} create={UserCreate} />
<Resource name="products" list={ProductList} show={ProductShow} />
```

其中 `inferencer` 组件可以**根据 API 响应自动推断生成 List/Create/Edit 页面**。这启示我们：
- `objectTypes` → Tabs 自动生成 就是一种 "Vue 版 inferencer"
- 未来可进一步：自动推断 column 配置、自动推断过滤控件类型

**关键启示 — URL-driven State**：Refine 通过 `syncWithLocation: true` 将过滤条件同步到 URL，支持浏览器前进后退、书签保存、跨页面携带过滤上下文。我们的 `filterFlow` 系统可借鉴此模式。

**⑤ Airtable — Table Switching + View 独立性**

Airtable 的 Table Tab Bar 实现了：

| Airtable 概念 | 本项目对应 |
|--------------|-----------|
| Table Tab Bar | `el-tabs` |
| View（每 Table 多 View） | 每个 Tab 的 `MetaListPage`（未来可扩展为多 View） |
| View 级 Filter/Sort/Group（独立配置） | 每个 Tab 的 `combinedFilters`（独立过滤策略） |
| Linked Record 双向查询 | `hierarchies.yaml` 层级关系追溯 |

**关键启示 — View 状态保持**：Airtable 在 Table 间切换时保持每个 View 的过滤/排序状态。我们的 `key=activeTab` 策略已经通过强制重建 MetaListPage 实现了类似的效果（切换 Tab 时重置列表状态）。

#### 9.0.3 对本次设计的 6 个关键启示

| # | 启示 | 来源 | 在本设计的应用 |
|---|------|------|---------------|
| 1 | **配置即组件声明**：用声明式配置替代硬编码 | Refine/React Admin | `objectTypes` + `pageConfig` 替代 switch-case |
| 2 | **层级自动推导**：父子关系 → 隐式过滤条件 | Salesforce + Palantir | `strategy: 'hierarchy'` 自动推导过滤映射 |
| 3 | **Object Set 抽象**：过滤结果为可复用一等公民 | Palantir | `scopeSelection` 标准化，未来支持命名保存 |
| 4 | **语义配置驱动 UI**：用语义注解自动生成 UI | SAP Fiori (Annotation-driven) | `hierarchies.yaml` → Tab label/icon 自动生成 |
| 5 | **独立 View 状态**：每个 Tab 保持独立过滤/排序 | Airtable | `key=activeTab` 隔离各 Tab 的列表状态 |
| 6 | **插槽扩展**：预留自定义点处理非通用场景 | Notion (Linked Database) | `#tabsExtra`, `#cell-{type}-{field}` 插槽 |

#### 9.0.4 架构对齐分析

我们的方案与行业最佳实践的对应关系：

```
我们的 MultiObjectManagementPage  = Palantir Workspace + Salesforce Tab-driven App + Refine Resource-based CRUD

数据流对齐:
  Palantir:   Ontology → Object Type → Object Set → Workspace → Cross-filter
  本项目:      hierarchies.yaml → ObjectType → scopeSelection → MultiObjectManagementPage → combinedFilters
  
  过滤模型对齐:
  Salesforce: Parent Context → Implicit Filter → Dynamic Related List
  本项目:      hierarchies.yaml → strategy:'hierarchy' → id__in / service_module_id__in
```

### 9.1 As-Is Analysis

#### 当前架构

```
RelationshipManagement.vue
├── GlobalToolbar（产品/版本 + 全局操作）
├── MasterDetailLayout
│   ├── #master: RelationScopeTree
│   │   ├── CollapsiblePanel: 对象范围 → ObjectScopeSection
│   │   ├── CollapsiblePanel: 关系范围 → RelationScopeSection
│   │   └── CollapsiblePanel: 过滤条件 → RelationFilterSection
│   └── #detail:
│       ├── Tabs（5个固定 Tab）
│       ├── tabs-extra（已选 x 项 + 清空）
│       └── MetaListPage（key=activeTab）
```

#### 当前问题

1. **combinedFilters 硬编码**（第174-236行）：switch-case 针对 5 个对象类型
2. **scopeSelection 结构固定**：effectiveDomainIds、effectiveSubDomainIds 等字段名写死
3. **RelationScopeTree 不可替换**：无法改为 ObjectTreePanel
4. **Tab 定义硬编码**：label、filterDisabled 逻辑写死在页面

#### 关键代码路径

- `src/views/SystemManagement/RelationshipManagement.vue`
- `src/components/common/RelationScopeTree/RelationScopeTree.vue`
- `src/components/common/RelationScopeTree/RelationFilterSection.vue`
- `src/components/common/RelationScopeTree/ObjectScopeSection.vue`
- `src/components/common/RelationScopeTree/RelationScopeSection.vue`
- `src/composables/filterSources/useScopeFilterSource.js`
- `src/composables/useFilterFlow.js`
- `meta/schemas/hierarchies.yaml`

### 9.2 完整数据流追踪

```
用户操作                  emit/event                  scopeSelection         combinedFilters         API param
─────────────────────────────────────────────────────────────────────────────────────────────────────

[对象范围] 勾选领域A      → {domainIds:[1]}         → selectedDomainIds:[1] → (tab=domain)
  ObjectScopeSection      → RelationScopeTree          effectiveDomainIds:[1]   id__in=1
  el-tree @check          → handleObjectScopeChange

[对象范围] 勾选服务模块X  → {serviceModuleIds:[5]}  → selectedServiceModuleIds → (tab=service_module)
                                                     :[5]                      id__in=5
                                                     effectiveDomainIds:[1]    (tab=business_object)
                                                     effectiveSubDomainIds:[3]  service_module_id__in=5

[关系范围] 勾选关系类型R  → {relationCodes:['R1']}   → relationCodes:['R1']    → (tab=relationship)
  RelationScopeSection    → RelationScopeTree                                      relation_code__in=R1
  el-tree @check          → handleRelationScopeChange

[过滤条件] 选备注类型N    → {annotationCategories   → annotationCategories    → (所有 Tab)
  RelationFilterSection   :['N1']}                    :['N1']                    annotation_category__in=N1
  el-select @change       → RelationScopeTree                                    (tab=relationship)
                          → handleFilterChange        filterRelationCodes:['R2']  relation_code__in=R1∩R2
```

### 9.3 Target State

#### 架构

```
MultiObjectManagementPage (配置驱动)
├── useMultiObjectPage (核心 composable)
│   ├── objectTypes → tabs 自动生成
│   ├── pageConfig → filterStrategies 构建
│   └── combinedFilters (配置驱动，消除 switch-case)
├── 动态 Toolbar (配置选择)
├── MasterDetailLayout
│   ├── 动态 Sidebar (配置选择)
│   └── Detail
│       ├── Tabs (自动生成)
│       ├── 插槽: tabsExtra
│       └── MetaListPage
│           └── 插槽: cell-{objectType}-{fieldName}
```

#### 使用示例

```vue
<template>
  <MultiObjectManagementPage
    :object-types="['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']"
    :config="pageConfig"
  >
    <template #tabsExtra="{ context }">
      <span v-if="context.hasSelection">已选 {{ context.selectionCount }} 项</span>
      <el-button type="primary" link size="small" @click="context.clear">清空</el-button>
    </template>
    
    <template #cell-relationship-source_bo_name="{ row }">
      <span>{{ row.source_bo_name }}({{ row.source_code }})</span>
    </template>
  </MultiObjectManagementPage>
</template>
```

### 9.4 Detailed Design

#### 9.4.1 配置结构 — 最小 pageConfig（单一事实源原则）

**设计原则：hierarchies.yaml 是唯一权威来源。层级对象的 Tab 生成、过滤映射、标签图标全部从 YAML 自动推导，不重复配置。**

##### 9.4.1.1 hierarchies.yaml 已具备的推导信息

```yaml
# hierarchies.yaml — 唯一事实源
levels:
  - level: 2, object: domain,          display_name: 领域,   ui.icon: business,   filter_field: id, filter_param: version_id
  - level: 3, object: sub_domain,      display_name: 子领域, ui.icon: account_tree, filter_field: id, filter_param: domain_id
  - level: 4, object: service_module,  display_name: 服务模块, ui.icon: widgets,  filter_field: id, filter_param: sub_domain_id
  - level: 5, object: business_object, display_name: 业务对象, ui.icon: description, filter_field: id, filter_param: service_module_id

api_mappings:
  by_dimension:
    domain:          → api_params: [{param: id,                source: checked_ids}]
    sub_domain:      → api_params: [{param: domain_id,         source: domain_ids}]
    service_module:  → api_params: [{param: sub_domain_id,     source: sub_domain_ids}]
    business_object: → api_params: [{param: service_module_id, source: service_module_ids}]
```

##### 9.4.1.2 自动推导规则

```
层级对象（domain / sub_domain / service_module / business_object）— 零配置：

  objectTypes 中的每个层级对象 → 从 hierarchies.yaml 查询其 level 定义 →
  
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ ① Tab label   = level.display_name    (备选: useHierarchyTypes.getLabel) │
  │ ② Tab icon    = level.ui.icon          (备选: useHierarchyTypes.getIcon) │
  │ ③ API 参数    = api_mappings.by_dimension[object].api_params             │
  │   例如 domain:         {param: id,                source: checked_ids}   │
  │        sub_domain:     {param: domain_id,         source: domain_ids}    │
  │        service_module: {param: sub_domain_id,     source: sub_domain_ids}│
  │        business_object:{param: service_module_id, source: service_module_ids}
  │ ④ scope 字段  = api_params[].source 对应 scopeSelection 字段              │
  │    checked_ids    → scopeSelection.selectedDomainIds 等                    │
  │    domain_ids     → scopeSelection.effectiveDomainIds                      │
  │    sub_domain_ids → scopeSelection.effectiveSubDomainIds                   │
  │    service_module_ids → scopeSelection.selectedServiceModuleIds            │
  └─────────────────────────────────────────────────────────────────────────┘

非层级对象（relationship）— 最小配置：

  hierarchies.yaml 中没有 relationship 的 level 定义（它不属于主线层级）→
  必须手动指定过滤映射。
```

##### 9.4.1.3 突破：侧边栏面板完全自动推导

**关键发现：侧边栏的三个面板都可以从 YAML 自动推导，无需 pageConfig 配置。**

**面板推导规则：**

```
objectTypes = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']

  Step 1: 扫描 hierarchies.yaml levels → 判断哪些对象有层级定义
    domain ✅ (level:2), sub_domain ✅ (level:3), service_module ✅ (level:4), business_object ✅ (level:5)
    relationship ❌ (不在 levels 中)

  Step 2: 扫描各对象 YAML 的 cross_table_filters
    relationship.yaml → cross_table_filters: [annotation_category, annotation_content_search]
    business_object.yaml → cross_table_filters: [annotation_category, annotation_content_search]

  Step 3: 自动构建面板
    ┌──────────────────────────────────────────────────────────────────┐
    │ ① 对象范围 (Object Scope)                                       │
    │    来源: hierarchies.yaml levels                                │
    │    内容: domain → sub_domain → service_module 树                │
    │    触发: objectTypes 中存在 hierarchy 对象                       │
    │    label: hierarchy.name = "业务层级"                            │
    │    defaultExpanded: true                                         │
    ├──────────────────────────────────────────────────────────────────┤
    │ ② 关系范围 (Relation Scope)                                     │
    │    来源: objectTypes 包含 'relationship'                        │
    │    内容: 关系类型 tree + FK 关联入口                             │
    │    触发: objectTypes.includes('relationship')                   │
    ├──────────────────────────────────────────────────────────────────┤
    │ ③ 过滤条件 (Filter Conditions)                                  │
    │    来源: 所有对象 YAML 的 cross_table_filters                    │
    │    内容: 过滤组下拉多选（全局 + Tab特定）                        │
    │    触发: 任意对象有 cross_table_filters                          │
    └──────────────────────────────────────────────────────────────────┘
```

**面板排序：层级（hierarchy）在上，全局/共享（global）在下。**

##### 9.4.1.4 突破：全局过滤条件自动检测

**关键发现：同一个 `cross_table_filter` 出现在多个对象的 YAML 中 = 全局过滤。**

```yaml
# 证据：annotation_category 同时出现在两个 YAML 中
# relationship.yaml:
cross_table_filters:
  - id: annotation_category
    where_conditions:
      - parameter: annotation_category    ← 同一个 parameter

# business_object.yaml:
cross_table_filters:
  - id: annotation_category
    where_conditions:
      - parameter: annotation_category    ← 同一个 parameter
```

**全局过滤自动检测规则：**

```javascript
function autoDeriveGlobalFilters(objectSchemas) {
  // 1. 收集所有对象 YAML 的 cross_table_filters
  const paramMap = new Map()
  for (const schema of objectSchemas) {
    for (const filter of (schema.cross_table_filters || [])) {
      // 以 where_conditions[0].parameter 为 key
      const param = filter.association?.where_conditions?.[0]?.parameter
      if (!param) continue
      if (paramMap.has(param)) {
        paramMap.get(param).objects.push(schema.id)
      } else {
        paramMap.set(param, {
          filter,
          objects: [schema.id],
          param,
          scopeField: `${schema.id}Categories` // 或统一命名
        })
      }
    }
  }

  // 2. 判断全局 vs Tab 特定
  const global = []
  const tabSpecific = {}
  for (const [param, entry] of paramMap) {
    if (entry.objects.length >= 2) {
      // 出现在 ≥2 个对象中 → 全局
      global.push({
        scopeField: 'annotationCategories',  // 统一 scope 字段
        apiParam: `${param}__in`,
        id: entry.filter.id,
        label: entry.filter.ui?.filter_label || entry.filter.display_name,
        scope: 'global',
        scopeHint: '(全局)',
        enumType: entry.filter.ui?.enum_type,
        controlType: entry.filter.ui?.filter_type || 'multi-select',
        appliesTo: entry.objects
      })
    } else {
      // 只出现在 1 个对象 → Tab 特定
      const obj = entry.objects[0]
      tabSpecific[obj] = [...(tabSpecific[obj] || []), {
        scopeField: `filter${capitalize(obj)}Types`,
        apiParam: `${param}__in`,
        id: entry.filter.id,
        label: entry.filter.ui?.filter_label || entry.filter.display_name,
        scope: `tab:${obj}`,
        scopeHint: `(仅${obj}页)`,
        enumType: entry.filter.ui?.enum_type,
        controlType: entry.filter.ui?.filter_type || 'multi-select'
      }]
    }
  }

  return { global, tabSpecific }
}
```

**推导结果：**

```
annotation_category: appears in [relationship, business_object] → 全局 ✅
annotation_content_search: appears in [relationship, business_object] → 全局 ✅

pageConfig.globalFilters → ❌ 删除（自动检测）
pageConfig.filterSection → ❌ 删除（自动生成）
```

##### 9.4.1.5 最终绝对最小 pageConfig

**所有可能推导的内容全部自动推导。仅保留无法推导的极少配置。**

```javascript
// MultiObjectManagementPage 所需的最小 pageConfig
// 注意：sidebar/globalFilters/filterSection 全部自动推导，无需配置
const pageConfig = {
  defaultTab: 'relationship',

  // 工具栏：产品/版本 + 导入/导出按钮（按钮 visible 从 YAML import_export 自动推导）
  toolbar: { type: 'global', compact: true },

  // relationship 自身属性过滤
  // relation_code / category_types 是 relationship 自身的字段属性
  // relationCodes 来自 RelationScopeSection 树选择
  // filterRelationCodes 来自 filterSection 下拉选择
  // categoryTypes 来自 hierarchy_scopes 计算
  tabFilters: {
    relationship: {
      scopeEntry: 'both',  // source/target/both — 决定 scope FK 链过滤入口
      ownFields: [
        { scopeField: 'relationCodes',       apiParam: 'relation_code__in' },
        { scopeField: 'categoryTypes',       apiParam: 'category_types__in' },
        { scopeField: 'filterRelationCodes', apiParam: 'relation_code__in', merge: 'intersection' }
      ]
    }
  }
}
```

##### 9.4.1.6 配置来源最终对比

```
                              hierarchies.yaml    {object}.yaml          pageConfig
                              自动推导             自动推导                手动配置
                              ───────────────     ───────────────        ──────────
domain/sub_domain/
service_module/business_object:
  Tab label/icon             ✅ level             ✅ semantics             -
  Tab 过滤映射                ✅ api_mappings       -                      -
  上下文过滤(version_id)      ✅ filter_param       ✅ context.field        -
  导入/导出按钮 visible       -                    ✅ import_export         -

relationship:
  Tab label/icon             -                    ✅ display_name          -
  上下文过滤(version_id)      -                    ✅ context.field         -
  导入/导出按钮 visible       -                    ✅ import_export         -
  scope→bo FK 链过滤          ✅ FK链遍历           ✅ source_bo_id FK       -
  relation_code 过滤           -                    ❌ 自身属性               ✅ ownFields
  category_types 过滤          -                    ❌ 自身属性               ✅ ownFields
  filterRelationCodes 过滤     -                    -                      ✅ ownFields

sidebar.panels:              ✅ levels 层级链       ✅ cross_table_filters   ❌ 零配置
  - 对象范围面板              ✅ has hierarchy       -                      ❌ 零配置
  - 关系范围面板              -                    ✅ relationship 存在      ❌ 零配置
  - 过滤条件面板              -                    ✅ cross_table_filters   ❌ 零配置

globalFilters:               -                    ✅ ≥2对象共有 filter     ❌ 零配置
filterSection.groups:        -                    ✅ cross_table_filters   ❌ 零配置
  - 全局/共享                 -                    ✅ ≥2 objects → global   ❌ 零配置
  - Tab 特定                  -                    ✅ 1 object → tab        ❌ 零配置
scopeEntry:                  ❌ 页面语义            ❌ 页面语义              ✅ 需配置
defaultTab:                  ❌ 页面语义            ❌ 页面语义              ✅ 需配置
toolbar:                     ❌ 页面语义            ❌ 页面语义              ✅ 需配置
```

**结论：pageConfig 从最初的 ~30 行缩减到 ~10 行，仅保留 2 种配置：**
1. **对象自身属性**（relationship 的 relation_code / category_types / scopeEntry）
2. **页面语义偏好**（defaultTab、toolbar 类型）

##### 9.4.1.7 FK 链自动推导详解（relationship scope 过滤）

**关键洞察：relationship 通过 `source_bo_id` / `target_bo_id` FK 关联到 business_object，再通过 hierarchy FK 链关联到 service_module / sub_domain / domain。这是纯 FK 链，100% 可从 YAML 推导。**

```
YAML 中已声明的 FK 关联链：
───────────────────────────────────────────────────────────────────────────
relationship.source_bo_id ──FK──→ business_object.id
  relationship.yaml: source_bo_id.semantics.resolve_to_object: business_object

business_object.service_module_id ──FK──→ service_module.id
  business_object.yaml: hierarchy.parent_field: service_module_id

service_module.sub_domain_id ──FK──→ sub_domain.id
  hierarchies.yaml level: parent_object: sub_domain

sub_domain.domain_id ──FK──→ domain.id
  hierarchies.yaml level: parent_object: domain
```

**FK 链遍历推导规则：**

```
scope 选择了 service_module[5]

  Step 1: 向上/向下遍历 FK 链获取关联的 business_object IDs
    → SELECT id FROM business_objects WHERE service_module_id IN (5)
    → effectiveBoIds = [BO-1, BO-2, BO-3]

  Step 2: relationship 的 source_bo_id / target_bo_id FK → business_object
    → relationship Tab 自动生成过滤:
      filters.source_bo_id__in = [BO-1, BO-2, BO-3]
      OR  filters.target_bo_id__in = [BO-1, BO-2, BO-3]
    （入口点 source vs target vs both 由 scopeEntry 配置控制）
```

**这意味着 pageConfig.tabFilters.relationship 中不需要配 scopeField！**

##### 9.4.1.8 上下文过滤（version_id）— 已是元数据驱动

每个对象 YAML 中已声明 `context.field: version_id`：

```yaml
# domain.yaml, sub_domain.yaml, service_module.yaml,
# business_object.yaml, relationship.yaml — 全部包含:
context:
  field: version_id
  description: "版本上下文，所有查询自动注入 version_id 过滤"
```

`useVersionContext` composable 读取此元数据，自动在 `combinedFilters` 中注入 `version_id`。**GlobalToolbar 的产品/版本选择 → filterFlow 中的 version_id 上下文过滤 → 全链路元数据驱动，无需 pageConfig 配置。**

##### 9.4.1.9 导入导出 — 已是元数据驱动

每个对象 YAML 中已声明 `import_export` 配置：

```yaml
# domain.yaml:
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: true       # 级联导出子对象

# audit_log.yaml:
import_export:
  import_enabled: false      # 审计日志不支持导入
  export_enabled: true
```

**GlobalToolbar 的导入/导出按钮 visible 应从当前 activeTab 对应对象 YAML 的 `import_export.enabled` 自动推导，无需 pageConfig 配置。**

#### 9.4.2 useMultiObjectPage Composable

```javascript
// src/composables/useMultiObjectPage.js
import { computed, reactive, ref } from 'vue'
import { useHierarchyTypes } from './useHierarchyTypes'
import { useVersionContext } from './useVersionContext'
import { useFilterFlow } from './useFilterFlow'
import { useContextFilterSource } from './filterSources/useContextFilterSource'
import { useScopeFilterSource } from './filterSources/useScopeFilterSource'

export function useMultiObjectPage(objectTypes, config = {}) {
  // 1. 层级类型元数据
  const hierarchyTypes = useHierarchyTypes()

  // 2. 自动生成 Tabs
  const tabs = computed(() =>
    objectTypes.map(type => ({
      name: type,
      label: config.tabs?.[type]?.label || hierarchyTypes.getLabel(type),
      icon: hierarchyTypes.getIcon(type)
    }))
  )

  // 3. 版本上下文 + filterFlow
  const versionContext = useVersionContext({ autoLoadProducts: true, autoRestore: true })
  const filterFlow = useFilterFlow({ aggregator: { strategy: 'merge' } })
  const contextSource = useContextFilterSource({ id: 'version-context', contextField: 'version_id' })
  filterFlow.registerSource(contextSource.source)
  const scopeSource = useScopeFilterSource({ id: 'multi-object-scope' })
  filterFlow.registerSource(scopeSource.source)

  // 4. Scope 选择状态（通用结构）
  const scopeSelection = reactive({
    boIds: [],
    relationCodes: [],
    categoryTypes: [],
    selectedDomainIds: [],
    selectedSubDomainIds: [],
    selectedServiceModuleIds: [],
    effectiveDomainIds: [],
    effectiveSubDomainIds: [],
    annotationCategories: [],
    filterRelationCodes: []
  })

  // 5. 侧边栏 & 过滤条件 — 全部自动推导
  const objectSchemas = useObjectSchemas(objectTypes)  // 加载所有对象的 YAML schema
  const { sidebarConfig, filterGroups, globalFilters, tabFilterGroups } = autoDeriveUIConfig(objectTypes, hierarchyConfig, objectSchemas)

  // 6. 过滤策略构建（层级对象从 YAML 自动推导 + pageConfig ownFields 合并）
  const filterStrategies = buildFilterStrategies(config.tabFilters || {}, hierarchyConfig, objectSchemas)

  // 7. combinedFilters（完全配置驱动）
  const combinedFilters = computed(() => {
    const baseFilters = { version_id: versionContext.selectedVersionId.value }
    let result = { ...baseFilters }

    // 全局过滤（自动检测：cross_table_filters 中出现在 ≥2 个对象的参数）
    for (const gf of globalFilters) {
      const scopeVal = scopeSelection[gf.scopeField]
      if (scopeVal && scopeVal.length > 0) {
        result[gf.apiParam] = scopeVal.join(',')
      }
    }

    // Tab 特定过滤
    const strategy = filterStrategies[activeTab.value]
    if (strategy) {
      result = strategy(scopeSelection, result)
    }

    return result
  })

  return {
    tabs, activeTab, versionContext, scopeSelection,
    combinedFilters, filterFlow, scopeSource, contextSource,
    sidebarConfig, filterGroups, globalFilters, tabFilterGroups   // 用于渲染
  }
}

// ========================================
// 自动推导侧边栏 & 过滤条件
// ========================================
function autoDeriveUIConfig(objectTypes, hierarchyConfig, objectSchemas) {
  // 1. 自动推导侧边栏面板
  const hasHierarchy = objectTypes.some(t =>
    hierarchyConfig.hierarchies?.[0]?.levels?.some(l => l.object === t)
  )
  const hasRelationship = objectTypes.includes('relationship')
  const allCrossFilters = objectSchemas.some(s =>
    s.cross_table_filters?.length > 0
  )

  const sidebarConfig = {
    type: hasHierarchy || hasRelationship ? 'scope-tree' : 'none',
    panels: []
  }
  if (hasHierarchy) {
    sidebarConfig.panels.push({
      id: 'object_scope',
      title: hierarchyConfig.hierarchies?.[0]?.name || '对象范围',
      defaultExpanded: true
    })
  }
  if (hasRelationship) {
    sidebarConfig.panels.push({
      id: 'relation_scope',
      title: '关系范围'
    })
  }
  if (allCrossFilters) {
    sidebarConfig.panels.push({
      id: 'filter_conditions',
      title: '过滤条件'
    })
  }

  // 2. 自动检测全局 vs Tab 特定过滤
  const paramMap = new Map()
  for (const schema of objectSchemas) {
    for (const filter of (schema.cross_table_filters || [])) {
      const param = filter.association?.where_conditions?.[0]?.parameter
      if (!param) continue
      if (paramMap.has(param)) {
        paramMap.get(param).objects.push(schema.id)
      } else {
        paramMap.set(param, {
          id: filter.id,
          label: filter.ui?.filter_label || filter.display_name,
          enumType: filter.ui?.enum_type,
          filterType: filter.ui?.filter_type || 'multi-select',
          objects: [schema.id],
          param
        })
      }
    }
  }

  const globalFilters = []       // 全局：≥2 对象共有
  const tabFilterGroups = {}     // Tab特定：仅 1 对象
  const filterGroups = []        // 用于 RelationFilterSection 渲染

  for (const [, entry] of paramMap) {
    if (entry.objects.length >= 2) {
      globalFilters.push({
        id: entry.id,
        scopeField: inferScopeField(entry.param),
        apiParam: `${entry.param}__in`
      })
      filterGroups.push({
        id: entry.id,
        label: entry.label,
        scope: 'global',
        scopeHint: '(全局)',
        enumType: entry.enumType,
        controlType: entry.filterType
      })
    } else {
      const obj = entry.objects[0]
      tabFilterGroups[obj] = [...(tabFilterGroups[obj] || []), {
        id: entry.id,
        scopeField: `filter${capitalize(obj)}Types`,
        apiParam: `${entry.param}__in`
      }]
      filterGroups.push({
        id: entry.id,
        label: entry.label,
        scope: `tab:${obj}`,
        scopeHint: `(仅${obj}页)`,
        enumType: entry.enumType,
        controlType: entry.filterType,
        disabledWhen: (tab) => tab !== obj
      })
    }
  }

  return { sidebarConfig, filterGroups, globalFilters, tabFilterGroups }
}

function inferScopeField(param) {
  // annotation_category → annotationCategories
  return param.replace(/_([a-z])/g, (_, c) => c.toUpperCase()) + 's'
}

// ========================================
// buildFilterStrategies
// ========================================
function buildFilterStrategies(customTabFilters, hierarchyConfig) {
  const strategies = {}

  // 第一步：从 hierarchies.yaml api_mappings 自动推导层级对象过滤
  for (const [dimension, mapping] of Object.entries(hierarchyConfig.api_mappings?.by_dimension || {})) {
    const apiParams = mapping.api_params || []
    strategies[dimension] = (scope, filters) => {
      for (const ap of apiParams) {
        // api_mappings 中 source 映射到 scopeSelection 字段：
        //   checked_ids       → scopeSelection.selected{Dimension}Ids
        //   domain_ids        → scopeSelection.effectiveDomainIds
        //   sub_domain_ids    → scopeSelection.effectiveSubDomainIds
        //   service_module_ids→ scopeSelection.selectedServiceModuleIds
        const scopeField = resolveScopeField(ap.source, dimension)
        const val = scope[scopeField]
        if (val && val.length > 0) {
          filters[ap.param + '__in'] = val.join(',')
        }
      }
      return filters
    }
  }

  // 第二步：合并 pageConfig 中手动配置的非层级对象过滤（如 relationship ownFields）
  for (const [tab, config] of Object.entries(customTabFilters || {})) {
    strategies[tab] = (scope, filters) => {
      // 2a. 先处理 FK 链推导：遍历该对象的 FK 字段，沿 FK 链获取 scope 关联的 ID
      //     例如 relationship 的 source_bo_id FK → business_object → service_module
      const objectSchema = getObjectSchema(tab)
      if (objectSchema && hasScopeSelection(scope)) {
        const fkChainIds = traverseFkChain(scope, objectSchema, hierarchyConfig)
        if (fkChainIds.length > 0) {
          // 根据 scopeEntry 决定过滤 source 还是 target
          const entry = config.scopeEntry || 'both'
          if (entry === 'source' || entry === 'both') {
            filters['source_bo_id__in'] = fkChainIds.join(',')
          }
          if (entry === 'target' || entry === 'both') {
            filters['target_bo_id__in'] = fkChainIds.join(',')
          }
        }
      }

      // 2b. 再处理该对象自身属性过滤（非 FK 关联）
      for (const f of (config.ownFields || [])) {
        const val = scope[f.scopeField]
        if (!val || val.length === 0) continue
        if (f.merge === 'intersection') {
          const existing = filters[f.apiParam]?.split(',') || []
          const combined = existing.length > 0
            ? existing.filter(r => val.includes(r))
            : val
          if (combined.length > 0) filters[f.apiParam] = combined.join(',')
        } else {
          filters[f.apiParam] = val.join(',')
        }
      }
      return filters
    }
  }

  return strategies
}

// FK 链遍历：从当前对象沿 FK 关联链向上/向下查找 scope 关联的目标 ID
// 例如 scope 选了 service_module[5]，沿 FK 链找到 service_module→business_object 的 ID
function traverseFkChain(scope, objectSchema, hierarchyConfig) {
  // 1. 确定 scope 的入口层级
  let scopeIds = null
  if (scope.effectiveDomainIds?.length > 0) {
    scopeIds = { ids: scope.effectiveDomainIds, from: 'domain' }
  } else if (scope.effectiveSubDomainIds?.length > 0) {
    scopeIds = { ids: scope.effectiveSubDomainIds, from: 'sub_domain' }
  } else if (scope.selectedServiceModuleIds?.length > 0) {
    scopeIds = { ids: scope.selectedServiceModuleIds, from: 'service_module' }
  }

  if (!scopeIds) return []

  // 2. 遍历层级链从 scope 入口到 target 对象
  //    例如 scope=service_module, target=business_object:
  //    链: service_module → 通过 hierarchies.yaml levels 向下 → business_object
  const chain = buildFkChain(scopeIds.from, objectSchema.id, hierarchyConfig)
  // chain = ['service_module', 'business_object']

  // 3. 获取最终层级的 IDs（这里是 business_object 的 IDs）
  //    实际需调用后端 API 或从 scopeSelection.boIds 获取
  if (objectSchema.id === 'business_object' || chain[chain.length - 1] === 'business_object') {
    return scope.boIds || []
  }
  // 如果是 relationship，business_object 已经是目标
  // 当前 ObjectScopeSection 已经计算了 boIds（在 handleObjectScopeChange 中）
  return scope.boIds || []
}

// 从 scope 入口层级构建到目标对象的 FK 链
function buildFkChain(fromObject, toObject, hierarchyConfig) {
  const levels = hierarchyConfig.hierarchies?.[0]?.levels || []
  const fromLevel = levels.find(l => l.object === fromObject)
  const toLevel = levels.find(l => l.object === toObject)
  if (!fromLevel || !toLevel) return []

  const chain = []
  let current = fromLevel.level
  const direction = fromLevel.level < toLevel.level ? 1 : -1
  while (current !== toLevel.level) {
    chain.push(levels.find(l => l.level === current)?.object)
    current += direction
  }
  chain.push(toObject)
  return chain
}

// scope 字段映射：api_mappings source → scopeSelection 字段名
function resolveScopeField(source, dimension) {
  const mapping = {
    checked_ids: `selected${capitalize(dimension)}Ids`,
    domain_ids: 'effectiveDomainIds',
    sub_domain_ids: 'effectiveSubDomainIds',
    service_module_ids: 'selectedServiceModuleIds'
  }
  return mapping[source] || `${source}Ids`
}
```

#### 9.4.3 层级过滤推导逻辑

```
hierarchies.yaml:
  levels:
    domain →        filter_field: id,     filter_param: version_id
    sub_domain →    filter_field: id,     filter_param: domain_id
    service_module→ filter_field: id,     filter_param: sub_domain_id
    business_object→filter_field: id,     filter_param: service_module_id

推导规则:
  对象范围勾选 domain[1,2]
    → effectiveDomainIds = [1,2]
    → domain 自身的 filter_field = id
    → API: id__in=1,2                        ✅ 可推导

  对象范围勾选 service_module[5]
    → selectedServiceModuleIds = [5]
    → business_object 的 filter_param = service_module_id
    → API: service_module_id__in=5            ✅ 可推导
```

### 9.5 分类总结：通用 vs 配置

| 能力 | 类型 | 推导来源 |
|------|------|----------|
| objectTypes → Tabs 自动生成 | **通用**（内置） | 组件内部 |
| Tab 切换 + key 刷新 | **通用**（内置） | 组件内部 |
| useVersionContext + filterFlow | **通用**（内置） | composable |
| MasterDetailLayout 布局 | **通用**（内置） | 组件内部 |
| GlobalToolbar | **通用**（内置） | 组件内部 |
| 上下文过滤 (version_id) | **元数据驱动** | `{object}.yaml` → `context.field` |
| 导入/导出按钮 visible | **元数据驱动** | `{object}.yaml` → `import_export.enabled` |
| CollapsiblePanel 手风琴 | **通用**（内置） | 组件内部 |
| Tabs label/icon 自动生成 | **自动推导** | `hierarchies.yaml` + `{object}.yaml` |
| 层级对象 Tab→Filter 映射 | **自动推导** | `hierarchies.yaml` api_mappings |
| relationship scope FK 链过滤 | **自动推导** | `relationship.yaml` FK + `hierarchies.yaml` levels |
| relationship 自身属性过滤 | **配置** | `pageConfig.tabFilters.relationship.ownFields` |
| 全局过滤字段 | **配置** | `pageConfig.globalFilters` |
| 过滤条件面板 Groups | **配置** | `pageConfig.filterSection` |
| 侧边栏类型选择 | **配置** | `pageConfig.sidebar` |
| 自定义单元格渲染 | **插槽扩展** | 组件插槽 |
| Tab-extra 状态信息 | **插槽扩展** | 组件插槽 |

### 9.6 配置推导策略（单一事实源）

**核心原则：YAML 是唯一权威来源。所有能推导的零配置，所有必须配置的仅限业务语义和 UI 偏好。**

| 推导来源 | 适用场景 | 推导方式 |
|---------|---------|----------|
| **`hierarchies.yaml` levels** | 层级对象 label/icon | `level.display_name` / `level.ui.icon` |
| **`hierarchies.yaml` api_mappings** | 层级对象过滤映射 | `api_mappings.by_dimension[object].api_params` |
| **`hierarchies.yaml` levels FK 链** | relationship scope FK 链 | `source_bo_id` FK → `business_object` hierarchy.parent_field → FK 链遍历 |
| **`{object}.yaml` context.field** | 上下文过滤 (version_id) | `context.field → baseFilter` |
| **`{object}.yaml` import_export** | 导入/导出按钮 visible | `import_export.import_enabled / export_enabled` |
| **`{object}.yaml` display_name** | Tab label（非层级对象） | `name` / `display_name_field` |
| **`{object}.yaml` FK fields** | FK 关联定义 | `semantics.resolve_to_object` + `parent_key` |
| **`pageConfig`** | 自身属性过滤 + 全局语义 + UI 偏好 | 仅 3 类：ownFields / globalFilters / UI layout

### 9.7 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| 保持现状 | 无需改动 | switch-case 硬编码，不可复用 | Rejected |
| 全部硬编码在组件 | 简单直接 | 无复用价值 | Rejected |
| 全部手动配置 tabFilters | 灵活 | 层级对象的配置与 hierarchies.yaml 重复，违反单一事实源 | Rejected |
| 完全从 YAML 推导一切 | 最自动化 | relationship 不在 YAML 中，全局过滤无法推导 | Rejected |
| **YAML 自动推导 + pageConfig 仅补缺** | 单一事实源，最小配置 | 需要确保 YAML 信息完整 | **Selected** |
| pageConfig Props 传入 | 快速落地 | 运行时不可改 | Phase 1 |
| 后端 API 动态加载 YAML | 运行时配置驱动 | 开发周期长 | Phase 2（可选） |

### 9.8 Implementation Plan

1. **Phase 1 - Composable**: 创建 `src/composables/useMultiObjectPage.js`
2. **Phase 2 - Component**: 创建 `src/components/common/MultiObjectManagementPage/`
3. **Phase 3 - Migration**: 重构 `RelationshipManagement.vue` 使用新组件
4. **Phase 4 - Verification**: 构建验证 + 功能测试

#### Testing Strategy

- Unit: `useMultiObjectPage` 中 `buildFilterStrategies` 函数
- Integration: MultiObjectManagementPage 组件渲染各 Tab
- E2E: 各 Tab 切换、过滤条件传递、列表刷新

#### Rollback Plan

- 保留原 RelationshipManagement.vue Git 历史
- 通过路由配置可切换新旧版本

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|--------------------|-----------|
| TBD-1 | 是否需要从后端 API 加载 pageConfig（YAML） | 第一阶段 Props 配置是否满足需求 | 先实现 Props 配置，后续评估是否引入 YAML |
| TBD-2 | 侧边栏是否只有 scope-tree 和 object-tree 两种 | 是否有其他面板类型需求 | 先支持两种，后续按需扩展 |
| TBD-3 | 是否需要支持跨组件通信场景 | useMultiObjectPage 需要暴露哪些方法给父组件 | 按需暴露 |

---
