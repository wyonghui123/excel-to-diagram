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
    default: 'fill:#fafafa,stroke:#666666,stroke-width:1px,color:#000000,font-size:24px,text-align:center',
    node: 'text-align:center,font-size:24px,font-weight:bold',
    container: 'fill:#ffffff,stroke:#000000,stroke-width:2px',
    edgeLabel: 'color:#000000,fill:none,stroke:none,font-size:16px'
  }
}

export function useBlockDiagramStyle() {
  const getNodeStyle = (color, textColor = BLOCK_DIAGRAM_STYLES.node.textColor) => {
    return `fill:${color},stroke:#333333,stroke-width:2px,color:${textColor}`
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
