/**
 * 分组扁平化处理器
 * 
 * 处理 enabled=false 的分组，将其子元素提升到最近的 enabled=true 的祖先下
 * 
 * 核心算法：
 * 1. 遍历分组树
 * 2. 若分组 enabled=true 且非末端节点 → 保留容器，递归处理 children
 * 3. 若分组 enabled=false → 不保留该节点，将其 children 提升到当前结果列表
 * 4. 末端节点始终保留
 */

import { GroupType, isTerminalGroup } from './types.js'
import { ChartType } from './chartTypeConfig.js'

/**
 * 扁平化禁用的分组
 * 将 enabled=false 的分组的子元素提升到最近启用的祖先下
 * 
 * @param {Array} groups - 分组模型数组
 * @param {string} chartType - 图表类型
 * @returns {Array} 扁平化后的分组模型
 */
export function flattenDisabledGroups(groups, chartType) {
  if (!groups || groups.length === 0) {
    return groups
  }

  console.log('[flattenDisabledGroups] input:', groups.map(g => g.title))
  const result = []

  groups.forEach(group => {
    const flattened = processGroup(group, chartType, null, [])
    if (flattened) {
      if (Array.isArray(flattened)) {
        console.log(`[flattenDisabledGroups] ${group.title} -> lifted: [${flattened.map(g => g.title).join(',')}]`)
        result.push(...flattened)
      } else {
        console.log(`[flattenDisabledGroups] ${group.title} -> kept`)
        result.push(flattened)
      }
    }
  })

  console.log('[flattenDisabledGroups] result:', result.map(g => `${g.title}(_disabledAncestorPath:[${(g._disabledAncestorPath || []).join(',')}])`))
  return result
}

/**
 * 处理单个分组
 * 
 * @param {Object} group - 分组对象
 * @param {string} chartType - 图表类型
 * @param {Object|null} parentContext - 父级上下文（用于继承 enabled 状态）
 * @param {Array} disabledAncestorPath - 被禁用的祖先路径
 * @returns {Object|Array|null} 处理后的分组或分组数组
 */
function processGroup(group, chartType, parentContext, disabledAncestorPath = []) {
  const isTerminal = isTerminalGroup(group, chartType)
  const isEnabled = group.layout?.enabled !== false

  console.log(`[processGroup] ${group.title} (isTerminal:${isTerminal}, isEnabled:${isEnabled}, layout.enabled:${group.layout?.enabled}, disabledAncestorPath:[${disabledAncestorPath.join(',')}])`)

  if (isTerminal) {
    const newParentId = parentContext?.id || null
    return {
      ...group,
      parentId: newParentId,
      _disabledAncestorPath: disabledAncestorPath.length > 0 ? disabledAncestorPath : undefined
    }
  }

  if (!isEnabled) {
    const newDisabledPath = [...disabledAncestorPath, group.title]
    console.log(`[processGroup] ${group.title} -> DISABLED, newDisabledPath:[${newDisabledPath.join(',')}]`)
    
    const liftedChildren = []
    
    if (group.children && group.children.length > 0) {
      group.children.forEach(child => {
        const processed = processGroup(child, chartType, null, newDisabledPath)
        if (processed) {
          if (Array.isArray(processed)) {
            liftedChildren.push(...processed)
          } else {
            liftedChildren.push(processed)
          }
        }
      })
    }

    return liftedChildren.length > 0 ? liftedChildren : null
  }

  const newGroup = {
    ...group,
    children: [],
    parentId: parentContext?.id || null,
    _disabledAncestorPath: disabledAncestorPath.length > 0 ? disabledAncestorPath : undefined
  }
  console.log(`[processGroup] ${group.title} -> ENABLED, _disabledAncestorPath:[${disabledAncestorPath.join(',')}]`)

  if (group.children && group.children.length > 0) {
    group.children.forEach(child => {
      const processed = processGroup(child, chartType, newGroup, []) // 传递空数组，因为当前分组启用了
      if (processed) {
        if (Array.isArray(processed)) {
          newGroup.children.push(...processed)
        } else {
          newGroup.children.push(processed)
        }
      }
    })
  }

  return newGroup
}

/**
 * 检查分组是否需要扁平化（是否有 disabled 的祖先）
 * 
 * @param {Object} group - 分组对象
 * @param {Array} allGroups - 所有分组
 * @returns {boolean}
 */
export function hasDisabledAncestor(group, allGroups) {
  if (!group.parentId) {
    return false
  }

  const parent = findGroupById(allGroups, group.parentId)
  if (!parent) {
    return false
  }

  if (parent.layout?.enabled === false) {
    return true
  }

  return hasDisabledAncestor(parent, allGroups)
}

/**
 * 查找分组（支持森林结构）
 */
function findGroupById(groups, id) {
  for (const group of groups) {
    if (group.id === id) {
      return group
    }
    if (group.children && group.children.length > 0) {
      const found = findGroupById(group.children, id)
      if (found) {
        return found
      }
    }
  }
  return null
}

/**
 * 获取分组的有效父级（最近的 enabled=true 的祖先）
 * 
 * @param {Object} group - 分组对象
 * @param {Array} allGroups - 所有分组
 * @returns {Object|null} 有效的父级分组
 */
export function getEffectiveParent(group, allGroups) {
  if (!group.parentId) {
    return null
  }

  const directParent = findGroupById(allGroups, group.parentId)
  if (!directParent) {
    return null
  }

  if (directParent.layout?.enabled !== false) {
    return directParent
  }

  return getEffectiveParent(directParent, allGroups)
}
