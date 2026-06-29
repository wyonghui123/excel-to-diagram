import { useSvgStyle } from '../style/useSvgStyle.js'
import { useTooltip } from '../tooltip/useTooltip.js'
import { useAnnotation, useAnnotationOverlay } from '../annotation/index.js'
import { useInteraction } from '../interaction/useInteraction.js'
import { isBidirectionalLink } from '../syntax/_shared/arrowHelper.js'

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
   * [v34 修复] 使用精确匹配 (===) 而非 includes,
   *   因为 relationCode 常是子串 (如 'CALLS' 出现在 'RECALLS' 中),
   *   includes 会导致所有 edgeLabel 都被错误标为同一个 relationCode
   *
   * [v40.1 修复] 之前只匹配 link.relationCode / link.relationDesc, 不匹配 link.code (实例编码)
   *   后果: arch data 路径下, SVG label 显示的是 link.code (关系实例编码 e.g. "BO_INBOUND_BO_INBOUND_L_01"),
   *         而 addBidirectionalAttributes 通过 relationCode (类型编码 e.g. "BELONGS_TO") 来识别双向边
   *         → labelText ("BO_INBOUND...") !== link.relationCode ("BELONGS_TO")
   *         → data-relation-code 属性永远不设, 双向边无法被识别, marker-start 缺失
   *   修复: 同时匹配 link.code / link.relationCode / link.relationDesc,
   *         找到匹配后用 matchedLink.relationCode 设 data-relation-code (addBidirectionalAttributes 仍按 relationCode 匹配)
   */
  const addLinkCodeAttributes = (svgEl, diagramData) => {
    if (!diagramData || !diagramData.links) return

    const edgeLabels = svgEl.querySelectorAll('.edgeLabel')
    edgeLabels.forEach(edgeLabel => {
      const labelText = (edgeLabel.textContent || '').trim()
      if (!labelText) return

      // [v40.1 关键修复] 同时匹配 3 个字段 (优先级: code > relationCode > relationDesc)
      //   code: 关系实例编码 (arch data 路径下的 label 文本)
      //   relationCode: 关系类型编码 (Excel 导入 / 旧版本下的 label 文本)
      //   relationDesc: 关系描述 (兜底)
      const matchedLink = diagramData.links.find(link => {
        if (link.code && link.code === labelText) return true
        if (link.relationCode && link.relationCode === labelText) return true
        if (link.relationDesc && link.relationDesc === labelText) return true
        return false
      })

      if (matchedLink && matchedLink.relationCode) {
        const edgeGroup = edgeLabel.closest('g')
        if (edgeGroup) {
          edgeGroup.setAttribute('data-relation-code', matchedLink.relationCode)
        }
      }
    })

    // [v40.2 诊断] 输出标记的 edgeLabel 数量
    const labeledCount = svgEl.querySelectorAll('g.edgeLabel[data-relation-code]').length
    const sampleCodes = Array.from(svgEl.querySelectorAll('g.edgeLabel[data-relation-code]'))
      .slice(0, 5)
      .map(el => el.getAttribute('data-relation-code'))
    console.log('[v40.2 诊断] addLinkCodeAttributes: marked %d edgeLabels with data-relation-code, sample=%s',
      labeledCount, JSON.stringify(sampleCodes))
  }

  /**
   * [v34 双向支持] 添加 data-bidirectional 属性到双向边的 path 元素
   * 供 fixArrowMarkers 检测后设置 marker-start
   *
   * Mermaid 11 SVG 结构:
   *   svg
   *   ├─ g.edges.edgePaths  (容器, 35 子元素)
   *   │   └─ g.edgePath (单条边的 path 容器)
   *   │       └─ path
   *   └─ g.edgeLabels
   *       └─ g.edgeLabel  ← addLinkCodeAttributes 在此设 data-relation-code
   *
   * edgePath 和 edgeLabel 按 document 顺序一一对应 (都是 N 条)
   *
   * [v1.5 修复 2026-06-15] 改用 isBidirectionalLink() (来自 arrowHelper.js)
   *   数据库 relation_direction 存的是 'BIDIRECTIONAL' (英文 enum code)
   *   之前用 === '双向' (中文) 永远 false → 双边属性永远不设 → 双向边变成单向边
   */
  const addBidirectionalAttributes = (svgEl, diagramData) => {
    if (!diagramData || !diagramData.links) {
      console.log('[v40.2 诊断] addBidirectionalAttributes: no diagramData.links')
      return
    }

    // 1. 收集所有双向 link 的 relationCode (用 isBidirectionalLink 统一判断)
    const bidiCodes = new Set(
      (diagramData.links || [])
        .filter(link => isBidirectionalLink(link))
        .map(link => link.relationCode)
        .filter(Boolean)
    )
    console.log('[v40.2 诊断] addBidirectionalAttributes: totalLinks=%d, bidiCodes=%d, codes=%s',
      (diagramData.links || []).length, bidiCodes.size, JSON.stringify([...bidiCodes]))

    if (bidiCodes.size === 0) return

    // 2. 按 document 顺序收集所有带 data-relation-code 的 g.edgeLabel
    const labeledEls = Array.from(svgEl.querySelectorAll('g.edgeLabel[data-relation-code]'))
    if (labeledEls.length === 0) return

    // 3. 按 document 顺序收集所有 g.edgePath (单条边的 path 容器)
    const edgePathEls = Array.from(svgEl.querySelectorAll('g.edges.edgePaths > g.edgePath'))
    if (edgePathEls.length === 0) {
      // 兼容旧结构: path.flowchart-link 直接放在 svg 下
      const flowLinks = Array.from(svgEl.querySelectorAll('path.flowchart-link'))
      labeledEls.forEach((el, idx) => {
        const code = el.getAttribute('data-relation-code')
        if (!bidiCodes.has(code)) return
        if (flowLinks[idx]) {
          flowLinks[idx].setAttribute('data-bidirectional', 'true')
        }
      })
      return
    }

    // 4. 按索引配对: edgeLabel[i] ↔ edgePath[i]
    let bidiEdgesMarked = 0
    labeledEls.forEach((el, idx) => {
      const code = el.getAttribute('data-relation-code')
      if (!bidiCodes.has(code)) return
      const edgePathG = edgePathEls[idx]
      if (!edgePathG) return
      // 给该 g.edgePath 内所有 path 设 data-bidirectional
      const paths = edgePathG.querySelectorAll('path')
      paths.forEach(p => {
        p.setAttribute('data-bidirectional', 'true')
      })
      bidiEdgesMarked++
    })
    console.log('[v40.2 诊断] addBidirectionalAttributes: marked %d paths with data-bidirectional=true', bidiEdgesMarked)
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
   * 关键修复 v32：在 SVG 渲染完成后调用，重新计算 edgeLabel 的 foreignObject 尺寸
   * 必须在 Mermaid.run() 之后 + 浏览器布局完成（nextTick/requestAnimationFrame）之后调用
   * 因为要读取 innerDiv.getBoundingClientRect() 的实际值
   *
   * 安全策略（v33 改进）:
   *   - 测 labelBkg.getBoundingClientRect().width 作为内容真实宽度
   *   - 调整 foreignObject width 属性 + x 属性（x 对称偏移保持中心）
   *   - 同步调整 rect 背景框宽度
   *   - 跟 v22 fixNodeRectSize 端点错位 bug 的区别：保持中心点位置不变
   */
  const fixEdgeLabelSize = (svgEl) => {
    if (!svgEl) return
    // 强制 reflow 一次再读取
    void svgEl.getBoundingClientRect()
    svgStyle.fixEdgeLabelOverflow(svgEl)
    // [v40 关键修复] Mermaid 11.13.0 不支持 flowchart.labelPosition 配置
    // 强制把 edgeLabel 移到连线中点, 必须在 fixEdgeLabelOverflow 之后调用
    // (fixEdgeLabelOverflow 先调整了 foreignObject width, 需要读到正确宽度)
    svgStyle.forceEdgeLabelToMidpoint(svgEl)
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

    // [V_NEW 2026-06-29] 传递 annotation category 过滤 - 主线不受影响 (空数组 = 不过滤)
    const annotationFilter = annotationConfig.annotationCategoryFilter || []
    const annotationList = annotation.parseAnnotationsFromData(diagramData, diagramType, { filter: annotationFilter })

    // [DEBUG 2026-06-29 已清理, 避免 console spam]

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

    // [v34 关键修复] 必须在 applyStyleFixes (含 fixArrowMarkers) 之前
    //   调用 addLinkCodeAttributes + addBidirectionalAttributes,
    //   这样 fixArrowMarkers 才能看到 data-bidirectional='true' 并设置 marker-start
    if (props.diagramData) {
      addNodeCodeAttributes(svgEl, props.diagramData)
      addContainerCodeAttributes(svgEl, props.diagramData)
      addLinkCodeAttributes(svgEl, props.diagramData)
      addBidirectionalAttributes(svgEl, props.diagramData)
    }

    applyStyleFixes(svgEl, props.diagramType, mermaidContainer, props.diagramData?.textColor)
    addTooltips(svgEl, relationDescriptions, props.diagramType, hideTails)

    // 注意：之前 v22 加的 fixNodeRectSize 会修改 rect/foreignObject width/height
    // 但 mermaid ELK layout 是基于原 width 算 edge endpoint 位置
    // 改 rect 后 edge endpoint 仍然按原位置定位 → 端点错位 + 文字溢出
    // 关键回退：删 fixNodeRectSize，让 mermaid 自己负责 node sizing（更稳定）

    fixContainerTitleCenter(svgEl)

    reorderZoneRows(svgEl)

    if (props.annotationConfig) {
      renderAnnotationOverlay(svgEl, props.diagramData, props.diagramType, props.annotationConfig, nodeColorMappings)
    }

    // [v33 关键修复] 调用 fixEdgeLabelSize, 必须在 layout 完成后
    // 用 requestAnimationFrame 等浏览器完成 reflow
    // 之前 fixEdgeLabelSize 导出后从未调用, 导致 v32 CSS 修复只在初次渲染生效
    // ELK 二次布局/全屏切换后宽度变化时, 右边字符仍被截掉
    scheduleEdgeLabelFix(svgEl)
  }

  /**
   * [v33] 调度 edge label 宽度修复
   * 使用 requestAnimationFrame 等浏览器完成 reflow
   * 然后再补一次 (双 rAF) 应对某些浏览器的延迟 layout
   */
  const scheduleEdgeLabelFix = (svgEl) => {
    if (!svgEl) return
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          try {
            fixEdgeLabelSize(svgEl)
          } catch (e) {
            console.warn('[useSvgProcessor.scheduleEdgeLabelFix] failed:', e)
          }
        })
      })
    } else {
      // 非浏览器环境 (jsdom) 退化
      setTimeout(() => {
        try {
          fixEdgeLabelSize(svgEl)
        } catch (e) {
          console.warn('[useSvgProcessor.scheduleEdgeLabelFix] failed:', e)
        }
      }, 0)
    }
  }

  /**
   * [v32 2026-06-13] 清理 useSvgProcessor 注册的事件监听器
   * 调用 tooltip.cleanup() 释放 mouseleave/mouseover 等事件
   * 幂等设计: 多次调用安全 (tooltip.cleanup 内部清空 _cleanupFns 数组)
   * 修复: 之前存在两个 const cleanup 导致 SyntaxError
   */
  const cleanup = () => {
    if (tooltip && typeof tooltip.cleanup === 'function') {
      try {
        tooltip.cleanup()
      } catch (e) {
        console.warn('[useSvgProcessor.cleanup] tooltip.cleanup failed:', e)
      }
    }
  }

  return {
    fixViewBox,
    fixContainerTitleCenter,
    addNodeCodeAttributes,
    addContainerCodeAttributes,
    addLinkCodeAttributes,
    applyStyleFixes,
    fixEdgeLabelSize,
    addTooltips,
    renderAnnotationOverlay,
    setupCanvasLayout,
    processSvg,
    // [v34 双向支持] 导出 addBidirectionalAttributes 以便单测覆盖
    addBidirectionalAttributes,
    cleanup,
    // 关键导出 v26：导出 buildColorLegendData 让 HTML 导出器复用 legend 逻辑
    buildColorLegendData
  }
}