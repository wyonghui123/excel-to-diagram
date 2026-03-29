export function useBehaviorExecutor() {
  const execute = (config, elements, data) => {
    if (!config || !elements) return

    if (config.zoom?.enabled) {
      executeZoom(config.zoom, elements)
    }

    if (config.selection?.enabled) {
      executeSelection(config.selection, elements, data)
    }

    if (config.tooltip?.enabled) {
      executeTooltip(config.tooltip, elements, data)
    }

    if (config.label) {
      executeLabel(config.label, elements)
    }

    if (config.container) {
      executeContainer(config.container, elements)
    }
  }

  const executeZoom = (config, elements) => {
    const { minScale = 0.1, maxScale = 3, zoomFactor = 0.1, mouseCentered = true } = config
    const { container, draggableArea, svg } = elements

    if (!container || !draggableArea) return

    let scale = 1
    let translateX = 0
    let translateY = 0

    const updateTransform = () => {
      const transformValue = `translate(${translateX}px, ${translateY}px) scale(${scale})`
      draggableArea.style.transform = transformValue
    }

    const handleWheel = (e) => {
      e.preventDefault()

      const delta = e.deltaY > 0 ? -zoomFactor : zoomFactor
      const newScale = Math.max(minScale, Math.min(maxScale, scale + delta))

      if (mouseCentered) {
        const rect = draggableArea.getBoundingClientRect()
        const mouseX = e.clientX - rect.left
        const mouseY = e.clientY - rect.top

        translateX = mouseX - (mouseX - translateX) * (newScale / scale)
        translateY = mouseY - (mouseY - translateY) * (newScale / scale)
      }

      scale = newScale
      updateTransform()
    }

    container.addEventListener('wheel', handleWheel, { passive: false })

    return { handleWheel, updateTransform }
  }

  const executeSelection = (config, elements, data) => {
    const { onPathClick, onLabelClick, highlightStyle } = config
    const { svg, paths, labels } = elements

    if (!svg || !paths) return

    const selectedElements = { path: null, label: null, sourceNode: null, targetNode: null }

    const clearHighlight = () => {
      if (selectedElements.path) {
        selectedElements.path.style.strokeWidth = '2px'
        selectedElements.path.style.filter = ''
        selectedElements.path = null
      }

      if (selectedElements.sourceNode) {
        const rect = selectedElements.sourceNode.querySelector('rect, polygon')
        if (rect) {
          rect.style.stroke = ''
          rect.style.strokeWidth = ''
          rect.style.filter = ''
        }
        selectedElements.sourceNode = null
      }

      if (selectedElements.targetNode) {
        const rect = selectedElements.targetNode.querySelector('rect, polygon')
        if (rect) {
          rect.style.stroke = ''
          rect.style.strokeWidth = ''
          rect.style.filter = ''
        }
        selectedElements.targetNode = null
      }

      selectedElements.label = null
    }

    const highlightNode = (nodeId, type) => {
      let nodeElement = svg.querySelector(`#${nodeId}`)

      if (!nodeElement) {
        const allNodes = svg.querySelectorAll('.node')
        for (const node of allNodes) {
          if (node.id && node.id.includes(nodeId)) {
            nodeElement = node
            break
          }
        }
      }

      if (nodeElement) {
        const nodeContainer = nodeElement.closest('.node') || nodeElement

        const rect = nodeContainer.querySelector('rect, polygon')
        if (rect) {
          rect.style.stroke = highlightStyle?.nodeStroke || '#FF6B6B'
          rect.style.strokeWidth = highlightStyle?.nodeStrokeWidth || '4px'
          rect.style.filter = highlightStyle?.nodeFilter || 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
        }

        if (type === 'source') {
          selectedElements.sourceNode = nodeContainer
        } else {
          selectedElements.targetNode = nodeContainer
        }
      }
    }

    paths.forEach(path => {
      path.addEventListener('click', (e) => {
        e.stopPropagation()
        clearHighlight()

        const relation = data?.pathMap?.get(path)
        if (relation) {
          if (onPathClick?.highlightPath) {
            path.style.strokeWidth = highlightStyle?.pathStrokeWidth || '4px'
            path.style.filter = highlightStyle?.pathFilter || 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
            selectedElements.path = path
          }

          if (onPathClick?.highlightNodes) {
            highlightNode(relation.source, 'source')
            highlightNode(relation.target, 'target')
          }
        }
      })
    })

    if (labels) {
      labels.forEach(label => {
        label.addEventListener('click', (e) => {
          e.stopPropagation()
          clearHighlight()

          const relation = data?.labelMap?.get(label)
          if (relation && onLabelClick?.highlightPath) {
            const path = data?.pathMap?.get(relation)
            if (path) {
              path.style.strokeWidth = highlightStyle?.pathStrokeWidth || '4px'
              path.style.filter = highlightStyle?.pathFilter || 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
              selectedElements.path = path
            }
          }
        })
      })
    }

    return { selectedElements, clearHighlight, highlightNode }
  }

  const executeTooltip = (config, elements, data) => {
    const { svg, paths, labels } = elements

    if (!svg) return

    let tooltip = document.getElementById('mermaid-tooltip')
    if (!tooltip) {
      tooltip = document.createElement('div')
      tooltip.id = 'mermaid-tooltip'
      tooltip.style.position = 'fixed'
      tooltip.style.backgroundColor = 'rgba(0, 0, 0, 0.85)'
      tooltip.style.color = 'white'
      tooltip.style.padding = '10px 14px'
      tooltip.style.borderRadius = '6px'
      tooltip.style.fontSize = '13px'
      tooltip.style.zIndex = '100000'
      tooltip.style.pointerEvents = 'none'
      tooltip.style.visibility = 'hidden'
      tooltip.style.whiteSpace = 'pre-line'
      tooltip.style.lineHeight = '1.5'
      tooltip.style.maxWidth = '300px'
      tooltip.style.wordWrap = 'break-word'
      tooltip.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)'
      document.body.appendChild(tooltip)
    }

    const showTooltip = (text, x, y) => {
      tooltip.textContent = text
      tooltip.style.visibility = 'visible'
      tooltip.style.left = x + 10 + 'px'
      tooltip.style.top = y + 10 + 'px'
    }

    const hideTooltip = () => {
      tooltip.style.visibility = 'hidden'
    }

    const moveTooltip = (x, y) => {
      tooltip.style.left = x + 10 + 'px'
      tooltip.style.top = y + 10 + 'px'
    }

    const formatTooltipText = (relation) => {
      if (!relation) return '无关系说明'
      const code = relation.relationCode || relation.label || ''
      const desc = relation.description || '无关系说明'
      const source = relation.sourceName || relation.source || ''
      const target = relation.targetName || relation.target || ''
      return `${code}\n${source} → ${target}\n${desc}`
    }

    const allElements = [...(paths || []), ...(labels || [])]
    allElements.forEach(el => {
      el.addEventListener('mouseenter', (e) => {
        const relation = data?.pathMap?.get(el) || data?.labelMap?.get(el)
        const text = formatTooltipText(relation)
        showTooltip(text, e.clientX, e.clientY)
      })

      el.addEventListener('mousemove', (e) => {
        moveTooltip(e.clientX, e.clientY)
      })

      el.addEventListener('mouseleave', () => {
        hideTooltip()
      })
    })

    return { tooltip, showTooltip, hideTooltip, moveTooltip }
  }

  const executeLabel = (config, elements) => {
    const { background, trailingLine } = config
    const { labels, svg } = elements

    if (!labels) return

    labels.forEach(label => {
      if (background === 'white') {
        const bgRect = label.querySelector('rect.background')
        if (bgRect) {
          bgRect.setAttribute('fill', '#ffffff')
          bgRect.style.fill = '#ffffff'
        }
        label.style.background = '#ffffff'
      } else if (background === 'transparent') {
        const bgRect = label.querySelector('rect.background')
        if (bgRect) {
          bgRect.setAttribute('fill', 'transparent')
          bgRect.style.fill = 'transparent'
        }
        label.style.background = 'transparent'
      }
    })

    if (trailingLine?.enabled && svg) {
      addTrailingDottedLines(svg, labels, trailingLine)
    }
  }

  const addTrailingDottedLines = (svg, labels, config) => {
    const { color = '#999', dashArray = '3,3' } = config

    let defs = svg.querySelector('defs')
    if (!defs) {
      defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
      svg.insertBefore(defs, svg.firstChild)
    }

    labels.forEach(label => {
      if (!label.getBBox) return

      const labelBBox = label.getBBox()
      const labelTransform = label.getAttribute('transform') || ''
      const translateMatch = labelTransform.match(/translate\(([^,]+),\s*([^)]+)\)/)

      if (!translateMatch) return

      const translateX = parseFloat(translateMatch[1])
      const translateY = parseFloat(translateMatch[2])
      const labelLeft = translateX + labelBBox.x
      const labelTop = translateY + labelBBox.y
      const labelCenterX = labelLeft + labelBBox.width / 2
      const labelCenterY = labelTop + labelBBox.height / 2

      const labelParent = label.parentElement
      const path = labelParent?.previousElementSibling?.querySelector('path')

      if (!path) return

      const pathD = path.getAttribute('d')
      if (!pathD) return

      const points = parsePathPoints(pathD)
      if (points.length < 2) return

      const nearestPoint = findNearestPoint(points, labelCenterX, labelCenterY)

      const tailLine = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      tailLine.setAttribute('x1', labelCenterX.toFixed(2))
      tailLine.setAttribute('y1', labelCenterY.toFixed(2))
      tailLine.setAttribute('x2', nearestPoint.x.toFixed(2))
      tailLine.setAttribute('y2', nearestPoint.y.toFixed(2))
      tailLine.setAttribute('stroke', color)
      tailLine.setAttribute('stroke-width', '1.5')
      tailLine.setAttribute('stroke-dasharray', dashArray)
      tailLine.setAttribute('opacity', '0.8')

      svg.appendChild(tailLine)
    })
  }

  const parsePathPoints = (d) => {
    const points = []
    const commands = d.match(/[ML]\s*[\d.\-]+/gi) || []

    commands.forEach(cmd => {
      const coords = cmd.match(/[\d.\-]+/g)
      if (coords && coords.length >= 2) {
        points.push({
          x: parseFloat(coords[0]),
          y: parseFloat(coords[1])
        })
      }
    })

    return points
  }

  const findNearestPoint = (points, x, y) => {
    let nearest = points[0]
    let minDist = Infinity

    points.forEach(point => {
      const dist = Math.hypot(point.x - x, point.y - y)
      if (dist < minDist) {
        minDist = dist
        nearest = point
      }
    })

    return nearest
  }

  const executeContainer = (config, elements) => {
    const { titleFormat, style } = config
    const { containers, svg } = elements

    if (!containers || !svg) return

    const clusterLabels = svg.querySelectorAll('.cluster-label, .subgraph-label')

    clusterLabels.forEach(label => {
      if (style?.titleFontStyle === 'italic') {
        label.style.fontStyle = 'italic'
        label.setAttribute('font-style', 'italic')
      }
    })
  }

  return {
    execute,
    executeZoom,
    executeSelection,
    executeTooltip,
    executeLabel,
    executeContainer
  }
}

export const behaviorExecutor = useBehaviorExecutor()
