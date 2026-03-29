export function useInteraction() {
  let scale = 1
  let translateX = 0
  let translateY = 0
  let isDragging = false
  let startX = 0
  let startY = 0

  const updateTransform = (draggableAreaRef) => {
    const el = draggableAreaRef?.value || document.querySelector('.draggable-area')
    if (el) {
      const transformValue = `translate(${translateX}px, ${translateY}px) scale(${scale})`
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

    const svgRect = svg.getBoundingClientRect()
    const contentRect = content?.getBoundingClientRect() || svgRect

    let contentWidth = svgRect.width
    let contentHeight = svgRect.height

    if (contentWidth === 0 || contentHeight === 0) {
      const viewBox = svg.getAttribute('viewBox')
      if (viewBox) {
        const parts = viewBox.split(' ').map(Number)
        contentWidth = parts[2]
        contentHeight = parts[3]
      } else {
        contentWidth = svg.scrollWidth || svg.clientWidth || 800
        contentHeight = svg.scrollHeight || svg.clientHeight || 600
      }
    }

    const scaleX = containerWidth / contentWidth
    const scaleY = containerHeight / contentHeight
    const fillRatio = 0.92
    scale = Math.min(scaleX, scaleY) * fillRatio
    translateX = 0
    translateY = 0
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
      const newScale = Math.max(minScale, Math.min(3, scale * zoomFactor))

      const centerX = rect.width / 2
      const centerY = rect.height / 2

      const offsetX = mouseX - centerX
      const offsetY = mouseY - centerY

      const scaleDiff = newScale - scale
      translateX = translateX - offsetX * scaleDiff
      translateY = translateY - offsetY * scaleDiff

      scale = newScale
      updateTransform(draggableAreaRef)
    }

    const handleMouseDown = (e) => {
      const target = e.target
      if (target.closest('.node') || target.closest('.edgePath') || target.closest('.edgeLabel')) {
        return
      }

      isDragging = true
      startX = e.clientX - translateX
      startY = e.clientY - translateY
      draggableAreaRef.value.style.cursor = 'grabbing'
      draggableAreaRef.value.classList.add('dragging')
    }

    const handleMouseMove = (e) => {
      if (!isDragging) return

      translateX = e.clientX - startX
      translateY = e.clientY - startY
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