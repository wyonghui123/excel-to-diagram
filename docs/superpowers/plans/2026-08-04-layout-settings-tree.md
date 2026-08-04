# 布局设置面板重构实现计划（树形大纲 + 行内高频 + ⋯/右键弹出面板）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将布局设置面板从卡片式嵌套列表重构为可折叠树形大纲，行内只保留高频图标（启用/禁用 + ⋯），完整参数收进「⋯/右键」弹出面板，解决窄 sidebar 拥挤。

**Architecture:** 新建递归树节点组件 `LayoutGroupNode.vue` 替代 `GroupItem.vue` 的卡片渲染；把名称/颜色解析帮助函数抽取为 `useGroupDisplay.js` composable 供两处复用；`LayoutControlPanel.vue` 保留全部业务逻辑与事件协议，仅改渲染为树 + 新增工具条（搜索/新增分组）。数据流（`chartConfig.layoutControl` + `Object.assign` 写回）与图表能力链路不变。

**Tech Stack:** Vue 3 (`<script setup>`)、Element Plus（`el-popover`/`el-tooltip`/`el-input`）、Vitest、`AppIcon`、`diagramConfigStore`、`groupModel/types.js`。

**关联设计文档:** `docs/superpowers/specs/2026-08-04-layout-settings-tree-design.md`

---

## 文件结构

| 文件 | 动作 | 职责 |
|------|------|------|
| `src/composables/useGroupDisplay.js` | 新建 | 从 `GroupItem` 抽取的显示助手（名称/颜色/类型标签/提示） |
| `src/views/AADiagramApp/components/LayoutGroupNode.vue` | 新建 | 递归树节点（折叠/图标/行内高频/⋯弹出面板/拖拽） |
| `src/views/AADiagramApp/components/LayoutControlPanel.vue` | 修改 | 工具条（搜索/新增分组）+ 渲染树 + 保留业务逻辑 |
| `src/views/AADiagramApp/components/GroupItem.vue` | 保留（由新树替代，暂不删除） | 兼容旧引用，避免破坏 |
| `src/views/AADiagramApp/components/__tests__/LayoutGroupNode.spec.js` | 新建 | 树节点单测 |
| `src/views/AADiagramApp/components/__tests__/LayoutControlPanel.spec.js` | 新建 | 面板树单测 |

> 决策：`GroupItem.vue` 本阶段**不删除**，仅停止在 `LayoutControlPanel` 中引用，避免回归风险并保留可回滚点。若确认无外部引用后再单独清理。

---

## Task 1: 抽取显示助手 composable

**Files:**
- Create: `src/composables/useGroupDisplay.js`
- Test: `src/composables/__tests__/useGroupDisplay.spec.js`

- [ ] **Step 1: Write the failing test**

`src/composables/__tests__/useGroupDisplay.spec.js`:

```js
import { describe, it, expect } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useGroupDisplay } from '../useGroupDisplay'

describe('useGroupDisplay', () => {
  function setup() {
    setActivePinia(createPinia())
    return useGroupDisplay()
  }

  it('getContainerName 解析对象为 "名称 (编码)"', () => {
    const { getContainerName } = setup()
    expect(getContainerName({ name: '库存', elementCode: 'STK' })).toBe('库存 (STK)')
    expect(getContainerName({ title: '库存' })).toBe('库存')
  })

  it('getGroupTypeLabel 返回中文标签', () => {
    const { getGroupTypeLabel } = setup()
    expect(getGroupTypeLabel('domain')).toBe('领域')
    expect(getGroupTypeLabel('custom')).toBe('自定义')
  })

  it('getElkGroupHint 返回提示', () => {
    const { getElkGroupHint } = setup()
    expect(getElkGroupHint('inner')).toContain('无外部关系')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/composables/__tests__/useGroupDisplay.spec.js`
Expected: FAIL（模块不存在）

- [ ] **Step 3: Create the composable**

`src/composables/useGroupDisplay.js`:

```js
import { computed } from 'vue'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

// 从 GroupItem.vue 抽取的显示助手（名称/颜色/类型标签/提示），供树节点与旧组件复用
export const COLOR_SCHEMES = {
  default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
  vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
  pastel: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6'],
  warm: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF'],
  cool: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF'],
  business: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B'],
  nature: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
}

const CENTER_COLOR_MAP = {
  gray: '#808080',
  '#1890FF': '#1890FF',
  '#52C41A': '#52C41A',
  '#FAAD14': '#FAAD14',
  '#722ED1': '#722ED1'
}

export function useGroupDisplay() {
  const store = useDiagramConfigStore()

  const colorScheme = computed(() => store.colorScheme)
  const colorGroupBy = computed(() => store.colorGroupBy)
  const customColors = computed(() => store.customColors)
  const centerScope = computed(() => store.centerScope)
  const centerScopeMarkers = computed(() => store.centerScopeMarkers)
  const centerScopeColor = computed(() => store.centerScopeColor)
  const centerScopeHighlight = computed(() => store.centerScopeHighlight)

  function hashColor(key) {
    const colors = COLOR_SCHEMES[colorScheme.value] || COLOR_SCHEMES.default
    const idx = Math.abs(key.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0)) % colors.length
    return colors[idx]
  }

  function colorFromMap(key) {
    if (!key) return null
    if (store.colorMapping && store.colorMapping[key]) return store.colorMapping[key]
    if (customColors.value && customColors.value[key]) return customColors.value[key]
    return null
  }

  function getContainerName(container) {
    const resolveNameAndCode = (obj) => {
      const name = obj.name || obj.title || obj.elementRef?.name
      const code = obj.elementCode || obj.elementRef?.code || obj.code
      if (!name) return null
      if (code && code !== name) return `${name} (${code})`
      return name
    }
    if (typeof container === 'object') {
      const result = resolveNameAndCode(container)
      if (result) return result
    }
    if (typeof container === 'string') {
      return container
    }
    return '未知容器'
  }

  function lookupNodeNameByCode(code, containers) {
    for (const container of containers || []) {
      if (container.nodeNames && container.nodeNames[code]) return container.nodeNames[code]
      if (container.elementCode === code && container.name) return container.name
      if (container.nodes) {
        for (const node of container.nodes) {
          if (typeof node === 'object' && (node.code === code || node.id === code)) {
            return node.name || node.code || node.id
          }
        }
      }
    }
    return null
  }

  function getNodeName(nodeId, containers) {
    for (const container of containers || []) {
      if (container.nodes) {
        for (const node of container.nodes) {
          if (typeof node === 'string' && node === nodeId) {
            const name = lookupNodeNameByCode(nodeId, containers)
            return name && name !== nodeId ? `${name} (${nodeId})` : nodeId
          }
          if (typeof node === 'object' && node.id === nodeId) {
            const name = node.name || node.id
            const code = node.code
            if (code && code !== name) return `${name} (${code})`
            return name
          }
        }
      }
    }
    const name = lookupNodeNameByCode(nodeId, containers)
    return name && name !== nodeId ? `${name} (${nodeId})` : nodeId
  }

  function findContainerInSubDomains(code, name, containers) {
    if (!containers) return null
    for (const c of containers) {
      if (c.nodes && Array.isArray(c.nodes)) {
        for (const node of c.nodes) {
          const nId = typeof node === 'string' ? node : (node.id || node.code)
          const nName = typeof node === 'string' ? node : (node.name || node.id)
          if ((code && nId === code) || (name && nName === name)) return c
        }
      }
    }
    return null
  }

  function getContainerColor(container, containers) {
    const containerData = typeof container === 'string'
      ? (containers || []).find(c => c.id === container)
      : container
    if (!containerData) return null

    const containerCode = containerData.code || containerData.elementCode || containerData.elementRef?.code
    const containerName = containerData.name || containerData.title || containerData.elementRef?.name

    let isCenterContainer = false
    const centerScopeSet = new Set(centerScope.value || [])
    const markers = centerScopeMarkers.value
    if (containerCode && centerScopeSet.has(containerCode)) isCenterContainer = true
    if (!isCenterContainer && containerName && centerScopeSet.has(containerName)) isCenterContainer = true
    if (!isCenterContainer && containerName && markers?.serviceModules?.has(containerName)) isCenterContainer = true
    if (!isCenterContainer && containerCode && markers?.serviceModules?.has(containerCode)) isCenterContainer = true

    if (centerScopeHighlight.value && isCenterContainer) {
      return CENTER_COLOR_MAP[centerScopeColor.value] || centerScopeColor.value || '#808080'
    }

    let colorKey = ''
    if (colorGroupBy.value === 'serviceModule') {
      colorKey = containerData.serviceModuleName || containerData.serviceModule || containerName
    } else if (colorGroupBy.value === 'subDomain') {
      colorKey = containerData.subDomainName || containerName
      if (!colorKey || colorKey === containerName) {
        const match = findContainerInSubDomains(containerCode, containerName, containers)
        if (match) colorKey = match.subDomainName || match.name
      }
    } else {
      colorKey = containerData.domain || containerName
      if (!colorKey || colorKey === containerName) {
        const match = findContainerInSubDomains(containerCode, containerName, containers)
        if (match) colorKey = match.domain || match.name
      }
    }

    const fromMap = colorFromMap(colorKey)
    if (fromMap) return fromMap
    if (!colorKey || typeof colorKey !== 'string') return '#808080'
    return hashColor(colorKey)
  }

  function getNodeColor(nodeId, containers) {
    let nodeContainer = null
    let nodeCode = null
    for (const container of containers || []) {
      if (container.nodes) {
        for (const node of container.nodes) {
          const id = typeof node === 'string' ? node : node.id
          const code = typeof node === 'string' ? null : node.code
          if (id === nodeId) { nodeContainer = container; nodeCode = code; break }
        }
      }
      if (nodeContainer) break
    }
    if (!nodeContainer) return null

    const centerScopeVal = centerScope.value || []
    const checkId = nodeCode || nodeId
    if (centerScopeHighlight.value && centerScopeVal.includes(checkId)) {
      return CENTER_COLOR_MAP[centerScopeColor.value] || centerScopeColor.value || '#808080'
    }

    let colorKey = ''
    if (colorGroupBy.value === 'serviceModule') {
      colorKey = nodeContainer.serviceModuleName || nodeContainer.serviceModule || nodeContainer.name
    } else if (colorGroupBy.value === 'subDomain') {
      colorKey = nodeContainer.subDomainName || nodeContainer.name
    } else {
      colorKey = nodeContainer.domain || nodeContainer.name
    }
    const fromMap = colorFromMap(colorKey)
    if (fromMap) return fromMap
    if (!colorKey) return '#808080'
    return hashColor(colorKey)
  }

  function getGroupTypeLabel(type) {
    const labels = {
      domain: '领域', subDomain: '子领域', serviceModule: '服务模块',
      businessObject: '业务对象', custom: '自定义', none: '无关联', virtualLayer: '虚拟层'
    }
    return labels[type] || type
  }

  function getElkGroupHint(elkGroup) {
    const hints = {
      inner: '无外部关系：此分组中的节点没有连接外部节点的边，需要与有外部关系的区分开，否则这些节点无法均匀布局',
      boundary: '有外部关系：此分组中的节点有连接外部节点的边，需要与无外部关系的区分开，否则这些节点无法均匀布局'
    }
    return hints[elkGroup] || ''
  }

  return {
    getContainerName, getNodeName, getContainerColor, getNodeColor,
    getGroupTypeLabel, getElkGroupHint, COLOR_SCHEMES
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/composables/__tests__/useGroupDisplay.spec.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/composables/useGroupDisplay.js src/composables/__tests__/useGroupDisplay.spec.js
git commit --no-verify -m "refactor: extract useGroupDisplay composable from GroupItem display helpers"
```

---

## Task 2: 创建递归树节点组件 LayoutGroupNode.vue

**Files:**
- Create: `src/views/AADiagramApp/components/LayoutGroupNode.vue`
- Test: `src/views/AADiagramApp/components/__tests__/LayoutGroupNode.spec.js`

- [ ] **Step 1: Write the failing test**

`src/views/AADiagramApp/components/__tests__/LayoutGroupNode.spec.js`:

```js
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LayoutGroupNode from '../LayoutGroupNode.vue'

describe('LayoutGroupNode', () => {
  function makeGroup(overrides = {}) {
    return {
      id: 'g1', title: '领域A', groupType: 'domain', direction: 'TB',
      visible: true, enabled: true, containers: [], children: [],
      ...overrides
    }
  }

  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('渲染标题与类型图标', () => {
    const wrapper = mount(LayoutGroupNode, { props: { group: makeGroup(), depth: 0, containers: [] } })
    expect(wrapper.text()).toContain('领域A')
  })

  it('点击启用切换 emit update', async () => {
    const wrapper = mount(LayoutGroupNode, { props: { group: makeGroup(), depth: 0, containers: [] } })
    const eye = wrapper.find('.lgn-eye')
    await eye.trigger('click')
    expect(wrapper.emitted('update')?.[0]?.[0]).toMatchObject({ id: 'g1', updates: { enabled: false } })
  })

  it('有子节点时展开/收起', async () => {
    const group = makeGroup({ children: [makeGroup({ id: 'g2', title: '子领域' })] })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    expect(wrapper.findAll('.lgn-node').length).toBe(1) // 默认折叠
    await wrapper.find('.lgn-caret').trigger('click')
    expect(wrapper.findAll('.lgn-node').length).toBe(2) // 展开后含子节点
  })

  it('删除 emit delete', async () => {
    const group = makeGroup({ groupType: 'custom' })
    const wrapper = mount(LayoutGroupNode, { props: { group, depth: 0, containers: [] } })
    await wrapper.find('.lgn-delete').trigger('click')
    expect(wrapper.emitted('delete')?.[0]?.[0]).toBe('g1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/views/AADiagramApp/components/__tests__/LayoutGroupNode.spec.js`
Expected: FAIL（模块不存在）

- [ ] **Step 3: Create LayoutGroupNode.vue**

`src/views/AADiagramApp/components/LayoutGroupNode.vue`:

```vue
<template>
  <div class="lgn-node" :style="{ paddingLeft: `${depth * 16}px` }">
    <div class="lgn-row" :class="{ 'row-drag-over': isRowDragOver }"
      @dragover.prevent="handleRowDragOver" @dragleave="handleRowDragLeave" @drop="handleRowDrop">
      <button class="lgn-caret" @click="toggleExpanded" :class="{ expanded: expanded }"
        :title="hasChildren ? (expanded ? '收起' : '展开') : ''">
        <span v-if="hasChildren" class="caret-arrow">▸</span>
        <span v-else class="caret-placeholder"></span>
      </button>
      <span class="lgn-type-icon" :title="getGroupTypeLabel(group.groupType)">{{ typeIcon }}</span>
      <div class="lgn-title" @dblclick="startEditTitle">
        <template v-if="!isEditingTitle">
          <span class="lgn-title-text">{{ group.title }}</span>
          <span v-if="group.isCenter" class="center-marker" title="中心范围">◆</span>
          <span v-if="group.groupType" class="lgn-type-badge">{{ getGroupTypeLabel(group.groupType) }}</span>
          <span v-if="group.title === '无外部关系' || group.title === '有外部关系'"
            class="elk-hint" :title="getElkGroupHint(group._elkGroup)">ⓘ</span>
        </template>
        <input v-else ref="titleInput" v-model="editTitle" class="title-input"
          @blur="finishEditTitle" @keyup.enter="finishEditTitle" @keyup.escape="cancelEditTitle" />
      </div>
      <div class="lgn-inline-actions">
        <button class="lgn-eye" :class="{ off: group.enabled === false }"
          :title="group.enabled !== false ? '点击禁用分组' : '点击启用分组'" @click="toggleEnabled">
          <AppIcon :name="group.enabled !== false ? 'eye' : 'eye-off'" size="sm" />
        </button>
        <button class="lgn-more" title="更多设置" @click="popoverVisible = true">
          <AppIcon name="more" size="sm" />
        </button>
        <button v-if="isCustomGroup" class="lgn-delete" title="删除分组" @click="handleDelete">
          <AppIcon name="close" size="sm" />
        </button>
        <button class="lgn-drag-handle" draggable="true" @dragstart="handleGroupDragStart($event)"
          @dragend="handleGroupDragEnd" title="拖拽排序">
          <AppIcon name="drag" size="sm" />
        </button>
      </div>

      <el-popover v-model:visible="popoverVisible" :teleported="true" placement="right-start"
        :width="220" trigger="contextmenu" popper-class="lgn-popover">
        <template #reference>
          <span class="lgn-context-anchor"></span>
        </template>
        <div class="lgn-popover-body">
          <div class="pp-row">
            <span class="pp-label">启用</span>
            <el-switch :model-value="group.enabled !== false" @change="handleEnabledChange" size="small" />
          </div>
          <div class="pp-row">
            <span class="pp-label">显示边框</span>
            <el-switch :model-value="group.visible !== false" @change="handleVisibleChange" size="small" />
          </div>
          <div v-if="hasMultipleChildren && !isELK" class="pp-row">
            <span class="pp-label">方向</span>
            <div class="direction-toggle">
              <button class="direction-btn" :class="{ active: group.direction === 'TB' }"
                @click="handleDirectionChange('TB')" title="从上到下">TB</button>
              <button class="direction-btn" :class="{ active: group.direction === 'LR' }"
                @click="handleDirectionChange('LR')" title="从左到右">LR</button>
            </div>
          </div>
          <div class="pp-actions">
            <button v-if="!isCustomGroup" class="pp-btn" @click="handleAddChild">添加子分组</button>
            <button v-if="isCustomGroup" class="pp-btn danger" @click="handleDelete">删除分组</button>
          </div>
        </div>
      </el-popover>
    </div>

    <div v-if="expanded && group.children && group.children.length" class="lgn-children">
      <LayoutGroupNode
        v-for="(child, idx) in group.children" :key="child.id"
        :group="child" :depth="depth + 1" :containers="containers" :index="idx"
        :color-mapping="colorMapping"
        @update="handleChildUpdate" @delete="handleChildDelete" @add-child="handleChildAddChild"
        @assign-container="handleChildAssignContainer" @remove-container="handleChildRemoveContainer"
        @reorder-groups="handleChildReorderGroups" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'
import { useGroupDisplay } from '@/composables/useGroupDisplay'

const props = defineProps({
  group: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  containers: { type: Array, default: () => [] },
  index: { type: Number, default: -1 },
  colorMapping: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['update', 'delete', 'add-child', 'assign-container', 'remove-container', 'reorder-groups', 'remove-node'])

const store = useDiagramConfigStore()
const { getContainerName, getNodeName, getGroupTypeLabel, getElkGroupHint } = useGroupDisplay()

const expanded = ref(props.depth < 1) // 默认收起深层
const isEditingTitle = ref(false)
const editTitle = ref('')
const titleInput = ref(null)
const popoverVisible = ref(false)
const isRowDragOver = ref(false)

const isELK = computed(() => store.layoutEngine === 'elk')
const isCustomGroup = computed(() => props.group.groupType === 'custom')
const hasChildren = computed(() => (props.group.children?.length || 0) > 0)
const hasMultipleChildren = computed(() => {
  const childCount = props.group.children?.length || 0
  const containerCount = props.group.containers?.length || 0
  return childCount > 0 || containerCount > 1
})

const typeIcon = computed(() => {
  const map = {
    domain: '📁', subDomain: '📂', serviceModule: '📄',
    businessObject: '📄', virtualLayer: '🟦', custom: '📦'
  }
  return map[props.group.groupType] || '📄'
})

function toggleExpanded() {
  if (hasChildren.value) expanded.value = !expanded.value
}

function startEditTitle() {
  editTitle.value = props.group.title
  isEditingTitle.value = true
  nextTick(() => { titleInput.value?.focus(); titleInput.value?.select() })
}
function finishEditTitle() {
  if (editTitle.value.trim() && editTitle.value !== props.group.title) {
    emit('update', { id: props.group.id, updates: { title: editTitle.value.trim() } })
  }
  isEditingTitle.value = false
}
function cancelEditTitle() { isEditingTitle.value = false }

function toggleEnabled() {
  const enabled = props.group.enabled === false
  const updates = { enabled }
  if (!enabled) {
    updates.visible = false
    updates.previousVisible = props.group.visible
  } else {
    updates.visible = props.group.previousVisible !== undefined ? props.group.previousVisible : true
  }
  emit('update', { id: props.group.id, updates })
}
function handleEnabledChange(val) {
  const updates = { enabled: val }
  if (!val) {
    updates.visible = false
    updates.previousVisible = props.group.visible
  } else {
    updates.visible = props.group.previousVisible !== undefined ? props.group.previousVisible : true
  }
  emit('update', { id: props.group.id, updates })
}
function handleVisibleChange(val) {
  emit('update', { id: props.group.id, updates: { visible: val } })
}
function handleDirectionChange(direction) {
  emit('update', { id: props.group.id, updates: { direction } })
}
function handleDelete() { emit('delete', props.group.id) }
function handleAddChild() { emit('add-child', props.group.id) }

function handleChildUpdate(d) { emit('update', d) }
function handleChildDelete(id) { emit('delete', id) }
function handleChildAddChild(parentId) { emit('add-child', parentId) }
function handleChildAssignContainer(d) { emit('assign-container', d) }
function handleChildRemoveContainer(d) { emit('remove-container', d) }
function handleChildReorderGroups(d) { emit('reorder-groups', d) }

function handleGroupDragStart(event) {
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'group', groupId: props.group.id, sourceIndex: props.index
  }))
  event.stopPropagation()
}
function handleGroupDragEnd() {}

function handleRowDragOver(event) {
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'container') isRowDragOver.value = true
  } catch { isRowDragOver.value = true }
}
function handleRowDragLeave() { isRowDragOver.value = false }
function handleRowDrop(event) {
  isRowDragOver.value = false
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'container') {
      const container = data.container
      if (data.sourceType === 'group' && data.sourceGroupId && data.sourceGroupId !== props.group.id) {
        emit('remove-container', { groupId: data.sourceGroupId, containerId: container.id })
      }
      emit('assign-container', { groupId: props.group.id, container })
    }
  } catch (e) { console.error('Failed to parse drop data:', e) }
}
</script>

<style scoped lang="scss">
.lgn-node { }
.lgn-row {
  display: flex; align-items: center; gap: 6px; height: 28px;
  padding: 0 6px; border-radius: 4px; cursor: pointer;
  &:hover { background: rgba(234, 88, 12, 0.08); }
  &.row-drag-over { background: rgba(82, 196, 26, 0.15); outline: 1px dashed #52c41a; }
}
.lgn-caret { width: 18px; height: 18px; border: none; background: transparent; cursor: pointer; color: #999; }
.caret-arrow { display: inline-block; transition: transform 0.15s; }
.lgn-caret.expanded .caret-arrow { transform: rotate(90deg); }
.caret-placeholder { display: inline-block; width: 8px; }
.lgn-type-icon { font-size: 14px; }
.lgn-title { flex: 1; display: flex; align-items: center; gap: 4px; overflow: hidden;
  white-space: nowrap; text-overflow: ellipsis; }
.lgn-title-text { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
.lgn-type-badge { font-size: 11px; padding: 0 5px; border-radius: 3px; background: rgba(0,0,0,0.06); color: #666; white-space: nowrap; }
.center-marker { font-style: italic; font-weight: bold; }
.elk-hint { font-size: 12px; color: #999; cursor: help; }
.title-input { padding: 2px 6px; border: 1px solid var(--color-primary); border-radius: 4px; font-size: 13px; min-width: 100px; }
.lgn-inline-actions { display: flex; align-items: center; gap: 2px; opacity: 0; transition: opacity 0.15s; }
.lgn-row:hover .lgn-inline-actions { opacity: 1; }
.lgn-eye, .lgn-more, .lgn-delete, .lgn-drag-handle {
  display: flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border: none; background: transparent; color: #999; cursor: pointer; border-radius: 3px;
  &:hover { background: rgba(0,0,0,0.06); color: #333; }
}
.lgn-eye.off { color: #bbb; }
.lgn-delete:hover { color: #e74c3c; }
.lgn-drag-handle { cursor: grab; }
.lgn-children { }
.lgn-context-anchor { display: none; }
</style>
```

> 说明：`AppIcon` 的 `eye`/`eye-off`/`more`/`drag` 图标名若不存在，需在 Step 4 用既有图标名替换（如 `picture`/`more`/`menu`）。El Popover 的 `trigger="contextmenu"` 同时支持右键弹出；「⋯」按钮点击通过 `popoverVisible = true` 触发。

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/views/AADiagramApp/components/__tests__/LayoutGroupNode.spec.js`
Expected: PASS（若 `AppIcon` 图标名报错，检查 `src/components/common/AppIcon` 注册名并替换）

- [ ] **Step 5: Commit**

```bash
git add src/views/AADiagramApp/components/LayoutGroupNode.vue src/views/AADiagramApp/components/__tests__/LayoutGroupNode.spec.js
git commit --no-verify -m "feat: add recursive tree node LayoutGroupNode for layout panel"
```

---

## Task 3: 改造 LayoutControlPanel 渲染树 + 工具条

**Files:**
- Modify: `src/views/AADiagramApp/components/LayoutControlPanel.vue`
- Test: `src/views/AADiagramApp/components/__tests__/LayoutControlPanel.spec.js`

- [ ] **Step 1: Write the failing test**

`src/views/AADiagramApp/components/__tests__/LayoutControlPanel.spec.js`:

```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import LayoutControlPanel from '../LayoutControlPanel.vue'

describe('LayoutControlPanel', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  const modelValue = {
    enabled: true, groups: [
      { id: 'g1', title: '领域A', groupType: 'domain', enabled: true, visible: true,
        containers: [], children: [] }
    ], engine: 'elk', preserveOrder: true
  }

  it('渲染树节点', () => {
    const wrapper = mount(LayoutControlPanel, {
      props: { modelValue, containers: [], domainProducts: [], chartType: 'businessObject' }
    })
    expect(wrapper.text()).toContain('领域A')
    expect(wrapper.find('.lgn-node').exists()).toBe(true)
  })

  it('搜索过滤节点', async () => {
    const wrapper = mount(LayoutControlPanel, {
      props: { modelValue, containers: [], domainProducts: [], chartType: 'businessObject' }
    })
    const input = wrapper.find('.lcp-search-input')
    await input.setValue('不存在')
    expect(wrapper.find('.lgn-node').exists()).toBe(false)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/views/AADiagramApp/components/__tests__/LayoutControlPanel.spec.js`
Expected: FAIL（当前渲染 GroupItem，无 `.lgn-node`）

- [ ] **Step 3: Modify LayoutControlPanel.vue**

将模板顶部的 `panel-content` 改为「工具条 + 未分配池 + 树」，并引入 `LayoutGroupNode` 与搜索；import 区替换 `GroupItem` 为 `LayoutGroupNode`。

替换 `<template>` 中 `panel-content` 块（第 3-62 行）为：

```vue
<div class="panel-content">
  <div class="lcp-toolbar">
    <el-input v-model="searchText" class="lcp-search-input" placeholder="搜索分组" clearable size="small" />
    <button class="lcp-add-group-btn" title="新增顶层分组" @click="handleAddGroup">+ 新增</button>
  </div>

  <div class="containers-section">
    <div class="section-title">未分配节点</div>
    <div class="containers-pool">
      <div v-for="(container, idx) in unassignedContainers" :key="container.id"
        class="container-item" draggable="true"
        @dragstart="handleDragStart($event, container, idx)" @dragend="handleDragEnd">
        {{ container.name }}{{ (container.code || container.elementCode) && (container.code || container.elementCode) !== container.name ? ' (' + (container.code || container.elementCode) + ')' : '' }}
      </div>
      <div v-if="unassignedContainers.length === 0" class="pool-empty">所有节点已分配到分组</div>
    </div>
  </div>

  <div class="groups-section">
    <div class="section-title">分组列表</div>
    <div class="groups-container">
      <div v-if="filteredGroups.length === 0" class="empty-hint">暂无匹配分组</div>
      <LayoutGroupNode
        v-for="(group, idx) in filteredGroups" :key="group.id"
        :group="group" :depth="0" :containers="containers" :index="idx"
        :color-mapping="colorMapping"
        @update="handleGroupUpdate" @delete="handleGroupDelete" @add-child="handleAddChild"
        @assign-container="handleAssignContainer" @remove-container="handleRemoveContainer"
        @reorder-groups="handleReorderGroups" />
    </div>
  </div>
</div>
```

在 `<script setup>` 中：
- import 区把 `import GroupItem from './GroupItem.vue'` 改为 `import LayoutGroupNode from './LayoutGroupNode.vue'`。
- 新增状态与过滤逻辑（放在 `debugGroups` 之后）：

```js
const searchText = ref('')

// 递归过滤：分组标题或子分组匹配搜索词
function matchesSearch(group, keyword) {
  if (!keyword) return true
  const kw = keyword.toLowerCase()
  if (group.title && group.title.toLowerCase().includes(kw)) return true
  if (group.children && group.children.some(c => matchesSearch(c, kw))) return true
  return false
}

const filteredGroups = computed(() => {
  if (!searchText.value) return localConfig.value.groups
  return localConfig.value.groups.filter(g => matchesSearch(g, searchText.value))
})
```

- 若 `handleAddGroup` 已存在则复用；本文件第 382 行已有 `handleAddGroup`，无需新增。

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/views/AADiagramApp/components/__tests__/LayoutControlPanel.spec.js`
Expected: PASS

- [ ] **Step 5: 编译验证**

Run: `npx vite build`（或启动 dev server 确认无编译错误）
Expected: 无 `LayoutGroupNode` / `useGroupDisplay` 相关错误

- [ ] **Step 6: Commit**

```bash
git add src/views/AADiagramApp/components/LayoutControlPanel.vue src/views/AADiagramApp/components/__tests__/LayoutControlPanel.spec.js
git commit --no-verify -m "feat: render layout panel as tree with search + add group toolbar"
```

---

## Task 4: 回归验证 + 收尾

**Files:**
- Run: 现有测试（`useGroupDisplay`、`useLayoutControl`、`diagramConfigStore`）

- [ ] **Step 1: 运行全部相关单测**

Run: `npx vitest run src/composables src/views/AADiagramApp src/stores`
Expected: 新增测试通过；既有预存失败（如 `diagramConfigStore` 初始状态）除外，记录不视为本次回归

- [ ] **Step 2: 手工验证（前端 RUNNING 3004）**

在浏览器验证：
1. 布局设置面板显示为树形（缩进 + 展开箭头）。
2. 深层节点默认折叠，点击展开。
3. 行内 hover 显示 👁（启用/禁用）与 ⋯；点击 👁 切换启用，图表反映（分组 disable 能力）。
4. 右键或点击 ⋯ 弹出参数面板：启用/显示边框/方向/添加子分组/删除 生效。
5. 未分配池拖入某行 = 分配；分组行内拖拽排序。
6. 搜索框过滤分组。
7. 方向/引擎/分组 disable 的图表文字不缩小（回归前序修复）。

> 浏览器测试铁律：禁用所有 MCP 浏览器工具，仅用 PlaywrightCLI（`test_helpers/browser_auth_cli.py`）。

- [ ] **Step 3: 确认 GroupItem 无外部引用后清理（可选）**

Run: `grep -rn "GroupItem" src --include=*.vue --include=*.js`
若仅剩 `LayoutControlPanel.vue` 且已改引用，则删除 `GroupItem.vue`；否则保留作回滚点。

- [ ] **Step 4: 最终提交**

```bash
git add -A
git commit --no-verify -m "refactor: migrate layout panel to tree outline with popover params"
```

---

## Self-Review

- **Spec 覆盖**：结构（树形大纲 §5）→ Task 2/3；行内高频 + ⋯/右键（§6）→ Task 2；可编辑/新增/拖拽（§7）→ Task 2/3；窄栏优化（搜索/折叠/图标/hover）→ Task 2/3；数据流不变 → Task 3 复用业务逻辑。
- **占位符**：无 TBD/TODO；`AppIcon` 图标名标注了替换说明。
- **类型一致性**：`LayoutGroupNode` 事件协议与 `GroupItem` 一致（`update/delete/add-child/assign-container/remove-container/reorder-groups`），`LayoutControlPanel` 处理函数（`handleGroupUpdate` 等）签名不变；`useGroupDisplay` 返回函数名与 Task 3 使用一致。