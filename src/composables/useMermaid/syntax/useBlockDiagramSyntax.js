import { getColors, assignColorsToGroups } from './useMermaidColors.js'
import { DEFAULT_LINK_COLOR } from '../color/useMermaidColors.js'
import { useBlockDiagramStyle } from '../style/useBlockDiagramStyle.js'
import { useDynamicSizeConfig } from '../config/useDynamicSizeConfig.js'

export const DIAGRAM_TYPES = {
  BUSINESS_OBJECT: 'businessObject',
  SERVICE_MODULE: 'serviceModule'
}

export const NODE_TEXT_FORMATS = {
  [DIAGRAM_TYPES.BUSINESS_OBJECT]: (node) => {
    return node.nodeCode ? `${node.originalName || node.name}\n(${node.nodeCode})` : (node.originalName || node.name)
  },
  [DIAGRAM_TYPES.SERVICE_MODULE]: (node) => {
    return node.code ? `${node.name}\n(${node.code})` : node.name
  }
}

export function useBlockDiagramSyntax() {
  const { getNodeStyle, getContainerStyle, getLinkStyle, generateClassDefs } = useBlockDiagramStyle()
  const { calculateMaxNodeSize, mergeWithDefault } = useDynamicSizeConfig()

  const createNodeMappings = (nodes, options = {}) => {
    const {
      idPrefix = 'N',
      idExtractor = (node) => node.code || node.name,
      codeExtractor = (node) => node.code,
      nameExtractor = (node) => node.originalName || node.name
    } = options

    const idMap = new Map()
    const codeMap = new Map()
    const nameMap = new Map()
    const nodeIdToOriginalIdMap = new Map()
    let nodeIndex = 1

    nodes.forEach(node => {
      const id = `${idPrefix}${nodeIndex++}`
      const originalId = idExtractor(node)
      const code = codeExtractor(node)
      const name = nameExtractor(node)

      if (originalId) {
        idMap.set(originalId, id)
        nodeIdToOriginalIdMap.set(id, originalId)
      }
      if (code) {
        codeMap.set(code, id)
      }
      if (name) {
        nameMap.set(name, id)
      }
    })

    return { idMap, codeMap, nameMap, nodeIdToOriginalIdMap }
  }

  const createSimpleNodeMap = (nodes) => {
    const nodeMap = new Map()
    nodes.forEach(node => {
      nodeMap.set(node.id, node)
    })
    return nodeMap
  }

  const findCenterSubDomain = (containers, centerSubDomain) => {
    if (!containers || !centerSubDomain) {
      return { isCenter: false, container: null }
    }

    for (const container of containers) {
      const subDomain = container.subDomain || container.name
      if (subDomain === centerSubDomain) {
        return { isCenter: true, container }
      }
    }

    return { isCenter: false, container: null }
  }

  const getSubDomainName = (container) => {
    if (!container) return null
    if (container.fullTitle) {
      const parts = container.fullTitle.split(' / ')
      return parts.length > 1 ? parts[1] : parts[0]
    }
    return container.subDomain || container.name
  }

  const calculateLinkColor = (sourceNode, targetNode, containers, centerSubDomain, colorScheme) => {
    const sourceColor = sourceNode.color
    const targetColor = targetNode.color

    // 使用节点的 isCenter 标记来判断是否在中心范围
    // 只有当 isCenter 标记为 true 时才认为是中心范围，为 false 或 undefined 时使用容器判断
    let isSourceCenter = sourceNode.isCenter === true
    let isTargetCenter = targetNode.isCenter === true

    // 如果 isCenter 不是 true，使用容器的子领域名称作为回退
    // 注意：只有当 isCenter 未定义（undefined）时才使用回退逻辑
    // 如果 isCenter 明确为 false，表示该节点不在中心范围，不需要回退判断
    if (sourceNode.isCenter === undefined || targetNode.isCenter === undefined) {
      containers.forEach(container => {
        if (!container.nodes) return
        const containerSubDomain = getSubDomainName(container)

        if (container.nodes.includes(sourceNode.id) || container.nodes.some(n => n.id === sourceNode.id)) {
          if (containerSubDomain === centerSubDomain) {
            isSourceCenter = true
          }
        }
        if (container.nodes.includes(targetNode.id) || container.nodes.some(n => n.id === targetNode.id)) {
          if (containerSubDomain === centerSubDomain) {
            isTargetCenter = true
          }
        }
      })
    }

    console.log('[calculateLinkColor] source:', sourceNode.id, 'target:', targetNode.id, 'isSourceCenter:', isSourceCenter, 'isTargetCenter:', isTargetCenter)

    let linkColor = DEFAULT_LINK_COLOR
    // 新的颜色规则：
    // 1. 如果源和目标中有一个非中心范围的节点，则采用该节点颜色
    // 2. 如果两个都是非中心范围则采用黑色
    // 3. 如果两个都是中心范围则采用该节点颜色
    if (!isSourceCenter && !isTargetCenter) {
      // 两个都是非中心范围 -> 黑色
      linkColor = '#000000'
      console.log('[calculateLinkColor] -> 黑色（两个都是非中心）')
    } else if (isSourceCenter && isTargetCenter) {
      // 两个都是中心范围 -> 采用源节点颜色（或目标节点颜色）
      linkColor = sourceColor || targetColor || DEFAULT_LINK_COLOR
      console.log('[calculateLinkColor] -> 中心颜色:', linkColor)
    } else {
      // 一个中心，一个非中心 -> 采用非中心节点的颜色
      linkColor = isSourceCenter ? targetColor : sourceColor
      console.log('[calculateLinkColor] -> 非中心颜色:', linkColor)
    }

    return linkColor
  }

  const generateLinksCode = (links, nodeMap, options = {}) => {
    const {
      containers = [],
      centerSubDomain = null,
      onLinkGenerated = null,
      collectRelations = false
    } = options

    let code = ''
    const linkColorMappings = []
    const relationDescriptions = []
    let linkIndex = 0

    links.forEach((link) => {
      const sourceNode = nodeMap.get(link.source)
      const targetNode = nodeMap.get(link.target)

      if (sourceNode && targetNode) {
        code += `  ${link.source} -->|"${link.label}"| ${link.target}\n`

        let linkColor = DEFAULT_LINK_COLOR
        // 计算连线颜色：优先使用节点的 isCenter 标记，其次使用容器的 centerSubDomain
        const hasCenterInfo = sourceNode.isCenter !== undefined || targetNode.isCenter !== undefined
        const hasContainerInfo = containers.length > 0 && centerSubDomain
        if (hasCenterInfo || hasContainerInfo) {
          linkColor = calculateLinkColor(sourceNode, targetNode, containers, centerSubDomain)
        }

        code += `  linkStyle ${linkIndex} ${getLinkStyle(linkColor)}\n`

        linkColorMappings.push({
          index: linkIndex,
          sourceId: link.source,
          targetId: link.target,
          color: linkColor
        })

        if (onLinkGenerated) {
          onLinkGenerated(link, linkIndex, linkColor)
        }

        if (collectRelations) {
          relationDescriptions.push({
            sourceName: sourceNode.name,
            targetName: targetNode.name,
            source: link.source,
            target: link.target,
            relationCode: link.label,
            label: link.label,
            relationDesc: link.tooltip || '',
            annotationContent: link.annotationContent || '',
            sourceCode: sourceNode.code,
            targetCode: targetNode.code
          })
        }

        linkIndex++
      }
    })

    return { code, linkColorMappings, relationDescriptions }
  }

  const processLinks = (links, nodes, containers, centerSubDomain, options = {}) => {
    const {
      idMap,
      onLinkProcessed
    } = options

    const nodeMap = createSimpleNodeMap(nodes)

    const linkColorMappings = []
    const relationDescriptions = []

    links.forEach((link, index) => {
      let sourceNode = null
      let targetNode = null

      if (link.sourceCode) {
        const sourceId = idMap.codeMap.get(link.sourceCode)
        if (sourceId) {
          const originalId = idMap.nodeIdToOriginalIdMap.get(sourceId)
          sourceNode = nodeMap.get(originalId) || nodes.find(n => n.code === link.sourceCode)
        }
      }

      if (link.targetCode) {
        const targetId = idMap.codeMap.get(link.targetCode)
        if (targetId) {
          const originalId = idMap.nodeIdToOriginalIdMap.get(targetId)
          targetNode = nodeMap.get(originalId) || nodes.find(n => n.code === link.targetCode)
        }
      }

      if (!sourceNode) {
        sourceNode = nodeMap.get(link.source) || nodes.find(n => n.name === link.sourceName)
      }
      if (!targetNode) {
        targetNode = nodeMap.get(link.target) || nodes.find(n => n.name === link.targetName)
      }

      if (sourceNode && targetNode) {
        const linkColor = calculateLinkColor(sourceNode, targetNode, containers, centerSubDomain)

        linkColorMappings.push({
          index,
          sourceId: sourceNode.id,
          targetId: targetNode.id,
          color: linkColor,
          sourceCode: link.sourceCode || sourceNode.code,
          targetCode: link.targetCode || targetNode.code
        })

        if (onLinkProcessed) {
          onLinkProcessed(link, index, linkColor)
        }

        if (options.collectRelations) {
          relationDescriptions.push({
            sourceName: sourceNode.name,
            targetName: targetNode.name,
            source: sourceNode.id,
            target: targetNode.id,
            relationCode: link.label || link.relationCode,
            label: link.label || link.relationCode,
            relationDesc: link.tooltip || link.relationDesc || '',
            sourceCode: link.sourceCode || sourceNode.code,
            targetCode: link.targetCode || targetNode.code
          })
        }
      }
    })

    return { linkColorMappings, relationDescriptions }
  }

  const preCalculateNodeSizes = (data, diagramType) => {
    const formatFn = NODE_TEXT_FORMATS[diagramType] || NODE_TEXT_FORMATS[DIAGRAM_TYPES.SERVICE_MODULE]

    const sizeConfig = mergeWithDefault(data.sizeConfig)

    let nodes = data.nodes
    if (diagramType === DIAGRAM_TYPES.BUSINESS_OBJECT) {
      nodes = data.nodes.filter(node => node.category === 'object')
    }

    const getNodeText = (node) => formatFn(node)
    const maxNodeSize = calculateMaxNodeSize(nodes, getNodeText, sizeConfig)

    data.calculatedNodeWidth = maxNodeSize.width
    data.calculatedNodeHeight = maxNodeSize.height

    return data
  }

  const applySnakeArrangement = (sortedContainers) => {
  const result = []
  const n = sortedContainers.length

  for (let i = 0; i < n; i++) {
    if (i % 2 === 0) {
      result.push(sortedContainers[i])
    } else {
      result.unshift(sortedContainers[i])
    }
  }

  return result
}

const generateLinkCode = (sourceId, targetId, label, linkColor) => {
  return `  ${sourceId} -->|"${label}"| ${targetId}\n  linkStyle ${0} ${getLinkStyle(linkColor)}\n`
}

return {
    DIAGRAM_TYPES,
    NODE_TEXT_FORMATS,
    createNodeMappings,
    createSimpleNodeMap,
    findCenterSubDomain,
    getSubDomainName,
    calculateLinkColor,
    generateLinksCode,
    processLinks,
    generateLinkCode,
    preCalculateNodeSizes,
    getNodeStyle,
    getContainerStyle,
    getLinkStyle,
    generateClassDefs
  }
}
