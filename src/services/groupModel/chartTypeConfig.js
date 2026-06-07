/**
 * 图表类型配置
 * 
 * 定义不同图表类型的分组层级、显示规则等
 */

import { GroupType } from './types.js'

export const ChartType = {
  BUSINESS_OBJECT: 'businessObject',
  SERVICE_MODULE: 'serviceModule'
}

export const ChartTypeConfig = {
  [ChartType.BUSINESS_OBJECT]: {
    groupHierarchy: [
      GroupType.DOMAIN,
      GroupType.SUB_DOMAIN,
      GroupType.SERVICE_MODULE,
      GroupType.BUSINESS_OBJECT
    ],
    visibleInControlPanel: [
      GroupType.DOMAIN,
      GroupType.SUB_DOMAIN,
      GroupType.SERVICE_MODULE
    ],
    terminalTypes: [GroupType.BUSINESS_OBJECT],
    defaultExpandDepth: 3,
    defaultDirection: 'LR'
  },
  [ChartType.SERVICE_MODULE]: {
    groupHierarchy: [
      GroupType.DOMAIN,
      GroupType.SUB_DOMAIN,
      GroupType.SERVICE_MODULE
    ],
    visibleInControlPanel: [
      GroupType.DOMAIN,
      GroupType.SUB_DOMAIN
    ],
    terminalTypes: [GroupType.SERVICE_MODULE],
    defaultExpandDepth: 2,
    defaultDirection: 'LR'
  }
}

export function getChartTypeConfig(chartType) {
  return ChartTypeConfig[chartType] || ChartTypeConfig[ChartType.BUSINESS_OBJECT]
}

export function isGroupVisibleInControlPanel(group, chartType) {
  const config = getChartTypeConfig(chartType)
  return config.visibleInControlPanel.includes(group.type)
}

export function isTerminalType(groupType, chartType) {
  const config = getChartTypeConfig(chartType)
  return config.terminalTypes.includes(groupType)
}

export function filterGroupsForControlPanel(groups, chartType) {
  const config = getChartTypeConfig(chartType)
  const result = []

  function processGroup(group) {
    if (config.visibleInControlPanel.includes(group.type)) {
      const filteredGroup = {
        ...group,
        children: group.children
          .map(child => processGroup(child))
          .filter(Boolean)
      }
      return filteredGroup
    }
    
    if (group.children && group.children.length > 0) {
      return group.children
        .map(child => processGroup(child))
        .filter(Boolean)
    }
    
    return null
  }

  groups.forEach(group => {
    const processed = processGroup(group)
    if (processed) {
      if (Array.isArray(processed)) {
        result.push(...processed)
      } else {
        result.push(processed)
      }
    }
  })

  return result
}
