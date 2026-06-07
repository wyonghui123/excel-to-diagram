# Spec: MultiObjectPage 通用过滤模型抽象与实现

## 1. Background & Objectives

### 1.1 Background

MultiObjectPage 是一个通用多对象管理页面，输入一组 `objectTypes`（如 `['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']`），自动生成带 Tab 切换的列表管理界面。左侧对象树（`RelationScopeTree`）提供层级勾选过滤，右侧列表按 Tab 展示对应对象数据。

当前实现已经具备较好的元数据驱动基础（`useMultiObjectPage`、`useHierarchyTypes`、`useFilterFlow` 等），但存在以下不足：

1. **层级关系类型隐式化**：`business_object`↔`service_module` 的 **Composition**（组合/归属）关系与 `domain`→`sub_domain` 的 **FK**（外键引用）关系在代码中混为一体，都通过 `getParentType()` + FK 回退处理，缺乏显式声明。
2. **Object 类型未区分 Entity 与 Association**：`relationship` 在语义上是 **association object**（描述 entity 之间的关联），而非独立 **entity**（实体）。它作为标准 metaObject 有自己的表、字段、API，用 `MetaListPage` 渲染——但其过滤模型与 entity 不同：scope 派生自 source/target entity 的 scopeIds（entity_scope 维度），而非层级 parent。当前 `_buildHierarchyFilters` 将两种过滤混为一谈。
3. **filter model mappings 散落**：过滤映射关系（如"对象树勾选 domain → sub_domain Tab 用 `domain_id__in` 过滤"）分散在 `_buildHierarchyFilters` 的条件分支中，未抽象为数据驱动配置。
4. **`useHierarchyTypes.js` 双重配置源**：同时存在硬编码的 `DEFAULT_TYPES_CONFIG` 和 YAML 注入的 `metaObject.hierarchies`，不符合"单一事实源"原则。
5. **lazy per-tab 计算**：`combinedFilters` 仅计算当前 activeTab 的过滤，切换 Tab 时重复计算。应改为 scopeIds 变更时 precompute 所有 Tab 的过滤。

### 1.2 核心设计原则 —— 三层模型

基于业界实践（SAP CDS、Salesforce Junction Object、Notion Relation）的研究，MultiObjectPage 采用**语义-存储-展示三层分离**的模型：

```
┌──────────────────────────────────────────────────────────────┐
│  YAML 语义层 (WHAT)                                           │
│                                                              │
│  Entity Object: kind=entity, 有独立的 identity              │
│    domain, sub_domain, service_module, business_object       │
│                                                              │
│  Association Object: kind=association, 描述 entity 之间的连接│
│    relationship: source=business_object, target=business_object│
│    语义上不是实体，本质是 "连接"                               │
└───────────────────────┬──────────────────────────────────────┘
                        │ 分离关注点
┌───────────────────────┴──────────────────────────────────────┐
│  存储层 (WHERE)                                               │
│                                                              │
│  entity objects → 各自的 DB 表（domains, sub_domains, ...）   │
│  association objects → 独立表（relationships）或 FK/Junction  │
│  存储策略是实现细节，不影响语义                                │
└───────────────────────┬──────────────────────────────────────┘
                        │ 渲染策略分离
┌───────────────────────┴──────────────────────────────────────┐
│  展示层 (HOW)                                                 │
│                                                              │
│  所有 object（entity + association）→ MetaListPage（通用列表）│
│                                                              │
│  "association" 是过滤模型概念，不是特殊UI组件：                │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  object kind     │  渲染         │  过滤模型           │   │
│  │  entity          │  MetaListPage │  HierarchyFilter   │   │
│  │  association     │  MetaListPage │  AssociationFilter │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  relationship 是标准 metaObject：有自己的表、字段、API          │
│  渲染与其他 object 完全一致（MetaListPage）                    │
│  唯一不同的是过滤模型如何构建（entity_scope + virtual_class）   │
│                                                              │
│  ObjectDetailPage 中：                                       │
│  - 子对象 Tab → MetaListPage (parent_id=X)                   │
│  - FK 引用 Tab → MetaListPage (fk_field=X)                   │
│  - 关系 Tab    → MetaListPage (source_bo_id=X OR target_bo_id=X) │
│  所有 Tab 都复用同一 MetaListPage 组件                        │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 Business Objectives

- 建立 **统一、可配置、可扩展** 的多对象过滤模型，使新增对象类型和过滤维度无需修改核心代码
- 以 `hierarchies.yaml` 作为层级配置的**单一事实源**（Single Source of Truth），消除硬编码双重配置；各 object YAML 的 `filter` section 不冗余声明可从 hierarchies 推导的信息（如 `filter_by: version_id` → 由 `context_levels` 推导）
- 区分 **entity object** 与 **association object**，为不同类型的 object 提供不同的过滤模型（HierarchyFilter vs AssociationFilter）；展示层统一使用 **MetaListPage**，"association" 是**过滤模型概念**而非特殊 UI 组件。relationship 作为标准 metaObject（有自己的 table/fields/API via `relationship.yaml`），渲染与其他 object 完全一致

### 1.4 User / Stakeholder Objectives

- **开发者**：理解过滤模型的数据流和映射规则，便于维护和扩展
- **架构师**：获得清晰的抽象模型规范，指导后续多对象页面的设计
- **产品/配置人员**：通过 YAML 配置即可定义新的层级关系和过滤规则

---

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence                                               |
| ----------------------- | ---------- | ------------------------------------------------------ |
| Business                | Yes        | 消除硬编码、统一配置源、区分 entity/association，降低维护成本 |
| User/Stakeholder        | Yes        | 开发者/架构师需要清晰的过滤模型规范                      |
| Solution                | Yes        | 三大过滤模型（Hierarchy / Association / Context）+ 配置化 |
| Functional              | Yes        | FR-001 ~ FR-007                                        |
| Nonfunctional           | Yes        | NFR-001 ~ NFR-003                                      |
| External Interface      | Yes        | IF-001: hierarchies.yaml schema extension              |
| Transition              | Yes        | TR-001: 渐进迁移，保持 API 兼容                         |

---

## 3. Functional Requirements

### FR-001: Context 模型 —— 动态公共祖先推导

- **Description**: 系统 MUST 根据输入的 `objectTypes` 自动推导出它们的公共祖先层级，并将祖先层级全局过滤注入所有 API 查询。
- **Acceptance Criteria**:
  - 输入包含 `domain` 及以上对象时，自动推导 `version` 和 `product` 为 context 层级
  - Context 过滤（如 `version_id`）应用于所有 Tab 的 API 请求
  - 支持通过 YAML 配置覆盖自动推导（处理无法推导的复杂场景）
- **Priority**: Should
- **Type Mapping**: Functional / Solution
- **Source**: 用户需求 + 代码分析（当前 `versionContext` 硬编码 product/version）

### FR-002: Hierarchy Filter Model —— 层级过滤抽象

- **Description**: 系统 MUST 支持层级过滤模型（适用于 `kind: entity` 的对象），区分 **1:1 FK 关系** 与 **Composition 关系**，并提供统一的过滤优先级链。
- **Acceptance Criteria**:
  - `hierarchies.yaml` 中每个 level 新增 `relation_type` 字段，取值为 `fk`（外键引用）或 `composition`（组合/归属）
  - **Confirmed**: `business_object` → `service_module` 为 `composition`
  - 1:1 FK 关系（如 domain→sub_domain→service_module）：过滤 = `id__in` → `effective` → `parent_{FK}__in` 回退
  - Composition 关系（如 service_module→business_object）：过滤 = `id__in` → `effective` → `{parent}_id__in`（getChildren 语义）
  - `_buildHierarchyFilters` 根据 `relation_type` 选择过滤策略，消除硬编码分支
- **Priority**: Must
- **Type Mapping**: Functional / Solution
- **Source**: 当前代码中 FK 回退隐式表达 Composition + 用户明确提出的 Composition 模型

### FR-003: Association Filter Model —— 关联过滤模型

- **Description**: 系统 MUST 支持 Association Filter Model（适用于 `kind: association` 的对象，如 `relationship`）。association object 的过滤模型与 entity object 完全不同：其 scope 派生自 source/target entity 的 scopeIds，其维度包含 association_type + virtual_classification。
- **Acceptance Criteria**:
  - `hierarchies.yaml` 新增 `object_kind` 字段，取值为 `entity` 或 `association`
  - 当 `kind: association` 时，系统 MUST 从以下维度构建过滤：
    - `association_type`（静态枚举维度：`relation_code__in`）
    - `virtual_classification`（动态计算维度：`category_types__in`，从 `relationship.yaml` 的 `filter` section 驱动）
    - `entity_scope`（派生维度：`source_bo_id__in` + `target_bo_id__in`）
  - `entity_scope` 支持两种模式：
    - **MultiObjectPage**：从对象树的 `scopeIds.business_object` 派生（多 BO 选中 → `source_bo_id__in` + `target_bo_id__in`）
    - **ObjectDetailPage**：从当前页面 anchor entity 派生（单个 BO → `source_bo_id = ${bo.id} OR target_bo_id = ${bo.id}`）
  - `relationship.yaml` 的 `filter` section 作为 Association Filter 的配置源（已有的 `tree_structure: category`、`tree_levels`）
  - Context 全局过滤（如 `version_id`）不从 `relationship.yaml` 的 `filter_by` 冗余读取，而由 `hierarchies.yaml` 的 `context_levels` 统一推导
  - `useRelationClassifier` 的分类逻辑从 `relationship.yaml` 的 `filter.tree_structure` 配置驱动
  - 对象树 scopeIds 变更 → 自动更新 association 的 `source_bo_id__in` / `target_bo_id__in` 过滤
- **Priority**: Should
- **Type Mapping**: Functional / Solution
- **Source**: 当前 `RelationScopeSection` + `useRelationClassifier` 硬编码分类逻辑 + 用户提出的 entity/association 区分 + ObjectDetailPage 复用场景

### FR-004: Filter Model Mappings —— 过滤到 Object 的映射

- **Description**: 系统 MUST 支持过滤模型到目标 Object 的显式映射，声明哪些过滤键作用于哪些 Object 的 API 查询。
- **Acceptance Criteria**:
  - `hierarchies.yaml` 中每个 level 新增 `filter_mappings` 字段：
    ```yaml
    filter_mappings:
      - target_object: domain
        filter_field: id
        priority: 1
        trigger: selected
      - target_object: sub_domain
        filter_field: domain_id
        priority: 2
        trigger: parent
    ```
  - `scopeFilterKeys` 从 YAML `filter_mappings` 动态推导，不再硬编码
  - `_buildHierarchyFilters`（entity）与 `_buildAssociationFilters`（association）的过滤策略由 `filter_mappings` + `kind` 联合决定
  - `trigger` 枚举：`selected` | `effective` | `parent` | `entity_scope`
    - `entity_scope`：作用于 association objects，由 source/target entity 的 scopeIds 派生
- **Priority**: Must
- **Type Mapping**: Solution / External Interface
- **Source**: 当前 `scopeFilterKeys` 部分硬编码 + `_buildHierarchyFilters` 隐式映射

### FR-005: Filter-to-Filter Interaction —— 过滤模型间作用

- **Description**: 系统 MUST 支持过滤模型之间的级联作用，明确过滤数据的传递链路。
- **Acceptance Criteria**:
  - 对象树选中 → 所有层级 Tab 的过滤（precompute 替代 lazy）
  - 对象树选中 → Association Filter 的 entity_scope（选中 BO scope → `source_bo_id__in` + `target_bo_id__in`）
  - 对象树选中 → 关系树数据范围（现有 autoLoad 机制，保留）
  - 关系树选中 → 关系 Tab 过滤（现有机制，保留）
  - `hierarchies.yaml` 中声明 `filter_dependencies`：
    ```yaml
    filter_dependencies:
      - from: hierarchy_filter
        to: association_filter
        trigger: onScopeChange
        transfer: entity_scope         # 将 entity scope 传递给 association
      - from: hierarchy_filter
        to: tab_filters
        trigger: onScopeChange
    ```
  - scopeIds 变更时 precompute 所有 Tab 的过滤并缓存
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: 当前 lazy per-tab 计算 + autoLoad 机制

### FR-006: Single Source of Truth —— hierarchies.yaml 扩展

- **Description**: `hierarchies.yaml` MUST 成为层级过滤配置的**唯一权威来源**，`useHierarchyTypes.js` 完全从中读取，消除 `DEFAULT_TYPES_CONFIG` 硬编码。
- **Acceptance Criteria**:
  - `useHierarchyTypes.js` 移除 `DEFAULT_TYPES_CONFIG`，完全通过 `inject('metaObject')` 获取配置
  - 当 metaObject 未注入时，提供最小回退（只保留 `levels` 基本信息），而非完整硬编码
  - hierarchies.yaml schema 扩展字段：
    - `object_kind`（entity/association）：每个 level
    - `relation_type`（fk/composition）：每个 level（仅 entity 有效）
    - `source_entity` / `target_entity`：association 类型的 level
    - `filter_mappings`：每个 level 的过滤-Object 映射列表
    - `context_levels`：声明哪些层级是 context（祖先）层级
    - `filter_dependencies`：声明过滤模型间依赖
  - association object 的过滤配置从对应 object YAML 的 `filter` section 读取（已有 `relationship.yaml` 中的 `tree_structure`、`tree_levels`）
    - Context 全局过滤（如 `version_id`）**不在**各 object YAML 的 `filter_by` 中冗余声明，由 `hierarchies.yaml` 的 `context_levels` 统一推导
  - 所有新增字段配合 `_template.yaml` 提供 schema 默认值
- **Priority**: Must
- **Type Mapping**: Solution / External Interface
- **Source**: 用户明确提出的 "单一事实" 原则

### FR-007: Precompute Filters —— 预计算所有 Tab 过滤

- **Description**: 系统 MUST 在 `scopeIds` 变更时 precompute 所有 Tab 的过滤结果，避免 activeTab 切换时的重复计算。
- **Acceptance Criteria**:
  - `combinedFilters` 不再只计算 `activeTab.value` 的过滤，而是计算所有 Tab 的过滤
  - 新增 `tabFilters` computed（Map<string, object>）：`{ domain: {...}, sub_domain: {...}, ... }`
  - `combinedFilters` 改为 `computed(() => tabFilters.value[activeTab.value] || {})`
  - scopeIds 变更 → 一次性计算所有 Tab 过滤 → 缓存
  - activeTab 切换 → 直接从缓存读取，O(1)
  - Entity tab 用 `_buildHierarchyFilters`，Association tab 用 `_buildAssociationFilters`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 当前 lazy per-tab 重复计算

---

## 4. Nonfunctional Requirements

### NFR-001: 元数据驱动优先于硬编码

- **Description**: 所有过滤逻辑的配置 MUST 来源于 YAML 配置（hierarchies.yaml + 各 object YAML 的 filter section），代码中不得出现针对特定 object type 的硬编码分支。
- **Measurement**: Code review 验证 —— `_buildHierarchyFilters`、`_buildAssociationFilters`、`scopeFilterKeys` 中无 hardcoded object type 名称或 FK 名称
- **Priority**: Must
- **Source**: 架构设计原则

### NFR-002: 测试覆盖

- **Description**: 过滤模型的映射规则 MUST 有单元测试覆盖，`useMultiObjectPage.spec.js` 保持 51+ 测试用例。
- **Measurement**: 测试通过率 100%；新增字段（relation_type、filter_mappings、kind）的过滤策略有独立测试
- **Priority**: Must
- **Source**: 现有测试基础

### NFR-003: 向后兼容

- **Description**: 扩展 hierarchies.yaml 后，现有 MultiObjectManagementPage 的功能 MUST 不受影响。
- **Measurement**: 所有现有页面（领域列表、服务模块列表、关系列表）正常展示、过滤正常工作
- **Priority**: Must
- **Source**: 用户 "继续" 指令隐含不破坏现有功能

---

## 5. External Interface Requirements

### IF-001: hierarchies.yaml Schema Extension

- **Type**: Configuration Interface（YAML Schema）
- **Schema 扩展说明**：

#### 5.1 Level 新增字段 —— Entity 类型

```yaml
levels:
  - level: 3
    object: sub_domain
    kind: entity                        # 新增: entity | association
    display_name: 子领域
    parent_object: domain
    foreign_key_field: domain_id
    relation_type: fk                   # 新增: fk | composition
    cardinality: N:1
    filter_field: id
    filter_param: domain_id
    filter_mappings:                    # 新增: 过滤映射列表
      - target_object: sub_domain
        filter_field: id
        priority: 1
        trigger: selected
      - target_object: sub_domain
        filter_field: id
        priority: 2
        trigger: effective
      - target_object: service_module
        filter_field: domain_id
        priority: 3
        trigger: parent
```

#### 5.2 Level 新增字段 —— Association 类型

```yaml
levels:
  - level: 5
    object: relationship
    kind: association                   # 关联对象
    display_name: 关系列表
    source_entity: business_object      # 新增: 源实体
    target_entity: business_object      # 新增: 目标实体
    association_cardinality: many_to_many
    filter_mappings:                    # association 专用的 trigger 类型
      - target_object: relationship
        filter_field: relation_code
        priority: 1
        trigger: selected
      - target_object: relationship
        filter_field: category_types
        priority: 2
        trigger: effective
      - target_object: relationship
        filter_field: source_bo_id
        priority: 3
        trigger: entity_scope           # 派生自 entity scope
      - target_object: relationship
        filter_field: target_bo_id
        priority: 3
        trigger: entity_scope           # 派生自 entity scope
```

#### 5.3 filter_mappings 字段定义

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_object` | string | 过滤作用的目标 object type |
| `filter_field` | string | API 参数名（`__in` 后缀由运行时自动添加） |
| `priority` | int | 优先级：1=selected, 2=effective, 3=parent/entity_scope |
| `trigger` | string | `selected`（直接勾选）, `effective`（树计算）, `parent`（父级 FK）, `entity_scope`（entity scope 派生） |
| `relation` | string (optional) | `1:1` 或 `composition`，覆盖 level 级 `relation_type` |

#### 5.4 新增 `context_levels` section

```yaml
context_levels:
  - object: version
    context_field: version_id
    derive_from: product
    auto: true
  - object: product
    context_field: product_id
    derive_from: null
    auto: true
```

#### 5.5 新增 `filter_dependencies` section

```yaml
filter_dependencies:
  - id: object_tree_to_tabs
    from: hierarchy_filter
    to: tab_filters
    trigger: onScopeChange
    description: 对象树勾选 → 所有层级 Tab 过滤
  - id: object_tree_to_association
    from: hierarchy_filter
    to: association_filter
    trigger: onScopeChange
    transfer: entity_scope
    description: 对象树勾选 → association 的 entity_scope 过滤（source_bo_id__in + target_bo_id__in）
```

#### 5.6 Association 过滤配置来源（非 hierarchies.yaml）+ 单一事实源规则

association object 的虚拟分类过滤（如 relationship 的 `category_types` 分类树）的配置来源于**对应 object YAML 自身的 `filter` section**（各 object 的 UI 配置保留在其自身 YAML 中）：

```yaml
# relationship.yaml 已有的 filter section
filter:
  layout: sidebar
  filters:
    - key: business_object
      title: 中心范围选择
      type: tree
      tree_structure: hierarchy         # entity 层级过滤（由对象树驱动）
      tree_levels: [domain, sub_domain, service_module, business_object]

    - key: category_type
      title: 关系范围
      type: tree
      tree_structure: category          # 虚拟分类过滤 → AssociationFilterModel 读取
      tree_levels: [scope_type, category_type]

    - key: relation_code
      title: 关系类型
      type: select                      # 关联类型过滤 → AssociationFilterModel 读取
```

**单一事实源规则——消除冗余声明**：

| 信息 | 事实源 | 不在其他 YAML 冗余声明 |
|------|--------|----------------------|
| 层级位置、`kind`、`relation_type` | `hierarchies.yaml` levels[] | — |
| Context 全局过滤（`version_id`、`product_id`） | `hierarchies.yaml` context_levels | ❌ **不再**在各 object YAML 的 `filter_by` 声明 |
| 过滤映射（`trigger`、`filter_field`、`priority`） | `hierarchies.yaml` filter_mappings[] | — |
| 过滤 UI 结构（`tree_structure`、`tree_levels`、`type`） | 各 object YAML 的 `filter` section | — |
| FK 定义、数据字段、CRUD API | 各 object YAML 自身 | — |

例如：`relationship.yaml` 的 `filter: filters[]` 中**不需要**再声明 `filter_by: version_id`，因为 `context_levels` 已定义 `version` 为 context 层级，所有 Tab 自动注入 `version_id` 过滤。

`useRelationClassifier` 的 `tree_structure: category` → groupBy 分类逻辑从该配置驱动。

---

## 6. Transition Requirements

### TR-001: 渐进迁移

- **Description**: hierarchies.yaml 扩展后，`useHierarchyTypes.js` 和 `useMultiObjectPage.js` 渐进迁移到新 schema，不一次性重写。
- **Strategy**:
  1. Phase 1: hierarchies.yaml 新增字段（kind, relation_type, filter_mappings），保持旧字段不动
  2. Phase 2: `useHierarchyTypes.js` 添加读取新字段的能力（getKind, getRelationType, getFilterMappings），优先使用新字段，fallback 到旧逻辑
  3. Phase 3: `useMultiObjectPage` 接入新 API，`_buildHierarchyFilters` 基于 `filter_mappings` 重写，新增 `_buildAssociationFilters`
  4. Phase 4: 新增 `tabFilters` precompute，保持 `combinedFilters` 兼容
  5. Phase 5: 移除 `DEFAULT_TYPES_CONFIG` 硬编码（最后一步）
- **Rollback Plan**: 每个 Phase 可独立回退（新字段有 fallback 时不影响旧行为）
- **Source**: "单一事实" + 渐进式架构演进

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- YAML schema 扩展后需保持 `meta/schemas/hierarchies.yaml` 向后兼容 —— 现有 Python 脚本（如 `menu_auto_generator.py`）可能读取该文件
- `useHierarchyTypes.js` 必须在 `metaObject` 未注入时保持可用（当前通过 `DEFAULT_TYPES_CONFIG` fallback）
- `el-tree` 的 `getHalfCheckedNodes()` API 依赖 Element Plus 版本（已验证可用）

### 7.2 Business Constraints

- 不能破坏现有的 MultiObjectManagementPage 列表功能
- 不引入新的外部依赖

### 7.3 Assumptions

- `hierarchies.yaml` 中的 `metaObject` 会在应用启动时加载到 Vue provide —— Source: Assumed（当前部分实现）
- API 过滤参数约定 `{field}__in` 格式保持不变 —— Source: Verified（当前 API 约定）
- FK 命名约定 `{parent_object}_id` 适用于所有层级对象 —— Source: Verified（YAML 中定义）
- `relationship.yaml` 的 `filter` section 配置由后端/配置脚本维护，前端只读取 —— Source: Assumed
- Context 全局过滤不再在各 object YAML 的 `filter_by` 冗余声明，统一由 `hierarchies.yaml` 的 `context_levels` 推导 —— Source: Confirmed（单一事实源原则）

---

## 8. Priorities & Milestone Suggestions

| ID     | Requirement                    | Priority | Reason                                      |
| ------ | ------------------------------ | -------- | ------------------------------------------- |
| FR-006 | Single Source of Truth         | Must     | 架构基础，所有后续 FR 依赖                    |
| FR-002 | Hierarchy Filter Model         | Must     | Composition 区分是核心诉求                    |
| FR-004 | Filter Model Mappings          | Must     | FR-002 + FR-003 的实现方式                    |
| FR-005 | Filter-to-Filter Interaction   | Must     | 解决当前 lazy per-tab + indeterminate 问题    |
| FR-003 | Association Filter Model       | Should   | 关系 Tab 配置化，Phase 3                      |
| FR-001 | Context Model                  | Should   | 依赖 FR-006，Phase 5                          |
| FR-007 | Precompute Filters             | Should   | 性能优化，Phase 4                             |

**Suggested Milestones**:

| Milestone | Scope                                                                                        |
| --------- | -------------------------------------------------------------------------------------------- |
| M1 (当前) | FR-006 部分：hierarchies.yaml 扩展 `kind` + `relation_type` + `filter_mappings` + `context_levels` + `filter_dependencies` |
| M2        | FR-002 + FR-004：`_buildHierarchyFilters` 接入 `kind`/`relation_type`/`filter_mappings`，`useHierarchyTypes` 读取新字段 |
| M3        | FR-003：`_buildAssociationFilters` 从 `filter_mappings[trigger=entity_scope]` + `relationship.yaml` filter section 构建 |
| M4        | FR-005 + FR-007：precompute `tabFilters`（entity + association），替代 lazy per-tab |
| M5        | FR-006 完整：移除 `DEFAULT_TYPES_CONFIG` 硬编码 + FR-001 Context 动态推导 |

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

#### Current Architecture

```
useMultiObjectPage.js  (编排层)
├── useVersionContext     → contextSource → filterFlow  (version_id)
├── useFilterFlow         → filterSource 注册 + DAG 聚合
├── useHierarchyTypes     → getParentType/getChildType/getLevelIndex
│   ├── metaObject.hierarchies (YAML)  (部分使用)
│   └── DEFAULT_TYPES_CONFIG (硬编码)  (主要使用！)
├── scopeIds              → reactive { [type]: { selected, effective } }
├── scopeFilterKeys       → 硬编码键名集合 (partially dynamic)
├── _buildHierarchyFilters → 3级优先级 (selected→effective→parent FK)  ← entity + association 混用
└── _buildRelationshipFilters → 硬编码 relationship 过滤逻辑
```

#### Current Issues

| Issue | 代码位置 | 严重程度 |
|-------|---------|---------|
| `DEFAULT_TYPES_CONFIG` 与 YAML 双层配置 | `useHierarchyTypes.js` | 高 |
| entity/association 不分，`relationship` 与 `domain` 同等待遇 | `useMultiObjectPage.js` 整体 | 高 |
| `relation_type` 不存在，composition/FK 混为一体 | `useHierarchyTypes.js` 整体 | 中 |
| relationship 过滤逻辑硬编码在 `_buildRelationshipFilters` | `useMultiObjectPage.js:284-315` | 中 |
| `scopeFilterKeys` 部分硬编码 | `useMultiObjectPage.js:209-231` | 中 |
| 关系树分类硬编码 | `useRelationClassifier.js` | 中 |
| lazy per-tab 计算 | `useMultiObjectPage.js:250-254` | 低 |

#### Relevant Code Paths

| 文件 | 职责 |
|------|------|
| [useMultiObjectPage.js](file:///d:/filework/excel-to-diagram/src/composables/useMultiObjectPage.js) | 核心编排 |
| [useHierarchyTypes.js](file:///d:/filework/excel-to-diagram/src/composables/useHierarchyTypes.js) | 层级元数据 |
| [useRelationClassifier.js](file:///d:/filework/excel-to-diagram/src/composables/useRelationClassifier.js) | 关系分类 |
| [useFilterFlow.js](file:///d:/filework/excel-to-diagram/src/composables/useFilterFlow.js) | 过滤流引擎 |
| [hierarchies.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/hierarchies.yaml) | 层级配置 |
| [relationship.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml) | 关系对象配置（含 filter section） |
| [ObjectScopeSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/ObjectScopeSection.vue) | 对象树 |
| [RelationScopeSection.vue](file:///d:/filework/excel-to-diagram/src/components/common/RelationScopeTree/RelationScopeSection.vue) | 关系树 |

### 9.2 Target State

#### Proposed Architecture

```
hierarchies.yaml  ←★★★ 单一事实源（层级配置） ★★★
├── levels[]
│   ├── kind: entity | association
│   ├── relation_type: fk | composition      (entity only)
│   ├── source_entity / target_entity         (association only)
│   ├── filter_mappings[]                     ← 新增
│   │   └── { target_object, filter_field, priority, trigger }
│   └── foreign_key_field (保留)
├── context_levels[]                          ← 新增
├── filter_dependencies[]                     ← 新增
└── dimensions, api_mappings (保留, 可能废弃)

relationship.yaml  filter section  ← association 过滤配置源
└── filters[]
    └── { key, type, tree_structure, tree_levels }

useHierarchyTypes.js
├── 完全从 metaObject.hierarchies 读取
├── 移除 DEFAULT_TYPES_CONFIG
├── 新增: getKind(type) → 'entity' | 'association'
├── 新增: getRelationType(type) → 'fk' | 'composition'
├── 新增: getFilterMappings(type) → FilterMapping[]
├── 新增: getContextLevels() → ContextLevel[]
└── 新增: isEntity(type) / isAssociation(type)

useMultiObjectPage.js
├── scopeIds (保留)
├── tabFilters ← computed(Map<objectType, filters>)      ← 新增 precompute
├── combinedFilters ← tabFilters[activeTab]              ← 简化
├── _buildHierarchyFilters → 读取 filter_mappings, entity 专用   ← 重写
├── _buildAssociationFilters → 读取 filter_mappings + entity_scope ← 新增
└── scopeFilterKeys → 从 filter_mappings 推导            ← 动态化

MultiObjectManagementPage.vue
├── Entity tabs → MetaListPage (保留)
└── Association tab → MetaListPage (保留, 渲染不变, 过滤模型升级为 AssociationFilter)

ObjectDetailPage.vue  ← 所有Tab复用 MetaListPage
├── 基本信息 Tab (保留)
├── 子对象列表 Tab → MetaListPage (parent_id=X)
├── FK 引用 Tab    → MetaListPage (fk_field=X)
└── 关系列表 Tab   → MetaListPage (source_bo_id=X OR target_bo_id=X)
```

#### Key Changes

1. **hierarchies.yaml 扩展**：新增 `kind`、`relation_type`、`source_entity`、`target_entity`、`filter_mappings`、`context_levels`、`filter_dependencies` 七个 section/字段
2. **`useHierarchyTypes.js` 纯 YAML 驱动**：新增 `getKind()`、`getRelationType()`、`getFilterMappings()`、`isEntity()`、`isAssociation()` 方法
3. **`_buildHierarchyFilters` 基于 `filter_mappings`**：用迭代映射替代 if-else 优先级链，区分 entity 和 association
4. **新增 `_buildAssociationFilters`**：处理 association object 的 `entity_scope` trigger（从 source/target entity scopeIds 派生 `source_bo_id__in` / `target_bo_id__in`）
5. **`tabFilters` precompute**：scopeIds 变更时一次性计算所有 Tab 过滤
6. **`scopeFilterKeys` 动态推导**：从所有 level 的 `filter_mappings` 收集不重复的 `filter_field`

### 9.3 Detailed Design

#### 9.3.1 `useHierarchyTypes.js` —— 新增方法

```javascript
const config = computed(() => {
  if (metaObject.value?.hierarchies?.[0]?.levels) {
    return metaObject.value.hierarchies[0]
  }
  return DEFAULT_MINIMAL_CONFIG
})

function getKind(objectType) {
  const level = findLevel(objectType)
  return level?.kind || 'entity'  // 默认 entity，向后兼容
}

function getRelationType(objectType) {
  const level = findLevel(objectType)
  return level?.relation_type || 'fk'
}

function getFilterMappings(objectType) {
  const level = findLevel(objectType)
  return level?.filter_mappings || []
}

function getContextLevels() {
  return config.value.context_levels || []
}

function isEntity(objectType) {
  return getKind(objectType) === 'entity'
}

function isAssociation(objectType) {
  return getKind(objectType) === 'association'
}
```

#### 9.3.2 `useMultiObjectPage.js` —— `_buildHierarchyFilters` 重写（entity 专用）

```javascript
function _buildHierarchyFilters(filters, objectType) {
  const typeScope = scopeIds[objectType]
  if (!typeScope) return filters

  const mappings = hierarchyTypes.getFilterMappings(objectType)
    .slice().sort((a, b) => a.priority - b.priority)

  for (const mapping of mappings) {
    if (mapping.trigger === 'selected' && typeScope.selected.length > 0) {
      filters[`${mapping.filter_field}__in`] = typeScope.selected.join(',')
      return filters
    }
    if (mapping.trigger === 'effective' && typeScope.effective.length > 0) {
      filters[`${mapping.filter_field}__in`] = typeScope.effective.join(',')
      return filters
    }
    if (mapping.trigger === 'parent') {
      const parentType = hierarchyTypes.getParentType(objectType)
      if (parentType && scopeIds[parentType]) {
        const parentScope = scopeIds[parentType]
        const parentIds = parentScope.selected.length > 0
          ? parentScope.selected
          : parentScope.effective.length > 0
            ? parentScope.effective
            : []
        if (parentIds.length > 0) {
          filters[`${mapping.filter_field}__in`] = parentIds.join(',')
          return filters
        }
      }
    }
  }

  return filters
}
```

#### 9.3.3 `useMultiObjectPage.js` —— `_buildAssociationFilters` 新增（association 专用）

```javascript
function _buildAssociationFilters(filters, objectType) {
  const mappings = hierarchyTypes.getFilterMappings(objectType)
    .slice().sort((a, b) => a.priority - b.priority)

  for (const mapping of mappings) {
    // 1. selected / effective：关系树直接勾选
    if (mapping.trigger === 'selected') {
      const sel = scopeIds.relationExtra?.selected?.[mapping.filter_field]
      if (sel && sel.length > 0) {
        filters[`${mapping.filter_field}__in`] = sel.join(',')
        return filters
      }
    }
    if (mapping.trigger === 'effective') {
      const eff = scopeIds.relationExtra?.effective?.[mapping.filter_field]
      if (eff && eff.length > 0) {
        filters[`${mapping.filter_field}__in`] = eff.join(',')
        return filters
      }
    }
    // 2. entity_scope：从 source/target entity 的 scopeIds 派生
    if (mapping.trigger === 'entity_scope') {
      const level = hierarchyTypes.findLevel(objectType)
      const sourceEntity = level?.source_entity
      const targetEntity = level?.target_entity

      if (mapping.filter_field === 'source_bo_id' && sourceEntity) {
        const scope = scopeIds[sourceEntity]
        const ids = scope?.selected.length > 0 ? scope.selected : scope?.effective
        if (ids && ids.length > 0) {
          filters.source_bo_id__in = ids.join(',')
        }
      }
      if (mapping.filter_field === 'target_bo_id' && targetEntity) {
        const scope = scopeIds[targetEntity]
        const ids = scope?.selected.length > 0 ? scope.selected : scope?.effective
        if (ids && ids.length > 0) {
          filters.target_bo_id__in = ids.join(',')
        }
      }
    }
  }

  return filters
}
```

#### 9.3.4 `tabFilters` precompute

```javascript
const tabFilters = computed(() => {
  const result = {}
  objectTypes.forEach(type => {
    if (hierarchyTypes.isEntity(type)) {
      result[type] = _buildHierarchyFilters({}, type)
    } else if (hierarchyTypes.isAssociation(type)) {
      result[type] = _buildAssociationFilters({}, type)
    } else {
      result[type] = {}
    }
  })
  return result
})

const combinedFilters = computed(() => {
  const baseFilters = filterFlow.combinedFilters.value
  const filters = { ...baseFilters }
  scopeFilterKeys.value.forEach(k => delete filters[k])

  Object.keys(scopeIds.globalFilters).forEach(key => {
    const val = scopeIds.globalFilters[key]
    if (Array.isArray(val) && val.length > 0) {
      filters[`${key}__in`] = val.join(',')
    }
  })

  const tabFilter = tabFilters.value[activeTab.value] || {}
  Object.assign(filters, tabFilter)

  return filters
})
```

#### 9.3.5 `scopeFilterKeys` 动态推导

```javascript
const scopeFilterKeys = computed(() => {
  const keys = new Set()
  keys.add('id__in')
  keys.add('annotation_category__in')
  keys.add('relation_code__in')
  keys.add('category_types__in')
  keys.add('source_bo_ids')
  keys.add('target_bo_ids')

  objectTypes.forEach(type => {
    const mappings = hierarchyTypes.getFilterMappings(type)
    mappings.forEach(m => {
      if (m.trigger === 'parent' || m.trigger === 'entity_scope') {
        keys.add(`${m.filter_field}__in`)
      }
    })
  })

  return [...keys]
})
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
| ------ | ---- | ---- | -------- |
| **A) 扩展 hierarchies.yaml + entity/association 区分** | 单一事实源、语义清晰、三层分离 | 需扩展 schema、渐进迁移 | ✅ Selected |
| B) 新建独立 filter_config.yaml | 不影响现有 YAML | 多配置源、维护负担重 | ❌ Rejected（违反单一事实源原则） |
| C) 保持现有硬编码 + 只加注释 | 零改动 | 不解决根本问题 | ❌ Rejected（与目标相悖） |
| D) relationship 不作为独立 object | 简化模型 | 但 relationship 有独立数据、API、Tab，必须作为 object | ❌ Rejected（实际需要） |

**Entity vs Association 区分的设计决策**：

| Option | Pros | Cons | Decision |
| ------ | ---- | ---- | -------- |
| association 用独立 YAML section | 语义最清晰 | 配置冗余 | ❌ Rejected |
| 在 hierarchies.yaml 中用 `kind` 区分 | 单一配置点、语义清晰 | 需扩展现有 schema | ✅ Selected |
| association 的过滤配置保留在各 object YAML 的 `filter` section（已有） | 已有配置、零重复 | 需前端适配读取 | ✅ Selected |

### 9.5 Implementation & Migration Plan

#### Implementation Order

1. **Step 1: hierarchies.yaml 扩展（M1）**
   - 为 6 个 level 添加 `kind`（domain/SM/BO = `entity`, relationship = `association`）
   - 为 entity level 添加 `relation_type`（前三层 = `fk`, BO↔SM = `composition`）✅ TBD-3 resolved
   - 为 association level 添加 `source_entity`、`target_entity`
   - 为 domain、sub_domain、service_module level 添加 `filter_mappings`
   - 为 relationship level 添加 `filter_mappings`（trigger 含 `entity_scope`）
   - 添加 `context_levels` section
   - 添加 `filter_dependencies` section

2. **Step 2: useHierarchyTypes.js 接入新字段（M2）**
   - 新增 `getKind()`、`getRelationType()`、`getFilterMappings()`、`isEntity()`、`isAssociation()` 方法
   - 优先从 YAML 读取，fallback 到旧逻辑
   - 不删除 `DEFAULT_TYPES_CONFIG`（保留为 fallback）

3. **Step 3: useMultiObjectPage 接入新 API（M2-M3）**
   - `_buildHierarchyFilters` 基于 `filter_mappings` 重写（仅处理 entity）
   - 新增 `_buildAssociationFilters`（处理 `trigger=entity_scope`）
   - `scopeFilterKeys` 从 `filter_mappings` 动态推导
   - 保持 `combinedFilters` 兼容

4. **Step 4: tabFilters precompute（M4）**
   - 实现 `tabFilters` computed
   - `combinedFilters` 改为从 `tabFilters[activeTab]` 读取
   - 验证 entity + association Tab 切换过滤正确性

5. **Step 5: 清理硬编码（M5）**
   - 移除 `DEFAULT_TYPES_CONFIG`
   - 保留最小 `DEFAULT_MINIMAL_CONFIG`（metaObject 为空时的回退）
   - FR-001 Context 动态推导

#### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| YAML schema 扩展破坏现有 Python 脚本 | 新增字段添加默认值，Python 脚本使用 `.get()` 安全访问 |
| `metaObject` 未注入导致 `useHierarchyTypes` 无数据 | 保留 `DEFAULT_MINIMAL_CONFIG` fallback（`kind` 默认 `entity`） |
| `filter_mappings` 配置错误导致过滤失效 | 单元测试覆盖所有层级类型的过滤映射 |
| precompute 性能问题（大量 Object 类型） | `tabFilters` 是 computed（惰性 + 缓存），复杂度 O(n × m) 可接受 |

#### Testing Strategy

- **Unit tests**: `useMultiObjectPage.spec.js`
  - `kind=entity` 测试：3 级优先级（selected→effective→parent FK）
  - `kind=entity + relation_type=composition` 测试：composition 回退
  - `kind=association + trigger=entity_scope` 测试：source_bo_id__in / target_bo_id__in 派生
  - `filter_mappings` 测试：验证从 YAML 读取的映射正确生成过滤键
  - `tabFilters` precompute 测试：验证所有 Tab 过滤同时计算
  - 保持现有 51 个测试通过
- **Integration tests**: `webapp-testing` 手动验证
  - 对象树勾选 → entity Tab 过滤正确 + association Tab `source_bo_id__in` / `target_bo_id__in` 正确
  - indeterminate 节点修复保持有效
  - 关系树分类过滤正常
- **E2E tests**: 当前不涉及

#### Rollback Plan

- 每个 Phase 可独立回退（新字段有 fallback 时不影响旧行为）
- Step 1（YAML 扩展）新增字段不影响现有读取逻辑
- Step 2-3（代码读取新字段）通过 `|| fallback` 保证向后兼容
- Step 5（移除硬编码）需在全部验证通过后执行，回退时恢复 `DEFAULT_TYPES_CONFIG`

---

## 10. TBD List

| ID     | Item                                     | Missing Information                                           | Status / Next Step                              |
| ------ | ---------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------- |
| ✅ TBD-3 | `business_object` 的 `relation_type`    | BO↔SM = **composition**                                       | ✅ Confirmed. 写入 YAML                          |
| TBD-1  | `context_levels` 自动推导逻辑            | 当输入的 objectTypes 不在同一棵层级树中时如何处理？           | 当前场景均在同树，M5 采用配置方式                |
| TBD-4  | `DEFAULT_MINIMAL_CONFIG` 回退范围       | metaObject 为空时的最小可用配置应包含哪些字段？               | M5 决定                                         |
| TBD-5  | `filter_mappings` 的 `trigger` 枚举      | 是否需要更多 trigger（ancestor, association_type）？           | 当前 4 种（selected/effective/parent/entity_scope）足用 |

---

Spec 包含 10 sections，最后 section 是 "TBD List"，内容完整。