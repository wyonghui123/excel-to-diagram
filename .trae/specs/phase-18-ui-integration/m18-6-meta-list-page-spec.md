# M18.6 MetaListPage 三栏布局整合 - 详细规格

> **状态**: 已完成
> **依赖里程碑**: M18.2 (产品版本上下文) | M18.3 (级联下拉) | M18.4 (树形导航) | M18.5 (层级钻取)
> **预计工时**: 3 天 (实际: 已完成)
> **目标归属**: 目标一 (架构数据管理 UI 迁移) + 目标二 (通用组件库)
> **完成日期**: 2026-05-14

---

## 1. 背景与目标

### 1.1 背景

Phase 18 的 M18.2-M18.5 阶段已完成以下工作:

| 里程碑 | 完成状态 | 产出组件 |
|--------|----------|----------|
| M18.2 产品版本上下文 | [OK] 已完成 | VersionContextSelector, useVersionContext |
| M18.3 级联下拉 | [OK] 已完成 | useCascadeSelect, MetaForm 级联集成 |
| M18.4 树形导航 | [OK] 已完成 | CollapsiblePanel, ObjectTreePanel |
| M18.5 层级钻取 | [OK] 已完成 | useHierarchyList, BreadcrumbNav, MetaTable 层级增强 |

当前需要整合以上所有能力,形成完整的三栏布局架构数据管理页面。

### 1.2 设计原则

本规格遵循以下核心设计原则:

| 原则 | 说明 | 实施方式 |
|------|------|---------|
| **复用现有组件** | 最大化复用已有组件 | 使用 MasterDetailLayout, MetaListPage, FilterBar |
| **元数据驱动** | 行为由 YAML 配置声明 | useMetaList, hierarchies 配置 |
| **符合 UI Guideline** | 遵循 YonDesign 规范 | AppButton, AppModal, CSS 变量 |

### 1.3 现有组件分析

#### 已有的可复用组件

| 组件 | 文件位置 | 功能 | 复用方式 |
|------|---------|------|---------|
| **MasterDetailLayout** | `src/components/common/MasterDetailLayout/` | 左右布局,支持折叠和拖拽调整 | [OK] 直接复用侧边栏布局 |
| **MetaListPage** | `src/components/common/MetaListPage/` | 元数据驱动列表页 | [OK] 直接使用,支持插槽扩展 |
| **FilterBar** | `src/components/common/FilterBar/` | 过滤器组件 | [OK] 复用过滤能力 |
| **ObjectTreePanel** | `src/components/business/ObjectTreePanel/` | 树形导航面板 | [OK] 集成到侧边栏 |
| **BreadcrumbNav** | `src/components/common/BreadcrumbNav/` | 面包屑导航 | [OK] 集成到主内容区 |
| **useHierarchyList** | `src/composables/useHierarchyList.js` | 层级钻取状态管理 | [OK] 复用钻取逻辑 |
| **useMetaList** | `src/composables/useMetaList.js` | 列表数据管理 | [OK] 复用数据加载逻辑 |

#### UI Guideline 合规检查

| 检查项 | 规范要求 | 实施方式 |
|--------|---------|---------|
| 主色调 | YonDesign Orange (#ea580c) | CSS 变量 `var(--yonyou-orange-600)` |
| 按钮组件 | 使用 AppButton | `import { AppButton }` |
| 弹窗组件 | 使用 AppModal | `import { AppModal }` |
| Link 按钮 | Material Design 风格 | 遵循 `yon-ep.scss` 中的样式 |
| 颜色变量 | 使用 CSS 变量 | `var(--color-*)` |

### 1.4 业务目标

- 实现统一的三栏布局界面,支持架构对象的层级导航与列表管理
- 整合版本上下文、树形导航、层级钻取三大核心能力
- 提供可复用的工作区布局组件

### 1.5 用户目标

- 用户可以通过侧边树形导航快速定位到目标架构对象
- 用户可以在列表中钻取查看子对象,面包屑显示完整路径
- 用户切换版本上下文时,树形和列表自动联动刷新

### 1.6 技术目标

| 目标 | 具体内容 |
|------|---------|
| 架构迁移 | 替代旧的 UnifiedScopePanel + DynamicView 组合 |
| 通用能力 | 复用 MasterDetailLayout, MetaListPage 为核心布局组件 |
| 代码精简 | 从 ~1250 行减少到 ~400 行 |

---

## 2. 需求类型概述

| 需求类型 | 适用性 | 证据来源 |
|----------|--------|----------|
| 业务需求 | [OK] | 架构数据管理统一交互体验 |
| 用户/涉众需求 | [OK] | 快速定位对象,联动刷新,层级钻取 |
| 解决方案需求 | [OK] | 三栏布局组件设计 |
| 功能需求 | [OK] | 上下文联动,树-列表同步,面包屑导航 |
| 非功能需求 | [OK] | 性能,可用性,可维护性 |
| 外部接口需求 | [OK] | API 对接,组件集成 |
| 过渡需求 | [OK] | 旧 App 迁移,向后兼容 |

---

## 3. 功能需求

### FR-001: 三栏布局渲染

**描述**: 系统必须使用 MasterDetailLayout 正确渲染三栏布局结构

**验收标准**:
- 使用 `MasterDetailLayout` 组件实现侧边栏 + 主内容区布局
- 左侧栏显示 ObjectTreePanel,宽度可调,默认 280px
- 右侧主内容区显示面包屑和 MetaListPage
- 顶部显示版本上下文选择器
- 响应式布局,窗口缩放时自动调整

**优先级**: Must
**类型映射**: 功能需求

---

### FR-002: 上下文-树-列表联动

**描述**: 当版本上下文变更时,系统必须自动刷新树形和列表数据

**验收标准**:
- 版本切换后,ObjectTreePanel 自动重新加载
- 列表自动带上新的 version_id 过滤条件
- 面包屑重置到根级别
- 加载状态正确显示

**优先级**: Must
**类型映射**: 功能需求

---

### FR-003: 树节点-列表联动

**描述**: 当用户点击树节点时,系统必须更新列表过滤条件

**验收标准**:
- 点击节点后,currentObjectType 更新为节点类型
- currentFilters 包含 parent_id 过滤
- MetaListPage 重新加载并显示过滤后数据
- BreadcrumbNav 显示新的钻取路径

**优先级**: Must
**类型映射**: 功能需求

---

### FR-004: 列表钻入-树同步

**描述**: 当用户在 MetaListPage 中点击钻入操作时,系统必须同步更新树形状态

**验收标准**:
- 目标节点自动展开到可见范围
- 目标节点被选中(高亮)
- 侧边树同步滚动到目标位置

**优先级**: Should
**类型映射**: 功能需求

---

### FR-005: 侧边栏折叠/展开

**描述**: 用户必须能够折叠和展开侧边栏

**验收标准**:
- MasterDetailLayout 内置折叠按钮存在且可用
- 折叠后主内容区自动扩展
- 展开后恢复原宽度
- 折叠状态可持久化保存

**优先级**: Should
**类型映射**: 功能需求

---

### FR-006: 侧边栏宽度拖拽调整

**描述**: 用户必须能够通过拖拽调整侧边栏宽度

**验收标准**:
- MasterDetailLayout 内置拖拽分隔条可用
- 宽度限制在 minWidth (200px) 和 maxWidth (400px) 之间
- 拖拽过程中实时预览宽度
- 宽度变化时不影响主内容区布局

**优先级**: Should
**类型映射**: 功能需求

---

### FR-007: MetaListPage 插槽扩展

**描述**: MetaListPage 必须支持新增的插槽以实现三栏布局

**验收标准**:
- 支持 #toolbar 插槽用于工具栏扩展
- 支持 #context-bar 插槽用于版本上下文选择器
- 支持 #breadcrumb 插槽用于面包屑导航
- 支持 #table 插槽用于自定义表格

**优先级**: Must
**类型映射**: 功能需求

---

### FR-008: 四个业务页面实现

**描述**: 系统必须实现四个业务管理页面

**验收标准**:
- DomainManagement.vue - 领域管理页面
- SubDomainManagement.vue - 子领域管理页面
- ServiceModuleManagement.vue - 服务模块管理页面
- BusinessObjectManagement.vue - 业务对象管理页面

**优先级**: Must
**类型映射**: 功能需求

---

### FR-009: 路由配置与导航菜单

**描述**: 四个业务页面必须正确注册路由并在导航菜单中显示

**验收标准**:
- 路由正确注册到 /system/* 路径下
- 导航菜单包含四个页面的入口
- 路由元信息(title, icon)正确配置

**优先级**: Must
**类型映射**: 功能需求

---

## 4. 非功能需求

### NFR-001: 性能要求

**描述**: 三栏布局必须满足以下性能指标

**测量方法**:
- 初始加载时间: < 2s (包含树数据和列表数据)
- 上下文切换响应: < 500ms
- 树节点展开响应: < 200ms
- 列表分页切换: < 300ms

**优先级**: Should

---

### NFR-002: 可用性要求

**描述**: 三栏布局必须提供良好的用户体验

**测量方法**:
- 所有交互操作必须有视觉反馈
- 加载状态必须显示 loading 指示器
- 空状态必须有友好的提示信息
- 错误状态必须提供重试机制

**优先级**: Should

---

### NFR-003: 可维护性要求

**描述**: 组件代码必须易于维护和扩展

**测量方法**:
- 使用 MasterDetailLayout, MetaListPage 等成熟组件
- 所有组件必须遵循元数据驱动原则
- 代码必须有清晰的分层结构

**优先级**: Should

---

### NFR-004: UI Guideline 合规

**描述**: 组件必须遵循项目 UI 设计规范

**测量方法**:
- 使用 AppButton, AppModal 等封装组件
- 颜色使用 CSS 变量
- Link 按钮遵循 Material Design 风格
- 主色调为 YonDesign Orange (#ea580c)

**优先级**: Must

---

## 5. 外部接口需求

### IF-001: HierarchyTree API

**接口**: GET /api/v2/meta/hierarchy/tree

**请求参数**:
```typescript
{
  version_id: number       // 版本 ID (必填)
  root_type?: string      // 根节点类型,默认 'domain'
  include_counts?: boolean // 是否包含子对象计数
}
```

**响应格式**:
```typescript
{
  success: boolean
  data: TreeNode[]
}
```

**错误处理**:
- 401: 未授权
- 404: 版本不存在
- 500: 服务器内部错误

---

### IF-002: BOQuery API

**接口**: POST /api/v2/bo/query

**请求参数**:
```typescript
{
  object_type: string      // 对象类型
  filters?: object         // 过滤条件
  pagination?: {
    page: number
    page_size: number
  }
  sort?: {
    field: string
    order: 'asc' | 'desc'
  }
}
```

**响应格式**:
```typescript
{
  success: boolean
  data: {
    items: object[]
    total: number
    page: number
    page_size: number
  }
}
```

---

### IF-003: BOCount API

**接口**: GET /api/v2/bo/{object}/count

**请求参数**:
```typescript
{
  parent_id?: number      // 父对象 ID
  version_id?: number     // 版本 ID
}
```

**响应格式**:
```typescript
{
  success: boolean
  data: {
    count: number
  }
}
```

---

### IF-004: VersionContext API

**接口**: GET /api/v2/product-versions

**响应格式**:
```typescript
{
  success: boolean
  data: Array<{
    id: number
    name: string
    product_name: string
  }>
}
```

---

## 6. 过渡需求

### TR-001: 旧 App 路由保留

**描述**: 在过渡期内保留旧 App 的路由

**策略**: 旧路由 /arch-data 添加 /legacy 前缀,保留 2 周过渡期

**回滚计划**: 如新架构出现问题,可快速切换回旧路由

---

### TR-002: 数据一致性保证

**描述**: 新旧架构必须读写同一数据库

**策略**: 确保 BO Framework 的 API 与旧 manage_api.py 读写同一数据源

---

## 7. 约束与假设

### 7.1 技术约束

- 前端框架: Vue 3 + Composition API
- UI 组件库: Element Plus + YonDesign 封装组件
- 状态管理: Pinia
- 样式规范: 遵循项目 SCSS 规范
- 必须使用 AppButton, AppModal, AppInput 等封装组件

### 7.2 业务约束

- 四个业务对象必须支持完整的 CRUD 操作
- 版本上下文必须作为顶层过滤条件
- 树形导航只支持单选(不支持多选)

### 7.3 假设

- M18.1-M18.5 的所有组件已正确实现并可复用
- 后端 API 接口已就绪并通过测试
- YAML 元数据配置已包含所有必要的级联和层级定义
- MasterDetailLayout, MetaListPage 等组件已稳定可用

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 原因 |
|----|------|--------|------|
| FR-001 | 三栏布局渲染 | Must | 核心布局结构,使用 MasterDetailLayout |
| FR-002 | 上下文-树-列表联动 | Must | 核心交互逻辑 |
| FR-003 | 树节点-列表联动 | Must | 核心交互逻辑 |
| FR-007 | MetaListPage 插槽扩展 | Must | 组件集成基础 |
| FR-008 | 四个业务页面实现 | Must | 功能交付 |
| FR-009 | 路由配置与导航菜单 | Must | 用户访问入口 |
| FR-004 | 列表钻入-树同步 | Should | 增强体验 |
| FR-005 | 侧边栏折叠/展开 | Should | 用户体验,MasterDetailLayout 内置 |
| FR-006 | 侧边栏宽度拖拽调整 | Should | 用户体验,MasterDetailLayout 内置 |

### 里程碑建议

| 里程碑 | 范围 | 工期 |
|---------|------|------|
| Milestone 1 | 布局组件 + 基础联动 | Day 1 |
| Milestone 2 | 业务页面 + 路由 | Day 2-2.5 |
| Milestone 3 | 增强功能 + 测试 | Day 3 |

---

## 9. 变更/设计方案 (RFC)

### 9.1 现状分析

#### 当前架构 (待废弃)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         旧架构 (待废弃)                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  UnifiedScopePanel + DynamicView                                         │
│  - 布局逻辑与业务逻辑耦合                                                │
│  - 组件职责不清晰                                                       │
│  - 树形与表格交互分离                                                   │
│  - 代码量: ~1250 行                                                     │
│                                                                         │
│  问题:                                                                  │
│  1. 上下文切换需要手动刷新多个组件                                        │
│  2. 树形导航与表格过滤逻辑分散                                            │
│  3. 面包屑与钻取逻辑未抽象                                               │
│  4. 组件复用性差                                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 已有的可复用组件

| 组件 | 文件 | 功能 |
|------|------|------|
| MasterDetailLayout.vue | `src/components/common/MasterDetailLayout/` | 左右布局容器,内置折叠/拖拽 |
| MetaListPage.vue | `src/components/common/MetaListPage/` | 元数据驱动列表页 |
| ObjectTreePanel.vue | `src/components/business/ObjectTreePanel/` | 树形导航面板 |
| BreadcrumbNav.vue | `src/components/common/BreadcrumbNav/` | 面包屑导航 |
| FilterBar.vue | `src/components/common/FilterBar/` | 过滤器组件 |

#### 相关代码路径

| 文件 | 说明 |
|------|------|
| `src/views/arch-data-manage/UnifiedScopePanel.vue` | 旧上下文选择面板 |
| `src/views/arch-data-manage/DynamicView.vue` | 旧动态视图 |
| `src/components/common/FilterBar.vue` | 过滤器组件 |
| `src/components/common/MetaListPage.vue` | 元数据列表页 |
| `src/components/common/MasterDetailLayout.vue` | 主从布局容器 |

### 9.2 目标架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         新架构 (目标状态)                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  DomainManagement.vue (或其他业务页面)                                    │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  Header: VersionContextSelector                                  │  │
│  ├──────────────────┬────────────────────────────────────────────┤  │
│  │ MasterDetailLayout │                                              │  │
│  │  ┌────────────┐  │  MetaListPage                              │  │
│  │  │ ObjectTree │  │  ┌──────────────────────────────────────┐  │  │
│  │  │ Panel     │  │  │ BreadcrumbNav                        │  │  │
│  │  │           │  │  ├──────────────────────────────────────┤  │  │
│  │  │           │  │  │ MetaTable                            │  │  │
│  │  │           │  │  │ - 层级路径列                         │  │  │
│  │  │           │  │  │ - 子对象计数列                        │  │  │
│  │  └────────────┘  │  └──────────────────────────────────────┘  │  │
│  └──────────────────┴────────────────────────────────────────────┘  │
│                                                                         │
│  优势:                                                                  │
│  1. 布局使用成熟组件 MasterDetailLayout                                  │
│  2. 列表使用元数据驱动的 MetaListPage                                   │
│  3. 组件职责单一清晰                                                     │
│  4. 高度可复用                                                         │
│  5. 代码量: ~400 行                                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 数据流架构设计

#### 9.3.1 现有数据流分析

通过对现有代码的分析，我们识别出 Panel 之间的过滤数据流:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          数据流架构图                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐                                                   │
│  │VersionContext   │ ← useVersionContext                               │
│  │ Selector       │                                                   │
│  └────────┬────────┘                                                   │
│           │                                                             │
│           │ contextFilters                                              │
│           │ { version_id, product_id }                                 │
│           ▼                                                             │
│  ┌─────────────────┐                                                   │
│  │ ObjectTreePanel │ ← 需要 version_id 加载树数据                     │
│  │                 │ ← 当前选中节点的 parent_id                          │
│  └────────┬────────┘                                                   │
│           │                                                             │
│           │ selectedNode: { id, type, name }                           │
│           ▼                                                             │
│  ┌─────────────────┐                                                   │
│  │  useHierarchyList │ ← 管理钻取路径                                  │
│  │                 │ ← parentId: 当前父对象 ID                          │
│  └────────┬────────┘                                                   │
│           │                                                             │
│           │ path: [{ type, id, name }, ...]                            │
│           ▼                                                             │
│  ┌─────────────────┐                                                   │
│  │ MetaListPage     │ ← 需要多个过滤条件组合                            │
│  │                 │ ← contextFilters + parent_id + keyword              │
│  └─────────────────┘                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 9.3.2 过滤数据 key/id 映射关系

**层级对象之间的过滤字段映射:**

| 当前对象类型 | 父过滤字段 | 过滤值来源 | 说明 |
|-------------|------------|-----------|------|
| domain | `version_id` | selectedVersionId | 根级别,直接使用版本上下文 |
| sub_domain | `domain_id` | selectedNode.id | 从 domain 节点获取 |
| service_module | `sub_domain_id` | selectedNode.id | 从 sub_domain 节点获取 |
| business_object | `service_module_id` | selectedNode.id | 从 service_module 节点获取 |

**关键洞察:**

1. **版本上下文** 是顶层过滤条件,影响所有层级
2. **父对象 ID** 是中间层级过滤条件,动态变化
3. **当前对象类型** 决定使用哪个父过滤字段

#### 9.3.3 过滤条件合并规则

MetaListPage 的过滤条件由多层合并:

```javascript
// useMetaList.js 中的过滤条件构建
function _buildQueryParams(extraParams = {}) {
  const params = {
    // 1. 分页参数
    page: pagination.current,
    page_size: pagination.pageSize,
    ...extraParams

    // 2. 关键词搜索
    // keyword: 从 searchFields 配置自动处理

    // 3. 用户过滤条件 (filterValues)
    // filterValues: 用户在 FilterBar 中设置的过滤条件

    // 4. 表头过滤条件 (headerFilterValues)
    // headerFilterValues: 用户点击列头设置的过滤

    // 5. 上下文过滤条件 (contextFilters)
    // contextFilters: 通过 setContextFilters() 设置的条件
  }

  // 合并顺序(后者覆盖前者):
  // userFilters → headerFilters → contextFilters → extraParams
}
```

**过滤条件优先级:**

| 优先级 | 来源 | 说明 | 重置行为 |
|--------|------|------|---------|
| 1 (最高) | extraParams | API 调用时传入 | 不保留 |
| 2 | contextFilters | 上下文过滤(版本/父级) | **永久保留** |
| 3 | headerFilterValues | 表头过滤 | 重置时清空 |
| 4 | filterValues | 用户过滤条件 | 重置时恢复默认值 |
| 5 | keyword | 关键词搜索 | 重置时清空 |

#### 9.3.4 元数据驱动的过滤数据流设计

**设计目标:**

1. 过滤数据流由 YAML 元数据配置声明
2. 组件自动解释配置,无需硬编码
3. 支持灵活的父子关系定义

**YAML 配置示例:**

```yaml
# domain.yaml
hierarchy:
  levels:
    - object_type: domain
      children_field: sub_domains
      filter_field: version_id      # 作为子对象的父过滤字段
      root_filter: true            # 是否是根过滤

context:
  scope_field: version_id        # 版本上下文字段
  cascade_to:
    - sub_domain
    - service_module
    - business_object

# sub_domain.yaml
hierarchy:
  parent_type: domain             # 父对象类型
  parent_filter_field: domain_id   # 父过滤字段(对应 domain 的 children_field)

context:
  scope_field: version_id
  cascade_to:
    - service_module
    - business_object
```

#### 9.3.5 推荐的 useWorkspaceFilter Composable

**设计思路:**

创建一个统一的过滤数据流管理 Composable,整合 useVersionContext 和 useHierarchyList:

```javascript
// src/composables/useWorkspaceFilter.js

/**
 * useWorkspaceFilter - 工作区过滤数据流管理
 *
 * 统一管理:
 * 1. 版本上下文 (useVersionContext)
 * 2. 层级钻取状态 (useHierarchyList)
 * 3. 过滤条件合并
 *
 * @example
 * const filter = useWorkspaceFilter({
 *   objectType: 'domain',
 *   metaObject: metaObjectRef
 * })
 *
 * // 获取合并后的过滤条件(用于 MetaListPage)
 * console.log(filter.combinedFilters.value)
 * // { version_id: 1, domain_id: 5 }
 *
 * // 获取当前对象类型(可能随钻取变化)
 * console.log(filter.currentObjectType.value)
 * // 'sub_domain'
 */
export function useWorkspaceFilter(options = {}) {
  const {
    objectType = 'domain',
    metaObject = null
  } = options

  // 版本上下文
  const versionContext = useVersionContext()

  // 层级钻取状态
  const hierarchy = useHierarchyList({
    objectType,
    versionId: computed(() => versionContext.selectedVersionId.value)
  })

  /**
   * 从 YAML hierarchies 配置获取父过滤字段映射
   * 例如: { domain: 'version_id', sub_domain: 'domain_id', ... }
   */
  const parentFilterFieldMap = computed(() => {
    const meta = metaObject?.value
    const levels = meta?.hierarchies?.[0]?.levels || []
    const map = {}

    levels.forEach((level, index) => {
      const objectType = level.object_type
      if (index === 0) {
        // 根级别使用 root_filter 字段
        map[objectType] = meta?.hierarchies?.[0]?.root_filter || 'version_id'
      } else {
        // 非根级别使用 children_field
        map[objectType] = level.children_field?.replace(/_ids?$/, '_id') || `${objectType}_id`
      }
    })

    return map
  })

  /**
   * 当前对象类型的父过滤字段
   * 例如: currentType='sub_domain' → 'domain_id'
   */
  const currentParentFilterField = computed(() => {
    return parentFilterFieldMap.value[hierarchy.currentType.value]
  })

  /**
   * 合并后的过滤条件
   * 组合版本上下文 + 父对象过滤
   */
  const combinedFilters = computed(() => {
    const filters = {}

    // 1. 版本上下文过滤(顶层)
    if (versionContext.selectedVersionId.value) {
      filters.version_id = versionContext.selectedVersionId.value
    }

    // 2. 父对象过滤(中间层)
    if (hierarchy.parentId.value) {
      const filterField = currentParentFilterField.value
      filters[filterField] = hierarchy.parentId.value
    }

    return filters
  })

  /**
   * 获取特定对象类型的过滤条件
   * 用于钻入子对象时构建新的过滤
   */
  function getFiltersForType(targetType, parentId) {
    const filters = {}

    if (versionContext.selectedVersionId.value) {
      filters.version_id = versionContext.selectedVersionId.value
    }

    const filterField = parentFilterFieldMap.value[targetType]
    if (filterField && parentId) {
      filters[filterField] = parentId
    }

    return filters
  }

  return {
    // 版本上下文
    versionContext,
    contextFilters: versionContext.contextFilters,

    // 层级钻取
    hierarchy,
    path: hierarchy.path,
    currentType: hierarchy.currentType,
    parentId: hierarchy.parentId,

    // 过滤字段映射
    parentFilterFieldMap,
    currentParentFilterField,

    // 合并后的过滤条件
    combinedFilters,

    // 方法
    getFiltersForType,
    drillIn: hierarchy.drillIn,
    goTo: hierarchy.goTo,
    reset: hierarchy.reset
  }
}
```

#### 9.3.6 数据流时序图

**场景: 用户点击树节点,列表自动过滤**

```
┌──────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐
│  用户    │    │ ObjectTreePanel │    │ useHierarchyList│    │ MetaListPage │
└────┬─────┘    └────────┬────────┘    └────────┬────────┘    └──────┬───────┘
     │                    │                      │                      │
     │ 1. 点击节点        │                      │                      │
     │──────────────────>│                      │                      │
     │                    │                      │                      │
     │                    │ 2. emit('select', node)                   │
     │                    │────────────────────>                      │
     │                    │                      │                      │
     │                    │                      │ 3. drillIn(type, id) │
     │                    │                      │ { parentId: 5 }    │
     │                    │                      │                      │
     │                    │                      │ 4. 更新钻取路径     │
     │                    │                      │ path: [domain, sub_domain]
     │                    │                      │                      │
     │                    │                      │ 5. 更新 currentType │
     │                    │                      │ currentType: 'sub_domain'
     │                    │                      │                      │
     │                    │                      │ 6. 返回新的 filters  │
     │                    │                      │ { version_id: 1,    │
     │                    │                      │   domain_id: 5 }   │
     │                    │                      │───────────────────>│
     │                    │                      │                      │
     │                    │                      │                      │ 7. setContextFilters(filters)
     │                    │                      │                      │ 8. loadList()
     │                    │                      │                      │
     │                    │                      │                      │ 9. API 调用
     │                    │                      │                      │ GET /bo/sub_domain?filters={...}
     │                    │                      │                      │
     │                    │                      │                      │
     │ 10. 显示子领域列表 │                      │                      │
     │<──────────────────│                      │                      │
```

#### 9.3.7 元数据驱动 vs 硬编码对比

| 场景 | 硬编码方式 | 元数据驱动方式 |
|------|-----------|---------------|
| 添加新层级 | 修改多处 if/else | 只需修改 YAML hierarchies 配置 |
| 变更过滤字段名 | 修改多处代码 | 修改 YAML filter_field 配置 |
| 支持多层级结构 | 代码复杂度指数增长 | YAML 配置复杂度线性增长 |
| 测试 | 需要 mock 多处 | 配置即测试 |

**硬编码示例 (不推荐):**

```javascript
// ❌ 硬编码方式
function getFilters(objectType, selectedNode) {
  if (objectType === 'domain') {
    return { version_id: selectedNode.version_id }
  } else if (objectType === 'sub_domain') {
    return { version_id: selectedNode.version_id, domain_id: selectedNode.id }
  } else if (objectType === 'service_module') {
    return { version_id: selectedNode.version_id, sub_domain_id: selectedNode.id }
  }
}
```

**元数据驱动示例 (推荐):**

```javascript
// ✅ 元数据驱动方式
function getFiltersFromMetadata(objectType, parentId, hierarchyConfig) {
  const level = hierarchyConfig.levels.find(l => l.object_type === objectType)
  const filterField = level?.parent_filter_field || `${objectType}_id`

  return {
    version_id: currentVersionId.value,
    [filterField]: parentId
  }
}
```

---

### 9.4 详细设计

#### 9.4.1 核心设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 布局组件 | MasterDetailLayout | 内置折叠/拖拽功能,稳定可用 |
| 列表组件 | MetaListPage | 元数据驱动,支持插槽扩展 |
| 状态管理 | useHierarchyList + useVersionContext | 已实现层级钻取逻辑 |
| 过滤管理 | useWorkspaceFilter (新增) | 统一管理过滤数据流 |
| 组件库 | AppButton, AppModal | 遵循 YonDesign 规范 |

#### 9.4.2 DomainManagement.vue 业务页面示例

```vue
<!-- src/views/system/DomainManagement.vue -->

<template>
  <div class="domain-management">
    <!-- 顶部上下文选择器 -->
    <slot name="context-bar">
      <VersionContextSelector
        :value="versionContext.selectedVersion"
        @change="handleVersionChange"
      />
    </slot>

    <!-- 使用 MasterDetailLayout 实现三栏布局 -->
    <MasterDetailLayout
      :sidebar-width="280"
      :sidebar-collapsible="true"
      :sidebar-collapsed="sidebarCollapsed"
      :min-width="200"
      :max-width="400"
      @collapse-change="handleSidebarCollapse"
    >
      <!-- 左侧: 树形导航 -->
      <template #master>
        <ObjectTreePanel
          :version-id="versionContext.selectedVersionId"
          :selected-node-id="selectedNodeId"
          :show-count="true"
          :show-checkbox="false"
          @node-select="handleNodeSelect"
          @load="handleTreeLoad"
        />
      </template>

      <!-- 右侧: 主内容区 -->
      <template #detail>
        <!-- 面包屑导航 -->
        <BreadcrumbNav
          v-if="hierarchy.path.value.length > 0"
          :path="hierarchy.path.value"
          @navigate="handleBreadcrumbNavigate"
        />

        <!-- 列表页 -->
        <MetaListPage
          :object-type="currentObjectType"
          :initial-filters="currentFilters"
          :options="{
            autoLoad: true,
            pageSize: 20
          }"
          :enable-detail="true"
          :enable-auto-crud="true"
        >
          <!-- 自定义插槽: 层级路径列 -->
          <template #cell-hierarchy_path="{ row }">
            <div class="hierarchy-path-cell">
              <template v-for="(segment, idx) in row.hierarchyPath" :key="idx">
                <span v-if="idx > 0" class="path-sep">{{ hierarchy.separator.value }}</span>
                <AppButton
                  v-if="idx < (row.hierarchyPath?.length || 0) - 1"
                  variant="link"
                  size="sm"
                  @click="handleDrillIn(segment)"
                >
                  {{ segment.name }}
                </AppButton>
                <span v-else>{{ segment.name }}</span>
              </template>
            </div>
          </template>

          <!-- 自定义插槽: 子对象计数列 -->
          <template #cell-children_count="{ row }">
            <AppButton
              v-if="row.children_count > 0"
              variant="link"
              size="sm"
              @click="handleChildCountClick(row)"
            >
              {{ row.children_count }} 个
            </AppButton>
            <span v-else>{{ row.children_count || 0 }} 个</span>
          </template>
        </MetaListPage>
      </template>
    </MasterDetailLayout>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { MasterDetailLayout } from '@/components/common/MasterDetailLayout'
import { MetaListPage } from '@/components/common/MetaListPage'
import { ObjectTreePanel } from '@/components/business/ObjectTreePanel'
import { BreadcrumbNav } from '@/components/common/BreadcrumbNav'
import { AppButton } from '@/components/common/AppButton'
import VersionContextSelector from '@/components/business/VersionContextSelector.vue'
import { useVersionContext } from '@/composables/useVersionContext'
import { useHierarchyList } from '@/composables/useHierarchyList'

// 版本上下文
const versionContext = useVersionContext()

// 侧边栏折叠状态
const sidebarCollapsed = ref(false)

// 层级钻取状态
const hierarchy = useHierarchyList({
  objectType: 'domain',
  versionId: computed(() => versionContext.selectedVersionId.value)
})

// 当前选中节点
const selectedNodeId = ref(null)
const currentObjectType = ref('domain')

// 当前过滤条件
const currentFilters = computed(() => {
  const filters = {}

  // 版本上下文过滤
  if (versionContext.selectedVersionId.value) {
    filters.version_id = versionContext.selectedVersionId.value
  }

  // 父对象过滤
  if (selectedNodeId.value) {
    filters.parent_id = selectedNodeId.value
  }

  return filters
})

// 事件处理
function handleVersionChange(context) {
  versionContext.setVersion(context)
  selectedNodeId.value = null
  hierarchy.reset()
}

function handleNodeSelect(node) {
  selectedNodeId.value = node.id
  currentObjectType.value = node.type
  hierarchy.drillIn(node.type, node.id, node.name)
}

function handleBreadcrumbNavigate(index) {
  const node = hierarchy.path.value[index]
  if (node) {
    selectedNodeId.value = node.id
    currentObjectType.value = node.type
    hierarchy.goTo(index)
  }
}

function handleSidebarCollapse(collapsed) {
  sidebarCollapsed.value = collapsed
}

function handleTreeLoad(treeData) {
  console.log('Tree loaded:', treeData)
}

function handleDrillIn(segment) {
  selectedNodeId.value = segment.id
  currentObjectType.value = segment.type
  hierarchy.drillIn(segment.type, segment.id, segment.name)
}

function handleChildCountClick(row) {
  if (row.children_count > 0) {
    selectedNodeId.value = row.id
    currentObjectType.value = getChildObjectType(currentObjectType.value)
    hierarchy.drillIn(currentObjectType.value, row.id, row.name)
  }
}

function getChildObjectType(currentType) {
  const map = {
    domain: 'sub_domain',
    sub_domain: 'service_module',
    service_module: 'business_object'
  }
  return map[currentType] || currentType
}
</script>

<style lang="scss" scoped>
.domain-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.hierarchy-path-cell {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.path-sep {
  color: var(--color-text-placeholder);
}

:deep(.el-table) {
  .hierarchy-path-cell {
    .el-button {
      padding: 0;
      font-size: inherit;
    }
  }
}
</style>
```

#### 9.3.2 其他业务页面模板

由于四个业务页面 (Domain, SubDomain, ServiceModule, BusinessObject) 的结构相似,可以复用相同的基础模板:

```vue
<!-- 通用模板: 只需修改 objectType -->
<script setup>
// 只需修改 objectType
const OBJECT_TYPE = 'domain'  // 或 'sub_domain', 'service_module', 'business_object'

// 层级映射
const HIERARCHY_MAP = {
  domain: 'sub_domain',
  sub_domain: 'service_module',
  service_module: 'business_object',
  business_object: null
}
</script>
```

### 9.5 替代方案考虑

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 方案 A: 使用 MasterDetailLayout | 成熟稳定,内置折叠/拖拽 | 需要适配 | **[SELECTED]** |
| 方案 B: 新建 WorkspaceLayout | 完全可控 | 重复造轮子 | 拒绝 |
| 方案 C: 使用子路由 | URL 可分享状态 | 路由复杂度增加 | 拒绝 |

### 9.6 实现计划

#### 阶段 1: 布局组件 (Day 1)

1. 创建 DomainManagement.vue 作为参考模板
2. 集成 MasterDetailLayout
3. 集成 ObjectTreePanel
4. 集成 MetaListPage
5. 实现三栏联动逻辑
6. 实现面包屑导航

#### 阶段 2: 业务页面 (Day 2-2.5)

1. 创建 SubDomainManagement.vue (基于模板)
2. 创建 ServiceModuleManagement.vue (基于模板)
3. 创建 BusinessObjectManagement.vue (基于模板)
4. 配置路由
5. 更新导航菜单

#### 阶段 3: 增强与测试 (Day 3)

1. 实现列表钻入-树同步
2. 单元测试
3. 集成测试
4. UI Guideline 合规检查

### 9.7 风险缓解

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| M18.4/M18.5 组件接口变化 | 集成失败 | Low | 提前沟通接口定义 |
| 后端 API 响应慢 | 体验下降 | Medium | 添加骨架屏和 loading |
| 树形数据量大 | 性能问题 | Medium | 实现虚拟滚动 |

---

## 10. TBD 列表

| ID | 项目 | 缺失信息 | 下一步 |
|----|------|----------|--------|
| TBD-1 | 子页面差异 | 部分业务页面可能有特殊需求 | 确认是否有额外需求 |
| TBD-2 | 持久化策略 | 侧边栏宽度是否需要持久化 | 确认是否需要 localStorage |

---

## 附录 A: 现有组件参考

### A.1 MasterDetailLayout 使用示例

```vue
<MasterDetailLayout
  :sidebar-width="280"
  :sidebar-collapsible="true"
  :sidebar-collapsed="collapsed"
  :min-width="200"
  :max-width="400"
  @collapse-change="handleCollapse"
>
  <template #master>
    <!-- 左侧内容 -->
  </template>

  <template #detail>
    <!-- 右侧内容 -->
  </template>
</MasterDetailLayout>
```

### A.2 MetaListPage 插槽说明

| 插槽名 | 说明 | 使用场景 |
|--------|------|---------|
| toolbar | 工具栏区域 | 搜索按钮,导入导出按钮 |
| table | 表格区域 | 自定义列渲染 |
| pagination | 分页区域 | 自定义分页器 |
| dialogs | 对话框区域 | 自定义对话框 |

### A.3 ObjectTreePanel Props

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| versionId | Number | required | 版本上下文 ID |
| selectedNodeId | Number | null | 选中的节点 ID |
| showCount | Boolean | true | 显示子对象计数 |
| showCheckbox | Boolean | false | 显示复选框 |

### A.4 useHierarchyList API

```javascript
const hierarchy = useHierarchyList({
  objectType: 'domain',
  versionId: computed(() => store.selectedVersionId)
})

// 钻取到子对象
hierarchy.drillIn(targetType, parentId, name)

// 点击面包屑回退
hierarchy.goTo(index)

// 重置到根
hierarchy.reset()

// 当前路径
console.log(hierarchy.path.value)
```

---

## 附录 B: UI Guideline 合规检查清单

### B.1 组件使用

| 检查项 | 要求 | 状态 |
|--------|------|------|
| 按钮组件 | 使用 AppButton,禁止 el-button | [TODO] |
| 弹窗组件 | 使用 AppModal,禁止 el-dialog | [TODO] |
| 输入组件 | 使用 AppInput,禁止 el-input | [TODO] |
| 选择组件 | 使用 AppSelect,禁止 el-select | [TODO] |

### B.2 颜色使用

| 检查项 | 要求 | 状态 |
|--------|------|------|
| 主色调 | var(--yonyou-orange-600) | [TODO] |
| 背景色 | var(--color-bg-*) | [TODO] |
| 边框色 | var(--color-border) | [TODO] |
| 禁止硬编码 | #1677ff 等蓝色禁用 | [TODO] |

### B.3 Link 按钮

| 检查项 | 要求 | 状态 |
|--------|------|------|
| 文字颜色 | var(--yonyou-orange-600) | [TODO] |
| Hover 背景 | rgba(234, 88, 12, 0.06) | [TODO] |
| Active 背景 | rgba(234, 88, 12, 0.16) | [TODO] |

---

## 附录 C: 验收检查清单

### 功能验收

- [ ] 三栏布局正确渲染(上下文栏+树+列表)
- [ ] 上下文变更后树和列表自动刷新
- [ ] 树节点点击后列表正确过滤
- [ ] 面包屑导航正常工作
- [ ] 侧边栏折叠/展开正常 (MasterDetailLayout 内置)
- [ ] 侧边栏宽度拖拽调整正常 (MasterDetailLayout 内置)
- [ ] 四个业务页面完整可用
- [ ] 路由正确注册
- [ ] 导航菜单正确显示

### 性能验收

- [ ] 初始加载 < 2s
- [ ] 上下文切换 < 500ms
- [ ] 树节点点击响应 < 200ms

### 代码质量验收

- [ ] 使用 MasterDetailLayout 作为布局容器
- [ ] 使用 MetaListPage 作为列表组件
- [ ] 使用 AppButton, AppModal 等封装组件
- [ ] 颜色使用 CSS 变量,无硬编码
- [ ] 所有组件遵循元数据驱动原则
- [ ] Link 按钮遵循 Material Design 风格
