import { ref } from 'vue'

// 关键修复 v19：用 window 全局对象共享拖动状态，跨 module reload 保持一致
// HMR 替换 module 后老 addZoomAndPan 闭包内的 let isDragging 与新 handleMouseMove 的 let isDragging 是不同变量
// 改用 window.__mermaidDrag 全局对象，所有 handler 引用同一对象，状态跨 HMR/闭包保持一致
const dragState = (typeof window !== 'undefined' && (window.__mermaidDrag || (window.__mermaidDrag = { isDragging: false, startX: 0, startY: 0 }))) || { isDragging: false, startX: 0, startY: 0 }

export function useInteraction() {
  const scale = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)

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
  const autoFitDiagram = () => {
    const container = document.querySelector('.mermaid-container')
    if (!container) return

    const containerWidth = container.offsetWidth
    const containerHeight = container.offsetHeight

    console.log('[autoFitDiagram] container size:', containerWidth, 'x', containerHeight)
    console.log('[autoFitDiagram] fit: scale=1, translate=(0,0) (CSS auto-scales SVG to container)')

    scale.value = 1
    translateX.value = 0
    translateY.value = 0

    updateTransform()
  }

  const resetAdaptive = () => {
    autoFitDiagram()
  }

  const addZoomAndPan = (mermaidContainerElRef, mermaidWrapperRef, mermaidContentRef) => {
    if (!mermaidContainerElRef?.value || !mermaidWrapperRef?.value || !mermaidContentRef?.value) return

    // 关键修复 v10：把 wheel/mousedown/dblclick 绑在真 .mermaid-container 元素（mermaidContainerEl）上
    // 之前绑在 mermaidWrapper 上，全屏模式下 mermaidWrapper 仍受父级 CSS 限制，
    // 事件触不到或 transform 视觉上没效果
    // mermaid-container 在真全屏时占满整个屏幕，事件能稳定触发
    const minScale = 0.3
    const maxScale = 10

    const handleWheel = (e) => {
      e.preventDefault()

      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
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
      dragState.startX = e.clientX - translateX.value
      dragState.startY = e.clientY - translateY.value
      mermaidContainerElRef.value.style.cursor = 'grabbing'
      mermaidContainerElRef.value.classList.add('dragging')
      // [v13 log 已移除, 避免 console spam]
    }

    const handleMouseMove = (e) => {
      if (!dragState.isDragging) {
        return
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

    const handleDblClick = () => {
      autoFitDiagram()
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
    return () => {
      window.removeEventListener('mousedown', handleMouseDown, true)
      document.removeEventListener('mousemove', handleMouseMove, false)
      document.removeEventListener('mouseup', handleMouseUp, false)
    }
  }

  return {
    scale,
    translateX,
    translateY,
    updateTransform,
    autoFitDiagram,
    resetAdaptive,
    addZoomAndPan
  }
}
