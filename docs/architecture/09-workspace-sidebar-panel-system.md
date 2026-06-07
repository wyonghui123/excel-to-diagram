# WorkspaceSidebar Panel 系统设计

> **版本**: v1.0  
> **更新日期**: 2024-05-13  
> **状态**: 详细设计

---

## 一、设计理念

### 1.1 当前实现分析

当前 `UnifiedScopePanel.vue` 的结构：

```vue
<UnifiedScopePanel>
  ├── ProductSelector/VersionSelector (固定选择器)
  ├── ObjectScopeSection (可折叠的对象范围)
  │   ├── SectionHeader (展开/收起)
  │   └── SectionBody (TreeNavNode)
  └── RelationScopeSection (可折叠的关系范围)
      ├── SectionHeader
      └── SectionBody (RelationScopeNode)
</UnifiedScopePanel>
```

**当前问题**：
1. ProductSelector/VersionSelector 写死，不灵活
2. 每个 Section 的折叠逻辑重复
3. 难以扩展新的 Panel（如"快捷筛选"、"最近访问"等）
4. 无法动态调整 Panel 顺序

### 1.2 建议的设计：Panel 系统

```
┌────────────────────────────────────────────────────────────┐
│ WorkspaceSidebar (Panel 容器)                               │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ CollapsiblePanel: ProductSelector                    │ │
│ │ ▼ 产品                    [−] [操作...]             │ │
│ │ ┌────────────────────────────────────────────────┐  │ │
│ │ │ [选择产品 ▼]                                   │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ CollapsiblePanel: VersionSelector                   │ │
│ │ ▶ 版本                   [−] [操作...]             │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ CollapsiblePanel: ObjectTree                       │ │
│ │ ▼ 对象范围                  [已选 5 项] [−]         │ │
│ │ ┌────────────────────────────────────────────────┐  │ │
│ │ │ TreeNavNode...                                 │  │ │
│ │ └────────────────────────────────────────────────┘  │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                            │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ CollapsiblePanel: RelationTree                      │ │
│ │ ▶ 关系范围                 [需刷新] [−]            │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                            │
│  (可扩展更多 Panel...)                                     │
│                                                            │
│  [+ 添加 Panel]  ← 可扩展性                                │
└────────────────────────────────────────────────────────────┘
```

---

## 二、核心组件设计

### 2.1 Panel 系统组件层级

```
WorkspaceSidebar
├── PanelContainer
│   ├── PanelHeader
│   │   ├── PanelTitle
│   │   ├── PanelBadge (数量/状态)
│   │   ├── PanelActions (操作按钮)
│   │   ├── CollapseToggle (展开/收起)
│   │   └── DragHandle (拖拽排序)
│   │
│   └── PanelBody
│       └── <slot> (自定义内容)
│
├── ProductSelectorPanel (extends CollapsiblePanel)
├── VersionSelectorPanel (extends CollapsiblePanel)
├── ObjectTreePanel (extends CollapsiblePanel)
├── RelationTreePanel (extends CollapsiblePanel)
└── QuickFilterPanel (扩展示例)
```

### 2.2 CollapsiblePanel 组件

```vue
<!-- CollapsiblePanel.vue -->
<template>
  <div 
    class="collapsible-panel"
    :class="{ 'is-collapsed': collapsed, 'is-dragging': dragging }"
  >
    <!-- Panel Header -->
    <div 
      class="panel-header"
      @click="toggleCollapse"
      :draggable="draggable"
      @dragstart="handleDragStart"
      @dragend="handleDragEnd"
      @dragover.prevent="handleDragOver"
      @drop="handleDrop"
    >
      <div class="panel-header-left">
        <span class="collapse-icon">{{ collapsed ? '▶' : '▼' }}</span>
        <span class="panel-title">{{ title }}</span>
        <span v-if="badge" class="panel-badge" :class="badgeClass">{{ badge }}</span>
      </div>
      
      <div class="panel-header-right">
        <slot name="actions" />
        <button 
          v-if="collapsible"
          class="collapse-btn" 
          @click.stop="toggleCollapse"
          :title="collapsed ? '展开' : '收起'"
        >
          {{ collapsed ? '−' : '−' }}
        </button>
      </div>
    </div>
    
    <!-- Panel Body -->
    <div v-show="!collapsed" class="panel-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  title: { type: String, required: true },
  collapsible: { type: Boolean, default: true },
  defaultCollapsed: { type: Boolean, default: false },
  badge: { type: [String, Number], default: null },
  badgeClass: { type: String, default: '' },
  draggable: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle', 'remove', 'drag-start', 'drag-end', 'drag-over', 'drop'])

const collapsed = ref(props.defaultCollapsed)

function toggleCollapse() {
  if (!props.collapsible) return
  collapsed.value = !collapsed.value
  emit('toggle', collapsed.value)
}

// 拖拽相关
const dragging = ref(false)

function handleDragStart(e) {
  dragging.value = true
  e.dataTransfer.effectAllowed = 'move'
  emit('drag-start', e)
}

function handleDragEnd(e) {
  dragging.value = false
  emit('drag-end', e)
}
</script>

<style scoped>
.collapsible-panel {
  border-bottom: 1px solid var(--color-border-light);
  transition: all 0.2s;
}

.collapsible-panel.is-dragging {
  opacity: 0.5;
  transform: scale(0.98);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  background: var(--color-bg-spotlight);
  border-bottom: 1px solid var(--color-border-secondary);
  transition: background 0.2s;
}

.panel-header:hover {
  background: var(--color-bg-tertiary);
}

.panel-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panel-badge {
  font-size: 11px;
  padding: 2px 6px;
  background: var(--color-primary-bg);
  color: var(--color-primary);
  border-radius: var(--radius-badge);
}

.panel-header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.collapse-icon {
  font-size: 10px;
  color: var(--color-text-tertiary);
  width: 14px;
  text-align: center;
}

.panel-body {
  padding: 8px 0;
  overflow-y: auto;
  max-height: 400px;
}

.collapsible-panel.is-collapsed .panel-body {
  display: none;
}
</style>
```

### 2.3 WorkspaceSidebar 容器组件

```vue
<!-- WorkspaceSidebar.vue -->
<template>
  <div class="workspace-sidebar" :style="{ width: width + 'px' }">
    <div class="sidebar-header" v-if="$slots.header">
      <slot name="header" />
    </div>
    
    <div class="sidebar-panels">
      <CollapsiblePanel
        v-for="(panel, index) in panels"
        :key="panel.id"
        :title="panel.title"
        :badge="panel.badge"
        :badge-class="panel.badgeClass"
        :default-collapsed="panel.defaultCollapsed"
        :draggable="sortable"
        @toggle="(collapsed) => handlePanelToggle(panel.id, collapsed)"
        @drag-start="(e) => handleDragStart(index)"
        @drag-end="handleDragEnd"
        @drag-over="(e) => handleDragOver(e, index)"
        @drop="() => handleDrop(index)"
      >
        <!-- Panel 内容 -->
        <component 
          :is="panel.component" 
          v-bind="panel.props"
          v-on="panel.listeners"
        />
        
        <!-- Panel 自定义操作 -->
        <template #actions>
          <button 
            v-for="action in panel.actions"
            :key="action.key"
            class="panel-action-btn"
            @click.stop="action.handler"
            :title="action.label"
          >
            {{ action.label }}
          </button>
        </template>
      </CollapsiblePanel>
    </div>
    
    <div class="sidebar-footer" v-if="$slots.footer">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  width: { type: Number, default: 300 },
  minWidth: { type: Number, default: 200 },
  maxWidth: { type: Number, default: 500 },
  sortable: { type: Boolean, default: false },
  panels: { type: Array, default: () => [] },
})

const emit = defineEmits(['panel-toggle', 'reorder', 'resize'])

// Panel 折叠状态管理
const collapsedPanels = ref(new Set())

function handlePanelToggle(panelId, collapsed) {
  if (collapsed) {
    collapsedPanels.value.add(panelId)
  } else {
    collapsedPanels.value.delete(panelId)
  }
  emit('panel-toggle', { panelId, collapsed })
}

// 拖拽排序
let draggedIndex = null

function handleDragStart(index) {
  draggedIndex = index
}

function handleDragEnd() {
  draggedIndex = null
}

function handleDragOver(e, index) {
  e.dataTransfer.dropEffect = 'move'
}

function handleDrop(dropIndex) {
  if (draggedIndex === null || draggedIndex === dropIndex) return
  
  const newPanels = [...props.panels]
  const [removed] = newPanels.splice(draggedIndex, 1)
  newPanels.splice(dropIndex, 0, removed)
  
  emit('reorder', newPanels)
}

// 宽度调整
const resizing = ref(false)
let startX = 0
let startWidth = 0

function startResize(e) {
  resizing.value = true
  startX = e.clientX
  startWidth = props.width
  document.addEventListener('mousemove', doResize)
  document.addEventListener('mouseup', stopResize)
}

function doResize(e) {
  if (!resizing.value) return
  const diff = e.clientX - startX
  const newWidth = Math.max(props.minWidth, Math.min(props.maxWidth, startWidth + diff))
  emit('resize', newWidth)
}

function stopResize() {
  resizing.value = false
  document.removeEventListener('mousemove', doResize)
  document.removeEventListener('mouseup', stopResize)
}
</script>
```

---

## 三、Panel 配置系统

### 3.1 Panel 配置结构

```typescript
interface PanelConfig {
  id: string                    // Panel 唯一标识
  title: string                 // Panel 标题
  component: Component           // Panel 内容组件
  props?: Record<string, any>    // 传递给组件的 props
  listeners?: Record<string, Function>  // 事件监听器
  
  // Panel 行为配置
  collapsible?: boolean          // 是否可折叠
  defaultCollapsed?: boolean   // 默认折叠状态
  draggable?: boolean           // 是否可拖拽排序
  removable?: boolean           // 是否可移除
  
  // Panel 状态
  badge?: string | number       // 徽章显示
  badgeClass?: string           // 徽章样式类
  
  // 操作按钮
  actions?: Array<{
    key: string
    label: string
    handler: () => void
  }>
}
```

### 3.2 预定义的 Panel 类型

```typescript
// 预定义 Panel 工厂函数

function createProductSelectorPanel(store) {
  return {
    id: 'product-selector',
    title: '产品',
    component: ProductSelectorComponent,
    props: {
      products: store.products,
      selectedId: store.selectedProductId,
    },
    listeners: {
      change: (id) => store.selectProduct(id)
    },
    collapsible: true,
    defaultCollapsed: false,
    draggable: false,
    removable: false,
  }
}

function createVersionSelectorPanel(store) {
  return {
    id: 'version-selector',
    title: '版本',
    component: VersionSelectorComponent,
    props: {
      versions: store.versions,
      selectedId: store.selectedVersionId,
      disabled: !store.selectedProductId,
    },
    listeners: {
      change: (id) => store.selectVersion(id)
    },
    collapsible: true,
    defaultCollapsed: false,
    // 依赖于产品选择，必须在产品选择之后
    dependsOn: 'product-selector',
  }
}

function createObjectTreePanel(options) {
  return {
    id: 'object-tree',
    title: '对象范围',
    component: ObjectTreeComponent,
    props: {
      data: options.treeData,
      checkedIds: options.checkedNodeIds,
    },
    listeners: {
      'node-check': options.handleNodeCheck,
      'node-toggle': options.handleNodeToggle,
    },
    collapsible: true,
    defaultCollapsed: false,
    draggable: true,
    removable: false,
    badge: options.checkedNodeIds.length > 0 ? `已选 ${options.checkedNodeIds.length} 项` : null,
    actions: [
      { key: 'expand', label: '展开', handler: options.expandAll },
      { key: 'collapse', label: '收起', handler: options.collapseAll },
      { key: 'select-all', label: '全选', handler: options.selectAll },
      { key: 'clear', label: '清空', handler: options.clearAll },
      { key: 'refresh', label: '刷新', handler: options.refresh },
    ],
  }
}

function createRelationTreePanel(options) {
  return {
    id: 'relation-tree',
    title: '关系范围',
    component: RelationTreeComponent,
    props: {
      data: options.relationTreeData,
      selectedIds: options.selectedScopeIds,
      stale: options.relationStale,
    },
    listeners: {
      'relation-select': options.handleRelationSelect,
    },
    collapsible: true,
    defaultCollapsed: true,  // 默认折叠
    draggable: true,
    removable: false,
    badgeClass: options.relationStale ? 'stale' : '',
    badge: options.relationStale ? '需刷新' : (options.relationTotalCount > 0 ? `(${options.relationTotalCount})` : null),
    actions: [
      { key: 'expand', label: '展开', handler: options.expandAll },
      { key: 'collapse', label: '收起', handler: options.collapseAll },
      { key: 'select-all', label: '全选', handler: options.selectAll },
      { key: 'clear', label: '清空', handler: options.clearAll },
      { key: 'refresh', label: '刷新', handler: options.refresh },
    ],
  }
}
```

### 3.3 Panel 依赖关系

```typescript
// Panel 依赖关系配置
const panelDependencies = {
  'version-selector': ['product-selector'],      // 版本选择依赖产品选择
  'object-tree': ['version-selector'],            // 对象树依赖版本选择
  'relation-tree': ['object-tree'],               // 关系树依赖对象树
}

// Panel 可见性规则
const panelVisibilityRules = {
  'version-selector': () => selectedProductId.value !== null,
  'object-tree': () => selectedVersionId.value !== null,
  'relation-tree': () => checkedNodeIds.value.length > 0,
}
```

---

## 四、使用示例

### 4.1 基本使用

```vue
<template>
  <WorkspaceSidebar
    :panels="panels"
    :width="sidebarWidth"
    :sortable="true"
    @panel-toggle="handlePanelToggle"
    @reorder="handleReorder"
    @resize="handleResize"
  />
</template>

<script setup>
import { computed } from 'vue'
import WorkspaceSidebar from './WorkspaceSidebar.vue'
import CollapsiblePanel from './CollapsiblePanel.vue'
import ProductSelector from './panels/ProductSelector.vue'
import VersionSelector from './panels/VersionSelector.vue'
import ObjectTree from './panels/ObjectTree.vue'
import RelationTree from './panels/RelationTree.vue'

const store = useArchDataStore()

const panels = computed(() => {
  const result = []
  
  // 1. 产品选择器（总是显示）
  result.push(createProductSelectorPanel(store))
  
  // 2. 版本选择器（依赖产品选择）
  if (store.selectedProductId) {
    result.push(createVersionSelectorPanel(store))
  }
  
  // 3. 对象树（依赖版本选择）
  if (store.selectedVersionId) {
    result.push(createObjectTreePanel({
      treeData: store.treeData,
      checkedNodeIds: store.checkedNodeIds,
      // ... 其他 options
    }))
  }
  
  // 4. 关系树（依赖对象选择）
  if (store.checkedNodeIds.length > 0) {
    result.push(createRelationTreePanel({
      relationTreeData: store.relationTreeData,
      // ... 其他 options
    }))
  }
  
  return result
})
</script>
```

### 4.2 动态添加 Panel

```vue
<template>
  <WorkspaceSidebar :panels="panels">
    <!-- 添加新 Panel 的按钮 -->
    <template #footer>
      <div class="add-panel-section">
        <el-dropdown @command="handleAddPanel">
          <button class="add-panel-btn">
            <span>+</span> 添加 Panel
          </button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="quick-filter">快捷筛选</el-dropdown-item>
              <el-dropdown-item command="recent-items">最近访问</el-dropdown-item>
              <el-dropdown-item command="favorites">收藏夹</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>
  </WorkspaceSidebar>
</template>

<script setup>
function handleAddPanel(command) {
  const newPanel = createCustomPanel(command)
  panels.value.push(newPanel)
}
</script>
```

---

## 五、Panel 状态管理

### 5.1 用户偏好持久化

```typescript
// 保存用户对 Panel 的自定义设置
function savePanelPreferences() {
  const preferences = {
    sidebarWidth: sidebarWidth.value,
    collapsedPanels: Array.from(collapsedPanels.value),
    panelOrder: panels.value.map(p => p.id),
    hiddenPanels: hiddenPanels.value,
  }
  localStorage.setItem('workspace-sidebar-prefs', JSON.stringify(preferences))
}

// 恢复用户偏好
function loadPanelPreferences() {
  const saved = localStorage.getItem('workspace-sidebar-prefs')
  if (saved) {
    const prefs = JSON.parse(saved)
    sidebarWidth.value = prefs.sidebarWidth
    collapsedPanels.value = new Set(prefs.collapsedPanels)
    hiddenPanels.value = new Set(prefs.hiddenPanels)
    // 按照保存的顺序重新排列 panels
    if (prefs.panelOrder) {
      panels.value.sort((a, b) => 
        prefs.panelOrder.indexOf(a.id) - prefs.panelOrder.indexOf(b.id)
      )
    }
  }
}

// 监听变化自动保存
watch([sidebarWidth, collapsedPanels, panels], () => {
  savePanelPreferences()
}, { deep: true })
```

### 5.2 Panel 状态类型

```typescript
type PanelState = {
  id: string
  collapsed: boolean           // 是否折叠
  order: number               // 排序顺序
  visible: boolean            // 是否可见
  customProps?: Record<string, any>  // 用户自定义属性
}
```

---

## 六、交互设计细节

### 6.1 折叠交互

| 操作 | 行为 |
|------|------|
| 点击 Header | 切换折叠状态 |
| 双击 Header | 快速折叠/展开 |
| 右键 Header | 显示菜单（折叠全部/展开全部） |
| 快捷键 `[` | 折叠当前 Panel |
| 快捷键 `]` | 展开当前 Panel |

### 6.2 拖拽排序交互

| 操作 | 行为 |
|------|------|
| 拖拽 Header | 显示拖拽预览 |
| 拖拽到位置 | 显示放置指示线 |
| 释放 | Panel 移动到新位置 |
| 取消（按 Escape） | Panel 返回原位置 |

### 6.3 视觉反馈

```css
/* 拖拽中 */
.panel-header.dragging {
  background: var(--color-primary-bg);
  border: 2px dashed var(--color-primary);
}

/* 放置目标 */
.panel-header.drag-over {
  background: var(--color-success-bg);
  border-top: 3px solid var(--color-success);
}

/* 折叠状态 */
.panel-header.collapsed .collapse-icon {
  transform: rotate(-90deg);
}
```

---

## 七、与现有实现的对比

### 7.1 现有 UnifiedScopePanel

| 特性 | 实现方式 |
|------|----------|
| 折叠 | 通过 `v-show` 控制，逻辑分散 |
| ProductSelector | 硬编码在组件内 |
| VersionSelector | 硬编码在组件内 |
| ObjectTree | SectionBody 内嵌 |
| RelationTree | SectionBody 内嵌 |
| 扩展性 | 差，难以添加新 Panel |

### 7.2 Panel 系统

| 特性 | 实现方式 |
|------|----------|
| 折叠 | 统一 CollapsiblePanel 组件 |
| ProductSelector | 可配置的 Panel |
| VersionSelector | 可配置的 Panel |
| ObjectTree | 可配置的 Panel |
| RelationTree | 可配置的 Panel |
| 扩展性 | 好，通过配置添加新 Panel |
| 拖拽排序 | 原生 HTML5 Drag & Drop |
| 状态持久化 | 支持用户偏好保存 |

### 7.3 迁移计划

1. **Phase 1**: 创建 CollapsiblePanel 组件
2. **Phase 2**: 创建各个 Panel 内容组件
3. **Phase 3**: 创建 WorkspaceSidebar 容器
4. **Phase 4**: 重构 UnifiedScopePanel 使用新架构
5. **Phase 5**: 添加拖拽排序和偏好持久化

---

## 八、附录

### A. Panel 操作菜单设计

```vue
<!-- Panel 操作菜单 -->
<el-dropdown trigger="click" @command="handleAction">
  <button class="panel-menu-btn">⋮</button>
  <template #dropdown>
    <el-dropdown-menu>
      <el-dropdown-item command="collapse">折叠</el-dropdown-item>
      <el-dropdown-item command="expand">展开</el-dropdown-item>
      <el-dropdown-item command="pin">固定位置</el-dropdown-item>
      <el-dropdown-item command="hide" divided>隐藏</el-dropdown-item>
    </el-dropdown-menu>
  </template>
</el-dropdown>
```

### B. Panel 空状态设计

```vue
<CollapsiblePanel title="对象范围">
  <div v-if="loading" class="panel-loading">
    <el-skeleton :rows="3" animated />
  </div>
  
  <div v-else-if="!data || data.length === 0" class="panel-empty">
    <el-empty description="暂无数据">
      <el-button size="small" @click="$emit('retry')">重试</el-button>
    </el-empty>
  </div>
  
  <div v-else class="panel-content">
    <!-- 实际内容 -->
  </div>
</CollapsiblePanel>
```

### C. Panel 错误状态设计

```vue
<CollapsiblePanel title="对象范围">
  <div v-if="error" class="panel-error">
    <el-alert
      :title="error.message"
      type="error"
      :closable="false"
    >
      <template #extra>
        <el-button size="small" @click="$emit('retry')">重试</el-button>
      </template>
    </el-alert>
  </div>
</CollapsiblePanel>
```
