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
 * @param {string} layoutType - 废弃的布局类型
 * @param {Array} containers - 容器列表
 * @param {Object} config - 原始配置
 * @returns {Object} - 转换后的配置 { layoutType, layoutControlConfig }
 */
export function convertDeprecatedLayout(layoutType, containers = [], config = {}) {
  console.log('[convertDeprecatedLayout] Converting deprecated layout:', layoutType)
  
  const containerIds = containers.map(c => c.id || c.name)
  
  switch (layoutType) {
    case DEPRECATED_LAYOUT_TYPES.DEFAULT:
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: false,
          overallDirection: 'TB',
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
      
    case DEPRECATED_LAYOUT_TYPES.ZONE:
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
      
    default:
      console.warn('[convertDeprecatedLayout] Unknown deprecated layout type:', layoutType)
      return {
        layoutType: LAYOUT_TYPES.GROUPED,
        layoutControlConfig: {
          enabled: false,
          overallDirection: 'TB',
          groups: []
        }
      }
  }
}

/**
 * 检查是否为废弃的布局类型
 * @param {string} layoutType
 * @returns {boolean}
 */
export function isDeprecatedLayout(layoutType) {
  return Object.values(DEPRECATED_LAYOUT_TYPES).includes(layoutType)
}

/**
 * 根据配置自动选择布局引擎
 * @param {Object} layoutControlConfig - 布局控制配置
 * @param {boolean} layoutControlConfig.enabled - 是否启用布局控制
 * @param {boolean} layoutControlConfig.preserveOrder - 是否保持顺序
 * @returns {string} - 选择的引擎 ('dagre' 或 'elk')
 */
export function selectLayoutEngine(layoutControlConfig) {
  if (layoutControlConfig?.enabled && layoutControlConfig?.preserveOrder) {
    return 'dagre'
  }
  return 'elk'
}

/**
 * 路由到对应的布局生成器
 * @param {Array} containers - 容器列表
 * @param {Object} config - 布局配置
 * @param {string} config.layoutType - 布局类型
 * @param {string} config.layoutEngine - 布局引擎 ('dagre' 或 'elk')
 * @param {Array} config.positions - 容器位置映射（可选）
 * @param {Array} config.sortedContainers - 已排序的容器列表（可选）
 * @param {number} config.zoneRowCount - 分区行数（仅 zone 布局）
 * @param {Map} config.nodeMap - 节点映射表
 * @param {Set} config.definedNodes - 已定义节点集合
 * @param {Object} config.layoutControlConfig - 布局控制配置（用于自动选择引擎）
 * @returns {string|null} - Mermaid 语法字符串，null 表示使用默认布局
 */
export function routeLayout(containers, config) {
  let { 
    layoutType = LAYOUT_TYPES.GROUPED, 
    layoutEngine = 'dagre', 
    positions = [], 
    sortedContainers = null, 
    zoneRowCount = 3,
    nodeMap,
    definedNodes,
    layoutControlConfig
  } = config || {}

  console.log('[routeLayout] called with:', { 
    layoutType, 
    layoutEngine, 
    zoneRowCount, 
    containersCount: containers?.length,
    layoutControlConfig,
    isDeprecated: isDeprecatedLayout(layoutType)
  })

  if (!containers || containers.length === 0) {
    return null
  }

  /**
   * 向后兼容：将废弃的布局类型转换为新的布局控制配置
   */
  if (isDeprecatedLayout(layoutType)) {
    console.log('[routeLayout] Converting deprecated layout type:', layoutType)
    const converted = convertDeprecatedLayout(layoutType, containers, { zoneRowCount })
    layoutType = converted.layoutType
    layoutControlConfig = converted.layoutControlConfig
    console.log('[routeLayout] Converted to:', { layoutType, layoutControlConfig })
  }

  const selectedEngine = selectLayoutEngine(layoutControlConfig)
  const finalEngine = layoutControlConfig ? selectedEngine : layoutEngine

  try {
    if (layoutControlConfig?.enabled && layoutControlConfig?.groups?.length > 0) {
      console.log('[routeLayout] GROUPED layout - groups:', JSON.stringify(layoutControlConfig.groups, null, 2))
      console.log('[routeLayout] GROUPED layout - containers:', containers?.map(c => ({ id: c.id, name: c.name, fullTitle: c.fullTitle, nodesCount: c.nodes?.length })))
      const result = generateGroupedLayout(layoutControlConfig.groups, containers, nodeMap, definedNodes, layoutControlConfig.overallDirection)
      if (result && result.mermaidCode) {
        let code = result.mermaidCode
        if (result.styleLines && result.styleLines.length > 0) {
              code += '\n' + result.styleLines.join('\n') + '\n'
            }
            console.log('[routeLayout] GROUPED layout - FULL generated code:\n', code)
            return code
          }
          return null
        }
        console.log('[routeLayout] No groups configured, using default layout')
        return null
  } catch (error) {
    console.error('Layout generation error:', error)
    return null
  }
}

/**
 * 检查布局类型是否为网格布局
 * @param {string} layoutType
 * @returns {boolean}
 */
export function isGridLayout(layoutType) {
  if (!layoutType) return false
  return layoutType === DEPRECATED_LAYOUT_TYPES.ZONE
}

/**
 * 获取布局引擎
 * @param {string} layoutType - 布局类型
 * @param {string} userEngine - 用户选择的引擎
 * @returns {string} - 实际使用的引擎
 */
export function getLayoutEngine(layoutType, userEngine = 'dagre') {
  return userEngine || 'dagre'
}

export { generateGroupedLayout }
