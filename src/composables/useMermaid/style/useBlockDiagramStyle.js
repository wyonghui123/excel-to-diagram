export const BLOCK_DIAGRAM_STYLES = {
  node: {
    fill: '#fafafa',
    stroke: '#333333',
    strokeWidth: 2,
    textColor: '#000000',
    fontSize: 24,
    fontWeight: 'bold'
  },
  container: {
    fill: '#ffffff',
    stroke: '#000000',
    strokeWidth: 2
  },
  link: {
    strokeWidth: 2,
    fill: 'none',
    dashArray: 0
  },
  edgeLabel: {
    textColor: '#000000',
    fontSize: 16
  },
  classDefs: {
    // [FIX 2026-08-02] 节点字号 24px→16px: classDef default 对所有无显式 class 的节点生效,
    //   classDef node 由 :::node 标记应用, 两处 24px 导致 BO/SM 图节点字体过大 (用户反馈"字体很大")。
    //   容器标题仍为 24px (CSS 注入 #mermaid-italic-style), 16px 节点 + 24px 容器形成正确层级。
    default: 'fill:#fafafa,stroke:#666666,stroke-width:1px,color:#000000,font-size:16px,text-align:center',
    node: 'text-align:center,font-size:16px,font-weight:bold',
    container: 'fill:#ffffff,stroke:#000000,stroke-width:2px',
    edgeLabel: 'color:#000000,fill:none,stroke:none,font-size:16px'
  }
}

export function useBlockDiagramStyle() {
  const getNodeStyle = (color, textColor = BLOCK_DIAGRAM_STYLES.node.textColor, stroke = '#333333', strokeWidth = 2, dashArray = null) => {
    // [FIX 2026-08-02] 支持自定义边框: 中心范围节点用粗虚线边框区分 (fill 保持分组色)
    const dashPart = dashArray ? `,stroke-dasharray:${dashArray}` : ''
    return `fill:${color},stroke:${stroke},stroke-width:${strokeWidth}px,color:${textColor}${dashPart}`
  }

  const getContainerStyle = (fillColor) => {
    const fill = fillColor || BLOCK_DIAGRAM_STYLES.container.fill
    return `fill:${fill},stroke:${BLOCK_DIAGRAM_STYLES.container.stroke},stroke-width:${BLOCK_DIAGRAM_STYLES.container.strokeWidth}px`
  }

  const getLinkStyle = (linkColor) => {
    return `stroke:${linkColor},stroke-width:${BLOCK_DIAGRAM_STYLES.link.strokeWidth}px,fill:${BLOCK_DIAGRAM_STYLES.link.fill},stroke-dasharray:${BLOCK_DIAGRAM_STYLES.link.dashArray}`
  }

  const generateClassDefs = () => {
    let code = ''
    code += `\nclassDef default ${BLOCK_DIAGRAM_STYLES.classDefs.default}\n`
    code += `\nclassDef node ${BLOCK_DIAGRAM_STYLES.classDefs.node}\n`
    code += `\nclassDef edgeLabel ${BLOCK_DIAGRAM_STYLES.classDefs.edgeLabel}\n`
    return code
  }

  return {
    BLOCK_DIAGRAM_STYLES,
    getNodeStyle,
    getContainerStyle,
    getLinkStyle,
    generateClassDefs
  }
}
