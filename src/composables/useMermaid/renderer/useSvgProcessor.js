import { useSvgStyle } from '../style/useSvgStyle.js'
import { useTooltip } from '../tooltip/useTooltip.js'
import { useAnnotation, useAnnotationOverlay } from '../annotation/index.js'
import { useInteraction } from '../interaction/useInteraction.js'

/**
 * SVG 后处理逻辑
 * @param {Object} options - 配置选项
 * @param {Object} options.svgEl - SVG 元素
 * @param {Object} options.props - 组件 props
 * @param {Object} options.relationDescriptions - 关系描述数组
 * @param {Object} options.mermaidContainer - mermaid 容器 ref
 * @param {Object} options.interaction - interaction composable
 */
export function useSvgProcessor(options) {
  const { svgStyle, tooltip, annotation, annotationOverlay } = {
    svgStyle: useSvgStyle(),
    tooltip: useTooltip(),
    annotation: useAnnotation(),
    annotationOverlay: useAnnotationOverlay(),
    ...options
  }

  /**
   * 修复 SVG ViewBox（处理负坐标）
   */
  const fixViewBox = (svgEl) => {
    const svgViewBox = svgEl.getAttribute('viewBox')
    if (svgViewBox) {
      const parts = svgViewBox.split(' ').map(Number)
      if (parts[0] < 0 || parts[1] < 0) {
        const padding = 20
        const newViewBox = `${parts[0] - padding} ${parts[1] - padding} ${parts[2] + padding * 2} ${parts[3] + padding * 2}`
        svgEl.setAttribute('viewBox', newViewBox)
      }
    }
    return svgEl
  }

  /**
   * 添加节点编码属性
   */
  const addNodeCodeAttributes = (svgEl, diagramData) => {
    if (!diagramData || !diagramData.nodes) return

    const allNodes = svgEl.querySelectorAll('.node')
    allNodes.forEach(node => {
      const nodeLabel = node.querySelector('.nodeLabel')
      if (nodeLabel) {
        const labelText = nodeLabel.textContent || ''
        const codeMatch = labelText.match(/\(([^)]+)\)/)
        const extractedCode = codeMatch ? codeMatch[1] : null

        let matchedNode = null
        if (extractedCode) {
          matchedNode = diagramData.nodes.find(n => n.code === extractedCode)
        }
        if (!matchedNode) {
          matchedNode = diagramData.nodes.find(n => labelText.includes(n.name))
        }

        if (matchedNode) {
          node.setAttribute('data-code', matchedNode.code || matchedNode.name)
        }
      }
    })
  }

  /**
   * 添加容器编码属性
   */
  const addContainerCodeAttributes = (svgEl, diagramData) => {
    if (!diagramData || !diagramData.serviceModules) return

    const subgraphs = svgEl.querySelectorAll('.subgraph, .cluster')
    subgraphs.forEach(subgraph => {
      const titleEl = subgraph.querySelector('.cluster-label, text')
      if (titleEl) {
        const titleText = titleEl.textContent || ''
        const titleMatch = titleText.match(/^([^\n(]+)/)
        const containerName = titleMatch ? titleMatch[1].trim() : titleText

        const matchedSM = diagramData.serviceModules.find(sm =>
          titleText.includes(sm.name) || containerName === sm.name
        )

        if (matchedSM && matchedSM.code) {
          subgraph.setAttribute('data-container-code', matchedSM.code)
        }
      }
    })
  }

  /**
   * 添加关系连线编码属性
   */
  const addLinkCodeAttributes = (svgEl, diagramData) => {
    if (!diagramData || !diagramData.links) return

    const edgeLabels = svgEl.querySelectorAll('.edgeLabel')
    edgeLabels.forEach(edgeLabel => {
      const labelText = edgeLabel.textContent || ''
      const matchedLink = diagramData.links.find(link =>
        labelText.includes(link.relationDesc || '') ||
        labelText.includes(link.relationCode || '')
      )
      if (matchedLink && matchedLink.relationCode) {
        const edgeGroup = edgeLabel.closest('g')
        if (edgeGroup) {
          edgeGroup.setAttribute('data-relation-code', matchedLink.relationCode)
        }
      }
    })
  }

  /**
   * 应用样式修复
   */
  const applyStyleFixes = (svgEl, diagramType, mermaidContainer, textColor) => {
    console.log('[applyStyleFixes] textColor:', textColor)
    svgStyle.fixArrowMarkers(svgEl, diagramType, mermaidContainer, textColor)
    svgStyle.fixLabelBackground(svgEl)
  }

  /**
   * 添加 Tooltip
   */
  const addTooltips = (svgEl, relationDescriptions, diagramType, hideTails = false) => {
    tooltip.addMouseOverTooltips(svgEl, relationDescriptions, diagramType, hideTails)
  }

  /**
   * 渲染备注叠加层
   */
  const renderAnnotationOverlay = (svgEl, diagramData, diagramType, annotationConfig, nodeColorMappings) => {
    if (!annotationConfig) return

    const annotationList = annotation.parseAnnotationsFromData(diagramData, diagramType)

    annotation.setConfig({
      panelPosition: annotationConfig.annotationPanelPosition || 'bottom',
      showIcons: annotationConfig.showAnnotationIcons || false
    })

    annotationOverlay.removeAnnotationLayers(svgEl)

    if (annotationList.length > 0) {
      const numberMap = annotation.buildNumberMap(annotationList)
      annotationOverlay.overlayNumberMarkers(svgEl, numberMap, annotationList)
      annotationOverlay.overlayAnnotationPanel(svgEl, annotationList, {
        position: annotationConfig.annotationPanelPosition || 'bottom',
        showIcons: annotationConfig.showAnnotationIcons || false
      })
      annotationOverlay.bindAnnotationInteraction(svgEl, annotationList)
    }

    // 渲染颜色图例
    if ((diagramType === 'serviceModule' || diagramType === 'businessObject') && diagramData) {
      const colorLegendData = buildColorLegendData(diagramData, nodeColorMappings, annotationConfig.centerScopeHighlight)
      if (colorLegendData && colorLegendData.length > 0) {
        annotationOverlay.overlayColorLegend(svgEl, colorLegendData, {
          position: annotationConfig.legendPosition || 'top-left'
        })
      }
    }
  }

  /**
   * 构建颜色图例数据
   */
  const buildColorLegendData = (diagramData, nodeColorMappings, centerScopeHighlight = true) => {
    const legendData = []
    const { nodes, colorGroupBy, centerScopeColor, centerObjectColor } = diagramData

    if (!nodes || nodes.length === 0) return legendData

    const colorMap = new Map()
    let hasCenterNodes = false

    nodes.forEach(node => {
      let groupKey = null
      if (colorGroupBy === 'subDomain') {
        groupKey = node.subDomain
      } else if (colorGroupBy === 'serviceModule') {
        groupKey = node.serviceModuleName || node.serviceModule || node.name
      } else {
        groupKey = node.domain
      }
      if (!groupKey) return

      if (centerScopeHighlight && node.isCenter) {
        hasCenterNodes = true
      }

      if (!colorMap.has(groupKey)) {
        let color = null
        if (nodeColorMappings && nodeColorMappings.length > 0) {
          const mapping = nodeColorMappings.find(m => m.nodeCode === node.code)
          if (mapping) {
            color = mapping.color
          }
        }
        if (!color) {
          color = node.color || '#e0e0e0'
        }

        if (!(centerScopeHighlight && node.isCenter)) {
          colorMap.set(groupKey, color)
        }
      }
    })

    nodes.forEach(node => {
      let groupKey = null
      if (colorGroupBy === 'subDomain') {
        groupKey = node.subDomain
      } else if (colorGroupBy === 'serviceModule') {
        groupKey = node.serviceModuleName || node.serviceModule || node.name
      } else {
        groupKey = node.domain
      }
      if (!groupKey || colorMap.has(groupKey)) return

      let color = null
      if (nodeColorMappings && nodeColorMappings.length > 0) {
        const mapping = nodeColorMappings.find(m => m.nodeCode === node.code)
        if (mapping) {
          color = mapping.color
        }
      }
      if (!color) {
        color = node.color || '#e0e0e0'
      }
      colorMap.set(groupKey, color)
    })

    // 先添加中心范围颜色项（如果有中心范围节点）
    if (hasCenterNodes) {
      legendData.push({
        name: '中心范围',
        color: centerScopeColor || centerObjectColor || '#EDEDED',
        isCenter: true
      })
    }

    // 再添加分组颜色项
    colorMap.forEach((color, name) => {
      legendData.push({ name, color })
    })

    return legendData
  }

  /**
   * 设置画布布局尺寸
   * 关键修复 v4：让 draggable/wrapper/mermaid-content 都 100% 覆盖 .mermaid-container，
   * 不再用 JS 算 fit scale，让 SVG 自身的 viewBox + CSS height:100% 自动按比例缩放。
   * mermaid-content 用 flex 居中（由 CSS 控制），不再用 absolute + transform。
   */
  const setupCanvasLayout = (mermaidWrapper, mermaidContainer, draggableArea) => {
    const wrapper = mermaidWrapper?.value || document.querySelector('.mermaid-wrapper')
    const draggable = draggableArea?.value || document.querySelector('.draggable-area')
    const content = document.querySelector('.mermaid-content')
    const pre = document.querySelector('pre.mermaid')
    const containerEl = mermaidContainer?.value || document.querySelector('.mermaid-container')

    if (!wrapper || !draggable || !content || !pre || !containerEl) return

    // 读取容器实际尺寸（首次渲染时容器可能尚未铺满，需要兜底）
    // 关键修复 v8：用 getBoundingClientRect() 强制 layout reflow，读取最新值
    // 避免 offsetWidth 缓存可能为旧值的问题
    const containerRect = containerEl.getBoundingClientRect()
    const containerWidth = Math.round(containerRect.width) || containerEl.offsetWidth || containerEl.clientWidth || 1000
    const containerHeight = Math.round(containerRect.height) || containerEl.offsetHeight || containerEl.clientHeight || 600

    // 关键修复 v4：draggable / wrapper 100% 覆盖容器，top-left 对齐
    // 不再用 1.5x 长边的正方形（之前会导致图表偏下/偏上、灰色背景裸露）
    wrapper.style.width = containerWidth + 'px'
    wrapper.style.height = containerHeight + 'px'
    wrapper.style.left = '0'
    wrapper.style.top = '0'
    wrapper.style.marginLeft = '0'
    wrapper.style.marginTop = '0'
    wrapper.style.boxSizing = 'border-box'

    draggable.style.width = containerWidth + 'px'
    draggable.style.height = containerHeight + 'px'
    draggable.style.left = '0'
    draggable.style.top = '0'
    draggable.style.marginLeft = '0'
    draggable.style.marginTop = '0'
    draggable.style.boxSizing = 'border-box'
    draggable.style.backgroundColor = '#F0F0F0'

    // 关键修复 v4：mermaid-content 不再 absolute 居中
    // 改用 CSS flex 居中（display: flex + align-items/justify-content: center）
    // 这样 SVG 100% 高度 + 浏览器按 viewBox 比例自动算宽度，图表天然 fit
    content.style.position = 'relative'
    content.style.width = '100%'
    content.style.height = '100%'
    content.style.transform = 'none'
    content.style.margin = '0'

    pre.style.width = '100%'  // 关键修复 v6：100% 容器，不要 auto（auto 会让 pre 收缩到 SVG intrinsic 2091.78，居中后溢出 mermaid-container 导致两侧白色背景）
    pre.style.height = '100%'
    pre.style.boxSizing = 'border-box'
    pre.style.padding = '0'
    pre.style.display = 'flex'
    pre.style.alignItems = 'center'
    pre.style.justifyContent = 'center'

    const svgEl = pre.querySelector('svg')
    if (svgEl) {
      // 关键修复 v6：让 SVG 100%×100% 容器，preserveAspectRatio="xMidYMid slice" 让图表 fill 容器不留白
      // 不再用 'auto' 收缩到 intrinsic（会溢出 mermaid-container）
      svgEl.style.height = '100%'
      svgEl.style.width = '100%'
      svgEl.style.maxWidth = 'none'
      svgEl.style.maxHeight = 'none'
      svgEl.setAttribute('preserveAspectRatio', 'xMidYMid slice')
    }

    // 关键诊断 v7：输出关键尺寸到 console，便于排查"全屏留白"问题
    console.log('[setupCanvasLayout] container:', containerWidth, 'x', containerHeight,
      '| wrapper:', wrapper.style.width, 'x', wrapper.style.height,
      '| draggable:', draggable.style.width, 'x', draggable.style.height,
      '| pre:', pre.style.width, 'x', pre.style.height,
      '| svg:', svgEl?.getAttribute('preserveAspectRatio'),
      '| containerEl.offset:', containerEl.offsetWidth, 'x', containerEl.offsetHeight)
  }

  /**
   * 重新排序分区布局的行
   */
  const reorderZoneRows = (svgEl) => {
    const rows = svgEl.querySelectorAll('[id^="flowchart-Row"]')
    if (rows.length === 0) return

    const rowArray = Array.from(rows)
    const rowPositions = rowArray.map(row => {
      const transform = row.getAttribute('transform') || ''
      const match = transform.match(/translate\(([^,]+),\s*([^)]+)\)/)
      if (match) {
        return {
          row,
          y: parseFloat(match[2]),
          rowNum: parseInt(row.id.match(/Row(\d+)/)?.[1] || '0')
        }
      }
      return { row, y: 0, rowNum: 0 }
    })

    rowPositions.sort((a, b) => a.rowNum - b.rowNum)

    const parent = rowArray[0].parentElement
    if (!parent) return

    rowPositions.forEach(({ row, y, rowNum }) => {
      const currentTransform = row.getAttribute('transform') || ''
      const match = currentTransform.match(/translate\(([^,]+),\s*([^)]+)\)/)
      if (match) {
        const x = parseFloat(match[1])
        const newY = rowNum * 200
        row.setAttribute('transform', `translate(${x}, ${newY})`)
      }
    })
  }

  /**
   * 修复 ELK 布局下嵌套容器的边界和间距问题
   * ELK 引擎在处理嵌套 subgraph 时，可能不会正确计算容器的边界框
   */
  const fixContainerTitleCenter = (svgEl) => {
    const allClusters = svgEl.querySelectorAll('.cluster')
    const allSubgraphs = svgEl.querySelectorAll('.subgraph')
    const allContainers = [...allClusters, ...allSubgraphs]

    if (allContainers.length === 0) return

    allContainers.forEach(container => {
      const labelEl = container.querySelector('.cluster-label, .subgraph-label')

      if (!labelEl) return

      const fo = labelEl.querySelector('foreignObject')
      if (fo) {
        const innerDiv = fo.querySelector('div')
        if (innerDiv) {
          innerDiv.style.textAlign = 'center'
          innerDiv.style.marginLeft = '0'
          innerDiv.style.paddingLeft = '0'
        }
        
        const pEls = fo.querySelectorAll('p')
        pEls.forEach((el) => {
          el.style.textAlign = 'center'
          el.style.margin = '0'
          el.style.padding = '0'
        })
      } else {
        const textEl = labelEl.querySelector('text')
        if (textEl) {
          textEl.setAttribute('text-anchor', 'middle')
        }
      }
    })
  }

  /**
   * 完整的后处理流程
   * 注意：此函数只处理 SVG 元素，不包含交互设置（交互在组件中单独调用）
   */
  const processSvg = (svgEl, props, relationDescriptions, mermaidContainer, nodeColorMappings) => {
    console.log('[processSvg] START, svgEl:', !!svgEl, 'layoutEngine:', props?.layoutEngine)
    if (!svgEl) {
      console.log('[processSvg] early return: svgEl is falsy')
      return
    }

    const hideTails = props.layoutEngine === 'elk' || props.diagramData?.hideLinkLabelTails === true

    fixViewBox(svgEl)
    applyStyleFixes(svgEl, props.diagramType, mermaidContainer, props.diagramData?.textColor)
    addTooltips(svgEl, relationDescriptions, props.diagramType, hideTails)

    fixContainerTitleCenter(svgEl)

    reorderZoneRows(svgEl)

    if (props.diagramData) {
      addNodeCodeAttributes(svgEl, props.diagramData)
      addContainerCodeAttributes(svgEl, props.diagramData)
      addLinkCodeAttributes(svgEl, props.diagramData)
    }

    if (props.annotationConfig) {
      renderAnnotationOverlay(svgEl, props.diagramData, props.diagramType, props.annotationConfig, nodeColorMappings)
    }
  }

  return {
    fixViewBox,
    fixContainerTitleCenter,
    addNodeCodeAttributes,
    addContainerCodeAttributes,
    addLinkCodeAttributes,
    applyStyleFixes,
    addTooltips,
    renderAnnotationOverlay,
    setupCanvasLayout,
    processSvg
  }
}