/**
 * 统一分组模型 - 类型定义和常量
 * 
 * 核心设计理念：
 * 1. 一切皆分组：领域、子领域、服务模块、业务对象都是分组
 * 2. 末端分组即节点：type 为 BUSINESS_OBJECT 或 SERVICE_MODULE（服务模块图）的分组就是渲染节点
 * 3. 关联关系明确：每个分组可选关联一个架构元素
 * 4. 层级结构统一：通过 parentId/children 构建树形结构
 */

export const GroupType = {
  DOMAIN: 'DOMAIN',
  SUB_DOMAIN: 'SUB_DOMAIN',
  SERVICE_MODULE: 'SERVICE_MODULE',
  BUSINESS_OBJECT: 'BUSINESS_OBJECT',
  LAYOUT: 'LAYOUT'
}

export const GroupTypeLabels = {
  [GroupType.DOMAIN]: '领域',
  [GroupType.SUB_DOMAIN]: '子领域',
  [GroupType.SERVICE_MODULE]: '服务模块',
  [GroupType.BUSINESS_OBJECT]: '业务对象',
  [GroupType.LAYOUT]: '布局分组'
}

export function createGroupId(type, code) {
  const prefix = {
    [GroupType.DOMAIN]: 'D',
    [GroupType.SUB_DOMAIN]: 'SD',
    [GroupType.SERVICE_MODULE]: 'SM',
    [GroupType.BUSINESS_OBJECT]: 'BO',
    [GroupType.LAYOUT]: 'L'
  }
  const safeCode = String(code).replace(/[^a-zA-Z0-9_\u4e00-\u9fa5]/g, '_')
  return `${prefix[type] || 'G'}_${safeCode}`
}

export function createGroupStyle() {
  return {
    fill: '#f5f5f5',
    stroke: '#333333',
    strokeWidth: 1,
    strokeDasharray: ''
  }
}

export function createGroup(options) {
  const {
    type,
    title,
    parentId = null,
    elementRef = null,
    children = [],
    containers = [],
    layout = {}
  } = options

  const id = elementRef?.code 
    ? createGroupId(type, elementRef.code)
    : createGroupId(type, title)

  return {
    id,
    type,
    title,
    elementRef,
    parentId,
    children: [...children],
    containers: [...containers],
    layout: {
      direction: layout.direction || 'TB',
      visible: layout.visible !== false,
      enabled: layout.enabled !== false,
      style: {
        ...createGroupStyle(),
        ...(layout.style || {})
      }
    },
    color: null,
    textColor: null,
    annotationCategory: 'info',
    annotationContent: ''
  }
}

export function isTerminalGroup(group, chartType) {
  if (chartType === 'serviceModule') {
    return group.type === GroupType.SERVICE_MODULE
  }
  return group.type === GroupType.BUSINESS_OBJECT
}

export function findGroupById(groups, id) {
  for (const group of groups) {
    if (group.id === id) {
      return group
    }
    const found = findGroupById(group.children, id)
    if (found) {
      return found
    }
  }
  return null
}

export function findGroupByElementCode(groups, type, code) {
  for (const group of groups) {
    if (group.elementRef?.type === type && group.elementRef?.code === code) {
      return group
    }
    const found = findGroupByElementCode(group.children, type, code)
    if (found) {
      return found
    }
  }
  return null
}

export function traverseGroups(groups, callback, depth = 0, parent = null) {
  groups.forEach((group, index) => {
    callback(group, depth, parent, index)
    if (group.children.length > 0) {
      traverseGroups(group.children, callback, depth + 1, group)
    }
  })
}

export function flattenGroups(groups) {
  const result = []
  traverseGroups(groups, (group) => {
    result.push(group)
  })
  return result
}

export function getGroupPath(groups, targetId) {
  const path = []
  
  function search(groupList, target, currentPath) {
    for (const group of groupList) {
      const newPath = [...currentPath, group]
      if (group.id === target) {
        return newPath
      }
      const found = search(group.children, target, newPath)
      if (found) {
        return found
      }
    }
    return null
  }
  
  return search(groups, targetId, path) || []
}
