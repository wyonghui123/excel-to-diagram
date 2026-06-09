## 目录

1. [一、需求概述](#一-需求概述)
2. [二、现有组件库分析](#二-现有组件库分析)
3. [三、需要新建的组件](#三-需要新建的组件)
4. [四、需要调整的现有组件](#四-需要调整的现有组件)
5. [五、可直接复用的组件](#五-可直接复用的组件)
6. [六、组件架构图](#六-组件架构图)
7. [七、实施优先级](#七-实施优先级)
8. [八、详细组件清单](#八-详细组件清单)
9. [九、待办清单](#九-待办清单)
10. [十、总结](#十-总结)

---
# Workspace 组件架构分析报告

> **版本**: v1.0  
> **分析日期**: 2024-05-13  
> **状态**: 详细分析

---

## 一、需求概述

### 1.1 Multi-Object Workspace 核心功能

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│ WorkspaceHeader                                                                              │
│ [← 返回] 架构数据管理    [导入] [导出] [刷新] [图表]           [搜索...] [用户]       │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────────────────┐  │
│  │ ProductSelector  │  │ VersionSelector  │  │                                    │  │
│  └──────────────────┘  └──────────────────┘  └────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────┐  ┌──────────────────────────────────────────────┐  │
│  │ WorkspaceSidebar            │  │ WorkspaceMain                                │  │
│  │                            │  │                                              │  │
│  │ ┌────────────────────┐ │  │  │  ┌──────────────────────────────────────┐│  │
│  │ │ ObjectTree           │ │  │  │  │ TabBar: [领域] [子领域] [服务模块]││  │
│  │ │ (中心范畴)            │ │  │  │  │                    [业务对象] [关系]││  │
│  │ └────────────────────┘ │  │  │  ├──────────────────────────────────────┤│  │
│  │                            │  │  │  │                                      ││  │
│  │ ┌────────────────────┐ │  │  │  │  ┌────────────────────────────────┐  ││  │
│  │ │ RelationTree         │ │  │  │  │  │ Toolbar                         │  ││  │
│  │ │ (关系范围)            │ │  │  │  │  ├────────────────────────────────┤  ││  │
│  │ └────────────────────┘ │  │  │  │  │  │                                │  ││  │
│  │                            │  │  │  │  │  ListView (MetaListPage)       │  ││  │
│  │ (可调整宽度)            │  │  │  │  │                                │  ││  │
│  └──────────────────────────────┘  │  │  │  ┌────────────────────────────────┐  ││  │
│                                      │  │  │  │ DetailPanel (侧滑详情)        │  ││  │
│                                      │  │  │  │ (点击列表项 → 侧滑显示)       │  ││  │
│                                      │  │  │  └────────────────────────────────┘  ││  │
│                                      │  │  │                                      ││  │
│                                      │  │  └──────────────────────────────────────┘│  │
│                                      └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 交互模式

| 交互 | 行为 |
|------|------|
| 点击列表项 | 侧滑详情面板（保持上下文） |
| 点击 "新建" | Navigate 到详情页（全屏） |
| 点击 "编辑" | Navigate 到详情页（全屏） |
| 多选后点击 "查看关联" | Association Navigation Dialog（待实现） |

---

## 二、现有组件库分析

### 2.1 现有组件清单

| 组件 | 路径 | 状态 | 可复用性 |
|------|------|------|---------|
| **AppHeader** | `@/components/common/AppHeader.vue` | ✅ 可用 | 高 |
| **AppButton** | `@/components/common/AppButton/` | ✅ 可用 | 高 |
| **AppIcon** | `@/components/common/AppIcon/` | ✅ 可用 | 高 |
| **AppTabs** | `@/components/common/AppTabs/` | ✅ 可用 | 需调整 |
| **AppModal** | `@/components/common/AppModal/` | ✅ 可用 | 高 |
| **AppCard** | `@/components/common/AppCard/` | ✅ 可用 | 高 |
| **AppInput** | `@/components/common/AppInput/` | ✅ 可用 | 高 |
| **AppSelect** | `@/components/common/AppSelect/` | ✅ 可用 | 高 |
| **Pagination** | `@/components/common/Pagination/` | ✅ 可用 | 高 |
| **EmptyState** | `@/components/common/EmptyState/` | ✅ 可用 | 高 |
| **FilterBar** | `@/components/common/FilterBar/` | ✅ 可用 | 高 |
| **MetaListPage** | `@/components/common/MetaListPage/` | ✅ 可用 | 高 |
| **MetaDetailPage** | `@/components/common/MetaDetailPage/` | ✅ 可用 | 需调整 |
| **ObjectPage** | `@/components/common/ObjectPage/` | ✅ 可用 | 需调整 |
| **Drawer** | Element Plus 原生 | ✅ 可用 | 高 |
| **InlineEditCell** | `@/components/common/MetaListPage/` | ✅ 可用 | 高 |

### 2.2 现有组件对应关系

| 新需求 | 现有组件 | 复用方式 | 调整点 |
|--------|---------|---------|--------|
| WorkspaceHeader | AppHeader | 直接使用 | 可能需要扩展 |
| 主内容区容器 | 无 | 新建 | - |
| WorkspaceSidebar | 无 | 新建 | - |
| CollapsiblePanel | 无 | 新建 | - |
| ProductSelector | 原生 select | 封装 | 统一样式 |
| VersionSelector | 原生 select | 封装 | 统一样式 |
| ObjectTree | TreeNavNode | 重构 | 组件化 |
| RelationTree | RelationScopeNode | 重构 | 组件化 |
| TabBar | AppTabs | 复用 | 样式调整 |
| Toolbar | 原生 div | 封装 | - |
| ListView | MetaListPage | 复用 | 集成侧滑 |
| DetailPanel | 无 | 新建 | 侧滑详情 |
| AssociationDialog | AppModal | 复用 | 内容定制（待实现） |

---

## 三、需要新建的组件

### 3.1 核心容器组件

| 序号 | 组件 | 文件路径 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 1 | **AppWorkspace** | `@/components/common/AppWorkspace/` | P0 | 工作空间顶层容器 |
| 2 | **WorkspaceHeader** | `@/components/common/WorkspaceHeader/` | P0 | 全局 Header（扩展自 AppHeader） |
| 3 | **WorkspaceSidebar** | `@/components/common/WorkspaceSidebar/` | P0 | 可调整宽度侧边栏容器 |
| 4 | **WorkspaceMain** | `@/components/common/WorkspaceMain/` | P1 | 主内容区容器 |

### 3.2 Panel 系统组件

| 序号 | 组件 | 文件路径 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 5 | **WorkspaceSelectorPanel** | `@/components/common/WorkspaceSelectorPanel/` | P0 | 产品+版本选择器 Panel（合并） |
| 6 | **CollapsiblePanel** | `@/components/common/CollapsiblePanel/` | P0 | 可折叠 Panel 容器 |

### 3.3 树组件

| 序号 | 组件 | 文件路径 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 8 | **ObjectTree** | `@/components/common/ObjectTree/` | P0 | 对象树（重构自 TreeNavNode） |
| 9 | **RelationTree** | `@/components/common/RelationTree/` | P0 | 关系树（重构自 RelationScopeNode） |

### 3.4 详情组件

| 序号 | 组件 | 文件路径 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 10 | **DetailPanel** | `@/components/common/DetailPanel/` | P0 | 侧滑详情面板 |

### 3.5 工具栏组件

| 序号 | 组件 | 文件路径 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 11 | **WorkspaceToolbar** | `@/components/common/WorkspaceToolbar/` | P1 | 工作空间工具栏 |

### 3.6 待实现组件（Association Navigation）

| 序号 | 组件 | 文件路径 | 优先级 | 说明 |
|------|------|---------|--------|------|
| 12 | **AssociationDialog** | `@/components/common/AssociationDialog/` | P2 | 关联导航对话框 |
| 13 | **RelationGraph** | `@/components/common/RelationGraph/` | P2 | 关系图可视化 |

---

## 四、需要调整的现有组件

### 4.1 ObjectPage 组件

**当前状态**: 已有完整实现，支持 YAML 驱动渲染

**需要调整**:
```typescript
// 1. 新增 props
interface ObjectPageProps {
  // 新增：支持侧滑模式
  slidePanel?: boolean              // 默认 true
  slidePanelWidth?: string         // 默认 '500px'
  
  // 新增：支持内联编辑
  inlineEdit?: boolean             // 默认 false
  inlineEditConfig?: InlineEditConfig
}

// 2. 新增 events
interface ObjectPageEvents {
  'row-click': (row: any) => void    // 列表项点击（用于侧滑）
}
```

**调整建议**:
- 添加 `slidePanel` 模式支持
- 添加 `inlineEdit` 模式支持
- 优化 FieldGroup 的布局（已调整）

### 4.2 MetaListPage 组件

**当前状态**: 支持列表和表单模式

**需要调整**:
```typescript
// 1. 新增 props
interface MetaListPageProps {
  // 新增：侧滑详情支持
  enableSlideDetail?: boolean        // 默认 false
  slideDetailWidth?: string         // 默认 '500px'
  
  // 新增：行点击事件
  rowClickMode?: 'navigate' | 'slide' | 'none'  // 默认 'navigate'
}

// 2. 新增 events
interface MetaListPageEvents {
  'row-click': (row: any, index: number) => void
}
```

**调整建议**:
- 集成 DetailPanel 作为侧滑
- 保持 `view-mode` 切换逻辑不变
- 添加行点击事件

### 4.3 AppTabs 组件

**当前状态**: 基础 Tab 导航

**需要调整**:
```typescript
// 1. 新增 props
interface AppTabsProps {
  // 新增：Tab 徽章（显示数量）
  showCount?: boolean
  counts?: Record<string, number>
  
  // 新增：Tab 样式变体
  variant?: 'default' | 'pills' | 'bordered'
}

// 2. 新增样式
interface TabStyle {
  // 支持胶囊样式（类似 Salesforce）
  pills: 'background: transparent; border-radius: 20px;'
  bordered: 'border-bottom: 2px solid transparent;'
}
```

**调整建议**:
- 添加数量徽章支持
- 添加 `pills` 样式变体
- 优化激活状态的视觉反馈

### 4.4 AppHeader 组件

**当前状态**: 基础 Header

**需要调整**:
```typescript
// 新增 props
interface AppHeaderProps {
  // 新增：面包屑支持
  breadcrumbs?: Array<{ label: string; to?: string }>
  showBackButton?: boolean
  backButtonText?: string
  
  // 新增：右侧操作区
  showGlobalActions?: boolean
}
```

**调整建议**:
- 扩展为 WorkspaceHeader
- 添加面包屑支持
- 添加返回按钮支持

---

## 五、可直接复用的组件

### 5.1 基础 UI 组件

| 组件 | 复用方式 | 说明 |
|------|---------|------|
| **AppButton** | 直接使用 | 所有按钮 |
| **AppIcon** | 直接使用 | 所有图标 |
| **AppInput** | 直接使用 | 表单输入 |
| **AppSelect** | 直接使用 | 下拉选择 |
| **AppCheckbox** | 直接使用 | 多选 |
| **AppSwitch** | 直接使用 | 开关 |

### 5.2 布局组件

| 组件 | 复用方式 | 说明 |
|------|---------|------|
| **AppCard** | 直接使用 | Card 容器 |
| **AppModal** | 直接使用 | 模态框 |
| **Drawer** | 直接使用 | 侧滑容器 |

### 5.3 列表组件

| 组件 | 复用方式 | 说明 |
|------|---------|------|
| **Pagination** | 直接使用 | 分页器 |
| **EmptyState** | 直接使用 | 空状态 |
| **FilterBar** | 直接使用 | 过滤器 |

### 5.4 业务组件

| 组件 | 复用方式 | 说明 |
|------|---------|------|
| **MetaListPage** | 集成侧滑 | 列表页 |
| **MetaDetailPage** | 详情页 | 参考 |
| **InlineEditCell** | 直接使用 | 单元格编辑 |

---

## 六、组件架构图

### 6.1 组件依赖关系

```
AppWorkspace (新建)
├── WorkspaceHeader (新建/扩展 AppHeader)
│   ├── GlobalActions
│   └── UserMenu
│
├── WorkspaceSidebar (新建)
│   ├── CollapsiblePanel (新建)
│   │   ├── ProductSelectorPanel (新建)
│   │   ├── VersionSelectorPanel (新建)
│   │   ├── ObjectTree (新建/重构)
│   │   └── RelationTree (新建/重构)
│   └── Resizer (拖拽调整宽度)
│
└── WorkspaceMain (新建)
    ├── TabBar (复用 AppTabs)
    ├── FilterBar (复用)
    ├── WorkspaceToolbar (新建)
    │   ├── CreateButton
    │   ├── ExportButton
    │   ├── BatchDeleteButton
    │   └── SearchInput
    │
    └── ContentArea
        ├── ListView (复用 MetaListPage)
        │   ├── Table
        │   └── Pagination
        │
        └── DetailPanel (新建)
            └── ObjectPage
                ├── FieldGroup
                └── InlineEdit
```

### 6.2 数据流架构

```
┌─────────────────────────────────────────────────────────┐
│ WorkspaceStore (Pinia)                                 │
│                                                       │
│  state:                                                │
│  - selectedProductId                                  │
│  - selectedVersionId                                  │
│  - centerScope { type, nodeId }                      │
│  - relationScope { relationType }                     │
│  - filters                                           │
│  - selectedRows                                      │
│  - currentDetail (侧滑详情)                          │
│                                                       │
│  actions:                                            │
│  - selectProduct()                                   │
│  - selectVersion()                                   │
│  - setCenterScope()                                  │
│  - setRelationScope()                                │
│  - openDetail() / closeDetail()                      │
│                                                       │
│  computed:                                           │
│  - finalFilter (组合过滤条件)                         │
│  - filteredData                                      │
└─────────────────────────────────────────────────────────┘
           │                              ▲
           │                              │
           ▼                              │
┌─────────────────────┐      ┌──────────────────────┐
│  MetaListPage       │ ←── │   DetailPanel         │
│                    │      │                      │
│  @row-click → openDetail()    │   ObjectPage        │
│                    │      │                      │
└─────────────────────┘      └──────────────────────┘
```

---

## 七、实施优先级

### Phase 1: 核心架构 (P0)

| 序号 | 组件 | 工作量 | 依赖 |
|------|------|--------|------|
| 1 | AppWorkspace | 中 | 无 |
| 2 | WorkspaceHeader | 小 | AppHeader |
| 3 | WorkspaceSidebar | 中 | 无 |
| 4 | CollapsiblePanel | 中 | 无 |
| 5 | ProductSelectorPanel | 小 | 无 |
| 6 | VersionSelectorPanel | 小 | 无 |
| 7 | ObjectTree | 大 | TreeNavNode 重构 |
| 8 | RelationTree | 大 | RelationScopeNode 重构 |
| 9 | DetailPanel | 中 | 无 |
| 10 | ObjectPage 调整 | 小 | 添加侧滑支持 |

### Phase 2: 集成与优化 (P1)

| 序号 | 组件 | 工作量 | 依赖 |
|------|------|--------|------|
| 11 | WorkspaceToolbar | 小 | 无 |
| 12 | WorkspaceMain | 小 | 无 |
| 13 | MetaListPage 调整 | 小 | 添加侧滑支持 |
| 14 | AppTabs 调整 | 小 | 添加徽章支持 |

### Phase 3: 高级功能 (P2)

| 序号 | 组件 | 工作量 | 依赖 |
|------|------|--------|------|
| 15 | AssociationDialog | 大 | Dialog |
| 16 | RelationGraph | 大 | 可选 SVG/D3.js |

---

## 八、详细组件清单

### 8.1 新建组件规格

#### 1. AppWorkspace

```typescript
// 组件 Props
interface AppWorkspaceProps {
  title: string
  showBackButton?: boolean
  breadcrumbs?: Array<{ label: string; to?: string }>
  
  // Sidebar 配置
  sidebarWidth?: number
  sidebarMinWidth?: number
  sidebarMaxWidth?: number
  
  // 全局操作
  globalActions?: Array<{ key: string; label: string; icon?: string }>
}

// Events
interface AppWorkspaceEvents {
  'back': () => void
  'global-action': (key: string) => void
}
```

#### 2. CollapsiblePanel

```typescript
// 组件 Props
interface CollapsiblePanelProps {
  title: string
  collapsible?: boolean
  defaultCollapsed?: boolean
  badge?: string | number
  draggable?: boolean
  
  // Panel 内容
  loading?: boolean
  error?: Error | null
}

// Events
interface CollapsiblePanelEvents {
  'toggle': (collapsed: boolean) => void
  'refresh': () => void
}

// Slots
interface CollapsiblePanelSlots {
  default: {}
  actions: {}
  empty: {}
  error: {}
}
```

#### 3. DetailPanel

```typescript
// 组件 Props
interface DetailPanelProps {
  visible: boolean
  title?: string
  width?: string
  objectType?: string
  objectId?: string | number
  objectData?: Record<string, any>
  
  // 详情页配置
  viewName?: string
  sections?: Array<SectionConfig>
  
  // 编辑支持
  editable?: boolean
  inlineEdit?: boolean
}

// Events
interface DetailPanelEvents {
  'update:visible': (visible: boolean) => void
  'saved': (data: any) => void
  'deleted': () => void
  'navigate': (type: string, id: string) => void
}
```

#### 4. ObjectTree

```typescript
// 组件 Props
interface ObjectTreeProps {
  data: TreeNode[]
  selectedIds?: string[]
  checkedIds?: string[]
  
  // 选择模式
  selectionMode?: 'single' | 'multiple' | 'none'
  showCheckbox?: boolean
  
  // 交互
  loadOnSelect?: boolean
  expandOnSelect?: boolean
  
  // 工具栏
  showActions?: boolean
  actions?: Array<{ key: string; label: string }>
}

// TreeNode 类型
interface TreeNode {
  id: string
  name: string
  type: 'domain' | 'sub_domain' | 'service_module' | 'business_object'
  children?: TreeNode[]
  count?: number
  disabled?: boolean
}
```

#### 5. RelationTree

```typescript
// 组件 Props
interface RelationTreeProps {
  data: RelationNode[]
  selectedIds?: string[]
  
  // 选择模式
  selectionMode?: 'single' | 'multiple' | 'none'
  
  // 筛选
  filterByObjects?: string[]  // 根据选中的对象筛选
  
  // 工具栏
  showActions?: boolean
}

// RelationNode 类型
interface RelationNode {
  id: string
  relationType: string
  relationTypeName: string
  sourceObjectId: string
  targetObjectId: string
  sourceObjectName: string
  targetObjectName: string
  children?: RelationNode[]
  count?: number
}
```

### 8.2 调整组件规格

#### 1. ObjectPage 调整

```typescript
// 新增 Props
interface ObjectPageAdjustments {
  // 侧滑模式
  slideMode?: boolean
  slideWidth?: string
  
  // 紧凑模式
  compact?: boolean
  
  // 工具栏
  showToolbar?: boolean
  toolbarActions?: Array<ActionConfig>
}
```

#### 2. MetaListPage 调整

```typescript
// 新增 Props
interface MetaListPageAdjustments {
  // 侧滑详情
  enableSlideDetail?: boolean
  slideDetailWidth?: string
  rowClickAction?: 'navigate' | 'slide' | 'none'
  
  // 工具栏增强
  extraToolbarActions?: Array<ActionConfig>
}
```

---

## 九、待办清单

### 9.1 立即执行

```markdown
## TODO: Multi-Object Workspace Phase 1

- [ ] 创建 AppWorkspace 组件
- [ ] 创建 WorkspaceHeader 组件
- [ ] 创建 WorkspaceSidebar 组件
- [ ] 创建 CollapsiblePanel 组件
- [ ] 创建 ProductSelectorPanel 组件
- [ ] 创建 VersionSelectorPanel 组件
- [ ] 创建 ObjectTree 组件（重构自 TreeNavNode）
- [ ] 创建 RelationTree 组件（重构自 RelationScopeNode）
- [ ] 创建 DetailPanel 组件
- [ ] 调整 ObjectPage 支持侧滑模式
- [ ] 调整 MetaListPage 支持侧滑详情
```

### 9.2 短期执行

```markdown
## TODO: Multi-Object Workspace Phase 2

- [ ] 创建 WorkspaceToolbar 组件
- [ ] 创建 WorkspaceMain 组件
- [ ] 调整 AppTabs 支持数量徽章
- [ ] 集成测试完整流程
- [ ] 性能优化
```

### 9.3 中期执行（Association Navigation）

```markdown
## TODO: Association Navigation (P2)

- [ ] 创建 AssociationDialog 组件
- [ ] 创建 RelationGraph 组件（可选）
- [ ] 实现关系图可视化
- [ ] 实现多选对象的关联查询
- [ ] 集成到 Toolbar
```

---

## 十、总结

### 10.1 组件统计

| 类型 | 新建 | 复用 | 调整 | 合计 |
|------|------|------|------|------|
| 容器组件 | 4 | 0 | 1 | 5 |
| Panel 组件 | 3 | 0 | 0 | 3 |
| 树组件 | 2 | 0 | 0 | 2 |
| 详情组件 | 1 | 0 | 1 | 2 |
| 工具栏 | 1 | 0 | 0 | 1 |
| **合计** | **11** | **0** | **2** | **13** |

### 10.2 核心可复用组件

| 组件 | 复用场景 |
|------|---------|
| AppButton | 所有按钮 |
| AppIcon | 所有图标 |
| AppCard | Card 容器 |
| AppModal | Dialog 容器 |
| Drawer | 侧滑容器 |
| Pagination | 分页器 |
| EmptyState | 空状态 |
| FilterBar | 过滤器 |
| InlineEditCell | 单元格编辑 |
| MetaListPage | 列表页 |
| MetaDetailPage | 详情页参考 |

### 10.3 关键设计决策

1. **侧滑优先**：默认采用侧滑详情，保持列表上下文
2. **Panel 系统**：通过配置灵活组合侧边栏内容
3. **树组件重构**：从 UnifiedScopePanel 中提取独立的树组件
4. **状态集中**：使用 Pinia Store 统一管理状态
5. **组件解耦**：每个组件职责单一，便于测试和维护
