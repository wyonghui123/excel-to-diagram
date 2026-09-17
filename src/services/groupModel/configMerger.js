/**
 * 用户配置合并器
 * 
 * 将用户布局配置合并到分组模型
 * 用户配置优先级高于自动生成
 */

import { 
  GroupType, 
  createGroup, 
  findGroupById,
  findGroupByElementCode,
  traverseGroups 
} from './types.js'

/**
 * 构建用户配置索引
 * 用于快速查找用户配置
 */
function buildConfigIndex(userGroups) {
  const index = new Map()

  function indexGroup(group) {
    console.log(`[buildConfigIndex] indexing group: id=${group.id}, title=${group.title}, elementCode=${group.elementCode}, enabled=${group.enabled}`)
    if (group.id) {
      index.set(group.id, group)
    }
    if (group.elementCode) {
      index.set(group.elementCode, group)
    }
    if (group.title) {
      index.set(group.title, group)
    }
    if (group.children) {
      group.children.forEach(child => indexGroup(child))
    }
  }

  userGroups.forEach(group => indexGroup(group))
  return index
}

/**
 * 合并用户布局配置到分组模型
 * 
 * @param {Array} groups - 分组模型数组
 * @param {Object} userConfig - 用户布局配置
 * @returns {Array} 合并后的分组模型
 */
export function mergeUserLayoutConfig(groups, userConfig) {
  console.log('[mergeUserLayoutConfig] userConfig:', JSON.stringify(userConfig, null, 2))
  if (!userConfig?.enabled || !userConfig?.groups?.length) {
    console.log('[mergeUserLayoutConfig] skipping merge - userConfig not valid')
    return groups
  }

  const configIndex = buildConfigIndex(userConfig.groups)
  console.log('[mergeUserLayoutConfig] configIndex keys:', [...configIndex.keys()])
  const processedIds = new Set()

  function mergeGroup(group, parentId = null) {
    const elementCode = group.elementRef?.code
    const groupId = group.id
    const groupTitle = group.title
    const currentParentId = group.parentId
    const currentPid = currentParentId ?? null

    if (elementCode === '供应链计划') {
      console.log(`[mergeGroup] 供应链计划: currentParentId=${currentParentId}, currentPid=${currentPid}`)
    }

    let userGroupConfig = null

    if (elementCode && configIndex.has(elementCode)) {
      const candidates = [...configIndex.entries()].filter(([key, cfg]) =>
        key === elementCode && cfg.elementCode === elementCode
      )
      console.log(`[mergeGroup] ${groupTitle} elementCode:${elementCode}, currentParentId:${currentParentId}, currentPid:${currentPid}, candidates:${candidates.length}`)
      const matchedCandidate = candidates.find(([key, cfg]) => {
        const cfgParentId = cfg.parentId ?? null
        console.log(`[mergeGroup] checking candidate key:${key}, cfgParentId:${cfgParentId}, currentPid:${currentPid}`)
        if (currentPid === null && cfgParentId === null) {
          console.log(`[mergeGroup] ${groupTitle} matched (both parentId null)`)
          return true
        }
        if (currentPid !== null && cfgParentId === currentPid) {
          console.log(`[mergeGroup] ${groupTitle} matched (parentId same)`)
          return true
        }
        if (currentPid !== null && cfgParentId === null) {
          console.log(`[mergeGroup] ${groupTitle} is lifted (parentId changed from ${currentPid} to null), still applying config`)
          return true
        }
        console.log(`[mergeGroup] ${groupTitle} no match`)
        return false
      })
      if (matchedCandidate) {
        userGroupConfig = matchedCandidate[1]
        console.log(`[mergeGroup] ${groupTitle} matched by elementCode: ${elementCode}, enabled: ${userGroupConfig.enabled}`)
      }
    } else if (groupId && configIndex.has(groupId)) {
      userGroupConfig = configIndex.get(groupId)
      console.log(`[mergeGroup] ${groupTitle} matched by id: ${groupId}, enabled: ${userGroupConfig.enabled}`)
    } else if (groupTitle && configIndex.has(groupTitle)) {
      userGroupConfig = configIndex.get(groupTitle)
      console.log(`[mergeGroup] ${groupTitle} matched by title, enabled: ${userGroupConfig.enabled}`)
    }

    let mergedGroup = { ...group }

    if (userGroupConfig) {
      processedIds.add(userGroupConfig.id || configKey)

      console.log(`[mergeGroup] ${groupTitle} applying userConfig, userConfig.enabled: ${userGroupConfig.enabled}, current layout.enabled: ${group.layout?.enabled}`)

      mergedGroup = {
        ...group,
        layout: {
          ...group.layout,
          direction: userGroupConfig.direction || group.layout.direction,
          visible: userGroupConfig.visible !== false,
          enabled: userGroupConfig.enabled !== false,
          style: {
            ...group.layout.style,
            ...(userGroupConfig.style || {})
          }
        }
      }

      console.log(`[mergeGroup] ${groupTitle} after merge, layout.enabled: ${mergedGroup.layout?.enabled}`)

      if (userGroupConfig.containers && userGroupConfig.containers.length > 0) {
        mergedGroup._userContainers = userGroupConfig.containers
      }

      if (userGroupConfig.directNodes && userGroupConfig.directNodes.length > 0) {
        mergedGroup._userDirectNodes = userGroupConfig.directNodes
      }
    }

    if (mergedGroup.children.length > 0) {
      mergedGroup.children = mergedGroup.children.map(child => mergeGroup(child, mergedGroup.id))
    }

    return mergedGroup
  }

  let result = groups.map(group => mergeGroup(group))

  result = appendCustomGroups(result, userConfig.groups, processedIds)

  return result
}

/**
 * 添加用户自定义分组（不关联架构元素）
 */
function appendCustomGroups(groups, userGroups, processedIds) {
  const customGroups = userGroups.filter(g => 
    !processedIds.has(g.id) && 
    !processedIds.has(g.title) &&
    g.type === 'custom' || !g.elementCode
  )

  if (customGroups.length === 0) {
    return groups
  }

  customGroups.forEach(customGroup => {
    const newGroup = createGroup({
      type: GroupType.LAYOUT,
      title: customGroup.title || '自定义分组',
      layout: {
        direction: customGroup.direction || 'TB',
        visible: customGroup.visible !== false,
        enabled: customGroup.enabled !== false,
        style: customGroup.style || {}
      }
    })

    if (customGroup.containers) {
      newGroup._userContainers = customGroup.containers
    }
    if (customGroup.directNodes) {
      newGroup._userDirectNodes = customGroup.directNodes
    }
    if (customGroup.children) {
      newGroup.children = customGroup.children.map(child => 
        createGroup({
          type: GroupType.LAYOUT,
          title: child.title || '子分组',
          parentId: newGroup.id,
          layout: {
            direction: child.direction || 'TB',
            visible: child.visible !== false,
            enabled: child.enabled !== false,
            style: child.style || {}
          }
        })
      )
    }

    groups.push(newGroup)
  })

  return groups
}

/**
 * 应用用户的节点分配配置
 * 将节点分配到用户指定的分组中
 */
export function applyNodeAssignments(groups, userConfig, nodeIdMap) {
  if (!userConfig?.groups) {
    return groups
  }

  const result = JSON.parse(JSON.stringify(groups))

  function processGroup(group) {
    const userGroup = findUserGroupConfig(userConfig.groups, group)
    
    if (userGroup?.directNodes && userGroup.directNodes.length > 0) {
      const assignedNodeIds = userGroup.directNodes.map(nodeRef => {
        if (typeof nodeRef === 'string') {
          return nodeIdMap.codeToIdMap.get(nodeRef) || 
                 nodeIdMap.nameToIdMap.get(nodeRef) || 
                 nodeRef
        }
        return nodeRef.id || nodeRef.code || nodeRef.name
      }).filter(Boolean)

      group._assignedNodes = assignedNodeIds
    }

    if (userGroup?.containers) {
      group._userContainers = userGroup.containers
    }

    if (group.children) {
      group.children.forEach(child => processGroup(child))
    }
  }

  result.forEach(group => processGroup(group))

  return result
}

function findUserGroupConfig(userGroups, group) {
  for (const userGroup of userGroups) {
    if (userGroup.id === group.id || 
        userGroup.title === group.title ||
        userGroup.elementCode === group.elementRef?.code) {
      return userGroup
    }
    if (userGroup.children) {
      const found = findUserGroupConfig(userGroup.children, group)
      if (found) return found
    }
  }
  return null
}

/**
 * 从用户配置构建独立的分组模型
 * 用于完全自定义的布局
 */
export function buildGroupModelFromUserConfig(userConfig, nodeIdMap) {
  if (!userConfig?.groups?.length) {
    return []
  }

  function convertUserGroup(userGroup, parentId = null) {
    const group = createGroup({
      type: GroupType.LAYOUT,
      title: userGroup.title || '分组',
      parentId,
      layout: {
        direction: userGroup.direction || 'TB',
        visible: userGroup.visible !== false,
        style: userGroup.style || {}
      }
    })

    if (userGroup.directNodes && userGroup.directNodes.length > 0) {
      group._assignedNodes = userGroup.directNodes.map(nodeRef => {
        if (typeof nodeRef === 'string') {
          return nodeIdMap.codeToIdMap.get(nodeRef) || 
                 nodeIdMap.nameToIdMap.get(nodeRef) || 
                 nodeRef
        }
        return nodeRef.id || nodeRef.code || nodeRef.name
      }).filter(Boolean)
    }

    if (userGroup.children && userGroup.children.length > 0) {
      group.children = userGroup.children
        .map(child => convertUserGroup(child, group.id))
        .filter(Boolean)
    }

    return group
  }

  return userConfig.groups.map(g => convertUserGroup(g))
}

/**
 * 将分组模型转换为用户配置格式
 * 用于保存用户的布局配置
 */
export function groupModelToUserConfig(groups) {
  function convertGroup(group) {
    const config = {
      id: group.id,
      title: group.title,
      direction: group.layout.direction,
      visible: group.layout.visible,
      enabled: group.layout.enabled,
      style: group.layout.style
    }

    if (group.elementRef) {
      config.elementCode = group.elementRef.code
      config.elementType = group.elementRef.type
    }

    if (group._assignedNodes && group._assignedNodes.length > 0) {
      config.directNodes = group._assignedNodes
    }

    if (group.children && group.children.length > 0) {
      config.children = group.children.map(convertGroup)
    }

    return config
  }

  return {
    enabled: true,
    overallDirection: 'TB',
    groups: groups.map(convertGroup)
  }
}
