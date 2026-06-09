## 目录

1. [一、设计决策](#一-设计决策)
2. [二、WorkspaceSelectorPanel 组件设计](#二-workspaceselectorpanel-组件设计)
3. [三、简化的 Sidebar Panel 配置](#三-简化的-sidebar-panel-配置)
4. [四、组件清单（更新版）](#四-组件清单（更新版）)
5. [五、实施计划](#五-实施计划)

---
# WorkspaceSelectorPanel 设计

> **版本**: v1.0  
> **更新日期**: 2024-05-13  
> **状态**: 简化设计

---

## 一、设计决策

### 1.1 Product + Version 合并为一个 SelectorPanel

**原因**：
1. 产品和版本选择是紧密关联的两个操作
2. 用户通常先选择产品，然后才能选择版本
3. 减少侧边栏的 Panel 数量
4. 更符合当前 UnifiedScopePanel 的实现方式

### 1.2 合并后的 Panel 结构

```
┌─────────────────────────────────────┐
│ WorkspaceSidebar                     │
│                                      │
│ ┌─────────────────────────────────┐ │
│ │ WorkspaceSelectorPanel           │ │ ← 合并后的选择器 Panel
│ │ ▼ 产品与版本                    │ │
│ │                                 │ │
│ │ 产品: [选择产品 ▼]              │ │
│ │ 版本: [选择版本 ▼]              │ │
│ │                                 │ │
│ │ 已选择: 产品 A → v1.0          │ │
│ └─────────────────────────────────┘ │
│                                      │
│ ┌─────────────────────────────────┐ │
│ │ CollapsiblePanel: ObjectTree    │ │
│ │ ▼ 对象范围                      │ │
│ └─────────────────────────────────┘ │
│                                      │
│ ┌─────────────────────────────────┐ │
│ │ CollapsiblePanel: RelationTree  │ │
│ │ ▶ 关系范围                      │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## 二、WorkspaceSelectorPanel 组件设计

### 2.1 组件 Props

```typescript
interface WorkspaceSelectorPanelProps {
  // 产品选择
  products: Array<{ id: string; name: string }>
  selectedProductId: string | null
  
  // 版本选择
  versions: Array<{ id: string; name: string; status?: string }>
  selectedVersionId: string | null
  
  // 状态
  loadingProducts?: boolean
  loadingVersions?: boolean
  disabled?: boolean
}

interface WorkspaceSelectorPanelEvents {
  'product-change': (productId: string) => void
  'version-change': (versionId: string) => void
}
```

### 2.2 组件模板

```vue
<template>
  <div class="workspace-selector-panel">
    <!-- Panel Header -->
    <div class="selector-header">
      <span class="selector-title">产品与版本</span>
      <span v-if="selectedProduct && selectedVersion" class="selection-summary">
        {{ selectedProduct.name }} → {{ selectedVersion.name }}
      </span>
    </div>
    
    <!-- Panel Body -->
    <div class="selector-body">
      <!-- 产品选择 -->
      <div class="selector-row">
        <label class="selector-label">产品</label>
        <el-select
          :model-value="selectedProductId"
          @change="handleProductChange"
          placeholder="请选择产品"
          :disabled="disabled || loadingProducts"
          class="selector-select"
        >
          <el-option
            v-for="product in products"
            :key="product.id"
            :label="product.name"
            :value="product.id"
          />
        </el-select>
      </div>
      
      <!-- 版本选择 -->
      <div class="selector-row">
        <label class="selector-label">版本</label>
        <el-select
          :model-value="selectedVersionId"
          @change="handleVersionChange"
          placeholder="请先选择产品"
          :disabled="disabled || !selectedProductId || loadingVersions"
          class="selector-select"
        >
          <el-option
            v-for="version in versions"
            :key="version.id"
            :label="version.name"
            :value="version.id"
          />
        </el-select>
      </div>
      
      <!-- 加载状态 -->
      <div v-if="loadingProducts || loadingVersions" class="selector-loading">
        <span class="loading-spinner"></span>
        <span>加载中...</span>
      </div>
      
      <!-- 空状态 -->
      <div v-else-if="!selectedProductId" class="selector-empty">
        请先选择产品和版本
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps<WorkspaceSelectorPanelProps>()
const emit = defineEmits<WorkspaceSelectorPanelEvents>()

const selectedProduct = computed(() => 
  props.products.find(p => p.id === props.selectedProductId)
)

const selectedVersion = computed(() => 
  props.versions.find(v => v.id === props.selectedVersionId)
)

function handleProductChange(productId) {
  emit('product-change', productId)
}

function handleVersionChange(versionId) {
  emit('version-change', versionId)
}
</script>

<style scoped>
.workspace-selector-panel {
  border-bottom: 1px solid var(--color-border-light);
}

.selector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--color-bg-spotlight);
  border-bottom: 1px solid var(--color-border-secondary);
}

.selector-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.selection-summary {
  font-size: 11px;
  color: var(--color-primary);
  background: var(--color-primary-bg);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.selector-body {
  padding: 12px 14px;
}

.selector-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.selector-row:last-child {
  margin-bottom: 0;
}

.selector-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  min-width: 32px;
  flex-shrink: 0;
}

.selector-select {
  flex: 1;
}

.selector-loading,
.selector-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
```

---

## 三、简化的 Sidebar Panel 配置

### 3.1 Panel 配置结构

```typescript
const panels = computed(() => {
  const result = []
  
  // 1. 选择器 Panel（产品 + 版本）
  result.push({
    id: 'selector',
    title: '产品与版本',
    component: WorkspaceSelectorPanel,
    props: {
      products: store.products,
      versions: store.versions,
      selectedProductId: store.selectedProductId,
      selectedVersionId: store.selectedVersionId,
      loadingProducts: store.loadingProducts,
      loadingVersions: store.loadingVersions,
    },
    listeners: {
      'product-change': (id) => store.selectProduct(id),
      'version-change': (id) => store.selectVersion(id),
    },
    collapsible: false,  // 选择器默认展开
    defaultCollapsed: false,
  })
  
  // 2. 对象树（依赖版本选择）
  if (store.selectedVersionId) {
    result.push({
      id: 'object-tree',
      title: '对象范围',
      component: ObjectTreePanel,
      props: { ... },
      collapsible: true,
      defaultCollapsed: false,
    })
  }
  
  // 3. 关系树（依赖对象选择）
  if (store.checkedNodeIds.length > 0) {
    result.push({
      id: 'relation-tree',
      title: '关系范围',
      component: RelationTreePanel,
      props: { ... },
      collapsible: true,
      defaultCollapsed: true,  // 关系树默认折叠
    })
  }
  
  return result
})
```

### 3.2 简化后的 Sidebar 布局

```
┌─────────────────────────────────────┐
│ WorkspaceSidebar                     │
│                                      │
│ ┌─────────────────────────────────┐ │
│ │ WorkspaceSelectorPanel           │ │ ← 选择器 Panel
│ │ 产品与版本                        │ │
│ │                                 │ │
│ │ 产品: [产品 A ▼]                 │ │
│ │ 版本: [v1.0 ▼]                  │ │
│ │                                 │ │
│ │ 已选择: 产品 A → v1.0          │ │
│ └─────────────────────────────────┘ │
│                                      │
│ ┌─────────────────────────────────┐ │
│ │ ▼ 对象范围         [已选 5 项]  │ │
│ │                                  │ │
│ │ 领域 A                           │ │
│ │   ├─ 子领域 A.1                 │ │
│ │   └─ 子领域 A.2                 │ │
│ └─────────────────────────────────┘ │
│                                      │
│ ┌─────────────────────────────────┐ │
│ │ ▶ 关系范围         [需刷新]      │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## 四、组件清单（更新版）

### 4.1 新建组件（10个）

| 序号 | 组件 | 优先级 | 说明 |
|------|------|--------|------|
| 1 | **AppWorkspace** | P0 | 工作空间顶层容器 |
| 2 | **WorkspaceHeader** | P0 | 全局 Header |
| 3 | **WorkspaceSidebar** | P0 | 侧边栏容器 |
| 4 | **CollapsiblePanel** | P0 | 可折叠 Panel 容器 |
| 5 | **WorkspaceSelectorPanel** | P0 | 产品+版本选择器 Panel |
| 6 | **ObjectTreePanel** | P0 | 对象树 Panel（重构） |
| 7 | **RelationTreePanel** | P0 | 关系树 Panel（重构） |
| 8 | **DetailPanel** | P0 | 侧滑详情面板 |
| 9 | **WorkspaceMain** | P1 | 主内容区容器 |
| 10 | **WorkspaceToolbar** | P1 | 工作空间工具栏 |

### 4.2 调整组件（2个）

| 组件 | 调整内容 |
|------|---------|
| **ObjectPage** | 添加侧滑模式支持 |
| **MetaListPage** | 添加侧滑详情支持 |

---

## 五、实施计划

### Phase 1: 核心架构 (P0)

1. AppWorkspace
2. WorkspaceHeader
3. WorkspaceSidebar
4. CollapsiblePanel
5. **WorkspaceSelectorPanel** ← 简化后的选择器
6. ObjectTreePanel（重构自 TreeNavNode）
7. RelationTreePanel（重构自 RelationScopeNode）
8. DetailPanel

### Phase 2: 集成优化 (P1)

1. WorkspaceMain
2. WorkspaceToolbar
3. ObjectPage 调整
4. MetaListPage 调整
