import { ref } from 'vue'
import { useDiagnostics } from '../core/useDiagnostics.js'

// 关键修复 v19：用 window 全局对象共享拖动状态，跨 module reload 保持一致
// HMR 替换 module 后老 addZoomAndPan 闭包内的 let isDragging 与新 handleMouseMove 的 let isDragging 是不同变量
// 改用 window.__mermaidDrag 全局对象，所有 handler 引用同一对象，状态跨 HMR/闭包保持一致
const dragState = (typeof window !== 'undefined' && (window.__mermaidDrag || (window.__mermaidDrag = { isDragging: false, startX: 0, startY: 0 }))) || { isDragging: false, startX: 0, startY: 0 }

export function useInteraction() {
  const scale = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)
  const diag = useDiagnostics()  // [FIX 2026-08-01] 交互埋点 — chart_diag 一键读取耗时

  /**
   * v4 重构：mermaid-content 不再 absolute 居中（由 CSS flex 居中接管）。
   * 所以 transform 只需要 `translate(tx, ty) scale(s)`，
   * 不需要 translate(-50%, -50%)。
   * scale=1 + translate=(0,0) 表示 fit 状态（CSS 已让 SVG 100% 容器高度）。
   */
  const updateTransform = (mermaidContentRef) => {
    const el = mermaidContentRef?.value || document.querySelector('.mermaid-content')
    if (el) {
      const transformValue = `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`
      el.style.transform = transformValue
    }
  }

  /**
   * v4 重构：fit 状态就是 scale=1, translate=(0,0)。
   * CSS 已经让 SVG 100% 容器高度 + 浏览器按 viewBox 比例自动算宽度，
   * 图表天然填满容器。fit 只需要重置用户缩放/平移。
   *
   * 根因复盘：之前用 JS 算 fit scale 永远不准，因为：
   *   - getBBox() 会被 viewBox 外的边/标签污染（实测 4571×1907）
   *   - SVG width/height attribute 跟 viewBox 一致（也是 4571×1907）
   *   - mermaid 渲染时直接把 viewBox 尺寸做 attribute，没法区分"逻辑尺寸"和"渲染尺寸"
   * 唯一可靠的是让浏览器自己按 viewBox + CSS height:100% 自动缩放。
   */
  const autoFitDiagram = (instant = false) => {
    const container = document.querySelector('.mermaid-container')
    if (!container) return

    const tFit = diag.time('autoFit')
    const containerWidth = container.offsetWidth
    const containerHeight = container.offsetHeight

    // [FIX 2026-08-01] 移除 console.log 噪音 — chart_diag 一键读取
    diag.recordStepMeta('autoFitDiagram', {
      container: `${containerWidth}x${containerHeight}`,
      result: 'scale=1, translate=(0,0)',
      instant
    })

    scale.value = 1
    translateX.value = 0
    translateY.value = 0

    // [FIX 2026-08-03] instant 模式: 禁用 CSS transition, 让 transform 立即生效。
    //   原因: .mermaid-content 有 CSS `transition: transform 0.15s ease-out`
    //   (MermaidComponent.css L180)。若不禁用, autoFit 后 transform 仍在动画中,
    //   getBoundingClientRect() 返回中间值 (含残余 zoom scale),
    //   导致 mermaid.run() 内部 ELK layout 读到大 BCR → 节点 foW/rectW 被放大 ×zoom scale。
    //   场景: 用户 zoom in 后切换图表类型, autoFit 重置 transform, 但 transition 动画中,
    //   mermaid.run() 立即执行读到错误 BCR → 文字被 rect 裁剪, 刷新页面才恢复。
    const contentEl = document.querySelector('.mermaid-content')
    let prevTransition = ''
    if (instant && contentEl) {
      prevTransition = contentEl.style.transition
      contentEl.style.transition = 'none'
    }

    updateTransform()

    // force reflow 让 transform 立即生效 (否则 transition 仍会影响下次 BCR 读取)
    if (instant && contentEl) {
      void contentEl.getBoundingClientRect()
      // 不恢复 transition — 让 mermaid.run() 在无 transition 下跑完,
      // transition 由 dblclick 路径 (非-instant) 自行管理。
      // 若需要恢复, 调用方可在 mermaid.run().then() 后恢复。
      // 保留 prevTransition 不还原是安全的: CSS 规则仍存在, 下次非-instant 调用会重设。
      contentEl.style.transition = prevTransition
    }
    diag.endStep('autoFit', tFit)
  }

  const resetAdaptive = () => {
    autoFitDiagram()
  }

  /**
   * [FIX 2026-07-31] 居中显示指定 SVG 元素 (annotation 面板点击后调用)
   *   设计意图: 选中 annotation 后, 用户期望图表自动滚到对应元素居中
   *     - 节点 (g.node), 容器 (subgraph/cluster), 连线 (edgeLabel/path) 都支持
   *     - 不修改 scale (保持当前缩放), 只平移到目标中心
   *     - 平滑动画 (transform transition) - 300ms ease
   *
   *   公式推导 (transform-origin: center, transform: translate(t) scale(s)):
   *     内容点 c 经过变换后屏幕位置 v = O + (c - O) * s + t
   *     其中 O = 内容元素未变换时中心（transform-origin: center 意味着 O = 内容元素中心点）
   *     设目标元素变换后屏幕位置 v_target, 我们要变换后 v_target_new = screenCenter:
   *       screenCenter = O + (c_target - O) * s + t_new
   *       t_new = screenCenter - O - (c_target - O) * s
   *     从 v_target 反推 c_target: c_target = O + (v_target - O - t_old) / s
   *     代入: t_new = screenCenter - O - (v_target - O - t_old)
   *          = screenCenter - v_target + t_old
   *     即: 增量平移 = screenCenter - v_target (与 scale 无关！)
   *     端到端测试: scale=0.5/1/2 都精确居中 (diff = 0)
   *
   * @param {SVGElement} svgEl - mermaid SVG 根元素 (未使用, 保留参数兼容性)
   * @param {SVGElement} targetEl - 目标节点/容器/连线元素
   * @returns {boolean} 是否成功居中
   */
  const centerElement = (svgEl, targetEl) => {
    if (!targetEl) return false
    // [FIX 2026-08-01] 居中操作埋点 — chart_diag 报告里可看到 centerElement 调了几次,
    //   dx/dy 各多少, 元素 tag/class. 排查 "click 没居中" 类问题时直接 dump 看是否调用过.
    const tCenter = diag.time('centerElement')
    try {
      // [FIX 2026-08-01 v5] 路径中心用 bbox 几何中心 (getBBox + getScreenCTM).
      //   实测对比三种方案:
      //     - midStroke (getPointAtLength/totalLen): 对长 L 型折线 path,
      //       midStroke 可能落在 stroke 起点附近 (例如 line 总长 1791 但起点段只有 19px → midStroke
      //       几乎紧贴起点), 完全不代表视觉中心, 用户感知"偏的比较多"
      //     - screen rect center (getBoundingClientRect): 与 bbox center 在 SVG 用户空间相同,
      //       但 getBoundingClientRect 包含了 stroke 宽度 + CSS transforms 的累积影响,
      //       对 path 而言与 bbox center 几乎一致
      //     - bbox center (getBBox + getScreenCTM): 几何包围盒中心, 对任何形状都是
      //       "用户视觉感知的线段中心"——线段两端与中心一目了然, 是居中连线最直观的锚点
      // [FIX 2026-08-01 v5.1] 之前 v3 漏掉了 let centerX = null, centerY = null 声明,
      //   改成赋值未声明变量 → ReferenceError → centerElement 总是 throw 然后 return false.
      //   当时用户反馈"偏的比较多"实际是"根本没动"——因为函数抛错提前 return.
      //   现在先声明, 再按类型计算.
      let centerX = null
      let centerY = null
      const svg = svgEl || targetEl.closest('svg')

      /**
       * 取 SVG 元素的"几何中心" (基于 getBBox, 不含 stroke)
       * getScreenCTM 返回 SVG 用户空间 → 屏幕空间的变换矩阵
       * 二者结合 = 几何中心在屏幕坐标上的精确位置
       */
      const getBBoxCenterScreen = (el) => {
        if (!el || typeof el.getBBox !== 'function') return null
        let bbox
        try { bbox = el.getBBox() } catch (e) { return null }
        if (!bbox) return null
        const ctm = el.getScreenCTM()
        if (!ctm) return null
        const cx = bbox.x + bbox.width / 2
        const cy = bbox.y + bbox.height / 2
        return {
          x: cx * ctm.a + cy * ctm.c + ctm.e,
          y: cx * ctm.b + cy * ctm.d + ctm.f
        }
      }

      if (targetEl.tagName && targetEl.tagName.toLowerCase() === 'path') {
        // [FIX v5] path 元素: 用 bbox center (getBBox + getScreenCTM)
        //   几何中心是线段最直观的"中点"——用户看到两端和中间, 都能看到全貌
        const c = getBBoxCenterScreen(targetEl)
        if (c) {
          centerX = c.x
          centerY = c.y
        } else {
          // 兜底
          const targetRect = targetEl.getBoundingClientRect()
          if (targetRect && (targetRect.width > 0 || targetRect.height > 0)) {
            centerX = targetRect.left + targetRect.width / 2
            centerY = targetRect.top + targetRect.height / 2
          }
        }
      } else if (targetEl.tagName && targetEl.tagName.toLowerCase() === 'g') {
        // [FIX 2026-08-01 v5.2] onSvgClick 经常传入 g.edge / g.node / g.subgraph 等父元素,
        //   而不是直接的 path/node/rect 子元素. 这里判断 g 是否包含 path → 当作连线处理.
        //   这样无论调用方传 path 还是 g.edge, 都能精确居中到 path bbox 中心.
        const innerPath = targetEl.querySelector('path.flowchart-link, path[data-relation-code]')
        if (innerPath) {
          const c = getBBoxCenterScreen(innerPath)
          if (c) {
            centerX = c.x
            centerY = c.y
          }
        }
        // 节点/容器 g: 用 g 自身的 bbox center (节点 g 含 rect+label, 容器 g 含 cluster rect)
        if (centerX === null || centerY === null) {
          const c = getBBoxCenterScreen(targetEl)
          if (c) {
            centerX = c.x
            centerY = c.y
          } else {
            const targetRect = targetEl.getBoundingClientRect()
            if (targetRect && (targetRect.width > 0 || targetRect.height > 0)) {
              centerX = targetRect.left + targetRect.width / 2
              centerY = targetRect.top + targetRect.height / 2
            }
          }
        }
      } else if (targetEl.classList && targetEl.classList.contains('edgeLabel')) {
        // [FIX v5] edgeLabel: 找最近的 path (基于 bbox center), 用 path 的 bbox center
        //   label rect 中心 ≈ label 视觉中心, 不代表"连线位置"
        //   最近的 path 的 bbox center = 连线的几何中心
        const labelRect = targetEl.getBoundingClientRect()
        const labelCenter = { x: labelRect.left + labelRect.width / 2, y: labelRect.top + labelRect.height / 2 }
        let bestPath = null
        let bestDist = Infinity
        const allPaths = svg.querySelectorAll('path.flowchart-link, path[data-relation-code]')
        allPaths.forEach(p => {
          try {
            const c = getBBoxCenterScreen(p)
            if (!c) return
            const d = Math.abs(c.x - labelCenter.x) + Math.abs(c.y - labelCenter.y)
            if (d < bestDist) { bestDist = d; bestPath = { el: p, center: c } }
          } catch (e) { /* skip */ }
        })
        if (bestPath) {
          centerX = bestPath.center.x
          centerY = bestPath.center.y
        }
      }

      if (centerX === null || centerY === null) {
        // 兜底: 用 getBoundingClientRect (节点/容器通常走到这里)
        const targetRect = targetEl.getBoundingClientRect()
        if (!targetRect || (targetRect.width === 0 && targetRect.height === 0)) return false
        centerX = targetRect.left + targetRect.width / 2
        centerY = targetRect.top + targetRect.height / 2
      }

      const contentEl = document.querySelector('.mermaid-content')
      if (!contentEl) return false
      const wrapper = document.querySelector('.mermaid-wrapper') || document.querySelector('.mermaid-container')
      const wrapperRect = wrapper ? wrapper.getBoundingClientRect() : null
      if (!wrapperRect) return false

      const screenCenter = {
        x: wrapperRect.left + wrapperRect.width / 2,
        y: wrapperRect.top + wrapperRect.height / 2
      }
      // 增量平移 = (屏幕中心 - 目标当前位置), 与 scale 无关
      const dx = screenCenter.x - centerX
      const dy = screenCenter.y - centerY

      // 加过渡动画让移动看起来平滑 (不影响其他 transform 操作)
      const prevTransition = contentEl.style.transition
      contentEl.style.transition = 'transform 0.3s ease'
      translateX.value = translateX.value + dx
      translateY.value = translateY.value + dy
      updateTransform()
      // [FIX 2026-08-01] 记录居中结果 (成功路径)
      diag.recordStepMeta('centerElement', {
        tag: targetEl.tagName,
        klass: (targetEl.getAttribute && targetEl.getAttribute('class')) || '',
        id: targetEl.id || '',
        centerX, centerY, dx, dy,
        translateX: translateX.value,
        translateY: translateY.value,
        scale: scale.value,
        succeeded: true
      })
      diag.endStep('centerElement', tCenter)
      setTimeout(() => {
        contentEl.style.transition = prevTransition
      }, 350)
      return true
    } catch (e) {
      // [FIX 2026-08-01] 记录居中失败 — 排查 "click 没居中" 类问题核心信号
      diag.recordError(e, 'centerElement')
      diag.recordStepMeta('centerElement', {
        tag: targetEl?.tagName || 'null',
        klass: (targetEl && targetEl.getAttribute && targetEl.getAttribute('class')) || '',
        succeeded: false,
        error: e?.message || String(e)
      })
      diag.endStep('centerElement', tCenter)
      console.warn('[centerElement] failed:', e)
      return false
    }
  }

  const addZoomAndPan = (mermaidContainerElRef, mermaidWrapperRef, mermaidContentRef) => {
    if (!mermaidContainerElRef?.value || !mermaidWrapperRef?.value || !mermaidContentRef?.value) return
    // [FIX 2026-08-01] 记录 zoom/pan/dblclick 监听器注册 — 排查 "拖拽/缩放没反应" 类问题
    diag.recordStepMeta('addZoomAndPan', {
      containerEl: mermaidContainerElRef.value?.tagName,
      wrapperEl: mermaidWrapperRef.value?.tagName,
      contentEl: mermaidContentRef.value?.tagName
    })

    // 关键修复 v10：把 wheel/mousedown/dblclick 绑在真 .mermaid-container 元素（mermaidContainerEl）上
    // 之前绑在 mermaidWrapper 上，全屏模式下 mermaidWrapper 仍受父级 CSS 限制，
    // 事件触不到或 transform 视觉上没效果
    // mermaid-container 在真全屏时占满整个屏幕，事件能稳定触发
    // [A3 2026-08-03] 收窄 zoom 边界到合理区间
    //   旧: 0.3 / 10 → 过小看不清字, 过大只能看一个节点
    //   新: 0.5 / 5 → 适配 Mermaid 11 节点字号 16px 的可视区间
    // [A4 2026-08-07] 用户反馈小对象范围(如仅一个子领域)时 5x 仍太小看不清 →
    //   提高上限到 10, 与 HTML 导出模板缩放上限一致, 允许放大到看清小图细节.
    // [A5 2026-08-16] 展开到业务对象后 10x 仍不足以看清 BO 文字 (fit 后大图文字仅 3-5px):
    //   调研: draw.io 5x, Mermaid 查看器 3-4x, vscode-mermaid-chart 5x(用户要 10x),
    //   Figma 16x, Miro 官方 2000%(20x). 上限提到 20x (对齐 Miro), 覆盖数百 BO 大图.
    const minScale = 0.5
    const maxScale = 20

    const handleWheel = (e) => {
      e.preventDefault()

      // [A1 2026-08-03] zoom 步长对称化: in/out 互为倒数, 避免 in→out 不回 1.0 的 drift
      //   旧: 0.9 / 1.1 → 5 次 in + 5 次 out 后 scale drift 至 0.886 (误差 -0.114)
      //   新: (1/1.1) / 1.1 → 严格互为倒数, drift < 0.001
      const zoomFactor = e.deltaY > 0 ? 1 / 1.1 : 1.1
      const newScale = Math.max(minScale, Math.min(maxScale, scale.value * zoomFactor))
      if (newScale === scale.value) return

      // 以图表可视区域（mermaid-wrapper）中央作为缩放中心
      // 参考 HTML 导出缩放中心修复 pattern (MermaidComponent.vue line 1449-1477)
      const wrapperRect = mermaidWrapperRef.value.getBoundingClientRect()
      const cx = wrapperRect.left + wrapperRect.width / 2
      const cy = wrapperRect.top + wrapperRect.height / 2

      // .mermaid-content 元素未变换时中心视口位置 O
      // transform-origin: center center 让缩放绕 O 进行，但 translate 会平移整个元素
      // 所以变换后 rect 中心 = O + translate，反推 O = 变换后 rect 中心 - translate
      const contentRect = mermaidContentRef.value.getBoundingClientRect()
      const ox = contentRect.left + contentRect.width / 2 - translateX.value
      const oy = contentRect.top + contentRect.height / 2 - translateY.value

      // 视口点 v 与内容点 c 的关系（transform-origin: center, transform: translate(t) scale(s)）：
      //   v = (c - o) * s + o + t   =>   c = (v - o - t) / s + o
      // 求屏幕中央 (cx, cy) 对应的内容点
      const xContent = (cx - ox - translateX.value) / scale.value + ox
      const yContent = (cy - oy - translateY.value) / scale.value + oy

      // 缩放后让该内容点仍对应屏幕中央
      //   t = v - (c - o) * s - o
      translateX.value = cx - (xContent - ox) * newScale - ox
      translateY.value = cy - (yContent - oy) * newScale - oy

      scale.value = newScale
      updateTransform(mermaidContentRef)
    }

    const handleMouseDown = (e) => {
      // 关键修复 v13：用 window 捕获阶段绑 mousedown，确保 fullscreen 模式下事件一定触发
      if (e.button !== 0) return
      if (!mermaidContainerElRef?.value) return
      // 只在 mermaid-container 内的 mousedown 触发拖动
      if (!mermaidContainerElRef.value.contains(e.target)) return
      // [FIX 2026-06-29 v8] 不在 toolbar/annotation panel 等可点击区域才走拖动逻辑
      //   之前 e.preventDefault() 阻止了 click 事件, 导致 annotation header 等可点击元素无响应
      const isInToolbar = e.target.closest('.toolbar') || e.target.closest('.toolbar-btn')
      const isInAnnotation = e.target.closest('.annotation-dock-panel') || e.target.closest('.annotation-header')
      if (isInToolbar || isInAnnotation) return  // 不阻止默认, 让 click 事件正常触发

      dragState.isDragging = true
      dragState.wasDrag = false  // [FIX 2026-08-16] 每次 mousedown 重置"是否拖拽"标记
      dragState.startX = e.clientX - translateX.value
      dragState.startY = e.clientY - translateY.value
      // [FIX 2026-08-16] 记录 mousedown 时屏幕坐标, 供 handleMouseMove 计算"从按下起的总位移".
      //   之前用 startX + translateX.value 推算, 但 translateX 每次 move 都更新,
      //   导致 moved 只反映"上一次 move 的增量" — 慢速小幅拖动 (每次 <8px 累计 >8px) 永远
      //   不置 wasDrag=true, 拖拽结束的 click 会误清高亮. 现在直接存初始坐标, 稳定判断.
      dragState.clientX = e.clientX
      dragState.clientY = e.clientY
      mermaidContainerElRef.value.style.cursor = 'grabbing'
      mermaidContainerElRef.value.classList.add('dragging')
      // [v13 log 已移除, 避免 console spam]
    }

    const handleMouseMove = (e) => {
      if (!dragState.isDragging) {
        return
      }
      // [FIX 2026-08-16] 位移超过阈值 → 标记为拖拽. 供 click 处理判断"拖拽不取消高亮, 只有纯粹点击才取消".
      //   clientX/clientY 为 mousedown 时的初始屏幕坐标, 差值即本次拖拽总位移 (与 translate 无关).
      if (!dragState.wasDrag) {
        const moved = Math.abs(e.clientX - dragState.clientX) + Math.abs(e.clientY - dragState.clientY)
        if (moved > 8) dragState.wasDrag = true
      }
      translateX.value = e.clientX - dragState.startX
      translateY.value = e.clientY - dragState.startY
      updateTransform(mermaidContentRef)
    }

    const handleMouseUp = () => {
      if (dragState.isDragging && mermaidContainerElRef?.value) {
        mermaidContainerElRef.value.classList.remove('dragging')
        mermaidContainerElRef.value.style.cursor = 'grab'
      }
      dragState.isDragging = false
    }

    // [FIX 2026-08-08] 双击: 只有点击空白区域时才 autoFit, 不干扰节点/容器的业务双击逻辑
    //   根因: MermaidComponent.vue 的 @dblclick.prevent="handleDblClick" 在 .mermaid-wrapper 上
    //   处理折叠/展开业务逻辑, 而这里在 .mermaid-container 上也绑了 dblclick → autoFitDiagram()。
    //   两个 handler 都触发, 业务逻辑先执行, 但 autoFitDiagram() 随后重置视图。
    //   修复: 检测目标是否在节点/容器内, 是则跳过 autoFit, 由业务逻辑处理。
    const handleDblClick = (e) => {
      // 检查 event.target 是否在 g.node/g.cluster/g.subgraph 内部
      let el = e.target
      let isOnGroupElement = false
      while (el && el !== mermaidContainerElRef.value) {
        if (el.tagName === 'g') {
          const cls = (el.getAttribute('class') || '').trim().split(/\s+/)
          if (cls.includes('node') || cls.includes('cluster') || cls.includes('subgraph')) {
            isOnGroupElement = true
            break
          }
        }
        el = el.parentElement
      }
      if (!isOnGroupElement) {
        autoFitDiagram()
      }
    }

    // 关键修复 v18：mousemove/mouseup 改用 document bubble 模式绑（不要 capture）
    // v16 改 window capture 是错的：window.addEventListener(..., true) 只在 capture 阶段触发
    // dispatchEvent bubbles:true 的事件走 bubble 阶段，window capture listener 收不到
    // 改用 document (bubble)，document 一定会收到 bubble 阶段事件
    // mermaid 内部 stopPropagation 影响 window 不影响 document
    window.addEventListener('mousedown', handleMouseDown, true)  // mousedown 仍 capture（避免 mermaid 拦截）
    document.addEventListener('mousemove', handleMouseMove, false)  // bubble 模式
    document.addEventListener('mouseup', handleMouseUp, false)  // bubble 模式
    // wheel 和 dblclick 仍绑在 mermaidContainerEl 上（这两个在 fullscreen 模式下工作正常）
    mermaidContainerElRef.value.addEventListener('wheel', handleWheel, { passive: false })
    mermaidContainerElRef.value.addEventListener('dblclick', handleDblClick)

    mermaidContainerElRef.value.style.cursor = 'grab'

    // 关键修复 v18：返回清理函数
    // 关键修复 v19：补上 wheel/dblclick 的移除 — 否则切换图表时重复绑定导致 zoom 步长翻倍
    return () => {
      window.removeEventListener('mousedown', handleMouseDown, true)
      document.removeEventListener('mousemove', handleMouseMove, false)
      document.removeEventListener('mouseup', handleMouseUp, false)
      if (mermaidContainerElRef.value) {
        mermaidContainerElRef.value.removeEventListener('wheel', handleWheel)
        mermaidContainerElRef.value.removeEventListener('dblclick', handleDblClick)
      }
    }
  }

  return {
    scale,
    translateX,
    translateY,
    updateTransform,
    autoFitDiagram,
    resetAdaptive,
    centerElement,
    addZoomAndPan
  }
}
