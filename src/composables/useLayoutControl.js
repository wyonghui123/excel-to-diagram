import { reactive, computed } from 'vue'

const layoutControlConfig = reactive({
  enabled: false,
  overallDirection: 'TB',
  groups: [],
  engine: 'dagre',
  preserveOrder: true
})

function generateGroupId() {
  return `group_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
}

function getDefaultGroupStyle() {
  return {
    fill: '#f5f5f5',
    stroke: '#333333',
    strokeWidth: 1,
    strokeDasharray: ''
  }
}

function getDefaultGroup(title, parentId) {
  return {
    id: generateGroupId(),
    title,
    direction: 'TB',
    visible: true,
    style: getDefaultGroupStyle(),
    containers: [],
    children: [],
    parentId
  }
}

function findGroupById(groups, id) {
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

function findParentGroup(groups, childId) {
  for (const group of groups) {
    if (group.children.some(child => child.id === childId)) {
      return group
    }
    const found = findParentGroup(group.children, childId)
    if (found) {
      return found
    }
  }
  return null
}

function getGroupDepth(id) {
  const group = getGroupById(id)
  if (!group) {
    return 0
  }
  let depth = 1
  let currentGroup = group
  while (currentGroup.parentId) {
    depth++
    currentGroup = getGroupById(currentGroup.parentId)
    if (!currentGroup) {
      break
    }
  }
  return depth
}

function canCreateChildGroup(parentId) {
  const parentDepth = getGroupDepth(parentId)
  return parentDepth < 3
}

function createGroup(title, parentId) {
  const newGroup = getDefaultGroup(title, parentId)
  
  if (parentId) {
    if (!canCreateChildGroup(parentId)) {
      console.warn('Cannot create child group: maximum depth of 3 levels reached')
      return newGroup
    }
    const parentGroup = findGroupById(layoutControlConfig.groups, parentId)
    if (parentGroup) {
      parentGroup.children.push(newGroup)
    } else {
      layoutControlConfig.groups.push(newGroup)
    }
  } else {
    layoutControlConfig.groups.push(newGroup)
  }
  
  return newGroup
}

function updateGroup(id, updates) {
  const group = findGroupById(layoutControlConfig.groups, id)
  if (!group) {
    return false
  }
  
  const { id: _, children: __, parentId: ___, ...safeUpdates } = updates
  
  Object.assign(group, safeUpdates)
  return true
}

function deleteGroupRecursive(groups, id) {
  const index = groups.findIndex(g => g.id === id)
  if (index !== -1) {
    groups.splice(index, 1)
    return true
  }
  
  for (const group of groups) {
    if (deleteGroupRecursive(group.children, id)) {
      return true
    }
  }
  
  return false
}

function deleteGroup(id) {
  return deleteGroupRecursive(layoutControlConfig.groups, id)
}

function getGroupById(id) {
  return findGroupById(layoutControlConfig.groups, id)
}

function assignContainerToGroup(containerIndex, groupId) {
  const group = getGroupById(groupId)
  if (!group) {
    return false
  }
  
  if (!group.containers.includes(containerIndex)) {
    group.containers.push(containerIndex)
  }
  
  return true
}

function removeContainerFromGroup(containerIndex, groupId) {
  const group = getGroupById(groupId)
  if (!group) {
    return false
  }
  
  const index = group.containers.indexOf(containerIndex)
  if (index !== -1) {
    group.containers.splice(index, 1)
    return true
  }
  
  return false
}

function moveContainerBetweenGroups(
  containerIndex,
  fromGroupId,
  toGroupId
) {
  const fromGroup = getGroupById(fromGroupId)
  const toGroup = getGroupById(toGroupId)
  
  if (!fromGroup || !toGroup) {
    return false
  }
  
  const index = fromGroup.containers.indexOf(containerIndex)
  if (index === -1) {
    return false
  }
  
  fromGroup.containers.splice(index, 1)
  
  if (!toGroup.containers.includes(containerIndex)) {
    toGroup.containers.push(containerIndex)
  }
  
  return true
}

function createChildGroup(parentId, title) {
  if (!canCreateChildGroup(parentId)) {
    console.warn('Cannot create child group: maximum depth of 3 levels reached')
    return null
  }
  
  return createGroup(title, parentId)
}

function resetConfig() {
  layoutControlConfig.enabled = false
  layoutControlConfig.overallDirection = 'TB'
  layoutControlConfig.groups = []
  layoutControlConfig.engine = 'dagre'
  layoutControlConfig.preserveOrder = true
}

const enabled = computed(() => layoutControlConfig.enabled)
const groups = computed(() => layoutControlConfig.groups)
const engine = computed(() => layoutControlConfig.engine)
const preserveOrder = computed(() => layoutControlConfig.preserveOrder)

export function useLayoutControl() {
  return {
    layoutControlConfig,
    enabled,
    groups,
    engine,
    preserveOrder,
    generateGroupId,
    getDefaultGroupStyle,
    createGroup,
    updateGroup,
    deleteGroup,
    getGroupById,
    assignContainerToGroup,
    removeContainerFromGroup,
    moveContainerBetweenGroups,
    createChildGroup,
    getGroupDepth,
    canCreateChildGroup,
    resetConfig
  }
}
