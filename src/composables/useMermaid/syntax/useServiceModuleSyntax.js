import { getColors, getLinkColor } from './useMermaidColors.js'
import { useBlockDiagramStyle } from '../style/useBlockDiagramStyle.js'
import { useBlockDiagramSyntax, DIAGRAM_TYPES } from './useBlockDiagramSyntax.js'
import { routeLayout, DEPRECATED_LAYOUT_TYPES, isDeprecatedLayout, convertDeprecatedLayout } from '../layouts/index.js'
import { formatContainerTitle } from '../../../utils/formatContainerTitle.js'
import { GroupType } from '../../../services/groupModel/types.js'

/**
 * 为网格布局排序容器，将中心容器放在中间位置
 * @param {Array} containers - 容器数组
 * @param {String} centerSubDomain - 中心子领域ID
 * @returns {Array} - 排序后的容器数组
 */
function sortContainersForGrid(containers, centerSubDomain) {
  if (!containers || !Array.isArray(containers) || containers.length === 0) {
    return []
  }

  if (!centerSubDomain || containers.length <= 1) {
    return [...containers]
  }

  const centerIndex = containers.findIndex(c => c.id === centerSubDomain)
  if (centerIndex === -1) {
    return [...containers]
  }

  const centerContainer = containers[centerIndex]
  const otherContainers = containers.filter((_, i) => i !== centerIndex)

  const count = containers.length
  const cols = Math.ceil(Math.sqrt(count))
  const rows = Math.ceil(count / cols)

  const centerRow = Math.floor(rows / 2)
  const centerCol = Math.floor(cols / 2)
  const centerPos = centerRow * cols + centerCol

  const result = new Array(count)
  result[centerPos] = centerContainer

  let otherIdx = 0
  for (let i = 0; i < count; i++) {
    if (i !== centerPos) {
      result[i] = otherContainers[otherIdx++]
    }
  }

  return result.filter(Boolean)
}

function resolveGroupContainers(layoutControlConfig, realContainers) {
  if (!layoutControlConfig?.groups || !realContainers || realContainers.length === 0) {
    return layoutControlConfig
  }

  const config = { ...layoutControlConfig, groups: [] }

  for (const group of layoutControlConfig.groups) {
    config.groups.push(resolveContainersInGroup(group, realContainers))
  }

  return config
}

function resolveContainersInGroup(group, realContainers) {
  console.log('[resolveContainersInGroup] Processing group:', {
    id: group.id,
    type: group.type,
    name: group.name,
    title: group.title,
    containersCount: group.containers?.length || 0,
    childrenCount: group.children?.length || 0
  })
  
  const resolved = { ...group }

  if (group.containers && group.containers.length > 0) {
    console.log('[resolveContainersInGroup] Group has containers, resolving...')
    resolved.containers = group.containers.map(containerData => {
      console.log('[resolveContainersInGroup] Processing container:', {
        id: containerData?.id,
        name: containerData?.name,
        enabled: containerData?.enabled,
        fullTitle: containerData?.fullTitle
      })
      if (typeof containerData === 'object' && containerData !== null) {
        if (containerData.nodes && containerData.nodes.length > 0) {
          console.log('[resolveContainersInGroup] Container already has nodes:', containerData.id || containerData.name)
          return containerData
        }
        const found = realContainers.find(c =>
          c.id === containerData.id ||
          c.name === containerData.name ||
          c.fullTitle === containerData.fullTitle ||
          (containerData.elementCode && c.id === containerData.elementCode)
        )
        if (found) {
          console.log('[resolveContainersInGroup] Matched container:', containerData.name, '-> found:', found.name, 'nodes:', found.nodes?.length)
          console.log('[resolveContainersInGroup] containerData.fullTitle:', containerData.fullTitle)
          console.log('[resolveContainersInGroup] containerData.enabled:', containerData.enabled)
          const result = { ...found }
          if (containerData.direction) result.direction = containerData.direction
          // 保留原始的 fullTitle（包含禁用路径信息）
          if (containerData.fullTitle) {
            console.log('[resolveContainersInGroup] Preserving fullTitle:', containerData.fullTitle)
            result.fullTitle = containerData.fullTitle
          }
          if (containerData.title && !result.title) {
            result.title = containerData.title
          }
          // 保留原始的 enabled（当容器被禁用时）
          if (containerData.enabled === false) {
            console.log('[resolveContainersInGroup] Preserving enabled=false from containerData')
            result.enabled = false
          }
          console.log('[resolveContainersInGroup] result.fullTitle:', result.fullTitle)
          console.log('[resolveContainersInGroup] result.enabled:', result.enabled)
          return result
        } else {
          console.log('[resolveContainersInGroup] No match found for container:', containerData)
        }
      }
      return containerData
    })
  }

  if (!resolved.containers || resolved.containers.length === 0) {
    console.log('[resolveContainersInGroup] No containers yet, trying to match group against realContainers...')
    console.log('[resolveContainersInGroup] group.name:', group.name, 'group.title:', group.title, 'group.elementCode:', group.elementCode, 'group.type:', group.type)
    console.log('[resolveContainersInGroup] realContainers:', realContainers.map(c => ({ id: c.id, name: c.name })))

    const matchedContainer = realContainers.find(c =>
      c.name === group.name ||
      c.name === group.title ||
      c.id === group.elementCode ||
      c.id === group.name ||
      c.id === group.title
    )

    console.log('[resolveContainersInGroup] matchedContainer:', matchedContainer ? { id: matchedContainer.id, name: matchedContainer.name, nodes: matchedContainer.nodes?.length } : null)

    if (matchedContainer && matchedContainer.nodes && matchedContainer.nodes.length > 0) {
      const groupTitleMatchesContainer = (group.name && group.name === matchedContainer.name) ||
        (group.title && group.title === matchedContainer.name)

      if (groupTitleMatchesContainer) {
        console.log('[resolveContainersInGroup] Group name matches container, using directNodes to avoid nested subgraph')
        resolved.directNodes = matchedContainer.nodes.map(n => typeof n === 'object' ? (n.id || n.code || n.name) : n)
      } else {
        resolved.containers = [{
          ...matchedContainer,
          id: group.id,
          name: group.name || group.title,
          fullTitle: group.fullTitle || group.title
        }]
        console.log('[resolveContainersInGroup] Created container from matched:', resolved.containers[0])
      }
    }
  }
  
  console.log('[resolveContainersInGroup] Final resolved.containers:', resolved.containers?.length || 0)

  if (group.children && group.children.length > 0) {
    resolved.children = group.children.map(child => resolveContainersInGroup(child, realContainers))
  }

  return resolved
}

export function useServiceModuleSyntax() {
  const { getContainerStyle, getLinkStyle, getNodeStyle, generateClassDefs } = useBlockDiagramStyle()
  const { preCalculateNodeSizes, createSimpleNodeMap, generateLinksCode } = useBlockDiagramSyntax()

  const generateMermaidCode = (data, relationDescriptions, layoutEngine = 'dagre', layoutType = 'grouped', positions = [], zoneRowCount = 3, preserveModelOrder = false, layoutControlConfig = null) => {
    if (!data || !data.nodes || !data.links) {
      console.warn('数据不完整:', data)
      return 'graph TD\n  A[No Data]'
    }

    if (!data.containers || !Array.isArray(data.containers)) {
      console.warn('[useServiceModuleSyntax] containers is not array:', data.containers)
      data.containers = []
    }

    preCalculateNodeSizes(data, DIAGRAM_TYPES.SERVICE_MODULE)

    const { nodes, links, containers, centerSubDomain, nodeTextColor, colorScheme } = data

    console.log('[useServiceModuleSyntax] layoutControlConfig parameter:', layoutControlConfig)
    console.log('[useServiceModuleSyntax] layoutControlConfig?.enabled:', layoutControlConfig?.enabled)
    console.log('[useServiceModuleSyntax] layoutControlConfig?.groups?.length:', layoutControlConfig?.groups?.length)
    
    let effectiveLayoutControlConfig = layoutControlConfig

    if (isDeprecatedLayout(layoutType)) {
      console.log('[useServiceModuleSyntax] Converting deprecated layout...')
      const converted = convertDeprecatedLayout(layoutType, containers, { zoneRowCount })
      
      // 只有当 layoutControlConfig 无效时，才使用 convertDeprecatedLayout 的结果
      const hasValidConfig = effectiveLayoutControlConfig && 
                             effectiveLayoutControlConfig.enabled && 
                             effectiveLayoutControlConfig.groups?.length > 0
      
      console.log('[useServiceModuleSyntax] hasValidConfig:', hasValidConfig)
      
      if (!hasValidConfig) {
        effectiveLayoutControlConfig = converted.layoutControlConfig
        console.log('[useServiceModuleSyntax] Using converted layoutControlConfig (original was invalid)')
      } else {
        console.log('[useServiceModuleSyntax] Keeping original layoutControlConfig (already valid)')
      }
    }

    console.log('[useServiceModuleSyntax] Final effectiveLayoutControlConfig:', effectiveLayoutControlConfig)

    const overallDirection = effectiveLayoutControlConfig?.overallDirection || 'TB'

    // ELK布局使用与配置一致的方向，不再反转
    // ELK的elk.direction配置会控制实际布局方向
    let actualDirection = overallDirection

    let graphKeyword
    let elkInitDirective = ''
    if (layoutEngine === 'elk') {
      graphKeyword = `flowchart-elk ${actualDirection}`
      // ELK配置通过mermaid.initialize传递，不需要在代码中重复配置
      elkInitDirective = ''
    } else {
      graphKeyword = `flowchart ${actualDirection}`
    }

    let mermaidCode = ''

    mermaidCode += elkInitDirective + graphKeyword + '\n'

    let sortedContainers = containers
    const centerSubDomain_value = data.centerSubDomain
    
    console.log('[useServiceModuleSyntax] containers count:', containers?.length)
    console.log('[useServiceModuleSyntax] centerSubDomain_value:', centerSubDomain_value)
    console.log('[useServiceModuleSyntax] containers before sort:', containers?.map(c => ({ id: c.id, name: c.name, nodesCount: c.nodes?.length })))
    
    if (centerSubDomain_value) {
      sortedContainers = sortContainersForGrid(containers, centerSubDomain_value)
    }
    
    console.log('[useServiceModuleSyntax] sortedContainers count:', sortedContainers?.length)
    console.log('[useServiceModuleSyntax] sortedContainers:', sortedContainers?.map(c => ({ id: c.id, name: c.name, nodesCount: c.nodes?.length })))

    const nodeMap = createSimpleNodeMap(nodes)
    const definedNodes = new Set()

    // 调试：打印所有节点 ID 和容器中的节点 ID
    const containerNodeIds = new Set()
    if (containers) {
      containers.forEach((c) => {
        if (c.nodes) {
          c.nodes.forEach(nid => {
            const nodeId = typeof nid === 'string' ? nid : (nid.id || nid.code || nid.name)
            containerNodeIds.add(nodeId)
          })
        }
      })
    }
    
    console.log('[useServiceModuleSyntax] containerNodeIds:', Array.from(containerNodeIds).slice(0, 20))

    // 检查链接端点是否都在容器节点中
    if (links) {
      const undefinedLinks = links.filter(l => !containerNodeIds.has(l.source) || !containerNodeIds.has(l.target))
      if (undefinedLinks.length > 0) {
        console.warn('[useServiceModuleSyntax] Links with undefined nodes:', undefinedLinks.map(l => `${l.source} -> ${l.target}`))
        console.warn('[useServiceModuleSyntax] Undefined source nodes:', undefinedLinks.filter(l => !containerNodeIds.has(l.source)).map(l => l.source))
        console.warn('[useServiceModuleSyntax] Undefined target nodes:', undefinedLinks.filter(l => !containerNodeIds.has(l.target)).map(l => l.target))
      }
    }

    console.log('[useServiceModuleSyntax] ====== CHECKING LAYOUT CONTROL ======')
    console.log('[useServiceModuleSyntax] effectiveLayoutControlConfig.enabled:', effectiveLayoutControlConfig?.enabled)
    console.log('[useServiceModuleSyntax] effectiveLayoutControlConfig.groups?.length:', effectiveLayoutControlConfig?.groups?.length)
    
    if (effectiveLayoutControlConfig?.groups?.length > 0) {
      console.log('[useServiceModuleSyntax] All groups structure:')
      effectiveLayoutControlConfig.groups.forEach((g, i) => {
        console.log(`  Group ${i}: id=${g.id}, type=${g.type}, containersCount=${g.containers?.length}, childrenCount=${g.children?.length}`)
        if (g.containers?.length > 0) {
          console.log(`    First container:`, g.containers[0])
        }
      })
    }
    
    if (effectiveLayoutControlConfig?.enabled && effectiveLayoutControlConfig?.groups?.length > 0) {
      console.log('[useServiceModuleSyntax] ====== START LAYOUT GENERATION ======')
      console.log('[useServiceModuleSyntax] effectiveLayoutControlConfig.enabled:', effectiveLayoutControlConfig.enabled)
      console.log('[useServiceModuleSyntax] effectiveLayoutControlConfig.groups count:', effectiveLayoutControlConfig.groups.length)
      console.log('[useServiceModuleSyntax] effectiveLayoutControlConfig.groups:', JSON.stringify(effectiveLayoutControlConfig.groups, null, 2).substring(0, 2000))
      console.log('[useServiceModuleSyntax] sortedContainers count:', sortedContainers.length)
      console.log('[useServiceModuleSyntax] sortedContainers:', sortedContainers.map(c => ({ id: c.id, name: c.name, nodesCount: c.nodes?.length })))
      
      const resolvedConfig = resolveGroupContainers(effectiveLayoutControlConfig, sortedContainers)
      console.log('[useServiceModuleSyntax] resolvedConfig.groups:', JSON.stringify(resolvedConfig.groups, null, 2).substring(0, 2000))
      
      console.log('[useServiceModuleSyntax] containers after resolveGroupContainers (resolvedConfig):')
      if (resolvedConfig?.groups?.length > 0) {
        resolvedConfig.groups.forEach((g, i) => {
          console.log(`  Group ${i} (${g.id}, type=${g.type}): containersCount=${g.containers?.length}`)
          if (g.containers) {
            g.containers.forEach((c, j) => {
              console.log(`    Container ${j}:`, {
                id: c?.id,
                name: c?.name,
                fullTitle: c?.fullTitle,
                title: c?.title,
                type: c?.type,
                nodesCount: c?.nodes?.length,
                elementCode: c?.elementCode
              })
            })
          }
        })
      }
    
    const layoutCode = routeLayout(sortedContainers, {
        layoutType: 'grouped',
        layoutEngine,
        positions,
        sortedContainers,
        zoneRowCount,
        nodeMap,
        definedNodes,
        layoutControlConfig: resolvedConfig
      })
      if (layoutCode) {
        mermaidCode += layoutCode

        // 渲染未分组的节点（不在 definedNodes 中的节点）
        nodes.forEach(node => {
          if (!definedNodes.has(node.id)) {
            const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
            mermaidCode += `  ${node.id}["${displayText}"]\n`
            definedNodes.add(node.id)
          }
        })
      } else {
        // 反转容器顺序：Mermaid 渲染时后定义的元素出现在布局的前面位置
        const reversedContainers = [...sortedContainers].reverse()
        reversedContainers.forEach((container, index) => {
          const containerId = `C${sortedContainers.length - index}`
          const containerTitle = formatContainerTitle(container.fullTitle || container.name || 'Container')

          mermaidCode += `  subgraph ${containerId}["${containerTitle}"]\n`
          // subgraph 内部方向跟随整体方向：LR=水平排列，TB=垂直排列
          mermaidCode += `    direction ${actualDirection}\n`

          // 反转节点顺序
          const reversedNodes = [...(container.nodes || [])].reverse()
          reversedNodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node) {
              if (!definedNodes.has(node.id)) {
                const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
                mermaidCode += `    ${node.id}["${displayText}"]\n`
                definedNodes.add(node.id)
              } else {
                mermaidCode += `    ${nodeId}\n`
              }
            }
          })

          mermaidCode += `  end\n`
          mermaidCode += `  style ${containerId} ${getContainerStyle()}\n`
        })
      }
    } else {
      // 反转容器顺序：Mermaid 渲染时后定义的元素出现在布局的前面位置
      const reversedContainers = [...sortedContainers].reverse()
      reversedContainers.forEach((container, index) => {
        const containerId = `C${sortedContainers.length - index}`
        const containerTitle = formatContainerTitle(container.fullTitle || container.name || 'Container')

        mermaidCode += `  subgraph ${containerId}["${containerTitle}"]\n`
        // subgraph 内部方向跟随整体方向：LR=水平排列，TB=垂直排列
        mermaidCode += `    direction ${actualDirection}\n`

        // 反转节点顺序
        const reversedNodes = [...(container.nodes || [])].reverse()
        reversedNodes.forEach(nodeId => {
          const node = nodeMap.get(nodeId)
          if (node) {
            if (!definedNodes.has(node.id)) {
              const displayText = node.code ? `${node.name}\\n(${node.code})` : node.name
              mermaidCode += `    ${node.id}["${displayText}"]\n`
              definedNodes.add(node.id)
            } else {
              mermaidCode += `    ${nodeId}\n`
            }
          }
        })

        mermaidCode += `  end\n`
        mermaidCode += `  style ${containerId} ${getContainerStyle()}\n`
      })
    }

    const { code: linksCode, relationDescriptions: relations } = generateLinksCode(links, nodeMap, {
      containers,
      centerSubDomain,
      collectRelations: true
    })
    mermaidCode += linksCode

    if (relationDescriptions && relations.length > 0) {
      relationDescriptions.push(...relations)
    }

    const textColor = nodeTextColor === 'white' ? '#ffffff' :
                      nodeTextColor === 'gray' ? '#808080' : '#000000'

    mermaidCode += generateClassDefs()

    const nodeColorMappings = []
    nodes.forEach(node => {
      mermaidCode += `  style ${node.id} ${getNodeStyle(node.color, textColor)}\n`
      nodeColorMappings.push({ nodeId: node.id, color: node.color, nodeCode: node.code, nodeName: node.name })
    })

    return {
      mermaidCode,
      nodeColorMappings
    }
  }

  return {
    generateMermaidCode
  }
}
