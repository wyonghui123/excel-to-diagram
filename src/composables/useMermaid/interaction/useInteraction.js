import { ref } from 'vue'

export function useInteraction() {
  const scale = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)
  let isDragging = false
  let startX = 0
  let startY = 0

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

  const addZoomAndPan = (mermaidWrapperRef, mermaidContainerRef, mermaidContentRef) => {
    if (!mermaidWrapperRef?.value || !mermaidContainerRef?.value) return

    // 缩放范围：fit=1（CSS 已让 SVG 100% 容器高度），用户可放大到 3x，缩小到 0.3x
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
      const target = e.target
      if (target.closest('.node') || target.closest('.edgePath') || target.closest('.edgeLabel')) {
        return
      }

      isDragging = true
      startX = e.clientX - translateX.value
      startY = e.clientY - translateY.value
      mermaidWrapperRef.value.style.cursor = 'grabbing'
      mermaidWrapperRef.value.classList.add('dragging')
    }

    const handleMouseMove = (e) => {
      if (!isDragging) return

      translateX.value = e.clientX - startX
      translateY.value = e.clientY - startY
      updateTransform(mermaidContentRef)
    }

    const handleMouseUp = () => {
      if (isDragging && mermaidWrapperRef?.value) {
        mermaidWrapperRef.value.classList.remove('dragging')
        mermaidWrapperRef.value.style.cursor = 'grab'
      }
      isDragging = false
    }

    const handleDblClick = () => {
      autoFitDiagram()
    }

    mermaidWrapperRef.value.addEventListener('wheel', handleWheel, { passive: false })
    mermaidWrapperRef.value.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    mermaidWrapperRef.value.addEventListener('dblclick', handleDblClick)

    mermaidWrapperRef.value.style.cursor = 'grab'
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
