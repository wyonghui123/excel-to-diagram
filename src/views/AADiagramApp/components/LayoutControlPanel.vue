<template>
  <div class="layout-control-panel">
    <div class="panel-content">
      <div class="containers-section">
        <div class="section-title">未分配节点</div>
        <div class="containers-pool">
          <div
            v-for="(container, idx) in unassignedContainers"
            :key="container.id"
            class="container-item"
            draggable="true"
            @dragstart="handleDragStart($event, container, idx)"
            @dragend="handleDragEnd"
          >
            {{ container.name }}
          </div>
          <div v-if="unassignedContainers.length === 0" class="pool-empty">
            所有节点已分配到分组
          </div>
        </div>
      </div>

      <div class="groups-section">
        <div class="section-title">
          分组列表
        </div>
        <div class="groups-container">
          <div v-if="localConfig.groups.length === 0" class="empty-hint">
            暂无分组，点击上方"新增分组"按钮添加
          </div>
          <div v-else class="debug-info">分组数量: {{ debugGroups.length }}</div>

          <GroupItem
            v-for="(group, idx) in localConfig.groups"
            :key="group.id + '-' + (diagramConfigStore.centerScopeColor || 'default')"
            :group="group"
            :depth="0"
            :containers="containers"
            :index="idx"
            :color-scheme="diagramConfigStore.colorScheme"
            :color-group-by="diagramConfigStore.colorGroupBy"
            :custom-colors="diagramConfigStore.customColors"
            :color-mapping="colorMapping"
            :center-scope="resolvedCenterScope"
            :center-scope-version="diagramConfigStore.centerScope.length"
            :center-scope-markers="diagramConfigStore.centerScopeMarkers"
            :center-scope-color="diagramConfigStore.centerScopeColor"
            @update="handleGroupUpdate"
            @delete="handleGroupDelete"
            @add-child="handleAddChild"
            @assign-container="handleAssignContainer"
            @remove-container="handleRemoveContainer"
            @reorder-groups="handleReorderGroups"
          />
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted } from 'vue'
import GroupItem from './GroupItem.vue'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'
import { createGroupId, GroupType } from '@/services/groupModel/types.js'

const props = defineProps({
  containers: {
    type: Array,
    default: () => []
  },
  domainProducts: {
    type: Array,
    default: () => []
  },
  chartType: {
    type: String,
    default: 'businessObject'
  },
  chartTypeChanged: {
    type: Boolean,
    default: false
  },
  modelValue: {
    type: Object,
    default: () => ({
      enabled: false,
      groups: [],
      engine: 'elk',
      preserveOrder: true
    })
  },
  customColors: {
    type: Object,
    default: () => ({})
  },
  colorMapping: {
    type: Object,
    default: () => ({})
  },
  links: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'reset-chart-type-changed'])

const diagramConfigStore = useDiagramConfigStore()

watch(() => diagramConfigStore.colorGroupBy, (newVal, oldVal) => {
  if (newVal !== oldVal && props.domainProducts && props.domainProducts.length > 0) {
    handleAutoGroupByDomain()
  }
})

watch(() => diagramConfigStore.centerScopeHighlight, (newVal, oldVal) => {
  if (newVal !== oldVal && props.domainProducts && props.domainProducts.length > 0) {
    handleAutoGroupByDomain()
  }
})

watch(() => diagramConfigStore.colorScheme, (newVal, oldVal) => {
  if (newVal !== oldVal && props.domainProducts && props.domainProducts.length > 0) {
    handleAutoGroupByDomain()
  }
})

defineExpose({
  handleAutoGroupByDomain,
  handleAutoVirtualLayering,
  handleOverallSort,
  handleInLayerSort,
  optimizeGroupEnabledState
})

const localConfig = ref({
  enabled: true,
  groups: [],
  engine: 'elk',
  preserveOrder: true,
  overallDirection: 'TB'
})

const draggingContainer = ref(null)
const draggingIndex = ref(-1)
const lastProcessedChartType = ref(null)

// 追踪 groups 变化的调试 computed
const debugGroups = computed(() => {
  return localConfig.value.groups
})

// 确保 centerScope 能够正确响应 props 变化
const resolvedCenterScope = computed(() => {
  return diagramConfigStore.centerScope || []
})

watch(() => diagramConfigStore.centerScope, (newVal) => {
})

watch(() => props.modelValue, (newVal, oldVal) => {
  if (newVal) {
    const newValStr = JSON.stringify(newVal)
    const oldValStr = oldVal ? JSON.stringify(oldVal) : ''
    if (newValStr !== oldValStr) {
      localConfig.value = JSON.parse(JSON.stringify(newVal))
    }
  }
}, { immediate: true, deep: true })

watch(() => props.chartType, (newType, oldType) => {
  // 当 chartType 变化时触发自动分组（图表类型变更时强制重新分组）
  // 注意：oldType 为 undefined 表示是初始挂载，不是真正的图表类型变化
  if (oldType !== undefined && newType !== oldType && props.domainProducts && props.domainProducts.length > 0) {
    lastProcessedChartType.value = newType
    handleAutoGroupByDomain()
  }
})

onMounted(() => {
  setTimeout(() => {
    const currentChartType = props.chartType
    
    // 判断是否需要自动分组：
    // 1. 如果图表类型刚刚变化（chartTypeChanged=true），强制触发自动分组
    // 2. 如果分组为空且图表类型没有变化，也触发自动分组（首次进入）
    const shouldAutoGroup = props.chartTypeChanged || (!localConfig.value.groups || localConfig.value.groups.length === 0)
    
    // 统一自动分组触发逻辑：
    // - 业务对象图：需要 domainProducts 和 containers
    // - 服务模块图：需要 domainProducts（containers 用于过滤，但 domainProducts 是必需的）
    const hasRequiredData = props.domainProducts && props.domainProducts.length > 0
    
    // 额外验证：检查现有分组数据是否与当前数据源一致
    // 场景：从预览页返回时，旧分组数据可能与当前 domainProducts 不匹配
    let needReGroup = false
    if (!shouldAutoGroup && hasRequiredData && localConfig.value.groups && localConfig.value.groups.length > 0) {
      if (currentChartType === 'serviceModule') {
        // 服务模块图：验证三层结构完整性（领域→子领域→服务模块）
        const totalSmInSource = countServiceModulesInDomainProducts(props.domainProducts)
        const totalSmInGroups = countServiceModulesInGroups(localConfig.value.groups)
        const unassignedCount = unassignedContainers.value?.length || 0
        
        // 如果有未分配节点，或分组中的服务模块数量与源数据不一致，需要重新分组
        if (unassignedCount > 0 || totalSmInGroups !== totalSmInSource) {
          needReGroup = true
        }
      } else {
        // 业务对象图：检查未分配节点
        const unassignedCount = unassignedContainers.value?.length || 0
        if (unassignedCount > 0) {
          needReGroup = true
        }
      }
    }
    
    if ((shouldAutoGroup || needReGroup) && hasRequiredData) {
      const reason = props.chartTypeChanged ? 'chartTypeChanged' : 
                     (!localConfig.value.groups?.length ? 'empty groups' : 'data mismatch re-group')
      lastProcessedChartType.value = currentChartType
      handleAutoGroupByDomain()
      emit('reset-chart-type-changed')
    }
  }, 100)
})

function countServiceModulesInDomainProducts(domainProducts) {
  let count = 0
  domainProducts?.forEach(domain => {
    domain.modules?.forEach(subDomain => {
      count += subDomain.submodules?.length || 0
    })
  })
  return count
}

function countServiceModulesInGroups(groups) {
  let count = 0
  groups.forEach(group => {
    if (group.containers) {
      group.containers.forEach(c => {
        if (c.groupType === 'serviceModule' || c.type === 'serviceModule') {
          count++
        }
      })
    }
    if (group.children) {
      count += countServiceModulesInGroups(group.children)
    }
  })
  return count
}

function getAllAssignedNodeIds(groups) {
  const ids = new Set()
  for (const group of groups) {
    collectGroupNodeIds(group, ids)
  }
  return ids
}

function collectGroupNodeIds(group, ids) {
  if (group.containers && Array.isArray(group.containers)) {
    group.containers.forEach(c => {
      if (typeof c === 'object' && c.id) {
        ids.add(c.id)
        if (c.name) ids.add(c.name)
        if (c.title) ids.add(c.title)
        if (c.elementCode) ids.add(c.elementCode)
        if (c.elementRef?.code) ids.add(c.elementRef.code)
        if (c.elementRef?.name) ids.add(c.elementRef.name)
        if (c.nodes && Array.isArray(c.nodes)) {
          c.nodes.forEach(node => {
            const nodeId = typeof node === 'string' ? node : (node.id || node.code)
            const nodeName = typeof node === 'string' ? node : (node.name || node.id || node.code)
            if (nodeId) ids.add(nodeId)
            if (nodeName) ids.add(nodeName)
          })
        }
      } else if (typeof c === 'string') {
        ids.add(c)
      }
    })
  }
  if (group.directNodes && Array.isArray(group.directNodes)) {
    group.directNodes.forEach(nodeId => {
      ids.add(nodeId)
    })
  }
  if (group.children && group.children.length > 0) {
    group.children.forEach(child => collectGroupNodeIds(child, ids))
  }
}

const unassignedContainers = computed(() => {
  const assignedIds = getAllAssignedNodeIds(localConfig.value.groups)

  const allNodes = []
  
  // 服务模块图：从 domainProducts 中提取服务模块节点
  if (props.chartType === 'serviceModule') {
    props.domainProducts.forEach(domain => {
      domain.modules?.forEach(subDomain => {
        subDomain.submodules?.forEach(sm => {
          const smCode = sm.code || sm.name
          const smName = sm.name || sm.code
          const smId = createGroupId(GroupType.SERVICE_MODULE, smCode)
          allNodes.push({
            id: smId,
            name: smName,
            code: smCode,
            containerName: subDomain.name
          })
        })
      })
    })
  } else {
    // 业务对象图：从 containers 中提取业务对象节点
    props.containers.forEach(container => {
      if (container.nodes) {
        container.nodes.forEach(node => {
          const nodeId = typeof node === 'string' ? node : (node.id || node.code)
          const nodeName = typeof node === 'string' ? node : (node.name || node.id || node.code)
          allNodes.push({
            id: nodeId,
            name: nodeName,
            containerName: container.name
          })
        })
      }
    })
  }

  return allNodes.filter(node => !assignedIds.has(node.id) && !assignedIds.has(node.name) && !assignedIds.has(node.code))
})

function generateGroupId() {
  return `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

function getDefaultGroup(title, parentId) {
  return {
    id: generateGroupId(),
    title,
    groupType: 'custom', // 自定义分组
    direction: 'TB',
    visible: true,
    enabled: true,
    style: {
      fill: '#ffffff',
      stroke: '#666666',
      strokeWidth: 2,
      strokeDasharray: ''
    },
    containers: [],
    children: [],
    parentId
  }
}

function emitUpdate() {
  emit('update:modelValue', JSON.parse(JSON.stringify(localConfig.value)))
}

function toggleEnabled() {
  localConfig.value.enabled = !localConfig.value.enabled
  emitUpdate()
}

function handleAddGroup() {
  const newGroup = getDefaultGroup(`分组 ${localConfig.value.groups.length + 1}`)
  localConfig.value.groups.push(newGroup)
  emitUpdate()
}

function findGroupById(groups, id) {
  for (const group of groups) {
    if (group.id === id) return group
    const found = findGroupById(group.children, id)
    if (found) return found
  }
  return null
}

function updateGroupInTree(groups, id, updates) {
  for (let i = 0; i < groups.length; i++) {
    if (groups[i].id === id) {
      const { id: _, children: __, parentId: ___, ...safeUpdates } = updates
      Object.assign(groups[i], safeUpdates)
      return true
    }
    if (updateGroupInTree(groups[i].children, id, updates)) {
      return true
    }
  }
  return false
}

function deleteGroupFromTree(groups, id) {
  const index = groups.findIndex(g => g.id === id)
  if (index !== -1) {
    groups.splice(index, 1)
    return true
  }
  for (const group of groups) {
    if (deleteGroupFromTree(group.children, id)) {
      return true
    }
  }
  return false
}

function getGroupDepth(groups, id, depth) {
  for (const group of groups) {
    if (group.id === id) return depth
    const found = getGroupDepth(group.children, id, depth + 1)
    if (found !== -1) return found
  }
  return -1
}

function handleGroupUpdate({ id, updates }) {
  updateGroupInTree(localConfig.value.groups, id, updates)
  emitUpdate()
}

function handleGroupDelete(id) {
  deleteGroupFromTree(localConfig.value.groups, id)
  emitUpdate()
}

function handleAddChild(parentId) {
  const parentDepth = getGroupDepth(localConfig.value.groups, parentId, 1)
  if (parentDepth >= 8) {
    console.warn('Cannot create child group: maximum depth of 8 levels reached')
    return
  }

  const parent = findGroupById(localConfig.value.groups, parentId)
  if (parent) {
    const newGroup = getDefaultGroup(`${parent.title}-子分组`, parentId)
    parent.children.unshift(newGroup)
    emitUpdate()
  }
}

function handleDragStart(event, container, idx) {
  draggingContainer.value = container
  draggingIndex.value = idx
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', JSON.stringify({
    type: 'container',
    container: container,
    sourceType: 'unassigned',
    sourceIndex: idx
  }))
}

function handleDragEnd() {
  draggingContainer.value = null
  draggingIndex.value = -1
}

function handleAssignContainer({ groupId, container }) {
  const group = findGroupById(localConfig.value.groups, groupId)
  if (group) {
    if (!group.containers) {
      group.containers = []
    }
    const existingIndex = group.containers.findIndex(c => 
      (typeof c === 'object' && c.id === container.id) || c === container.id
    )
    if (existingIndex === -1) {
      group.containers.push(container)
      emitUpdate()
    }
  }
}

function handleRemoveContainer({ groupId, containerId }) {
  const group = findGroupById(localConfig.value.groups, groupId)
  if (group && group.containers) {
    const idx = group.containers.findIndex(c => 
      (typeof c === 'object' && c.id === containerId) || c === containerId
    )
    if (idx !== -1) {
      group.containers.splice(idx, 1)
      emitUpdate()
    }
  }
}

function handleReorderGroups({ sourceIndex, targetIndex }) {
  if (sourceIndex !== targetIndex) {
    const newGroups = [...localConfig.value.groups]
    const [removed] = newGroups.splice(sourceIndex, 1)
    newGroups.splice(targetIndex, 0, removed)
    localConfig.value.groups = newGroups
    emitUpdate()
  }
}

const autoGroupButtonText = computed(() => {
  return props.chartType === 'serviceModule' ? '基于领域自动分组（领域→子领域）' : '基于领域自动分组（领域→子领域→服务模块）'
})

function handleAutoGroupByDomain() {
  // 服务模块图使用 props.domainProducts，业务对象图使用 props.containers
  if (props.chartType === 'serviceModule') {
    if (!props.domainProducts || props.domainProducts.length === 0) return
    handleServiceModuleAutoGroup()
  } else {
    if (!props.containers || props.containers.length === 0) return
    handleBusinessObjectAutoGroup()
  }
}

function handleServiceModuleAutoGroup() {
  // 使用 props.domainProducts 构建分组，与 buildServiceModuleGroupModel 保持一致
  // 结构：领域 → 子领域 → 服务模块（始终三层，即使只有一个子领域也创建完整结构）
  const groups = []

  if (!props.domainProducts || props.domainProducts.length === 0) {
    return
  }

  props.domainProducts.forEach(domain => {
    const domainName = domain.name || '未分类'
    const domainCode = domain.code || domainName
    const domainId = createGroupId(GroupType.DOMAIN, domainCode)

    // 创建领域分组
    const domainGroup = {
      id: domainId,
      title: domainName,
      elementCode: domainCode,
      groupType: 'domain',
      direction: 'LR',
      visible: true,
      enabled: true,
      style: {
        fill: '#f5f5f5',
        stroke: '#333333',
        strokeWidth: 2,
        strokeDasharray: ''
      },
      containers: [],
      children: [],
      parentId: null
    }

    domain.modules?.forEach(subDomain => {
      const subDomainName = subDomain.name || '未分类'
      const subDomainCode = subDomain.code || subDomainName
      const subDomainId = createGroupId(GroupType.SUB_DOMAIN, subDomainCode)

      // 创建子领域分组
      const subDomainGroup = {
        id: subDomainId,
        title: subDomainName,
        elementCode: subDomainCode,
        groupType: 'subDomain',
        direction: 'TB',
        visible: true,
        enabled: true,
        style: {
          fill: '#ffffff',
          stroke: '#666666',
          strokeWidth: 2,
          strokeDasharray: ''
        },
        containers: [],
        children: [],
        parentId: domainGroup.id
      }

      // 服务模块：作为 containers 节点（与 buildServiceModuleGroupModel 一致）
      // 不添加到 children，children 只用于分层结构
      subDomain.submodules?.forEach(sm => {
        const smCode = sm.code || sm.name
        const smName = sm.name || sm.code
        const smId = createGroupId(GroupType.SERVICE_MODULE, smCode)

        // 作为 containers 节点（用于合并和渲染）
        subDomainGroup.containers.push({
          id: smId,
          type: GroupType.SERVICE_MODULE,
          title: smName,
          elementRef: {
            type: GroupType.SERVICE_MODULE,
            code: smCode,
            name: smName
          },
          parentId: subDomainGroup.id,
          groupType: 'serviceModule',
          direction: 'TB',
          visible: true,
          enabled: true,
          style: {
            fill: '#ffffff',
            stroke: '#666666',
            strokeWidth: 1,
            strokeDasharray: ''
          },
          containers: [],
          children: []
        })
      })
      if (subDomainGroup.containers.length > 0) {
        domainGroup.children.push(subDomainGroup)
      }
    })


    if (domainGroup.children.length > 0) {
      groups.push(domainGroup)
    }
  })


  localConfig.value.groups = groups
  localConfig.value.enabled = true
  emitUpdate()
}

function handleBusinessObjectAutoGroup() {
  // 构建节点编码到名称的映射
  const codeToNameMap = new Map()
  props.containers.forEach(container => {
    if (container.nodes) {
      container.nodes.forEach(node => {
        const nodeCode = typeof node === 'string' ? node : (node.code || node.id)
        const nodeName = typeof node === 'string' ? node : (node.name || node.code || node.id)
        if (nodeCode) {
          codeToNameMap.set(nodeCode, nodeName)
        }
      })
    }
  })

  // 先构建 domainMap 结构（用于后续判断服务模块）
  const domainMap = new Map()

  props.containers.forEach(container => {
    const domainName = container.domain || '未分类'
    const domainCode = container.domainCode || domainName
    const subDomainName = container.name
    const subDomainCode = container.id || subDomainName
    const serviceModuleMap = container.serviceModuleMap || {}

    if (!domainMap.has(domainName)) {
      domainMap.set(domainName, {
        subDomainMap: new Map(),
        domainCode: domainCode
      })
    }
    const subDomainMap = domainMap.get(domainName).subDomainMap

    if (!subDomainMap.has(subDomainName)) {
      subDomainMap.set(subDomainName, {
        smMap: new Map(),
        subDomainCode: subDomainCode
      })
    }
    const smMap = subDomainMap.get(subDomainName).smMap

    Object.entries(serviceModuleMap).forEach(([smName, smData]) => {
      const boNodes = smData.nodes || smData
      const boCodes = Array.isArray(boNodes)
        ? boNodes.map(node => typeof node === 'string' ? node : (node.code || node.id))
        : []
      const smCode = smData.code || smName
      if (!smMap.has(smName)) {
        smMap.set(smName, { boCodes: [], smCode: smCode })
      }
      smMap.get(smName).boCodes.push(...boCodes)
    })

    // 如果没有 serviceModuleMap，直接使用 container.nodes
    if (Object.keys(serviceModuleMap).length === 0 && container.nodes) {
      const allNodeCodes = container.nodes.map(node => typeof node === 'string' ? node : (node.code || node.id))
      if (!smMap.has(subDomainName)) {
        smMap.set(subDomainName, { boCodes: [], smCode: subDomainCode })
      }
      smMap.get(subDomainName).boCodes.push(...allNodeCodes)
    }
  })

  // 构建节点到服务模块的映射（用于判断外部连线）
  const nodeToServiceModuleMap = new Map()
  domainMap.forEach((domainData, domainName) => {
    domainData.subDomainMap.forEach((subDomainData, subDomainName) => {
      subDomainData.smMap.forEach((smData, smName) => {
        smData.boCodes.forEach(boCode => {
          nodeToServiceModuleMap.set(boCode, smName)
        })
      })
    })
  })

  // 分析哪些节点有外部连线（基于服务模块级别）
  const nodesWithExternalLinks = new Set()
  if (props.links && props.links.length > 0) {
    props.links.forEach(link => {
      const sourceCode = link.sourceCode
      const targetCode = link.targetCode
      const sourceServiceModule = nodeToServiceModuleMap.get(sourceCode)
      const targetServiceModule = nodeToServiceModuleMap.get(targetCode)

      if (sourceServiceModule && targetServiceModule && sourceServiceModule !== targetServiceModule) {
        if (sourceCode) nodesWithExternalLinks.add(sourceCode)
        if (targetCode) nodesWithExternalLinks.add(targetCode)
      }
    })
  }

  // domainMap 已经在前面构建好了，直接使用
  const groups = []

  domainMap.forEach((domainData, domainName) => {
    const { subDomainMap, domainCode } = domainData
    const childGroups = []

    subDomainMap.forEach((subDomainData, subDomainName) => {
      const { smMap, subDomainCode } = subDomainData
      const smChildGroups = []

      smMap.forEach((smData, smName) => {
        const { boCodes, smCode } = smData
        
        // ELK 自动分组：将有/无外部连线的节点分离
        const innerNodes = boCodes.filter(code => !nodesWithExternalLinks.has(code))
        const boundaryNodes = boCodes.filter(code => nodesWithExternalLinks.has(code))
        
        // 创建容器对象（供后续分组使用）
        const createNodeContainer = (boCode, elkType) => ({
          id: `bo_${boCode}_${elkType}`,
          name: codeToNameMap.get(boCode) || boCode,
          elementCode: boCode,
          isVirtual: true,
          nodes: [boCode],
          domain: domainName,
          subDomainName: subDomainName,
          serviceModuleName: smName,
          _elkGroup: elkType
        })
        
        // 内部节点容器（无外部连线）
        const innerContainers = innerNodes.map(code => createNodeContainer(code, 'inner'))
        // 边界节点容器（有外部连线）
        const boundaryContainers = boundaryNodes.map(code => createNodeContainer(code, 'boundary'))
        
        // 创建 ELK 子分组
        const createElkSubGroup = (title, containers, elkType) => ({
          id: createGroupId(GroupType.CUSTOM, `${smCode}_${elkType}`),
          title,
          elementCode: `${smCode}_${elkType}`,
          groupType: 'custom',
          domainName,
          subDomainName,
          serviceModuleName: smName,
          direction: 'TB',
          visible: false,  // 默认隐藏
          enabled: true,
          style: {
            fill: elkType === 'inner' ? '#e8f5e9' : '#fff3e0',
            stroke: elkType === 'inner' ? '#4caf50' : '#ff9800',
            strokeWidth: 1,
            strokeDasharray: ''
          },
          containers,
          children: [],
          parentId: null,  // 稍后设置
          _elkGroup: elkType
        })
        
        // 内部子分组（无外部关系）
        const innerGroup = createElkSubGroup('无外部关系', innerContainers, 'inner')
        // 边界子分组（有外部关系）
        const boundaryGroup = createElkSubGroup('有外部关系', boundaryContainers, 'boundary')
        
        // 根据是否有两类节点决定分组结构
        const hasInner = innerNodes.length > 0
        const hasBoundary = boundaryNodes.length > 0
        
        if (hasInner && hasBoundary) {
          // 两类节点都存在：创建父子分组结构
          const parentGroupId = createGroupId(GroupType.SERVICE_MODULE, smCode)
          innerGroup.parentId = parentGroupId
          boundaryGroup.parentId = parentGroupId
          
          const parentGroup = {
            id: parentGroupId,
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName,
            subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: [],
            children: [innerGroup, boundaryGroup],
            parentId: null
          }
          smChildGroups.push(parentGroup)
        } else if (hasInner) {
          // 只有无外部关系节点：只创建无外部关系分组（平铺，不嵌套）
          smChildGroups.push({
            id: createGroupId(GroupType.SERVICE_MODULE, smCode),
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName,
            subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: innerContainers,
            children: [],
            parentId: null,
            _elkGroup: 'inner'  // 标记为 ELK 分组
          })
        } else if (hasBoundary) {
          // 只有有外部关系节点：只创建有外部关系分组（平铺，不嵌套）
          smChildGroups.push({
            id: createGroupId(GroupType.SERVICE_MODULE, smCode),
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName,
            subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: boundaryContainers,
            children: [],
            parentId: null,
            _elkGroup: 'boundary'  // 标记为 ELK 分组
          })
        } else {
          // 不分离，保持原样 - 使用节点名称（没有外部连线数据时）
          const virtualContainers = boCodes.map(boCode => ({
            id: `bo_${boCode}`,
            name: codeToNameMap.get(boCode) || boCode,
            elementCode: boCode,
            isVirtual: true,
            nodes: [boCode],
            domain: domainName,
            subDomainName: subDomainName,
            serviceModuleName: smName
          }))

          smChildGroups.push({
            id: createGroupId(GroupType.SERVICE_MODULE, smCode),
            title: smName,
            elementCode: smCode,
            groupType: 'serviceModule',
            domainName: domainName,
            subDomainName: subDomainName,
            serviceModuleName: smName,
            direction: 'TB',
            visible: true,
            enabled: true,
            style: {
              fill: '#ffffff',
              stroke: '#666666',
              strokeWidth: 2,
              strokeDasharray: ''
            },
            containers: virtualContainers,
            children: [],
            parentId: null
          })
        }
      })

      childGroups.push({
        id: createGroupId(GroupType.SUB_DOMAIN, subDomainCode),
        title: subDomainName,
        elementCode: subDomainCode,
        groupType: 'subDomain',
        domainName: domainName,
        subDomainName: subDomainName,
        direction: 'LR',
        visible: true,
        enabled: true,
        style: {
          fill: '#ffffff',
          stroke: '#666666',
          strokeWidth: 2,
          strokeDasharray: ''
        },
        containers: [],
        children: smChildGroups,
        parentId: null
      })
    })

    const group = {
      id: createGroupId(GroupType.DOMAIN, domainCode),
      title: domainName,
      elementCode: domainCode,
      groupType: 'domain',
      domainName: domainName,
      direction: 'TB',
      visible: false,
      enabled: false,
      style: {
        fill: '#f5f5f5',
        stroke: '#333333',
        strokeWidth: 2,
        strokeDasharray: ''
      },
      containers: [],
      children: childGroups,
      parentId: null
    }

    groups.push(group)
  })

  localConfig.value.groups = groups
  localConfig.value.enabled = true
  emitUpdate()
}

function countNodesInGroup(group) {
  let count = 0
  if (group.containers && group.containers.length > 0) {
    count += group.containers.reduce((sum, c) => sum + (c.nodes ? c.nodes.length : 1), 0)
  }
  if (group.children && group.children.length > 0) {
    group.children.forEach(child => {
      count += countNodesInGroup(child)
    })
  }
  return count
}

function collectNodesInGroup(group, nodeSet = new Set()) {
  if (group.containers && group.containers.length > 0) {
    group.containers.forEach(container => {
      if (container.nodes) {
        container.nodes.forEach(nodeId => {
          const actualId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
          if (actualId) nodeSet.add(actualId)
        })
      }
    })
  }
  if (group.children && group.children.length > 0) {
    group.children.forEach(child => collectNodesInGroup(child, nodeSet))
  }
  return nodeSet
}

function calculateGroupConnectionDensity(group, links) {
  if (!links || links.length === 0) return 0
  
  const nodeSet = collectNodesInGroup(group)
  let density = 0
  
  links.forEach(link => {
    const sourceId = link.sourceCode || link.sourceName || link.source
    const targetId = link.targetCode || link.targetName || link.target
    
    const sourceInGroup = nodeSet.has(sourceId)
    const targetInGroup = nodeSet.has(targetId)
    
    if (sourceInGroup || targetInGroup) {
      density++
    }
  })
  
  return density
}

function countLeafNodesInGroup(group) {
  let count = 0
  
  if (group.containers && group.containers.length > 0) {
    group.containers.forEach(container => {
      if (container.nodes) {
        count += container.nodes.length
      } else {
        count += 1
      }
    })
  }
  
  if (group.directNodes && group.directNodes.length > 0) {
    count += group.directNodes.length
  }
  
  if (group.children && group.children.length > 0) {
    group.children.forEach(child => {
      count += countLeafNodesInGroup(child)
    })
  }
  
  return count
}

function isLeafGroup(group) {
  return (group.containers && group.containers.length > 0) ||
         (group.directNodes && group.directNodes.length > 0)
}

function hasSpecialGroup(group) {
  if (group.title === '有外部关系' || group.title === '无外部关系') {
    return true
  }
  if (group.children) {
    return group.children.some(child => hasSpecialGroup(child))
  }
  return false
}

function isInCenterScope(group, centerScopeCodes) {
  if (group.containers && group.containers.length > 0) {
    for (const container of group.containers) {
      if (container.nodes && container.nodes.length > 0) {
        for (const node of container.nodes) {
          const nodeCode = typeof node === 'object' ? (node.code || node.id || node.name) : node
          if (nodeCode && centerScopeCodes.has(nodeCode)) {
            return true
          }
        }
      }
    }
  }

  if (group.directNodes && group.directNodes.length > 0) {
    for (const node of group.directNodes) {
      const nodeCode = typeof node === 'object' ? (node.code || node.id || node.name) : node
      if (nodeCode && centerScopeCodes.has(nodeCode)) {
        return true
      }
    }
  }

  if (group.children && group.children.length > 0) {
    return group.children.some(child => isInCenterScope(child, centerScopeCodes))
  }

  return false
}

function optimizeGroupEnabledState(threshold = 0.2) {
  const groups = localConfig.value.groups

  if (!groups || groups.length === 0) {
    return
  }

  let totalNodes = (props.nodes || []).length
  if (totalNodes === 0) {
    totalNodes = groups.reduce((sum, g) => sum + countLeafNodesInGroup(g), 0)
  }

  const centerScopeCodes = new Set(diagramConfigStore.centerScope || [])

  function processGroup(group) {
    const isCenterGroup = isInCenterScope(group, centerScopeCodes)

    if (group.enabled === false) {
      if (group.children && group.children.length > 0) {
        group.children.forEach(child => processGroup(child))
      }
      return
    }

    if (isCenterGroup) {
      return
    }

    const isLeaf = isLeafGroup(group)

    if (isLeaf) {
      return
    }

    const leafNodeCount = countLeafNodesInGroup(group)
    const exceedsThreshold = leafNodeCount > totalNodes * threshold

    if (exceedsThreshold) {
      group.enabled = false
      if (group.children && group.children.length > 0) {
        group.children.forEach(child => processGroup(child))
      }
      return
    }

    if (group.children && group.children.length > 0) {
      group.children.forEach(child => processGroup(child))
    }
  }

  groups.forEach(group => {
    processGroup(group)
  })

  emitUpdate()
}

function handleOverallSort() {
  const groups = localConfig.value.groups
  
  if (!groups || groups.length === 0) {
    return
  }
  
  const links = props.links || []
  
  function collectFirstEnabledInBranch(groupList, collected, parentPath = []) {
    groupList.forEach(group => {
      if (group.enabled) {
        collected.push({ group, parentPath: [...parentPath, group] })
      } else {
        if (group.children && group.children.length > 0) {
          collectFirstEnabledInBranch(group.children, collected, [...parentPath, group])
        }
      }
    })
  }
  
  const firstEnabledGroups = []
  collectFirstEnabledInBranch(groups, firstEnabledGroups)
  
  if (firstEnabledGroups.length === 0) {
    return
  }
  
  const groupsWithStats = firstEnabledGroups.map(item => ({
    ...item,
    nodeCount: countNodesInGroup(item.group),
    connectionDensity: calculateGroupConnectionDensity(item.group, links)
  }))
  
  const maxNodes = Math.max(...groupsWithStats.map(g => g.nodeCount), 1)
  const maxDensity = Math.max(...groupsWithStats.map(g => g.connectionDensity), 1)
  
  groupsWithStats.sort((a, b) => {
    const scoreA = (a.nodeCount / maxNodes) * 0.4 + (a.connectionDensity / maxDensity) * 0.6
    const scoreB = (b.nodeCount / maxNodes) * 0.4 + (b.connectionDensity / maxDensity) * 0.6
    return scoreB - scoreA
  })
  
  groupsWithStats.forEach((item, index) => {
    item.group._sortOrder = index + 1
  })
  
  function reorderGroupsInTree(groupList, sortedGroups) {
    const sortedIds = new Set(sortedGroups.map(g => g.id))
    const sortedOrder = new Map(sortedGroups.map((g, i) => [g.id, i]))
    
    const sortedInThisLevel = groupList
      .filter(g => sortedIds.has(g.id))
      .sort((a, b) => (sortedOrder.get(a.id) || 0) - (sortedOrder.get(b.id) || 0))
    
    const notInSort = groupList.filter(g => !sortedIds.has(g.id))
    
    const result = [...sortedInThisLevel, ...notInSort]
    
    result.forEach(group => {
      if (group.children && group.children.length > 0) {
        group.children = reorderGroupsInTree(group.children, sortedGroups)
      }
    })
    
    return result
  }
  
  const sortedGroupObjects = groupsWithStats.map(g => g.group)
  localConfig.value.groups = reorderGroupsInTree(groups, sortedGroupObjects)
  
  emitUpdate()
}

function handleInLayerSort() {
  const groups = localConfig.value.groups
  if (!groups || groups.length === 0) {
    return
  }
  
  const links = props.links || []
  
  function sortLayerChildren(groupList, layerIndex = 0) {
    groupList.forEach(group => {
      if (group._isVirtualLayer && group.children && group.children.length > 0) {
        const enabledChildren = group.children.filter(c => c.enabled !== false)
        const disabledChildren = group.children.filter(c => c.enabled === false)
        
        if (enabledChildren.length > 1) {
          const childrenWithStats = enabledChildren.map(child => ({
            child,
            nodeCount: countNodesInGroup(child),
            connectionDensity: calculateGroupConnectionDensity(child, links)
          }))
          
          const maxNodes = Math.max(...childrenWithStats.map(c => c.nodeCount), 1)
          const maxDensity = Math.max(...childrenWithStats.map(c => c.connectionDensity), 1)
          
          childrenWithStats.sort((a, b) => {
            const scoreA = (a.nodeCount / maxNodes) * 0.4 + (a.connectionDensity / maxDensity) * 0.6
            const scoreB = (b.nodeCount / maxNodes) * 0.4 + (b.connectionDensity / maxDensity) * 0.6
            return scoreB - scoreA
          })
          
          childrenWithStats.forEach((item, index) => {
            item.child._layerSortOrder = index + 1
            item.child._parentLayerIndex = layerIndex
          })
          
          group.children = [...childrenWithStats.map(item => item.child), ...disabledChildren]
        }
      }
      
      if (group.children && group.children.length > 0) {
        sortLayerChildren(group.children, group._isVirtualLayer ? group._layerIndex : layerIndex)
      }
    })
  }
  
  sortLayerChildren(groups)
  
  emitUpdate()
}

function handleAutoVirtualLayering(layerCount = 3) {
  const groups = localConfig.value.groups
  
  if (!groups || groups.length === 0) {
    console.warn('[LayoutControlPanel] No groups to virtual layer')
    return
  }

  function collectTopLevelGroupsForLayering(groupList, collected, parentList = []) {
    groupList.forEach(group => {
      if (!group.enabled) {
        if (group.children) {
          const newParentList = [...parentList, group]
          group.children.forEach(child => {
            collectFromDisabledGroup(child, newParentList, collected)
          })
        }
        return
      }

      collected.push({ group, parentList: [...parentList, group] })
    })
  }

  function collectFromDisabledGroup(group, parentList, collected) {
    if (group.enabled) {
      collected.push({ group, parentList: [...parentList, group] })
    } else {
      const newParentList = [...parentList, group]
      if (group.children) {
        group.children.forEach(child => {
          collectFromDisabledGroup(child, newParentList, collected)
        })
      }
    }
  }

  const allEnabledLeafGroups = []
  collectTopLevelGroupsForLayering(groups, allEnabledLeafGroups)



  if (allEnabledLeafGroups.length === 0) {
    console.warn('[LayoutControlPanel] No enabled leaf groups found')
    return
  }

  allEnabledLeafGroups.forEach(item => {
    if (item.parentList.length >= 2) {
      const directParent = item.parentList[item.parentList.length - 2]
      if (directParent && directParent.children) {
        directParent.children = directParent.children.filter(c => c.id !== item.group.id)
      }
    } else if (item.parentList.length === 1) {
      const idx = groups.findIndex(g => g.id === item.group.id)
      groups.splice(idx, 1)
    }
  })

  const layerCountInt = Math.max(1, Math.min(layerCount, 10))

  const targetLayerNodeCounts = []
  let totalNodes = allEnabledLeafGroups.reduce((sum, item) => sum + countNodesInGroup(item.group), 0)
  for (let i = 0; i < layerCountInt; i++) {
    targetLayerNodeCounts.push(Math.round(totalNodes / layerCountInt))
  }

  const layers = []
  for (let i = 0; i < layerCountInt; i++) {
    layers.push({
      id: generateGroupId(),
      title: `虚拟层 ${i + 1}`,
      elementCode: `virtual_layer_${i + 1}`,
      groupType: 'virtualLayer',
      direction: 'TB',
      visible: true,
      enabled: true,
      style: {
        fill: '#f0f9ff',
        stroke: '#0284c7',
        strokeWidth: 1,
        strokeDasharray: '5,5'
      },
      containers: [],
      children: [],
      parentId: null,
      _isVirtualLayer: true,
      _layerIndex: i
    })
  }

  const layerNodeTargets = new Array(layerCountInt).fill(0)
  const groupToLayer = new Map()

  const hasSortOrder = allEnabledLeafGroups.some(item => item.group._sortOrder)
  
  if (hasSortOrder) {
    allEnabledLeafGroups.sort((a, b) => {
      const orderA = a.group._sortOrder || Infinity
      const orderB = b.group._sortOrder || Infinity
      return orderA - orderB
    })
  } else {
    allEnabledLeafGroups.sort((a, b) => countNodesInGroup(b.group) - countNodesInGroup(a.group))
  }

  for (let i = 0; i < allEnabledLeafGroups.length; i++) {
    const item = allEnabledLeafGroups[i]
    const nodeCount = countNodesInGroup(item.group)
    let bestLayer = 0
    let minLoadAfter = Infinity

    for (let j = 0; j < layerCountInt; j++) {
      const loadAfter = layerNodeTargets[j] + nodeCount
      if (loadAfter < minLoadAfter) {
        minLoadAfter = loadAfter
        bestLayer = j
      } else if (loadAfter === minLoadAfter) {
        if (layerNodeTargets[j] < layerNodeTargets[bestLayer]) {
          bestLayer = j
        }
      }
    }

    layerNodeTargets[bestLayer] += nodeCount
    groupToLayer.set(i, bestLayer)
  }

  const virtualLayerGroups = new Map()
  layers.forEach(layer => {
    virtualLayerGroups.set(layer._layerIndex, [])
  })

  allEnabledLeafGroups.forEach((item, idx) => {
    const layerIdx = groupToLayer.get(idx)
    virtualLayerGroups.get(layerIdx).push(item.group)
  })

  virtualLayerGroups.forEach((groupsInLayer, layerIdx) => {
    layers[layerIdx].children = groupsInLayer
    groupsInLayer.forEach(g => {
      g.parentId = layers[layerIdx].id
    })
  })

  // 注意：fullTitle 的计算已统一在 GroupModel.toMermaidConfig() 中处理
  // 这里不再二次修改 fullTitle，遵循原生布局原则

  allEnabledLeafGroups.forEach(item => {
    item.parentList.forEach(parent => {
      if (parent.children) {
        parent.children = parent.children.filter(c => c.id !== item.group.id)
      }
    })
  })

  function isGroupEmpty(group) {
    if (group.containers && group.containers.length > 0) return false
    if (group.children && group.children.length > 0) {
      return group.children.every(child => !child.enabled && isGroupEmpty(child))
    }
    return true
  }

  function promoteDisabledChildren(groups) {
    let result = [...groups]
    let changed = true

    while (changed) {
      changed = false
      const newResult = []

      for (const g of result) {
        if (g.enabled) {
          newResult.push(g)
        } else {
          if (g.children && g.children.length > 0) {
            const onlyDisabledChildren = g.children.every(child => !child.enabled)
            if (onlyDisabledChildren) {
              const promotedChildren = g.children.map(child => ({
                ...child,
                parentId: g.parentId,
                children: []
              }))
              newResult.push(...promotedChildren)
              g.children = []
              changed = true
            } else {
              newResult.push(g)
            }
          }
          // disabled groups with no children are not added to newResult
        }
      }

      result = newResult
    }

    return result
  }

  let remainingGroups = groups.filter(g => {
    if (g.enabled) return true
    return !isGroupEmpty(g)
  })



  localConfig.value.groups = [...remainingGroups, ...layers]
  localConfig.value.enabled = true
  emitUpdate()
}
</script>

<style scoped lang="scss">
.layout-control-panel {
  padding: var(--spacing-md);
}

.panel-content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.auto-group-section {
  padding: var(--spacing-sm) 0;
}

.auto-group-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  .btn-icon {
    font-size: 16px;
  }

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
  }

  &:active {
    transform: translateY(0);
  }
}

.overall-direction-section {
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.direction-select {
  width: 100%;
  padding: var(--spacing-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  background: white;
  cursor: pointer;

  &:focus {
    outline: none;
    border-color: var(--color-primary);
  }
}

.section-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: var(--spacing-sm);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.containers-section {
  padding: var(--spacing-md);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.containers-pool {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  min-height: 32px;
  max-height: 120px;
  overflow-y: auto;
}

.container-item {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: white;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  cursor: grab;
  transition: all 0.2s;
  user-select: none;

  &:hover {
    border-color: var(--color-primary);
    background: rgba(234, 88, 12, 0.05);
  }

  &:active {
    cursor: grabbing;
    opacity: 0.7;
  }
}

.pool-empty {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  font-style: italic;
  padding: var(--spacing-sm);
}

.groups-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.label-hint {
  font-size: 11px;
  color: #888;
  font-weight: normal;
  text-transform: none;
  letter-spacing: normal;
}

.groups-container {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.empty-hint {
  padding: var(--spacing-lg);
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

.add-group-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.2s;

  &:hover {
    border-color: var(--color-primary);
    color: var(--color-primary);
    background: rgba(234, 88, 12, 0.05);
  }

  .btn-icon {
    font-size: 16px;
    font-weight: bold;
  }
}

.auto-group-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  border: 2px solid var(--color-primary);
  border-radius: var(--radius-md);
  background: rgba(234, 88, 12, 0.08);
  color: var(--color-primary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all 0.2s;

  &:hover {
    background: rgba(234, 88, 12, 0.15);
    box-shadow: 0 2px 8px rgba(234, 88, 12, 0.2);
  }

  .btn-icon {
    font-size: 14px;
  }
}
</style>
