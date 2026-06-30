// 布局类型常量（简化后只保留 grouped）
export const LAYOUT_TYPES = {
  GROUPED: 'grouped',
}

// 废弃的布局类型（向后兼容）
export const DEPRECATED_LAYOUT_TYPES = {
  DEFAULT: 'default',
  HORIZONTAL: 'horizontal',
  VERTICAL: 'vertical',
  ZONE: 'zone',
}

import { generateLinearLayout } from './linearLayout.js'
import { generateZoneLayout } from './elkZoneLayout.js'
import { generateGroupedLayout } from './groupedLayout.js'

/**
 * 将废弃的布局类型转换为新的布局控制配置
 */
export function convertDeprecatedLayout(layoutType, containers = [], config = {}) {
  const containerIds = containers.map(c => c.id || c.name)
  
  switch (layoutType) {
    case DEPRECATED_LAYOUT_TYPES.DEFAULT:
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: false,
          overallDirection: 'LR',
          groups: []
        }
      }
      
    case DEPRECATED_LAYOUT_TYPES.HORIZONTAL:
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: true,
          overallDirection: 'LR',
          groups: [{
            id: 'group-0',
            title: '主分组',
            direction: 'LR',
            containers: containerIds,
          }]
        }
      }
      
    case DEPRECATED_LAYOUT_TYPES.VERTICAL:
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: true,
          overallDirection: 'TB',
          groups: [{
            id: 'group-0',
            title: '主分组',
            direction: 'TB',
            containers: containerIds,
          }]
        }
      }
      
    case DEPRECATED_LAYOUT_TYPES.ZONE: {
      const zoneRowCount = config.zoneRowCount || 3
      const containersPerRow = Math.ceil(containers.length / zoneRowCount)
      const groups = []
      
      for (let r = 0; r < zoneRowCount; r++) {
        const rowContainers = containerIds.slice(r * containersPerRow, (r + 1) * containersPerRow)
        if (rowContainers.length > 0) {
          groups.push({
            id: `group-${r}`,
            title: `第${r + 1}行`,
            direction: 'LR',
            containers: rowContainers,
          })
        }
      }
      
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: true,
          overallDirection: 'TB',
          groups: groups
        }
      }
    }
      
    default:
      console.warn('[convertDeprecatedLayout] Unknown deprecated layout type:', layoutType)
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: false,
          overallDirection: 'LR',
          groups: []
        }
      }
  }
}

/**
 * 检查是否为废弃的布局类型
 */
export function isDeprecatedLayout(layoutType) {
  return Object.values(DEPRECATED_LAYOUT_TYPES).includes(layoutType)
}

/**
 * 根据配置自动选择布局引擎
 */
export function selectLayoutEngine(layoutControlConfig) {
  if (layoutControlConfig?.enabled && layoutControlConfig?.preserveOrder) {
    return 'dagre'
  }
  return 'elk'
}

/**
 * 路由到对应的布局生成器
 */
export function routeLayout(containers, config) {
  console.log('[routeLayout] ENTRY - containers:', containers?.length)
  console.log('[routeLayout] config.layoutControlConfig.groups?.length:', config?.layoutControlConfig?.groups?.length)
  
  let {
    layoutType = LAYOUT_TYPES.GROUPED,
    layoutEngine = 'dagre',
    positions = [],
    sortedContainers = null,
    zoneRowCount = 3,
    nodeMap,
    definedNodes,
    layoutControlConfig,
    links = []
  } = config || {}

  if (!containers || containers.length === 0) {
    console.log('[routeLayout] No containers, returning null')
    return null
  }

  if (isDeprecatedLayout(layoutType)) {
    const converted = convertDeprecatedLayout(layoutType, containers, { zoneRowCount })
    layoutType = converted.layoutType
    layoutControlConfig = converted.layoutControlConfig
  }

  try {
    if (layoutControlConfig?.enabled && layoutControlConfig?.groups?.length > 0) {
      console.log('[routeLayout] Calling generateGroupedLayout...')
      const result = generateGroupedLayout(layoutControlConfig.groups, containers, nodeMap, definedNodes, layoutControlConfig.overallDirection, layoutEngine, links)
      console.log('[routeLayout] generateGroupedLayout result:', result)
      if (result && result.mermaidCode) {
        let code = result.mermaidCode
        if (result.styleLines && result.styleLines.length > 0) {
          code += '\n' + result.styleLines.join('\n') + '\n'
        }
        return code
      }
      return null
    }
    console.log('[routeLayout] layoutControlConfig condition not met, returning null')
    return null
  } catch (error) {
    console.error('Layout generation error:', error)
    return null
  }
}

/**
 * 检查布局类型是否为网格布局
 */
export function isGridLayout(layoutType) {
  if (!layoutType) return false
  return layoutType === DEPRECATED_LAYOUT_TYPES.ZONE
}

/**
 * 获取布局引擎
 */
export function getLayoutEngine(layoutType, userEngine = 'dagre') {
  return userEngine || 'dagre'
}

export { generateGroupedLayout }
