import { ref, nextTick } from 'vue'
import mermaid from 'mermaid'
import { useMermaidConfig } from '../config/useMermaidConfig.js'
import { useBusinessObjectSyntax } from '../syntax/useBusinessObjectSyntax.js'
import { useServiceModuleSyntax } from '../syntax/useServiceModuleSyntax.js'
import { routeLayout } from '../layouts/index.js'
import { useDiagnostics } from './useDiagnostics.js'

export function useMermaidRenderer(containerRef, options = {}) {
  const { onRenderComplete, onError } = options
  const diag = useDiagnostics()

  const isRendered = ref(false)
  const lastDiagramData = ref(null)
  const lastLayoutConfig = ref(null)
  const lastMermaidCode = ref('')  // [v34 双向支持] 暴露给 dev/__diagramApp, E2E 可读取诊断 syntax error

  const { initializeMermaid } = useMermaidConfig()

  /**
   * [FIX 2026-08-01] 渲染入口埋点 — 记录开始时间, 触发 hooks.onRenderStart.
   * chart_diag 通过 hooks.onRenderStart/onRenderEnd 测量完整渲染耗时,
   * 不需要再依赖 chart_diag 自己的 setTimeout.
   */
  const render = (diagramData, diagramType = 'businessObject', layoutConfig = null) => {
    if (!containerRef.value || !diagramData) {
      diag.recordWarning('渲染条件不满足: containerRef or diagramData missing', 'render')
      return false
    }

    // [FIX 2026-08-01] 渲染开始埋点 — 替代散落的 console.log
    diag.beginRender({ diagramType, layoutEngine: layoutConfig?.layoutEngine })
    const tSyntax = diag.time('syntax_gen')

    try {
      lastDiagramData.value = diagramData
      lastLayoutConfig.value = layoutConfig

      const layoutEngine = layoutConfig?.layoutEngine || 'dagre'
      const layoutType = layoutConfig?.layoutType || 'default'
      const preserveModelOrder = layoutConfig?.preserveModelOrder || false

      initializeMermaid(diagramType, null, layoutEngine, layoutType, preserveModelOrder, layoutConfig)

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
      // [v34 双向支持] 保存到 ref, E2E 可从 window 读取
      lastMermaidCode.value = mermaidCode
      diag.endStep('syntax_gen', tSyntax)

      if (layoutType !== 'default' && layoutConfig?.containers) {
        try {
          const layoutSyntax = routeLayout(layoutConfig.containers, {
            layoutType,
            positions: layoutConfig.positions || []
          })

          if (layoutSyntax) {
            mermaidCode = mermaidCode + '\n' + layoutSyntax
          }
        } catch (layoutError) {
          diag.recordError(layoutError, 'routeLayout')
        }
      }

      containerRef.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`

      const tRun = diag.time('mermaid_run')
      nextTick(() => {
        mermaid.run().then(() => {
          diag.endStep('mermaid_run', tRun)
          // [FIX 2026-08-01] 移除魔法 setTimeout(300), 直接处理 (SVG 已渲染到 DOM).
          //   旧实现: 硬等 300ms, 慢机器超时 / 快机器浪费时间.
          //   新实现: mermaid.run() resolve 时 SVG 已在 DOM, 浏览器 layout 自动完成 (CSS height:100%).
          const svg = containerRef.value?.querySelector('svg')
          if (!svg) {
            diag.recordWarning('mermaid.run() resolved but no SVG found', 'render')
            diag.endRender({ mermaidCode, layoutEngine, error: 'no_svg' })
            onError?.(new Error('mermaid.run() resolved but no SVG found'))
            return
          }
          finishRender(svg, mermaidCode, layoutEngine)
        }).catch((err) => {
          diag.endStep('mermaid_run', tRun)
          diag.recordError(err, 'mermaid.run')
          diag.endRender({ mermaidCode, layoutEngine, error: err?.message || String(err) })
          console.error('mermaid.run() error:', err)
          onError?.(err)
        })
      })

      return true
    } catch (error) {
      diag.recordError(error, 'render.sync')
      diag.endRender({
        mermaidCode: lastMermaidCode.value,
        layoutEngine: layoutConfig?.layoutEngine,
        error: error?.message || String(error)
      })
      console.error('Mermaid渲染失败:', error)
      onError?.(error)
      return false
    }
  }

  /**
   * [FIX 2026-08-01] SVG 渲染完成后的处理 — 抽出独立函数, 替代原 setTimeout(300) 内的内联代码.
   * 时序: mermaid.run() 完成后 svg 已在 DOM, 浏览器 layout 自动完成 (CSS height:100%).
   * 不再依赖 setTimeout 固定延迟.
   */
  const finishRender = (svg, mermaidCode, layoutEngine) => {
    const tPost = diag.time('post_render')

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
      // 画布背景: 白色 (与 MermaidComponent.css .draggable-area 一致, 用户偏好)
      draggableArea.style.backgroundColor = '#FFFFFF'
    }

    // 统计渲染结果元数据 (chart_diag 一键读取)
    const nodeCount = svg.querySelectorAll('g.node').length
    const edgeCount = svg.querySelectorAll('path.flowchart-link').length
    const containerCount = svg.querySelectorAll('g.cluster').length

    isRendered.value = true
    diag.endStep('post_render', tPost)
    diag.endRender({
      mermaidCode,
      layoutEngine,
      nodeCount,
      edgeCount,
      containerCount
    })
    onRenderComplete?.()
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
    lastMermaidCode,  // [v34 双向支持] E2E 诊断用
    render,
    reRender
  }
}