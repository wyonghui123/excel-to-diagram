/**
 * 生成基于分组的布局代码
 * @param {Array} groups - 分组配置数组
 * @param {Array} containers - 容器数组（完整数据，包含 nodes）
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {string} overallDirection - 整体方向 ('TB' | 'LR' | 'BT' | 'RL')
 * @returns {Object} { mermaidCode, styleLines }
 */
export function generateGroupedLayout(groups, containers, nodeMap, definedNodes, overallDirection = 'TB') {
  console.log('[generateGroupedLayout] called with:', {
    groupsCount: groups?.length,
    containersCount: containers?.length,
    nodeMapSize: nodeMap?.size,
    overallDirection
  })

  if (!groups || groups.length === 0) {
    console.log('[generateGroupedLayout] No groups, returning empty')
    return { mermaidCode: '', styleLines: [] }
  }

  const styleLines = []
  let mermaidCode = '\n%% 分组布局\n'

  /**
   * 分组顺序说明（重要！请勿修改）
   * 
   * Mermaid 渲染时，后定义的 subgraph 会出现在布局的前面位置（上/左）。
   * 例如：先定义分组1，再定义分组2，渲染结果是分组2在上/左，分组1在下/右。
   * 
   * 为了让用户看到的顺序与配置顺序一致（分组1在上/左，分组2在下/右），
   * 需要反转分组生成顺序。
   * 
   * 注意：根据测试结果，分组顺序受连线方向影响，这里的反转可能无法完全控制顺序。
   * 但整体方向（TB/LR）仍然有效，影响分组之间的排列方式。
   */
  console.log('[generateGroupedLayout] Original groups order:', groups.map(g => g.title))
  console.log('[generateGroupedLayout] Overall direction:', overallDirection, '(TB=垂直排列, LR=水平排列)')
  
  const reversedGroups = [...groups].reverse()
  console.log('[generateGroupedLayout] Reversed groups order:', reversedGroups.map(g => g.title))
  
  reversedGroups.forEach((group, index) => {
    console.log(`[generateGroupedLayout] Processing group ${index}:`, group.title, 'containers:', group.containers, 'children:', group.children?.length)
    const result = generateGroupCode(group, containers, nodeMap, definedNodes, 0)
    console.log(`[generateGroupedLayout] Group ${index} result:`, result.code ? 'has code' : 'no code')
    if (result.code) {
      mermaidCode += result.code
      styleLines.push(...result.styleLines)
    }
  })

  console.log('[generateGroupedLayout] Generated code length:', mermaidCode.length)
  return { mermaidCode, styleLines }
}

/**
 * 检查分组是否有内容
 * @param {Object} group - 分组配置
 * @param {Array} containers - 容器数组
 * @returns {boolean} - 是否有内容
 */
function hasGroupContent(group, containers) {
  if (!group) {
    console.log('[hasGroupContent] Group is null')
    return false
  }
  
  console.log(`[hasGroupContent] Checking group "${group.title}" containers:`, group.containers)
  
  if (group.containers && group.containers.length > 0) {
    const hasValidContainers = group.containers.some(containerData => {
      const container = resolveContainer(containerData, containers)
      const isValid = container && container.nodes && container.nodes.length > 0
      console.log(`[hasGroupContent] Container "${typeof containerData === 'object' ? containerData.name : containerData}" valid:`, isValid)
      return isValid
    })
    console.log(`[hasGroupContent] Group "${group.title}" hasValidContainers:`, hasValidContainers)
    if (hasValidContainers) return true
  }
  
  if (group.children && group.children.length > 0) {
    const hasChildren = group.children.some(child => hasGroupContent(child, containers))
    console.log(`[hasGroupContent] Group "${group.title}" hasChildren:`, hasChildren)
    return hasChildren
  }
  
  console.log(`[hasGroupContent] Group "${group.title}" has no content`)
  return false
}

/**
 * 生成单个分组的代码
 * @param {Object} group - 分组配置
 * @param {Array} containers - 容器数组
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {number} depth - 当前深度
 * @returns {Object} { code, styleLines }
 */
function generateGroupCode(group, containers, nodeMap, definedNodes, depth = 0) {
  const styleLines = []
  let code = ''

  if (!group) {
    return { code, styleLines }
  }

  if (!hasGroupContent(group, containers)) {
    console.log(`[generateGroupCode] Group "${group.title}" has no content, skipping`)
    return { code, styleLines }
  }

  const indent = '  '.repeat(depth)
  const groupId = `G_${group.id.replace(/[^a-zA-Z0-9]/g, '_')}`
  const groupTitle = group.title || 'Group'

  code += `${indent}subgraph ${groupId}["${groupTitle}"]\n`

  /**
   * 方向映射说明（重要！请勿修改）
   * 
   * Mermaid 的 subgraph direction 与用户直觉是相反的：
   * - 用户选择 "TB"（从上到下），期望子元素垂直排列，但 Mermaid 的 direction TB 
   *   实际上是控制 subgraph 边框的延伸方向，而非内部元素的排列方向
   * - 要让元素垂直排列，需要设置 direction LR（让边框水平延伸，元素自然垂直排列）
   * - 要让元素水平排列，需要设置 direction TB（让边框垂直延伸，元素自然水平排列）
   * 
   * 因此需要反向映射：
   * - 用户选择 TB -> 实际使用 LR
   * - 用户选择 LR -> 实际使用 TB
   * 
   * 这是经过测试验证的正确行为，请勿"修复"此映射！
   * 参考测试文件：test-mermaid-direction.html
   */
  const directionMap = {
    TB: 'LR',
    BT: 'RL',
    LR: 'TB',
    RL: 'BT'
  }
  console.log(`[generateGroupCode] Group "${groupTitle}" direction input:`, group.direction, 'mapped to:', directionMap[group.direction] || 'LR')
  const direction = directionMap[group.direction] || 'LR'
  code += `direction ${direction}\n`

  console.log(`[generateGroupCode] Group "${groupTitle}" containers:`, group.containers?.length, group.containers?.map(c => c.id || c.name || c))
  if (group.containers && group.containers.length > 0) {
    /**
     * 容器顺序说明：与分组顺序相同，需要反转以保持用户配置顺序
     */
    const reversedContainers = [...group.containers].reverse()
    reversedContainers.forEach((containerData, idx) => {
      console.log(`[generateGroupCode] Processing container ${idx}:`, containerData, 'direction:', containerData?.direction)
      const container = resolveContainer(containerData, containers)
      console.log(`[generateGroupCode] Resolved container ${idx}:`, container?.name, 'direction:', container?.direction, 'nodes:', container?.nodes?.length)
      if (container && container.nodes && container.nodes.length > 0) {
        const containerCode = generateContainerCode(container, idx, nodeMap, definedNodes, indent)
        code += containerCode
      } else {
        console.warn(`[generateGroupCode] Container not found or has no nodes:`, containerData)
      }
    })
  }

  if (group.children && group.children.length > 0) {
    /**
     * 子分组顺序说明：与分组顺序相同，需要反转以保持用户配置顺序
     */
    const reversedChildren = [...group.children].reverse()
    reversedChildren.forEach((childGroup) => {
      const childResult = generateGroupCode(childGroup, containers, nodeMap, definedNodes, depth + 1)
      if (childResult.code) {
        code += childResult.code
        styleLines.push(...childResult.styleLines)
      }
    })
  }

  code += `${indent}end\n`

  const styleCode = generateGroupStyle(group, groupId)
  styleLines.push(styleCode)

  return { code, styleLines }
}

/**
 * 解析容器数据
 * @param {Object|number|string} containerData - 容器数据（可能是对象、索引或ID）
 * @param {Array} containers - 完整容器数组
 * @returns {Object|null} - 完整容器对象
 */
function resolveContainer(containerData, containers) {
  console.log('[resolveContainer] Input:', {
    containerData: containerData,
    containerDataKeys: typeof containerData === 'object' ? Object.keys(containerData) : null,
    containersCount: containers?.length
  })
  
  if (!containers || containers.length === 0) {
    console.log('[resolveContainer] No containers available')
    return null
  }

  if (typeof containerData === 'object' && containerData !== null) {
    console.log('[resolveContainer] containerData is object, nodes:', containerData.nodes?.length, 'direction:', containerData.direction)
    if (containerData.nodes && containerData.nodes.length > 0) {
      console.log('[resolveContainer] Container already has nodes, returning as-is with direction:', containerData.direction)
      return containerData
    }
    
    console.log('[resolveContainer] Searching for container by id/name/fullTitle:', containerData.id, containerData.name, containerData.fullTitle)
    console.log('[resolveContainer] Available containers:', containers.map(c => ({ id: c.id, name: c.name, fullTitle: c.fullTitle, nodesCount: c.nodes?.length })))
    
    const found = containers.find(c => {
      const match = c.id === containerData.id || 
        c.name === containerData.name ||
        c.fullTitle === containerData.fullTitle
      if (match) {
        console.log('[resolveContainer] Found match:', c.name, 'nodes:', c.nodes?.length)
      }
      return match
    })
    console.log('[resolveContainer] Final found:', found?.name, 'nodes:', found?.nodes?.length)
    if (found) {
      const result = { ...found }
      if (containerData.direction) {
        result.direction = containerData.direction
      }
      console.log('[resolveContainer] Returning with direction:', result.direction)
      return result
    }
    return null
  }
  
  if (typeof containerData === 'number') {
    const found = containers[containerData]
    console.log('[resolveContainer] Found container by index:', containerData, found?.name, 'nodes:', found?.nodes?.length)
    return found || null
  }
  
  if (typeof containerData === 'string') {
    const found = containers.find(c => c.id === containerData || c.name === containerData)
    console.log('[resolveContainer] Found container by string:', containerData, found?.name, 'nodes:', found?.nodes?.length)
    return found || null
  }
  
  console.log('[resolveContainer] Could not resolve container')
  return null
}

/**
 * 生成容器 subgraph 代码
 * @param {Object} container - 容器对象
 * @param {number} index - 容器索引
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {string} indent - 缩进字符串
 * @returns {string} mermaid 代码
 */
function generateContainerCode(container, index, nodeMap, definedNodes, indent = '') {
  let code = ''

  const containerId = `C${index + 1}_${Date.now().toString(36)}`
  const containerName = container.fullTitle || container.name || 'Container'

  code += `${indent}  subgraph ${containerId}["${containerName}"]\n`

  /**
   * 方向映射说明（重要！请勿修改）
   * 与分组方向映射相同，Mermaid 的 subgraph direction 与用户直觉相反。
   * 详见上方 generateGroupCode 函数中的注释说明。
   */
  const directionMap = {
    TB: 'LR',
    BT: 'RL',
    LR: 'TB',
    RL: 'BT'
  }
  const containerDirection = container.direction || 'LR'
  const actualDirection = directionMap[containerDirection] || 'TB'
  console.log(`[generateContainerCode] Container "${containerName}" direction: ${containerDirection} -> ${actualDirection}`)
  code += `${indent}    direction ${actualDirection}\n`

  if (container.nodes && container.nodes.length > 0 && nodeMap) {
    /**
     * 节点顺序说明：与分组顺序相同，需要反转以保持用户配置顺序
     */
    const reversedNodes = [...container.nodes].reverse()
    reversedNodes.forEach(nodeId => {
      const node = nodeMap.get(nodeId)
      if (node) {
        if (definedNodes && !definedNodes.has(node.id)) {
          const nodeLabel = `${node.name}\\n(${node.code})`
          code += `${indent}    ${nodeId}["${nodeLabel}"]:::node\n`
          definedNodes.add(node.id)
        } else {
          code += `${indent}    ${nodeId}\n`
        }
      }
    })
  }

  code += `${indent}  end\n`

  return code
}

/**
 * 生成分组样式代码
 * @param {Object} group - 分组配置
 * @param {string} groupId - 分组 ID
 * @returns {string} 样式代码
 */
function generateGroupStyle(group, groupId) {
  if (!group.visible) {
    return `style ${groupId} fill:none,stroke:none\n`
  }

  const style = group.style || {}
  const fill = style.fill || '#f5f5f5'
  const stroke = style.stroke || '#333333'
  const strokeWidth = style.strokeWidth !== undefined ? style.strokeWidth : 1
  const strokeDasharray = style.strokeDasharray || ''

  let styleCode = `style ${groupId} fill:${fill},stroke:${stroke},stroke-width:${strokeWidth}px`

  if (strokeDasharray) {
    styleCode += `,stroke-dasharray:${strokeDasharray}`
  }
  
  styleCode += '\n'

  return styleCode
}
