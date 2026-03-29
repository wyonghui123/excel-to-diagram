<template> 
  <div class="mermaid-container" :class="{ 'maximized': isMaximized }">
    <div class="toolbar">
      <button class="toolbar-btn" @click="resetAdaptive" title="重置视图">
        <span class="btn-icon">🔄</span>
      </button>
      <button class="toolbar-btn" @click="toggleMaximize" :title="isMaximized ? '退出全屏' : '全屏查看'">
        <span class="btn-icon">{{ isMaximized ? '⛶' : '⛶' }}</span>
      </button>
    </div>

    <div class="mermaid-wrapper" ref="mermaidWrapper">
      <div class="draggable-area" ref="draggableArea">
        <div class="diagram-canvas">
          <div ref="mermaidContainer" class="mermaid-content" :class="diagramType"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import mermaid from 'mermaid'

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

    const mermaidContainer = ref(null)
    const mermaidWrapper = ref(null)
    const draggableArea = ref(null)
    const isMaximized = ref(false)

    // 保存节点和连线的颜色映射，用于切换颜色分组时只更新颜�?
    let nodeColorMappings = []
    let linkColorMappings = []
    let lastColorGroupBy = 'domain'
    
    const toggleMaximize = () => {
      isMaximized.value = !isMaximized.value
    }

    // 生成Mermaid图表代码并保存关系说明信�?
    let relationDescriptions = []

    const serviceModuleSyntax = useServiceModuleSyntax()
    const businessObjectSyntax = useBusinessObjectSyntax()

    // 根据生成的内容类型，返回相应的Mermaid代码生成函数
    const generateMermaidCode = (data, layoutEngine, layoutType, positions = [], zoneRowCount = 3, preserveModelOrder = false, layoutControlConfig = null) => {
      console.log('[MermaidComponent] generateMermaidCode called:', {
        hasContainers: !!data?.containers,
        layoutEngine,
        layoutType,
        preserveModelOrder,
        layoutControlConfig,
        overallDirection: layoutControlConfig?.overallDirection
      })
      relationDescriptions = []

      if (data && data.containers) {
        console.log('[MermaidComponent] Calling serviceModuleSyntax.generateMermaidCode')
        return serviceModuleSyntax.generateMermaidCode(data, relationDescriptions, layoutEngine, layoutType, positions, zoneRowCount, preserveModelOrder, layoutControlConfig)
      } else {
        console.log('[MermaidComponent] Calling businessObjectSyntax.generateMermaidCode with layoutType:', layoutType)
        return businessObjectSyntax.generateMermaidCode(data, relationDescriptions, layoutEngine, layoutType, layoutControlConfig)
      }
    }

    // 渲染Mermaid图表
    const renderMermaid = async () => {
      if (mermaidContainer.value && props.diagramData) {
        let effectiveLayoutEngine = props.layoutEngine
        const positions = props.layoutPositions || []
        const zoneRowCount = props.zoneRowCount || 3
        
        console.log('[MermaidComponent] renderMermaid called with:', {
          layoutEngine: props.layoutEngine,
          layoutType: props.layoutType,
          preserveModelOrder: props.preserveModelOrder,
          layoutControlConfig: props.layoutControlConfig,
          overallDirection: props.layoutControlConfig?.overallDirection,
          effectiveLayoutEngine,
          positions,
          zoneRowCount
        })
        
        if (props.layoutEngine === 'elk') {
          const elkLoaded = await loadElkLayouts(true)
          if (!elkLoaded) {
            effectiveLayoutEngine = 'dagre'
            console.log('[MermaidComponent] ELK not available, fallback to dagre')
          } else {
            console.log('[MermaidComponent] ELK loaded successfully')
            initializeMermaid(props.diagramType, props.diagramData, 'elk', props.layoutType, props.preserveModelOrder)
            try {
              const mermaidCode = generateMermaidCode(props.diagramData, effectiveLayoutEngine, props.layoutType, positions, zoneRowCount, props.preserveModelOrder, props.layoutControlConfig)
              console.log('[MermaidComponent] Generated Mermaid code (first 500 chars):', mermaidCode.substring(0, 500))
              console.log('[MermaidComponent] Full Generated Mermaid code:', mermaidCode)
              mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
            } catch (e) {
              console.error('[MermaidComponent] Error generating mermaid code:', e)
            }
          }
        }
        
        if (effectiveLayoutEngine !== 'elk') {
          initializeMermaid(props.diagramType, props.diagramData, effectiveLayoutEngine, props.layoutType, props.preserveModelOrder)
          try {
            const mermaidCode = generateMermaidCode(props.diagramData, effectiveLayoutEngine, props.layoutType, positions, zoneRowCount, props.preserveModelOrder, props.layoutControlConfig)
            console.log('[MermaidComponent] Generated Mermaid code (first 500 chars):', mermaidCode.substring(0, 500))
            console.log('[MermaidComponent] Full Generated Mermaid code:', mermaidCode)
            mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
          } catch (e) {
            console.error('[MermaidComponent] Error generating mermaid code:', e)
          }
        }

        nextTick(() => {
          try {
            mermaid.run().then(() => {
              setTimeout(() => {
                const svgEl = mermaidContainer.value.querySelector('svg')
                if (svgEl) {
                  svgProcessor.processSvg(svgEl, props, relationDescriptions, mermaidContainer)

                  // 设置交互功能
                  interaction.addZoomAndPan(mermaidWrapper, mermaidContainer, draggableArea)

                  // 设置画布布局
                  svgProcessor.setupCanvasLayout(mermaidWrapper, mermaidContainer, draggableArea)

                  interaction.autoFitDiagram()

                  lastColorGroupBy = props.diagramData?.colorGroupBy || 'domain'
                  console.log('渲染完成')
                  
                  // 额外使用CSS样式注入，解决优先级样式问题
                  const styleId = 'mermaid-italic-style'
                  let styleEl = document.getElementById(styleId)
                  if (!styleEl) {
                    styleEl = document.createElement('style')
                    styleEl.id = styleId
                    document.head.appendChild(styleEl)
                  }
                  
                  const cssRules = `
                    /* 业务对象�?- edgeLabel 透明背景 */
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

                    /* 容器标签斜体 - 强制容器标题文字为斜�?包含tspan) */
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
                    }
                    
                    /* 模块斜体效果 - 使用CSS transform */
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
                      transform: skewX(-10deg) !important;
                      -webkit-transform: skewX(-10deg) !important;
                      transform-origin: left center !important;
                    }
                    
                    /* 强制 foreignObject 内部元素为斜�?*/
                    .mermaid-content.businessObject .subgraph foreignObject *,
                    .mermaid-content.serviceModule .cluster foreignObject *,
                    .mermaid-content.serviceModule .subgraph foreignObject * {
                      font-style: italic !important;
                      transform: skewX(-10deg) !important;
                      -webkit-transform: skewX(-10deg) !important;
                      transform-origin: left center !important;
                    }
                    
                    /* 补偿 skewX 导致的左边截�?*/
                    .mermaid-content.businessObject .subgraph foreignObject > div,
                    .mermaid-content.businessObject .subgraph foreignObject > span,
                    .mermaid-content.serviceModule .cluster foreignObject > div,
                    .mermaid-content.serviceModule .cluster foreignObject > span,
                    .mermaid-content.serviceModule .subgraph foreignObject > div,
                    .mermaid-content.serviceModule .subgraph foreignObject > span {
                      margin-left: 10px !important;
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
                      transform: none !important;
                      -webkit-transform: none !important;
                    }
                  `
                  styleEl.textContent = cssRules

                  setTimeout(() => {
                    const svgAgain = mermaidContainer.value.querySelector('svg')
                    if (svgAgain) {
                      svgStyle.applyContainerTitleItalic(svgAgain)
                    }
                  }, 800)
                }
              }, 300)
            }).catch((err) => {
              console.error('mermaid.run() 错误:', err)
            })
          } catch (err) {
            console.error('调用 mermaid.run() 时发生错�?', err)
          }
        })
      } else {
        console.warn('渲染条件不满�? mermaidContainer或diagramData为空')
      }
    }
    
    // 只在新增节点或连线时才重新渲染颜色，否则只更新图�?
    const updateColorsOnly = (newColorGroupBy) => {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) {
        return false
      }

      if (nodeColorMappings.length === 0 || linkColorMappings.length === 0) {
        return false
      }

      const currentColorGroupBy = props.diagramData?.colorGroupBy || 'domain'

      if (currentColorGroupBy === lastColorGroupBy) {
        return true
      }

      const data = props.diagramData
      const colorGroupBy = currentColorGroupBy

      const moduleGroups = new Map()
      const objectToModuleMap = dataMap.buildObjectToModuleMap(data)

      const centerSubDomain = data.centerSubDomain
      const centerDomain = data.centerDomain || centerSubDomain

      const centerDomainColor = data.centerDomainColor || colors.CENTER_DOMAIN_COLOR

      const colorMap = colors.buildColorMap(
        nodeColorMappings,
        objectToModuleMap,
        colorGroupBy,
        colors.getColorScheme(data.colorScheme),
        centerDomainColor,
        centerSubDomain,
        centerDomain
      )

      colors.updateNodeColors(svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap)
      colors.updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, centerSubDomain, centerDomain)

      lastColorGroupBy = currentColorGroupBy

      return true
    }

    // 监听数据变化 - 合并了原来的 diagramData watcher（行 596-613）和 layoutType/layoutEngine watcher
    watch(
      () => props.diagramData,
      (newVal, oldVal) => {
        if (!newVal) return

        console.log('[MermaidComponent] diagramData changed, rendering with layoutEngine:', props.layoutEngine, 'layoutType:', props.layoutType)

        // 判断是否只需要更新颜�?
        if (oldVal) {
          const newColorGroupBy = newVal?.colorGroupBy
          const oldColorGroupBy = oldVal?.colorGroupBy
          const nodesChanged = JSON.stringify(newVal.nodes) !== JSON.stringify(oldVal.nodes)
          const linksChanged = JSON.stringify(newVal.links) !== JSON.stringify(oldVal.links)

          // 如果节点和连线没变，只是颜色分组变化，则只更新颜�?
          if (!nodesChanged && !linksChanged && newColorGroupBy !== oldColorGroupBy) {
            const updated = updateColorsOnly(newColorGroupBy)
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
          console.log('[MermaidComponent] layoutType changed:', oldVal, '->', newVal)
          renderMermaid()
        }
      }
    )

    // 监听 layoutEngine 变化
    watch(
      () => props.layoutEngine,
      (newVal, oldVal) => {
        if (newVal !== oldVal && props.diagramData && mermaidContainer.value) {
          console.log('[MermaidComponent] layoutEngine changed:', oldVal, '->', newVal)
          renderMermaid()
        }
      }
    )

    // 监听 zoneRowCount 变化
    watch(
      () => props.zoneRowCount,
      (newVal, oldVal) => {
        if (newVal !== oldVal && props.diagramData && mermaidContainer.value) {
          console.log('[MermaidComponent] zoneRowCount changed:', oldVal, '->', newVal)
          renderMermaid()
        }
      }
    )

    // 组件挂载后初始化
    onMounted(() => {
      if (props.diagramData) {
        renderMermaid()
      }
    })

    // 导出为图�?
    const exportAsImage = () => {
      if (mermaidContainer.value) {
        console.log('Export Mermaid as image')
      }
    }

    // 导出为原生格�?
    const exportAsNative = () => {
      if (props.diagramData) {
        const mermaidCode = generateMermaidCode(props.diagramData)
        const blob = new Blob([mermaidCode], { type: 'text/plain' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `diagram-${Date.now()}.mmd`
        link.click()
      }
    }

    return {
      mermaidContainer,
      mermaidWrapper,
      draggableArea,
      isMaximized,
      toggleMaximize,
      resetAdaptive: interaction.resetAdaptive,
      autoFitDiagram: interaction.autoFitDiagram,
      exportAsImage,
      exportAsNative
    }
  }
}
</script>



