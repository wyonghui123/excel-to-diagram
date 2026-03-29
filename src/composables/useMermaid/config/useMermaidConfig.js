import mermaid from 'mermaid'

export const LAYOUT_TEMPLATES = {
  VERTICAL: 'vertical',
  HORIZONTAL: 'horizontal'
}

export function calculateOptimalLayout(data) {
  const nodeCount = data?.nodes?.length || 0
  const linkCount = data?.links?.length || 0
  const containerCount = data?.containers?.length ||
    data?.domainProducts?.reduce((sum, d) =>
      sum + (d.modules?.length || 0), 0) || 0

  const densityRatio = linkCount / Math.max(nodeCount, 1)
  const avgNodesPerContainer = nodeCount / Math.max(containerCount, 1)

  let rankdir = 'TB'
  let rankSpacing = 80
  let nodeSpacing = 100
  let aspectRatio = 0.8

  if (containerCount <= 3) {
    rankdir = 'LR'
    rankSpacing = 50
    nodeSpacing = 120
    aspectRatio = 1.2
  } else if (containerCount <= 6) {
    rankdir = 'TB'
    rankSpacing = 80
    nodeSpacing = 100
    aspectRatio = 0.8
  } else {
    rankdir = 'TB'
    rankSpacing = 50
    nodeSpacing = 100
    aspectRatio = 0.8
  }

  if (densityRatio > 2) {
    rankSpacing *= 0.85
    nodeSpacing *= 0.9
  }

  if (avgNodesPerContainer > 5) {
    nodeSpacing *= 1.15
  }

  return {
    rankdir,
    rankSpacing,
    nodeSpacing,
    aspectRatio
  }
}

/**
 * 获取 ELK 布局配置
 * @param {Object} data - 图表数据
 * @param {string} layoutType - 布局类型
 * @param {boolean} preserveModelOrder - 是否保持模型顺序
 * @returns {Object} - { layout: 'elk.xxx', elk: {...配置} }
 */
export function getElkConfig(data = null, layoutType = 'default', preserveModelOrder = false) {
  const aspectRatio = data?.aspectRatio || 1.0

  console.log('[getElkConfig] Called with layoutType:', layoutType, 'aspectRatio:', aspectRatio, 'preserveModelOrder:', preserveModelOrder)

  const baseElkOptions = {
    'elk.spacing.nodeNode': 50,
    'elk.padding': '[20, 20, 20, 20]',
    'elk.separateConnectedComponents': false,
    'elk.edgeRouting': 'ORTHOGONAL',
  }

  switch (layoutType) {
    case 'horizontal':
      console.log('[getElkConfig] Using horizontal (elk.layered + RIGHT)')
      return {
        layout: 'elk.layered',
        elk: {
          ...baseElkOptions,
          'elk.direction': 'RIGHT',
          'elk.layered.spacing.nodeNodeBetweenLayers': 150,
        }
      }

    case 'vertical':
      console.log('[getElkConfig] Using vertical (elk.layered + DOWN)')
      return {
        layout: 'elk.layered',
        elk: {
          ...baseElkOptions,
          'elk.direction': 'DOWN',
          'elk.spacing.nodeNode': 80,
        }
      }

    case 'zone':
      if (preserveModelOrder) {
        console.log('[getElkConfig] Using zone (elk.layered + DOWN with model order preserved)')
        return {
          layout: 'elk.layered',
          elk: {
            ...baseElkOptions,
            'elk.direction': 'DOWN',
            'elk.spacing.nodeNode': 80,
            'elk.layered.considerModelOrder.strategy': 'NODES_AND_EDGES',
            'elk.layered.crossingMinimization.forceNodeModelOrder': true,
          }
        }
      } else {
        console.log('[getElkConfig] Using zone (elk.layered + DOWN, optimized)')
        return {
          layout: 'elk.layered',
          elk: {
            ...baseElkOptions,
            'elk.direction': 'DOWN',
            'elk.spacing.nodeNode': 80,
          }
        }
      }

    default:
      console.log('[getElkConfig] Using default (elk.layered)')
      return {
        layout: 'elk.layered',
        elk: {
          ...baseElkOptions,
          'elk.direction': aspectRatio > 1.2 ? 'RIGHT' : 'DOWN',
        }
      }
  }
}

export function useMermaidConfig() {
  const getConfig = (diagramType, data = null, layoutEngine = 'dagre', layoutType = 'default', preserveModelOrder = false) => {
    let layoutParams = null
    if (data) {
      layoutParams = calculateOptimalLayout(data)
    }

    const baseConfig = {
      startOnLoad: false,
      securityLevel: 'loose',
      theme: 'base',
      themeVariables: {
        edgeLabelBackground: '#ffffff',
        edgeLabelColor: '#000000',
        primaryColor: '#ffffff',
        primaryTextColor: '#000000',
        primaryBorderColor: '#333333',
        lineColor: '#333333',
        secondaryColor: '#f0f0f0',
        tertiaryColor: '#ffffff'
      },
      flowchart: {
        curve: 'basis',
        padding: 25,
        nodeSpacing: layoutParams?.nodeSpacing || 80,
        rankSpacing: layoutParams?.rankSpacing || 100,
        arrowMarkerAbsolute: true,
        useMaxWidth: false,
        htmlLabels: true,
        diagramPadding: 30,
        wrappingWidth: 200,
        labelPosition: 'c',
        defaultLinkLength: 60,
        arrowHeadWidth: 6,
        arrowHeadHeight: 6,
        rankdir: layoutParams?.rankdir || 'TB'
      }
    }

    if (diagramType === 'serviceModule') {
      baseConfig.flowchart.padding = 30
      baseConfig.flowchart.nodeSpacing = layoutParams?.nodeSpacing || 150
      baseConfig.flowchart.rankSpacing = layoutParams?.rankSpacing || 200
      baseConfig.flowchart.diagramPadding = 50
      baseConfig.flowchart.wrappingWidth = 500
      baseConfig.flowchart.defaultLinkLength = 80
      baseConfig.flowchart.arrowHeadWidth = 10
      baseConfig.flowchart.arrowHeadHeight = 8
    }

    if (data && data.calculatedNodeWidth && data.calculatedNodeHeight) {
      baseConfig.flowchart.nodeWidth = data.calculatedNodeWidth
      baseConfig.flowchart.nodeHeight = data.calculatedNodeHeight
    } else {
      if (diagramType === 'serviceModule') {
        baseConfig.flowchart.nodeWidth = 300
        baseConfig.flowchart.nodeHeight = 120
      } else {
        baseConfig.flowchart.nodeWidth = 180
        baseConfig.flowchart.nodeHeight = 80
      }
    }

    if (layoutEngine === 'elk') {
      const elkResult = getElkConfig(data, layoutType, preserveModelOrder)
      console.log('[useMermaidConfig] ELK config result:', elkResult)
      return {
        ...baseConfig,
        layout: elkResult.layout,
        elk: elkResult.elk,
      }
    }

    return baseConfig
  }

  const initializeMermaid = (diagramType, data = null, layoutEngine = 'dagre', layoutType = 'default', preserveModelOrder = false) => {
    const config = getConfig(diagramType, data, layoutEngine, layoutType, preserveModelOrder)
    mermaid.initialize(config)
  }

  return {
    getConfig,
    initializeMermaid,
    LAYOUT_TEMPLATES
  }
}
