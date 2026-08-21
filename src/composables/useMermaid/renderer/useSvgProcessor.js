import { useSvgStyle } from '../style/useSvgStyle.js'
import { useTooltip } from '../tooltip/useTooltip.js'
import { useAnnotation, useAnnotationOverlay } from '../annotation/index.js'
import { useInteraction } from '../interaction/useInteraction.js'
import { isBidirectionalLink } from '../syntax/_shared/arrowHelper.js'
import { useDiagnostics } from '../core/useDiagnostics.js'
import { getLiftedParentPathMap } from '../layouts/groupedLayout.js'
import { isFeatureEnabled } from '@/utils/featureFlags.js'

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
  const diag = useDiagnostics()  // [FIX 2026-08-01] 统一诊断入口

  /**
   * 修复 SVG ViewBox（处理负坐标）
   * [FIX 2026-08-10 幂等] 同一 SVG 元素只加一次 padding。
   *   旧实现: 只要有负坐标就无条件 +20 padding, 且无已处理标记 → 同一元素每次被
   *   processSvg 处理(如反复切换"区分对象范围")都会再 +20, viewBox 坐标范围逐次扩大
   *   (实测 -28→-48→-68→...), 而 SVG 元素尺寸恒定, preserveAspectRatio: meet 缩放下
   *   图表内容相对越来越小 → 用户看到的"每次切换图表微小缩小"。
   *   修复: 用 data-viewbox-padded 标记, 已处理过就不再叠加, 保留首次渲染的精确外观。
   */
  const fixViewBox = (svgEl) => {
    if (!svgEl) return svgEl
    const svgViewBox = svgEl.getAttribute('viewBox')
    if (svgViewBox) {
      const parts = svgViewBox.split(' ').map(Number)
      if (parts[0] < 0 || parts[1] < 0) {
        if (svgEl.getAttribute('data-viewbox-padded') === 'true') return svgEl
        const padding = 20
        const newViewBox = `${parts[0] - padding} ${parts[1] - padding} ${parts[2] + padding * 2} ${parts[3] + padding * 2}`
        svgEl.setAttribute('viewBox', newViewBox)
        svgEl.setAttribute('data-viewbox-padded', 'true')
      }
    }
    return svgEl
  }

  /**
   * 添加节点编码属性
   */
  const addNodeCodeAttributes = (svgEl, diagramData) => {
    if (!diagramData || !diagramData.nodes) return

    // [PERF 2026-08-13] 预建 code→node Map, 消除每个 SVG 节点的 O(节点) find.
    //   大图 (286 节点) 下两次 find 合计 O(节点²); Map 化后主路径 O(1).
    //   feature flag: ff_perfProcessSvg=0 回退原 find 逻辑.
    const perfOpt = isFeatureEnabled('perfProcessSvg')
    const nodesByCode = perfOpt ? new Map() : null
    if (nodesByCode) {
      for (const n of diagramData.nodes) {
        if (n && n.code && !nodesByCode.has(n.code)) nodesByCode.set(n.code, n)
      }
    }

    const allNodes = svgEl.querySelectorAll('.node')
    allNodes.forEach(node => {
      const nodeLabel = node.querySelector('.nodeLabel')
      if (nodeLabel) {
        const labelText = nodeLabel.textContent || ''
        // [FIX 2026-08-08 v2] 兼容中文全角括号（SCP）和 ASCII 括号 (SCP)
        //   COLLAPSE 节点标签使用中文括号（Mermaid 代码中的 `（${code}）`），
        //   原 ASCII 括号正则无法匹配，导致 extractedCode 始终为 null，
        //   data-container-code 属性缺失。改为匹配两种括号。
        // [FIX 2026-08-09] 兼容新折叠节点格式 "领域 SCM"/"子领域 SCP"/"服务模块 DP" (无括号):
        //   类型关键字后的 token 即编码, 优先于括号提取 (旧格式 "（编码）" 仍兼容).
        const typeCodeMatch = labelText.match(/(?:领域|子领域|服务模块)\s*([^\s]+)/)
        const codeMatch = labelText.match(/[（(]([^）)]+)[）)]/)
        const extractedCode = (typeCodeMatch && typeCodeMatch[1]) || (codeMatch && codeMatch[1]) || null

        let matchedNode = null
        if (extractedCode) {
          matchedNode = nodesByCode ? nodesByCode.get(extractedCode) : diagramData.nodes.find(n => n.code === extractedCode)
        }
        // [FIX 2026-08-09] 修复 BO 叶子节点 data-code 错配为同名前缀节点:
        //   旧兜底 `labelText.includes(n.name)` 会命中"名称是标签子串"的节点——
        //   服务模块"需求计划"(DP) 下的 BO"需求计划算法方案"(PLB034) 等, 因 DP01 名称
        //   "需求计划" 是其标签前缀, 全被错误标成 data-code="DP01" → 点击高亮命中 DP01.
        //   正确: BO 叶子节点标签格式为 `名称+编码`(编码在末尾), 应匹配"标签以编码结尾".
        //   (COLLAPSE 容器节点由上方 extractedCode 精确处理, 不受此兜底影响)
        if (!matchedNode) {
          // [PERF] 先精确提取 \n 后编码走 Map O(1), miss 时回退原 endsWith 线性兜底.
          if (nodesByCode) {
            const nl = labelText.lastIndexOf('\n')
            const tailCode = nl >= 0 ? labelText.slice(nl + 1).trim() : ''
            if (tailCode) matchedNode = nodesByCode.get(tailCode) || null
          }
          if (!matchedNode) {
            matchedNode = diagramData.nodes.find(n => n.code && labelText.endsWith(n.code))
          }
        }

        if (matchedNode) {
          node.setAttribute('data-code', matchedNode.code || matchedNode.name)
        }
        // [FIX 2026-08-08] COLLAPSE 节点: 从标签提取编码, 设 data-container-code
        //   COLLAPSE 节点是 g.node (无 data-container-code), 但 identifyGroupFromSvg
        //   优先使用 data-container-code 识别分组. 从标签 "(编码)" 提取后直接设置.
        const nodeId = node.getAttribute('id') || ''
        if (nodeId.includes('COLLAPSE_') && extractedCode) {
          node.setAttribute('data-container-code', extractedCode)
        }
      }
    })
  }

  /**
   * 添加容器编码属性
   *
   * [FIX 2026-08-08] 编码来源对齐分组树 elementCode:
   *   增量隐藏(updateVisibilityOnly)按 group.elementCode 匹配 SVG 容器,
   *   而本函数原实现仅按 domainProducts 的 名称→code 映射, 两者编码源可能不一致
   *   (例: "销售管理" 分组树 elementCode=OM, domainProducts 名称映射=SCMSA)
   *   → data-container-code=SCMSA 但 hiddenContainerCodes 只有 OM → 永远匹配不上 → 空容器无法隐藏.
   *   修复: 优先按标题匹配分组树(layoutGroups)取其 elementCode, 兜底再用 domainProducts 名称映射,
   *   保证 data-container-code 与 updateVisibilityOnly 消费的编码源一致.
   */
  const addContainerCodeAttributes = (svgEl, diagramData, layoutGroups = null) => {
    if (!diagramData) return

    // 1) 分组树 标题→elementCode (权威编码源, 与 updateVisibilityOnly 一致)
    const titleToElementCode = new Map()
    const collectGroups = (list) => {
      ;(list || []).forEach((g) => {
        if (!g || typeof g !== 'object') return
        const title = g.title || g.name
        const code = g.elementCode || g.id
        if (title && code && !titleToElementCode.has(title)) {
          titleToElementCode.set(title, code)
        }
        collectGroups(g.children)
        collectGroups(g.containers)
      })
    }
    collectGroups(layoutGroups)

    // 2) domainProducts 名称→code (兜底, 兼容无 layoutGroups 路径)
    const nameToCode = new Map()
    const collectLevel = (list) => {
      ;(list || []).forEach((item) => {
        if (item && typeof item === 'object') {
          if (item.name && item.code) nameToCode.set(item.name, item.code)
          collectLevel(item.submodules)
          collectLevel(item.modules)
          collectLevel(item.businessObjects)
        }
      })
    }
    collectLevel(diagramData.domainProducts)
    // 兼容没有 domainProducts 的路径 (直接读 serviceModules)
    ;(diagramData.serviceModules || []).forEach((sm) => {
      if (sm && sm.name && sm.code) nameToCode.set(sm.name, sm.code)
    })

    const subgraphs = svgEl.querySelectorAll('.subgraph, .cluster')
    subgraphs.forEach((subgraph) => {
      const titleEl = subgraph.querySelector('.cluster-label, text')
      if (titleEl) {
        const titleText = titleEl.textContent || ''
        const titleMatch = titleText.match(/^([^\n(]+)/)
        // [FIX 2026-08-09] 新容器标题带层级标记符号 (<名称>/ {名称}/ [名称]),
        //   去除首尾标记后才是纯名称, 否则无法匹配分组树标题 → data-container-code 缺失
        //   → 右键/双击无法识别容器 (需求计划 SM 容器右击无菜单/双击不折叠).
        let containerName = titleMatch ? titleMatch[1].trim() : titleText
        containerName = containerName.replace(/^[<{\[]/, '').replace(/[>}\]]$/, '')
        // [FIX 2026-08-08] 优先分组树 elementCode, 兜底 domainProducts 名称映射
        const matchedCode = titleToElementCode.get(containerName)
          || titleToElementCode.get(titleText)
          || nameToCode.get(containerName)
          || nameToCode.get(titleText)
        if (matchedCode) {
          subgraph.setAttribute('data-container-code', matchedCode)
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

    // [PERF 2026-08-13] 预建 link 查找 Map, 把 O(边×标签) 的 .find() 降为 O(1) 查找.
    //   大图 (如采购供应 602 边) 每条 edgeLabel 都对 links 全量 .find() 是 process_svg 主要热点.
    //   用 !has() 守卫保留"取首个匹配"语义 (与原 .find() 一致, 避免同 key 多 link 时取到末尾).
    const linkByKey = new Map()
    for (const link of diagramData.links) {
      if (!link) continue
      if (link.code && !linkByKey.has(link.code)) linkByKey.set(link.code, link)
      if (link.relationCode && !linkByKey.has(link.relationCode)) linkByKey.set(link.relationCode, link)
      if (link.relationDesc && !linkByKey.has(link.relationDesc)) linkByKey.set(link.relationDesc, link)
    }

    const edgeLabels = svgEl.querySelectorAll('.edgeLabel')
    edgeLabels.forEach(edgeLabel => {
      const labelText = (edgeLabel.textContent || '').trim()
      if (!labelText) return

      // [v40.1] 精确匹配 link.code / relationCode / relationDesc
      //   ELK 引擎生成的 link label 是 sourceName-targetName 拼接 (如 "PLA001-PLD00201"),
      //   与 link.sourceCode 不一致, 无法用文本精确匹配。
      //   这种情况下 annotationList 里的 relation targetId 来自 link.relationCode,
      //   annotation panel item 点击会通过 highlightTargetElement 找 [data-relation-code="..."],
      //   若 ELK 自动 label 不可匹配, 此 attribute 缺失, 但不影响 annotation panel 链路 (annotationList 内部仍可工作)。
      const matchedLink = linkByKey.get(labelText) || null

      if (matchedLink) {
        // [FIX 2026-08-09] 关系定位失败: arch data 流程 link.relationCode 为空(""),
        //   旧守卫 `matchedLink.relationCode` 恒为 falsy → data-relation-code 永不设置
        //   → 关系连线无法按编码定位 (点击/备注面板高亮全失效).
        //   修复: relationCode 为空时回退到 link.code (即 `${source}-${target}` 渲染标签,
        //   与 annotation targetId 的 `${link.source}-${link.target}` 兜底一致).
        //   relationCode 非空时仍优先用 relationCode (addBidirectionalAttributes 依赖它).
        const code = matchedLink.relationCode || matchedLink.code
        if (code) {
          const edgeGroup = edgeLabel.closest('g')
          if (edgeGroup) {
            edgeGroup.setAttribute('data-relation-code', code)
          }
        }
      }
    })

    // [FIX 2026-08-01] 收集诊断信息但不在生产 console 输出
    const labeledCount = svgEl.querySelectorAll('g.edgeLabel[data-relation-code]').length
    const sampleCodes = Array.from(svgEl.querySelectorAll('g.edgeLabel[data-relation-code]'))
      .slice(0, 5)
      .map(el => el.getAttribute('data-relation-code'))
    diag.recordStepMeta('addLinkCodeAttributes', { labeledCount, sampleCodes })
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
      diag.recordStepMeta('addBidirectionalAttributes', { reason: 'no_diagramData_links' })
      return
    }

    // 1. 收集所有双向 link 的 relationCode (用 isBidirectionalLink 统一判断)
    const bidiCodes = new Set(
      (diagramData.links || [])
        .filter(link => isBidirectionalLink(link))
        .map(link => link.relationCode)
        .filter(Boolean)
    )
    diag.recordStepMeta('addBidirectionalAttributes', {
      totalLinks: (diagramData.links || []).length,
      bidiCodesCount: bidiCodes.size,
      bidiCodes: [...bidiCodes].slice(0, 5)
    })

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
    diag.recordStepMeta('addBidirectionalAttributes', { bidiEdgesMarked })
  }

  /**
   * 应用样式修复
   */
  const applyStyleFixes = (svgEl, diagramType, mermaidContainer, textColor) => {
    // [FIX 2026-08-01] 移除 [v40.2 诊断] 噪音 console.log, 改由 useDiagnostics hooks 集中管理
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
   * [FIX 2026-06-30] 透传 annotationFilter, 让 tooltip 弹窗只展示过滤后的备注
   */
  const addTooltips = (svgEl, relationDescriptions, diagramType, hideTails = false, annotationFilter = []) => {
    tooltip.addMouseOverTooltips(svgEl, relationDescriptions, diagramType, hideTails, annotationFilter)
  }

  // [SIMPLE 2026-08-15] 增量刷新拖尾线(关系连线关联点): 关联点开关切换时调用,
  //   只增删现有 SVG 拖尾线元素, 不触发 mermaid.run 全量重绘. 见 useTooltip.refreshTrailingDottedLines.
  const refreshTrailingDottedLines = (svgEl, diagramType, hideTails = false) => {
    tooltip.refreshTrailingDottedLines(svgEl, diagramType, hideTails)
  }

  /**
   * 渲染备注叠加层
   * @param {Object} interaction - (可选) useInteraction 实例, 提供 centerElement 回调用于点击 annotation 时居中元素
   * @param {Array} layoutGroups - (可选) layoutControlConfig.groups (分组树), 供图例项点击时定位分组并切换 visible
   * @param {Function} onToggleGroupVisible - (可选) 图例项点击分组可见性切换回调 (name, visible, groups),
   *   用于就地改 visible + 以新引用替换 store 配置, 触发增量隐/显与配置树双向同步
   * @param {Function} onLegendItemColorChange - (可选) 图例项色块改色回调 (colorKey, color),
   *   写入 store.customColors 触发增量变色 (方案A, 由 MermaidComponent 注入)
   */
  const renderAnnotationOverlay = (svgEl, diagramData, diagramType, annotationConfig, nodeColorMappings, interaction = null, layoutGroups = null, onToggleGroupVisible = null, onLegendItemColorChange = null) => {
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

    // [FIX 2026-07-31 v2] bindAnnotationInteraction 必须在 annotationList 为空时也调用
    //   onSvgClick 处理节点单击 + 居中 - 与 annotation item 是否存在无关
    //   之前只在 annotationList.length > 0 时调用 → 无 annotation 时单击节点无反应
    if (annotationList.length > 0) {
      const numberMap = annotation.buildNumberMap(annotationList)
      annotationOverlay.overlayNumberMarkers(svgEl, numberMap, annotationList)
      annotationOverlay.overlayAnnotationPanel(svgEl, annotationList, {
        position: annotationConfig.annotationPanelPosition || 'bottom',
        showIcons: annotationConfig.showAnnotationIcons || false
      })
    }
    // 始终绑定 svg click listener (支持单击节点/容器/连线 高亮 + 居中)
    annotationOverlay.bindAnnotationInteraction(svgEl, annotationList, {
      onCenterElement: interaction && interaction.centerElement
        ? (targetEl) => interaction.centerElement(svgEl, targetEl)
        : null
    })

    // 渲染颜色图例
    if ((diagramType === 'serviceModule' || diagramType === 'businessObject') && diagramData) {
      const colorLegendData = buildColorLegendData(diagramData, nodeColorMappings, annotationConfig.centerScopeHighlight, layoutGroups)
      if (colorLegendData && colorLegendData.length > 0) {
        annotationOverlay.overlayColorLegend(svgEl, colorLegendData, {
          position: annotationConfig.legendPosition || 'top-left',
          onToggleGroupVisible,
          onLegendItemColorChange,
          colorScheme: diagramData?.colorScheme || 'default'
        })
      }
    }
  }

  /**
   * [FIX 2026-07-31] 增量刷新颜色图例
   *
   * 用法: 切换 colorGroupBy 后, 不重跑 mermaid.run, 只重建 legend panel。
   *   updateColorsOnly() 已负责更新节点/连线颜色, 这里只同步 legend。
   *
   * @param {SVGElement} svgEl - mermaid 渲染的 SVG
   * @param {Object} diagramData - 包含 nodes/colorGroupBy/nodeColorMappings
   * @param {Object} annotationConfig - centerScopeHighlight / legendPosition
   * @param {Array} nodeColorMappings - 当前节点的 colorMap (从 generateMermaidCode 返回值)
   * @param {Array} layoutGroups - layoutControlConfig.groups (图例项点击定位分组用)
   * @param {Function} onToggleGroupVisible - 图例项点击回调
   * @param {Map|null} groupColorMap - 增量路径传入的 分组名→颜色 映射 (折叠视图用)
   * @param {Function} onLegendItemColorChange - (方案A) 图例项色块改色回调 (colorKey, color)
   */
  const updateColorLegend = (svgEl, diagramData, annotationConfig, nodeColorMappings, layoutGroups = null, onToggleGroupVisible = null, groupColorMap = null, onLegendItemColorChange = null) => {
    if (!annotationConfig) return
    if (diagramData?.nodes?.[0]?.category !== 'object' && !diagramData?.serviceModules?.length) {
      return
    }
    const centerScopeHighlight = annotationConfig.centerScopeHighlight !== false
    const colorLegendData = buildColorLegendData(diagramData, nodeColorMappings, centerScopeHighlight, layoutGroups, groupColorMap)
    if (colorLegendData && colorLegendData.length > 0) {
      annotationOverlay.overlayColorLegend(svgEl, colorLegendData, {
        position: annotationConfig.legendPosition || 'top-left',
        onToggleGroupVisible,
        onLegendItemColorChange,
        colorScheme: diagramData?.colorScheme || 'default'
      })
    }
  }

  /**
   * 构建颜色图例数据
   * @param {Array|null} groups - layoutControlConfig.groups (分组树), 用于建立 层级名称→分组对象 映射,
   *   供图例项点击时定位对应分组并切换 visible (与图表配置树双向同步)。传入空/缺省时不附加分组引用。
   * @param {Map|null} groupColorMap - 当前 colorGroupBy 下的 分组名→颜色 映射 (MermaidComponent 增量路径
   *   传入, 与折叠节点/展开节点取色同源)。优先用其取色, 回退 nodeColorMappings / node.color。
   */
  const buildColorLegendData = (diagramData, nodeColorMappings, centerScopeHighlight = true, groups = null, groupColorMap = null) => {
    const legendData = []
    const { nodes, colorGroupBy, centerScopeColor, centerObjectColor, centerScope } = diagramData

    if (!nodes || nodes.length === 0) return legendData

    // [FIX 2026-08-15] 中心判定不再依赖 node.isCenter (增量切"区分/不区分"时 nodes 的
    //   isCenter 可能陈旧, 见 useDiagramData 高亮 watch 同步重算的注释), 优先由
    //   diagramData.centerScope 直接判定, 与 useMermaidColors.updateNodeColors 取色口径一致.
    //   centerScope 缺失 (如单测/合成数据只带 node.isCenter) 时回退 node.isCenter.
    const hasCenterScope = Array.isArray(centerScope) && centerScope.length > 0
    const centerScopeSet = new Set(hasCenterScope ? centerScope : [])
    const nodeIsCenter = (node) => hasCenterScope ? centerScopeSet.has(node.code) : node.isCenter === true

    // [LEGEND 2026-08-07] 收集分组树: 按层级(domain/subDomain/serviceModule)建立 名称→分组对象 映射,
    //   供图例项点击隐藏/显示时定位对应分组 (可能多个同名分组, 如跨领域的同名子领域)。
    //   兼容两种结构: LayoutControlPanel 面板树用 groupType(小写), GroupModel 渲染结构用 type(大写)。
    const groupsByType = { domain: new Map(), subDomain: new Map(), serviceModule: new Map() }
    if (Array.isArray(groups)) {
      const collectType = (g) => {
        if (!g || typeof g !== 'object') return
        const t = String(g.groupType || g.type || '').toLowerCase()
        let key = null
        if (t === 'domain') key = 'domain'
        else if (t === 'subdomain') key = 'subDomain'
        else if (t === 'servicemodule') key = 'serviceModule'
        if (key) {
          // 注册分组: 同时用完整标题与去掉"(...)/（...）"后缀的裸名作键,
          //   兼容标题含祖先路径/编码的情况 (如 "采购供应（供应链计划）"), 使 node.domain/subDomain/serviceModuleName 能命中。
          const rawTitle = g.title || g.name
          const bareTitle = (rawTitle || '').replace(/[（(].*$/, '').trim()
          const keys = new Set([rawTitle, bareTitle].filter(Boolean))
          keys.forEach((k) => {
            if (!groupsByType[key].has(k)) groupsByType[key].set(k, [])
            groupsByType[key].get(k).push(g)
          })
        }
        ;(g.children || []).forEach(collectType)
        ;(g.containers || []).forEach(collectType)
      }
      groups.forEach(collectType)
    }

    // [恢复 2026-08-05] isGroupFullyCenter 跳过逻辑（此前 2026-08-02 移除）：
    //   区分对象范围时，整组都在对象范围（所有节点 isCenter）→ 该分组节点 fill 全被
    //   centerScopeColor 覆盖，图例组色块无意义，不再单独列示。
    //   例：供应链计划为对象范围、按服务模块分组时，"需求计划"（全属供应链计划）
    //   不单独出现在图例。仅列出至少含一个非对象范围节点的分组。
    const groupTotalNodes = new Map()
    const groupCenterNodes = new Map()
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

      // 统计每组总节点数与中心节点数（判断是否"整组都在对象范围"）
      groupTotalNodes.set(groupKey, (groupTotalNodes.get(groupKey) || 0) + 1)
      if (nodeIsCenter(node)) {
        groupCenterNodes.set(groupKey, (groupCenterNodes.get(groupKey) || 0) + 1)
        if (centerScopeHighlight) hasCenterNodes = true
      }

      if (!colorMap.has(groupKey)) {
        let color = null
        // [FOLD 2026-08-09] 优先用增量路径传入的 groupColorMap (与折叠/展开节点取色同源).
        //   折叠视图 nodeColorMappings 为空时, 若不传 groupColorMap, 回退 node.color 是
        //   初始渲染烘焙的旧分组色 → 图例键色与折叠节点(按新 colorGroupBy 重算)不一致.
        if (groupColorMap && typeof groupColorMap.get === 'function') {
          color = groupColorMap.get(groupKey)
        }
        if (!color && nodeColorMappings && nodeColorMappings.length > 0) {
          const mapping = nodeColorMappings.find(m => m.nodeCode === node.code)
          if (mapping) {
            color = mapping.color
          }
        }
        if (!color) {
          color = node.color || '#e0e0e0'
        }

        colorMap.set(groupKey, color)
      }
    })

    // 整组都在对象范围 → 不单独列示（区分对象范围开启时）
    const isGroupFullyCenter = (groupKey) =>
      centerScopeHighlight &&
      groupCenterNodes.get(groupKey) === groupTotalNodes.get(groupKey) &&
      (groupTotalNodes.get(groupKey) || 0) > 0

    // 先添加对象范围颜色项（如果有对象范围节点）
    // [LEGEND-SECTION 2026-08-15] 区分对象范围时, 颜色分组只针对"对象范围外部"元素:
    //   对象范围项之后插入 isSection 节标题项, 明确下方颜色分组属于范围外元素, 提升可读性.
    const centerScopeItem = hasCenterNodes
      ? [{
          name: '对象范围',
          color: centerScopeColor || centerObjectColor || '#EDEDED',
          isCenter: true,
          // [LEGEND-COLOR v2 2026-08-11] 对象范围色块也可改色: 特殊 colorKey 标记,
          //   改色走 store.updateCenterScopeColor (非 customColors). annotationOverlay 借此
          //   区分"中心范围改色"与"分组改色", 均弹同一调色板, 只是写入目标不同.
          colorKey: '__centerScope__'
        }]
      : []

    // [LEGEND 2026-08-07] 图例按 colorGroupBy 判定分组层级, 用于点击时匹配对应分组
    const typeKey = colorGroupBy === 'subDomain' ? 'subDomain'
      : colorGroupBy === 'serviceModule' ? 'serviceModule'
      : 'domain'

    // 再添加分组颜色项（跳过整组都在对象范围的分组）
    const groupItems = []
    colorMap.forEach((color, name) => {
      if (isGroupFullyCenter(name)) return
      groupItems.push({
        name,
        color,
        // [LEGEND-COLOR 2026-08-11] 方案A: 图例项改色的 customColors 写入键.
        //   与 useGroupDisplay.getGroupColor 的 key 对齐 (按 colorGroupBy 维度取
        //   domain/subDomain/serviceModuleName), 供图例项色块点击后写 store.customColors,
        //   经 updateColorsOnly 增量变色. 中心范围项不带此键(不可编辑).
        colorKey: name,
        // 附加该分组树中匹配的分组对象引用 (供图例项点击切换 visible, 与配置树双向同步)
        groups: (groupsByType[typeKey] && groupsByType[typeKey].get(name)) || []
      })
    })

    // 仅当存在对象范围项且其后还有范围外颜色分组时, 才插入"对象范围外部"节标题
    if (centerScopeItem.length > 0 && groupItems.length > 0) {
      legendData.push(...centerScopeItem, { isSection: true, name: '对象范围外部' }, ...groupItems)
    } else {
      legendData.push(...centerScopeItem, ...groupItems)
    }

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
    // [FIX 2026-08-02] 必须用真 .mermaid-container, 不能依赖 mermaidContainer 参数:
    //   该 ref 在模板里绑定在 .mermaid-content 上 (MermaidComponent L38), 其
    //   getBoundingClientRect() 包含用户 wheel 缩放 transform 的视觉尺寸。
    //   全量渲染 (切中心范围/图表类型等) 时 setupCanvasLayout 会把 wrapper/draggable
    //   锁在"缩放后的视觉尺寸"上, 下次渲染再读取已缩小的尺寸 → 画布每次缩小一倍 (累积)。
    //   调用点传参也不一致 (L276 传真容器 mermaidContainerEl, L479 传 content),
    //   统一优先 DOM 查询真容器 (其 rect = 布局尺寸, 不受子元素 transform 影响)。
    const containerEl = document.querySelector('.mermaid-container') || mermaidContainer?.value

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
    // 画布背景: 白色 (与 MermaidComponent.css .draggable-area 一致, 用户偏好)
    draggable.style.backgroundColor = '#FFFFFF'

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
      // [FIX 2026-08-03] preserveAspectRatio: slice -> meet
      //   原 v6 用 slice (fill 容器裁切超出), 对窄高 viewBox (SM 1177×2000, BO 3049×3848)
      //   + 宽扁容器 (928×600) 会按宽度缩放 → 上下严重裁剪 → 图表偏大.
      //   meet 按比例缩放到容器内完整显示 (可能左右留白), 不裁剪, 初始视图合适.
      //   用户可 zoom in 放大看细节.
      svgEl.style.height = '100%'
      svgEl.style.width = '100%'
      svgEl.style.maxWidth = 'none'
      svgEl.style.maxHeight = 'none'
      svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet')
    }

    // [FIX 2026-08-01] 移除关键诊断 v7 console.log, 改由 useDiagnostics 收集 (chart_diag.dump() 一键读取)
    diag.recordStepMeta('setupCanvasLayout', {
      container: `${containerWidth}x${containerHeight}`,
      wrapper: `${wrapper.style.width}x${wrapper.style.height}`,
      draggable: `${draggable.style.width}x${draggable.style.height}`,
      pre: `${pre.style.width}x${pre.style.height}`,
      svgPreserveAspectRatio: svgEl?.getAttribute('preserveAspectRatio'),
      containerElOffset: `${containerEl.offsetWidth}x${containerEl.offsetHeight}`
    })
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
   *
   * [FIX 2026-08-03] 同时规范化 cluster-label foreignObject 高度:
   *   mermaid labelHelper 在 BO→SM→BO 切换后会用不同 baseline 测量,
   *   导致同一标题的 foreignObject height 从 24 (初始) 变为 36 (切回),
   *   标题底部下移 12px, 吃掉容器顶部 padding, 与首个子节点重叠 (+33 处).
   *   实际 inner div 渲染高度不变 (bcrH 一致), 仅 foreignObject height attribute 被错算.
   *   修复: 强制设为 24 (24px 单行字体最小高度, 与初始渲染一致).
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

        // [FIX 2026-08-03] 规范化 foreignObject height: 强制 24 (单行 24px 字体最小高度)
        //   防止 mermaid labelHelper 切换后测量到 36px 导致标题遮挡首个子节点
        const foH = parseFloat(fo.getAttribute('height') || '0')
        if (foH && foH > 24) {
          fo.setAttribute('height', '24')
        }
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
  const processSvg = (svgEl, props, relationDescriptions, mermaidContainer, nodeColorMappings, interaction = null, onToggleGroupVisible = null, onLegendItemColorChange = null) => {
    if (!svgEl) {
      diag.recordStepMeta('processSvg', { reason: 'svgEl_falsy' })
      return
    }
    const tProcess = diag.time('process_svg')
    diag.recordStepMeta('processSvg', { started: true, layoutEngine: props?.layoutEngine })

    // [FIX 2026-08-03] 缺口1: 镜像 relationDescriptions 到 diagnostics store,
    //   供 snapshot.links.relations + dump().relationDescriptions 暴露给 e2e/排查.
    //   必须在 addTooltips 之前设 (matchPathsToRelations 会读 relationDescriptions 做匹配诊断).
    diag.setRelationDescriptions(relationDescriptions || [])

    // [SIMPLE 2026-08-15] 拖尾线(关系连线关联点)可见性:
    //   hideLinkLabelTails = true → 隐藏; false → 始终显示(用户手动打开, 即使直线/ELK 也显示);
    //   null/undefined(自动) → 跟随引擎: ELK(直线)隐藏, Dagre(曲线)显示.
    //   之前无条件 `layoutEngine==='elk'` 导致直线+手动打开关联点也被隐藏 (用户反馈问题2).
    const tailSetting = props.diagramData?.hideLinkLabelTails
    const hideTails = tailSetting === true || (tailSetting !== false && props.layoutEngine === 'elk')

    fixViewBox(svgEl)

    // [v34 关键修复] 必须在 applyStyleFixes (含 fixArrowMarkers) 之前
    //   调用 addLinkCodeAttributes + addBidirectionalAttributes,
    //   这样 fixArrowMarkers 才能看到 data-bidirectional='true' 并设置 marker-start
    if (props.diagramData) {
      addNodeCodeAttributes(svgEl, props.diagramData)
      // [FIX 2026-08-08] 传 layoutGroups, 让 data-container-code 对齐分组树 elementCode
      //   (updateVisibilityOnly 按 elementCode 匹配容器; 仅靠 domainProducts 名称映射会因编码源
      //   不一致导致空容器无法隐藏, 例: 销售管理 elementCode=OM vs domainProducts=SCMSA).
      addContainerCodeAttributes(svgEl, props.diagramData, props.layoutControlConfig?.groups)
      addLinkCodeAttributes(svgEl, props.diagramData)
      addBidirectionalAttributes(svgEl, props.diagramData)
    }

    applyStyleFixes(svgEl, props.diagramType, mermaidContainer, props.diagramData?.textColor)

    // [FIX 2026-08-06g] 上提自禁用父容器的子分组: 标题保持单行, 父名称以悬停 tooltip 展示。
    //   原方案 (fixLiftedClusterTitleOverlap 后处理下移内容+拉伸容器) 会导致节点/子容器
    //   跑出容器盒, 已废弃。此处改为读取 groupedLayout 注册的父路径 map, 挂 hover tooltip。
    try {
      svgStyle.attachLiftedParentTooltips(svgEl, getLiftedParentPathMap())
    } catch (e) { console.warn('[useSvgProcessor] attachLiftedParentTooltips failed:', e) }

    // [STAT-TOOLTIP 2026-08-14] 容器统计 tooltip: 业务对象数量 + 内部关系数量
    //   (领域/子领域/服务模块, 含折叠聚合节点), 复用共享 #mermaid-tooltip.
    try {
      svgStyle.attachContainerStatTooltips(svgEl, props.diagramData, props.layoutControlConfig?.groups)
    } catch (e) { console.warn('[useSvgProcessor] attachContainerStatTooltips failed:', e) }

    // [FIX 2026-08-03] 缺口3: 统计 fixArrowMarkers 实际渲染的 marker-start 数量,
    //   与 addBidirectionalAttributes.bidiEdgesMarked 互补 (后者是标记前, 这里是渲染后).
    //   e2e 可断言 bidiMarkerCount > 0 验证双向渲染生效 (commit 2ba5ec3 修复可验证).
    const _allPaths = svgEl.querySelectorAll('path.flowchart-link, .edgePath path')
    const _bidiMarkerCount = Array.from(_allPaths).filter(p => p.getAttribute('marker-start')).length
    diag.recordStepMeta('fixArrowMarkers', {
      totalPaths: _allPaths.length,
      bidiMarkerCount: _bidiMarkerCount,
      bidiDataAttrCount: Array.from(_allPaths).filter(p => p.getAttribute('data-bidirectional') === 'true').length
    })

    // [FIX 2026-06-30] 透传 annotationCategoryFilter, 让 tooltip 弹窗只展示过滤后的备注
    addTooltips(svgEl, relationDescriptions, props.diagramType, hideTails, props.annotationConfig?.annotationCategoryFilter || [])

    // 注意：之前 v22 加的 fixNodeRectSize 会修改 rect/foreignObject width/height
    // 但 mermaid ELK layout 是基于原 width 算 edge endpoint 位置
    // 改 rect 后 edge endpoint 仍然按原位置定位 → 端点错位 + 文字溢出
    // 关键回退：删 fixNodeRectSize，让 mermaid 自己负责 node sizing（更稳定）

    fixContainerTitleCenter(svgEl)

    reorderZoneRows(svgEl)

    if (props.annotationConfig) {
      // [LEGEND 2026-08-07] 传响应式 layoutControlConfig.groups 供图例项点击切换 visible (与配置树双向同步)
      renderAnnotationOverlay(svgEl, props.diagramData, props.diagramType, props.annotationConfig, nodeColorMappings, interaction, props.layoutControlConfig?.groups || null, onToggleGroupVisible, onLegendItemColorChange)
    }

    // [v33 关键修复] 调用 fixEdgeLabelSize, 必须在 layout 完成后
    // 用 requestAnimationFrame 等浏览器完成 reflow
    // 之前 fixEdgeLabelSize 导出后从未调用, 导致 v32 CSS 修复只在初次渲染生效
    // ELK 二次布局/全屏切换后宽度变化时, 右边字符仍被截掉
    scheduleEdgeLabelFix(svgEl)
    diag.endStep('process_svg', tProcess)
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
    // [CLEANUP 2026-08-19] 释放 useSvgStyle 内部创建的 MutationObserver
    //   (fixArrowMarkers serviceModule 分支), 避免组件卸载后 observer 泄漏。
    if (svgStyle && typeof svgStyle.cleanup === 'function') {
      try {
        svgStyle.cleanup()
      } catch (e) {
        console.warn('[useSvgProcessor.cleanup] svgStyle.cleanup failed:', e)
      }
    }
    // [CLEANUP 2026-08-19] 释放 annotationOverlay 注册的事件监听器 (svg/edgeLabel/path/panel),
    //   补齐卸载清理链 (之前仅 tooltip/svgStyle 被清理)。
    if (annotationOverlay && typeof annotationOverlay.cleanupListeners === 'function') {
      try {
        annotationOverlay.cleanupListeners()
      } catch (e) {
        console.warn('[useSvgProcessor.cleanup] annotationOverlay.cleanupListeners failed:', e)
      }
    }
  }

  // [FIX 2026-08-10] 透传到内部 useTooltip 实例的"清除选择高亮"。
  //   选择高亮 (点击连线高亮端点) 状态保存在本模块内部 tooltip 的闭包 selectedElements 里,
  //   关系高亮 (MermaidComponent) 应用前必须先清掉它, 否则 saveRelHlOrigStyle 会把选择高亮
  //   样式误存为"原始样式", 清除关系高亮时错误恢复 → 该节点残留高亮.
  const clearSelectionHighlight = () => {
    if (tooltip && typeof tooltip.clearSelectionHighlight === 'function') {
      tooltip.clearSelectionHighlight()
    }
  }

  // [FIX 2026-08-10] 透传到内部 useAnnotationOverlay 的"清除备注/节点点击高亮"。
  //   点击节点/连线会走 annotationOverlay 的 highlightTargetElement (加 .annotation-highlighted 类),
  //   这是独立于 useTooltip 选择高亮的另一套高亮。关系高亮 (MermaidComponent) 应用前必须先清掉它,
  //   否则 saveRelHlOrigStyle 会把节点点击高亮样式误存为"原始样式", 清除关系高亮时错误恢复 → 节点残留高亮.
  const clearAnnotationHighlight = (svgEl) => {
    if (annotationOverlay && typeof annotationOverlay.clearSvgHighlightsOnly === 'function') {
      annotationOverlay.clearSvgHighlightsOnly(svgEl)
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
    refreshTrailingDottedLines,
    renderAnnotationOverlay,
    setupCanvasLayout,
    processSvg,
    // [v34 双向支持] 导出 addBidirectionalAttributes 以便单测覆盖
    addBidirectionalAttributes,
    cleanup,
    clearSelectionHighlight,
    clearAnnotationHighlight,
    // 关键导出 v26：导出 buildColorLegendData 让 HTML 导出器复用 legend 逻辑
    buildColorLegendData,
    // [FIX 2026-07-31] 导出 updateColorLegend 供 MermaidComponent.updateColorsOnly 增量刷新 legend
    updateColorLegend
  }
}