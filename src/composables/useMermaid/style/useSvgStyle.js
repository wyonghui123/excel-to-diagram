const CONTAINER_TITLE_KEYWORDS = [
  '采购', '寻源', '合同', '价格', '任务', '供应商', '销售', '其他'
]

export function useSvgStyle() {
  const applyContainerTitleItalic = (svg) => {
    if (!svg) return

    const allTextElements = svg.querySelectorAll('text, tspan')
    const allHtmlElements = svg.querySelectorAll('.cluster span, .cluster-label span, .subgraph span, .subgraph-label span, .cluster p, .cluster-label p, .subgraph p, .subgraph-label p')

    const processElement = (el) => {
      const content = el.textContent || ''
      const parentClass = el.parentElement?.getAttribute('class') || ''
      const grandparentClass = el.parentElement?.parentElement?.getAttribute('class') || ''

      const isContainerTitle = CONTAINER_TITLE_KEYWORDS.some(keyword => content.includes(keyword)) ||
        parentClass.includes('subgraph') || parentClass.includes('cluster') ||
        parentClass.includes('label') ||
        grandparentClass.includes('subgraph') || grandparentClass.includes('cluster')

      if (isContainerTitle) {
        el.style.fontStyle = 'italic'
        el.style.transform = 'skewX(-10deg)'
        el.style.webkitTransform = 'skewX(-10deg)'
        el.style.transformOrigin = 'left center'
      } else {
        el.style.fontStyle = 'normal'
        el.style.transform = 'none'
      }
    }

    allTextElements.forEach(processElement)
    allHtmlElements.forEach(processElement)

    fixForeignObjectWidth(svg)
  }

  const fixForeignObjectWidth = (svg) => {
    const foreignObjects = svg.querySelectorAll('.cluster-label foreignObject, .subgraph foreignObject, .cluster foreignObject')

    foreignObjects.forEach((fo) => {
      const currentWidth = parseFloat(fo.getAttribute('width') || 0)
      const currentHeight = parseFloat(fo.getAttribute('height') || 0)

      const skewCompensation = currentHeight * Math.tan(10 * Math.PI / 180)

      const newWidth = currentWidth + skewCompensation + 15

      fo.setAttribute('width', newWidth)
      fo.style.width = newWidth + 'px'
      fo.style.overflow = 'visible'

      const innerDiv = fo.querySelector('div')
      if (innerDiv) {
        innerDiv.style.marginLeft = (skewCompensation + 5) + 'px'
        innerDiv.style.transformOrigin = 'left center'
      }
    })
  }

  const fixArrowMarkers = (svg, diagramType, mermaidContainerRef) => {
    let defs = svg.querySelector('defs')
    if (!defs) {
      defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
      svg.insertBefore(defs, svg.firstChild)
    }

    applyContainerTitleItalic(svg)

    const paths = svg.querySelectorAll('.flowchart-link path, .edgePath path, path[class*="edge"]')
    const colorMap = new Map()

    paths.forEach((path) => {
      const strokeColor = path.getAttribute('stroke') || path.style.stroke || '#333'

      if (!colorMap.has(strokeColor)) {
        const markerId = `arrowhead-${strokeColor.replace(/[^a-zA-Z0-9]/g, '')}`
        colorMap.set(strokeColor, markerId)

        let existingMarker = defs.querySelector(`#${markerId}`)
        if (existingMarker) {
          existingMarker.remove()
        }

        const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker')
        marker.setAttribute('id', markerId)
        marker.setAttribute('markerWidth', '8')
        marker.setAttribute('markerHeight', '6')
        marker.setAttribute('refX', '8')
        marker.setAttribute('refY', '3')
        marker.setAttribute('orient', 'auto')
        marker.setAttribute('markerUnits', 'strokeWidth')

        const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon')
        polygon.setAttribute('points', '0 0, 8 3, 0 6')
        polygon.setAttribute('fill', strokeColor)
        polygon.setAttribute('stroke', 'none')

        marker.appendChild(polygon)
        defs.appendChild(marker)
      }

      path.removeAttribute('marker-end')
      const markerId = colorMap.get(strokeColor)
      path.setAttribute('marker-end', `url(#${markerId})`)
    })

    const allSvgElements = svg.querySelectorAll('*')

    allSvgElements.forEach((el) => {
      el.style.removeProperty('font-style')
      el.removeAttribute('font-style')
      el.style.removeProperty('transform')

      if (el.tagName === 'text' || el.tagName === 'tspan') {
        const content = el.textContent || ''
        const parentClass = el.parentElement?.getAttribute('class') || ''

        const isContainerTitle = CONTAINER_TITLE_KEYWORDS.some(keyword => content.includes(keyword)) ||
          parentClass.includes('subgraph') || parentClass.includes('cluster') ||
          parentClass.includes('label')

        if (isContainerTitle) {
          el.style.fontStyle = 'italic'
          el.setAttribute('font-style', 'italic')
          el.style.transform = 'skewX(-10deg)'
          el.style.webkitTransform = 'skewX(-10deg)'
        } else {
          el.style.fontStyle = 'normal'
          el.setAttribute('font-style', 'normal')
          el.style.transform = 'none'
        }
      }
    })

    const htmlClusterTitles = document.querySelectorAll('.trae-browser-inspect-draggable, .cluster-title, .subgraph-title, p[class*="cluster"], p[class*="subgraph"]')
    htmlClusterTitles.forEach((title) => {
      title.style.fontSize = '28px'
      title.style.fontWeight = '700'
      title.style.fontStyle = 'italic'
    })

    const foreignObjects = svg.querySelectorAll('.cluster foreignObject, .subgraph foreignObject')

    foreignObjects.forEach((fo) => {
      const allElements = fo.querySelectorAll('*')

      allElements.forEach((el) => {
        el.style.fontStyle = 'italic'
        el.style.transform = 'skewX(-10deg)'
        el.style.webkitTransform = 'skewX(-10deg)'
        el.style.transformOrigin = 'left center'
      })
    })

    fixForeignObjectWidth(svg)

    updateNodeStyles(svg, diagramType)

    setTimeout(() => {
      const svgFinal = mermaidContainerRef?.value?.querySelector('svg')
      if (svgFinal) {
        applyContainerTitleItalic(svgFinal)
      }
    }, 1200)

    if (diagramType === 'serviceModule') {
      const observer = new MutationObserver((mutations) => {
        const currentSvg = mermaidContainerRef?.value?.querySelector('svg')
        if (currentSvg) {
          const textElements = currentSvg.querySelectorAll('text, tspan')
          if (textElements.length > 0) {
            applyContainerTitleItalic(currentSvg)
          }
        }
      })

      observer.observe(mermaidContainerRef.value, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['style', 'class']
      })
    }
  }

  const updateNodeStyles = (svg, textColorSetting) => {
    const textColorMap = {
      'black': '#000000',
      'gray': '#666666',
      'white': '#FFFFFF'
    }
    const nodeTextColor = textColorMap[textColorSetting] || '#000000'

    const nodes = svg.querySelectorAll('.node')

    nodes.forEach((node) => {
      if (node.closest('.cluster')) return

      const label = node.querySelector('.nodeLabel, text')
      if (label) {
        label.style.fontSize = '18px'
        label.style.fontWeight = 'bold'
        label.style.fill = nodeTextColor
        label.style.color = nodeTextColor
        label.style.textAnchor = 'middle'
        label.style.dominantBaseline = 'middle'
      }
    })
  }

  const fixLabelBackground = (svg) => {
    setTimeout(() => {
      const edgeLabels = svg.querySelectorAll('.edgeLabel')
      edgeLabels.forEach((label) => {
        const bgRect = label.querySelector('rect.background')
        if (bgRect) {
          bgRect.setAttribute('fill', '#ffffff')
          bgRect.style.fill = '#ffffff'
        }
        label.style.background = '#ffffff'
        label.style.backgroundColor = '#ffffff'
      })
    }, 100)
  }

  return {
    applyContainerTitleItalic,
    fixArrowMarkers,
    updateNodeStyles,
    fixLabelBackground
  }
}