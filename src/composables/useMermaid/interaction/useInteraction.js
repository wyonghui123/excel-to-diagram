import { ref } from 'vue'

export function useInteraction() {
  const scale = ref(1)
  const translateX = ref(0)
  const translateY = ref(0)
  let isDragging = false
  let startX = 0
  let startY = 0

  const updateTransform = (draggableAreaRef) => {
    const el = draggableAreaRef?.value || document.querySelector('.draggable-area')
    if (el) {
      const transformValue = `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`
      el.style.transform = transformValue
    }
  }

  const autoFitDiagram = () => {
    const container = document.querySelector('.mermaid-container')
    const draggableAreaEl = document.querySelector('.draggable-area')
    const svg = document.querySelector('.mermaid-content svg')
    const content = document.querySelector('.mermaid-content')

    if (!container || !draggableAreaEl || !svg) {
      return
    }

    const containerWidth = container.offsetWidth
    const containerHeight = container.offsetHeight

    let contentWidth = 0
    let contentHeight = 0

    // 优先使用 viewBox 获取尺寸
    const viewBox = svg.getAttribute('viewBox')
    if (viewBox) {
      const parts = viewBox.split(' ').map(Number)
      contentWidth = parts[2]
      contentHeight = parts[3]
    }

    // 如果 viewBox 无效，尝试其他方法
    if (contentWidth <= 0 || contentHeight <= 0) {
      const svgRect = svg.getBoundingClientRect()
      contentWidth = svgRect.width
      contentHeight = svgRect.height
    }

    // 检查 SVG 的 width/height 属性
    const svgWidthAttr = svg.getAttribute('width')
    const svgHeightAttr = svg.getAttribute('height')
    if (svgWidthAttr && svgHeightAttr) {
      const parsedWidth = parseFloat(svgWidthAttr)
      const parsedHeight = parseFloat(svgHeightAttr)
      if (parsedWidth > 0 && parsedHeight > 0) {
        contentWidth = parsedWidth
        contentHeight = parsedHeight
      }
    }

    // 检查 SVG 的 style.width/height
    const svgStyleWidth = svg.style.width
    const svgStyleHeight = svg.style.height
    if (svgStyleWidth && svgStyleHeight) {
      const parsedWidth = parseFloat(svgStyleWidth)
      const parsedHeight = parseFloat(svgStyleHeight)
      if (parsedWidth > 0 && parsedHeight > 0) {
        contentWidth = parsedWidth
        contentHeight = parsedHeight
      }
    }

    // 最后的兜底
    if (contentWidth <= 0 || contentHeight <= 0) {
      contentWidth = svg.scrollWidth || svg.clientWidth || 800
      contentHeight = svg.scrollHeight || svg.clientHeight || 600
    }

    console.log('[autoFitDiagram] content size:', contentWidth, contentHeight)
    console.log('[autoFitDiagram] container size:', containerWidth, containerHeight)

    const scaleX = containerWidth / contentWidth
    const scaleY = containerHeight / contentHeight
    const fillRatio = 0.92
    scale.value = Math.min(scaleX, scaleY) * fillRatio
    translateX.value = 0
    translateY.value = 0
    console.log('[autoFitDiagram] calculated scale:', scale.value)
    updateTransform()
  }

  const resetAdaptive = () => {
    autoFitDiagram()
  }

  const addZoomAndPan = (mermaidWrapperRef, mermaidContainerRef, draggableAreaRef) => {
    if (!mermaidWrapperRef?.value || !mermaidContainerRef?.value) return

    const svg = mermaidContainerRef.value.querySelector('svg')
    if (!svg) return

    let contentWidth, contentHeight
    const viewBox = svg.getAttribute('viewBox')
    if (viewBox) {
      const parts = viewBox.split(' ').map(Number)
      contentWidth = parts[2]
      contentHeight = parts[3]
    } else {
      contentWidth = svg.scrollWidth || svg.clientWidth
      contentHeight = svg.scrollHeight || svg.clientHeight
    }

    const containerRect = mermaidContainerRef.value.getBoundingClientRect()
    const containerWidth = containerRect.width
    const containerHeight = containerRect.height

    const minScaleX = containerWidth / contentWidth
    const minScaleY = containerHeight / contentHeight
    const minScale = Math.max(0.01, Math.min(minScaleX, minScaleY) * 0.15)

    if (draggableAreaRef?.value) {
      draggableAreaRef.value.style.backgroundColor = '#F0F0F0'
    }

    const handleWheel = (e) => {
      e.preventDefault()

      const rect = draggableAreaRef.value.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top

      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1
      const newScale = Math.max(minScale, Math.min(3, scale.value * zoomFactor))

      const centerX = rect.width / 2
      const centerY = rect.height / 2

      const offsetX = mouseX - centerX
      const offsetY = mouseY - centerY

      const scaleDiff = newScale - scale.value
      translateX.value = translateX.value - offsetX * scaleDiff
      translateY.value = translateY.value - offsetY * scaleDiff

      scale.value = newScale
      updateTransform(draggableAreaRef)
    }

    const handleMouseDown = (e) => {
      const target = e.target
      if (target.closest('.node') || target.closest('.edgePath') || target.closest('.edgeLabel')) {
        return
      }

      isDragging = true
      startX = e.clientX - translateX.value
      startY = e.clientY - translateY.value
      draggableAreaRef.value.style.cursor = 'grabbing'
      draggableAreaRef.value.classList.add('dragging')
    }

    const handleMouseMove = (e) => {
      if (!isDragging) return

      translateX.value = e.clientX - startX
      translateY.value = e.clientY - startY
      updateTransform(draggableAreaRef)
    }

    const handleMouseUp = () => {
      if (isDragging && draggableAreaRef?.value) {
        draggableAreaRef.value.classList.remove('dragging')
        draggableAreaRef.value.style.cursor = 'grab'
      }
      isDragging = false
    }

    const handleDblClick = () => {
      autoFitDiagram()
    }

    draggableAreaRef.value.addEventListener('wheel', handleWheel, { passive: false })
    draggableAreaRef.value.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    draggableAreaRef.value.addEventListener('dblclick', handleDblClick)

    draggableAreaRef.value.style.cursor = 'grab'
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
