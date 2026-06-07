<template>
  <div 
    class="group-item" 
    :style="{ marginLeft: `${depth * 16}px` }"
    :class="{ 'group-dragging': isGroupDragging }"
  >
    <div
      class="group-card"
      :class="{ 'drag-over': isDragOver, 'group-drag-over': isGroupDragOver, 'is-virtual-layer': group._isVirtualLayer }"
      @dragover.prevent="handleAllDragOver"
      @dragleave="handleAllDragLeave"
      @drop="handleAllDrop"
    >
      <div class="group-header">
        <div class="group-drag-handle" 
          draggable="true"
          @dragstart="handleGroupDragStart($event)"
          @dragend="handleGroupDragEnd"
          title="拖拽排序"
        >
          <svg viewBox="0 0 24 24" width="12" height="12">
            <path fill="currentColor" d="M11 18c0 1.1-.9 2-2 2s-2-.9-2-2 .9-2 2-2 2 .9 2 2zm-2-8c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm6 4c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/>
          </svg>
        </div>
        <div class="group-title" @dblclick="startEditTitle">
          <template v-if="!isEditingTitle">
            <span v-if="sortOrder" class="sort-order-badge" title="整体排序序号">{{ sortOrder }}</span>
            <span v-if="layerSortOrder" class="layer-sort-order-badge" title="层内排序序号">L{{ layerSortOrder }}</span>
            <span v-if="group.isCenter" class="center-marker" title="中心范围">◆ </span>{{ group.title }}
            <span
              v-if="group.groupType"
              class="group-type-badge"
            >
              {{ getGroupTypeLabel(group.groupType) }}
            </span>
            <span
              v-if="group.title === '无外部关系' || group.title === '有外部关系'"
              class="elk-hint"
              :title="getElkGroupHint(group._elkGroup)"
            >
              ⓘ
            </span>
          </template>
          <input
            v-else
            ref="titleInput"
            v-model="editTitle"
            class="title-input"
            @blur="finishEditTitle"
            @keyup.enter="finishEditTitle"
            @keyup.escape="cancelEditTitle"
          />
        </div>

        <div class="group-actions">
          <template v-if="group.enabled !== false">
            <div class="action-config" v-if="hasMultipleChildren && !isELK">
              <div class="direction-toggle" title="布局方向">
                <button
                  class="direction-btn"
                  :class="{ active: group.direction === 'TB' }"
                  @click="handleDirectionChange('TB')"
                  title="从上到下"
                >
                  <AppIcon name="direction-tb" size="sm" />
                </button>
                <button
                  class="direction-btn"
                  :class="{ active: group.direction === 'LR' }"
                  @click="handleDirectionChange('LR')"
                  title="从左到右"
                >
                  <AppIcon name="direction-lr" size="sm" />
                </button>
              </div>
            </div>
            <div class="action-config" title="显示或隐藏分组边框">
              <label class="mini-toggle">
                <input
                  type="checkbox"
                  :checked="group.visible"
                  @change="handleVisibleChange"
                />
                <span class="mini-toggle-label">{{ group.visible ? '显示边框' : '隐藏边框' }}</span>
              </label>
            </div>
          </template>
          <template v-else>
            <div class="action-config" title="分组已禁用，边框自动隐藏">
              <label class="mini-toggle disabled">
                <input
                  type="checkbox"
                  disabled
                  :checked="false"
                />
                <span class="mini-toggle-label">边框已隐藏</span>
              </label>
            </div>
          </template>
          <div class="action-config" :title="group.enabled !== false ? '点击禁用分组，子元素将提升到父级' : '点击启用分组'">
            <label class="mini-toggle">
              <input
                type="checkbox"
                :checked="group.enabled !== false"
                @change="handleEnabledChange"
              />
              <span class="mini-toggle-label">{{ group.enabled !== false ? '已启用' : '已禁用' }}</span>
            </label>
          </div>
          <button class="action-btn add-child-btn" @click="handleAddChild" title="添加子分组">
            <AppIcon name="plus" size="sm" />
          </button>
          <button v-if="isCustomGroup" class="action-btn delete-btn" @click="handleDelete" title="删除分组">
            <AppIcon name="close" size="sm" />
          </button>
        </div>
      </div>

      <div class="group-config" v-if="group.enabled === false">
        <span class="config-hint">禁用后子元素将提升到父级</span>
      </div>

      <div v-if="group.containers && group.containers.length > 0" class="assigned-containers">
        <div class="containers-list">
          <div
            v-for="(container, idx) in group.containers"
            :key="container.id || idx"
            class="assigned-container-item"
            :class="{ 'dragging': draggingContainerIndex === idx, 'drag-over': dragOverIndex === idx }"
            :style="getItemStyle(getContainerColor(container) || groupColor)"
            draggable="true"
            @dragstart="handleContainerDragStart($event, container, idx)"
            @dragend="handleContainerDragEnd"
            @dragover="handleContainerDragOver($event, idx)"
            @dragleave="handleContainerDragLeave"
            @drop="handleContainerDrop($event, idx)"
          >
            <span class="container-name" :style="getTextStyle(getContainerColor(container) || groupColor)">{{ getContainerName(container) }}</span>
            <button class="remove-container-btn" @click="handleRemoveContainer(container)" title="移除容器">
              <AppIcon name="close" size="xs" />
            </button>
          </div>
        </div>
      </div>

      <div v-if="group.directNodes && group.directNodes.length > 0" class="assigned-nodes">
        <div class="nodes-label">已分配节点 ({{ group.directNodes.length }})：</div>
        <div class="nodes-list">
          <div
            v-for="(nodeId, idx) in group.directNodes"
            :key="nodeId"
            class="assigned-node-item"
            :class="{ 'dragging': draggingNodeIndex === idx }"
            :style="getItemStyle(getNodeColor(nodeId) || groupColor)"
            draggable="true"
            @dragstart="handleNodeDragStart($event, nodeId, idx)"
            @dragend="handleNodeDragEnd"
          >
            <span class="node-name" :style="getTextStyle(getNodeColor(nodeId) || groupColor)">{{ getNodeName(nodeId) }}</span>
            <button class="remove-node-btn" @click="handleRemoveNode(nodeId)" title="移除节点">
              <AppIcon name="close" size="xs" />
            </button>
          </div>
        </div>
      </div>
      <div v-else-if="group.directNodes">
        <div class="nodes-label">已分配节点 (0)：无</div>
      </div>

      <div class="drop-zone-area" :class="{ 'active': isDragOver }">
        <span v-if="isDragOver" class="drop-hint">释放以添加</span>
        <span v-else class="drop-hint-placeholder">拖拽到此处</span>
      </div>

      <div v-if="group.children && group.children.length > 0" class="children-container">
        <GroupItem
          v-for="child in group.children"
          :key="child.id + '-' + (centerScopeColor || 'default')"
          :group="child"
          :depth="depth + 1"
          :containers="containers"
          :color-scheme="colorScheme"
          :color-group-by="colorGroupBy"
          :custom-colors="customColors"
          :color-mapping="colorMapping"
          :center-scope="centerScope"
          :center-scope-markers="centerScopeMarkers"
          :center-scope-color="centerScopeColor"
          @update="handleChildUpdate"
          @delete="handleChildDelete"
          @add-child="handleChildAddChild"
          @assign-container="handleChildAssignContainer"
          @remove-container="handleChildRemoveContainer"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, computed, watch } from 'vue'
import { AppIcon } from '@/components/common/AppIcon'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

const props = defineProps({
  group: {
    type: Object,
    required: true
  },
  depth: {
    type: Number,
    default: 0
  },
  containers: {
    type: Array,
    default: () => []
  },
  index: {
    type: Number,
    default: -1
  },
  colorMapping: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['update', 'delete', 'add-child', 'assign-container', 'remove-container', 'reorder-containers', 'reorder-groups', 'remove-node'])

const diagramConfigStore = useDiagramConfigStore()

const containers = computed(() => props.containers)
const colorMapping = computed(() => props.colorMapping)
const colorScheme = computed(() => diagramConfigStore.colorScheme)
const colorGroupBy = computed(() => diagramConfigStore.colorGroupBy)
const customColors = computed(() => diagramConfigStore.customColors)
const centerScope = computed(() => diagramConfigStore.centerScope)
const centerScopeMarkers = computed(() => diagramConfigStore.centerScopeMarkers)
const centerScopeColor = computed(() => diagramConfigStore.centerScopeColor)
const centerScopeHighlight = computed(() => diagramConfigStore.centerScopeHighlight)
const layoutEngine = computed(() => diagramConfigStore.layoutEngine)
const isELK = computed(() => layoutEngine.value === 'elk')

const COLOR_SCHEMES = {
  default: ['#1890FF', '#52C41A', '#FAAD14', '#722ED1', '#13C2C2', '#EB2F96', '#F5222D', '#FA541C', '#FA8C16', '#A0D911', '#2F54EB', '#531DAB'],
  vibrant: ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B739', '#52B788'],
  pastel: ['#FFB3BA', '#BAFFC9', '#BAE1FF', '#FFFFBA', '#FFDFBA', '#E0BBE4', '#957DAD', '#D291BC', '#FEC8D8', '#FFDFD3', '#AED9E0', '#B8F2E6'],
  warm: ['#E74C3C', '#E67E22', '#F39C12', '#F1C40F', '#D35400', '#C0392B', '#E84393', '#FD79A8', '#FDCB6E', '#E17055', '#D63031', '#74B9FF'],
  cool: ['#3498DB', '#2980B9', '#1ABC9C', '#16A085', '#9B59B6', '#8E44AD', '#00B894', '#00CEC9', '#0984E3', '#6C5CE7', '#A29BFE', '#74B9FF'],
  business: ['#2C3E50', '#34495E', '#7F8C8D', '#1ABC9C', '#16A085', '#27AE60', '#2980B9', '#8E44AD', '#2C3E50', '#E67E22', '#D35400', '#C0392B'],
  nature: ['#27AE60', '#229954', '#1E8449', '#52BE80', '#7DCEA0', '#A9DFBF', '#F4D03F', '#F7DC6F', '#F39C12', '#E67E22', '#D35400', '#A04000']
}

const isEditingTitle = ref(false)
const editTitle = ref('')
const titleInput = ref(null)
const isDragOver = ref(false)
const draggingContainerData = ref(null)
const draggingContainerIndex = ref(-1)

const sortOrder = computed(() => props.group?._sortOrder)
const layerSortOrder = computed(() => props.group?._layerSortOrder)
const dragOverIndex = ref(-1)
const isGroupDragging = ref(false)
const isGroupDragOver = ref(false)
const draggingNodeIndex = ref(-1)

const centerScopeVersion = computed(() => centerScope.value?.length || 0)

// 用于触发 getContainerColor 重新计算的版本号
const centerScopeColorVersion = computed(() => centerScopeColor.value || '#EDEDED')

const groupColor = computed(() => {
  if (props.group.groupType === 'custom') {
    return null
  }

  // 引用 centerScopeVersion 确保响应式
  const _ = centerScopeVersion.value

  let colorKey = ''
  if (colorGroupBy.value === 'subDomain') {
    colorKey = props.group.subDomainName || props.group.title
  } else if (colorGroupBy.value === 'serviceModule') {
    colorKey = props.group.serviceModuleName || props.group.title
  } else {
    colorKey = props.group.domainName || props.group.title
  }

  if (colorMapping.value && colorMapping.value[colorKey]) {
    return colorMapping.value[colorKey]
  }

  if (customColors.value && customColors.value[colorKey]) {
    return customColors.value[colorKey]
  }

  const colors = COLOR_SCHEMES[colorScheme.value] || COLOR_SCHEMES.default
  const colorIndex = Math.abs(colorKey.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % colors.length
  return colors[colorIndex]
})

const hasMultipleChildren = computed(() => {
  const childCount = props.group.children?.length || 0
  const containerCount = props.group.containers?.length || 0
  if (childCount > 0) {
    return true
  }
  if (containerCount > 1) {
    return true
  }
  return false
})

const isCustomGroup = computed(() => {
  return props.group.groupType === 'custom'
})

const isLeafGroup = computed(() => {
  const hasChildren = props.group.children && props.group.children.length > 0
  return !hasChildren
})

function startEditTitle() {
  editTitle.value = props.group.title
  isEditingTitle.value = true
  nextTick(() => {
    titleInput.value?.focus()
    titleInput.value?.select()
  })
}

function finishEditTitle() {
  if (editTitle.value.trim() && editTitle.value !== props.group.title) {
    emit('update', {
      id: props.group.id,
      updates: { title: editTitle.value.trim() }
    })
  }
  isEditingTitle.value = false
}

function cancelEditTitle() {
  isEditingTitle.value = false
}

function handleDirectionChange(direction) {
  emit('update', {
    id: props.group.id,
    updates: { direction }
  })
}

function handleEnabledChange(event) {
  const enabled = event.target.checked
  const updates = { enabled }
  if (!enabled) {
    // 禁用时保存当前边框状态并隐藏边框
    updates.visible = false
    updates.previousVisible = props.group.visible
  } else {
    // 启用时恢复之前的边框状态（如果有保存的话）
    if (props.group.previousVisible !== undefined) {
      updates.visible = props.group.previousVisible
    } else {
      updates.visible = true
    }
  }
  emit('update', {
    id: props.group.id,
    updates
  })
}

function handleVisibleChange(event) {
  emit('update', {
    id: props.group.id,
    updates: { visible: event.target.checked }
  })
}

function handleDelete() {
  emit('delete', props.group.id)
}

function handleAddChild() {
  emit('add-child', props.group.id)
}

function handleChildUpdate(data) {
  emit('update', data)
}

function handleChildDelete(id) {
  emit('delete', id)
}

function handleChildAddChild(parentId) {
  emit('add-child', parentId)
}

function handleChildAssignContainer(data) {
  emit('assign-container', data)
}

function handleChildRemoveContainer(data) {
  emit('remove-container', data)
}

function handleDragOver(event) {
  isDragOver.value = true
}

function handleDragLeave(event) {
  isDragOver.value = false
}

function handleDrop(event) {
  isDragOver.value = false
  
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    
    if (data.type === 'container') {
      const container = data.container
      
      if (data.sourceType === 'group' && data.sourceGroupId === props.group.id) {
        return
      }
      
      if (data.sourceType === 'group' && data.sourceGroupId) {
        emit('remove-container', {
          groupId: data.sourceGroupId,
          containerId: container.id
        })
      }
      
      emit('assign-container', {
        groupId: props.group.id,
        container: container
      })
    }
  } catch (e) {
    console.error('Failed to parse drop data:', e)
  }
}

function handleAllDragOver(event) {
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    if (data.type === 'group') {
      isGroupDragOver.value = true
    } else {
      isDragOver.value = true
    }
  } catch (e) {
    isDragOver.value = true
  }
}

function handleAllDragLeave(event) {
  isDragOver.value = false
  isGroupDragOver.value = false
}

function handleAllDrop(event) {
  isDragOver.value = false
  isGroupDragOver.value = false
  
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    
    if (data.type === 'group') {
      const sourceIdx = data.sourceIndex
      const targetIdx = props.index
      if (sourceIdx !== targetIdx && sourceIdx !== -1 && targetIdx !== -1) {
        emit('reorder-groups', { sourceIndex: sourceIdx, targetIndex: targetIdx })
      }
    } else if (data.type === 'container') {
      const container = data.container
      
      if (data.sourceType === 'group' && data.sourceGroupId === props.group.id) {
        return
      }
      
      if (data.sourceType === 'group' && data.sourceGroupId) {
        emit('remove-container', {
          groupId: data.sourceGroupId,
          containerId: container.id
        })
      }
      
      emit('assign-container', {
        groupId: props.group.id,
        container: container
      })
      
      event.stopPropagation()
    }
  } catch (e) {
    console.error('Failed to parse drop data:', e)
  }
}

function getContainerName(container) {
  if (typeof container === 'object') {
    // 优先使用 name，其次使用 title（服务模块图）
    if (container.name) return container.name
    if (container.title) return container.title
    if (container.elementRef?.name) return container.elementRef.name
  }
  if (typeof container === 'string') {
    const found = containers.value.find(c => c.id === container)
    if (found) {
      return found.name || found.title || container
    }
    return container
  }
  return '未知容器'
}

function getNodeName(nodeId) {
  for (const container of containers.value) {
    if (container.nodes) {
      for (const node of container.nodes) {
        if (typeof node === 'string' && node === nodeId) {
          return nodeId
        }
        if (typeof node === 'object' && node.id === nodeId) {
          return node.name || node.id
        }
      }
    }
  }
  return nodeId
}

function getNodeColor(nodeId) {
  const _ = centerScopeVersion.value
  const __ = centerScopeColorVersion.value

  let nodeContainer = null
  let nodeCode = null
  for (const container of containers.value) {
    if (container.nodes) {
      for (const node of container.nodes) {
        const id = typeof node === 'string' ? node : node.id
        const code = typeof node === 'string' ? null : node.code
        if (id === nodeId) {
          nodeContainer = container
          nodeCode = code
          break
        }
      }
    }
    if (nodeContainer) break
  }

  if (!nodeContainer) {
    return null
  }

  const centerScopeVal = centerScope.value || []
  const checkId = nodeCode || nodeId
  if (centerScopeHighlight.value && centerScopeVal.includes(checkId)) {
    const centerColorMap = {
      'gray': '#808080',
      '#1890FF': '#1890FF',
      '#52C41A': '#52C41A',
      '#FAAD14': '#FAAD14',
      '#722ED1': '#722ED1'
    }
    return centerColorMap[centerScopeColor.value] || centerScopeColor.value || '#808080'
  }

  let colorKey = ''
  if (colorGroupBy.value === 'serviceModule') {
    colorKey = nodeContainer.serviceModuleName || nodeContainer.serviceModule || nodeContainer.name
  } else if (colorGroupBy.value === 'subDomain') {
    colorKey = nodeContainer.subDomainName || nodeContainer.name
  } else {
    colorKey = nodeContainer.domain || nodeContainer.name
  }

  if (colorMapping.value && colorMapping.value[colorKey]) {
    return colorMapping.value[colorKey]
  }

  if (customColors.value && customColors.value[colorKey]) {
    return customColors.value[colorKey]
  }

  if (!colorKey) {
    return '#808080'
  }

  const colors = COLOR_SCHEMES[colorScheme.value] || COLOR_SCHEMES.default
  const colorIndex = Math.abs(colorKey.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % colors.length
  return colors[colorIndex]
}

function findContainerInSubDomains(code, name) {
  if (!containers.value) return null
  for (const c of containers.value) {
    if (c.nodes && Array.isArray(c.nodes)) {
      for (const node of c.nodes) {
        const nId = typeof node === 'string' ? node : (node.id || node.code)
        const nName = typeof node === 'string' ? node : (node.name || node.id)
        if ((code && nId === code) || (name && nName === name)) {
          return c
        }
      }
    }
  }
  return null
}

function getContainerColor(container) {
  const containerData = typeof container === 'string'
    ? containers.value.find(c => c.id === container)
    : container

  if (!containerData) {
    return null
  }

  // 统一获取 code 和 name（支持业务对象图和服务模块图）
  const containerCode = containerData.code || containerData.elementCode || containerData.elementRef?.code
  const containerName = containerData.name || containerData.title || containerData.elementRef?.name

  let isCenterContainer = false
  const centerScopeSet = new Set(centerScope?.value || [])
  const centerScopeMarkersVal = centerScopeMarkers?.value

  // 关键修复：只检查节点本身是否在中心范围，而不是检查节点所在的子领域/领域
  // 1. 检查 containerCode 是否在 centerScope 中
  if (containerCode && centerScopeSet.has(containerCode)) {
    isCenterContainer = true
  }

  // 2. 检查 containerName 是否在 centerScope 中
  if (!isCenterContainer && containerName && centerScopeSet.has(containerName)) {
    isCenterContainer = true
  }

  // 3. 检查 containerName 或 containerCode 是否在 serviceModules 中（服务模块图）
  if (!isCenterContainer && containerName && centerScopeMarkersVal?.serviceModules?.has(containerName)) {
    isCenterContainer = true
  }
  if (!isCenterContainer && containerCode && centerScopeMarkersVal?.serviceModules?.has(containerCode)) {
    isCenterContainer = true
  }

  // 注意：不再检查 domain 和 subDomainName，因为同一个子领域下可能既有中心节点也有非中心节点
  // 只应该根据节点本身是否在中心范围来判断

  if (centerScopeHighlight.value && isCenterContainer) {
    const centerColorMap = {
      'gray': '#808080',
      '#1890FF': '#1890FF',
      '#52C41A': '#52C41A',
      '#FAAD14': '#FAAD14',
      '#722ED1': '#722ED1'
    }
    return centerColorMap[centerScopeColor?.value || centerScopeColor] || (centerScopeColor?.value || centerScopeColor) || '#808080'
  }

  let colorKey = ''
  if (colorGroupBy.value === 'serviceModule') {
    colorKey = containerData.serviceModuleName || containerData.serviceModule || containerName
    if (!colorKey && containerData.nodes && containerData.nodes.length > 0) {
      for (const node of containerData.nodes) {
        const nodeCode = typeof node === 'string' ? node : node.code
        const nodeId = typeof node === 'string' ? node : node.id
        for (const c of containers.value) {
          if (c.nodes) {
            for (const n of c.nodes) {
              const nCode = typeof n === 'string' ? n : n.code
              const nId = typeof n === 'string' ? n : n.id
              if (nCode === nodeCode || nId === nodeId) {
                if (n.serviceModuleName) {
                  colorKey = n.serviceModuleName
                  break
                }
                if (n.serviceModule) {
                  colorKey = n.serviceModule
                  break
                }
              }
            }
          }
          if (colorKey) break
        }
        if (colorKey) break
      }
    }
    if (!colorKey) {
      colorKey = containerName
    }
  } else if (colorGroupBy.value === 'subDomain') {
    colorKey = containerData.subDomainName || containerName
    if (!colorKey || colorKey === containerName) {
      const match = findContainerInSubDomains(containerCode, containerName)
      if (match) colorKey = match.subDomainName || match.name
    }
  } else {
    colorKey = containerData.domain || containerName
    if (!colorKey || colorKey === containerName) {
      const match = findContainerInSubDomains(containerCode, containerName)
      if (match) colorKey = match.domain || match.name
    }
  }

  if (colorMapping.value && colorMapping.value[colorKey]) {
    return colorMapping.value[colorKey]
  }

  if (customColors.value && customColors.value[colorKey]) {
    return customColors.value[colorKey]
  }

  if (!colorKey || typeof colorKey !== 'string') {
    console.warn('[getContainerColor] colorKey is invalid:', colorKey, 'containerData:', containerData)
    return '#808080'
  }

  const colors = COLOR_SCHEMES[colorScheme.value] || COLOR_SCHEMES.default
  const colorIndex = Math.abs(colorKey.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0)) % colors.length
  return colors[colorIndex]
  }

function getItemStyle(color) {
  if (!color) return {}
  return {
    borderColor: color,
    backgroundColor: color + '10'
  }
}

function getTextStyle(color) {
  if (!color) return {}
  return { color: color }
}

function getContainerNodeCount(container) {
  if (typeof container === 'object' && container.nodes) {
    return container.nodes.length
  }
  const containerId = typeof container === 'object' ? container.id : container
  const found = containers.value.find(c => c.id === containerId)
  return found?.nodes?.length || 0
}

function getGroupTypeLabel(type) {
  const labels = {
    domain: '领域',
    subDomain: '子领域',
    serviceModule: '服务模块',
    businessObject: '业务对象',
    custom: '自定义',
    none: '无关联',
    virtualLayer: '虚拟层'
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

function handleContainerDragStart(event, container, idx) {
  draggingContainerData.value = { container, idx }
  draggingContainerIndex.value = idx
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'container',
    container: container,
    sourceType: 'group',
    sourceGroupId: props.group.id,
    sourceIndex: idx
  }))
}

function handleContainerDragEnd() {
  draggingContainerData.value = null
  draggingContainerIndex.value = -1
  dragOverIndex.value = -1
}

function handleContainerDragOver(event, idx) {
  event.preventDefault()
  if (draggingContainerIndex.value !== -1 && draggingContainerIndex.value !== idx) {
    dragOverIndex.value = idx
  }
}

function handleContainerDragLeave() {
  dragOverIndex.value = -1
}

function handleContainerDrop(event, targetIdx) {
  event.preventDefault()
  dragOverIndex.value = -1
  
  try {
    const data = JSON.parse(event.dataTransfer.getData('text/plain'))
    
    if (data.type === 'container' && data.sourceGroupId === props.group.id) {
      const sourceIdx = data.sourceIndex
      if (sourceIdx !== targetIdx) {
        const newContainers = [...props.group.containers]
        const [removed] = newContainers.splice(sourceIdx, 1)
        newContainers.splice(targetIdx, 0, removed)
        emit('update', {
          id: props.group.id,
          updates: { containers: newContainers }
        })
      }
    }
  } catch (e) {
    console.error('Failed to parse drop data:', e)
  }
}

function handleGroupDragStart(event) {
  isGroupDragging.value = true
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'group',
    groupId: props.group.id,
    sourceIndex: props.index
  }))
  event.stopPropagation()
}

function handleGroupDragEnd() {
  isGroupDragging.value = false
}

function handleRemoveContainer(container) {
  const containerId = typeof container === 'object' ? container.id : container
  emit('remove-container', {
    groupId: props.group.id,
    containerId: containerId
  })
}

function handleNodeDragStart(event, nodeId, idx) {
  draggingNodeIndex.value = idx
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'node',
    nodeId: nodeId,
    sourceGroupId: props.group.id,
    sourceIndex: idx
  }))
}

function handleNodeDragEnd() {
  draggingNodeIndex.value = -1
}

function handleRemoveNode(nodeId) {
  const newNodes = props.group.directNodes.filter(id => id !== nodeId)
  emit('update', {
    id: props.group.id,
    updates: { directNodes: newNodes }
  })
}
</script>

<style scoped lang="scss">
.group-item {
  margin-bottom: var(--spacing-xs);

  &.group-dragging {
    opacity: 0.5;
  }
}

.group-card {
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  transition: all 0.2s;
  margin-bottom: var(--spacing-xs);

  &.drag-over {
    border-color: var(--color-primary);
    border-width: 2px;
    box-shadow: 0 0 8px rgba(234, 88, 12, 0.3);
  }

  &.group-drag-over {
    border-color: #52c41a;
    border-width: 2px;
    box-shadow: 0 0 8px rgba(82, 196, 26, 0.3);
  }

  &.is-virtual-layer {
    background: #f0f9ff;
    border: 1px dashed #0284c7;
  }
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
}

.group-drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  cursor: grab;
  color: var(--color-text-secondary);
  margin-right: var(--spacing-xs);

  &:hover {
    color: var(--color-primary);
  }

  &:active {
    cursor: grabbing;
  }
}

.group-title {
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex: 1;
  justify-content: flex-start;

  &:hover {
    background: rgba(234, 88, 12, 0.1);
  }
}

.group-type-badge {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-weight: 400;
  white-space: nowrap;
  background: rgba(0, 0, 0, 0.06);
  color: #666;
}

.sort-order-badge {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  white-space: nowrap;
  background: rgba(234, 88, 12, 0.15);
  color: var(--color-primary);
  margin-right: 4px;
}

.layer-sort-order-badge {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  white-space: nowrap;
  background: rgba(59, 130, 246, 0.15);
  color: #3b82f6;
  margin-right: 4px;
}

.elk-hint {
  font-size: 12px;
  color: #999;
  cursor: help;
  margin-left: 4px;
  opacity: 0.7;
  transition: opacity 0.2s;

  &:hover {
    opacity: 1;
    color: var(--color-primary);
  }
}

.center-marker {
  font-style: italic;
  font-weight: bold;
  font-size: 14px;
  text-decoration: underline;
}

.title-input {
  padding: 2px 6px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  font-size: inherit;
  font-weight: 500;
  background: white;
  outline: none;
  min-width: 100px;
}

.group-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.action-config {
  display: flex;
  align-items: center;
}

.direction-select-mini {
  padding: 2px 4px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: 12px;
  background: white;
  cursor: pointer;

  &:hover {
    border-color: var(--color-primary);
  }
}

.direction-toggle {
  display: flex;
  gap: 2px;
  background: #f5f5f5;
  border-radius: 4px;
  padding: 2px;
}

.direction-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: #999;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.2s;

  &:hover {
    color: #666;
    background: rgba(0, 0, 0, 0.05);
  }

  &.active {
    background: white;
    color: var(--color-primary);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  }
}

.mini-toggle {
  display: flex;
  align-items: center;
  gap: 2px;
  cursor: pointer;

  input {
    display: none;
  }

  .mini-toggle-label {
    padding: 2px 8px;
    border: 1px solid #d9d9d9;
    border-radius: 4px;
    font-size: 11px;
    background: #fff;
    color: #595959;
    transition: all 0.2s;
    min-width: 36px;
    text-align: center;
  }

  /* 未选中状态（禁用）- 灰色 */
  input:not(:checked) + .mini-toggle-label {
    background: #f5f5f5;
    color: #999;
    border-color: #d9d9d9;
  }

  /* 选中状态（启用）- 普通白色 */
  input:checked + .mini-toggle-label {
    background: #fff;
    color: #333;
    border-color: #999;
  }

  &:hover .mini-toggle-label {
    border-color: #999;
  }

  input:not(:checked):hover + .mini-toggle-label {
    background: #e8e8e8;
    border-color: #999;
  }

  input:checked:hover + .mini-toggle-label {
    background: #fff;
    border-color: #666;
  }



  &.disabled {
    cursor: not-allowed;
    opacity: 0.5;

    .mini-toggle-label {
      background: #f5f5f5;
      color: #bfbfbf;
      border-color: #d9d9d9;
    }

    &:hover .mini-toggle-label {
      border-color: #d9d9d9;
    }
  }
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: white;
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  z-index: 10;

  &:hover {
    background: var(--color-bg-secondary);
    border-color: var(--color-primary);
  }

  svg {
    flex-shrink: 0;
  }
}

.add-child-btn {
  font-size: 16px;
  font-weight: 500;

  .plus-icon {
    line-height: 1;
  }

  &:hover {
    color: var(--color-primary);
    background: rgba(234, 88, 12, 0.1);
  }
}

.delete-btn:hover {
  color: #e74c3c;
}

.group-config {
  padding: var(--spacing-sm) var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.config-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.config-label {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  min-width: 60px;
}

.config-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-style: italic;
  margin-left: var(--spacing-sm);
}

.direction-select {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  background: white;
  color: var(--color-text-primary);
  cursor: pointer;
  outline: none;

  &:focus {
    border-color: var(--color-primary);
  }
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  cursor: pointer;

  input {
    opacity: 0;
    width: 0;
    height: 0;

    &:checked + .toggle-slider {
      background-color: var(--color-primary);

      &::before {
        transform: translateX(16px);
      }
    }
  }

  .toggle-slider {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: var(--color-border);
    border-radius: 10px;
    transition: 0.2s;

    &::before {
      position: absolute;
      content: "";
      height: 16px;
      width: 16px;
      left: 2px;
      bottom: 2px;
      background-color: white;
      border-radius: 50%;
      transition: 0.2s;
    }
  }
}

.assigned-containers {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-top: 1px solid var(--color-border);
}

.containers-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
}

.containers-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.assigned-container-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 4px 12px;
  background: rgba(234, 88, 12, 0.1);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: grab;
  transition: all 0.2s;
  min-height: 28px;

  &:hover {
    background: rgba(234, 88, 12, 0.2);
  }

  &:active {
    cursor: grabbing;
  }

  &.dragging {
    opacity: 0.5;
    border-style: dashed;
  }

  &.drag-over {
    border-color: #52c41a;
    background: rgba(82, 196, 26, 0.1);
    border-style: dashed;
  }
}

.assigned-container-item .container-name {
  color: var(--color-primary);
  font-weight: 500;
}

.container-direction-select {
  padding: 1px 4px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-xs);
  background: white;
  cursor: pointer;
  outline: none;

  &:focus {
    border-color: var(--color-primary);
  }
}

.remove-container-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  line-height: 1;

  &:hover {
    color: #e74c3c;
  }
}

.drop-zone-area {
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--color-border);
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;

  &.active {
    background: rgba(234, 88, 12, 0.1);
    border: 2px dashed var(--color-primary);
    margin: var(--spacing-xs) var(--spacing-sm);
    border-radius: var(--radius-sm);
  }
}

.drop-hint {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  font-weight: 500;
}

.drop-hint-placeholder {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-style: italic;
}

.children-container {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-top: 1px solid var(--color-border);
}

.assigned-nodes {
  padding: var(--spacing-xs) var(--spacing-sm);
  border-top: 1px solid var(--color-border);
}

.nodes-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-xs);
}

.nodes-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.assigned-node-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: 4px 12px;
  background: rgba(82, 196, 26, 0.1);
  border: 1px solid #52c41a;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  cursor: grab;
  transition: all 0.2s;
  min-height: 28px;

  &:hover {
    background: rgba(82, 196, 26, 0.2);
  }

  &:active {
    cursor: grabbing;
  }

  &.dragging {
    opacity: 0.5;
    border-style: dashed;
  }
}

.assigned-node-item .node-name {
  color: #52c41a;
  font-weight: 500;
}

.remove-node-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  line-height: 1;

  &:hover {
    color: #e74c3c;
  }
}
</style>
