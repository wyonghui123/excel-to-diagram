/**
 * 生成基于分组的布局代码
 * @param {Array} groups - 分组配置数组
 * @param {Array} containers - 容器数组（完整数据，包含 nodes）
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {string} overallDirection - 整体方向 ('TB' | 'LR' | 'BT' | 'RL')
 * @param {string} layoutEngine - 布局引擎 ('dagre' | 'elk')
 * @param {Array} links - 所有连线数据（用于 ELK 自动分组）
 * @returns {Object} { mermaidCode, styleLines }
 */
import { MAX_RECURSION_DEPTH, checkDepth, checkCycle, createVisitedSet } from '../../../services/groupModel/safetyUtils.js'
import { formatContainerTitle } from '../../../utils/formatContainerTitle.js'

const LEVEL_STYLES = {
  1: { fill: '#f5f5f5', stroke: '#333333', strokeWidth: 1 },
  2: { fill: '#ffffff', stroke: '#333333', strokeWidth: 1 },
  3: { fill: '#f5f5f5', stroke: '#333333', strokeWidth: 1 },
  4: { fill: '#ffffff', stroke: '#333333', strokeWidth: 1 },
}

function getLevelStyle(level) {
  return LEVEL_STYLES[Math.min(level, 4)] || LEVEL_STYLES[4]
}

const getContainerLevelStyle = getLevelStyle
const getGroupLevelStyle = getLevelStyle

export function generateGroupedLayout(groups, containers, nodeMap, definedNodes, overallDirection = 'TB', layoutEngine = 'dagre', links = []) {
  if (!groups || groups.length === 0) {
    return { mermaidCode: '', styleLines: [] }
  }

  const styleLines = []
  let mermaidCode = '\n%% 分组布局\n'

  const reversedGroups = [...groups].reverse()

  reversedGroups.forEach((group, index) => {
    const groupIndex = index + 1
    
    const result = generateGroupCode(group, containers, nodeMap, definedNodes, 0, groupIndex, createVisitedSet(), layoutEngine, links, 0)
    if (result.code) {
      mermaidCode += result.code
      styleLines.push(...result.styleLines)
    }
  })

  return { mermaidCode, styleLines }
}

/**
 * 检查分组是否有内容
 */
function hasGroupContent(group, containers, visited = null, depth = 0) {
  if (!group) {
    return false
  }
  
  // 对于 disabled 的分组，不显示（返回 false）
  // 但如果分组有 disabled 祖先路径（_disabledAncestorPath），说明它是被提升的，应该显示
  if (group.enabled === false) {
    if (group._disabledAncestorPath && group._disabledAncestorPath.length > 0) {
    } else {
      return false
    }
  }

  const groupEnabled = group.enabled !== false
  
  if (!checkDepth(depth, 'GroupLayout.hasGroupContent')) {
    return false
  }
  
  if (!visited) {
    visited = createVisitedSet()
  }
  
  if (group.id && checkCycle(group.id, visited, 'GroupLayout.hasGroupContent')) {
    return false
  }

  if (group.directNodes && group.directNodes.length > 0) {
    return true
  }

  if (group.containers && group.containers.length > 0) {
    const hasValidContainers = group.containers.some((containerData, idx) => {
      // 跳过 disabled 的容器
      const containerEnabled = containerData?.enabled !== false
      if (containerData?.enabled === false) {
        return false
      }
      if (typeof containerData === 'object' && containerData !== null) {
        if (containerData.nodes && containerData.nodes.length > 0) {
          return true
        }
        if (containerData.id || containerData.name || containerData.fullTitle) {
          return true
        }
      }
      const container = resolveContainer(containerData, containers)
      const result = container && container.nodes && container.nodes.length > 0
      return result
    })
    if (hasValidContainers) {
      return true
    }
  }

  if (group.children && group.children.length > 0) {
    const hasChildren = group.children.some((childId, idx) => {
      // childId 可能是字符串 ID 或分组对象
      const child = typeof childId === 'string' ? null : childId  // 字符串 ID 无法解析，暂时返回 false
      if (!child) {
        return false
      }
      return hasGroupContent(child, containers, visited, depth + 1)
    })
    if (hasChildren) {
      return true
    }
  }

  return false
}

/**
 * 生成单个分组的代码
 * @param {string} layoutEngine - 布局引擎 ('dagre' | 'elk')
 * @param {Array} links - 所有连线数据
 * @param {number} containerDepth - 容器嵌套层次（基于实际创建的 subgraph）
 */
function generateGroupCode(group, containers, nodeMap, definedNodes, depth = 0, groupIndex = 1, visited = null, layoutEngine = 'dagre', links = [], containerDepth = 0) {
  const styleLines = []
  let code = ''

  console.log(`[generateGroupCode] depth=${depth}, group:`, {
    id: group?.id,
    type: group?.type,
    title: group?.title,
    containersCount: group?.containers?.length || 0,
    childrenCount: group?.children?.length || 0
  })

  if (!group) {
    console.log('[generateGroupCode] No group, returning empty')
    return { code, styleLines }
  }

  if (!checkDepth(depth, 'GroupLayout.generateGroupCode')) {
    console.log('[generateGroupCode] Max depth reached, returning empty')
    return { code, styleLines }
  }

  if (!visited) {
    visited = createVisitedSet()
  }

  if (group.id && checkCycle(group.id, visited, 'GroupLayout.generateGroupCode')) {
    console.log('[generateGroupCode] Cycle detected, returning empty')
    return { code, styleLines }
  }

  const hasContent = hasGroupContent(group, containers)
  console.log(`[generateGroupCode] hasGroupContent result: ${hasContent}`)
  
  if (!hasContent && !group.directNodes) {
    console.log('[generateGroupCode] No content and no directNodes, returning empty')
    return { code, styleLines }
  }

  const indent = '  '.repeat(depth)
  // 保留 Unicode 字符（包括中文），只替换特殊字符
  const safeId = group.id.replace(/[^\w\u4e00-\u9fff]/g, '_')
  const groupId = `G_${safeId}`
  const groupTitle = formatContainerTitle(group.title || 'Group')
  const groupEnabled = group.enabled !== false

  if (!groupEnabled) {
    // 禁用的分组：不再创建 subgraph，直接渲染子元素到当前层级
    // 这样 ELK 布局时不会把它们当作一个分组容器来计算间距

    if (group.directNodes && group.directNodes.length > 0 && nodeMap && nodeMap.size > 0) {
      const reversedNodes = [...group.directNodes].reverse()
      reversedNodes.forEach(nodeId => {
        const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
        if (!definedNodes.has(actualNodeId)) {
          const node = nodeMap.get(actualNodeId)
          if (node) {
            const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
            code += `${indent}${actualNodeId}["${displayText}"]\n`
            definedNodes.add(actualNodeId)
          }
        }
      })
    }

    if (group.containers && group.containers.length > 0) {
      const reversedContainers = [...group.containers].reverse()
      reversedContainers.forEach((containerData, idx) => {
        if (containerData._isDirectNodesContainer) {
          if (containerData.nodes && containerData.nodes.length > 0) {
            containerData.nodes.forEach(nodeId => {
              const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
              if (!definedNodes.has(actualNodeId)) {
                const node = nodeMap.get(actualNodeId)
                if (node) {
                  const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
                  code += `${indent}${actualNodeId}["${displayText}"]\n`
                  definedNodes.add(actualNodeId)
                }
              }
            })
          }
          return
        }

        const container = resolveContainer(containerData, containers)
        if (!container) {
          return
        }
        if (container && container.nodes && container.nodes.length > 0) {
          const containerEnabled = container.enabled !== false
          if (containerEnabled) {
            const containerId = `${groupId}_C${idx + 1}`
            const containerCode = generateContainerCode(container, idx, nodeMap, definedNodes, indent, containerId, layoutEngine, links, containerDepth + 1)
            code += containerCode
          } else {
            container.nodes.forEach(nodeId => {
              const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
              if (!definedNodes.has(actualNodeId)) {
                const node = nodeMap.get(actualNodeId)
                if (node) {
                  const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
                  code += `${indent}${actualNodeId}["${displayText}"]\n`
                  definedNodes.add(actualNodeId)
                }
              }
            })
          }
        }
      })
    }

    if (group.children && group.children.length > 0) {
      const reversedChildren = [...group.children].reverse()
      let childGroupIndex = groupIndex * 10
      reversedChildren.forEach((childGroup) => {
        childGroupIndex++
        const childResult = generateGroupCode(childGroup, containers, nodeMap, definedNodes, depth, childGroupIndex, visited, layoutEngine, links, containerDepth)
        if (childResult.code) {
          code += childResult.code
          styleLines.push(...childResult.styleLines)
        }
      })
    }

    return { code, styleLines }
  }

  if (group.visible === false) {
    code += `${indent}subgraph ${groupId}[ ]\n`
  } else {
    code += `${indent}subgraph ${groupId}["${groupTitle}"]\n`
  }

  let direction = group.direction || 'TB'
  code += `${indent}direction ${direction}\n`

  const isVisible = group.visible !== false
  const nextContainerDepth = isVisible ? containerDepth + 1 : containerDepth

  if (group.directNodes && group.directNodes.length > 0 && nodeMap && nodeMap.size > 0) {
    const reversedNodes = [...group.directNodes].reverse()
    reversedNodes.forEach(nodeId => {
      const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
      if (!definedNodes.has(actualNodeId)) {
        const node = nodeMap.get(actualNodeId)
        if (node) {
          const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
          code += `${indent}  ${actualNodeId}["${displayText}"]\n`
          definedNodes.add(actualNodeId)
        }
      }
    })
  }

  if (group.containers && group.containers.length > 0) {
    const reversedContainers = [...group.containers].reverse()
    const containerCodes = []
    const containerNodePairs = [] // 保存每个容器的(第一个节点ID, 最后一个节点ID)

    reversedContainers.forEach((containerData, idx) => {
      if (containerData._isDirectNodesContainer) {
        if (containerData.nodes && containerData.nodes.length > 0) {
          let firstNode = null
          let lastNode = null
          containerData.nodes.forEach(nodeId => {
            const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
            if (!firstNode) firstNode = actualNodeId
            lastNode = actualNodeId
            if (!definedNodes.has(actualNodeId)) {
              const node = nodeMap.get(actualNodeId)
              if (node) {
                const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
                code += `${indent}  ${actualNodeId}["${displayText}"]\n`
                definedNodes.add(actualNodeId)
              }
            }
          })
          if (firstNode && lastNode) {
            containerNodePairs.push({ first: firstNode, last: lastNode })
          }
        }
        return
      }

      const container = resolveContainer(containerData, containers)
      if (container && container.nodes && container.nodes.length > 0) {
        // [v32 修复 2026-06-13] 跳过 disabled 容器, 与 disabled group 分支行为一致
        if (container.enabled === false) {
          // disabled 容器: 不创建 subgraph, 仅外提节点
          container.nodes.forEach(nodeId => {
            const actualNodeId = typeof nodeId === 'object' ? (nodeId.id || nodeId.code || nodeId.name) : nodeId
            if (!definedNodes.has(actualNodeId)) {
              const node = nodeMap.get(actualNodeId)
              if (node) {
                const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
                code += `${indent}  ${actualNodeId}["${displayText}"]\n`
                definedNodes.add(actualNodeId)
              }
            }
          })
          return
        }
        const containerId = `G${groupIndex}_C${idx + 1}`
        const containerCode = generateContainerCode(container, idx, nodeMap, definedNodes, indent, containerId, layoutEngine, links, nextContainerDepth + 1)
        containerCodes.push(containerCode)

        // 收集容器内的第一个和最后一个节点ID
        const firstNodeId = container.nodes[0]
        const firstNodeIdStr = typeof firstNodeId === 'string' ? firstNodeId : (firstNodeId.id || firstNodeId.code || firstNodeId.name)
        const lastNodeId = container.nodes[container.nodes.length - 1]
        const lastNodeIdStr = typeof lastNodeId === 'string' ? lastNodeId : (lastNodeId.id || lastNodeId.code || lastNodeId.name)
        containerNodePairs.push({ first: firstNodeIdStr, last: lastNodeIdStr })
      }
    })

    containerCodes.forEach(cc => {
      code += cc
    })
  }

  if (group.children && group.children.length > 0) {
    const reversedChildren = [...group.children].reverse()
    let childGroupIndex = groupIndex * 10
    reversedChildren.forEach((childGroup) => {
      childGroupIndex++
      const childResult = generateGroupCode(childGroup, containers, nodeMap, definedNodes, depth + 1, childGroupIndex, visited, layoutEngine, links, nextContainerDepth)
      if (childResult.code) {
        code += childResult.code
        styleLines.push(...childResult.styleLines)
      }
    })
  }

  code += `${indent}end\n`

  const styleCode = generateGroupStyle(group, groupId, nextContainerDepth)
  styleLines.push(styleCode)

  return { code, styleLines }
}

/**
 * 解析容器数据
 */
function resolveContainer(containerData, containers) {
  if (typeof containerData === 'object' && containerData !== null) {
    if (containerData.nodes && containerData.nodes.length > 0) {
      return containerData
    }

    if (!containers || containers.length === 0) {
      return null
    }

    const found = containers.find(c => {
      const match = c.id === containerData.id ||
             (containerData.elementCode && c.elementCode === containerData.elementCode) ||
             c.name === containerData.name ||
             c.fullTitle === containerData.fullTitle ||
             (containerData.code && c.elementCode === containerData.code) ||
             (containerData.elementCode && c.code === containerData.elementCode)
      return match
    })
    
    if (found) {
      const result = { ...found }
      if (containerData.direction) {
        result.direction = containerData.direction
      }
      return result
    }
    return null
  }

  if (!containers || containers.length === 0) {
    return null
  }

  if (typeof containerData === 'number') {
    return containers[containerData] || null
  }

  if (typeof containerData === 'string') {
    return containers.find(c => c.id === containerData || c.name === containerData) || null
  }

  return null
}

/**
 * 生成容器 subgraph 代码
 * @param {Object} container - 容器对象
 * @param {number} index - 容器索引
 * @param {Map} nodeMap - 节点映射
 * @param {Set} definedNodes - 已定义节点集合
 * @param {string} indent - 缩进
 * @param {string} containerId - 容器ID
 * @param {string} layoutEngine - 布局引擎
 * @param {Array} links - 所有连线数据
 * @param {number} containerDepth - 容器嵌套层次
 */
function generateContainerCode(container, index, nodeMap, definedNodes, indent = '', containerId = null, layoutEngine = 'dagre', links = [], containerDepth = 1) {
  let code = ''

  // 虚拟容器直接渲染节点，不创建 subgraph
  if (container.isVirtual) {
    if (container.nodes && container.nodes.length > 0 && nodeMap && nodeMap.size > 0) {
      container.nodes.forEach(nodeData => {
        const nodeId = typeof nodeData === 'string' ? nodeData : (nodeData.id || nodeData.code || nodeData.name)
        if (definedNodes && !definedNodes.has(nodeId)) {
          const node = nodeMap.get(nodeId)
          if (node) {
            const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
            code += `${indent}${nodeId}["${displayText}"]\n`
            definedNodes.add(nodeId)
          }
        } else if (definedNodes) {
          code += `${indent}${nodeId}\n`
        }
      })
    }
    return code
  }

  const actualContainerId = containerId || `C${index + 1}`
  // 如果容器有 fullTitle（包含完整路径，如 "财务云 / 费控服务"），说明它是 disabled 域的容器
  // 使用 fullTitle 而不是 name，这样会显示完整路径
  const rawContainerName = container.fullTitle || container.name || container.title || 'Container'
  const containerName = formatContainerTitle(rawContainerName)
  
  code += `${indent}  subgraph ${actualContainerId}["${containerName}"]\n`

  // 注意：当容器内节点有外部连线时，此 direction 设置会被 ELK 忽略
  // 容器会继承父图的方向。这是 Mermaid + ELK 的已知限制。
  const containerDirection = container.direction || 'LR'
  code += `${indent}    direction ${containerDirection}\n`

  // 收集此容器中的有效节点ID
  const containerNodeIds = []
  if (container.nodes && container.nodes.length > 0 && nodeMap && nodeMap.size > 0) {
    container.nodes.forEach(nodeData => {
      const nodeId = typeof nodeData === 'string' ? nodeData : (nodeData.id || nodeData.code || nodeData.name)
      containerNodeIds.push(nodeId)
    })
  }

  // ELK 自动分组：将有/无外部连线的节点分离
  if (layoutEngine === 'elk' && links && links.length > 0 && containerNodeIds.length > 1) {
    const containerNodeSet = new Set(containerNodeIds)
    const nodesWithExternalLinks = new Set()
    
    for (const link of links) {
      const sourceInContainer = containerNodeSet.has(link.source)
      const targetInContainer = containerNodeSet.has(link.target)
      
      // 如果只有一个端点在当前容器，则该节点有外部连线
      if (sourceInContainer && !targetInContainer) {
        nodesWithExternalLinks.add(link.source)
      }
      if (targetInContainer && !sourceInContainer) {
        nodesWithExternalLinks.add(link.target)
      }
    }

    const innerNodes = containerNodeIds.filter(n => !nodesWithExternalLinks.has(n))
    const boundaryNodes = containerNodeIds.filter(n => nodesWithExternalLinks.has(n))

    // 只有当两组都有节点时才分离
    if (innerNodes.length > 0 && boundaryNodes.length > 0) {
      // 生成内部节点子容器（无外部连线，方向会被尊重）
      code += `${indent}    subgraph ${actualContainerId}_inner[" "]\n`
      code += `${indent}      direction ${containerDirection}\n`
      innerNodes.forEach(nodeId => {
        if (definedNodes && !definedNodes.has(nodeId)) {
          const node = nodeMap.get(nodeId)
          if (node) {
            const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
            code += `${indent}      ${nodeId}["${displayText}"]\n`
            definedNodes.add(nodeId)
          }
        } else if (definedNodes) {
          code += `${indent}      ${nodeId}\n`
        }
      })
      code += `${indent}    end\n`
      code += `${indent}    style ${actualContainerId}_inner fill:none,stroke:none\n`

      // 生成边界节点子容器（有外部连线）
      code += `${indent}    subgraph ${actualContainerId}_boundary[" "]\n`
      code += `${indent}      direction ${containerDirection}\n`
      boundaryNodes.forEach(nodeId => {
        if (definedNodes && !definedNodes.has(nodeId)) {
          const node = nodeMap.get(nodeId)
          if (node) {
            const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
            code += `${indent}      ${nodeId}["${displayText}"]\n`
            definedNodes.add(nodeId)
          }
        } else if (definedNodes) {
          code += `${indent}      ${nodeId}\n`
        }
      })
      code += `${indent}    end\n`
      code += `${indent}    style ${actualContainerId}_boundary fill:none,stroke:none\n`

      code += `${indent}  end\n`
      return code
    }
  }

  // 默认处理：不分离节点
  if (containerNodeIds.length > 0) {
    const reversedNodes = [...containerNodeIds].reverse()
    reversedNodes.forEach(nodeId => {
      if (definedNodes && !definedNodes.has(nodeId)) {
        const node = nodeMap.get(nodeId)
        if (node) {
          const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
          code += `${indent}    ${nodeId}["${displayText}"]\n`
          definedNodes.add(nodeId)
        }
      } else if (definedNodes) {
        code += `${indent}    ${nodeId}\n`
      }
    })
  }

  code += `${indent}  end\n`

  const levelStyle = getContainerLevelStyle(containerDepth)
  code += `${indent}  style ${actualContainerId} fill:${levelStyle.fill},stroke:${levelStyle.stroke},stroke-width:${levelStyle.strokeWidth}\n`

  return code
}

/**
 * 生成分组样式代码
 * @param {Object} group - 分组对象
 * @param {string} groupId - 分组ID
 * @param {number} containerDepth - 容器嵌套层次
 */
function generateGroupStyle(group, groupId, containerDepth = 1) {
  if (!group.visible) {
    return `style ${groupId} fill:none,stroke:none\n`
  }

  const levelStyle = getGroupLevelStyle(containerDepth)
  const fill = levelStyle.fill
  const stroke = levelStyle.stroke
  const strokeWidth = levelStyle.strokeWidth

  return `style ${groupId} fill:${fill},stroke:${stroke},stroke-width:${strokeWidth}\n`
}
