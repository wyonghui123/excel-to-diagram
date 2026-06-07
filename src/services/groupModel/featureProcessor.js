/**
 * 分组特性统一处理模块
 * 
 * 设计原则：
 * 1. 所有跨层级的特性在此统一处理
 * 2. 下游模块只需要处理"已标准化"的数据
 * 3. 每个特性有明确的处理时机和处理方式
 */

/**
 * 特性定义
 */
export const GroupFeatures = {
  ENABLED: {
    name: 'enabled',
    description: '控制分组是否生成容器',
    defaultValue: true,
    // 处理时机：在 flatten 阶段
    phase: 'flatten',
    // 处理函数
    handler: handleEnabledFeature
  },
  VISIBLE: {
    name: 'visible',
    description: '控制分组是否可见',
    defaultValue: true,
    phase: 'render',
    handler: handleVisibleFeature
  }
}

/**
 * 统一处理入口
 * 在数据流的特定阶段调用，确保特性被正确处理
 * 
 * @param {Array} groups - 分组数据
 * @param {string} phase - 当前阶段 ('flatten' | 'convert' | 'render')
 * @param {Object} context - 上下文信息
 * @returns {Array} 处理后的分组数据
 */
export function processGroupFeatures(groups, phase, context = {}) {
  if (!groups || groups.length === 0) {
    return groups
  }

  const applicableFeatures = Object.values(GroupFeatures)
    .filter(f => f.phase === phase)

  let processedGroups = groups
  
  applicableFeatures.forEach(feature => {
    processedGroups = feature.handler(processedGroups, context)
  })

  return processedGroups
}

/**
 * enabled 特性处理
 * 在 flatten 阶段处理，将禁用分组的子元素提升
 */
function handleEnabledFeature(groups, context) {
  const { chartType } = context
  
  return groups.flatMap(group => {
    const isEnabled = group.layout?.enabled !== false
    
    if (!isEnabled) {
      // 禁用分组：提升子元素，传递父分组名称
      console.log(`[Feature:enabled] Lifting children from disabled group: ${group.title}`)
      return liftChildren(group, chartType, [group.title])
    }
    
    // 启用分组：保留，递归处理子元素
    return [{
      ...group,
      children: group.children ? handleEnabledFeature(group.children, context) : []
    }]
  })
}

/**
 * 提升子元素
 * @param {Object} group - 被禁用的分组
 * @param {string} chartType - 图表类型
 * @param {Array} ancestorPath - 被禁用的祖先路径
 */
function liftChildren(group, chartType, ancestorPath = []) {
  if (!group.children || group.children.length === 0) {
    return []
  }
  
  return group.children.flatMap(child => {
    const childIsEnabled = child.layout?.enabled !== false
    
    if (!childIsEnabled) {
      // 子元素也被禁用，继续提升，添加到祖先路径
      return liftChildren(child, chartType, [...ancestorPath, child.title])
    }
    
    // 子元素启用，标记为"被提升"，设置祖先路径
    return [{
      ...child,
      _lifted: true,
      _originalParentId: group.id,
      parentId: null,
      _disabledAncestorPath: ancestorPath.length > 0 ? ancestorPath : undefined
    }]
  })
}

/**
 * visible 特性处理
 * 在 render 阶段处理，控制样式
 */
function handleVisibleFeature(groups, context) {
  // visible 特性只影响样式，不改变结构
  return groups.map(group => ({
    ...group,
    _visible: group.layout?.visible !== false,
    children: group.children ? handleVisibleFeature(group.children, context) : []
  }))
}

/**
 * 特性验证
 * 在关键节点验证特性是否被正确处理
 */
export function validateGroupFeatures(groups, phase) {
  const issues = []
  
  function validate(group, path = '') {
    const currentPath = path ? `${path} > ${group.title}` : group.title
    
    // 检查 enabled 特性是否被正确处理
    if (phase === 'convert' || phase === 'render') {
      if (group.layout?.enabled === false && !group._processed) {
        issues.push({
          path: currentPath,
          issue: 'DISABLED_GROUP_NOT_PROCESSED',
          message: `分组 "${group.title}" 已禁用但未被正确处理`
        })
      }
    }
    
    if (group.children) {
      group.children.forEach(child => validate(child, currentPath))
    }
  }
  
  groups.forEach(group => validate(group))
  
  if (issues.length > 0) {
    console.warn('[validateGroupFeatures] Found issues:', issues)
  }
  
  return issues
}
