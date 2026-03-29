import { getColors, getLinkColor } from './useMermaidColors.js'
import { useBlockDiagramStyle } from '../style/useBlockDiagramStyle.js'
import { useBlockDiagramSyntax, DIAGRAM_TYPES } from './useBlockDiagramSyntax.js'
import { routeLayout, DEPRECATED_LAYOUT_TYPES, isDeprecatedLayout, convertDeprecatedLayout } from '../layouts/index.js'

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
    console.log('[useServiceModuleSyntax] generateMermaidCode - layoutEngine:', layoutEngine, 'layoutControlConfig:', layoutControlConfig)

    if (!data || !data.nodes || !data.links) {
      console.warn('数据不完整:', data)
      return 'graph TD\n  A[No Data]'
    }

    if (!data.containers || !Array.isArray(data.containers)) {
      console.warn('[useServiceModuleSyntax] containers 不存在或为空')
      data.containers = []
    }

    preCalculateNodeSizes(data, DIAGRAM_TYPES.SERVICE_MODULE)

    const { nodes, links, containers, centerSubDomain, serviceModuleTextColor, colorScheme } = data

    let effectiveLayoutControlConfig = layoutControlConfig
    
    if (isDeprecatedLayout(layoutType)) {
      console.log('[useServiceModuleSyntax] Converting deprecated layout type:', layoutType)
      const converted = convertDeprecatedLayout(layoutType, containers, { zoneRowCount })
      effectiveLayoutControlConfig = converted.layoutControlConfig
    }

    const overallDirection = effectiveLayoutControlConfig?.overallDirection || 'TB'
    
    let graphKeyword
    if (layoutEngine === 'elk') {
      graphKeyword = `flowchart-elk ${overallDirection}`
    } else {
      graphKeyword = `flowchart ${overallDirection}`
    }
    
    console.log('[useServiceModuleSyntax] graphKeyword:', graphKeyword, 'overallDirection:', overallDirection)
    
    let mermaidCode = ''
    
    mermaidCode += graphKeyword + '\n'

    let sortedContainers = containers
    const centerSubDomain_value = data.centerSubDomain
    
    if (centerSubDomain_value) {
      sortedContainers = sortContainersForGrid(containers, centerSubDomain_value)
    }

    const nodeMap = createSimpleNodeMap(nodes)
    const definedNodes = new Set()

    if (effectiveLayoutControlConfig?.enabled && effectiveLayoutControlConfig?.groups?.length > 0) {
      const layoutCode = routeLayout(sortedContainers, {
        layoutType: 'grouped',
        layoutEngine,
        positions,
        sortedContainers,
        zoneRowCount,
        nodeMap,
        definedNodes,
        layoutControlConfig: effectiveLayoutControlConfig
      })
      console.log('[useServiceModuleSyntax] layoutCode generated:', layoutCode?.substring(0, 200))
      if (layoutCode) {
        mermaidCode += layoutCode
      } else {
        console.log('[useServiceModuleSyntax] No layout code generated, using default container rendering')
        sortedContainers.forEach((container, index) => {
          const containerId = `C${index + 1}`

          mermaidCode += `  subgraph ${containerId}["${container.fullTitle}"]\n`

          container.nodes && container.nodes.forEach(nodeId => {
            const node = nodeMap.get(nodeId)
            if (node) {
              if (!definedNodes.has(node.id)) {
                const nodeLabel = `${node.name}\\n(${node.code})`
                mermaidCode += `    ${node.id}["${nodeLabel}"]:::node\n`
                definedNodes.add(node.id)
              } else {
                mermaidCode += `    ${node.id}\n`
              }
            }
          })

          mermaidCode += `  end\n`
          mermaidCode += `  style ${containerId} ${getContainerStyle()}\n`
        })
      }
    } else {
      sortedContainers.forEach((container, index) => {
        const containerId = `C${index + 1}`

        mermaidCode += `  subgraph ${containerId}["${container.fullTitle}"]\n`

        container.nodes && container.nodes.forEach(nodeId => {
          const node = nodeMap.get(nodeId)
          if (node) {
            if (!definedNodes.has(node.id)) {
              const nodeLabel = `${node.name}\\n(${node.code})`
              mermaidCode += `    ${node.id}["${nodeLabel}"]:::node\n`
              definedNodes.add(node.id)
            } else {
              mermaidCode += `    ${node.id}\n`
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

    const textColor = serviceModuleTextColor === 'white' ? '#ffffff' :
                      serviceModuleTextColor === 'gray' ? '#808080' : '#000000'

    mermaidCode += generateClassDefs()

    nodes.forEach(node => {
      mermaidCode += `  style ${node.id} ${getNodeStyle(node.color, textColor)}\n`
    })

    console.log('[useServiceModuleSyntax] Final mermaidCode length:', mermaidCode.length)

    return mermaidCode
  }

  return {
    generateMermaidCode
  }
}
