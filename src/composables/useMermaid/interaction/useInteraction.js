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
    const maxScale = 3

    const handleWheel = (e) => {
      e.preventDefault()

      const rect = mermaidContentRef.value.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top

      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
      const newScale = Math.max(minScale, Math.min(maxScale, scale.value * zoomFactor))

      const centerX = rect.width / 2
      const centerY = rect.height / 2

      const offsetX = mouseX - centerX
      const offsetY = mouseY - centerY

      const scaleDiff = newScale - scale.value
      translateX.value = translateX.value - offsetX * scaleDiff
      translateY.value = translateY.value - offsetY * scaleDiff

      scale.value = newScale
      updateTransform(mermaidContentRef)
    }

    const handleMouseDown = (e) => {
      // 关键修复 v13：用 window 捕获阶段绑 mousedown，确保 fullscreen 模式下事件一定触发
      if (e.button !== 0) return
      if (!mermaidContainerElRef?.value) return
      // 只在 mermaid-container 内的 mousedown 触发拖动
      if (!mermaidContainerElRef.value.contains(e.target)) return
      if (e.target.closest('.toolbar') || e.target.closest('.toolbar-btn')) return
      e.preventDefault()  // 阻止默认行为（防文本选择等）

      dragState.isDragging = true
      dragState.startX = e.clientX - translateX.value
      dragState.startY = e.clientY - translateY.value
      mermaidContainerElRef.value.style.cursor = 'grabbing'
      mermaidContainerElRef.value.classList.add('dragging')
      // 关键修复 v13：加 log 让用户能验证 mousedown 触发
      console.log('[drag] mousedown', { startX: dragState.startX, startY: dragState.startY, target: e.target.tagName })
    }

    const handleMouseMove = (e) => {
      // 关键诊断 v17：log 每次 mousemove 触发，让用户能看到 mousemove 次数
      console.log('[drag] mousemove, isDragging=', dragState.isDragging, 'e.clientX=', e.clientX)
      if (!dragState.isDragging) {
        return
      }
      translateX.value = e.clientX - dragState.startX
      translateY.value = e.clientY - dragState.startY
      updateTransform(mermaidContentRef)
    }

    const handleMouseUp = () => {
      if (dragState.isDragging) {
        console.log('[drag] mouseup, final translate:', translateX.value, translateY.value)
      }
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
