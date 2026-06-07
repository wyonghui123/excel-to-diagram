const CONTAINER_TITLE_KEYWORDS = [
  '采购', '寻源', '合同', '价格', '任务', '供应商', '销售', '其他'
]

export function useSvgStyle() {
  const validateContainerTitles = (svg) => {
    if (!svg) return

    const allTextElements = svg.querySelectorAll('text, tspan')
    const allHtmlElements = svg.querySelectorAll('.cluster span, .cluster-label span, .subgraph span, .subgraph-label span, .cluster p, .cluster-label p, .subgraph p, .subgraph-label p')

    let validCount = 0
    let totalCount = 0

    const processElement = (el) => {
      totalCount++
      const content = el.textContent || ''
      const parentClass = el.parentElement?.getAttribute('class') || ''
      const grandparentClass = el.parentElement?.parentElement?.getAttribute('class') || ''
      const greatGrandparentClass = el.parentElement?.parentElement?.parentElement?.getAttribute('class') || ''
      const greatGreatGrandparentClass = el.parentElement?.parentElement?.parentElement?.parentElement?.getAttribute('class') || ''

      const isContainerTitle = CONTAINER_TITLE_KEYWORDS.some(keyword => content.includes(keyword)) ||
        parentClass.includes('subgraph') || parentClass.includes('cluster') ||
        parentClass.includes('label') || parentClass.includes('nodeLabel') ||
        grandparentClass.includes('subgraph') || grandparentClass.includes('cluster') ||
        greatGrandparentClass.includes('subgraph') || greatGrandparentClass.includes('cluster') ||
        greatGreatGrandparentClass.includes('subgraph') || greatGreatGrandparentClass.includes('cluster')

      if (isContainerTitle) {
        validCount++
        // 样式已移至 CSS 控制，这里只做验证
      }
    }

    allTextElements.forEach(processElement)
    allHtmlElements.forEach(processElement)

    fixForeignObjectWidth(svg)
  }

  const fixForeignObjectWidth = (svg) => {
    const foreignObjects = svg.querySelectorAll('.cluster-label foreignObject, .subgraph foreignObject, .cluster foreignObject')

    foreignObjects.forEach((fo) => {
      const innerDiv = fo.querySelector('div')
      if (!innerDiv) return

      // 获取文本内容
      const textContent = innerDiv.textContent || ''
      
      // 检查是否包含换行符（由 formatContainerTitle 添加）
      const hasNewLine = textContent.includes('\n')
      
      // 设置 foreignObject 样式
      fo.style.overflow = 'visible'
      
      // 设置内部 div 样式
      innerDiv.style.marginLeft = '0'
      innerDiv.style.transformOrigin = 'center center'
      innerDiv.style.whiteSpace = hasNewLine ? 'pre-line' : 'nowrap'
      innerDiv.style.textAlign = 'center'
      innerDiv.style.lineHeight = hasNewLine ? '1.3' : '1.2'
      
      // 多行标题时增加一些内边距
      if (hasNewLine) {
        innerDiv.style.padding = '4px 8px'
      }
    })
  }

  const fixArrowMarkers = (svg, diagramType, mermaidContainerRef, textColor) => {
    let defs = svg.querySelector('defs')
    if (!defs) {
      defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs')
      svg.insertBefore(defs, svg.firstChild)
    }

    validateContainerTitles(svg)

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

    // 只清除样式，不设置新样式（样式已移至 CSS）
    const textElements = svg.querySelectorAll('text, tspan')
    textElements.forEach((el) => {
      el.style.removeProperty('font-style')
      el.removeAttribute('font-style')
      el.style.removeProperty('transform')
    })

    const foreignObjects = svg.querySelectorAll('.cluster foreignObject, .subgraph foreignObject')

    foreignObjects.forEach((fo) => {
      const divEl = fo.querySelector('div')
      if (divEl) {
        divEl.style.textAlign = 'center'
        divEl.style.marginLeft = '0'
        divEl.style.paddingLeft = '0'
      }
      // 样式已移至 CSS，不再设置内联样式
    })

    fixForeignObjectWidth(svg)

    updateNodeStyles(svg, textColor)
    updateClusterStyles(svg, textColor)

    // 使用 MutationObserver 替代 setTimeout
    waitForRender(mermaidContainerRef, () => {
      const svgFinal = mermaidContainerRef?.value?.querySelector('svg')
      if (svgFinal) {
        validateContainerTitles(svgFinal)
      }
    })

    if (diagramType === 'serviceModule') {
      const observer = new MutationObserver((mutations) => {
        const currentSvg = mermaidContainerRef?.value?.querySelector('svg')
        if (currentSvg) {
          const textElements = currentSvg.querySelectorAll('text, tspan')
          if (textElements.length > 0) {
            validateContainerTitles(currentSvg)
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

  const waitForRender = (mermaidContainerRef, callback) => {
    let attempts = 0
    const maxAttempts = 10
    const checkInterval = 200

    const tryCallback = () => {
      const svg = mermaidContainerRef?.value?.querySelector('svg')
      if (svg && svg.querySelectorAll('text, tspan').length > 0) {
        callback()
        return true
      }
      attempts++
      if (attempts < maxAttempts) {
        setTimeout(tryCallback, checkInterval)
      } else {
        console.warn('[waitForRender] 最大重试次数已达，跳过回调')
      }
      return false
    }

    tryCallback()
  }

  const updateNodeStyles = (svg, textColorSetting) => {
    const textColorMap = {
      'black': '#000000',
      'gray': '#666666',
      'white': '#FFFFFF'
    }
    const nodeTextColor = textColorMap[textColorSetting] || '#000000'
    console.log('[updateNodeStyles] textColorSetting:', textColorSetting, '-> nodeTextColor:', nodeTextColor)

    svg.style.setProperty('--node-text-color', nodeTextColor)

    const nodeLabels = svg.querySelectorAll('.nodeLabel')
    console.log('[updateNodeStyles] Found .nodeLabel elements:', nodeLabels.length)

    let processedCount = 0
    nodeLabels.forEach((label) => {
      console.log('[updateNodeStyles] Processing label:', label.className, 'parent:', label.parentElement?.className)
      label.style.cssText = `color: ${nodeTextColor} !important; fill: ${nodeTextColor} !important;`

      const pElements = label.querySelectorAll('p, span')
      pElements.forEach((p) => {
        p.style.cssText = `color: ${nodeTextColor} !important; fill: ${nodeTextColor} !important;`
      })

      processedCount++
    })
    console.log('[updateNodeStyles] Processed nodes:', processedCount)

    const allTextInSvg = svg.querySelectorAll('text, tspan')
    console.log('[updateNodeStyles] Found text/tspan elements:', allTextInSvg.length)
    allTextInSvg.forEach((el) => {
      el.setAttribute('fill', nodeTextColor)
      el.style.cssText = `fill: ${nodeTextColor} !important;`
    })
  }

  const updateClusterStyles = (svg, textColorSetting) => {
    const textColorMap = {
      'black': '#000000',
      'gray': '#666666',
      'white': '#FFFFFF'
    }
    const clusterTextColor = textColorMap[textColorSetting] || '#000000'
    console.log('[updateClusterStyles] textColorSetting:', textColorSetting, '-> clusterTextColor:', clusterTextColor)

    svg.style.setProperty('--cluster-text-color', clusterTextColor)

    const clusters = svg.querySelectorAll('.cluster, .subgraph')
    console.log('[updateClusterStyles] Found .cluster/.subgraph elements:', clusters.length)

    clusters.forEach((cluster) => {
      const labels = cluster.querySelectorAll('.cluster-label, .subgraph-label, .label, text')
      labels.forEach((label) => {
        const tagName = label.tagName?.toLowerCase()
        if (tagName === 'text') {
          label.setAttribute('fill', clusterTextColor)
          label.style.cssText = `fill: ${clusterTextColor} !important;`
        } else if (tagName === 'div' || tagName === 'p' || tagName === 'span') {
          label.style.cssText = `color: ${clusterTextColor} !important;`
        }
      })

      const foreignObjects = cluster.querySelectorAll('foreignObject')
      foreignObjects.forEach((fo) => {
        const div = fo.querySelector('div')
        if (div) {
          div.style.cssText = `color: ${clusterTextColor} !important;`
        }
        const pElements = fo.querySelectorAll('p, span')
        pElements.forEach((el) => {
          el.style.cssText = `color: ${clusterTextColor} !important;`
        })
      })

      const nodeLabels = cluster.querySelectorAll('.nodeLabel')
      nodeLabels.forEach((label) => {
        label.style.cssText = `color: ${clusterTextColor} !important; fill: ${clusterTextColor} !important;`
      })

      const textElements = cluster.querySelectorAll('text')
      textElements.forEach((el) => {
        el.setAttribute('fill', clusterTextColor)
        el.style.cssText = `fill: ${clusterTextColor} !important;`
      })
    })

    const standaloneNodes = svg.querySelectorAll('.node:not(.cluster *)')
    standaloneNodes.forEach((node) => {
      const label = node.querySelector('.nodeLabel')
      if (label) {
        label.style.cssText = `color: ${clusterTextColor} !important; fill: ${clusterTextColor} !important;`
      }
    })
  }

  const fixLabelBackground = (svg) => {
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
  }

  return {
    validateContainerTitles,
    fixArrowMarkers,
    updateNodeStyles,
    updateClusterStyles,
    fixLabelBackground,
    // 向后兼容别名
    applyContainerTitleItalic: validateContainerTitles
  }
}
