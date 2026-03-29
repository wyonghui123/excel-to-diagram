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

    let sourceGroupKey = null
    let targetGroupKey = null
    let isSourceCenter = false
    let isTargetCenter = false

    containers.forEach(container => {
      if (!container.nodes) return
      const containerSubDomain = getSubDomainName(container)

      if (container.nodes.includes(sourceNode.id)) {
        sourceGroupKey = containerSubDomain
        if (containerSubDomain === centerSubDomain) {
          isSourceCenter = true
        }
      }
      if (container.nodes.includes(targetNode.id)) {
        targetGroupKey = containerSubDomain
        if (containerSubDomain === centerSubDomain) {
          isTargetCenter = true
        }
      }
    })

    let linkColor = DEFAULT_LINK_COLOR
    if (isSourceCenter || isTargetCenter) {
      linkColor = isSourceCenter ? targetColor : sourceColor
    } else if (sourceColor && targetColor) {
      linkColor = sourceColor
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
        if (containers.length > 0 && centerSubDomain) {
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
