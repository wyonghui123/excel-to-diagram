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
      
      // [FIX 2026-08-02] 统一管道后 groups 由 deriveLayoutGroups 从同一容器树派生,
      // 与 sortedContainers 归属严格一致, 不再需要按 name/code 匹配真实容器 (spec 4.3)
      const resolvedConfig = effectiveLayoutControlConfig
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
      // [FIX 2026-08-02 v5] 回到原方案: 中心模块 (isCenter) fill 固定用 centerScopeColor 灰 (与 BO 图一致),
      //   不再用粗虚线边框区分 (用户反馈虚线区分不明显)。
      mermaidCode += node.isCenter
        ? `  style ${node.id} ${getNodeStyle('#808080', textColor)}\n`
        : `  style ${node.id} ${getNodeStyle(node.color, textColor)}\n`
      nodeColorMappings.push({ nodeId: node.id, color: node.color, nodeCode: node.code, nodeName: node.name, isCenter: !!node.isCenter })
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
