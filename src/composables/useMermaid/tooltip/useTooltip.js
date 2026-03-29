let tooltipInstance = null

export function useTooltip() {

  const createTooltipElement = () => {
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
    tooltipInstance = tooltip
    return tooltip
  }

  const showTooltip = (tooltip, text, x, y) => {
    tooltip.textContent = text
    tooltip.style.visibility = 'visible'
    tooltip.style.left = x + 10 + 'px'
    tooltip.style.top = y + 10 + 'px'
  }

  const hideTooltip = (tooltip) => {
    tooltip.style.visibility = 'hidden'
  }

  const moveTooltip = (tooltip, x, y) => {
    tooltip.style.left = x + 10 + 'px'
    tooltip.style.top = y + 10 + 'px'
  }

  const formatTooltipText = (relation) => {
    if (!relation) return '无关系说明'
    const relationCode = relation.relationCode || ''
    const relationDesc = relation.relationDesc || '无关系说明'
    const sourceName = relation.sourceName || ''
    const targetName = relation.targetName || ''
    return `${relationCode}\n${sourceName} → ${targetName}\n${relationDesc}`
  }

  const createSelectionState = () => {
    return {
      path: null,
      label: null,
      sourceNode: null,
      targetNode: null
    }
  }

  const clearHighlight = (selectedElements) => {
    if (selectedElements.path) {
      selectedElements.path.style.strokeWidth = '2px'
      selectedElements.path.style.removeProperty('filter')
      selectedElements.path = null
    }

    if (selectedElements.sourceNode) {
      const rect = selectedElements.sourceNode.querySelector('rect, polygon')
      if (rect) {
        rect.style.removeProperty('stroke')
        rect.style.strokeWidth = '2px'
        rect.style.removeProperty('filter')
      }
      const label = selectedElements.sourceNode.querySelector('.nodeLabel, text')
      if (label) {
        label.style.removeProperty('font-weight')
        label.style.removeProperty('font-size')
      }
      selectedElements.sourceNode = null
    }

    if (selectedElements.targetNode) {
      const rect = selectedElements.targetNode.querySelector('rect, polygon')
      if (rect) {
        rect.style.removeProperty('stroke')
        rect.style.strokeWidth = '2px'
        rect.style.removeProperty('filter')
      }
      const label = selectedElements.targetNode.querySelector('.nodeLabel, text')
      if (label) {
        label.style.removeProperty('font-weight')
        label.style.removeProperty('font-size')
      }
      selectedElements.targetNode = null
    }

    if (selectedElements.label) {
      selectedElements.label = null
    }
  }

  const highlightNode = (svg, nodeId, type, selectedElements) => {
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

    if (!nodeElement) {
      nodeElement = svg.querySelector(`[data-id="${nodeId}"]`)
    }

    if (nodeElement) {
      const nodeContainer = nodeElement.closest('.node') || nodeElement

      const rect = nodeContainer.querySelector('rect, polygon')
      if (rect) {
        rect.style.stroke = '#FF6B6B'
        rect.style.strokeWidth = '4px'
        rect.style.filter = 'drop-shadow(0 0 6px rgba(255, 107, 107, 0.6))'
      }

      const label = nodeContainer.querySelector('.nodeLabel, text')
      if (label) {
        label.style.fontWeight = 'bold'
        label.style.fontSize = '16px'
      }

      if (type === 'source') {
        selectedElements.sourceNode = nodeContainer
      } else {
        selectedElements.targetNode = nodeContainer
      }
    }
  }

  /**
   * ❌ 已移除：不再需要 JavaScript 设置背景
   * 所有 edgeLabel 背景样式由 CSS .edge-label-clean 类统一管理
   */
  // const setLabelBackground = (edgeLabels) => { ... }

  const matchPathsToRelations = (svg, labels, relationDescriptions) => {
    const pathToRelationMap = new Map()
    const relationCodeMap = new Map()

    relationDescriptions.forEach(relation => {
      if (relation.relationCode) {
        relationCodeMap.set(relation.relationCode, relation)
      }
    })

    labels.forEach((label) => {
      const labelText = label.textContent || label.innerHTML
      const relation = relationCodeMap.get(labelText.trim())
      if (relation) {
        pathToRelationMap.set(label, relation)
      }
    })

    const edgeContainers = Array.from(svg.querySelectorAll('.edgePath'))
    const directEdgePaths = Array.from(svg.querySelectorAll('path.flowchart-link'))
    const realEdgePaths = []

    edgeContainers.forEach((edgeContainer, edgeIndex) => {
      const path = edgeContainer.querySelector('path')
      if (path) {
        realEdgePaths.push({ path, index: edgeIndex })
      }
    })

    directEdgePaths.forEach((path, edgeIndex) => {
      if (!realEdgePaths.some(item => item.path === path)) {
        realEdgePaths.push({ path, index: edgeIndex + edgeContainers.length })
      }
    })

    realEdgePaths.forEach((edgePathInfo, idx) => {
      if (idx < relationDescriptions.length) {
        const relation = relationDescriptions[idx]
        pathToRelationMap.set(edgePathInfo.path, relation)
      }
    })

    return { pathToRelationMap, realEdgePaths }
  }

  const getEdgeLabels = (svg) => {
    const allEdgeLabels = svg.querySelectorAll('.edgeLabel')
    return Array.from(allEdgeLabels).filter(el => el.getBBox)
  }

  const setupLabelEvents = (label, index, tooltip, relationDescriptions, pathToRelationMap, labels, selectedElements, svg, realEdgePaths) => {
    label.addEventListener('mouseenter', (e) => {
      let tooltipText = '无关系说明'
      const labelText = label.textContent || label.innerHTML
      const relation = relationDescriptions.find(r => r.relationCode && r.relationCode.trim() === labelText.trim())
      if (relation) {
        tooltipText = formatTooltipText(relation)
      }
      showTooltip(tooltip, tooltipText, e.clientX, e.clientY)
    })

    label.addEventListener('mousemove', (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    })

    label.addEventListener('mouseleave', () => {
      hideTooltip(tooltip)
    })

    label.addEventListener('click', (e) => {
      e.stopPropagation()
      clearHighlight(selectedElements)
      selectedElements.label = label

      const relation = pathToRelationMap.get(label)

      if (relation) {
        const correspondingPath = realEdgePaths.find((item) => item.path && pathToRelationMap.get(item.path) === relation)?.path

        if (correspondingPath) {
          selectedElements.path = correspondingPath
          correspondingPath.style.strokeWidth = '4px'
          correspondingPath.style.filter = 'drop-shadow(0 0 8px rgba(0, 0, 0, 0.6))'
        }
      }
    })
  }

  const setupPathEvents = (path, tooltip, pathToRelationMap, labels, selectedElements, svg) => {
    path.addEventListener('mouseenter', (e) => {
      const relation = pathToRelationMap.get(path)
      const tooltipText = relation ? formatTooltipText(relation) : '无关系说明'
      showTooltip(tooltip, tooltipText, e.clientX, e.clientY)
    })

    path.addEventListener('mousemove', (e) => {
      moveTooltip(tooltip, e.clientX, e.clientY)
    })

    path.addEventListener('mouseleave', () => {
      hideTooltip(tooltip)
    })

    path.addEventListener('click', (e) => {
      e.stopPropagation()

      selectedElements.path = null
      selectedElements.label = null
      selectedElements.sourceNode = null
      selectedElements.targetNode = null
      selectedElements.path = path

      const relation = pathToRelationMap.get(path)

      if (relation) {
        const relationCode = relation.relationCode
        const correspondingLabel = Array.from(labels).find((label) => {
          const labelText = label.textContent || label.innerHTML
          return labelText.trim() === relationCode
        })

        if (correspondingLabel) {
          selectedElements.label = correspondingLabel
        }

        highlightNode(svg, relation.source, 'source', selectedElements)
        highlightNode(svg, relation.target, 'target', selectedElements)
      }
    })
  }

  const addTrailingDottedLines = (svg, labels, diagramType) => {
    if (diagramType !== 'businessObject' && diagramType !== 'serviceModule') return

    let defs = svg.querySelector('defs')
    if (!defs) {
      defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
      svg.insertBefore(defs, svg.firstChild)
    }

    labels.forEach((label, index) => {
      if (!label.getBBox) {
        console.warn(`标签 ${index} 不是 SVG 元素，跳过`);
        return
      }

      const labelTransform = label.getAttribute('transform') || ''
      const translateMatch = labelTransform.match(/translate\(([^,]+),\s*([^)]+)\)/)

      if (!translateMatch) {
        console.warn(`标签 ${index} 没有 Transform`)
        return
      }

      const translateX = parseFloat(translateMatch[1])
      const translateY = parseFloat(translateMatch[2])

      // 获取标签内容元素（foreignObject 或文本）
      const foreignObject = label.querySelector('foreignObject')
      let contentWidth = 0
      let contentHeight = 0

      if (foreignObject) {
        // 如果有 foreignObject，使用其子元素的实际尺寸
        const foDiv = foreignObject.querySelector('div')
        if (foDiv) {
          const rect = foDiv.getBoundingClientRect()
          contentWidth = rect.width
          contentHeight = rect.height
        }
      }

      // 如果无法获取内容尺寸，使用 getBBox 作为备选
      const labelBBox = label.getBBox()
      const finalWidth = contentWidth > 0 ? contentWidth : labelBBox.width
      const finalHeight = contentHeight > 0 ? contentHeight : labelBBox.height

      // 计算标签中心位置（基于 transform）
      const labelCenterX = translateX
      const labelCenterY = translateY
      const labelLeft = labelCenterX - finalWidth / 2
      const labelTop = labelCenterY - finalHeight / 2

      const labelParent = label.parentElement

      // ✅ 纯 CSS 方案：添加 CSS 类，由 CSS 隐藏装饰元素
      label.classList.add('edge-label-clean')

      // ✅ 创建白色背景 rect
      // 使用 requestAnimationFrame 确保 Mermaid 渲染完成后再设置
      requestAnimationFrame(() => {
        // 获取 label 的位置和大小
        try {
          const bbox = label.getBBox()
          
          // 创建 SVG rect 作为白色背景
          const bgRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
          
          bgRect.setAttribute('x', bbox.x)
          bgRect.setAttribute('y', bbox.y)
          bgRect.setAttribute('width', bbox.width)
          bgRect.setAttribute('height', bbox.height)
          bgRect.setAttribute('fill', '#ffffff')
          bgRect.setAttribute('fill-opacity', '1')
          bgRect.setAttribute('data-bg-rect', 'true')
          
          // 强制设置样式（覆盖 Mermaid classDef 的 fill:none）
          bgRect.style.setProperty('fill', '#ffffff', 'important')
          bgRect.style.setProperty('fill-opacity', '1', 'important')
          bgRect.style.setProperty('opacity', '1', 'important')
          bgRect.style.setProperty('display', 'block', 'important')
          bgRect.style.setProperty('visibility', 'visible', 'important')
          bgRect.style.setProperty('stroke', 'none', 'important')
          
          // 插入到最前面（作为背景）
          const firstChild = label.firstChild
          if (firstChild) {
            label.insertBefore(bgRect, firstChild)
          } else {
            label.appendChild(bgRect)
          }
        } catch (e) {
          console.warn('创建背景 rect 失败:', e)
        }
      })

      const rootGroup = labelParent?.parentElement
      const allEdgePathsInRoot = rootGroup?.querySelectorAll('.edgePath path, path.flowchart-link')

      let correspondingPath = null
      if (allEdgePathsInRoot && allEdgePathsInRoot.length > index) {
        correspondingPath = allEdgePathsInRoot[index]
      }

      if (!correspondingPath) {
        console.warn(`标签 ${index} 没有找到对应的连线path`)
        return
      }

      const pathLength = correspondingPath.getTotalLength()
      const startPoint = correspondingPath.getPointAtLength(0)
      const endPoint = correspondingPath.getPointAtLength(pathLength)

      const sampleCount = 50
      let nearestPoint = null
      let nearestDist = Infinity

      for (let i = 0; i <= sampleCount; i++) {
        const ratio = i / sampleCount
        const point = correspondingPath.getPointAtLength(pathLength * ratio)
        const dist = Math.hypot(point.x - labelCenterX, point.y - labelCenterY)
        if (dist < nearestDist) {
          nearestDist = dist
          nearestPoint = point
        }
      }

      const distToStart = Math.hypot(startPoint.x - labelCenterX, startPoint.y - labelCenterY)
      const distToEnd = Math.hypot(endPoint.x - labelCenterX, endPoint.y - labelCenterY)

      const useNearestPoint = nearestDist < Math.min(distToStart, distToEnd) ? nearestPoint : (distToStart < distToEnd ? startPoint : endPoint)

      const tailLine = document.createElementNS('http://www.w3.org/2000/svg', 'line')
      tailLine.setAttribute('x1', labelCenterX.toFixed(2))
      tailLine.setAttribute('y1', labelCenterY.toFixed(2))
      tailLine.setAttribute('x2', useNearestPoint.x.toFixed(2))
      tailLine.setAttribute('y2', useNearestPoint.y.toFixed(2))
      tailLine.setAttribute('stroke', '#333333')
      tailLine.setAttribute('stroke-width', '1.5')
      tailLine.setAttribute('stroke-dasharray', '4,3')
      tailLine.setAttribute('opacity', '0.8')

      const endMarker = document.createElementNS('http://www.w3.org/2000/svg', 'circle')
      endMarker.setAttribute('cx', useNearestPoint.x.toFixed(2))
      endMarker.setAttribute('cy', useNearestPoint.y.toFixed(2))
      endMarker.setAttribute('r', '3')
      endMarker.setAttribute('fill', '#333333')
      endMarker.setAttribute('opacity', '0.8')

      svg.appendChild(tailLine)
      svg.appendChild(endMarker)
    })
  }

  const addClickToClearHighlight = (svg, selectedElements) => {
    svg.addEventListener('click', (e) => {
      const target = e.target
      const isNode = target.closest('.node')
      const isEdgePath = target.closest('.edgePath') || target.classList.contains('flowchart-link')
      const isEdgeLabel = target.closest('.edgeLabel')

      if (!isNode && !isEdgePath && !isEdgeLabel) {
        clearHighlight(selectedElements)
      }
    })
  }

  const addMouseOverTooltips = (svg, relationDescriptions, diagramType) => {
    if (!svg) return

    const tooltip = createTooltipElement()
    const selectedElements = createSelectionState()
    const edgeLabels = getEdgeLabels(svg)

    // ✅ 纯 CSS 方案：不再需要 JavaScript 设置背景
    // setLabelBackground(edgeLabels)

    const { pathToRelationMap, realEdgePaths } = matchPathsToRelations(svg, edgeLabels, relationDescriptions)

    edgeLabels.forEach((label, index) => {
      setupLabelEvents(label, index, tooltip, relationDescriptions, pathToRelationMap, edgeLabels, selectedElements, svg, realEdgePaths)
    })

    realEdgePaths.forEach((edgePathInfo) => {
      setupPathEvents(edgePathInfo.path, tooltip, pathToRelationMap, edgeLabels, selectedElements, svg)
    })

    addTrailingDottedLines(svg, edgeLabels, diagramType)

    addClickToClearHighlight(svg, selectedElements)
  }

  return {
    addMouseOverTooltips
  }
}