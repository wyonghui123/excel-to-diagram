import { getColors, assignColorsToGroups } from './useMermaidColors.js'
import { DEFAULT_LINK_COLOR } from '../color/useMermaidColors.js'
import { useBlockDiagramStyle } from '../style/useBlockDiagramStyle.js'
import { useDynamicSizeConfig } from '../config/useDynamicSizeConfig.js'
import { getArrowSyntax, sanitizeLabel } from './_shared/arrowHelper.js'
import { businessObjectLabel } from './nodeLabelTemplate.js'

export const DIAGRAM_TYPES = {
  BUSINESS_OBJECT: 'businessObject',
  /**
   * @deprecated 服务模块图（serviceModule）已废弃（2026-08-08）。
   *   业务层面不再区分「业务对象图 / 服务模块图」，唯一业务入口为嵌入式 Mermaid 图表，
   *   且「图表类型」下拉已被「展开层级」取代，chartType 固定为 'businessObject'。
   *   保留仅作历史兼容，禁止作为新功能入口。
   */
  SERVICE_MODULE: 'serviceModule'
}

export const NODE_TEXT_FORMATS = {
  [DIAGRAM_TYPES.BUSINESS_OBJECT]: (node) => {
    // [TEMPLATE 2026-08-11] 委托统一模板 (名称\n编码 两行)
    return businessObjectLabel(node)
  },
  // @deprecated 服务模块图（serviceModule）已废弃（2026-08-08），与 DIAGRAM_TYPES.SERVICE_MODULE 一同保留仅作历史参考
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

  const calculateLinkColor = (sourceNode, targetNode, containers, centerSubDomain, colorScheme, centerScopeColor = '#808080') => {
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

    // [FIX 2026-08-02 v6] 连线颜色规则 (与 BO 图对齐):
    //   1. 双中心 -> centerScopeColor 灰 (与中心模块灰色一致)
    //   2. 一中心一非中心 -> 非中心节点的颜色
    //   3. 双非中心 -> 黑色
    let linkColor = DEFAULT_LINK_COLOR
    if (isSourceCenter && isTargetCenter) {
      linkColor = centerScopeColor
      console.log('[calculateLinkColor] -> 中心范围色:', linkColor)
    } else if (isSourceCenter) {
      linkColor = targetColor || sourceColor || DEFAULT_LINK_COLOR
      console.log('[calculateLinkColor] -> 非中心颜色:', linkColor)
    } else if (isTargetCenter) {
      linkColor = sourceColor || targetColor || DEFAULT_LINK_COLOR
      console.log('[calculateLinkColor] -> 非中心颜色:', linkColor)
    } else {
      linkColor = '#000000'
      console.log('[calculateLinkColor] -> 黑色（两个都是非中心）')
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
        // [v39 关系线标题修复] 优先 code (实例编码), fallback 到 label, 再 fallback 到 relationCode
        const linkLabel = link.code || link.label || link.relationCode || ''
        code += getArrowSyntax(link.source, link.target, linkLabel, link)

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
            relationCode: linkLabel,
            label: linkLabel,
            relationDesc: link.tooltip || '',
            // [FIX 2026-06-30] 透传统数数组, 供 tooltip 按类别过滤
            annotationContent: link.annotationContent || '',
            annotationCategory: link.annotationCategory || 'info',
            annotationContents: link.annotationContents || [],
            annotationCategories: link.annotationCategories || [],
            sourceCode: sourceNode.code,
            targetCode: targetNode.code,
            // [FIX 2026-08-03] 透传 SM 子关系数组, 供 useTooltip 展示所有子关系 BO 对.
            //   BO 图 link 无此字段 → 空数组 → useTooltip 走单关系老逻辑 (单测兼容).
            childRelations: link.childRelations || [],
            // [FIX 2026-08-03] 透传方向/类型, 供 snapshot.links.relations 暴露给 e2e 断言双向渲染.
            //   之前缺失 → snapshot relations 的 relationDirection 恒空 → e2e 无法验证 SM 双向.
            relationDirection: link.relationDirection || '',
            relationType: link.relationType || ''
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
          // [v39 关系线标题修复] 优先 code → label → relationCode
          // - code: 关系实例编码 (e.g. "ORDER-USER-01")
          // - label: 透传的 label (旧逻辑保留, 兼容部分老数据流)
          // - relationCode: 关系类型编码 (e.g. "DEPENDS_ON")
          const resolvedRelationCode = link.code || link.label || link.relationCode || ''
          relationDescriptions.push({
            sourceName: sourceNode.name,
            targetName: targetNode.name,
            source: sourceNode.id,
            target: targetNode.id,
            relationCode: resolvedRelationCode,
            label: resolvedRelationCode,
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

const generateLinkCode = (sourceId, targetId, label, linkColor, link) => {
  return `${getArrowSyntax(sourceId, targetId, label, link)}  linkStyle ${0} ${getLinkStyle(linkColor)}\n`
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
