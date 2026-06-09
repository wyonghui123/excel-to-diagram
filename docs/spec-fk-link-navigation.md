## 目录

1. [0. 与关联导航 Spec 的关系](#0-与关联导航-spec-的关系)
2. [1. Background & Objectives](#1-background-objectives)
3. [2. Requirement Type Overview](#2-requirement-type-overview)
4. [3. Functional Requirements](#3-functional-requirements)
5. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
6. [5. External Interface Requirements](#5-external-interface-requirements)
7. [6. Transition Requirements](#6-transition-requirements)
8. [7. Constraints & Assumptions](#7-constraints-assumptions)
9. [8. Priorities & Milestone Suggestions](#8-priorities-milestone-suggestions)
10. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
11. [10. TBD List](#10-tbd-list)
12. [11. 文件清单](#11-文件清单)
13. [12. 设计决策记录 (ADR)](#12-设计决策记录-(adr))
14. [13. 元数据模型驱动分析](#13-元数据模型驱动分析)

---
# Spec: 详情页模式切换与 FK 链接导航优化

> **版本**: 1.0  
> **状态**: 规划中  
> **日期**: 2026-05-15  
> **关联 Spec**: [spec-association-navigation.md](./spec-association-navigation.md) - 基于列表多选的关联导航

---

## 0. 与关联导航 Spec 的关系

### 0.1 功能对比

| 维度 | spec-association-navigation | 本 Spec (FK 链接导航) |
|------|----------------------------|----------------------|
| **触发入口** | 列表页多选 + 工具栏下拉菜单 | 详情页 FK 字段链接 |
| **导航目标** | 目标对象**列表页** | 目标对象**详情页** |
| **选择模式** | 多选（批量） | 单选（单个 FK） |
| **过滤条件** | 以源对象 ID 列表过滤 | 无（直接打开详情） |
| **已实现** | ✅ 是 | ❌ 否 |

### 0.2 可复用的服务能力

以下能力已在 `spec-association-navigation` 中实现，本 Spec 直接复用：

| 能力 | 来源文件 | 复用方式 |
|------|---------|---------|
| **路由映射表** | `useAssociationNavigation.js` | 直接复用 `routePathMap` |
| **SessionStorage 状态管理** | `useAssociationNavigation.js` | 复用 `saveSourceState/restoreSourceState` |
| **URL 参数命名规范** | `_nav_*` 前缀 | 统一命名空间 |
| **NavigationSourceInfo 组件** | 已实现 | 详情页也可显示来源信息 |
| **container 判断逻辑** | MetaListPage | 复用 `action.container` 判断 |

### 0.3 统一导航基础设施

两个 Spec 共享以下基础设施，形成统一的关联导航体系：

```
┌─────────────────────────────────────────────────────────────┐
│                    关联导航基础设施                           │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              useAssociationNavigation (核心)            │ │
│  │  - routePathMap (路由映射表)                             │ │
│  │  - saveSourceState / restoreSourceState (状态管理)       │ │
│  │  - parseNavigationParams (参数解析)                      │ │
│  │  - navigateBack (返回导航)                               │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│           ┌───────────────┴───────────────┐                 │
│           ▼                               ▼                 │
│  ┌─────────────────────┐      ┌─────────────────────────┐  │
│  │ AssociationNavigation│      │ FkLinkField             │  │
│  │ Menu (列表页多选)     │      │ (详情页 FK 链接)         │  │
│  │ - 多选触发            │      │ - 单击触发               │  │
│  │ - 导航到列表页        │      │ - 导航到详情页           │  │
│  │ - 带过滤条件          │      │ - 无过滤条件             │  │
│  └─────────────────────┘      └─────────────────────────┘  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              NavigationSourceInfo (来源信息栏)          │ │
│  │  - 显示来源对象信息                                      │ │
│  │  - 提供"返回来源"按钮                                    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Background & Objectives

### 1.1 Background

当前 BIP 应用架构管理系统的列表页操作列包含"详情"、"编辑"、"删除"三个按钮，占用较多空间。同时，外键（FK）字段在列表页和详情页仅显示为文本，无法快速导航到关联对象。

业界头部产品（Salesforce、Jira、Linear、Notion）普遍采用：
- 详情页内切换浏览态/编辑态，而非独立入口
- FK 字段作为可点击链接，点击导航到关联对象
- 操作列简化为仅"删除"或合并到下拉菜单

### 1.2 Business Objectives

- 提升数据关联的可发现性和导航效率
- 减少操作列空间占用，提高列表页数据密度
- 统一详情页交互模式，降低用户学习成本

### 1.3 User / Stakeholder (涉众) Objectives

- 用户可通过点击 FK 字段快速跳转到关联对象详情
- 用户可在详情页内一键切换浏览态/编辑态
- 用户可通过面包屑或浏览器后退返回上一级

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence (Source)        |
| ----------------------- | ---------- | ------------------------ |
| Business                | Yes        | 提升数据关联导航效率      |
| User/Stakeholder (涉众) | Yes        | 用户讨论                  |
| Solution                | Yes        | 详情页模式切换设计        |
| Functional              | Yes        | FR-001 ~ FR-004          |
| Nonfunctional           | Yes        | NFR-001 交互一致性        |
| External Interface      | No         | 无外部系统集成            |
| Transition              | Yes        | TR-001 操作列迁移         |

## 3. Functional Requirements

### FR-001: 详情页浏览态/编辑态切换

- **Description**: 详情页 MUST 支持在同一页面内切换浏览态和编辑态，而非打开独立弹窗。
- **Acceptance Criteria**:
  - 详情页默认显示浏览态
  - 点击"编辑"按钮切换到编辑态，字段变为可编辑
  - 编辑态下显示"保存"和"取消"按钮
  - 点击"保存"保存数据并返回浏览态
  - 点击"取消"放弃修改并返回浏览态
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论 + 业界研究

### FR-002: FK 字段链接导航

- **Description**: 所有外键字段 MUST 在浏览态下显示为可点击链接，点击后导航到关联对象详情页。
- **Acceptance Criteria**:
  - FK 字段值显示为可点击链接样式（下划线、hover 手型光标）
  - 点击 FK 链接后，根据现有 container 判断逻辑打开详情页（drawer 或 page）
  - 导航后可通过面包屑或浏览器后退返回
  - 若 FK 值为空，显示"-"且不可点击
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论 + 业界研究

### FR-003: 操作列简化

- **Description**: 列表页操作列 MUST 简化为下拉菜单，仅保留必要操作。
- **Acceptance Criteria**:
  - 操作列显示"⋮"图标按钮
  - 点击后展开下拉菜单，包含"详情"、"编辑"、"删除"选项
  - 列宽固定为 50px
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论（已实现）

### FR-004: 导航回退机制

- **Description**: 系统 MUST 提供导航回退机制，支持用户返回上一级。
- **Acceptance Criteria**:
  - 面包屑导航显示层级路径
  - 浏览器后退按钮正常工作
  - 详情页顶部可选显示"返回"按钮
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 业界研究

### FR-005: Business Key 链接导航 (NEW)

- **Description**: 列表页中标记了 `business_key: true` 的字段 MUST 显示为可点击链接，点击后导航到该对象的详情页。
- **Acceptance Criteria**:
  - 列表页 business key 字段（如 username、code）显示为可点击链接样式
  - 链接文本使用 business key 字段的值（如用户名、编码）
  - 点击后按照现有 container 判断逻辑打开详情页（drawer 或 page），editMode=false
  - hover 时手型光标 + 下划线效果
  - FK 字段链接和 Business Key 链接使用统一的视觉样式（复用 FkLinkField 组件）
  - 若 business key 值为空，显示"-"且不可点击
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论 + 头部产品研究

### FR-006: 元数据驱动识别 (NEW)

- **Description**: Business Key 字段 MUST 通过 YAML 元数据 `semantics.business_key: true` 自动识别，无需额外前端代码配置。
- **Acceptance Criteria**:
  - 后端 `get_ui_config()` 在字段信息中传递 `business_key` 标记
  - 前端 MetaListPage 根据列配置中的 `businessKey` 标记自动渲染为链接
  - 新增 YAML 对象只需配置 `semantics.business_key: true` 即可启用
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 元数据模型驱动架构

## 4. Nonfunctional Requirements

### NFR-001: 交互一致性

- **Description**: 所有详情页 MUST 遵循统一的浏览态/编辑态切换模式。
- **Measurement**: 代码审查 + UI 一致性测试
- **Priority**: Must
- **Source**: 设计规范

### NFR-002: 性能

- **Description**: FK 链接导航 MUST 复用现有详情页打开逻辑，不引入额外性能开销。
- **Measurement**: 导航延迟 < 200ms
- **Priority**: Should
- **Source**: 性能要求

## 5. External Interface Requirements

无外部系统集成需求。

## 6. Transition Requirements

### TR-001: 操作列迁移

- **Description**: 现有操作列（详情/编辑/删除按钮）需迁移为下拉菜单模式。
- **Strategy**: 已完成，操作列改为"⋮"下拉菜单
- **Rollback Plan**: 恢复原有按钮布局代码
- **Source**: 已实现

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 复用现有 `action.container` 判断逻辑（page/drawer）
- 复用现有 ObjectPage 的 `editing` prop 和切换机制
- 复用现有 ValueHelpField 组件的配置信息

### 7.2 Business Constraints

- 不改变现有 API 接口
- 不改变现有数据模型

### 7.3 Assumptions

- FK 字段的 `relation_object` 或 `value_help_config` 信息已存在于元数据中
- 用户熟悉面包屑导航和浏览器后退操作

## 8. Priorities & Milestone Suggestions

| ID     | Requirement              | Priority | Reason                 |
| ------ | ------------------------ | -------- | ---------------------- |
| FR-001 | 详情页模式切换            | Must     | 核心交互改进            |
| FR-002 | FK 链接导航              | Must     | 核心导航改进            |
| FR-003 | 操作列简化               | Must     | 已实现                  |
| FR-004 | 导航回退机制             | Should   | 用户体验增强            |
| FR-005 | Business Key 链接导航    | Must     | 核心导航改进（NEW）     |
| FR-006 | 元数据驱动识别            | Must     | 架构一致性（NEW）       |

- Suggested Milestones:
  - Milestone 1: FK 链接导航实现（FR-002）
  - Milestone 2: Business Key 链接导航实现（FR-005, FR-006）
  - Milestone 3: 详情页模式切换优化（FR-001）

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**:
  - 列表页操作列：三个独立按钮（详情/编辑/删除）
  - 详情页：使用 DetailPage（el-drawer）+ ObjectPage 组件
  - ObjectPage 已有 `editing` prop 和 `edit`/`save`/`cancel` action 处理
  - FK 字段：使用 ValueHelpField 组件（编辑态），浏览态仅显示文本
  - 详情页打开：`action.container === 'page'` → 路由跳转，默认 → drawer

- **Current Issues**:
  - 操作列占用空间大（已解决）
  - FK 字段无链接导航功能
  - 详情页浏览态/编辑态切换入口在操作列，而非页面内

- **Relevant Code Paths**:
  - `src/components/common/MetaListPage/MetaListPage.vue` - 列表页操作列
  - `src/components/common/DetailPage/DetailPage.vue` - 详情页抽屉
  - `src/components/common/ObjectPage/ObjectPage.vue` - 对象页面组件
  - `src/components/common/ValueHelpField.vue` - FK 字段组件

### 9.2 Target State

- **Proposed Architecture**:
  - 操作列：下拉菜单（已实现）
  - 详情页：浏览态下 FK 字段显示为可点击链接
  - 详情页：顶部操作栏包含"编辑"按钮，点击切换到编辑态
  - 编辑态：顶部操作栏包含"保存"/"取消"按钮

- **Key Changes**:
  1. 创建 `FkLinkField` 组件，用于浏览态下 FK 字段的链接渲染
  2. 修改 ObjectPage 的字段渲染逻辑，识别 FK 字段并使用 FkLinkField
  3. 确认 ObjectPage 的 action 配置正确支持 edit/save/cancel

### 9.3 Detailed Design

#### 9.3.1 FkLinkField 组件设计

**复用说明**：路由映射表直接复用 `useAssociationNavigation.js` 中的 `routePathMap`，保持一致性。

```vue
<!-- FkLinkField.vue -->
<template>
  <router-link
    v-if="value && targetRoute"
    :to="targetRoute"
    class="fk-link"
    @click.stop
  >
    {{ displayValue }}
  </router-link>
  <span v-else class="fk-empty">-</span>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAssociationNavigation } from '@/composables/useAssociationNavigation'

const props = defineProps({
  value: { type: [String, Number], default: null },        // FK ID
  displayValue: { type: String, default: '' },             // 显示文本
  targetObjectType: { type: String, required: true },      // 目标对象类型
  container: { type: String, default: 'drawer' }           // 打开方式
})

const emit = defineEmits(['navigate'])

const router = useRouter()
const { getRoutePath } = useAssociationNavigation()

const targetRoute = computed(() => {
  if (!props.value) return null
  // 复用 useAssociationNavigation 的路由映射逻辑
  const basePath = getRoutePath(props.targetObjectType)
  return { path: `${basePath}/${props.value}` }
})
</script>

<style scoped>
.fk-link {
  color: var(--color-primary);
  text-decoration: none;
  cursor: pointer;
}
.fk-link:hover {
  text-decoration: underline;
}
.fk-empty {
  color: var(--color-text-tertiary);
}
</style>
```

**路由映射表（复用）**：

```js
// 来自 useAssociationNavigation.js
const routePathMap = {
  'user': '/user-permission/users',
  'role': '/user-permission/roles',
  'permission': '/user-permission/permissions',
  'user_group': '/user-permission/groups',
  'enum_type': '/business-config/enums',
  'domain': '/data/domains',
  'sub_domain': '/data/subdomains',
  'service_module': '/data/service-modules',
  'business_object': '/data/business-objects',
  'product': '/product-version/products',
  'version': '/product-version/versions',
  // 默认规则: object_type -> /{object_type.replace(/_/g, '-')}
}
```

#### 9.3.2 ObjectPage 字段渲染修改

在 ObjectPage 的浏览态字段渲染中，识别 FK 字段并使用 FkLinkField：

```vue
<!-- ObjectPage.vue 字段渲染部分 -->
<template v-if="!editing">
  <!-- FK 字段：显示为链接 -->
  <FkLinkField
    v-if="field.is_foreign_key && field.relation_object"
    :value="formData[field.key + '_id']"
    :display-value="formData[field.key + '_name'] || formData[field.key]"
    :target-object-type="field.relation_object"
    :container="field.container || 'drawer'"
  />
  <!-- 普通字段：显示文本 -->
  <span v-else>{{ formatFieldValue(field, formData[field.key]) }}</span>
</template>
```

#### 9.3.3 详情页操作按钮配置

ObjectPage 的 actions 配置：

```js
// 浏览态
const viewActions = [
  { key: 'edit', label: '编辑', icon: 'Edit', variant: 'primary' }
]

// 编辑态
const editActions = [
  { key: 'save', label: '保存', icon: 'Check', variant: 'primary' },
  { key: 'cancel', label: '取消', icon: 'Close', variant: 'secondary' }
]
```

#### 9.3.4 Business Key 链接设计 (NEW)

**复用说明**：Business Key 链接复用 FkLinkField 组件的视觉样式，保持一致的链接体验。

**元数据流**：

```
YAML: semantics.business_key: true
  → bo_framework.py: field_info['business_key'] = True
  → useMetaList.js: column.businessKey = true
  → MetaListPage.vue: v-if="column.businessKey" → 渲染 FkLinkField
```

**MetaListPage 渲染逻辑修改**：

```vue
<!-- 默认渲染 -->
<template v-else>
  <!-- FK 字段：导航到关联对象 -->
  <FkLinkField
    v-if="isFkColumn(column)"
    :value="row[column.prop]"
    :display-value="getFkDisplayValue(row, column)"
    :target-object-type="getFkTargetObjectType(column)"
  />
  <!-- Business Key：导航到自己的详情页 -->
  <span
    v-else-if="column.businessKey && row[column.prop]"
    class="bk-link"
    @click.stop="openDetailDrawer(row, false)"
  >
    {{ row[column.prop] }}
  </span>
  <span v-else-if="column.businessKey" class="bk-empty">-</span>
  <!-- 其他字段：普通文本 -->
  <template v-else-if="column.format === 'datetime'">
    {{ formatDate(row[column.prop]) }}
  </template>
  <template v-else>
    {{ row[column.prop] ?? '-' }}
  </template>
</template>
```

**FK 链接 vs Business Key 链接对比**：

| 维度 | FK 链接 | Business Key 链接 |
|------|--------|-------------------|
| **导航目标** | 关联对象详情页 | 当前对象自己的详情页 |
| **识别方式** | `value_help.source.type == 'bo'` | `semantics.business_key: true` |
| **触发位置** | 详情页浏览态 + 列表页 | 列表页 |
| **组件复用** | FkLinkField（router-link） | FkLinkField 样式（inline handler） |
| **打开方式** | router-link 路由跳转 | openDetailDrawer（复用现有 drawer 逻辑） |

**头部产品参考**：

| 产品 | Business Key 实现 | 详情 |
|------|-------------------|------|
| **Salesforce** | "Link to Record: Yes" 配置 | 列表视图任意字段可配置为链接到记录详情 |
| **Jira** | 点击 # Key 列打开详情 | Issue Key 列可点击，弹出 Modal 显示详情 |
| **Linear** | 标题列可点击 | 点击任务标题打开详情面板 |
| **Notion** | 每行可打开独立页面 | 数据库表每行都有独立详情页 |

### 9.4 Alternatives Considered

| Option                    | Pros                          | Cons                          | Decision    |
| ------------------------- | ----------------------------- | ----------------------------- | ----------- |
| A. FK 链接跳转新页面      | 简单实现                      | 离开当前上下文                | Rejected   |
| B. FK 链接打开 drawer     | 保持当前上下文                | 需要关闭 drawer 才能返回      | Selected   |
| C. FK 链接打开侧边栏      | 最佳用户体验                  | 实现复杂度高                  | Future      |

### 9.5 Implementation & Migration Plan

- **Implementation Order**:
  1. 创建 FkLinkField 组件
  2. 修改 ObjectPage 字段渲染逻辑，识别 FK 字段
  3. 确认详情页操作按钮配置正确
  4. 测试 FK 链接导航功能
  5. 测试详情页模式切换功能

- **Risk Mitigation**:
  - FK 字段识别失败 → 使用 field.relation_object 或 value_help_config 作为判断依据
  - 导航目标不存在 → 显示文本而非链接

- **Testing Strategy**:
  - 单元测试：FkLinkField 组件渲染
  - 集成测试：FK 链接点击导航
  - E2E 测试：详情页模式切换完整流程

- **Rollback Plan**:
  - 移除 FkLinkField 组件
  - 恢复 ObjectPage 原有字段渲染逻辑

## 10. TBD List

| ID    | Item                        | Missing Information          | Next Step               |
| ----- | --------------------------- | ---------------------------- | ----------------------- |
| TBD-1 | FK 字段元数据结构           | 确认 field.relation_object   | 检查元数据 API 返回     |
| TBD-2 | 目标对象路由映射完整性       | 确认所有对象类型的路由路径   | 检查 router 配置        |
| TBD-3 | useAssociationNavigation 扩展 | 是否需要新增 getRoutePath 导出 | 检查现有 composable    |
| TBD-4 | 详情页来源信息栏            | 是否需要在详情页显示来源信息 | 用户确认交互需求        |

---

## 11. 文件清单

### 11.1 新增文件

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/components/common/FkLinkField/FkLinkField.vue` | Vue 组件 | FK 链接字段组件 |
| `src/components/common/FkLinkField/index.js` | JS | 组件导出 |

### 11.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `src/components/common/ObjectPage/ObjectPage.vue` | 字段渲染逻辑：识别 FK 字段并使用 FkLinkField |
| `src/composables/useAssociationNavigation.js` | 新增 `getRoutePath()` 导出（如不存在） |
| `src/components/common/index.js` | 注册 FkLinkField 组件 |

---

## 12. 设计决策记录 (ADR)

### ADR-001: 复用 useAssociationNavigation 路由映射

**决策**: FkLinkField 复用 `useAssociationNavigation.js` 中的 `routePathMap`

**理由**:
- 单一事实原则: 路由映射只维护一处
- 一致性: 列表页导航和详情页 FK 链接使用相同的路由规则
- 可维护性: 新增对象类型只需更新一处

### ADR-002: 详情页导航不显示来源信息栏

**决策**: 默认不在详情页显示来源信息栏（与列表页导航区分）

**理由**:
- 详情页可通过浏览器后退返回
- 面包屑已提供层级导航
- 避免信息过载

---

## 13. 元数据模型驱动分析

### 13.1 元数据模型结构

FK 字段的元数据定义遵循三层架构：

```
EnhancedMetaField
└── value_help: ValueHelpConfig
    ├── source: ValueHelpSource
    │   ├── type: "bo" | "enum"           ← FK 字段: type == "bo"
    │   ├── target_bo: str                 ← 目标业务对象类型
    │   ├── value_field: str               ← 值字段（默认 "id"）
    │   ├── display_field: str             ← 显示字段（默认 "name"）
    │   └── apply_target_permissions: bool ← 是否应用目标对象权限
    ├── behavior: ValueHelpBehavior
    │   ├── binding_strength: "strict" | "loose"
    │   ├── validation: bool
    │   └── result_type: "dropdown" | "dialog" | "inline"
    └── presentation: ValueHelpPresentation
        └── result_type: "dropdown" | "dialog" | "inline"
```

### 13.2 元数据驱动渲染流程

```
┌─────────────────────────────────────────────────────────────┐
│                    后端 (Python/Flask)                       │
│                                                              │
│  YAML Schema                                                 │
│  └── field:                                                  │
│        name: parent_domain                                   │
│        type: string                                          │
│        widget: lookup          ← 触发 FK 识别                │
│        relation: domain        ← 目标对象类型                 │
│                                                              │
│  yaml_loader.py                                              │
│  └── _build_value_help()                                     │
│      └── ValueHelpSource(type="bo", target_bo="domain")     │
│                                                              │
│  bo_framework.py                                             │
│  └── get_ui_config()                                         │
│      └── _value_help_to_dict()                               │
│          └── { source: { type: "bo", target_bo: "domain" }} │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ HTTP API: GET /api/v2/meta/{type}/ui-config
┌─────────────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                              │
│                                                              │
│  metaService.js                                              │
│  └── getUIConfig(objectType)                                 │
│      └── { fields: [...], associations: [...] }              │
│                                                              │
│  ObjectPage.vue / MetaListPage.vue                           │
│  └── 渲染字段时检查 field.value_help                          │
│      ├── 编辑态: ValueHelpField 组件                          │
│      │   ├── type == "enum" → el-select (下拉)               │
│      │   └── type == "bo"   → SearchHelpDialog (弹窗选择)    │
│      └── 浏览态: FkLinkField 组件 (NEW)                       │
│          └── type == "bo" → 可点击链接                        │
└─────────────────────────────────────────────────────────────┘
```

### 13.3 方案符合性分析

| 检查项 | 状态 | 说明 |
|--------|------|------|
| **复用现有元数据字段** | ✅ | 使用 `field.value_help.source.target_bo`，无需新增字段 |
| **不修改后端 API** | ✅ | `getUIConfig()` 已返回完整 value_help 配置 |
| **不修改 YAML Schema** | ✅ | 现有 `widget: lookup` + `relation: xxx` 配置已足够 |
| **前端组件自动识别** | ✅ | 根据 `value_help.source.type == "bo"` 自动渲染为链接 |
| **与编辑态一致** | ✅ | 编辑态用 ValueHelpField，浏览态用 FkLinkField，共享同一元数据 |
| **支持权限控制** | ✅ | `apply_target_permissions` 已在元数据中定义 |

### 13.4 与现有组件的关系

| 组件 | 用途 | 元数据依赖 |
|------|------|-----------|
| **ValueHelpField** | 编辑态 FK 字段选择 | `field.value_help` |
| **FkLinkField** (NEW) | 浏览态 FK 字段链接 | `field.value_help.source.target_bo` |
| **SearchHelpDialog** | FK 值选择弹窗 | `field.value_help` |
| **AssociationNavigationMenu** | 列表页多选导航 | `metaConfig.associations` |

### 13.5 元数据驱动优势

1. **零配置启用**：只要字段配置了 `widget: lookup` + `relation: xxx`，浏览态自动显示为可点击链接
2. **一致性保证**：编辑态和浏览态使用相同的目标对象类型（`target_bo`）
3. **权限继承**：自动继承 `apply_target_permissions` 配置
4. **向后兼容**：不识别为 FK 的字段仍显示为普通文本

### 13.6 结论

**本方案完全符合元数据模型驱动架构**：

- ✅ 不引入新的元数据字段
- ✅ 不修改后端 API
- ✅ 不修改 YAML Schema
- ✅ 前端组件根据现有元数据自动渲染
- ✅ 与现有 ValueHelpField 组件共享同一数据源
