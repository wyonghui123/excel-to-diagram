<template> 
  <div ref="mermaidContainerEl" class="mermaid-container" :class="{ 'maximized': isMaximized }">
    <div class="toolbar">
      <!-- 查看操作组 -->
      <div class="toolbar-group">
        <button class="toolbar-btn" @click="resetAdaptive" title="重置视图">
          <AppIcon name="refresh" size="sm" />
          <span class="toolbar-btn-label">重置</span>
        </button>
        <button class="toolbar-btn" @click="toggleMaximize" :title="isMaximized ? '退出全屏' : '全屏查看'">
          <AppIcon :name="isMaximized ? 'fullscreen-exit' : 'fullscreen'" size="sm" />
          <span class="toolbar-btn-label">{{ isMaximized ? '退出' : '全屏' }}</span>
        </button>
      </div>
      
      <span class="toolbar-divider"></span>
      
      <!-- 导出操作组 -->
      <div class="toolbar-group">
        <button class="toolbar-btn" @click="copyToClipboard" title="复制代码">
          <AppIcon name="copy" size="sm" />
          <span class="toolbar-btn-label">复制</span>
        </button>
        <button class="toolbar-btn toolbar-btn--primary" @click="exportAsHtmlFull" title="导出 HTML（彩色版 - 可直接双击打开）">
          <AppIcon name="export" size="sm" />
          <span class="toolbar-btn-label">彩色HTML</span>
        </button>
        <button class="toolbar-btn toolbar-btn--primary" @click="exportAsPdf" title="导出 PDF（横版矢量图）">
          <AppIcon name="export" size="sm" />
          <span class="toolbar-btn-label">PDF</span>
        </button>
      </div>
    </div>

    <div class="mermaid-wrapper" ref="mermaidWrapper">
      <div class="draggable-area" ref="draggableArea">
        <div class="diagram-canvas">
          <div ref="mermaidContainer" class="mermaid-content" :class="[diagramType, { 'hide-tails': shouldHideTails }]"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue'
import mermaid from 'mermaid'
import { jsPDF } from 'jspdf'
// eslint-disable-next-line no-unused-vars -- svg2pdf.js 注册 jsPDF 的 .svg() 方法
import 'svg2pdf.js'
import html2canvas from 'html2canvas'
import { AppIcon } from './common/AppIcon'
import { useDiagramConfigStore } from '../stores/diagramConfigStore.js'

import { useMermaidConfig } from '../composables/useMermaid/config/useMermaidConfig.js'
import { useInteraction } from '../composables/useMermaid/interaction/useInteraction.js'
import { useBusinessObjectSyntax, useServiceModuleSyntax } from '../composables/useMermaid/syntax/index.js'
import { useSvgStyle } from '../composables/useMermaid/style/index.js'
import { useTooltip } from '../composables/useMermaid/tooltip/index.js'
import { useMermaidColors } from '../composables/useMermaid/color/index.js'
import { useMermaidDataMap } from '../composables/useMermaid/dataMap/index.js'
import { useAnnotation, useAnnotationOverlay } from '../composables/useMermaid/annotation/index.js'
import { loadElkLayouts } from '../composables/useMermaid/renderer/useElkLoader.js'
import { useSvgProcessor } from '../composables/useMermaid/renderer/useSvgProcessor.js'
import './MermaidComponent.css'

export default {
  name: 'MermaidComponent',
  components: {
    AppIcon
  },
  props: {
    diagramData: {
      type: Object,
      default: null
    },
    diagramType: {
      type: String,
      default: 'businessObject',
      validator: (value) => ['businessObject', 'serviceModule'].includes(value)
    },
    annotationConfig: {
      type: Object,
      default: null
    },
    layoutEngine: {
      type: String,
      default: 'dagre'
    },
    layoutType: {
      type: String,
      default: 'default'
    },
    preserveModelOrder: {
      type: Boolean,
      default: false
    },
    layoutContainers: {
      type: Array,
      default: null
    },
    layoutPositions: {
      type: Array,
      default: () => []
    },
    zoneRowCount: {
      type: Number,
      default: 3
    },
    layoutControlConfig: {
      type: Object,
      default: null
    },
    hideLinkLabelTails: {
      type: Boolean,
      default: false
    }
  },
  emits: ['layout-change'],
  setup(props, { emit }) {
    const { initializeMermaid } = useMermaidConfig()
    const interaction = useInteraction()
    const svgStyle = useSvgStyle()
    const tooltip = useTooltip()
    const colors = useMermaidColors()
    const dataMap = useMermaidDataMap()
    const annotation = useAnnotation()
    const annotationOverlay = useAnnotationOverlay()
    const svgProcessor = useSvgProcessor({ interaction })
    const configStore = useDiagramConfigStore()

    function applyTitleMapToGroups(groups, titleMap) {
      if (!groups || !titleMap || Object.keys(titleMap).length === 0) {
        return
      }
      
      function processGroup(group) {
        const matchedTitle = titleMap[group.id] || titleMap[group.elementCode] || titleMap[group.title]
        if (matchedTitle) {
          group.title = matchedTitle
          group.fullTitle = matchedTitle
        }
        // 处理 containers
        if (group.containers && group.containers.length > 0) {
          group.containers.forEach(container => processGroup(container))
        }
        // 处理 children
        if (group.children && group.children.length > 0) {
          group.children.forEach(child => processGroup(child))
        }
      }
      
      groups.forEach(group => processGroup(group))
    }

    const mermaidContainer = ref(null)
    const mermaidContainerEl = ref(null)  // 关键修复 v10：真 .mermaid-container 元素 ref（之前 mermaidContainer 绑在 .mermaid-content 上）
    const mermaidWrapper = ref(null)
    const draggableArea = ref(null)
    const isMaximized = ref(false)
    let isRendering = false  // 防止无限循环
    let lastRenderData = null  // 上次渲染的数据，用于检测变化

    const effectiveLayoutControlConfig = computed(() => {
      const baseConfig = props.layoutControlConfig || props.diagramData?.layoutControlConfig || null
      if (!baseConfig) {
        return null
      }
      
      const mergedConfig = JSON.parse(JSON.stringify(baseConfig))
      applyTitleMapToGroups(mergedConfig.groups, props.diagramData?.groupControlTitleMap || {})
      
      return mergedConfig
    })

    const shouldHideTails = computed(() => {
      return props.layoutEngine === 'elk' || props.diagramData?.hideLinkLabelTails === true
    })

    let nodeColorMappings = []
    let linkColorMappings = []
    let lastColorGroupBy = 'domain'
    let lastCustomColors = null
    let isFirstRender = true

    /**
     * 关键修复 v5：全屏切换后必须重新计算画布布局
     * 否则 .mermaid-wrapper / .draggable-area 的 inline style 仍是切换前基于 600px
     * 容器算的尺寸，mermaid-container 100vw×100vh 之后 draggle 仍占旧尺寸，
     * 视口下方/右侧是 mermaid-container 的白色背景，视觉上"挡住图表"
     */
    const relayoutAfterSizeChange = () => {
      // 双层 nextTick + requestAnimationFrame 兜底：
      //   1) nextTick: 等待 Vue 更新 DOM（maximized class 切换）
      //   2) requestAnimationFrame: 等待浏览器应用 CSS（mermaid-container 尺寸变化）
      //   3) setTimeout 0: 再次兜底，处理某些浏览器下一帧才完成 layout 的情况
      requestAnimationFrame(() => {
        if (!mermaidContainer.value) return
        const w = mermaidContainer.value.offsetWidth
        const h = mermaidContainer.value.offsetHeight
        if (w === 0 || h === 0) {
          // 尺寸还没准备好，下一帧再试
          requestAnimationFrame(() => relayoutAfterSizeChange())
          return
        }
        svgProcessor.setupCanvasLayout(mermaidWrapper, mermaidContainer, draggableArea)
        interaction.autoFitDiagram()
      })
    }

    const toggleMaximize = () => {
      // 关键修复 v11：进入时强制 console.log，确认函数被调用
      // 关键修复 v10：用 mermaidContainerEl（真 .mermaid-container 元素）调 requestFullscreen
      console.log('[toggleMaximize] called | fullscreenElement:', document.fullscreenElement, '| mermaidContainerEl.value:', !!mermaidContainerEl.value)

      if (document.fullscreenElement) {
        // 当前是浏览器真全屏，退出
        document.exitFullscreen().then(() => {
          console.log('[toggleMaximize] exitFullscreen ok')
        }).catch((err) => {
          console.error('[toggleMaximize] exitFullscreen failed:', err?.name, err?.message, err)
          isMaximized.value = !isMaximized.value
        })
      } else if (mermaidContainerEl.value) {
        // 当前非全屏，尝试进入浏览器真全屏
        const p = mermaidContainerEl.value.requestFullscreen()
        if (p && typeof p.then === 'function') {
          p.then(() => {
            console.log('[toggleMaximize] requestFullscreen ok')
          }).catch((err) => {
            console.error('[toggleMaximize] requestFullscreen failed:', err?.name, err?.message, err)
            // 关键修复 v11：失败时兜底切 CSS class（v8 行为）
            isMaximized.value = !isMaximized.value
          })
        } else {
          // requestFullscreen 同步返回 undefined（旧浏览器或某些环境）
          console.warn('[toggleMaximize] requestFullscreen returned no promise, fallback to CSS class')
          isMaximized.value = !isMaximized.value
        }
      } else {
        // mermaidContainerEl.value 为 null，template ref 没绑上，兜底切 CSS class
        console.warn('[toggleMaximize] mermaidContainerEl.value is null, fallback to CSS class')
        isMaximized.value = !isMaximized.value
      }
    }

    // 监听浏览器全屏变化（v9：Fullscreen API 接管，v10：用 mermaidContainerEl）
    // fullscreenchange 事件在浏览器全屏状态改变时触发，时机可靠
    const handleFullscreenChange = () => {
      const isFullscreen = !!document.fullscreenElement
      isMaximized.value = isFullscreen
      // 关键修复 v21：fullscreen element 在 browser top layer，永远盖住 body 子元素
      // tooltip 元素默认在 document.body 内，全屏时会被 fullscreen element 遮挡
      // 解决：进入全屏时把 tooltip 移入 mermaidContainerEl（成为 fullscreen element 子元素，
      // 一起在 top layer 内），退出全屏时移回 body
      const tooltip = document.getElementById('mermaid-tooltip')
      if (tooltip) {
        if (isFullscreen && mermaidContainerEl.value && tooltip.parentElement !== mermaidContainerEl.value) {
          mermaidContainerEl.value.appendChild(tooltip)
        } else if (!isFullscreen && document.body && tooltip.parentElement !== document.body) {
          document.body.appendChild(tooltip)
        }
      }
      // setTimeout(50) 给 Vue 一点时间完成 DOM 更新（isMaximized 切换 → CSS 应用）
      setTimeout(() => {
        if (mermaidContainerEl.value) {
          svgProcessor.setupCanvasLayout(mermaidWrapper, mermaidContainerEl, draggableArea)
          interaction.autoFitDiagram()
        }
      }, 50)
    }

    // 生成Mermaid图表代码并保存关系说明信�?
    let relationDescriptions = []

    const serviceModuleSyntax = useServiceModuleSyntax()
    const businessObjectSyntax = useBusinessObjectSyntax()

    // 根据生成的内容类型，返回相应的Mermaid代码生成函数
    const generateMermaidCode = (data, layoutEngine, layoutType, positions = [], zoneRowCount = 3, preserveModelOrder = false, layoutControlConfig = null) => {
      relationDescriptions = []
      nodeColorMappings = []
      linkColorMappings = []

      try {
        if (data && data.containers) {
          const result = serviceModuleSyntax.generateMermaidCode(data, relationDescriptions, layoutEngine, layoutType, positions, zoneRowCount, preserveModelOrder, layoutControlConfig)
          if (typeof result === 'object' && result !== null) {
            nodeColorMappings = result.nodeColorMappings || []
            return result.code || result.mermaidCode || ''
          }
          return result
        } else {
          const result = businessObjectSyntax.generateMermaidCode(data, relationDescriptions, layoutEngine, layoutType, layoutControlConfig)
          if (typeof result === 'object' && result !== null) {
            nodeColorMappings = result.nodeColorMappings || []
            linkColorMappings = result.linkColorMappings || []
            return result.mermaidCode || ''
          }
          return result
        }
      } catch (e) {
        console.error('[generateMermaidCode] error:', e)
        return 'graph TD\n  A[Error]'
      }
    }

    // 渲染Mermaid图表
    const renderMermaid = async () => {
      // 防止无限循环
      if (isRendering) {
        return
      }
      isRendering = true
      
      if (mermaidContainer.value && props.diagramData) {
        try {
          // 暂时禁用 UnifiedRenderer，因为它缺少样式、tooltip、交互等功能
          // UnifiedRenderer 的 disabled 提升功能已经通过 GroupModel.getFlattenedGroups 修复
          if (props.diagramData._unifiedMermaidCode && false) {
            initializeMermaid(props.diagramType, props.diagramData, props.layoutEngine, props.layoutType, props.preserveModelOrder, effectiveLayoutControlConfig.value, configStore.mermaidMaxTextSize)
            mermaidContainer.value.innerHTML = `<pre class="mermaid">${props.diagramData._unifiedMermaidCode}</pre>`
          } else {
            let effectiveLayoutEngine = props.layoutEngine
            const positions = props.layoutPositions || []
            const zoneRowCount = props.zoneRowCount || 3

            if (props.layoutEngine === 'elk') {
              const elkLoaded = await loadElkLayouts(true)
              if (!elkLoaded) {
                effectiveLayoutEngine = 'dagre'
              } else {
                initializeMermaid(props.diagramType, props.diagramData, 'elk', props.layoutType, props.preserveModelOrder, effectiveLayoutControlConfig.value, configStore.mermaidMaxTextSize)
                try {
                  const mermaidCode = generateMermaidCode(props.diagramData, 'elk', props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
                  mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
                } catch (e) {
                  console.error('[MermaidComponent] ELK Error generating mermaid code, falling back to dagre:', e)
                  effectiveLayoutEngine = 'dagre'
                }
              }
            }

            if (!effectiveLayoutEngine || effectiveLayoutEngine !== 'elk') {
              initializeMermaid(props.diagramType, props.diagramData, effectiveLayoutEngine || 'dagre', props.layoutType, props.preserveModelOrder, effectiveLayoutControlConfig.value, configStore.mermaidMaxTextSize)
              try {
                const mermaidCode = generateMermaidCode(props.diagramData, effectiveLayoutEngine || 'dagre', props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
                mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
              } catch (e) {
                console.error('[MermaidComponent] Error generating mermaid code:', e)
              }
            }
          }
        } catch (err) {
          console.error('[MermaidComponent] renderMermaid error:', err)
          isRendering = false
        }

      nextTick(() => {
          const preEl = mermaidContainer.value?.querySelector('pre.mermaid')
          mermaid.run()
            .then(() => {
              const preElAfter = mermaidContainer.value?.querySelector('pre.mermaid')
              const svgElAfter = mermaidContainer.value?.querySelector('svg')
              if (svgElAfter) {
                svgProcessor.processSvg(svgElAfter, props, relationDescriptions, mermaidContainer, nodeColorMappings)

                // 设置交互功能
                // 关键修复 v10：传 mermaidContainerEl（真 .mermaid-container）作为 wheel/mousedown 事件目标
                // 之前传 mermaidWrapper，全屏模式下 mermaidWrapper 仍受父级 CSS 限制，事件触不到或无效
                // 关键修复 v15：第 3 个参数必须传 mermaidContainer（.mermaid-content），
                // 之前误传 draggableArea，导致 updateTransform 把 transform 设到 draggle 上而不是 content 上
                // （v10 改 addZoomAndPan 签名时漏改调用方）
                interaction.addZoomAndPan(mermaidContainerEl, mermaidWrapper, mermaidContainer)

                // 设置画布布局
                svgProcessor.setupCanvasLayout(mermaidWrapper, mermaidContainer, draggableArea)

                // 只在首次渲染时自动适应，后续更新保持当前缩放状态
                if (isFirstRender) {
                  setTimeout(() => {
                    interaction.autoFitDiagram()
                  }, 100)
                  isFirstRender = false
                }

                lastColorGroupBy = props.diagramData?.colorGroupBy || 'domain'
                
                // 渲染完成，重置渲染状态
                isRendering = false

                // 额外使用CSS样式注入，解决优先级样式问题
                const styleId = 'mermaid-italic-style'
                let styleEl = document.getElementById(styleId)
                if (!styleEl) {
                  styleEl = document.createElement('style')
                  styleEl.id = styleId
                  document.head.appendChild(styleEl)
                }

                const cssRules = `
                    /* 使用 CSS 变量设置文字颜色 */
                    .mermaid-content.businessObject .node text,
                    .mermaid-content.businessObject .node tspan,
                    .mermaid-content.businessObject .nodeLabel {
                      fill: var(--node-text-color, #333333) !important;
                      color: var(--node-text-color, #333333) !important;
                    }
                    .mermaid-content.businessObject .cluster text,
                    .mermaid-content.businessObject .subgraph text,
                    .mermaid-content.businessObject .cluster-label,
                    .mermaid-content.businessObject .subgraph-label {
                      fill: var(--cluster-text-color, #333333) !important;
                      color: var(--cluster-text-color, #333333) !important;
                    }
                    /* 业务对象 - edgeLabel 透明背景 */
                    .mermaid-content.businessObject .edgeLabel rect.background {
                      fill: transparent !important;
                      fill-opacity: 0 !important;
                    }
                    /* 注意：这些规则不适用�?.edge-label-clean，因为它有自己的背景规则 */
                    .mermaid-content.businessObject .edgeLabel:not(.edge-label-clean) .label {
                      background: transparent !important;
                      background-color: transparent !important;
                    }
                    .mermaid-content.businessObject .edgeLabel:not(.edge-label-clean) {
                      background: transparent !important;
                      background-color: transparent !important;
                    }
                    .mermaid-content.businessObject .edgeLabel:not(.edge-label-clean) foreignObject {
                      background: transparent !important;
                      background-color: transparent !important;
                    }
                    .mermaid-content.businessObject .edgeLabel:not(.edge-label-clean) foreignObject > div {
                      background: transparent !important;
                      background-color: transparent !important;
                    }
                    /* 隐藏 edgeLabel 内的装饰�?path 元素 */
                    .mermaid-content.businessObject .edgeLabel path,
                    .mermaid-content.businessObject .edgeLabelBkg path,
                    .mermaid-content.businessObject g.edgeLabel path,
                    .mermaid-content.businessObject .labelBkg path,
                    .mermaid-content.businessObject g.labelBkg path,
                    .mermaid-content.businessObject span.edgeLabel svg path,
                    .mermaid-content.businessObject span.edgeLabel path,
                    .mermaid-content.businessObject .edgeLabel svg,
                    .mermaid-content.businessObject span.edgeLabel svg {
                      fill: transparent !important;
                      stroke: transparent !important;
                      display: none !important;
                      visibility: hidden !important;
                      opacity: 0 !important;
                    }
                    /* 只让 labelBkg 有背景颜�?*/
                    .mermaid-content.businessObject .labelBkg {
                      background: #ffffff !important;
                      background-color: #ffffff !important;
                      display: inline-block !important;
                      line-height: 1.2 !important;
                      padding: 2px 6px !important;
                    }
                    .mermaid-content.businessObject .labelBkg * {
                      background: #ffffff !important;
                      background-color: #ffffff !important;
                    }
                    .mermaid-content.businessObject .labelBkg p {
                      margin: 0 !important;
                      padding: 0 !important;
                    }

                    /* ELK 布局 - 隐藏所有 edgeLabel 的拖尾线背景 */
                    .mermaid-container .edgeLabel rect,
                    .mermaid-container g.edgeLabel rect,
                    .mermaid-container .edge-label rect,
                    .mermaid-content .edgeLabel rect,
                    .mermaid-content g.edgeLabel rect,
                    .mermaid-content .edge-label rect,
                    svg .edgeLabel rect,
                    svg g.edgeLabel rect,
                    [data-bg-rect="true"] {
                      display: none !important;
                      visibility: hidden !important;
                      opacity: 0 !important;
                      width: 0 !important;
                      height: 0 !important;
                      overflow: hidden !important;
                    }
                    .mermaid-container .edgeLabel polygon,
                    .mermaid-container g.edgeLabel polygon,
                    .mermaid-content .edgeLabel polygon,
                    .mermaid-content g.edgeLabel polygon,
                    svg .edgeLabel polygon,
                    svg g.edgeLabel polygon {
                      display: none !important;
                      visibility: hidden !important;
                    }
                    .mermaid-container .edgeLabel path,
                    .mermaid-container g.edgeLabel path,
                    .mermaid-content .edgeLabel path,
                    .mermaid-content g.edgeLabel path,
                    svg .edgeLabel path,
                    svg g.edgeLabel path {
                      display: none !important;
                      visibility: hidden !important;
                    }
                    /* 强制隐藏所有 edgeLabel 内的 rect */
                    * .edgeLabel rect {
                      display: none !important;
                    }

                    /* 容器标签斜体 - 强制容器标题文字为斜体(包含tspan) */
                    .mermaid-content.businessObject .subgraph text,
                    .mermaid-content.businessObject .subgraph-label text,
                    .mermaid-content.businessObject .subgraph .label text,
                    .mermaid-content.serviceModule .cluster text,
                    .mermaid-content.serviceModule .cluster-label text,
                    .mermaid-content.serviceModule .cluster .label text,
                    .mermaid-content.serviceModule .subgraph text,
                    .mermaid-content.serviceModule .subgraph-label text,
                    .mermaid-content.serviceModule .subgraph .label text,
                    .mermaid-content.businessObject .subgraph tspan,
                    .mermaid-content.businessObject .subgraph-label tspan,
                    .mermaid-content.businessObject .subgraph .label tspan,
                    .mermaid-content.serviceModule .cluster tspan,
                    .mermaid-content.serviceModule .cluster-label tspan,
                    .mermaid-content.serviceModule .cluster .label tspan,
                    .mermaid-content.serviceModule .subgraph tspan,
                    .mermaid-content.serviceModule .subgraph-label tspan,
                    .mermaid-content.serviceModule .subgraph .label tspan {
                      font-style: italic !important;
                      font-size: 24px !important;
                    }

                    /* 容器 foreignObject 内部文字大小 */
                    .mermaid-content.businessObject .subgraph-label foreignObject p,
                    .mermaid-content.businessObject .subgraph-label foreignObject span,
                    .mermaid-content.businessObject .subgraph-label foreignObject div,
                    .mermaid-content.businessObject .cluster-label foreignObject p,
                    .mermaid-content.businessObject .cluster-label foreignObject span,
                    .mermaid-content.businessObject .cluster-label foreignObject div,
                    .mermaid-content.serviceModule .cluster foreignObject p,
                    .mermaid-content.serviceModule .cluster foreignObject span,
                    .mermaid-content.serviceModule .cluster foreignObject div,
                    .mermaid-content.serviceModule .cluster-label foreignObject p,
                    .mermaid-content.serviceModule .cluster-label foreignObject span,
                    .mermaid-content.serviceModule .cluster-label foreignObject div,
                    .mermaid-content.serviceModule .subgraph foreignObject p,
                    .mermaid-content.serviceModule .subgraph foreignObject span,
                    .mermaid-content.serviceModule .subgraph foreignObject div,
                    .mermaid-content.serviceModule .subgraph-label foreignObject p,
                    .mermaid-content.serviceModule .subgraph-label foreignObject span,
                    .mermaid-content.serviceModule .subgraph-label foreignObject div {
                      font-size: 24px !important;
                      font-weight: bold !important;
                      font-style: italic !important;
                    }

                    /* 容器 foreignObject 内部 p 元素斜体居中 */
                    .mermaid-content.businessObject .subgraph foreignObject p,
                    .mermaid-content.serviceModule .cluster foreignObject p,
                    .mermaid-content.serviceModule .subgraph foreignObject p {
                      font-style: italic !important;
                      font-size: 24px !important;
                      text-align: center !important;
                      margin: 0 !important;
                      padding: 0 !important;
                    }

                    /* 确保连线标签不倾斜 */
                    .mermaid-content.businessObject .edgeLabel text,
                    .mermaid-content.businessObject .edge-label text,
                    .mermaid-content.businessObject .edgeLabel tspan,
                    .mermaid-content.businessObject .edge-label tspan,
                    .mermaid-content.serviceModule .edgeLabel text,
                    .mermaid-content.serviceModule .edge-label text,
                    .mermaid-content.serviceModule .edgeLabel tspan,
                    .mermaid-content.serviceModule .edge-label tspan {
                      font-style: normal !important;
                    }
                  `
                  styleEl.textContent = cssRules

                  const shouldHideTails = props.layoutEngine === 'elk' ||
                    props.diagramData?.hideLinkLabelTails === true

                  if (shouldHideTails) {
                    setTimeout(() => hideLinkLabelTails(), 2000)
                  }

                  setTimeout(() => {
                    const svgAgain = mermaidContainer.value.querySelector('svg')
                    if (svgAgain) {
                      svgStyle.applyContainerTitleItalic(svgAgain)
                    }
                  }, 800)
                }
            }).catch((err) => {
              console.error('[MermaidComponent] mermaid.run() rejected:', err)
              isRendering = false
            })
        })
      } else {
        isRendering = false
      }
    }

    const hideLinkLabelTails = () => {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) {
        return
      }

      // 隐藏所有 data-bg-rect
      const bgRects = svg.querySelectorAll('[data-bg-rect="true"]')
      bgRects.forEach((rect, i) => {
        rect.setAttribute('style', 'display: none !important; visibility: hidden !important;')
      })

      // 隐藏 edgeLabel 内的 rect, polygon, path
      const edgeLabelRects = svg.querySelectorAll('.edgeLabel rect, g.edgeLabel rect')
      edgeLabelRects.forEach(rect => {
        rect.setAttribute('style', 'display: none !important; visibility: hidden !important;')
      })

      const edgeLabelPolygons = svg.querySelectorAll('.edgeLabel polygon, g.edgeLabel polygon')
      edgeLabelPolygons.forEach(poly => {
        poly.setAttribute('style', 'display: none !important; visibility: hidden !important;')
      })

      const edgeLabelPaths = svg.querySelectorAll('.edgeLabel path, g.edgeLabel path')
      edgeLabelPaths.forEach(path => {
        path.setAttribute('style', 'display: none !important; visibility: hidden !important;')
      })

      // 隐藏拖尾线 - line 和 circle 元素（虚线和末端圆点）
      const lines = svg.querySelectorAll('line')
      lines.forEach((line, i) => {
        const strokeDasharray = line.getAttribute('stroke-dasharray')
        if (strokeDasharray) {
          line.setAttribute('style', 'display: none !important; visibility: hidden !important;')
        }
      })

      const circles = svg.querySelectorAll('circle')
      circles.forEach((circle, i) => {
        const r = circle.getAttribute('r')
        const fill = circle.getAttribute('fill')
        if (r && parseFloat(r) <= 5) {
          circle.setAttribute('style', 'display: none !important; visibility: hidden !important;')
        }
      })

      // 5秒后再执行一次
      setTimeout(() => {
        const remainingLines = svg.querySelectorAll('line[stroke-dasharray]')
        remainingLines.forEach(line => {
          line.setAttribute('style', 'display: none !important; visibility: hidden !important;')
        })
        const remainingCircles = svg.querySelectorAll('circle')
        remainingCircles.forEach(circle => {
          const r = circle.getAttribute('r')
          if (r && parseFloat(r) <= 5) {
            circle.setAttribute('style', 'display: none !important; visibility: hidden !important;')
          }
        })
      }, 5000)

    }
    
    // 只在新增节点或连线时才重新渲染颜色，否则只更新图�?
    const updateColorsOnly = (newColorGroupBy, customColorsChanged) => {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) {
        return false
      }

      if (nodeColorMappings.length === 0 || linkColorMappings.length === 0) {
        return false
      }

      const currentColorGroupBy = props.diagramData?.colorGroupBy || 'domain'
      const currentCustomColors = props.diagramData?.customColors || {}

      if (currentColorGroupBy === lastColorGroupBy && !customColorsChanged) {
        return true
      }

      const data = props.diagramData
      const colorGroupBy = currentColorGroupBy

      const moduleGroups = new Map()
      const objectToModuleMap = dataMap.buildObjectToModuleMap(data)

      const colorMap = colors.buildColorMap(
        nodeColorMappings,
        objectToModuleMap,
        colorGroupBy,
        colors.getColorScheme(data.colorScheme),
        data.customColors || {}
      )

      colors.updateNodeColors(svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap)
      colors.updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap)

      // 更新文字颜色
      const textColorSetting = props.diagramData?.textColor || 'black'
      svgStyle.updateNodeStyles(svg, textColorSetting)
      svgStyle.updateClusterStyles(svg, textColorSetting)

      lastColorGroupBy = currentColorGroupBy
      lastCustomColors = { ...currentCustomColors }

      return true
    }

    // 监听数据变化 - 合并了原来的 diagramData watcher（行 596-613）和 layoutType/layoutEngine watcher
    watch(
      () => props.diagramData,
      (newVal, oldVal) => {
        if (!newVal) return
        
        // 防止无限循环：如果正在渲染中，跳过
        if (isRendering) {
          return
        }

        // 判断是否只需要更新颜色
        if (oldVal) {
          const newColorGroupBy = newVal?.colorGroupBy
          const oldColorGroupBy = oldVal?.colorGroupBy
          const newCustomColors = newVal?.customColors || {}
          const oldCustomColors = oldVal?.customColors || {}
          const customColorsChanged = JSON.stringify(newCustomColors) !== JSON.stringify(oldCustomColors)
          const nodesChanged = JSON.stringify(newVal.nodes) !== JSON.stringify(oldVal.nodes)
          const linksChanged = JSON.stringify(newVal.links) !== JSON.stringify(oldVal.links)
          const textColorChanged = newVal?.textColor !== oldVal?.textColor

          // 如果节点和连线没变，只是颜色分组变化、自定义颜色变化或文字颜色变化，则只更新颜色
          if (!nodesChanged && !linksChanged && (newColorGroupBy !== oldColorGroupBy || customColorsChanged || textColorChanged)) {
            // 如果只是文字颜色变化，不需要重新生成颜色映射
            if (textColorChanged && !customColorsChanged) {
              const svg = mermaidContainer.value?.querySelector('svg')
              if (svg) {
                svgStyle.updateNodeStyles(svg, newVal?.textColor || 'black')
                svgStyle.updateClusterStyles(svg, newVal?.textColor || 'black')
              }
              return
            }
            const updated = updateColorsOnly(newColorGroupBy, customColorsChanged)
            if (!updated) {
              renderMermaid()
            }
            return
          }
        }

        renderMermaid()
      },
      { deep: true }
    )

    // 监听 layoutType 变化
    watch(
      () => props.layoutType,
      (newVal, oldVal) => {
        if (newVal !== oldVal && props.diagramData && mermaidContainer.value) {
          renderMermaid()
        }
      }
    )

    // 监听 layoutEngine 变化
    watch(
      () => props.layoutEngine,
      (newVal, oldVal) => {
        if (newVal !== oldVal && props.diagramData && mermaidContainer.value) {
          renderMermaid()
        }
      }
    )

    // 监听 zoneRowCount 变化
    watch(
      () => props.zoneRowCount,
      (newVal, oldVal) => {
        if (newVal !== oldVal && props.diagramData && mermaidContainer.value) {
          renderMermaid()
        }
      }
    )

    // 关键修复 v14：用 debounced window resize 替代 ResizeObserver
    // ResizeObserver 监听 mermaid-container 会触发 setupCanvasLayout 死循环
    // （mermaid 渲染过程中 container 尺寸会被 SVG 推大，触发 observer 重算，再推大...）
    // 改为监听 window resize（debounced）+ fullscreenchange 事件，架构上消除循环
    let resizeDebounceTimer = null

    const handleWindowResize = () => {
      clearTimeout(resizeDebounceTimer)
      resizeDebounceTimer = setTimeout(() => {
        if (mermaidContainer.value) {
          // 关键修复 v14：尺寸安全检查，防止异常尺寸触发死循环
          const w = mermaidContainer.value.offsetWidth
          const h = mermaidContainer.value.offsetHeight
          // 正常浏览器视口不可能超过 10000px，超过说明状态异常，跳过
          if (w > 0 && w < 10000 && h > 0 && h < 10000) {
            svgProcessor.setupCanvasLayout(mermaidWrapper, mermaidContainer, draggableArea)
          } else {
            console.warn('[handleWindowResize] abnormal size, skip:', w, 'x', h)
          }
        }
      }, 150)
    }

    // 组件挂载后初始化
    onMounted(() => {
      if (props.diagramData) {
        renderMermaid()
      }

      // 关键修复 v14：监听 window resize（debounced 150ms）
      // 覆盖：浏览器窗口 resize、dev tools 开合、tab 切换等场景
      // 不监听 mermaid-container 自身（避免 v8 ResizeObserver 死循环）
      window.addEventListener('resize', handleWindowResize)

      // 关键修复 v9：监听浏览器 fullscreenchange 事件
      document.addEventListener('fullscreenchange', handleFullscreenChange)
    })

    onBeforeUnmount(() => {
      clearTimeout(resizeDebounceTimer)
      window.removeEventListener('resize', handleWindowResize)
      // 关键修复 v9：清理 fullscreenchange 监听
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
    })

    // 导出为图片
    const exportAsImage = () => {
      if (mermaidContainer.value) {
      }
    }

    // 导出为原生格�?
    const exportAsNative = () => {
      if (props.diagramData) {
        const positions = props.layoutPositions || []
        const zoneRowCount = props.zoneRowCount || 3
        const mermaidCode = generateMermaidCode(props.diagramData, props.layoutEngine, props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
        const blob = new Blob([mermaidCode], { type: 'text/plain' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `diagram-${Date.now()}.mmd`
        link.click()
      }
    }

    // 导出为 HTML 文件（简洁版 - 内嵌库，离线可用）
    const exportAsHtmlSimple = async () => {
      if (props.diagramData) {
        const positions = props.layoutPositions || []
        const zoneRowCount = props.zoneRowCount || 3
        const mermaidCode = generateMermaidCode(props.diagramData, props.layoutEngine, props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
        const chartTypeLabel = props.diagramType === 'serviceModule' ? '服务模块图' : '业务对象图'
        
        const isServiceModule = props.diagramType === 'serviceModule'
        const overallDirection = effectiveLayoutControlConfig.value?.overallDirection || 'LR'
        const isElk = props.layoutEngine === 'elk'
        
        // 简版不使用ELK（ESM版本有chunk依赖问题，在file://协议下无法加载）
        const useElk = false
        
        let mermaidScript = ''
        try {
          // eslint-disable-next-line no-restricted-globals -- CDN 外部资源，不走 httpClient
          const mermaidResponse = await fetch('https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js')
          mermaidScript = await mermaidResponse.text()
        } catch (e) {
          console.error('获取库失败:', e)
          showToast('获取库失败，请检查网络')
          return
        }
        
        const config = {
          startOnLoad: true,
          securityLevel: 'loose',
          maxTextSize: configStore.mermaidMaxTextSize,
          theme: 'base',
          themeVariables: {
            edgeLabelBackground: '#ffffff',
            edgeLabelColor: '#000000',
            primaryColor: '#ffffff',
            primaryTextColor: '#000000',
            primaryBorderColor: '#333333',
            lineColor: '#333333',
            secondaryColor: '#f0f0f0',
            tertiaryColor: '#ffffff'
          },
          flowchart: {
            curve: 'basis',
            padding: isServiceModule ? 25 : 20,
            nodeSpacing: isServiceModule ? 120 : 80,
            rankSpacing: isServiceModule ? 150 : 100,
            arrowMarkerAbsolute: true,
            useMaxWidth: false,
            htmlLabels: true,
            diagramPadding: isServiceModule ? 40 : 20,
            wrappingWidth: isServiceModule ? 400 : 200,
            labelPosition: 'c',
            defaultLinkLength: isServiceModule ? 60 : 50,
            arrowHeadWidth: isServiceModule ? 8 : 6,
            arrowHeadHeight: 6,
            rankdir: overallDirection,
            subGraphTitleMargin: { top: 15, bottom: 15 }
          }
        }
        
        // 简版强制使用dagre布局（ELK的ESM版本有chunk依赖问题）
        if (useElk) {
          config.layout = 'elk'
          config.elk = {
            'elk.direction': overallDirection === 'TB' ? 'DOWN' : 'RIGHT',
            'elk.spacing.nodeNode': 100,
            'elk.layered.spacing.nodeNodeBetweenLayers': 150,
            'elk.padding': '[top=40,left=80,right=80,bottom=40]',
            'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
            'elk.algorithm': 'layered',
            'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
            'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
            'elk.layered.spacing.edgeNodeBetweenLayers': 60,
            'elk.layered.componentsSpacing': 200,
            'elk.layered.spacing.baseValue': 50,
            'elk.contentAlignment': 'CENTER',
            'elk.alignment': 'CENTER',
            'elk.spacing.componentComponent': 250,
            'elk.layered.spacing.componentComponent': 250,
            'elk.spacing.parentParent': 50,
            'elk.padding.nodes': '[top=30,left=50,right=50,bottom=30]',
            'elk.layered.cycleBreaking.strategy': 'GREEDY_MODEL_ORDER',
            'elk.layered.layering.strategy': 'NETWORK_SIMPLEX'
          }
        }
        
        const mermaidBase64 = btoa(unescape(encodeURIComponent(mermaidScript)))
        
        const htmlContent = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${chartTypeLabel} - ${new Date().toLocaleDateString()}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      background: #ffffff;
      height: auto;
      min-height: 100vh;
    }
    body {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      padding: 10px;
    }
    pre.mermaid { 
      display: block;
      background: white; 
      width: 100%;
      margin: 0;
      padding: 0;
      border: none;
      overflow: visible;
      line-height: 0;
    }
    pre.mermaid svg {
      display: block;
      cursor: grab;
      transform-origin: top left;
      transition: transform 0.1s ease-out;
      max-width: none;
    }
    pre.mermaid svg:active {
      cursor: grabbing;
    }
  <\/style>
<\/head>
<body>
  <pre class="mermaid">
${mermaidCode}
  <\/pre>
  <script>
    const mermaidBase64 = "${mermaidBase64}";
    const mermaidCode = decodeURIComponent(escape(atob(mermaidBase64)));
    const mermaidBlob = new Blob([mermaidCode], { type: 'text/javascript' });
    const mermaidUrl = URL.createObjectURL(mermaidBlob);
    const script = document.createElement('script');
    script.src = mermaidUrl;
    script.onload = () => {
      mermaid.initialize(${JSON.stringify(config)});
      // 手动触发渲染
      mermaid.run({
        querySelector: '.mermaid'
      }).then(() => {
        // 渲染完成后修改容器颜色，增加嵌套容器区分度
        setTimeout(() => {
          const svg = document.querySelector('.mermaid svg');
          const mermaidDiv = document.querySelector('.mermaid');
          // 滚动到SVG位置
          if (svg) {
            svg.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
          
          // 修复SVG顶部空白：调整viewBox
          {
            const viewBox = svg.getAttribute('viewBox');
            if (viewBox) {
              const parts = viewBox.split(' ');
              if (parts.length === 4) {
                parts[0] = '0';
                parts[1] = '0';
                svg.setAttribute('viewBox', parts.join(' '));
              }
            }
          }
          
          // 添加滚轮缩放功能
          if (svg && mermaidDiv) {
            let scale = 1;
            const minScale = 0.1;
            const maxScale = 3;
            
            mermaidDiv.addEventListener('wheel', (e) => {
              e.preventDefault();
              e.stopPropagation();
              
              const rect = svg.getBoundingClientRect();
              const mouseX = e.clientX - rect.left;
              const mouseY = e.clientY - rect.top;
              
              const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
              const newScale = Math.max(minScale, Math.min(maxScale, scale * zoomFactor));
              
              // 以鼠标位置为中心缩放
              const offsetX = mouseX - rect.width / 2;
              const offsetY = mouseY - rect.height / 2;
              const scaleDiff = newScale - scale;
              
              svg.style.transform = 'scale(' + newScale + ')';
              scale = newScale;
            }, { passive: false });
          }
          
          if (svg) {
            // 获取所有子图（容器）- 尝试多种选择器
            let subgraphs = Array.from(svg.querySelectorAll('.cluster'));
            // 如果找不到，尝试其他选择器
            if (subgraphs.length === 0) {
              // flowchart-elk 使用不同的class名
              subgraphs = Array.from(svg.querySelectorAll('g.cluster'));
            }
            
            if (subgraphs.length === 0) {
              // 尝试通过rect元素查找容器
              const allRects = svg.querySelectorAll('rect');
              // 收集所有rect及其尺寸信息
              const rectInfos = [];
              allRects.forEach(rect => {
                const width = parseFloat(rect.getAttribute('width')) || 0;
                const height = parseFloat(rect.getAttribute('height')) || 0;
                const area = width * height;
                const parent = rect.closest('g');
                rectInfos.push({ rect, width, height, area, parent });
              });
              
              // 按面积排序，找出大尺寸的容器
              rectInfos.sort((a, b) => b.area - a.area);
              
              // 计算面积分布，找出容器阈值
              const areas = rectInfos.map(r => r.area);
              const maxArea = Math.max(...areas);
              const minArea = Math.min(...areas);
              const avgArea = areas.reduce((a, b) => a + b, 0) / areas.length;
              
              // 容器通常是面积较大的元素（大于平均面积的2倍）
              const containerThreshold = avgArea * 2;
              const containerGroups = new Set();
              
              rectInfos.forEach(info => {
                if (info.area >= containerThreshold && info.parent) {
                  containerGroups.add(info.parent);
                }
              });
              
              subgraphs = Array.from(containerGroups);
            }
            
            // 计算每个容器的嵌套层级
            const getNestingLevel = (subgraph) => {
              let level = 0;
              let parent = subgraph.parentElement;
              while (parent) {
                if (parent.tagName === 'g' && subgraphs.includes(parent)) {
                  level++;
                }
                parent = parent.parentElement;
              }
              return level;
            };
            
            // 为每个容器计算层级
            const containerLevels = new Map();
            subgraphs.forEach(subgraph => {
              containerLevels.set(subgraph, getNestingLevel(subgraph));
            });
            
            // 按层级分组
            const levelGroups = new Map();
            subgraphs.forEach(subgraph => {
              const level = containerLevels.get(subgraph);
              if (!levelGroups.has(level)) {
                levelGroups.set(level, []);
              }
              levelGroups.get(level).push(subgraph);
            });
            
            // 按层级分配颜色（外层浅色，内层深色）
            const colors = ['#ffffff', '#e0e0e0', '#c0c0c0', '#a0a0a0'];
            const maxLevel = Math.max(...containerLevels.values());
            
            subgraphs.forEach((subgraph, index) => {
              const rect = subgraph.querySelector('rect');
              if (rect) {
                const level = containerLevels.get(subgraph);
                // 根据层级选择颜色（外层=0用白色，内层递增）
                const colorIndex = Math.min(level, colors.length - 1);
                const color = colors[colorIndex];
                rect.setAttribute('fill', color);
                rect.setAttribute('stroke', '#666666');
                rect.setAttribute('stroke-width', '2');
                rect.style.fill = color;
                rect.style.stroke = '#666666';
                rect.style.strokeWidth = '2px';
                rect.style.opacity = '1';
                rect.setAttribute('opacity', '1');
              }
            });
            
            // 修复容器标题斜体
            const clusterLabels = svg.querySelectorAll('.cluster-label, .label');
            clusterLabels.forEach(label => {
              const texts = label.querySelectorAll('text, tspan');
              texts.forEach(text => {
                text.style.fontStyle = 'italic';
                text.setAttribute('font-style', 'italic');
                // 使用skewX模拟斜体效果
                text.style.transform = 'skewX(-10deg)';
                text.style.transformOrigin = 'center';
              });
            });
          }
        }, 500);
      }).catch(err => {
        console.error('Mermaid渲染失败:', err);
      });
    };
    document.head.appendChild(script);
  <\/script>
<\/body>
<\/html>`
        const blob = new Blob([htmlContent], { type: 'text/html' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `diagram-simple-${Date.now()}.html`
        link.click()
      }
    }

    // 导出为 HTML 文件（彩色版 - 内嵌库，可直接双击打开）
    const exportAsHtmlFull = async () => {
      if (props.diagramData) {
        showToast('正在生成彩色版，请稍候...')

        const positions = props.layoutPositions || []
        const zoneRowCount = props.zoneRowCount || 3
        const mermaidCode = generateMermaidCode(props.diagramData, props.layoutEngine, props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
        const chartTypeLabel = props.diagramType === 'serviceModule' ? '服务模块图' : '业务对象图'

        // 关键修复 v26：根据当前 diagramData 计算 legend 数据（与 app 内一致）
        const annotationConfigFull = props.diagramData?.annotationConfig || {}
        const centerScopeHighlightFull = annotationConfigFull.centerScopeHighlight !== false
        const colorLegendDataFull = (props.diagramType === 'serviceModule' || props.diagramType === 'businessObject')
          ? svgProcessor.buildColorLegendData(props.diagramData, nodeColorMappings, centerScopeHighlightFull)
          : []
        const legendItemsHtmlFull = colorLegendDataFull.map((item, idx) => {
          const sep = (item.isCenter && idx < colorLegendDataFull.length - 1)
            ? '<div class="legend-sep"></div>'
            : ''
          return `<div class="legend-item" title="${item.name || ''}">
            <span class="legend-dot" style="background:${item.color || '#e0e0e0'}"></span>
            <span class="legend-name">${item.name || ''}</span>
          </div>${sep}`
        }).join('')
        const legendHtmlFull = colorLegendDataFull.length > 0
          ? `<div class="color-legend-panel" data-annotation-layer="legend">
              <div class="color-legend-title">图例</div>
              <div class="color-legend-list">${legendItemsHtmlFull}</div>
            </div>`
          : ''
        
        const isServiceModule = props.diagramType === 'serviceModule'
        const overallDirection = effectiveLayoutControlConfig.value?.overallDirection || 'LR'
        const isElk = props.layoutEngine === 'elk'
        
        const config = {
          startOnLoad: true,
          securityLevel: 'loose',
          maxTextSize: configStore.mermaidMaxTextSize,
          theme: 'base',
          themeVariables: {
            edgeLabelBackground: '#ffffff',
            edgeLabelColor: '#000000',
            primaryColor: '#ffffff',
            primaryTextColor: '#000000',
            primaryBorderColor: '#333333',
            lineColor: '#333333',
            secondaryColor: '#f0f0f0',
            tertiaryColor: '#ffffff'
          },
          flowchart: {
            curve: 'basis',
            padding: isServiceModule ? 25 : 20,
            nodeSpacing: isServiceModule ? 120 : 80,
            rankSpacing: isServiceModule ? 150 : 100,
            arrowMarkerAbsolute: true,
            useMaxWidth: false,
            htmlLabels: true,
            diagramPadding: isServiceModule ? 40 : 20,
            wrappingWidth: isServiceModule ? 400 : 200,
            labelPosition: 'c',
            defaultLinkLength: isServiceModule ? 60 : 50,
            arrowHeadWidth: isServiceModule ? 8 : 6,
            arrowHeadHeight: 6,
            rankdir: overallDirection,
            subGraphTitleMargin: { top: 15, bottom: 15 }
          }
        }
        
        if (isElk) {
          config.layout = 'elk'
          config.elk = {
            'elk.direction': overallDirection === 'TB' ? 'DOWN' : 'RIGHT',
            'elk.spacing.nodeNode': 100,
            'elk.layered.spacing.nodeNodeBetweenLayers': 150,
            'elk.padding': '[top=40,left=80,right=80,bottom=40]',
            'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
            'elk.algorithm': 'layered',
            'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
            'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
            'elk.layered.spacing.edgeNodeBetweenLayers': 60,
            'elk.layered.componentsSpacing': 200,
            'elk.layered.spacing.baseValue': 50,
            'elk.contentAlignment': 'CENTER',
            'elk.alignment': 'CENTER',
            'elk.spacing.componentComponent': 250,
            'elk.layered.spacing.componentComponent': 250,
            'elk.spacing.parentParent': 50,
            'elk.padding.nodes': '[top=30,left=50,right=50,bottom=30]',
            'elk.layered.cycleBreaking.strategy': 'GREEDY_MODEL_ORDER',
            'elk.layered.layering.strategy': 'NETWORK_SIMPLEX'
          }
        }
        
        const htmlContent = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${chartTypeLabel} - ${new Date().toLocaleDateString()}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      background: #ffffff;
      height: auto;
      min-height: 100vh;
    }
    body {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      padding: 10px;
    }
    .notice {
      background: #fff3cd;
      border: 1px solid #ffc107;
      color: #856404;
      padding: 12px 20px;
      border-radius: 8px;
      margin-bottom: 10px;
      font-size: 13px;
      text-align: center;
      width: 100%;
      box-sizing: border-box;
    }
    pre.mermaid { 
      display: block;
      background: white; 
      width: 100%;
      margin: 0;
      padding: 0;
      border: none;
      overflow: visible;
      line-height: 0;
    }
    pre.mermaid svg {
      display: block;
      background: white;
      cursor: grab;
      transform-origin: top left;
      transition: transform 0.1s ease-out;
      max-width: none;
    }
    pre.mermaid svg:active {
      cursor: grabbing;
    }
    /* 关键修复 v26：导出 HTML 内嵌的 legend 样式（与 app 内一致） */
    .color-legend-panel {
      position: fixed;
      top: 60px;
      left: 20px;
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid #ddd;
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 12px;
      font-family: Arial, sans-serif;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      max-width: 200px;
      z-index: 100;
    }
    .color-legend-title {
      font-weight: bold;
      margin-bottom: 6px;
      border-bottom: 1px solid #eee;
      padding-bottom: 4px;
    }
    .color-legend-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .legend-dot {
      display: inline-block;
      width: 12px;
      height: 12px;
      border-radius: 2px;
      flex-shrink: 0;
      border: 1px solid rgba(0,0,0,0.15);
    }
    .legend-name {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .legend-sep {
      height: 1px;
      background: #eee;
      margin: 4px 0;
    }
  <\/style>
<\/head>
<body>
  <div class="notice">
    [WARNING] 此文件需要从 CDN 加载资源，请保持网络连接。图表将在资源加载完成后自动渲染。
  <\/div>
  ${legendHtmlFull}
  <pre class="mermaid">
${mermaidCode}
  <\/pre>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';

    let initPromise = Promise.resolve();
    ${isElk ? `
    initPromise = import('https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@0.1.4/dist/mermaid-layout-elk.esm.min.mjs')
      .then(elkLayouts => {
        mermaid.registerLayoutLoaders(elkLayouts.default);
      });
    ` : ''}

    // 先添加缩放和拖拽功能（在mermaid渲染之前）
    let scale = 1;
    let translateX = 0;
    let translateY = 0;
    let isDragging = false;
    let lastX = 0;
    let lastY = 0;
    const minScale = 0.1;
    const maxScale = 3;
    
    const updateTransform = (svg) => {
      svg.style.transform = 'translate(' + translateX + 'px, ' + translateY + 'px) scale(' + scale + ')';
    };
    
    document.addEventListener('wheel', (e) => {
      const svg = document.querySelector('.mermaid svg');
      if (!svg) return;
      
      const svgRect = svg.getBoundingClientRect();
      const margin = 50;
      if (e.clientX >= svgRect.left - margin && e.clientX <= svgRect.right + margin &&
          e.clientY >= svgRect.top - margin && e.clientY <= svgRect.bottom + margin) {
        e.preventDefault();
        
        const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
        const newScale = Math.max(minScale, Math.min(maxScale, scale * zoomFactor));
        scale = newScale;
        updateTransform(svg);
      }
    }, { passive: false });
    
    // 拖拽功能
    document.addEventListener('mousedown', (e) => {
      const svg = document.querySelector('.mermaid svg');
      if (!svg) return;
      
      const svgRect = svg.getBoundingClientRect();
      if (e.clientX >= svgRect.left && e.clientX <= svgRect.right &&
          e.clientY >= svgRect.top && e.clientY <= svgRect.bottom) {
        isDragging = true;
        lastX = e.clientX;
        lastY = e.clientY;
        svg.style.cursor = 'grabbing';
      }
    });
    
    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      
      const svg = document.querySelector('.mermaid svg');
      if (!svg) return;
      
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      translateX += dx;
      translateY += dy;
      lastX = e.clientX;
      lastY = e.clientY;
      updateTransform(svg);
    });
    
    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        const svg = document.querySelector('.mermaid svg');
        if (svg) {
          svg.style.cursor = 'grab';
        }
      }
    });
    
    // 渲染完成后滚动到SVG位置
    const scrollToSvg = () => {
      const svg = document.querySelector('.mermaid svg');
      if (svg) {
        svg.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    };
    
    initPromise.then(() => {
      mermaid.initialize(${JSON.stringify(config)});
      mermaid.run({ querySelector: '.mermaid' }).then(() => {
        // 关键修复 v26：渲染成功后自动移除顶部 WARNING 提示
        // 之前渲染完成后没移除 .notice，导致 WARNING 一直显示
        const noticeEl = document.querySelector('.notice');
        if (noticeEl) noticeEl.remove();

        // 渲染完成后滚动到SVG位置
        setTimeout(scrollToSvg, 100);
        
        // 修复SVG顶部空白：调整viewBox
        setTimeout(() => {
          const svg = document.querySelector('.mermaid svg');
          if (svg) {
            const viewBox = svg.getAttribute('viewBox');
            if (viewBox) {
              const parts = viewBox.split(' ');
              if (parts.length === 4) {
                // 重置viewBox的起始位置到0,0
                parts[0] = '0';
                parts[1] = '0';
                svg.setAttribute('viewBox', parts.join(' '));
                svg.style.marginTop = '0';
              }
            }
          }
        }, 200);
        
        // 渲染完成后修改容器颜色，增加嵌套容器区分度
        setTimeout(() => {
          const svg = document.querySelector('.mermaid svg');
          if (svg) {
            let subgraphs = Array.from(svg.querySelectorAll('.cluster'));
            if (subgraphs.length === 0) {
              subgraphs = Array.from(svg.querySelectorAll('g.cluster'));
            }
            
            if (subgraphs.length === 0) {
              const allRects = svg.querySelectorAll('rect');
              const rectInfos = [];
              allRects.forEach(rect => {
                const width = parseFloat(rect.getAttribute('width')) || 0;
                const height = parseFloat(rect.getAttribute('height')) || 0;
                const area = width * height;
                const parent = rect.closest('g');
                rectInfos.push({ rect, width, height, area, parent });
              });
              
              rectInfos.sort((a, b) => b.area - a.area);
              const areas = rectInfos.map(r => r.area);
              const avgArea = areas.reduce((a, b) => a + b, 0) / areas.length;
              const containerThreshold = avgArea * 2;
              const containerGroups = new Set();
              
              rectInfos.forEach(info => {
                if (info.area >= containerThreshold && info.parent) {
                  containerGroups.add(info.parent);
                }
              });
              subgraphs = Array.from(containerGroups);
            }
            
            const getNestingLevel = (subgraph) => {
              let level = 0;
              let parent = subgraph.parentElement;
              while (parent) {
                if (parent.tagName === 'g' && subgraphs.includes(parent)) {
                  level++;
                }
                parent = parent.parentElement;
              }
              return level;
            };
            
            const containerLevels = new Map();
            subgraphs.forEach(subgraph => {
              containerLevels.set(subgraph, getNestingLevel(subgraph));
            });
            
            const colors = ['#ffffff', '#e0e0e0', '#c0c0c0', '#a0a0a0'];
            
            subgraphs.forEach((subgraph, index) => {
              const rect = subgraph.querySelector('rect');
              if (rect) {
                const level = containerLevels.get(subgraph);
                const colorIndex = Math.min(level, colors.length - 1);
                const color = colors[colorIndex];
                rect.setAttribute('fill', color);
                rect.setAttribute('stroke', '#666666');
                rect.setAttribute('stroke-width', '2');
                rect.style.fill = color;
                rect.style.stroke = '#666666';
                rect.style.strokeWidth = '2px';
                rect.style.opacity = '1';
                rect.setAttribute('opacity', '1');
              }
            });
          }
        }, 500);
      }).catch(err => {
        console.error('Mermaid渲染失败:', err);
        const notice = document.querySelector('.notice');
        if (notice) {
          const errMsg = err && err.message ? err.message : String(err);
          const isTextSizeError = errMsg.toLowerCase().includes('text size') || errMsg.toLowerCase().includes('maximum');
          if (isTextSizeError) {
            notice.innerHTML = '[WARNING] 图表内容过大，超出当前渲染限制。建议：在应用内使用"导出图片"功能代替HTML导出。';
          } else {
            notice.innerHTML = '[X] 图表渲染失败：' + errMsg + '。请检查图表数据是否正确。';
          }
          notice.style.background = '#f8d7da';
          notice.style.borderColor = '#f5c6cb';
          notice.style.color = '#721c24';
        }
      });
    }).catch(err => {
      console.error('加载失败:', err);
      const notice = document.querySelector('.notice');
      if (notice) {
        notice.innerHTML = '[X] 资源加载失败，请检查网络连接后刷新页面。错误：' + err.message;
        notice.style.background = '#f8d7da';
        notice.style.borderColor = '#f5c6cb';
        notice.style.color = '#721c24';
      }
    });
  <\/script>
<\/body>
<\/html>`
        const blob = new Blob([htmlContent], { type: 'text/html' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `diagram-full-${Date.now()}.html`
        link.click()
        showToast('彩色版已生成')
      }
    }

    // 导出为 PDF（横版，含 legend）
    // 关键修复 v28：分两路合成
    //   - SVG 走 Image 路径：浏览器原生渲染 SVG，自动应用 <style> 块里的 fill/stroke 等（保留图表颜色）
    //   - Legend 走 html2canvas：浏览器原生渲染中文（无字体限制）
    //   - 用 Canvas 2D 把两者合成到一起，再嵌入 jsPDF
    // 修复历史：
    //   v26 svg2pdf.js → 中文乱码 + 图表文字不显示（Helvetica 不支持中文）
    //   v27 html2canvas 单体 → 中文 OK，但图表颜色丢失（html2canvas 不解析 SVG <style> 块）
    //   v28 分路合成 → 中文 OK + 颜色 OK
    const exportAsPdf = async () => {
      const svgEl = mermaidContainer.value?.querySelector('svg')
      if (!svgEl) {
        showToast('暂无图表可导出')
        return
      }

      // 准备 legend 数据
      const annotationConfigPdf = props.diagramData?.annotationConfig || {}
      const centerScopeHighlightPdf = annotationConfigPdf.centerScopeHighlight !== false
      const colorLegendDataPdf = (props.diagramType === 'serviceModule' || props.diagramType === 'businessObject')
        ? svgProcessor.buildColorLegendData(props.diagramData, nodeColorMappings, centerScopeHighlightPdf)
        : []

      showToast('正在生成 PDF，请稍候...')

      const scale = 1.5
      const padding = 20

      try {
        // ============================================================
        // 1. SVG → Image（浏览器原生 SVG 渲染，完美保留 <style> 块的颜色 + 中文）
        // 关键修复 v29：用 data URL 代替 blob URL（headless 环境下 blob URL 的 SVG 加载有兼容性问题，会卡住 onload）
        // ============================================================
        // 先克隆 SVG 并设置明确的 width/height（避免 load 后 naturalWidth=0）
        const svgCloneForExport = svgEl.cloneNode(true)
        if (!svgCloneForExport.getAttribute('xmlns')) {
          svgCloneForExport.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
        }
        // 优先用 viewBox 尺寸，否则用 bounding rect
        const origViewBox = svgEl.getAttribute('viewBox')
        let exportSvgWidth, exportSvgHeight
        if (origViewBox) {
          const parts = origViewBox.split(/\s+/).map(parseFloat)
          if (parts.length === 4 && parts[2] > 0 && parts[3] > 0) {
            exportSvgWidth = parts[2]
            exportSvgHeight = parts[3]
          }
        }
        if (!exportSvgWidth) {
          const rect = svgEl.getBoundingClientRect()
          exportSvgWidth = rect.width || 800
          exportSvgHeight = rect.height || 600
        }
        svgCloneForExport.setAttribute('width', String(exportSvgWidth))
        svgCloneForExport.setAttribute('height', String(exportSvgHeight))

        const svgString = new XMLSerializer().serializeToString(svgCloneForExport)
        // 用 encodeURIComponent 编码生成 data URL（避免 SVG 里的 # 等字符被截断）
        const svgDataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgString)

        const svgImg = new Image()
        // 加 5s 超时保护，避免 headless 环境下 onload 卡住
        await Promise.race([
          new Promise((resolve, reject) => {
            svgImg.onload = resolve
            svgImg.onerror = () => reject(new Error('SVG 加载失败'))
            svgImg.src = svgDataUrl
          }),
          new Promise((_, reject) => {
            setTimeout(() => reject(new Error('SVG 加载超时 (5s)')), 5000)
          })
        ])

        // 获取 SVG 实际尺寸（优先用 Image 加载后的 naturalWidth，fallback 到 viewBox 解析）
        let svgWidth = svgImg.naturalWidth || exportSvgWidth || 800
        let svgHeight = svgImg.naturalHeight || exportSvgHeight || 600

        // ============================================================
        // 2. Legend → Canvas（用 html2canvas 渲染 DOM，中文由浏览器绘制）
        // ============================================================
        let legendCanvas = null
        if (colorLegendDataPdf.length > 0) {
          const legendWrapper = document.createElement('div')
          legendWrapper.style.cssText = [
            'position: fixed',
            'left: -99999px',
            'top: 0',
            'background: #ffffff',
            'padding: 20px',
            'font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", "Helvetica Neue", Arial, sans-serif',
            'color: #222',
            'width: ' + (svgWidth + padding * 2) + 'px',
            'box-sizing: border-box'
          ].join(';')

          const legendTitle = document.createElement('div')
          legendTitle.textContent = '图例'
          legendTitle.style.cssText = 'font-size: 36px; font-weight: bold; margin-bottom: 20px; color: #333;'
          legendWrapper.appendChild(legendTitle)

          const legendGrid = document.createElement('div')
          legendGrid.style.cssText = 'display: flex; flex-wrap: wrap; gap: 16px 32px;'
          colorLegendDataPdf.forEach((item) => {
            const itemDiv = document.createElement('div')
            itemDiv.style.cssText = 'display: flex; align-items: center; gap: 12px; font-size: 30px; white-space: nowrap;'
            const colorBox = document.createElement('span')
            colorBox.style.cssText = `display: inline-block; width: 36px; height: 36px; background: ${item.color || '#e0e0e0'}; border: 1px solid #999; border-radius: 2px;`
            const nameSpan = document.createElement('span')
            nameSpan.textContent = item.name || ''
            itemDiv.appendChild(colorBox)
            itemDiv.appendChild(nameSpan)
            legendGrid.appendChild(itemDiv)
          })
          legendWrapper.appendChild(legendGrid)

          document.body.appendChild(legendWrapper)
          try {
            legendCanvas = await html2canvas(legendWrapper, {
              backgroundColor: '#ffffff',
              scale: scale,
              logging: false,
              useCORS: true
            })
          } finally {
            document.body.removeChild(legendWrapper)
          }
        }

        // ============================================================
        // 3. 合成 final canvas（白底 + legend + SVG）
        // ============================================================
        const finalWidth = Math.max(
          legendCanvas ? legendCanvas.width : 0,
          svgWidth * scale + padding * 2 * scale
        )
        const legendHeightPx = legendCanvas ? legendCanvas.height : 0
        const finalHeight = legendHeightPx + svgHeight * scale + padding * scale

        const finalCanvas = document.createElement('canvas')
        finalCanvas.width = finalWidth
        finalCanvas.height = finalHeight
        const ctx = finalCanvas.getContext('2d')
        ctx.fillStyle = '#ffffff'
        ctx.fillRect(0, 0, finalCanvas.width, finalCanvas.height)

        // 画 legend（顶部）
        if (legendCanvas) {
          ctx.drawImage(legendCanvas, 0, 0)
        }
        // 画 SVG（legend 下方）
        const svgDrawY = legendHeightPx + padding * scale
        const svgDrawX = padding * scale
        ctx.drawImage(svgImg, svgDrawX, svgDrawY, svgWidth * scale, svgHeight * scale)

        // ============================================================
        // 4. A4 横版 PDF
        // ============================================================
        const pdf = new jsPDF({
          orientation: 'landscape',
          unit: 'pt',
          format: 'a4'
        })
        const pageWidthPt = pdf.internal.pageSize.getWidth()   // ~841.89
        const pageHeightPt = pdf.internal.pageSize.getHeight()  // ~595.28
        const marginPt = 20

        const aspectCanvas = finalCanvas.width / finalCanvas.height
        const drawAreaW = pageWidthPt - marginPt * 2
        const drawAreaH = pageHeightPt - marginPt * 2
        const aspectArea = drawAreaW / drawAreaH
        let renderW, renderH
        if (aspectCanvas > aspectArea) {
          renderW = drawAreaW
          renderH = drawAreaW / aspectCanvas
        } else {
          renderH = drawAreaH
          renderW = drawAreaH * aspectCanvas
        }
        const renderX = marginPt + (drawAreaW - renderW) / 2
        const renderY = marginPt + (drawAreaH - renderH) / 2

        // 嵌入 PNG 到 PDF
        const imgData = finalCanvas.toDataURL('image/png')
        pdf.addImage(imgData, 'PNG', renderX, renderY, renderW, renderH)
        pdf.save(`diagram-${Date.now()}.pdf`)
        showToast('PDF 已生成')
      } catch (err) {
        console.error('[MermaidComponent] PDF 导出失败:', err)
        showToast('PDF 导出失败: ' + (err?.message || String(err)))
      }
    }

    // 复制到剪贴板
    const copyToClipboard = async () => {
      if (props.diagramData) {
        const positions = props.layoutPositions || []
        const zoneRowCount = props.zoneRowCount || 3
        const mermaidCode = generateMermaidCode(props.diagramData, props.layoutEngine, props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
        try {
          await navigator.clipboard.writeText(mermaidCode)
          showToast('已复制到剪贴板')
        } catch (err) {
          console.error('复制失败:', err)
          showToast('复制失败')
        }
      }
    }

    // Toast 提示
    const showToast = (message) => {
      let toast = document.createElement('div')
      toast.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0,0,0,0.8);
        color: white;
        padding: 10px 20px;
        border-radius: 4px;
        font-size: 14px;
        z-index: 10000;
        animation: fadeIn 0.3s ease;
      `
      toast.textContent = message
      document.body.appendChild(toast)
      setTimeout(() => {
        toast.style.opacity = '0'
        toast.style.transition = 'opacity 0.3s'
        setTimeout(() => toast.remove(), 300)
      }, 2000)
    }

    return {
      mermaidContainer,
      mermaidContainerEl,
      mermaidWrapper,
      draggableArea,
      isMaximized,
      shouldHideTails,
      toggleMaximize,
      resetAdaptive: interaction.resetAdaptive,
      autoFitDiagram: interaction.autoFitDiagram,
      exportAsImage,
      exportAsNative,
      exportAsHtmlSimple,
      exportAsHtmlFull,
      exportAsPdf,
      copyToClipboard
    }
  }
}
</script>



