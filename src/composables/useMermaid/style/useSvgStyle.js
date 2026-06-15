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

        // [v34 双向支持] 同步创建 source 端 marker (refX=0, orient=auto-start-reverse)
        const sourceMarkerId = `arrowhead-source-${strokeColor.replace(/[^a-zA-Z0-9]/g, '')}`
        let existingSourceMarker = defs.querySelector(`#${sourceMarkerId}`)
        if (existingSourceMarker) {
          existingSourceMarker.remove()
        }
        const sourceMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker')
        sourceMarker.setAttribute('id', sourceMarkerId)
        sourceMarker.setAttribute('markerWidth', '8')
        sourceMarker.setAttribute('markerHeight', '6')
        sourceMarker.setAttribute('refX', '0')           // source 端 refX=0
        sourceMarker.setAttribute('refY', '3')
        sourceMarker.setAttribute('orient', 'auto-start-reverse')  // 反向
        sourceMarker.setAttribute('markerUnits', 'strokeWidth')
        const sourcePolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon')
        sourcePolygon.setAttribute('points', '0 0, 8 3, 0 6')
        sourcePolygon.setAttribute('fill', strokeColor)
        sourcePolygon.setAttribute('stroke', 'none')
        sourceMarker.appendChild(sourcePolygon)
        defs.appendChild(sourceMarker)
      }

      // [v34 双向支持] 检测 path 是否双向（通过 Mermaid 原生 marker-start 或 data-bidirectional）
    const isBidi =
      path.getAttribute('data-bidirectional') === 'true' ||
      path.getAttribute('marker-start') !== null

    path.removeAttribute('marker-end')
    const markerId = colorMap.get(strokeColor)
    path.setAttribute('marker-end', `url(#${markerId})`)

    if (isBidi) {
      // 双向：额外设 marker-start (source 端)
      const strokeKey = strokeColor.replace(/[^a-zA-Z0-9]/g, '')
      path.setAttribute('marker-start', `url(#arrowhead-source-${strokeKey})`)
      // [v40.2 诊断] 记录双向边被标记的情况
      if (path.getAttribute('data-bidirectional') === 'true') {
        console.log('[v40.2 诊断] fixArrowMarkers: bidi path data-bidirectional=true, marker-start=url(#arrowhead-source-%s)', strokeKey)
      }
    } else {
      // 单向：主动清除 marker-start 残留
      path.removeAttribute('marker-start')
    }
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

  /**
   * 关键修复 v32 + v33：修复 edgeLabel 文字被右侧截断的问题
   * 根本原因：
   *   Mermaid 给 foreignObject 设的 width 是基于无 padding 的 labelBkg 计算的
   *   CSS 加 padding: 4px 8px (16px) 后，内容实际需要 width + 16px
   *   即使 overflow:visible 也会被父 g.edgeLabel / SVG viewBox 裁剪
   *
   * 修复策略（v33 关键改进）：
   *   1. CSS: 解除 max-width / 设置 overflow:visible (跟之前一样)
   *   2. JS 测宽: 读 labelBkg.getBoundingClientRect().width 作为内容实际宽度
   *   3. 改 foreignObject width 属性 = 内容宽度 + 缓冲
   *   4. 调整 foreignObject x 属性, 保持中心点位置不变 (避免端点错位)
   *   5. 同步调整 <g class="label"> 内的 <rect> 宽度 (背景框)
   *
   * 重要：调整 x 保持中心点对齐, 这样不破坏 edge endpoint 位置
   *       跟 v22 fixNodeRectSize 端点错位 bug 的区别: x 对称偏移
   */
  const fixEdgeLabelOverflow = (svg) => {
    if (!svg) return

    // 只查询 g.edgeLabel 内的 foreignObject
    const edgeLabels = svg.querySelectorAll('g.edgeLabel')
    if (edgeLabels.length === 0) return

    edgeLabels.forEach((edgeLabel) => {
      const foreignObject = edgeLabel.querySelector('foreignObject')
      if (!foreignObject) return

      // Mermaid 输出: foreignObject > div.labelBkg > span.edgeLabel > p
      // 只动 .labelBkg 自己的样式，绝不往下走 (避免影响节点/容器的同名 .edgeLabel span)
      const labelBkg = foreignObject.querySelector(':scope > div')
      if (!labelBkg || !labelBkg.classList.contains('labelBkg')) return

      // 解除 mermaid 的 max-width/white-space 限制
      // 用 !important 优先级，确保覆盖 Mermaid 内联 style
      labelBkg.style.setProperty('max-width', 'none', 'important')
      labelBkg.style.setProperty('white-space', 'nowrap', 'important')
      labelBkg.style.setProperty('overflow', 'visible', 'important')
      labelBkg.style.setProperty('box-sizing', 'border-box', 'important')
      // [v40.4 修复] 之前 padding: 4px 8px 让白底 div 比文字大 16x8 px
      //   改成 0, 让 div 跟文字本身等大, 白底紧贴文字 (背景由 useTooltip.js 的 bgRect 提供)
      labelBkg.style.setProperty('padding', '0', 'important')

      // 显式设置 text-align（防御性，正常情况 Mermaid 已设）
      labelBkg.style.setProperty('text-align', 'center', 'important')

      // 显式设置 display（防御性，正常情况 Mermaid 已设 table-cell）
      labelBkg.style.setProperty('display', 'table-cell', 'important')

      foreignObject.style.setProperty('overflow', 'visible', 'important')

      // [v33 关键改进] 测宽 + 调整 foreignObject width
      // 必须等 layout 完成后才能读到正确 getBoundingClientRect()
      // 调用方 fixEdgeLabelSize 已用 requestAnimationFrame 强制 reflow
      //
      // [v40.8 关键修复] viewport 像素 != SVG 单位!
      //   之前 v40 直接把 labelBkg.viewport.width (像素) 当成 SVG 单位设给 foreignObject width
      //   当 SVG 使用 xMidYMid slice (Mermaid 11 默认), 实际有效缩放 = max(scaleX, scaleY) ≈ scaleY
      //   labelBkg viewport width = 64.60px  →  正确 SVG width = 64.60 / 0.349 = 185 SVG 单位
      //   错误设置 width=69 SVG → viewport 24px, 比 labelBkg 实际宽度小 2.7 倍
      //   → labelBkg 撑出 foreignObject 右边, 文字中心相对 path 中点右偏 20-100px
      //   修复: 用 foreignObject.getCTM() 获取真实 SVG→viewport 缩放, 把 viewport 像素换算成 SVG 单位
      let measuredWidthVp = 0
      try {
        const rect = labelBkg.getBoundingClientRect()
        measuredWidthVp = rect.width
      } catch (e) {
        // jsdom 等无 layout 环境: 退回到 scrollWidth
        measuredWidthVp = labelBkg.scrollWidth || 0
      }

      if (measuredWidthVp > 0) {
        // [v40.8] 计算 effective scale (SVG→viewport)
        // 优先用 foreignObject.getCTM() — 它包含 g.edgeLabel/g.label/preserveAspectRatio 等所有 transform
        // 退路: 用 svg.getBoundingClientRect / viewBox.baseVal 推算 (用 max 模拟 xMidYMid slice)
        let effectiveScale = 1
        try {
          const ctm = foreignObject.getCTM()
          if (ctm) {
            // CTM.a 是 X 轴的 X 分量, CTM.b 是 X 轴的 Y 分量
            // 缩放因子 = X 轴基向量的长度 (假设无旋转)
            effectiveScale = Math.sqrt(ctm.a * ctm.a + ctm.b * ctm.b) || 1
          }
        } catch (e) {
          // jsdom 等无 getCTM 环境, 用 svg rect/viewBox 推算
          const svgEl2 = foreignObject.closest('svg')
          if (svgEl2) {
            const sr = svgEl2.getBoundingClientRect()
            const vb = svgEl2.viewBox?.baseVal
            if (vb && vb.width > 0 && vb.height > 0) {
              const sx = sr.width / vb.width
              const sy = sr.height / vb.height
              // xMidYMid slice 用较大缩放, meet 用较小; 这里保守用较大 (slice 常见)
              effectiveScale = Math.max(sx, sy) || 1
            }
          }
        }

        // viewport 像素 → SVG 单位
        const measuredWidthSvg = measuredWidthVp / (effectiveScale || 1)

        const currentWidth = parseFloat(foreignObject.getAttribute('width')) || 0
        // 至少给 4 SVG 单位的缓冲, 避免边界裁剪
        const SAFETY = 4
        const targetWidth = Math.ceil(measuredWidthSvg + SAFETY)

        if (Math.abs(targetWidth - currentWidth) > 1) {
          // 调整 foreignObject width
          foreignObject.setAttribute('width', String(targetWidth))

          // 调整 foreignObject x 保持中心点对齐
          // Mermaid 通常将 foreignObject 居中放置 (x = -width/2)
          // 调整后 x = -(targetWidth / 2) = oldX - (targetWidth - oldWidth) / 2
          const oldX = parseFloat(foreignObject.getAttribute('x')) || 0
          const widthDiff = targetWidth - currentWidth
          const newX = oldX - widthDiff / 2
          foreignObject.setAttribute('x', String(newX))

          // 同步调整 rect 背景框 (如果有)
          const rectEl = edgeLabel.querySelector('rect.background, rect.label-container')
          if (rectEl) {
            const oldRectX = parseFloat(rectEl.getAttribute('x')) || 0
            const oldRectWidth = parseFloat(rectEl.getAttribute('width')) || currentWidth
            rectEl.setAttribute('width', String(targetWidth))
            rectEl.setAttribute('x', String(oldRectX - widthDiff / 2))
          }
        }
      }
    })
  }

  /**
   * [v40 关键修复] 强制把 edgeLabel 移到连线中点
   * 根因: Mermaid 11.13.0 不支持 flowchart.labelPosition 配置 (代码里找不到)
   *       Mermaid 把 label 放在 start 位置 (源节点附近), 而不是连线中间
   * 修复: 利用 Mermaid SVG 的"按 document 顺序一一对应"特性
   *       edgePath[i] ↔ edgeLabel[i] (v34 注释 line 136)
   *       配对后用 path.getPointAtLength(pathLen/2) 拿到几何中点
   *
   * [v40.1 强化] Mermaid 11 SVG 结构是嵌套 transform:
   *   g.edgeLabel  transform="translate(midX, midY)"     ← 决定 label 位置
   *     g.label    transform="translate(-w/2, -h/2)"     ← 居中 label 内容
   *       foreignObject x, y, width, height              ← 内容盒子
   *
   *   之前 v40 只设 foreignObject.x/y = midPt - foWidth/2, 没动外层 g.edgeLabel/g.label
   *   → 双重 transform 导致 label 偏离 path 中点 (用户反馈: "文字不在连线中间")
   *   修复: 始终覆盖 g.edgeLabel transform 为中点, 同时把 g.label/foreignObject 设为相对居中
   * 必须等 layout 完成后调用, 所以用 requestAnimationFrame 包装
   */
  const forceEdgeLabelToMidpoint = (svg) => {
    if (!svg) {
      console.warn('[forceEdgeLabelToMidpoint] svg is null')
      return
    }

    // [v40.2 诊断日志] 输出关键状态, 排查 "label 不在连线中间"
    const edgeLabels = Array.from(svg.querySelectorAll('g.edgeLabel'))
    console.log('[v40.2 诊断] forceEdgeLabelToMidpoint: edgeLabels=%d', edgeLabels.length)

    // 收集所有 edgeLabel (按 document 顺序)
    if (edgeLabels.length === 0) return

    // 收集所有 edgePath (按 document 顺序) - Mermaid 11 容器: g.edges.edgePaths > g.edgePath
    const edgePathEls = Array.from(svg.querySelectorAll('g.edges.edgePaths > g.edgePath'))
    console.log('[v40.2 诊断] forceEdgeLabelToMidpoint: edgePathEls=%d', edgePathEls.length)
    if (edgePathEls.length === 0) {
      // 兼容旧结构: path.flowchart-link 直接放在 svg 下
      const flowLinkEls = Array.from(svg.querySelectorAll('path.flowchart-link')).map(p => ({ _path: p }))
      if (flowLinkEls.length === 0) return
      // 用 flowLinkEls 走相同配对逻辑
      const flowPairs = edgeLabels.map((edgeLabel, idx) => {
        const ep = flowLinkEls[idx]
        if (!ep) return null
        const pathEl = ep._path
        if (!pathEl || !pathEl.getAttribute('d')) return null
        return { edgeLabel, pathEl, idx }
      }).filter(Boolean)
      processPairs(flowPairs)
      return
    }

    // 配对: edgeLabel[i] ↔ edgePath[i]
    const pairs = edgeLabels.map((edgeLabel, idx) => {
      const ep = edgePathEls[idx]
      if (!ep) return null
      // 取 path 元素 (可能在 g.edgePath 内, 也可能直接是 path.flowchart-link)
      const pathEl = ep.querySelector ? ep.querySelector('path') : ep._path
      if (!pathEl || !pathEl.getAttribute('d')) return null
      return { edgeLabel, pathEl, idx }
    }).filter(Boolean)

    processPairs(pairs)
  }

  // [v40.2 修复] 提取配对处理为独立函数, 避免重复声明 edgePathEls
  //   旧代码: function 顶部 const edgePathEls=... + 后面 let edgePathEls=... (重复声明 SyntaxError)
  //   新代码: 单一 processPairs 函数, 配对成功后统一处理
  const processPairs = (pairs) => {
    // [v40.2 诊断] 输出每个配对的处理结果
    let successCount = 0
    let failCount = 0

    pairs.forEach(({ edgeLabel, pathEl, idx }) => {
      const foreignObject = edgeLabel.querySelector('foreignObject')
      if (!foreignObject) {
        failCount++
        return
      }

      // 计算 path 的几何中点 (在 SVG 坐标系中)
      let midPt
      try {
        const pathLen = pathEl.getTotalLength()
        if (!isFinite(pathLen) || pathLen === 0) {
          failCount++
          return
        }
        midPt = pathEl.getPointAtLength(pathLen / 2)
      } catch (e) {
        failCount++
        return  // jsdom 等无 layout 环境, 跳过
      }

      if (!midPt || !isFinite(midPt.x) || !isFinite(midPt.y)) {
        failCount++
        return
      }

      // foreignObject 当前宽度 (已经被 fixEdgeLabelOverflow 调整过)
      const foWidth = parseFloat(foreignObject.getAttribute('width')) || 100
      const foHeight = parseFloat(foreignObject.getAttribute('height')) || 24

      // [v40.6 关键] 读取 labelBkg 实际高度, 让 div 几何中心对齐连线
      //   v40.5 用 -textH*0.35 假设 "text 视觉中心在 div 顶部 0.35*H 处"
      //   但实际 HTML baseline 行为: 文字 baseline 在 div 底部, 视觉中心在 0.5*H (近似) 到 0.6*H
      //   → v40.5 让文字视觉中心落在 path 下方 1-3px (用户反馈: 文字在连线下方, 没居中)
      //   修复: 让 div 几何中心对齐连线 (gLabelY = -textH/2), 文字视觉中心误差 < 1.5px
      //
      // [v40.7 关键] 当 SVG 非均匀缩放 (scaleX != scaleY) 时,
      //   高度应该用 scaleY 转换, 不是 scaleX!
      //   错误: textHSvg = divRect.height / scaleX → 当 scaleX < scaleY 时, 算出偏大的 textHSvg,
      //         让 div 中心上偏 0.5-2 SVG 单位 (0.2-1 viewport px), 看起来"label 在连线上方"
      //   修复: 分别计算 scaleX/scaleY, 高度用 scaleY
      let textHSvg = foHeight
      let textHalfSvg = foHeight / 2
      try {
        const labelBkgDiv = foreignObject.querySelector(':scope > div')
        if (labelBkgDiv) {
          const divRect = labelBkgDiv.getBoundingClientRect()
          const svgEl2 = foreignObject.closest('svg')
          let scaleX = 1, scaleY = 1
          if (svgEl2) {
            const svgRect2 = svgEl2.getBoundingClientRect()
            const vb2 = svgEl2.viewBox?.baseVal
            if (vb2 && vb2.width > 0) scaleX = svgRect2.width / vb2.width
            if (vb2 && vb2.height > 0) scaleY = svgRect2.height / vb2.height
          }
          const textHVp = divRect.height
          if (textHVp > 0) {
            // [v40.7] 高度用 scaleY 转换 (垂直方向的缩放)
            textHSvg = textHVp / (scaleY || scaleX || 1)
            textHalfSvg = textHSvg / 2
          }
        }
      } catch (e) {
        // fallback to foHeight / 2
      }

      // [v40.1 关键] 始终覆盖 g.edgeLabel transform 为 path 中点
      //   不论 Mermaid 11 是否已经设了 transform, 都强制覆盖 (它可能设在 start 位置)
      edgeLabel.setAttribute('transform', `translate(${midPt.x}, ${midPt.y})`)

      // [v40.6 关键] g.label y 偏移: 让 div 几何中心对齐连线
      //   div 顶部在 y=gLabelY, div 中心在 y=gLabelY + textHSvg/2
      //   要 div 中心 = 0 (连线): gLabelY = -textHSvg/2
      const innerLabelG = edgeLabel.querySelector('g.label')
      if (innerLabelG) {
        innerLabelG.setAttribute('transform', `translate(${-foWidth / 2}, ${-textHalfSvg})`)
      }

      // [v40.1 关键] foreignObject x/y 设为 0
      //   之前 v40 误设为 midPt - foWidth/2, 但因为 g.edgeLabel 已经 translate 到 midPt,
      //   foreignObject 再用绝对坐标会导致双重偏移
      //   现在 g.edgeLabel 在中点, g.label 负责居中, foreignObject 在 g.label 局部坐标 (0,0) 即可
      foreignObject.setAttribute('x', '0')
      foreignObject.setAttribute('y', '0')

      // [v40.2 诊断] 输出前 3 个 edgeLabel 的处理结果, 排查 "label 不在连线中间"
      // [v40.5 关闭诊断] 已稳定, 不再需要日志刷屏
      // if (successCount < 3) {
      //   console.log('[v40.2 诊断] edgeLabel[%d] midPt=(%s, %s) foWidth=%s transform=%s',
      //     idx,
      //     midPt.x.toFixed(1), midPt.y.toFixed(1),
      //     foWidth,
      //     edgeLabel.getAttribute('transform'))
      // }
      successCount++
    })

    console.log('[v40.2 诊断] forceEdgeLabelToMidpoint DONE: success=%d, fail=%d', successCount, failCount)
  }

  return {
    validateContainerTitles,
    fixArrowMarkers,
    updateNodeStyles,
    updateClusterStyles,
    fixLabelBackground,
    fixEdgeLabelOverflow,
    // [v40 新增] 强制 edgeLabel 到连线中点
    forceEdgeLabelToMidpoint,
    // 向后兼容别名
    applyContainerTitleItalic: validateContainerTitles
  }
}
