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
        <!-- [DEPRECATED 2026-07-11] 彩色 HTML 导出 - 后续废弃，简版已具备全部功能
        <button class="toolbar-btn toolbar-btn--primary" @click="exportAsHtmlFull" title="导出 HTML（彩色版 - 可直接双击打开）">
          <AppIcon name="export" size="sm" />
          <span class="toolbar-btn-label">彩色HTML</span>
        </button>
        -->
        <button class="toolbar-btn toolbar-btn--primary" @click="exportAsHtmlSimple" title="导出 HTML（简版 - 单文件、依赖轻、双击即可打开）">
          <AppIcon name="export" size="sm" />
          <span class="toolbar-btn-label">HTML</span>
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
import { useTooltip, preloadEnums } from '../composables/useMermaid/tooltip/index.js'
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
    let interactionCleanup = null  // useInteraction 返回的清理函数（用于 onBeforeUnmount）

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
    // [v34 双向支持] 暴露 mermaidCode 到 window, E2E 可读取诊断 syntax error
    let lastMermaidCodeRef = ''

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
            const code = result.code || result.mermaidCode || ''
            lastMermaidCodeRef = code
            if (typeof window !== 'undefined') window.__lastMermaidCode = code
            return code
          }
          lastMermaidCodeRef = result
          if (typeof window !== 'undefined') window.__lastMermaidCode = result
          return result
        } else {
          const result = businessObjectSyntax.generateMermaidCode(data, relationDescriptions, layoutEngine, layoutType, layoutControlConfig)
          if (typeof result === 'object' && result !== null) {
            nodeColorMappings = result.nodeColorMappings || []
            linkColorMappings = result.linkColorMappings || []
            const code = result.mermaidCode || ''
            lastMermaidCodeRef = code
            if (typeof window !== 'undefined') window.__lastMermaidCode = code
            return code
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

      // [v40 关系枚举预加载] 渲染前先预加载 relation_type / direction 枚举
      // 之前 fire-and-forget 时, 用户首次 hover 时 EnumService 还没加载完 → tooltip 显示 code
      // 修复: 在渲染前 await 加载, 后续 hover 一定命中缓存 (L1)
      if (props.diagramData && props.diagramData.links && props.diagramData.links.length > 0) {
        preloadEnums().catch((e) => {
          console.warn('[MermaidComponent] preloadEnums failed:', e?.message || e)
        })
      }

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

            // [V007.59] 关系数大图自动切 elk
            //   根因 (Playwright 验证): mermaid 11.13.0 + dagre 在 ≥ 2000 关系时
            //   dagre 内部用递归 DFS 处理 edge routing, 触发 "Maximum call stack size
            //   exceeded", mermaid 把它包装成模糊的 "Syntax error in text".
            //   阈值: 1500 边 (< 1500 边 dagre 仍稳定; ≥ 1500 自动 elk)
            //   验证: tools/test_mermaid_volume.py 1000 边 dagre PASS, 2000 边 dagre FAIL
            const relationshipCount = props.diagramData?.links?.length || 0
            const DAGRE_REL_LIMIT = 1500
            if (effectiveLayoutEngine !== 'elk' && relationshipCount >= DAGRE_REL_LIMIT) {
              console.log(`[V007.59] ${relationshipCount} 关系 >= ${DAGRE_REL_LIMIT} 阈值, 自动切换 elk 布局 (避免 dagre stack overflow)`)
              effectiveLayoutEngine = 'elk'
            }

            if (effectiveLayoutEngine === 'elk') {
              const elkLoaded = await loadElkLayouts(true)
              if (!elkLoaded) {
                effectiveLayoutEngine = 'dagre'
              } else {
                try {
                  const mermaidCode = generateMermaidCode(props.diagramData, 'elk', props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
                  // 关键修复：动态调整 maxTextSize，避免大图表报 'Maximum text size in diagram exceeded'
                  const dynamicMaxTextSize = Math.max(configStore.mermaidMaxTextSize || 500000, mermaidCode.length * 2 + 100000)
                  initializeMermaid(props.diagramType, props.diagramData, 'elk', props.layoutType, props.preserveModelOrder, effectiveLayoutControlConfig.value, dynamicMaxTextSize)
                  mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
                } catch (e) {
                  console.error('[MermaidComponent] ELK Error generating mermaid code, falling back to dagre:', e)
                  effectiveLayoutEngine = 'dagre'
                }
              }
            }

            if (!effectiveLayoutEngine || effectiveLayoutEngine !== 'elk') {
              try {
                const mermaidCode = generateMermaidCode(props.diagramData, effectiveLayoutEngine || 'dagre', props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
                // [V007.55 DEBUG] 暴露 mermaidCode 到 window, Playwright 可抓
                if (typeof window !== 'undefined') {
                  window.__lastMermaidCode = mermaidCode
                  window.__lastMermaidCodeLen = mermaidCode.length
                  console.log('[V007.55 DEBUG] mermaidCode length:', mermaidCode.length)
                }
                // [V007.59] 关系数 >= 1000 时主动降低 maxTextSize, 给 dagre stack 留余量
                //   maxTextSize 越大 mermaid 内部 lexer/parser 递归越深, 容易爆栈
                //   经验值: 1000 边 dagre 用默认 500000 还能 PASS, 2000 边即使 maxTextSize 很小也 FAIL (dagre 自身递归)
                const dynamicMaxTextSize = Math.max(configStore.mermaidMaxTextSize || 500000, mermaidCode.length * 2 + 100000)
                initializeMermaid(props.diagramType, props.diagramData, effectiveLayoutEngine || 'dagre', props.layoutType, props.preserveModelOrder, effectiveLayoutControlConfig.value, dynamicMaxTextSize)
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
          // [V007.60] mermaid.run() 在 parse 失败时不 reject promise, 只把
          //   "Syntax error in text" 插入 DOM. 用户看不到真实错误.
          //   显式调 mermaid.parse() 捕获真实错误 (RangeError / 具体语法位置)
          const codeToParse = lastMermaidCodeRef || window.__lastMermaidCode || ''
          if (codeToParse) {
            mermaid.parse(codeToParse, { suppressErrors: false })
              .then(() => {
                console.log('[V007.60] mermaid.parse() OK, code length:', codeToParse.length)
              })
              .catch((parseErr) => {
                const detail = {
                  name: parseErr?.name,
                  message: parseErr?.message?.slice(0, 500),
                  hash: parseErr?.hash,
                  stack: parseErr?.stack?.split('\n').slice(0, 10).join('\n'),
                  codeLen: codeToParse.length,
                }
                console.error('[V007.60] mermaid.parse() FAIL:', JSON.stringify(detail, null, 2))
                if (typeof window !== 'undefined') {
                  window.__mermaidParseError = detail
                }
              })
          }
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
              // [V007.57] 详细打印 mermaid.run 错误 (之前的日志只显示 Object, 看不到 Syntax error 详情)
              const errDetail = {
                message: err?.message || String(err),
                hash: err?.hash,
                str: err?.str,
                name: err?.name,
                stack: err?.stack?.split('\n').slice(0, 5).join('\n'),
              }
              console.error('[V007.57 MermaidComponent] mermaid.run() rejected DETAIL:', JSON.stringify(errDetail, null, 2))
              console.error('[V007.57 MermaidComponent] mermaid.run() rejected RAW:', err)
              // 暴露到 window, Playwright 可抓
              if (typeof window !== 'undefined') {
                window.__mermaidLastError = errDetail
                window.__mermaidLastErrorRaw = err
              }
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

    // [FIX 2026-06-29] 监听 annotationConfig 变化 (用户切换备注类型过滤)
    // 之前没监听, filter 变更不会触发重新渲染, annotation overlay 不会更新
    // 只重跑 renderAnnotationOverlay 而不重跑整个 mermaid 渲染 (性能)
    watch(
      () => props.annotationConfig,
      (newVal, oldVal) => {
        if (!newVal || !mermaidContainer.value) return
        const svgEl = mermaidContainer.value.querySelector('svg')
        if (!svgEl) return
        console.log('[MermaidComponent] annotationConfig changed, filter:', newVal.annotationCategoryFilter, 'panel:', newVal.annotationPanelPosition, 'icons:', newVal.showAnnotationIcons)
        // 重跑 processSvg (它内部会调 renderAnnotationOverlay)
        // 主线不受影响: annotation overlay 移除+重新渲染, 其他 SVG 元素不动 (renderAnnotationOverlay 内部 removeAnnotationLayers 后重画)
        svgProcessor.processSvg(svgEl, props, relationDescriptions, mermaidContainer, nodeColorMappings)
      },
      { deep: true }
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

      // [v40 修复] 主动预加载 direction / relation_type 枚举
      // 原因: 之前 fire-and-forget 在第一次 hover 时才触发, 用户在第一次 hover 前
      //       tooltip 仍显示 raw code (例如 'PUSH' / 'GENERATES')
      // 修复: 组件挂载即 await preloadEnums(), EnumService._cache 在用户首次 hover 前就绪
      preloadEnums().catch((e) => {
        console.warn('[MermaidComponent] preloadEnums failed:', e?.message || e)
      })

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
      // 修复内存泄漏：清理 useInteraction 注册的 wheel/mousedown/mousemove/mouseup 监听器
      if (interactionCleanup) {
        interactionCleanup()
        interactionCleanup = null
      }
      // 修复内存泄漏：清理 useTooltip + annotationOverlay 注册的监听器
      // svgProcessor.cleanup() 内部调用 tooltip.cleanup()
      if (svgProcessor && typeof svgProcessor.cleanup === 'function') {
        svgProcessor.cleanup()
      }
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

    // 导出为 HTML 文件（简洁版 - 预渲染静态 SVG，离线可用，支持 ELK 布局）
    // [V007.62] 改为预渲染模式：从前端已渲染的 SVG 直接嵌入 HTML，无需 mermaid.js 运行时
    //   - 保留当前布局引擎（dagre/ELK）的渲染结果
    //   - file:// 协议兼容（纯 SVG + CSS，零 JS 执行）
    //   - 体积从 ~2MB（内嵌 mermaid.min.js）降至 ~200KB（纯 SVG）
    const exportAsHtmlSimple = async () => {
      // 每次调用生成一个唯一 token，用于区分浏览器调用的是哪份代码
      const runtimeToken = 'RT-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8)
      console.log('[V007.62-FIX-20260711-1440] exportAsHtmlSimple called, token=' + runtimeToken)
      if (props.diagramData) {
        const chartTypeLabel = props.diagramType === 'serviceModule' ? '服务模块图' : '业务对象图'
        
        // 从 DOM 获取已渲染的 SVG
        const svgEl = mermaidContainer.value?.querySelector('svg')
        if (!svgEl) {
          showToast('图表尚未渲染，请稍候重试')
          return
        }
        
        // 克隆 SVG 并清理（移除交互事件、tooltip 等运行时元素）
        const svgClone = svgEl.cloneNode(true)
        // 把 runtime token 写进 SVG 根节点，下载后可作为"这是新代码生成的"证据
        svgClone.setAttribute('data-runtime-token', runtimeToken)
        // 移除独立 tooltip 弹窗（保留 annotation markers 和 color legend）
        svgClone.querySelectorAll('.tooltip, #mermaid-tooltip').forEach(el => el.remove())
        // 移除内联事件处理器
        svgClone.querySelectorAll('[onclick], [onmouseover], [onmouseout], [onmousemove]').forEach(el => {
          el.removeAttribute('onclick')
          el.removeAttribute('onmouseover')
          el.removeAttribute('onmouseout')
          el.removeAttribute('onmousemove')
        })
        // 修复 viewBox：确保起点为 0,0
        const viewBox = svgClone.getAttribute('viewBox')
        if (viewBox) {
          const parts = viewBox.split(' ')
          if (parts.length === 4) {
            parts[0] = '0'
            parts[1] = '0'
            svgClone.setAttribute('viewBox', parts.join(' '))
          }
        }
        // [v50 修复] SVG 真实 DOM 大小必须可控
        //   之前强制 width/height = viewBox 数字 (90k px), SVG 真实占 90k×52k
        //   撑爆 body, 滚动条超长
        //   新方案: width/height = 100%, viewBox 控制坐标系, SVG 元素大小由 container 决定
        //   这样 SVG 永远占满可视区域, viewBox 决定坐标系 (90k×52k 单位)
        //   用户的 transform scale zoom 在此基础上工作
        if (!svgClone.getAttribute('width') || svgClone.getAttribute('width') === '100%') {
          // 不强制设 width/height, 保留 100% (CSS .diagram-container svg { max-width: none } 已生效)
          // 实际渲染时 SVG 跟随 container (100vw × auto)
        }
        // 显式设 width=100% + height=auto, 让 SVG 跟随 container 宽度, 高度按 viewBox 比例
        svgClone.setAttribute('width', '100%')
        svgClone.setAttribute('height', 'auto')
        // 重要: preserveAspectRatio="xMidYMid meet" 让内容 fit 容器, 不裁剪
        svgClone.setAttribute('preserveAspectRatio', 'xMidYMid meet')
        
        // svgHtml 暂不序列化，等 tooltip/annotation 注入后再取 outerHTML

        // 诊断：收集真实状态
        const diag = {
          hasDiagramData: !!props.diagramData,
          diagramType: props.diagramType,
          layoutEngine: props.layoutEngine,
          annotationConfigKeys: Object.keys(props.annotationConfig || {}),
          hasAnnotationComposable: typeof annotation !== 'undefined' && !!annotation,
          hasParseMethod: typeof annotation !== 'undefined' && typeof annotation.parseAnnotationsFromData === 'function',
          relationDescriptionsLen: Array.isArray(relationDescriptions) ? relationDescriptions.length : 0,
          relationDescriptionsSample: Array.isArray(relationDescriptions) && relationDescriptions.length > 0 ? Object.keys(relationDescriptions[0] || {}) : [],
          svgNodeCount: svgClone.querySelectorAll('.node').length,
          svgEdgeCount: svgClone.querySelectorAll('g.edges > path, g.edgePaths > path, g.edgePath > path, path.flowchart-link').length,
          svgEdgeLabelCount: svgClone.querySelectorAll('.edgeLabel').length,
          svgAnnotationMarkerCount: svgClone.querySelectorAll('.annotation-marker').length
        }

        // 收集 annotation 数据（marker 数字 → 文字内容），嵌入 JSON
        const annotationMap = {}
        try {
          const annCfg = props.annotationConfig || {}
          const annFilter = annCfg.annotationCategoryFilter || []
          let annotationList = []
          if (typeof window.__getAnnotationList === 'function') {
            annotationList = window.__getAnnotationList(props.diagramData, props.diagramType, annFilter)
          } else if (annotation && typeof annotation.parseAnnotationsFromData === 'function') {
            annotationList = annotation.parseAnnotationsFromData(props.diagramData, props.diagramType, { filter: annFilter })
          }
          annotationList.forEach((a, idx) => {
            const targetLabel = a.targetType === 'relation'
              ? (a.targetName || (a.sourceBOName || a.targetBOName ? `${a.sourceBOName || ''} → ${a.targetBOName || ''}` : ''))
              : (a.targetName || '')
            annotationMap[String(idx + 1)] = {
              title: targetLabel || `备注 ${idx + 1}`,
              content: a.content || '',
              category: a.category || '',
              // [v41 修复] category 名优先(优先中文), 找不到则 fallback 到 code
              categoryLabel: a.categoryName || a.category || '',
              targetType: a.targetType || '',
              targetId: a.targetId || '',
              relationCode: a.relationCode || ''
            }
          })
        } catch (e) { console.warn('[exportAsHtmlSimple] annotation collection:', e) }

        // 收集边的 tooltip 文本（relationDescriptions 是数组，按边渲染顺序一一对应）
        const tooltipMap = {}
        // ELK 模式下 mermaid 用 <g class="edges edgePaths"><path>...</g> 结构
        // dagre 模式下用 <g class="edgePath"><path/></g> 结构
        // 用通用选择器：所有 g.edges > path 和 g.edgePath > path
        const realEdgePaths = Array.from(svgClone.querySelectorAll('g.edges > path, g.edgePaths > path, g.edgePath > path, path.flowchart-link'))
        // 兜底：如果上面没找到，尝试直接选 g.edges 内的所有 path
        if (realEdgePaths.length === 0) {
          const edgesContainer = svgClone.querySelector('g.edges, g.edgePaths')
          if (edgesContainer) {
            realEdgePaths.push(...Array.from(edgesContainer.querySelectorAll('path')))
          }
        }
        const relArr = Array.isArray(relationDescriptions) ? relationDescriptions : []
        const directionMap = { PUSH: '推(PUSH)', PULL: '拉(PULL)', BIDIRECTIONAL: '双向', '双向': '双向' }
        relArr.forEach((rel, idx) => {
          if (idx >= realEdgePaths.length) return
          // 与图表边标签一致：code > relationCode > relationDesc（同 useBusinessObjectSyntax L905-911）
          const codeLabel = (rel.code && String(rel.code).trim())
            ? rel.code
            : (rel.relationCode && String(rel.relationCode).trim())
              ? rel.relationCode
              : (rel.relationDesc && String(rel.relationDesc).trim())
                ? rel.relationDesc
                : ''
          if (!codeLabel) return
          // 构建 tooltip：标签 + 源→目标 + 关系类型 + 方向 + 描述
          const lines = [codeLabel]
          const src = rel.sourceName || rel.sourceCode || ''
          const tgt = rel.targetName || rel.targetCode || ''
          if (src && tgt) lines.push(`${src} → ${tgt}`)
          const rt = String(rel.relationType || '').replace(/^legacy[_\s]*null$/i, '').replace(/^null$/i, '').trim()
          if (rt) lines.push(`类型: ${rt}`)
          const rd = String(rel.relationDirection || '').replace(/^legacy[_\s]*null$/i, '').replace(/^null$/i, '').trim()
          if (rd) {
            const dirText = directionMap[rd] || rd
            lines.push(`方向: ${dirText}`)
          }
          if (rel.relationDesc && rel.relationDesc !== codeLabel) lines.push(rel.relationDesc)
          const key = 'tt' + idx
          tooltipMap[key] = lines.join('\n')
          realEdgePaths[idx].setAttribute('data-edge-tooltip', key)
        })
        // 给 edgeLabel 也注入 data-edge-tooltip，通过 path id 关联
        svgClone.querySelectorAll('.edgeLabel').forEach((labelEl) => {
          // 通过 label 内的 data-id 或 label 自身属性找对应的 path id
          const labelDataId = labelEl.querySelector('[data-id]')?.getAttribute('data-id')
            || labelEl.getAttribute('data-id')
          if (!labelDataId) return
          const pathEl = svgClone.querySelector(`path[id="${labelDataId}"]`)
            || svgClone.querySelector(`[id="${labelDataId}"]`)
          if (!pathEl) return
          const ttKey = pathEl.getAttribute('data-edge-tooltip')
          if (ttKey) labelEl.setAttribute('data-edge-tooltip', ttKey)
        })
        // 兜底：如果 relationDescriptions 为空但 edgeLabel 有文本，仍尝试注入
        if (Object.keys(tooltipMap).length === 0) {
          let fallbackIdx = 0
          svgClone.querySelectorAll('.edgeLabel').forEach((labelEl) => {
            const txt = labelEl.textContent?.trim()
            if (!txt) return
            const key = 'tt' + (fallbackIdx++)
            tooltipMap[key] = txt
            const edgePath = labelEl.closest('g.edgeContainer')?.querySelector('.edgePath') || labelEl.parentElement?.querySelector('.edgePath')
            if (edgePath) edgePath.setAttribute('data-edge-tooltip', key)
            else labelEl.setAttribute('data-edge-tooltip', key)
          })
        }
        // 运行时诊断 dump（便于用户配合排查）
        console.log('[V007.62-FIX-20260711-1440] runtime=' + runtimeToken
          + ' realEdgePaths.length=' + realEdgePaths.length
          + ' relArr.length=' + relArr.length
          + ' tooltipMap.size=' + Object.keys(tooltipMap).length
          + ' svgEdgeDataAttrCount=' + svgClone.querySelectorAll('[data-edge-tooltip]').length)

        // 所有关联 data 注入完成后再序列化 SVG
        const svgHtml = svgClone.outerHTML

        // 收集图例数据（与彩色版一致）
        const annotationConfigSimple = props.annotationConfig || {}
        const centerScopeHighlightSimple = annotationConfigSimple.centerScopeHighlight !== false
        const colorLegendDataSimple = (props.diagramType === 'serviceModule' || props.diagramType === 'businessObject')
          ? svgProcessor.buildColorLegendData(props.diagramData, nodeColorMappings, centerScopeHighlightSimple)
          : []
        const legendItemsHtmlSimple = colorLegendDataSimple.map((item, idx) => {
          const sep = (item.isCenter && idx < colorLegendDataSimple.length - 1)
            ? '<div class="legend-sep"></div>'
            : ''
          return `<div class="legend-item" title="${item.name || ''}">
            <span class="legend-dot" style="background:${item.color || '#e0e0e0'}"></span>
            <span class="legend-name">${item.name || ''}</span>
          </div>${sep}`
        }).join('')
        const legendHtmlSimple = colorLegendDataSimple.length > 0
          ? `<div class="color-legend-panel">
              <div class="color-legend-title">图例</div>
              <div class="color-legend-list">${legendItemsHtmlSimple}</div>
            </div>`
          : ''

        const annotationJson = JSON.stringify(annotationMap).replace(/</g, '\\u003c')
        const tooltipJson = JSON.stringify(tooltipMap).replace(/</g, '\\u003c')
        const layoutEngineLabel = props.layoutEngine === 'elk' ? 'ELK' : 'dagre'

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
      /* [v49 修复] 允许 body 滚动, 否则 90k × 52k 像素的 SVG 上下左右被裁 */
      height: auto;
      min-height: 100%;
      overflow: auto;
    }
    body {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
      padding: 10px;
    }
    .diagram-container {
      display: block;
      background: white;
      width: 100%;
      /* [v50 修复] 固定高度 = 视口高度, 让 SVG width=100% height=auto 渲染时能 fit 容器 */
      height: calc(100vh - 20px);
      /* [v50 修复] hidden 让 SVG 溢出部分不显示, 由 transform 拖动查看 */
      overflow: hidden;
      cursor: grab;
      position: relative;
    }
    .diagram-container:active { cursor: grabbing; }
    .diagram-container svg {
      display: block;
      transform-origin: top left;
      transition: transform 0.1s ease-out;
      max-width: none;
      max-height: 100%;
    }
    .annotation-panel { background: rgba(255,255,255,0.97); border: 1px solid #ddd; border-radius: 6px;
      padding: 8px 12px; font-size: 12px; font-family: Arial, sans-serif;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15); max-width: 320px; z-index: 1000;
      display: none; position: absolute; pointer-events: auto; }
    .annotation-panel.visible { display: block; }
    .annotation-panel-title { font-weight: bold; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 1px solid #eee; color: #333; }
    .annotation-panel-content { color: #555; line-height: 1.5; white-space: pre-wrap; }
    .annotation-panel-cat { display: inline-block; font-size: 10px; padding: 2px 6px; border-radius: 3px; background: #e0e7ff; color: #4f46e5; margin-bottom: 4px; }
    .annotation-dock { position: fixed; bottom: 0; left: 0; right: 0; background: rgba(255,255,255,0.98);
      border-top: 1px solid #ddd; max-height: 40vh; overflow-y: auto; z-index: 800; font-size: 6px;
      box-shadow: 0 -2px 8px rgba(0,0,0,0.08); }
    .annotation-dock-header { padding: 4px 7px; font-weight: bold; border-bottom: 1px solid #eee;
      cursor: pointer; user-select: none; color: #333; background: #fafafa; position: sticky; top: 0; }
    .annotation-dock-list { padding: 3px 7px; }
    .annotation-dock-item { padding: 3px 0; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
    .annotation-dock-item:hover { background: #f8f8ff; }
    .annotation-dock-item:last-child { border-bottom: none; }
    .ann-num { display: inline-block; min-width: 10px; height: 10px; line-height: 10px; text-align: center;
      border-radius: 50%; background: #4f46e5; color: #fff; font-size: 6px; margin-right: 4px; font-weight: bold; }
    .ann-title { font-weight: 500; color: #333; }
    .ann-cat { display: inline-block; font-size: 5px; padding: 1px 3px; border-radius: 2px;
      background: #e0e7ff; color: #4f46e5; margin-left: 3px; }
    .ann-content { color: #666; margin-top: 2px; margin-left: 14px; line-height: 1.3; }
    .edge-tooltip { position: absolute; background: rgba(0,0,0,0.85); color: #fff; padding: 6px 10px;
      border-radius: 4px; font-size: 12px; line-height: 1.4; max-width: 280px; z-index: 2000;
      pointer-events: none; display: none; }
    .edge-tooltip.visible { display: block; }
    [data-edge-tooltip].hover-target { cursor: help; transition: stroke-width 0.1s, filter 0.1s; }
    [data-edge-tooltip].hover-active { stroke-width: 3 !important; filter: drop-shadow(0 0 5px rgba(0,0,0,0.6)); }
    .edgePath.hover-target path { transition: stroke-width 0.1s, filter 0.1s; }
    .edgePath.hover-active path { stroke-width: 2.5; filter: drop-shadow(0 0 4px rgba(0,0,0,0.5)); }
    .edgeLabel.hover-target { cursor: help; }
    .node.hover-target .basic, .node.hover-target rect, .node.hover-target polygon { transition: filter 0.1s; }
    .node.hover-active .basic, .node.hover-active rect, .node.hover-active polygon { filter: drop-shadow(0 0 6px rgba(0,0,0,0.5)); }
    .annotation-marker { cursor: pointer; }
    .annotation-marker:hover circle { stroke: #555 !important; stroke-width: 2 !important; }
    .color-legend-panel { position: fixed; top: 50px; right: 12px; background: rgba(255,255,255,0.96);
      border: 1px solid #ddd; border-radius: 4px; padding: 4px 6px; font-size: 6px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08); z-index: 900; max-height: 80vh; overflow-y: auto; }
    .color-legend-title { font-weight: bold; margin-bottom: 3px; padding-bottom: 2px; border-bottom: 1px solid #eee; color: #333; }
    .color-legend-list { display: flex; flex-direction: column; gap: 2px; }
    .legend-item { display: flex; align-items: center; gap: 3px; }
    .legend-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
    .legend-name { flex: 1; color: #555; }
    .legend-sep { height: 1px; background: #eee; margin: 2px 0; }
    .edge-tooltip { white-space: pre-line; }
  <\/style>
<\/head>
<body>
  <div class="diagram-container">
    ${svgHtml}
    ${Object.keys(annotationMap).length > 0 ? `
    <div id="annotation-dock" class="annotation-dock">
      <div class="annotation-dock-header" id="ann-dock-header">备注 (${Object.keys(annotationMap).length})</div>
      <div class="annotation-dock-list" id="ann-dock-list">
        ${Object.entries(annotationMap).map(([num, a]) => `
        <div class="annotation-dock-item" data-ann="${num}">
          <span class="ann-title">${a.title}</span>
          ${a.categoryLabel ? `<span class="ann-cat">${a.categoryLabel}</span>` : ''}
          ${a.content ? `<div class="ann-content">${a.content}</div>` : ''}
        </div>`).join('')}
      </div>
    </div>` : `<div id="annotation-panel" class="annotation-panel">
      <div id="ann-cat"></div>
      <div id="ann-title" class="annotation-panel-title"></div>
      <div id="ann-content" class="annotation-panel-content"></div>
    </div>`}
  </div>
  <div id="edge-tooltip" class="edge-tooltip"></div>
  ${legendHtmlSimple}
  <div id="annotations-data" style="display:none" data-json="${annotationJson.replace(/"/g, '&quot;')}"></div>
  <div id="tooltips-data" style="display:none" data-json="${tooltipJson.replace(/"/g, '&quot;')}"></div>
  <script>
    (function() {
      const container = document.querySelector('.diagram-container');
      const svg = container ? container.querySelector('svg') : null;
      if (!container || !svg) return;
      const annMap = JSON.parse(document.getElementById('annotations-data').getAttribute('data-json') || '{}');
      const ttMap = JSON.parse(document.getElementById('tooltips-data').getAttribute('data-json') || '{}');
      const annPanel = document.getElementById('annotation-panel');
      const tooltip = document.getElementById('edge-tooltip');
      let scale = 1, tx = 0, ty = 0, dragging = false, startX, startY;
      const minScale = 0.05, maxScale = 100;
      function applyTransform() {
        svg.style.transition = 'none';
        svg.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
      }
      function zoomBy(factor, cx, cy) {
        var prevScale = scale;
        var newScale = Math.max(minScale, Math.min(maxScale, scale * factor));
        if (newScale === prevScale) return;
        if (cx === undefined || cy === undefined) {
          var rect = container.getBoundingClientRect();
          cx = rect.width / 2; cy = rect.height / 2;
        }
        tx = cx - (cx - tx) * (newScale / prevScale);
        ty = cy - (cy - ty) * (newScale / prevScale);
        scale = newScale;
        applyTransform();
      }
      function fitView() {
        // [v50 修复] fit-to-container
        //   SVG 真实 DOM 已是 100% × auto, viewBox 90k×52k 决定坐标系
        //   preserveAspectRatio="xMidYMid meet" 让浏览器自动 fit (按比例缩到容器内)
        //   用户打开时已经看到完整图, fitView 重置 transform 即可
        if (!container || !svg) return;
        scale = 1; tx = 0; ty = 0;
        applyTransform();
      }
      // [v49] 打开时自动 fit-to-screen
      //   bug fix: 之前 setTimeout 50ms 太早, SVG viewBox.baseVal.width 还未稳定
      //   改用 requestAnimationFrame 等待 layout 完成, 失败时再 setTimeout 兜底
      function safeFitView() {
        var svgW = svg && svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal.width : 0;
        if (svgW > 0) {
          fitView();
        } else {
          setTimeout(safeFitView, 50);
        }
      }
      if (document.readyState === 'complete') {
        requestAnimationFrame(safeFitView);
      } else {
        window.addEventListener('load', function() {
          requestAnimationFrame(safeFitView);
        });
      }
      // 窗口大小变化时也重新 fit
      window.addEventListener('resize', fitView);
      container.addEventListener('wheel', function(e) {
        e.preventDefault();
        var factor = e.deltaY > 0 ? 0.9 : 1.1;
        var rect = container.getBoundingClientRect();
        zoomBy(factor, e.clientX - rect.left, e.clientY - rect.top);
      }, { passive: false });
      container.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;
        if (e.target.closest('.annotation-marker, [data-edge-tooltip], .edgeLabel, .node')) return;
        dragging = true; startX = e.clientX - tx; startY = e.clientY - ty;
        e.preventDefault();
      });
      window.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        tx = e.clientX - startX; ty = e.clientY - startY;
        applyTransform();
      });
      window.addEventListener('mouseup', function() { dragging = false; });
      svg.querySelectorAll('.annotation-marker').forEach(function(marker) {
        marker.addEventListener('click', function(e) {
          e.stopPropagation();
          var t = marker.querySelector('text, tspan');
          var numText = t ? t.textContent.trim() : '';
          var data = annMap[numText];
          if (!data) return;
          document.getElementById('ann-title').textContent = data.title || '';
          document.getElementById('ann-content').textContent = data.content || '';
          var catEl = document.getElementById('ann-cat');
          catEl.innerHTML = data.category ? '<span class="annotation-panel-cat">' + data.category + '</span>' : '';
          annPanel.classList.add('visible');
          var rect = container.getBoundingClientRect();
          var mx = e.clientX - rect.left + 12, my = e.clientY - rect.top + 12;
          annPanel.style.left = mx + 'px'; annPanel.style.top = my + 'px';
          setTimeout(function() {
            var pr = annPanel.getBoundingClientRect();
            if (pr.right > rect.right) annPanel.style.left = (mx - pr.width - 24) + 'px';
            if (pr.bottom > rect.bottom) annPanel.style.top = (my - pr.height - 24) + 'px';
          }, 0);
        });
      });
      document.addEventListener('click', function(e) {
        if (!e.target.closest('.annotation-marker, #annotation-panel')) annPanel.classList.remove('visible');
      });
      function showTooltip(e, txt) {
        tooltip.textContent = txt;
        tooltip.classList.add('visible');
        var rect = container.getBoundingClientRect();
        tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
        tooltip.style.top = (e.clientY - rect.top + 12) + 'px';
      }
      function hideTooltip() { tooltip.classList.remove('visible'); }
      // 当前高亮的边（点击切换）
      var _activeEdge = null;
      function highlightEdge(pathEl) {
        pathEl._origStroke = pathEl._origStroke || pathEl.style.stroke || '';
        pathEl._origStrokeWidth = pathEl._origStrokeWidth || pathEl.style.strokeWidth || '';
        pathEl._origFilter = pathEl._origFilter || pathEl.style.filter || '';
        // [v41 修复] 保持原色, 不覆盖 stroke, 仅加粗 + halo
        pathEl.style.strokeWidth = '3px';
        pathEl.style.filter = 'drop-shadow(0 0 5px rgba(0,0,0,0.6))';
      }
      function unhighlightEdge(pathEl) {
        pathEl.style.stroke = pathEl._origStroke || '';
        pathEl.style.strokeWidth = pathEl._origStrokeWidth || '';
        pathEl.style.filter = pathEl._origFilter || '';
      }
      // 边 path 交互：hover + 点击切换高亮
      svg.querySelectorAll('[data-edge-tooltip]').forEach(function(el) {
        if (el.tagName.toLowerCase() === 'path') {
          el.style.cursor = 'help';
          el._origStroke = el.style.stroke || '';
          el._origStrokeWidth = el.style.strokeWidth || '';
          el._origFilter = el.style.filter || '';
          el.addEventListener('mouseenter', function(e) {
            if (el !== _activeEdge) highlightEdge(el);
            var k = el.getAttribute('data-edge-tooltip');
            if (ttMap[k]) showTooltip(e, ttMap[k]);
          });
          el.addEventListener('mousemove', function(e) {
            var k = el.getAttribute('data-edge-tooltip');
            if (ttMap[k]) showTooltip(e, ttMap[k]);
          });
          el.addEventListener('mouseleave', function() {
            if (el !== _activeEdge) unhighlightEdge(el);
            hideTooltip();
          });
          el.addEventListener('click', function(e) {
            e.stopPropagation();
            if (_activeEdge === el) {
              unhighlightEdge(el);
              _activeEdge = null;
            } else {
              if (_activeEdge) unhighlightEdge(_activeEdge);
              highlightEdge(el);
              _activeEdge = el;
            }
          });
        }
      });
      // edgeLabel 交互：hover tooltip + 点击高亮对应 path
      var _idToPath = {};
      svg.querySelectorAll('path[id]').forEach(function(p) { _idToPath[p.id] = p; });
      svg.querySelectorAll('.edgeLabel').forEach(function(labelEl) {
        var labelDataId = (labelEl.querySelector('[data-id]') || labelEl).getAttribute('data-id') || '';
        var ttKey = labelEl.getAttribute('data-edge-tooltip');
        var linkedPath = _idToPath[labelDataId] || null;
        if (!ttKey && !linkedPath) return;
        labelEl.style.cursor = 'pointer';
        labelEl.addEventListener('mouseenter', function(e) {
          if (linkedPath && linkedPath !== _activeEdge) highlightEdge(linkedPath);
          if (ttKey && ttMap[ttKey]) showTooltip(e, ttMap[ttKey]);
        });
        labelEl.addEventListener('mousemove', function(e) {
          if (ttKey && ttMap[ttKey]) showTooltip(e, ttMap[ttKey]);
        });
        labelEl.addEventListener('mouseleave', function() {
          if (linkedPath && linkedPath !== _activeEdge) unhighlightEdge(linkedPath);
          hideTooltip();
        });
        labelEl.addEventListener('click', function(e) {
          e.stopPropagation();
          if (!linkedPath) return;
          if (_activeEdge === linkedPath) {
            unhighlightEdge(linkedPath);
            _activeEdge = null;
          } else {
            if (_activeEdge) unhighlightEdge(_activeEdge);
            highlightEdge(linkedPath);
            _activeEdge = linkedPath;
          }
        });
      });
      // 点击空白取消高亮
      document.addEventListener('click', function() {
        if (_activeEdge) { unhighlightEdge(_activeEdge); _activeEdge = null; }
      });
      svg.querySelectorAll('.node').forEach(function(nodeEl) {
        nodeEl.classList.add('hover-target');
        nodeEl.addEventListener('mouseenter', function() { nodeEl.classList.add('hover-active'); });
        nodeEl.addEventListener('mouseleave', function() { nodeEl.classList.remove('hover-active'); });
      });
      // Annotation dock 折叠/展开
      var dockHeader = document.getElementById('ann-dock-header');
      var dockList = document.getElementById('ann-dock-list');
      var dockEl = document.querySelector('.annotation-dock');
      if (dockHeader && dockList && dockEl) {
        var dockCollapsed = false;
        var savedScrollTop = 0;
        dockHeader.addEventListener('click', function() {
          // [v41 修复] 收起前保存滚动位置, 展开后恢复
          if (!dockCollapsed) {
            savedScrollTop = dockEl.scrollTop;
          }
          dockCollapsed = !dockCollapsed;
          dockList.style.display = dockCollapsed ? 'none' : 'block';
          dockHeader.textContent = dockCollapsed
            ? '\u5907\u6ce8 (' + Object.keys(annMap).length + ') \u25B6'
            : '\u5907\u6ce8 (' + Object.keys(annMap).length + ')';
          if (!dockCollapsed) {
            // 展开后恢复滚动位置
            requestAnimationFrame(function() {
              dockEl.scrollTop = savedScrollTop;
            });
          }
        });
      }
      // [v41 修复] Annotation 点击高亮 - 保持原色 + 加粗 + halo，不覆盖 fill
      var _annHighlighted = null;
      function clearAnnHighlight() {
        if (!_annHighlighted) return;
        if (_annHighlighted.tagName && _annHighlighted.tagName.toLowerCase() === 'path') {
          _annHighlighted.style.stroke = _annHighlighted._origStroke || '';
          _annHighlighted.style.strokeWidth = _annHighlighted._origStrokeWidth || '';
          _annHighlighted.style.filter = _annHighlighted._origFilter || '';
        } else {
          var rect = _annHighlighted.querySelector('rect, polygon');
          if (rect) rect.style.filter = _annHighlighted._origFilter || '';
          var strokeEl = _annHighlighted.querySelector('rect, polygon');
          if (strokeEl && _annHighlighted._origStrokeWidth) {
            strokeEl.style.strokeWidth = _annHighlighted._origStrokeWidth;
          }
        }
        _annHighlighted.classList.remove('annotation-highlighted');
        _annHighlighted = null;
      }
      function annHighlightNode(el) {
        clearAnnHighlight();
        _annHighlighted = el;
        el.classList.add('annotation-highlighted');
        var rect = el.querySelector('rect, polygon');
        if (rect) {
          _annHighlighted._origFilter = rect.style.filter || '';
          // 保持原色, 仅加 halo + 粗描边
          rect.style.filter = 'drop-shadow(0 0 8px rgba(0,0,0,0.5))';
          _annHighlighted._origStrokeWidth = rect.style.strokeWidth || '';
          rect.style.strokeWidth = '3px';
        }
      }
      function annHighlightContainer(el) {
        clearAnnHighlight();
        _annHighlighted = el;
        el.classList.add('annotation-highlighted');
        var rect = el.querySelector('rect');
        if (rect) {
          _annHighlighted._origFilter = rect.style.filter || '';
          rect.style.filter = 'drop-shadow(0 0 8px rgba(0,0,0,0.5))';
          _annHighlighted._origStrokeWidth = rect.style.strokeWidth || '';
          rect.style.strokeWidth = '3px';
        }
      }
      function annHighlightRelation(targetId, relationCode) {
        clearAnnHighlight();
        var edgeLabelG = svg.querySelector('[data-link-code="' + targetId + '"]');
        if (!edgeLabelG && relationCode) {
          edgeLabelG = svg.querySelector('[data-relation-code="' + relationCode + '"]');
        }
        if (!edgeLabelG) {
          svg.querySelectorAll('.edgeLabel').forEach(function(label) {
            if (edgeLabelG) return;
            var text = label.textContent || '';
            if (text.includes(targetId) || (relationCode && text.includes(relationCode))) edgeLabelG = label.closest('g') || label;
          });
        }
        if (!edgeLabelG) return;
        var targetPath = null;
        var labelDataId = (edgeLabelG.querySelector('[data-id]') || edgeLabelG).getAttribute('data-id') || '';
        if (labelDataId && _idToPath[labelDataId]) {
          targetPath = _idToPath[labelDataId];
        }
        if (!targetPath) {
          targetPath = edgeLabelG.querySelector('path');
        }
        if (targetPath && targetPath.tagName && targetPath.tagName.toLowerCase() === 'path') {
          // 保持原色, 只加粗 + halo
          targetPath._origStroke = targetPath._origStroke || targetPath.style.stroke || '';
          targetPath._origStrokeWidth = targetPath._origStrokeWidth || targetPath.style.strokeWidth || '';
          targetPath._origFilter = targetPath._origFilter || targetPath.style.filter || '';
          targetPath.style.strokeWidth = '3px';
          targetPath.style.filter = 'drop-shadow(0 0 6px rgba(0,0,0,0.6))';
          _annHighlighted = targetPath;
        } else {
          _annHighlighted = edgeLabelG;
          edgeLabelG.classList.add('annotation-highlighted');
        }
      }
      document.querySelectorAll('.annotation-dock-item').forEach(function(item) {
        // [v41 修复] 单击同时触发: 高亮 + 居中
        item.addEventListener('click', function() {
          var annKey = item.getAttribute('data-ann');
          var annData = annMap[annKey];
          if (!annData) return;
          var targetType = annData.targetType;
          var targetId = annData.targetId;
          var relCode = annData.relationCode || '';
          // 1) 查找目标元素
          var targetEl = null;
          if (targetType === 'node') {
            targetEl = svg.querySelector('[data-code="' + targetId + '"]');
            if (!targetEl) {
              svg.querySelectorAll('.node').forEach(function(n) {
                if (targetEl) return;
                var label = n.querySelector('.nodeLabel');
                if (label && label.textContent.includes(targetId)) targetEl = n;
              });
            }
          } else if (targetType === 'container') {
            targetEl = svg.querySelector('[data-container-code="' + targetId + '"]');
            if (!targetEl) {
              svg.querySelectorAll('.subgraph, .cluster').forEach(function(c) {
                if (targetEl) return;
                var label = c.querySelector('.cluster-label, text');
                if (label && label.textContent.includes(targetId)) targetEl = c;
              });
            }
          } else if (targetType === 'relation') {
            targetEl = svg.querySelector('[data-link-code="' + targetId + '"]');
            if (!targetEl && relCode) {
              targetEl = svg.querySelector('[data-relation-code="' + relCode + '"]');
            }
            if (!targetEl) {
              svg.querySelectorAll('.edgeLabel').forEach(function(label) {
                if (targetEl) return;
                var text = label.textContent || '';
                if (text.includes(targetId) || (relCode && text.includes(relCode))) targetEl = label.closest('g') || label;
              });
            }
          }
          // 2) 触发高亮
          if (targetType === 'node') {
            annHighlightNode(targetEl);
          } else if (targetType === 'container') {
            annHighlightContainer(targetEl);
          } else if (targetType === 'relation') {
            annHighlightRelation(targetId, relCode);
          }
          // 3) 居中目标元素
          if (targetEl) {
            var bbox = null;
            try { bbox = targetEl.getBBox(); } catch(e) {}
            if (bbox && (bbox.width > 0 || bbox.height > 0)) {
              var ctm = null;
              try { ctm = targetEl.getCTM(); } catch(e) {}
              if (ctm) {
                var localCx = bbox.x + bbox.width / 2;
                var localCy = bbox.y + bbox.height / 2;
                var svgCx = ctm.a * localCx + ctm.c * localCy + ctm.e;
                var svgCy = ctm.b * localCx + ctm.d * localCy + ctm.f;
                var cw = container.clientWidth, ch = container.clientHeight;
                tx = cw / 2 - svgCx * scale;
                ty = ch * 0.38 - svgCy * scale;
                applyTransform();
              }
            }
          }
          // 4) 切换选中样式
          document.querySelectorAll('.annotation-dock-item').forEach(function(i) { i.style.background = ''; });
          item.style.background = 'rgba(0,0,0,0.05)';
        });
      });
    })();
  <\/script>
<\/body>
<\/html>`
        const blob = new Blob([htmlContent], { type: 'text/html' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `diagram-${Date.now()}.html`
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
        const annotationConfigFull = props.annotationConfig || {}
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
        const overallDirection = effectiveLayoutControlConfig.value?.overallDirection || 'TB'
        const isElk = props.layoutEngine === 'elk'

        const config = {
          startOnLoad: false,
          securityLevel: 'loose',
          maxTextSize: 1000000000,
          // [V007.62] maxEdges 是 top-level secure config, 必须在 mermaid.initialize 设置
          maxEdges: 10000,
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

    // 关键修复 v27：在 import 之后立即同步调用 mermaid.initialize 设置 startOnLoad: false
    // 防止 DOMContentLoaded 时 mermaid 用默认 maxTextSize=50000 自动渲染
    // （module script 同步部分在 DOMContentLoaded 之前执行，但 initPromise.then 是异步的，晚于 DOMContentLoaded）
    mermaid.initialize({ startOnLoad: false, maxTextSize: ${config.maxTextSize}, maxEdges: ${config.maxEdges || 10000} });

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
    const maxScale = 10;
    
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
        if (Math.abs(newScale - scale) < 1e-6) return;

        // [修复 2026-06-29] 以视口中心为缩放中心
        // 之前: 只改 scale, transform-origin: top left → 缩放中心在 SVG 左上角, 越缩放图越跑向右下
        // 现在: 缩放时让视口中心对应的 SVG 内容点保持不动
        //   数学: contentPoint = (viewportCenter - translate) / scale
        //         缩放后 translate = viewportCenter - contentPoint * newScale
        const cx = window.innerWidth / 2;
        const cy = window.innerHeight / 2;
        const contentX = (cx - translateX) / scale;
        const contentY = (cy - translateY) / scale;
        translateX = cx - contentX * newScale;
        translateY = cy - contentY * newScale;
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
      try { console.log('[mermaid-debug] maxTextSize生效:', mermaid.getConfig().maxTextSize, 'mermaidCode.length:', ${mermaidCode.length}); } catch(e) { console.log('[mermaid-debug] getConfig失败:', e); }
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
      const annotationConfigPdf = props.annotationConfig || {}
      const centerScopeHighlightPdf = annotationConfigPdf.centerScopeHighlight !== false
      const colorLegendDataPdf = (props.diagramType === 'serviceModule' || props.diagramType === 'businessObject')
        ? svgProcessor.buildColorLegendData(props.diagramData, nodeColorMappings, centerScopeHighlightPdf)
        : []

      showToast('正在生成 PDF，请稍候...')

      // [v42 高清方案] 优先 svg2pdf.js 矢量输出 (清晰度无限)
      //   兜底: PNG raster 路径 (旧实现, 兼容)
      try {
        // 等待中文字体就绪 (svg2pdf.js 用浏览器已加载字体的字形数据)
        if (document.fonts && document.fonts.ready) {
          try {
            await Promise.race([
              document.fonts.ready,
              new Promise((resolve) => setTimeout(resolve, 2000))
            ])
            // 主动加载 Microsoft YaHei / PingFang SC / 系统中文字体
            const cnFontFamilies = ['"Microsoft YaHei"', '"微软雅黑"', '"PingFang SC"', '"SimHei"', '"SimSun"', 'sans-serif']
            for (const ff of cnFontFamilies) {
              try { await document.fonts.load('14px ' + ff) } catch (e) { /* 忽略 */ }
            }
          } catch (e) { /* 字体加载失败不影响后续 */ }
        }
      } catch (e) { /* document.fonts 不可用, 继续 */ }

      try {
        // ============================================================
        // [v44 高清方案] html2canvas 整段渲染 legend + svg, 输出 PNG
        //   1) legend 走 HTML 渲染 (浏览器原生中文字体, 不乱码)
        //   2) svg 走 SVG → Image → canvas (不污染, 毫秒级)
        //   3) canvas 高分 (scale=3, 输出 ≈ 12000px wide) → A2 PDF 极清晰
        //   4) 拒绝 svg2pdf (它对 ELK 大 viewBox 处理差, 且图例中文乱码)
        // ============================================================

        // [v45] 高清方案 - scale 由 viewBox 自动计算, 详见下面
        // const scale = 2  // [已弃用] 现在根据 viewBox 自动算 scale
        const padding = 30

        // 获取 SVG 实际尺寸
        // [v45 修复] ELK 模式 viewBox 通常超大 (如 8000x4000), 直接用会爆内存
        //   方案: viewBox 保留, 但 scale 与 A2 PDF 页面尺寸匹配
        //   A2 横版 1684pt ≈ 2240px @ 96dpi, 让最终 PNG ≈ 6000-8000px wide (3x over-sampling)
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

        // [v45 关键修复] 实际节点 bbox 通常比 viewBox 小很多
        //   遍历 SVG 内所有节点元素, 算出紧凑 bbox, 替换 viewBox 让 SVG 紧凑
        //   8000x4000 viewBox 但实际内容在 (100, 100, 2000, 1500) → 替换为 2000x1500
        //   → PNG 渲染像素减 4x, 节点在 PDF 上反而看起来更大更清晰
        let tightViewBoxStr = null  // [v45] 紧凑 viewBox 字符串, 用于 clone
        try {
          // [v45 关键] 只查询节点和 cluster, 不包括 edge (edge bbox 可能横跨整图, 没意义)
          const contentEls = svgEl.querySelectorAll('.node, .cluster, .subgraph, foreignObject')
          if (contentEls.length > 0) {
            let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
            contentEls.forEach((el) => {
              try {
                const bb = el.getBBox()
                if (bb && bb.width > 0 && bb.height > 0) {
                  minX = Math.min(minX, bb.x)
                  minY = Math.min(minY, bb.y)
                  maxX = Math.max(maxX, bb.x + bb.width)
                  maxY = Math.max(maxY, bb.y + bb.height)
                }
              } catch (e) { /* 忽略 */ }
            })
            if (minX !== Infinity && maxX > minX && maxY > minY) {
              // [v45 调试] 输出 bbox 信息, 验证紧凑 viewBox 计算正确
              console.log('[v45 DEBUG] 节点 bbox 范围:',
                'x:', minX.toFixed(0), '~', maxX.toFixed(0),
                '| y:', minY.toFixed(0), '~', maxY.toFixed(0),
                '| 尺寸:', (maxX - minX).toFixed(0), 'x', (maxY - minY).toFixed(0),
                '| 原 viewBox:', exportSvgWidth, 'x', exportSvgHeight,
                '| 节点数:', contentEls.length)
              // 留 2% 边距 (v45 缩小 padding, 节点在 PDF 上更大)
              const padX = (maxX - minX) * 0.02
              const padY = (maxY - minY) * 0.02
              const tightW = maxX - minX + padX * 2
              const tightH = maxY - minY + padY * 2
              const tightX = minX - padX
              const tightY = minY - padY
              // 只要新尺寸 < 原尺寸 95% 就替换 (v45 几乎总是替换)
              if (tightW * tightH < exportSvgWidth * exportSvgHeight * 0.95) {
                console.log('[v45] 紧凑 viewBox: 原', exportSvgWidth, 'x', exportSvgHeight,
                  '→ 新', tightW.toFixed(0), 'x', tightH.toFixed(0),
                  '| 节省', ((1 - tightW * tightH / (exportSvgWidth * exportSvgHeight)) * 100).toFixed(1) + '%')
                // 用局部变量记录紧凑尺寸, 后续 clone 时再用 setAttribute 改 viewBox
                exportSvgWidth = tightW
                exportSvgHeight = tightH
                // 暂存紧凑 viewBox 元数据, 下面 clone 时使用 (通过函数返回值传递)
                // 注: 不直接改 svgEl viewBox (避免污染用户视图)
                tightViewBoxStr = `${tightX} ${tightY} ${tightW} ${tightH}`
              }
            }
          }
        } catch (e) { console.warn('[v45] 紧凑 viewBox 计算失败:', e) }

        // [v47 强制放大节点] 根因: 节点 viewBox 200 / 总 viewBox 86000 = 0.23% 占比
        //   无论 PNG/PDF 怎么缩放, 节点在 PDF 视觉永远是 1684pt × 0.23% = 3.87pt → 文字 0.7pt 不可读
        //   强制把 viewBox 数字缩小 2x (元素坐标不变), 让节点在 viewBox 中占比提升 2x
        //   元素坐标不变, 只缩小 viewBox 数字 → 保留完整 viewBox 范围, 不裁剪
        //   节点 200/43000 = 0.46% → PDF 7.7pt (文字 14pt → 1.4pt)
        //   + 字体放大 20% (14pt → 16.8pt) → 文字 1.4 × 1.2 = 1.68pt
        //   综合提升 2.4x 可读性
        if (tightViewBoxStr && exportSvgWidth > 30000) {
          const parts = tightViewBoxStr.split(/\s+/).map(parseFloat)
          if (parts.length === 4) {
            const SCALE = 2  // viewBox 缩小 2x
            const newW = parts[2] / SCALE
            const newH = parts[3] / SCALE
            // [v47 不裁剪] 保持 viewBox 中心, 但 X/Y 偏移到原位置/SCALE
            //   原 viewBox "x y w h" → 缩小后应该是 "x/2 y/2 w/2 h/2"
            //   这样元素坐标不变, viewBox 数字减半, SVG 渲染时元素在 viewBox 中占比翻倍
            const newX = parts[0] / SCALE
            const newY = parts[1] / SCALE
            console.log('[v47 强制放大] 原 viewBox:', parts[2].toFixed(0), 'x', parts[3].toFixed(0),
              '→ 新 viewBox:', newW.toFixed(0), 'x', newH.toFixed(0),
              '| 节点相对占比: 0.23% → 0.46% (2x)',
              '| PDF 节点视觉尺寸: 3.87pt → 7.7pt',
              '| 字体 +20%: 14pt → 16.8pt')
            exportSvgWidth = newW
            exportSvgHeight = newH
            tightViewBoxStr = `${newX} ${newY} ${newW} ${newH}`
          }
        }

        // [v45 修复] 计算合适的 renderScale: 让最终 PNG 宽度 ≈ 8000-12000px (适配 A2)
        //   8000 → 1684pt PDF: 4.75x 缩放, 高清
        //   12000 → 1684pt PDF: 7.1x 缩放, 极清
        const TARGET_PNG_WIDTH = 10000  // 目标 PNG 宽度
        const autoScale = Math.min(2, TARGET_PNG_WIDTH / Math.max(exportSvgWidth, 1))
        const finalScale = Math.max(0.5, autoScale)
        console.log('[v45] viewBox:', exportSvgWidth, 'x', exportSvgHeight,
          '| autoScale:', autoScale.toFixed(3),
          '| 最终 PNG 尺寸:', (exportSvgWidth * finalScale).toFixed(0), 'x', (exportSvgHeight * finalScale).toFixed(0))
        // 用 finalScale 作为后续的 scale (在函数作用域)
        const scale = finalScale

        // 构造统一容器: legend (HTML) + SVG (克隆副本)
        const pdfWrapper = document.createElement('div')
        pdfWrapper.id = '__mermaid_pdf_wrapper__'
        pdfWrapper.style.cssText = [
          'position: fixed',
          'left: -99999px',
          'top: 0',
          'background: #ffffff',
          'padding: ' + padding + 'px',
          'box-sizing: border-box',
          'width: ' + (exportSvgWidth + padding * 2) + 'px',
          'font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", "Helvetica Neue", Arial, sans-serif',
          'color: #222'
        ].join(';')

        // 1. legend (可选)
        if (colorLegendDataPdf.length > 0) {
          const legendTitle = document.createElement('div')
          legendTitle.textContent = '图例'
          legendTitle.style.cssText = 'font-size: 36px; font-weight: bold; margin-bottom: 20px; color: #333;'
          pdfWrapper.appendChild(legendTitle)

          const legendGrid = document.createElement('div')
          legendGrid.style.cssText = 'display: flex; flex-wrap: wrap; gap: 16px 32px; margin-bottom: 24px;'
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
          pdfWrapper.appendChild(legendGrid)
        }

        // 2. [十轮核心] SVG → Image 路径（不走 html2canvas, 避免 DOM 遍历卡死）
        const svgCloneForExport = svgEl.cloneNode(true)
        if (!svgCloneForExport.getAttribute('xmlns')) {
          svgCloneForExport.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
        }
        // [v45] 用紧凑 viewBox 替换, 提升 PDF 清晰度 (节点占更大比例)
        if (tightViewBoxStr) {
          svgCloneForExport.setAttribute('viewBox', tightViewBoxStr)
        }
        svgCloneForExport.setAttribute('width', String(exportSvgWidth))
        svgCloneForExport.setAttribute('height', String(exportSvgHeight))

        // [v47 字体放大 20%] 同步放大 svgClone 内 text 元素的 font-size
        //   viewBox 缩 2x 让节点视觉 2x, 但 text 元素 font-size 是绝对值
        //   必须主动放大 font-size 1.2x, 让文字可读性提升 2.4x (2x viewBox × 1.2x font)
        const FONT_BOOST = 1.2
        svgCloneForExport.querySelectorAll('text').forEach((t) => {
          const curSize = parseFloat(t.getAttribute('font-size') || t.style.fontSize || '14')
          if (!isNaN(curSize) && curSize > 0) {
            t.setAttribute('font-size', String(curSize * FONT_BOOST))
            if (t.style.fontSize) t.style.fontSize = String(curSize * FONT_BOOST)
          }
        })
        // 同步放大 foreignObject 内 html font-size
        svgCloneForExport.querySelectorAll('foreignObject *').forEach((el) => {
          const curSize = parseFloat(el.style.fontSize || '14')
          if (!isNaN(curSize) && curSize > 0) {
            el.style.fontSize = (curSize * FONT_BOOST) + 'px'
          }
        })

        // foreignObject → text 转换 (六轮已验证)
        const foreignObjects = svgCloneForExport.querySelectorAll('foreignObject')
        foreignObjects.forEach((fo) => {
          const textContent = (fo.textContent || '').replace(/\s+/g, ' ').trim()
          if (!textContent) {
            fo.remove()
            return
          }
          const x = parseFloat(fo.getAttribute('x') || '0')
          const y = parseFloat(fo.getAttribute('y') || '0')
          const w = parseFloat(fo.getAttribute('width') || '100')
          const h = parseFloat(fo.getAttribute('height') || '20')
          const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text')
          textEl.setAttribute('x', String(x + w / 2))
          textEl.setAttribute('y', String(y + h / 2 + 5))
          textEl.setAttribute('text-anchor', 'middle')
          textEl.setAttribute('font-size', '12')
          textEl.setAttribute('font-family', 'Microsoft YaHei, sans-serif')
          textEl.setAttribute('fill', '#333')
          const lines = textContent.split(/\n/).filter(l => l.trim())
          if (lines.length === 1) {
            textEl.textContent = lines[0]
          } else {
            lines.forEach((line, i) => {
              const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan')
              tspan.setAttribute('x', String(x + w / 2))
              tspan.setAttribute('dy', i === 0 ? '0' : '1.2em')
              tspan.textContent = line
              textEl.appendChild(tspan)
            })
          }
          fo.replaceWith(textEl)
        })

        // [十轮新增] 移除所有 <style> 块（canvas tainted 的真正污染源）
        const styleEls = svgCloneForExport.querySelectorAll('style')
        let styleRemovedCount = 0
        styleEls.forEach((s) => { s.remove(); styleRemovedCount++ })
        console.log('[BUG-V034 十轮诊断] 移除 <style> 块:', styleRemovedCount, '个')

        // 大图降级 (避免 SVG viewBox × scale 后 canvas 像素爆炸)
        // [v45] 不再过度降级 - 让 SVG 接近 1:1 渲染, 保留细节
        //   提升 MAX_CANVAS_PIXELS 到 400M (~1.6GB 内存), 接受更大 canvas
        //   8000×4000 SVG @ scale=2 → 16000×8000 = 128M 像素, 512MB 内存, OK
        //   10000×5000 SVG @ scale=2 → 20000×10000 = 200M 像素, 800MB 内存, OK
        const MAX_SVG_DIMENSION = 16000
        const MAX_CANVAS_PIXELS = 400_000_000  // 400M 像素 (1.6GB RGBA), 高清优先
        let renderScale = scale
        const scaledW = exportSvgWidth * scale
        const scaledH = exportSvgHeight * scale
        if (scaledW > MAX_SVG_DIMENSION || scaledH > MAX_SVG_DIMENSION) {
          renderScale = Math.min(MAX_SVG_DIMENSION / exportSvgWidth, MAX_SVG_DIMENSION / exportSvgHeight)
        }
        // 双重保护: canvas 总像素超 400M 时再降级
        if (exportSvgWidth * renderScale * exportSvgHeight * renderScale > MAX_CANVAS_PIXELS) {
          const pixelRatio = Math.sqrt(MAX_CANVAS_PIXELS / (exportSvgWidth * exportSvgHeight))
          renderScale = Math.min(renderScale, pixelRatio)
        }
        if (renderScale !== scale) {
          console.log('[v45] SVG renderScale=', scale, '→', renderScale.toFixed(3),
            '| 原 viewBox:', exportSvgWidth, 'x', exportSvgHeight,
            '| 渲染像素:', (exportSvgWidth * renderScale).toFixed(0), 'x', (exportSvgHeight * renderScale).toFixed(0))
        }

        let finalCanvas
        // [BUG-V034 九轮修复] 用 html2canvas 整段渲染
          //   foreignObjectRendering: true → 让 html2canvas 自己序列化 foreignObject (不会污染)
          //   allowTaint: false → 拒绝跨域图片 (避免 canvas 被污染)
          //   useCORS: true → 尝试 CORS 加载
          //   onclone: 把原 SVG 的 <style> 块注入到克隆节点, 恢复节点颜色
          //             (html2canvas 默认不解析 SVG <style> 块, 节点会丢失 fill/stroke)
          // [BUG-V034 十轮核心] SVG → Image 走 SVG 渲染管线（毫秒级，不卡）
          const svgString = new XMLSerializer().serializeToString(svgCloneForExport)
          const svgDataUrl = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgString)

          const svgImg = new Image()
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

          const svgWidth = svgImg.naturalWidth || exportSvgWidth || 800
          const svgHeight = svgImg.naturalHeight || exportSvgHeight || 600

          // Legend → Canvas (html2canvas 仅渲染 legend, 简单 DOM 不卡)
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
              'width: ' + (svgWidth * renderScale + padding * 2) + 'px',
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
                scale: 1,
                logging: false,
                useCORS: true
              })
            } finally {
              document.body.removeChild(legendWrapper)
            }
          }

          // 合成 final canvas（白底 + legend + SVG）
          const finalWidth = Math.max(
            legendCanvas ? legendCanvas.width : 0,
            svgWidth * renderScale + padding * 2 * renderScale
          )
          const legendHeightPx = legendCanvas ? legendCanvas.height : 0
          const finalHeight = legendHeightPx + svgHeight * renderScale + padding * renderScale

          finalCanvas = document.createElement('canvas')
          finalCanvas.width = finalWidth
          finalCanvas.height = finalHeight
          const ctx = finalCanvas.getContext('2d')
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(0, 0, finalCanvas.width, finalCanvas.height)

          if (legendCanvas) {
            ctx.drawImage(legendCanvas, 0, 0)
          }
          const svgDrawY = legendHeightPx + padding * renderScale
          const svgDrawX = padding * renderScale
          ctx.drawImage(svgImg, svgDrawX, svgDrawY, svgWidth * renderScale, svgHeight * renderScale)

        // ============================================================
        // 4. A4 横版 PDF
        // ============================================================
        // [v44] A2 横版 (1684 x 1190 pt ≈ 23.4 x 16.5 inch)
        //   比 A4 大 4 倍面积, 高 scale=3 PNG 嵌入后极清晰
        const pdf = new jsPDF({
          orientation: 'landscape',
          unit: 'pt',
          format: 'a2'
        })
        const pageWidthPt = pdf.internal.pageSize.getWidth()   // ~1684
        const pageHeightPt = pdf.internal.pageSize.getHeight()  // ~1190
        const marginPt = 30

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
        // [BUG-V034 九轮修复 2026-06-29] finalCanvas 来源说明
        //   finalCanvas 现在直接来自 html2canvas(pdfWrapper) 的输出
        //   html2canvas 走 DOM→canvas 路径, 完全绕开 SVG→Image→canvas 污染链
        //   → toDataURL 应正常返回 PNG data URL (前 23 字符 "data:image/png;base64,")
        // [v48 优化文件大小] 用 JPEG 95% 质量 替代 PNG
        //   PNG 无损但体积大 (8000x4821 ≈ 5-10MB)
        //   JPEG 95% 视觉无损, 体积减小 60-80% (1-2MB)
        //   addImage 接受 'JPEG' 格式, jsPDF 4.x 完美支持
        console.log('[BUG-V034 九轮诊断] finalCanvas 尺寸:', finalCanvas.width, 'x', finalCanvas.height)
        let imgData
        try {
          // [v48 优化] 白色背景填充 (避免 JPEG 透明区域变黑)
          //   不用 getImageData/putImageData (会分配 154MB 内存), 用 destination-over 复合
          const ctx = finalCanvas.getContext('2d')
          ctx.save()
          ctx.globalCompositeOperation = 'destination-over'
          ctx.fillStyle = '#ffffff'
          ctx.fillRect(0, 0, finalCanvas.width, finalCanvas.height)
          ctx.restore()
          // 转 JPEG 95% 质量
          imgData = finalCanvas.toDataURL('image/jpeg', 0.95)
          console.log('[v48] JPEG 95% 返回长度:', (imgData.length / 1024 / 1024).toFixed(2), 'MB (vs PNG 通常 5-10MB)')
        } catch (e) {
          console.error('[BUG-V034 九轮诊断] toDataURL 抛错:', e?.name, e?.message)
          throw e
        }
        pdf.addImage(imgData, 'JPEG', renderX, renderY, renderW, renderH)
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



