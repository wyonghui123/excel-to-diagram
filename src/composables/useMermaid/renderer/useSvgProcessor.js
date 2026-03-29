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
  const applyStyleFixes = (svgEl, diagramType, mermaidContainer) => {
    svgStyle.fixArrowMarkers(svgEl, diagramType, mermaidContainer)
    svgStyle.fixLabelBackground(svgEl)
  }

  /**
   * 添加 Tooltip
   */
  const addTooltips = (svgEl, relationDescriptions, diagramType) => {
    tooltip.addMouseOverTooltips(svgEl, relationDescriptions, diagramType)
  }

  /**
   * 渲染备注叠加层
   */
  const renderAnnotationOverlay = (svgEl, diagramData, diagramType, annotationConfig) => {
    if (!annotationConfig) return

    const annotationList = annotation.parseAnnotationsFromData(diagramData, diagramType)
    if (annotationList.length === 0) return

    const numberMap = annotation.buildNumberMap(annotationList)

    annotation.setConfig({
      panelPosition: annotationConfig.annotationPanelPosition || 'bottom',
      showIcons: annotationConfig.showAnnotationIcons || false
    })

    annotationOverlay.removeAnnotationLayers(svgEl)
    annotationOverlay.overlayNumberMarkers(svgEl, numberMap, annotationList)
    annotationOverlay.overlayAnnotationPanel(svgEl, annotationList, {
      position: annotationConfig.annotationPanelPosition || 'bottom',
      showIcons: annotationConfig.showAnnotationIcons || false
    })
    annotationOverlay.bindAnnotationInteraction(svgEl, annotationList)
  }

  /**
   * 设置画布布局尺寸
   */
  const setupCanvasLayout = (mermaidWrapper, mermaidContainer, draggableArea) => {
    const wrapper = mermaidWrapper?.value || document.querySelector('.mermaid-wrapper')
    const draggable = draggableArea?.value || document.querySelector('.draggable-area')
    const content = document.querySelector('.mermaid-content')
    const pre = document.querySelector('pre.mermaid')

    if (!wrapper || !draggable || !content || !pre) return

    const canvasSize = 8000
    const skySize = canvasSize * 1.5

    wrapper.style.width = skySize + 'px'
    wrapper.style.height = skySize + 'px'
    wrapper.style.left = '50%'
    wrapper.style.top = '50%'
    wrapper.style.marginLeft = (-skySize / 2) + 'px'
    wrapper.style.marginTop = (-skySize / 2) + 'px'
    wrapper.style.boxSizing = 'border-box'

    draggable.style.width = canvasSize + 'px'
    draggable.style.height = canvasSize + 'px'
    draggable.style.left = '50%'
    draggable.style.top = '50%'
    draggable.style.marginLeft = (-canvasSize / 2) + 'px'
    draggable.style.marginTop = (-canvasSize / 2) + 'px'
    draggable.style.boxSizing = 'border-box'
    draggable.style.backgroundColor = '#F0F0F0'

    content.style.width = 'auto'
    content.style.height = 'auto'
    content.style.position = 'absolute'
    content.style.top = '50%'
    content.style.left = '50%'
    content.style.transform = 'translate(-50%, -50%)'

    pre.style.width = 'auto'
    pre.style.height = 'auto'
    pre.style.boxSizing = 'border-box'

    const svgEl = pre.querySelector('svg')
    if (svgEl) {
      svgEl.style.width = 'auto'
      svgEl.style.height = 'auto'
    }
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
   * 完整的后处理流程
   * 注意：此函数只处理 SVG 元素，不包含交互设置（交互在组件中单独调用）
   */
  const processSvg = (svgEl, props, relationDescriptions, mermaidContainer) => {
    if (!svgEl) return

    fixViewBox(svgEl)
    applyStyleFixes(svgEl, props.diagramType, mermaidContainer)
    addTooltips(svgEl, relationDescriptions, props.diagramType)
    
    reorderZoneRows(svgEl)

    if (props.diagramData) {
      addNodeCodeAttributes(svgEl, props.diagramData)
      addContainerCodeAttributes(svgEl, props.diagramData)
      addLinkCodeAttributes(svgEl, props.diagramData)
    }

    if (props.annotationConfig) {
      renderAnnotationOverlay(svgEl, props.diagramData, props.diagramType, props.annotationConfig)
    }
  }

  return {
    fixViewBox,
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