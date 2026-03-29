export function useDiagramStyle() {
  const apply = (svg, data, strategy) => {
    if (!svg || !data) return

    applyNodeStyles(svg, data, strategy)
    applyLinkStyles(svg, data, strategy)
    applyContainerStyles(svg, data, strategy)
    applyLabelStyles(svg, data, strategy)
  }

  const applyNodeStyles = (svg, data, strategy) => {
    const nodes = svg.querySelectorAll('.node')

    nodes.forEach(node => {
      const nodeId = node.id
      const nodeData = data.nodes?.find(n => n.id === nodeId || node.id?.includes(n.id))

      if (!nodeData) return

      const color = data.nodeColors?.get(nodeData.id)
      if (color) {
        const rect = node.querySelector('rect, polygon')
        if (rect) {
          rect.style.fill = color
          rect.style.stroke = '#333'
          rect.style.strokeWidth = '2px'
        }
      }

      const size = data.nodeSizes?.get(nodeData.id)
      if (size) {
        const rect = node.querySelector('rect, polygon')
        if (rect) {
          rect.style.width = `${size.width}px`
          rect.style.height = `${size.height}px`
        }
      }
    })
  }

  const applyLinkStyles = (svg, data, strategy) => {
    const links = svg.querySelectorAll('.edgePath')

    links.forEach(link => {
      const path = link.querySelector('path')
      if (!path) return

      const linkId = link.id
      const linkData = data.links?.find(l => linkId?.includes(l.id))

      if (!linkData) return

      const color = data.linkColors?.get(linkData.id)
      if (color) {
        path.style.stroke = color
        path.style.fill = 'none'
      }

      const width = data.linkWidths?.get(linkData.id)
      if (width) {
        path.style.strokeWidth = width
      }
    })
  }

  const applyContainerStyles = (svg, data, strategy) => {
    const containers = svg.querySelectorAll('.cluster')

    containers.forEach(container => {
      const containerId = container.id
      const containerData = data.containers?.find(c => containerId?.includes(c.id))

      if (!containerData) return

      const rect = container.querySelector('rect')
      if (rect) {
        rect.style.fill = strategy?.behaviorConfig?.container?.style?.fill || '#ffffff'
        rect.style.stroke = strategy?.behaviorConfig?.container?.style?.stroke || '#333'
        rect.style.strokeWidth = strategy?.behaviorConfig?.container?.style?.strokeWidth || '2px'
      }
    })
  }

  const applyLabelStyles = (svg, data, strategy) => {
    const labels = svg.querySelectorAll('.edgeLabel')

    labels.forEach(label => {
      const background = strategy?.behaviorConfig?.label?.background

      if (background === 'white') {
        label.style.background = '#ffffff'
        const bgRect = label.querySelector('rect.background')
        if (bgRect) {
          bgRect.setAttribute('fill', '#ffffff')
          bgRect.style.fill = '#ffffff'
        }
      } else if (background === 'transparent') {
        label.style.background = 'transparent'
        const rects = label.querySelectorAll('rect')
        rects.forEach(rect => {
          rect.style.fill = 'transparent'
          rect.setAttribute('fill', 'transparent')
        })
      }
    })
  }

  const updateNodeStyle = (svg, nodeId, styleConfig) => {
    const node = svg.querySelector(`#${nodeId}`) || svg.querySelector(`[id*="${nodeId}"]`)
    if (!node) return

    const rect = node.querySelector('rect, polygon')
    if (!rect) return

    if (styleConfig.fill) rect.style.fill = styleConfig.fill
    if (styleConfig.stroke) rect.style.stroke = styleConfig.stroke
    if (styleConfig.strokeWidth) rect.style.strokeWidth = styleConfig.strokeWidth
    if (styleConfig.filter) rect.style.filter = styleConfig.filter
  }

  const updateLinkStyle = (svg, linkId, styleConfig) => {
    const link = svg.querySelector(`#${linkId}`) || svg.querySelector(`[id*="${linkId}"]`)
    if (!link) return

    const path = link.querySelector('path')
    if (!path) return

    if (styleConfig.stroke) path.style.stroke = styleConfig.stroke
    if (styleConfig.strokeWidth) path.style.strokeWidth = styleConfig.strokeWidth
    if (styleConfig.filter) path.style.filter = styleConfig.filter
  }

  const highlightElement = (svg, elementId, type, highlightStyle) => {
    if (type === 'node') {
      updateNodeStyle(svg, elementId, {
        stroke: highlightStyle?.nodeStroke || '#FF6B6B',
        strokeWidth: highlightStyle?.nodeStrokeWidth || '4px',
        filter: highlightStyle?.nodeFilter || 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
      })
    } else if (type === 'link') {
      updateLinkStyle(svg, elementId, {
        stroke: highlightStyle?.pathStroke || '#FF6B6B',
        strokeWidth: highlightStyle?.pathStrokeWidth || '4px',
        filter: highlightStyle?.pathFilter || 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
      })
    }
  }

  const clearHighlight = (svg, elementId, type) => {
    if (type === 'node') {
      updateNodeStyle(svg, elementId, {
        stroke: '#333',
        strokeWidth: '2px',
        filter: ''
      })
    } else if (type === 'link') {
      updateLinkStyle(svg, elementId, {
        strokeWidth: '2px',
        filter: ''
      })
    }
  }

  return {
    apply,
    applyNodeStyles,
    applyLinkStyles,
    applyContainerStyles,
    applyLabelStyles,
    updateNodeStyle,
    updateLinkStyle,
    highlightElement,
    clearHighlight
  }
}

export const diagramStyle = useDiagramStyle()
