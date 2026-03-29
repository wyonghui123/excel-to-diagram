import { ref, nextTick } from 'vue'
import mermaid from 'mermaid'
import { useMermaidConfig } from '../config/useMermaidConfig.js'
import { useBusinessObjectSyntax } from '../syntax/useBusinessObjectSyntax.js'
import { useServiceModuleSyntax } from '../syntax/useServiceModuleSyntax.js'
import { routeLayout } from '../layouts/index.js'

export function useMermaidRenderer(containerRef, options = {}) {
  const { onRenderComplete, onError } = options

  const isRendered = ref(false)
  const lastDiagramData = ref(null)
  const lastLayoutConfig = ref(null)

  const { initializeMermaid } = useMermaidConfig()

  const render = (diagramData, diagramType = 'businessObject', layoutConfig = null) => {
    if (!containerRef.value || !diagramData) {
      console.warn('渲染条件不满足')
      return false
    }

    try {
      lastDiagramData.value = diagramData
      lastLayoutConfig.value = layoutConfig

      const layoutEngine = layoutConfig?.layoutEngine || 'dagre'
      const layoutType = layoutConfig?.layoutType || 'default'
      const preserveModelOrder = layoutConfig?.preserveModelOrder || false

      initializeMermaid(diagramType, null, layoutEngine, layoutType, preserveModelOrder)

      const syntax = diagramType === 'serviceModule'
        ? useServiceModuleSyntax()
        : useBusinessObjectSyntax()

      const relationDescriptions = []
      let mermaidCode = syntax.generateMermaidCode(
        diagramData, 
        relationDescriptions, 
        layoutEngine, 
        layoutType, 
        layoutConfig
      )
      console.log('Generated mermaid code length:', mermaidCode.length)

      if (layoutType !== 'default' && layoutConfig?.containers) {
        try {
          const layoutSyntax = routeLayout(layoutConfig.containers, {
            layoutType,
            positions: layoutConfig.positions || []
          })

          if (layoutSyntax) {
            mermaidCode = mermaidCode + '\n' + layoutSyntax
            console.log('Layout syntax applied, new code length:', mermaidCode.length)
          }
        } catch (layoutError) {
          console.warn('Layout generation failed, using default layout:', layoutError)
        }
      }

      containerRef.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`

      nextTick(() => {
        mermaid.run().then(() => {
          console.log('mermaid.run() completed')
          setTimeout(() => {
            const svg = containerRef.value.querySelector('svg')
            if (svg) {
              const svgViewBox = svg.getAttribute('viewBox')
              if (svgViewBox) {
                const parts = svgViewBox.split(' ').map(Number)
                if (parts[0] < 0 || parts[1] < 0) {
                  const padding = 20
                  const newViewBox = `${parts[0] - padding} ${parts[1] - padding} ${parts[2] + padding * 2} ${parts[3] + padding * 2}`
                  svg.setAttribute('viewBox', newViewBox)
                }
              }

              const wrapper = containerRef.value.closest('.mermaid-wrapper')
              const draggableArea = containerRef.value.closest('.draggable-area')

              if (wrapper && draggableArea) {
                const canvasSize = 8000
                const skySize = canvasSize * 1.5

                wrapper.style.width = skySize + 'px'
                wrapper.style.height = skySize + 'px'
                wrapper.style.left = '50%'
                wrapper.style.top = '50%'
                wrapper.style.marginLeft = (-skySize / 2) + 'px'
                wrapper.style.marginTop = (-skySize / 2) + 'px'

                draggableArea.style.width = canvasSize + 'px'
                draggableArea.style.height = canvasSize + 'px'
                draggableArea.style.left = '50%'
                draggableArea.style.top = '50%'
                draggableArea.style.marginLeft = (-canvasSize / 2) + 'px'
                draggableArea.style.marginTop = (-canvasSize / 2) + 'px'
                draggableArea.style.backgroundColor = '#E0E0E0'
              }

              isRendered.value = true
              onRenderComplete?.()
            }
          }, 300)
        }).catch((err) => {
          console.error('mermaid.run() error:', err)
          onError?.(err)
        })
      })

      return true
    } catch (error) {
      console.error('Mermaid渲染失败:', error)
      onError?.(error)
      return false
    }
  }

  const reRender = () => {
    if (lastDiagramData.value) {
      return render(lastDiagramData.value, 'businessObject', lastLayoutConfig.value)
    }
    return false
  }

  return {
    isRendered,
    lastDiagramData,
    render,
    reRender
  }
}
