# Spec: 标准化父子页面（Parent-Child Page）架构设计

## 1. Background & Objectives

### 1.1 Background

当前项目存在多种父子数据关系（Product-Version、EnumType-EnumValue、Domain-SubDomain-ServiceModule-BusinessObject 等），但缺乏统一的页面模式标准：

- **现状问题**：
  - `ProductVersionApp` 使用自定义的 `MasterDetailLayout`，与 `MetaListPage`/`ObjectPage` 体系不互通
  - `EnumTypeDetail` 手动在 `ObjectPage` 中嵌入 `MetaListPage` slot，代码重复且不可复用
  - `DomainManagement` 等四级层级页面各自独立实现，结构高度重复
  - YAML Schema 中已定义 `parent_object` 关系，但前端未自动消费
  - 父子页面路由需要手动配置，无自动生成机制

- **已具备的基础设施**：
  - `MetaListPage`：YAML 驱动列表页（筛选、分页、行操作、导入导出）
  - `ObjectPage`：对象页容器（面包屑、Tab 导航、FieldGroup 渲染）
  - `DetailPage`：Drawer 详情页（含变更历史）
  - `useMetaList`：列表逻辑 composable（含 `setContextFilters`）
  - `useDetail`：详情逻辑 composable（含关联数据加载）
  - `MasterDetailLayout`：可折叠/拖拽的主从布局容器
  - YAML Schema：已支持 `parent_object`、`relations`、`ui_view_config`

### 1.2 Business Objectives

- **统一父子页面交互模式**：为所有父子关系数据提供标准化的页面模式
- **提升开发效率**：通过 YAML 配置自动生成父子页面，减少重复代码
- **保证用户体验一致性**：无论底层数据如何，用户面对统一的交互模式
- **降低维护成本**：父子关系逻辑集中管理，修改一处全局生效

### 1.3 User / Stakeholder Objectives

| 涉众 | 目标 |
|------|------|
| 终端用户 | 在产品详情页直接查看和管理版本，无需跳转页面 |
| 前端开发者 | 通过 YAML 配置即可生成父子页面，无需写重复代码 |
| 架构师 | 父子页面模式标准化，易于扩展和维护 |
| 产品经理 | 统一的交互模式降低用户学习成本 |

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 需要统一父子页面模式以提升开发效率和用户体验 |
| User/Stakeholder | Yes | 终端用户需要上下文连续的版本管理体验 |
| Solution | Yes | 需要新增 `useParentChild` composable 和 `ObjectChildSection` 组件 |
| Functional | Yes | 详见 FR-001 ~ FR-012 |
| Nonfunctional | Yes | 详见 NFR-001 ~ NFR-004 |
| External Interface | Yes | YAML Schema 扩展、路由约定 |
| Transition | Yes | 现有 `ProductVersionApp` 需要迁移 |

---

## 3. Functional Requirements

### FR-001: 父对象列表页（Parent List Page）

- **Description**: 系统必须提供标准化的父对象列表页，使用 `MetaListPage` 组件，支持完整的列表操作能力。
- **Acceptance Criteria**:
  - 父对象列表页使用 `MetaListPage`，`objectType` 为父对象类型
  - 行操作包含"管理子对象"按钮，点击后路由跳转到父对象详情页
  - 保留现有的"编辑"、"删除"、"详情"操作
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 现有 `MetaListPage` 能力 + 用户讨论

### FR-002: 父对象详情页 - 基本信息 Section

- **Description**: 父对象详情页必须显示对象的基本信息，使用 `ObjectPage` 的 `display: 'always'` section。
- **Acceptance Criteria**:
  - 页面顶部显示面包屑导航：`‹ 返回 产品管理 / 供应链系统`
  - 显示对象标题和关键字段摘要
  - 支持"编辑"、"删除"操作
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 现有 `ObjectPage` 能力

### FR-003: 父对象详情页 - 子对象列表 Section（核心）

- **Description**: 父对象详情页必须包含子对象列表 Section，使用 `MetaListPage` 的简化版自动渲染。
- **Acceptance Criteria**:
  - 子列表 Section 标题为"{childLabel}列表 ({count})"
  - 子列表显示核心列（由 YAML `child_list_config.columns` 定义）
  - 子列表支持新增、编辑、删除操作
  - 子列表的分页、筛选、搜索独立运作
  - 子列表自动应用父对象过滤条件（`parent_id = currentParentId`）
  - 新增子对象时自动注入 `parent_id`
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论 + SAP Fiori Object Page 模式

### FR-004: 子对象列表的上下文连续性

- **Description**: 子对象的新增/编辑操作必须在父对象详情页内完成，不离开当前页面。
- **Acceptance Criteria**:
  - 子对象的新增/编辑使用 `DetailPage` Drawer 弹窗
  - Drawer 标题显示父对象上下文：`新增版本 - 供应链系统`
  - 保存成功后子列表自动刷新
  - 支持批量删除子对象
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论

### FR-005: YAML Schema 扩展 - `child_list_config`

- **Description**: YAML Schema 必须支持 `child_list_config` 配置段，定义子列表的展示行为。
- **Acceptance Criteria**:
  - `child_list_config` 包含：`pageSize`、`columns`、`actions`、`defaultSort`
  - `columns` 支持引用父对象字段（如 `product_name`）
  - `actions` 支持：`edit`、`delete`、`set_current` 等自定义操作
  - 后端 `metaService` 返回 `child_list_config` 配置
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 现有 YAML Schema + 用户讨论

### FR-006: `useParentChild` Composable

- **Description**: 系统必须提供 `useParentChild` composable，封装父子关系的通用逻辑。
- **Acceptance Criteria**:
  - 接收参数：`parentObjectType`、`childObjectType`、`parentId`
  - 返回：`parentDetail`、`childList`、`breadcrumbs`、`createChild`、`updateChild`、`deleteChild`
  - 自动注入 `parent_id` 到子对象的 CRUD 操作
  - 支持 `childListInDetail` 选项控制是否在详情页嵌入子列表
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 技术设计

### FR-007: `ObjectChildSection` 组件

- **Description**: 系统必须提供 `ObjectChildSection` 组件，用于在 `ObjectPage` 中渲染子对象列表。
- **Acceptance Criteria**:
  - 接收 `objectType`、`parentId`、`config`（YAML child_list_config）参数
  - 内部使用 `useParentChild` 获取数据和逻辑
  - 渲染简化版 `MetaListPage`（无面包屑、无标题栏，保留表格+操作）
  - 支持展开/折叠 Section
  - 支持 `display: 'always'` 和 `display: 'expandable'` 两种模式
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 技术设计

### FR-008: 路由自动生成约定

- **Description**: 父子页面路由必须遵循统一约定，支持自动生成。
- **Acceptance Criteria**:
  - 父对象列表：`/{parentObjectType}`
  - 父对象详情：`/{parentObjectType}/:id`
  - 子对象列表（独立页面）：`/{parentObjectType}/:id/{childObjectType}`
  - 路由参数自动注入 `parent_id` 过滤条件
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 技术设计

### FR-009: 现有页面迁移 - `ProductVersionApp`

- **Description**: 现有 `ProductVersionApp` 必须迁移到新的标准化父子页面模式。
- **Acceptance Criteria**:
  - 保留现有的 `MasterDetailLayout` 布局能力
  - 使用 `useParentChild` 替代自定义逻辑
  - 子列表使用 `ObjectChildSection` 或 `MetaListPage`
  - 功能等价，用户体验不降级
- **Priority**: Should
- **Type Mapping**: Transition
- **Source**: 现有代码分析

### FR-010: 现有页面迁移 - `EnumTypeDetail`

- **Description**: 现有 `EnumTypeDetail` 的手动 slot 嵌入模式必须替换为 `ObjectChildSection`。
- **Acceptance Criteria**:
  - 移除手动 `MetaListPage` slot 注入代码
  - 使用 `ObjectChildSection` 自动渲染枚举值列表
  - 功能等价，代码更简洁
- **Priority**: Should
- **Type Mapping**: Transition
- **Source**: 现有代码分析

### FR-011: 四级层级页面标准化

- **Description**: Domain/SubDomain/ServiceModule/BusinessObject 四级层级页面必须使用标准化父子模式重构。
- **Acceptance Criteria**:
  - 使用 `useParentChild` 替代重复的自定义逻辑
  - 使用 `ObjectChildSection` 渲染子层级列表
  - 支持层级钻取（点击子域名进入子域名详情页）
- **Priority**: Could
- **Type Mapping**: Functional
- **Source**: 现有代码分析

### FR-012: 面包屑与导航

- **Description**: 父子页面必须提供清晰的面包屑导航和返回机制。
- **Acceptance Criteria**:
  - 父对象详情页面包屑：`‹ 返回 {parentLabel} / {parentName}`
  - 子对象独立列表页面包屑：`‹ 返回 {parentLabel} / {parentName} / {childLabel}列表`
  - 点击面包屑可返回上级页面
  - 支持浏览器前进/后退
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户讨论

---

## 4. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: 子列表的首次加载时间不超过 500ms，分页切换不超过 200ms。
- **Measurement**: 使用 Chrome DevTools Performance 面板测量，在本地开发环境（无网络延迟）下测试。
- **Priority**: Must
- **Source**: 通用性能要求

### NFR-002: 可扩展性

- **Description**: 新的父子页面模式必须支持任意层级的父子关系（不限于两级）。
- **Measurement**: 能够支持三级（祖父-父-子）和四级层级关系，无需修改核心代码。
- **Priority**: Should
- **Source**: 现有四级层级页面（Domain/SubDomain/ServiceModule/BusinessObject）

### NFR-003: 可维护性

- **Description**: 父子页面相关代码的圈复杂度不超过 10，组件行数不超过 500 行。
- **Measurement**: 使用 ESLint + 代码审查。
- **Priority**: Should
- **Source**: 代码质量要求

### NFR-004: 向后兼容性

- **Description**: 新架构必须兼容现有的 `MetaListPage`、`ObjectPage`、`DetailPage` 使用方式，不破坏现有页面。
- **Measurement**: 所有现有页面在无修改的情况下正常运行。
- **Priority**: Must
- **Source**: 迁移要求

---

## 5. External Interface Requirements

### IF-001: YAML Schema 扩展

- **Type**: System Integration
- **Endpoint**: `metaService.getObjectMeta(objectType)`
- **Request/Response**:
  ```yaml
  # version.yaml 扩展示例
  parent_object: product
  ui_view_config:
    child_list_config:
      pageSize: 10
      columns:
        - name
        - code
        - status
        - is_current
        - created_at
      actions:
        - type: edit
          label: 编辑
        - type: delete
          label: 删除
        - type: custom
          label: 设为当前版本
          action: set_current
      defaultSort:
        field: created_at
        order: desc
  ```
- **Error Handling**: 如果 `child_list_config` 缺失，使用默认值（pageSize=10，columns=所有可见列，actions=edit+delete）
- **Source**: 技术设计

### IF-002: 路由接口

- **Type**: UI
- **Entry Point**: `/{parentObjectType}/:id` 和 `/{parentObjectType}/:id/{childObjectType}`
- **Interaction**: 路由参数 `id` 作为 `parent_id` 自动注入子列表的过滤条件
- **Error Handling**: 如果 `parent_id` 无效，显示错误提示并返回父列表页
- **Source**: 技术设计

---

## 6. Transition Requirements

### TR-001: 现有页面迁移

- **Description**: `ProductVersionApp` 和 `EnumTypeDetail` 需要迁移到新的标准化模式。
- **Strategy**:
  1. Phase 1：新增 `useParentChild` 和 `ObjectChildSection`（不影响现有代码）
  2. Phase 2：`EnumTypeDetail` 替换为 `ObjectChildSection`（低风险）
  3. Phase 3：`ProductVersionApp` 重构（中风险，需要功能测试）
  4. Phase 4：四级层级页面重构（可选）
- **Rollback Plan**: 每个 Phase 独立提交，发现问题可快速回滚到上一 Phase
- **Source**: 迁移策略

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 必须使用 Vue 3 Composition API + Ant Design Vue 4.x
- 必须兼容现有的 `useMetaList`、`useDetail`、`MetaListPage`、`ObjectPage`、`DetailPage`
- 必须使用 YAML Schema 驱动配置
- 路由使用 Vue Router 4.x

### 7.2 Business Constraints

- 产品-版本关系是强归属关系，版本不能脱离产品存在
- 用户主要围绕"某个产品"进行版本操作
- 一个产品的版本数量通常不超过 20 个

### 7.3 Assumptions

- 后端 `metaService` 可以扩展返回 `child_list_config` 配置 — Source: 待确认
- 现有的 `MetaListPage` 可以通过 props 控制隐藏面包屑和标题栏 — Source: 已验证（`showBreadcrumb` prop 存在）
- `ObjectPage` 支持动态 section 渲染 — Source: 已验证（`sections` prop 支持动态配置）

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|----|-------------|----------|--------|
| FR-006 | `useParentChild` composable | Must | 核心基础设施，其他功能依赖 |
| FR-007 | `ObjectChildSection` 组件 | Must | 核心基础设施，其他功能依赖 |
| FR-005 | YAML Schema 扩展 | Must | 配置驱动的前提 |
| FR-003 | 子对象列表 Section | Must | 核心用户需求 |
| FR-004 | 上下文连续性 | Must | 核心用户体验 |
| FR-012 | 面包屑与导航 | Must | 基础导航能力 |
| FR-001 | 父对象列表页 | Must | 入口页面 |
| FR-002 | 父对象详情页 | Must | 基础页面 |
| FR-010 | `EnumTypeDetail` 迁移 | Should | 低风险，验证新模式 |
| FR-009 | `ProductVersionApp` 迁移 | Should | 中风险，需要测试 |
| FR-008 | 路由自动生成 | Should | 提升开发效率 |
| FR-011 | 四级层级页面 | Could | 可选优化 |

- **Suggested Milestones**:
  - **Milestone 1（2周）**: FR-006 + FR-007 + FR-005 — 核心基础设施
  - **Milestone 2（1周）**: FR-003 + FR-004 + FR-012 — 核心功能集成
  - **Milestone 3（1周）**: FR-010 + FR-009 — 现有页面迁移
  - **Milestone 4（1周）**: FR-008 + FR-011 — 增强功能

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**Current Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  MetaListPage (列表页)                                       │
│  - 独立页面，通过 initialFilters 过滤                        │
│  - 行操作跳转 DetailPage Drawer                             │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  ObjectPage (详情页)                                         │
│  - Header + Anchor Bar + Sections                           │
│  - Sections 通过 slot 注入                                   │
│  - EnumTypeDetail: 手动注入 MetaListPage slot               │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  ProductVersionApp (自定义父子页)                             │
│  - MasterDetailLayout (自定义布局)                           │
│  - 左侧产品列表 + 右侧版本详情                                │
│  - 与 MetaListPage/ObjectPage 体系不互通                     │
└─────────────────────────────────────────────────────────────┘
```

**Current Issues**:

1. **代码重复**：`EnumTypeDetail` 手动嵌入 `MetaListPage`，代码不可复用
2. **架构分裂**：`ProductVersionApp` 使用自定义布局，与标准化组件体系割裂
3. **配置缺失**：YAML 中 `parent_object` 未自动消费，需要手动写 `initial-filters`
4. **扩展困难**：新增父子关系需要重复实现相同的模式
5. **维护成本高**：父子关系逻辑分散在多个页面中

**Relevant Code Paths**:

- `src/components/common/MetaListPage/MetaListPage.vue` — 列表页容器
- `src/components/common/ObjectPage/ObjectPage.vue` — 对象页容器
- `src/components/common/DetailPage/DetailPage.vue` — 详情 Drawer
- `src/composables/useMetaList.js` — 列表逻辑
- `src/composables/useDetail.js` — 详情逻辑
- `src/views/SystemManagement/EnumTypeDetail.vue` — 手动嵌入子列表的示例
- `src/views/ProductVersionApp/index.vue` — 自定义父子页
- `src/views/SystemManagement/DomainManagement.vue` — 四级层级页面

### 9.2 Target State

**Proposed Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│  YAML Schema (配置层)                                        │
│  - parent_object: product                                   │
│  - child_list_config: { columns, actions, pageSize }        │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  useParentChild (逻辑层)                                     │
│  - 封装父子关系 CRUD 逻辑                                    │
│  - 自动注入 parent_id                                       │
│  - 生成面包屑导航                                           │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  ObjectChildSection (组件层)                                 │
│  - 在 ObjectPage 中渲染子列表                                │
│  - 内部使用 useParentChild + MetaListPage                   │
└─────────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│  ObjectPage (容器层)                                         │
│  - Header + Anchor Bar + Sections                           │
│  - Section 自动渲染 ObjectChildSection                      │
│  - 支持 display: 'always' / 'expandable'                    │
└─────────────────────────────────────────────────────────────┘
```

**Key Changes**:

1. 新增 `useParentChild` composable — 封装父子关系通用逻辑
2. 新增 `ObjectChildSection` 组件 — 在 ObjectPage 中渲染子列表
3. 扩展 YAML Schema — 增加 `child_list_config` 配置段
4. 扩展现有组件 — `MetaListPage` 支持简化模式，`ObjectPage` 支持自动渲染 child sections
5. 迁移现有页面 — `EnumTypeDetail`、`ProductVersionApp`

### 9.3 Detailed Design

#### 9.3.1 Module/Component Design

**`useParentChild` Composable**:

```javascript
// src/composables/useParentChild.js
export function useParentChild(parentObjectType, childObjectType, options = {}) {
  const {
    parentId,
    autoLoadParent = true,
    childListInDetail = true
  } = options

  const router = useRouter()
  const route = useRoute()

  // 父对象详情
  const parentDetail = useDetail(parentObjectType, { id: parentId })

  // 子对象列表
  const childList = useMetaList(childObjectType, {
    initialFilters: { [`${parentObjectType}_id`]: parentId }
  })

  // 面包屑
  const breadcrumbs = computed(() => [
    { label: parentDetail.meta.value?.label || parentObjectType, to: `/${parentObjectType}` },
    { label: parentDetail.detail.value?.name || '详情' }
  ])

  // 子对象 CRUD（自动注入 parent_id）
  async function createChild(data) {
    return boService.create(childObjectType, {
      ...data,
      [`${parentObjectType}_id`]: parentId
    })
  }

  async function updateChild(id, data) {
    return boService.update(childObjectType, id, data)
  }

  async function deleteChild(id) {
    return boService.delete(childObjectType, id)
  }

  // 返回父列表
  function navigateToParentList() {
    router.push(`/${parentObjectType}`)
  }

  return {
    parentDetail,
    childList,
    breadcrumbs,
    createChild,
    updateChild,
    deleteChild,
    navigateToParentList
  }
}
```

**`ObjectChildSection` 组件**:

```vue
<!-- src/components/common/ObjectChildSection/ObjectChildSection.vue -->
<template>
  <div class="object-child-section">
    <MetaListPage
      :object-type="childObjectType"
      :initial-filters="initialFilters"
      :show-breadcrumb="false"
      :show-title="false"
      :page-size="config.pageSize || 10"
      :custom-actions="config.actions"
      @row-click="handleRowClick"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useParentChild } from '@/composables/useParentChild'
import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'

const props = defineProps({
  parentObjectType: { type: String, required: true },
  childObjectType: { type: String, required: true },
  parentId: { type: [String, Number], required: true },
  config: { type: Object, default: () => ({}) }
})

const { childList, createChild } = useParentChild(
  props.parentObjectType,
  props.childObjectType,
  { parentId: props.parentId }
)

const initialFilters = computed(() => ({
  [`${props.parentObjectType}_id`]: props.parentId
}))

function handleRowClick(record) {
  // 打开 DetailPage Drawer
}
</script>
```

**`ObjectPage` 扩展**:

```javascript
// ObjectPage.vue 中增加 childSections 支持
const props = defineProps({
  // ... 现有 props
  childSections: {
    type: Array,
    default: () => []
  }
})

// 在 sections 渲染逻辑中增加 child section 渲染
function renderChildSection(section) {
  return h(ObjectChildSection, {
    parentObjectType: section.parentObjectType,
    childObjectType: section.childObjectType,
    parentId: route.params.id,
    config: section.config
  })
}
```

#### 9.3.2 Data Model

**YAML Schema 扩展**:

```yaml
# version.yaml
object_name: version
label: 版本
parent_object: product

ui_view_config:
  list:
    # ... 现有配置
  
  child_list_config:
    pageSize: 10
    columns:
      - name
      - code
      - status
      - is_current
      - created_at
    actions:
      - type: edit
        label: 编辑
      - type: delete
        label: 删除
      - type: custom
        label: 设为当前版本
        action: set_current
    defaultSort:
      field: created_at
      order: desc
```

#### 9.3.3 API Design

**后端 `metaService` 扩展**:

```javascript
// GET /api/meta/:objectType
{
  "object_name": "version",
  "label": "版本",
  "parent_object": "product",
  "fields": [...],
  "ui_view_config": {
    "list": {...},
    "child_list_config": {
      "pageSize": 10,
      "columns": ["name", "code", "status", "is_current"],
      "actions": [...]
    }
  }
}
```

#### 9.3.4 Main Flows

**Flow 1: 用户查看产品详情并管理版本**

```
用户 → 产品列表页 → 点击"管理版本" → 产品详情页
  → 查看基本信息 Section
  → 展开版本列表 Section
    → 查看版本列表（自动过滤 product_id）
    → 点击"新增版本" → DetailPage Drawer
      → 填写表单（自动隐藏 product_id 字段）
      → 保存 → Drawer 关闭 → 版本列表刷新
```

**Flow 2: 用户编辑版本**

```
用户 → 版本列表 → 点击"编辑" → DetailPage Drawer
  → 表单显示版本信息（product_id 只读）
  → 修改 → 保存 → Drawer 关闭 → 列表刷新
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| A. 内嵌子列表（SAP Fiori 模式） | 上下文连续、用户体验好、符合现有 ObjectPage 架构 | 右侧空间受限、不适合大数据量 | **Selected** |
| B. 路由跳转子列表 | 空间充裕、适合大数据量、URL 可书签 | 上下文切换、需要额外导航 | Rejected（用户体验不如 A） |
| C. MasterDetailLayout | 左侧列表右侧详情、空间利用率高 | 与现有 MetaListPage 体系不互通、自定义成本高 | Rejected（架构分裂） |

**Rationale for Selection**:

- 产品-版本是强归属关系，用户心智模型是"管理某个产品的版本"，不是"管理版本"
- 与现有 `EnumTypeDetail` 的成功模式一致
- `ObjectPage` + `MetaListPage` 的组合已经验证可行
- 通过 `ObjectChildSection` 组件化，可以解决代码复用问题

### 9.5 Implementation & Migration Plan

**Implementation Order**:

1. **Step 1**: 创建 `useParentChild` composable（`src/composables/useParentChild.js`）
2. **Step 2**: 创建 `ObjectChildSection` 组件（`src/components/common/ObjectChildSection/`）
3. **Step 3**: 扩展 `MetaListPage` 支持简化模式（隐藏面包屑、标题栏）
4. **Step 4**: 扩展 `ObjectPage` 支持 `childSections` prop
5. **Step 5**: 扩展 YAML Schema 和后端 `metaService`
6. **Step 6**: 迁移 `EnumTypeDetail`（低风险验证）
7. **Step 7**: 迁移 `ProductVersionApp`（功能测试）
8. **Step 8**: 文档和示例

**Risk Mitigation**:

| Risk | Mitigation |
|------|-----------|
| 现有页面被破坏 | 每个 Step 独立分支，充分测试后再合并 |
| 性能问题 | 子列表使用虚拟滚动，限制初始加载条数 |
| YAML 配置复杂 | 提供默认值，简化配置 |
| 用户不习惯新交互 | 保留原有操作习惯，渐进式迁移 |

**Testing Strategy**:

- **Unit tests**: `useParentChild` 的逻辑测试（CRUD、面包屑生成、过滤条件注入）
- **Integration tests**: `ObjectChildSection` + `MetaListPage` + `useParentChild` 集成测试
- **E2E tests**: 产品详情页的版本列表增删改查流程

**Rollback Plan**:

- 每个 Step 独立 Git 提交
- 使用 feature 分支开发
- 发现问题可快速回滚到主分支

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|----|------|-------------------|-----------|
| ~~TBD-1~~ | ~~后端 `metaService` 扩展~~ | ✅ 已确认：基于 Association 确定父子模型 | ~~确认后端开发资源~~ |
| ~~TBD-2~~ | ~~`ProductVersionApp` 的 `MasterDetailLayout`~~ | ✅ 已确认：采纳迁移到 ObjectPage + ObjectChildSection 方案 | ~~确认产品需求~~ |
| TBD-3 | 四级层级页面重构优先级 | 是否需要支持祖父-父-子三级嵌套？ | 记录待办，Milestone 4 处理 |
| ~~TBD-4~~ | ~~子列表的批量操作~~ | ✅ 已确认：复用 MetaListPage 的批量操作能力 | ~~确认用户需求~~ |

### 实现状态

| 功能 | 状态 | 文件 |
|------|------|------|
| `useParentChild` composable | ✅ 已完成 | `src/composables/useParentChild.js` |
| `ObjectChildSection` 组件 | ✅ 已完成 | `src/components/common/ObjectChildSection/` |
| `ObjectPageWithChildren` 包装组件 | ✅ 已完成 | `src/components/common/ObjectPage/ObjectPageWithChildren.vue` |
| YAML Schema `child_sections` 配置 | ✅ 已完成 | `product.yaml` 扩展示例 |
| `metaService` 扩展方法 | ✅ 已完成 | `getChildSections`, `getParentChildRelations`, `getChildObjectTypes`, `getParentIdField` |
| `metaService.getViewConfigSync` | ✅ 已完成 | 同步获取缓存的视图配置 |
| ObjectChildSection 支持两种模式 | ✅ 已完成 | 简单表格模式 + MetaListPage 模式 |
| ObjectChildSection 支持 inline-edit | ✅ 已完成 | 通过 `useMetaList: true` 启用 |
| EnumTypeDetail 迁移示例 | ✅ 已完成 | `EnumTypeDetailV2.vue` |
| ProductDetailPage 迁移示例 | ✅ 已完成 | `ProductDetailPage.vue` |
| 路由设计文档 | ✅ 已完成 | `docs/architecture/routing-parent-child-pattern.md` |

### 页面迁移映射

| 原页面 | 新页面 | 说明 |
|--------|--------|------|
| `EnumTypeDetail.vue` | `EnumTypeDetailV2.vue` | 使用 ObjectChildSection，支持 inline-edit |
| `ProductVersionApp` | `ProductDetailPage.vue` | 使用 ObjectPageWithChildren + ObjectChildSection |

---

Spec + RFC contain 10 sections, last section is "TBD List", content is complete. Implementation status updated.
