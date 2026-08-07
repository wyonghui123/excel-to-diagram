import { computed } from 'vue'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

// 从 GroupItem.vue 抽取的显示助手（名称/颜色/类型标签/提示），供树节点与旧组件复用
// colorMapping 由调用方传入（来自 props），store 不持有该字段
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

// colorMapping 支持两种传法：
//   1) 普通对象（测试/一次性场景）
//   2) getter 函数 () => props.colorMapping —— 组件内必须用 getter，
//      否则闭包会捕获 setup 时的旧引用，导致 chartDataSnapshot 更新后
//      (groupColorMap 每次 re-colorize 都是新对象) 色点仍读旧映射 → 清空自定义色后回不到默认色。
export function useGroupDisplay(colorMapping) {
  const store = useDiagramConfigStore()

  // 每次调用实时解析，保证读到当前 colorMapping（无闭包陈旧问题）
  const resolveColorMap = () => (typeof colorMapping === 'function' ? colorMapping() : colorMapping)

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
    const map = resolveColorMap()
    if (map && map[key]) return map[key]
    if (customColors.value && customColors.value[key]) return customColors.value[key]
    return null
  }

  function getContainerName(container, containers) {
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
      const found = (containers || []).find(c => c.id === container)
      if (found) {
        const result = resolveNameAndCode(found)
        if (result) return result
      }
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

  // 判断分组是否属于中心范围（区分中心范围时，其 BO/容器节点 code 命中 centerScope）
  function isGroupInCenterScope(group, centerScopeSet) {
    if (!group || !centerScopeSet || centerScopeSet.size === 0) return false
    if (group.groupType === 'businessObject') {
      const boid = group.elementCode || group.id || group.name
      if (boid && centerScopeSet.has(boid)) return true
    }
    if (group.containers && group.containers.length) {
      for (const c of group.containers) {
        if (c.nodes && c.nodes.length) {
          for (const n of c.nodes) {
            const code = typeof n === 'object' ? (n.code || n.id || n.name) : n
            if (code && centerScopeSet.has(code)) return true
          }
        }
      }
    }
    if (group.directNodes && group.directNodes.length) {
      for (const n of group.directNodes) {
        const code = typeof n === 'object' ? (n.code || n.id || n.name) : n
        if (code && centerScopeSet.has(code)) return true
      }
    }
    if (group.children && group.children.length) {
      return group.children.some(ch => isGroupInCenterScope(ch, centerScopeSet))
    }
    return false
  }

  // 分组节点取色（与 GroupItem.vue groupColor 逻辑一致；custom 分组不参与着色）
  // 返回 { color, key, isCenter }：
  //   - color 为当前展示色；key 为 customColors 写入键（与 colorize.js 维度 key 对齐）
  //   - isCenter=true 表示该分组属于中心范围且区分开启 → color 用 centerScopeColor（与图表同源）
  //     此时 key 置空（改色走 centerScopeColor，不写 customColors）。
  function getGroupColor(group) {
    if (!group) return { color: null, key: '', isCenter: false }
    if (group.groupType === 'custom') return { color: null, key: '', isCenter: false }

    // [中心范围 2026-08-05 方案A] 区分中心范围开启且分组属于中心范围 →
    //   色点显示 centerScopeColor（灰），与图表中心节点被 centerScopeColor 覆盖一致。
    const centerScopeSet = new Set(centerScope.value || [])
    if (centerScopeHighlight.value && isGroupInCenterScope(group, centerScopeSet)) {
      const cc = CENTER_COLOR_MAP[centerScopeColor.value] || centerScopeColor.value || '#808080'
      return { color: cc, key: '', isCenter: true }
    }

    let colorKey = ''
    if (colorGroupBy.value === 'subDomain') {
      colorKey = group.subDomainName || group.title
    } else if (colorGroupBy.value === 'serviceModule') {
      colorKey = group.serviceModuleName || group.title
    } else {
      colorKey = group.domainName || group.title
    }

    const fromMap = colorFromMap(colorKey)
    if (fromMap) return { color: fromMap, key: colorKey, isCenter: false }
    if (!colorKey || typeof colorKey !== 'string') return { color: '#808080', key: colorKey, isCenter: false }
    return { color: hashColor(colorKey), key: colorKey, isCenter: false }
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
    getContainerName, getNodeName, getContainerColor, getNodeColor, getGroupColor,
    getGroupTypeLabel, getElkGroupHint, COLOR_SCHEMES
  }
}