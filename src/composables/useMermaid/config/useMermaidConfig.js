import mermaid from 'mermaid'
import { LAYOUT_TEMPLATES } from '@/constants/diagram'

export { LAYOUT_TEMPLATES }

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
 * @param {Object} layoutControlConfig - 布局控制配置
 * @returns {Object} - { layout: 'elk.xxx', elk: {...配置} }
 */
export function getElkConfig(data = null, layoutType = 'default', preserveModelOrder = false, layoutControlConfig = null) {
  // 根据整体方向设置ELK方向
  // ELK方向: DOWN(从上到下), RIGHT(从左到右), LEFT(从右到左), UP(从下到上)
  const overallDirection = layoutControlConfig?.overallDirection || 'TB'
  const elkDirection = overallDirection === 'TB' ? 'DOWN' : 'RIGHT'

  // ELK 配置 - layout 指定使用 elk 引擎
  // 注意：padding 格式使用 = 分隔符，不是 :
  // ELK 官方文档参考：https://www.eclipse.org/elk/documentation.html
  const elkOptions = {
    'elk.direction': elkDirection,

    // 节点间距配置 - 增加间距以改善均匀分布
    'elk.spacing.nodeNode': 100,
    'elk.layered.spacing.nodeNodeBetweenLayers': 150,

    // 图表整体 padding（增加 left/right 以改善嵌套容器内边距）
    'elk.padding': '[top=40,left=80,right=80,bottom=40]',

    // 关键：支持嵌套结构
    'elk.hierarchyHandling': 'INCLUDE_CHILDREN',

    // 算法选择
    'elk.algorithm': 'layered',

    // 交叉最小化策略
    'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',

    // 节点放置策略 - 尝试 NETWORK_SIMPLEX 以获得更平衡的节点分布
    'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',

    // 边间距
    'elk.layered.spacing.edgeNodeBetweenLayers': 60,

    // 独立组件间距 - 大幅增加以改善分组之间的间距
    'elk.layered.componentsSpacing': 200,

    // 基础间距值
    'elk.layered.spacing.baseValue': 50,

    // 内容对齐 - 居中对齐
    'elk.contentAlignment': 'CENTER',
    'elk.alignment': 'CENTER',

    // 容器间距 - 增加容器之间的间距（标题变长后需要更大间距）
    'elk.spacing.componentComponent': 250,
    'elk.layered.spacing.componentComponent': 250,
    
    // 父容器间距 - 嵌套容器之间的间距
    'elk.spacing.parentParent': 50,
    
    // 节点与容器边缘的间距
    'elk.padding.nodes': '[top=30,left=50,right=50,bottom=30]',

    // 循环检测
    'elk.layered.cycleBreaking.strategy': 'GREEDY_MODEL_ORDER',

    // 层级策略
    'elk.layered.layering.strategy': 'NETWORK_SIMPLEX',
  }
  return {
    layout: 'elk',
    elk: elkOptions,
  }
}

export function useMermaidConfig() {
  const getConfig = (diagramType, data = null, layoutEngine = 'dagre', layoutType = 'default', preserveModelOrder = false, layoutControlConfig = null, maxTextSize = 500000) => {
    let layoutParams = null
    if (data) {
      layoutParams = calculateOptimalLayout(data)
    }

    // rankdir 应该与 overallDirection 同步，而不是使用 calculateOptimalLayout 的自动计算
    const rankdir = layoutControlConfig?.overallDirection || 'LR'

    const baseConfig = {
      startOnLoad: false,
      securityLevel: 'loose',
      maxTextSize: maxTextSize,
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
        padding: 20,
        nodeSpacing: layoutParams?.nodeSpacing || 80,
        rankSpacing: layoutParams?.rankSpacing || 100,
        arrowMarkerAbsolute: true,
        useMaxWidth: false,
        htmlLabels: true,
        diagramPadding: 20,
        wrappingWidth: 200,
        labelPosition: 'c',
        defaultLinkLength: 50,
        arrowHeadWidth: 6,
        arrowHeadHeight: 6,
        rankdir: rankdir,
        subGraphTitleMargin: { top: 15, bottom: 15 }
      }
    }

    if (diagramType === 'serviceModule') {
      baseConfig.flowchart.padding = 25
      baseConfig.flowchart.nodeSpacing = layoutParams?.nodeSpacing || 120
      baseConfig.flowchart.rankSpacing = layoutParams?.rankSpacing || 150
      baseConfig.flowchart.diagramPadding = 40
      baseConfig.flowchart.wrappingWidth = 400
      baseConfig.flowchart.defaultLinkLength = 60
      baseConfig.flowchart.arrowHeadWidth = 8
      baseConfig.flowchart.arrowHeadHeight = 6
    }

    if (data && data.calculatedNodeWidth && data.calculatedNodeHeight) {
      baseConfig.flowchart.nodeWidth = data.calculatedNodeWidth
      baseConfig.flowchart.nodeHeight = data.calculatedNodeHeight
    } else {
      if (diagramType === 'serviceModule') {
        baseConfig.flowchart.nodeWidth = 250
        baseConfig.flowchart.nodeHeight = 100
      } else {
        baseConfig.flowchart.nodeWidth = 150
        baseConfig.flowchart.nodeHeight = 60
      }
    }

    if (layoutEngine === 'elk') {
      const elkResult = getElkConfig(data, layoutType, preserveModelOrder, layoutControlConfig)
      return {
        ...baseConfig,
        layout: elkResult.layout,
        elk: elkResult.elk,
      }
    }

    return baseConfig
  }

  const initializeMermaid = (diagramType, data = null, layoutEngine = 'dagre', layoutType = 'default', preserveModelOrder = false, layoutControlConfig = null, maxTextSize = 500000) => {
    const config = getConfig(diagramType, data, layoutEngine, layoutType, preserveModelOrder, layoutControlConfig, maxTextSize)
    mermaid.initialize(config)
  }

  return {
    getConfig,
    initializeMermaid,
    LAYOUT_TEMPLATES
  }
}
