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

      <!-- [DBG 2026-08-08] 调试面板 toggle: 仅 ?mode=debug 时可见 -->
      <template v-if="debug.isDebug">
        <span class="toolbar-divider"></span>
        <div class="toolbar-group">
          <button class="toolbar-btn toolbar-btn--debug" @click="debug.debugPanelVisible = !debug.debugPanelVisible" title="调试面板">
            <span class="toolbar-btn-label">{{ debug.debugPanelVisible ? '关闭调试' : '调试面板' }}</span>
          </button>
        </div>
        <span class="toolbar-divider"></span>
        <!-- [OBS 2026-08-10] 状态真相面板入口: 仅 ?mode=debug 时可见, 避免污染正式工具栏 -->
        <div class="toolbar-group">
          <button class="toolbar-btn toolbar-btn--debug" @click="openTruthPanel" title="状态真相面板（调试模式可见）：store/chart/渲染树三份状态并排、差异高亮">
            <span class="toolbar-btn-label">真相</span>
          </button>
        </div>
      </template>
      
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

    <div class="mermaid-wrapper" ref="mermaidWrapper" @contextmenu.prevent="handleContextMenu" @dblclick.prevent="handleDblClick">
      <div class="draggable-area" ref="draggableArea">
        <div class="diagram-canvas">
          <div ref="mermaidContainer" class="mermaid-content" :class="[diagramType, { 'hide-tails': shouldHideTails }, { 'is-rendering': rendering }]"></div>
        </div>
      </div>
      <!-- [UX 2026-08-05] 渲染覆盖层: mermaid.run() 期间 SVG 元素堆叠在中心,
           显示转圈覆盖层 + 隐藏未完成 SVG, 渲染完成后淡入, 消除"堆叠中心"闪烁 -->
      <transition name="rendering-fade">
        <div v-if="rendering" class="mermaid-rendering-overlay">
          <el-icon class="mermaid-loading-icon" :size="28"><Loading /></el-icon>
          <span class="mermaid-loading-text">图表渲染中<span class="mermaid-loading-dots"><i></i><i></i><i></i></span></span>
        </div>
      </transition>
      <!-- [CTX 2026-08-07] 右键上下文菜单: 按分组类型展示折叠/展开选项 -->
      <div v-if="ctxMenu?.visible" class="mermaid-ctx-menu"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }">
        <div class="ctx-menu-header">{{ ctxMenu.groupTitle }}</div>
        <div class="ctx-menu-divider"></div>
        <div v-for="item in ctxMenu.items" :key="item.key"
          class="ctx-menu-item"
          @click="executeContextMenuAction(item.key)">{{ item.label }}</div>
      </div>

      <!-- [DBG 2026-08-08] 浮动调试面板: 仅 ?mode=debug 时可见 -->
      <div v-if="debug.isDebug && debug.debugPanelVisible" class="mermaid-debug-panel">
        <div class="debug-panel-header">
          <span>调试面板</span>
          <span class="debug-panel-close" @click="debug.debugPanelVisible = false">✕</span>
        </div>
        <div class="debug-panel-body">
          <div class="debug-section">
            <div class="debug-section-title">状态查看</div>
            <button class="debug-btn" @click="debugDump">📋 全量状态</button>
            <button class="debug-btn" @click="debugInspectGroups">📊 分组列表</button>
            <button class="debug-btn" @click="debugInspectRendering">🎨 渲染分组</button>
            <button class="debug-btn" @click="debugIdentifyCollapse">🔍 COLLAPSE 节点</button>
            <button class="debug-btn" @click="debugVerifyChart">✅ 一键自检 verifyChart</button>
          </div>
          <div class="debug-section">
            <div class="debug-section-title">交互模拟</div>
            <button class="debug-btn" @click="debugTestRightClick">🖱️ 模拟右键 (首个)</button>
            <button class="debug-btn" @click="debugTestDblClick">🖱️ 模拟双击 (首个)</button>
          </div>
          <div class="debug-section">
            <div class="debug-section-title">快速操作</div>
            <button class="debug-btn" @click="debugExpandSCP">🔽 展开 SCP 到服务模块</button>
            <button class="debug-btn" @click="debugCollapseSCP">🔼 折叠 SCP</button>
          </div>
          <div class="debug-panel-hint">
            打开 Console 查看详细输出 | 窗口可拖拽
          </div>
        </div>
      </div>

      <!-- [OBS 2026-08-10] 状态真相面板: 任意模式可用, 三份状态并排 + 差异高亮 + 一键自检 + 导出复现链接 -->
      <TruthPanel v-if="truthPanelVisible" @close="truthPanelVisible = false" />
    </div>
  </div>
</template>

<script>
import { ref, reactive, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue'
import mermaid from 'mermaid'
import { jsPDF } from 'jspdf'
// eslint-disable-next-line no-unused-vars -- svg2pdf.js 注册 jsPDF 的 .svg() 方法
import 'svg2pdf.js'
import html2canvas from 'html2canvas'
import { AppIcon } from './common/AppIcon'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useDiagramConfigStore } from '../stores/diagramConfigStore.js'

import { useMermaidConfig } from '../composables/useMermaid/config/useMermaidConfig.js'
import { installDiagnosticsToWindow, useDiagnostics } from '../composables/useMermaid/core/useDiagnostics.js'
import { useDebugMode } from '../composables/useDebugMode.js'
import { useInteraction } from '../composables/useMermaid/interaction/useInteraction.js'
import { useBusinessObjectSyntax, useServiceModuleSyntax } from '../composables/useMermaid/syntax/index.js'
import { useSvgStyle } from '../composables/useMermaid/style/index.js'
import { useTooltip, preloadEnums } from '../composables/useMermaid/tooltip/index.js'
import { useMermaidColors, createColorStateTracker } from '../composables/useMermaid/color/index.js'
import { useMermaidDataMap } from '../composables/useMermaid/dataMap/index.js'
import { remapLinksToVisibleAncestors } from '../composables/useMermaid/layouts/linkRemapper.js'
import { upliftNodeId } from '../composables/useMermaid/layouts/upliftDerivation.js'
import { useAnnotation, useAnnotationOverlay } from '../composables/useMermaid/annotation/index.js'
import { loadElkLayouts } from '../composables/useMermaid/renderer/useElkLoader.js'
import { useSvgProcessor } from '../composables/useMermaid/renderer/useSvgProcessor.js'
import { groupLevelOf, expandGroupsToLevel } from '../services/expandLevel.js'
import TruthPanel from './TruthPanel.vue'
import './MermaidComponent.css'

export default {
  name: 'MermaidComponent',
  components: {
    AppIcon,
    TruthPanel
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
    const debug = useDebugMode()
    // [OBS 2026-08-10] 状态真相面板可见性: 任意模式可用 (不依赖 ?mode=debug).
    //   面板独立组件 TruthPanel.vue, 直接读 window.__archPage.diag() 渲染三份状态.
    const truthPanelVisible = ref(false)
    const openTruthPanel = () => { truthPanelVisible.value = true }
    const diag = useDiagnostics()  // [FIX 2026-08-01] 渲染埋点 — chart_diag 一键读取耗时
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
        // [FIX 2026-08-04] 用户手动重命名的分组 (标记 _userRenamed) 不被 titleMap 还原，
        //   否则 groupControlTitleMap (原始数据名) 会把面板里的重命名标题覆盖掉。
        const matchedTitle = titleMap[group.id] || titleMap[group.elementCode] || titleMap[group.title]
        if (matchedTitle && !group._userRenamed) {
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
    // [UX 2026-08-05] 渲染覆盖层状态 (转圈 + SVG 淡入):
    //   mermaid.run() 期间 SVG 元素尚未布局定位 (全部堆叠在中心), 用户体验差.
    //   rendering 为响应式 ref, 模板据此显示覆盖层 + 隐藏未完成 SVG; 渲染完成后淡入.
    //   setRendering 统一封装 (isRendering 防重入 guard + rendering 覆盖层开关), 避免遗漏退出点.
    const rendering = ref(false)
    const setRendering = (v) => { isRendering = v; rendering.value = v }
    let lastRenderData = null  // 上次渲染的数据，用于检测变化
    // [FIX 2026-08-02] L5 渲染跳过 (spec 4.4): 上次生成的 mermaidCode, code-diff 用
    let lastRenderedCode = null
    // [FIX 2026-08-03] reload (forceRerender) 时设为 true, renderMermaid 内消费后重置.
    //   必要性: reload 走 mermaid.run() 全量重排, 与首次渲染/chartType 切换等价,
    //   若不 autoFit, ELK 会读含 zoom transform 的 BCR → 节点维度放大, 文字变小.
    //   之前直接在 if 条件里引用未定义的 forceAutoFit → ReferenceError → reload 显示 text.
    let forceAutoFit = false
    let interactionCleanup = null  // useInteraction 返回的清理函数（用于 onBeforeUnmount）
    // [HIGHLIGHT 2026-08-09] 展开/折叠后需保持高亮的目标 (如双击展开/折叠领域/子领域/服务模块).
    //   渲染为异步 (mermaid.run), SVG 重建会丢失高亮 class; 这里缓存目标, 在 renderMermaid
    //   完成后 (processSvg 设置 data-* 属性后) 消费, 重新 focusOnTarget 恢复高亮.
    let pendingHighlightTarget = null

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
    // [FOLD-COLOR 2026-08-08] 中性灰折叠节点集合: 由 useBusinessObjectSyntax.generateMermaidCode 透出,
    //   渲染完成后若非空则弹 ElMessage 提示 (折叠层级 > 颜色分组层级 → 聚合节点显示中性灰).
    let neutralCollapseIds = new Set()
    // [FIX 2026-08-10] 颜色状态追踪器: 统一维护"最近一次渲染值(last*)快照", 供 deep watch
    //   判断颜色字段是否变化. 替代原 lastColorGroupBy/lastCustomColors/lastColorScheme/
    //   lastCenterScopeHighlight 手写变量. 根因: deep watch 原地修改时 oldVal === newVal,
    //   基于 oldVal 的 diff 恒 false → 颜色变化识别失效 → 恒全量重建. tracker 用 last* 快照
    //   对比 (每次渲染结束时 snapshot 刷新), 使原地修改的颜色字段(如 centerScopeHighlight)
    //   也能被正确识别 → 走 updateColorsOnly 增量变色. 未来任何颜色字段改原地修改都安全.
    const colorTracker = createColorStateTracker()
    let isFirstRender = true
    let lastDiagramType = null

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

    // 生成Mermaid图表代码并保存关系说明信息
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
        // [UPLIFT 2026-08-05] FR-003: 存在上提分组时, 在语法层前重映射连线端点.
        //   上提分组由 enabled 自动推导 (见 upliftDerivation), 无需显式标记判断;
        //   remapLinksToVisibleAncestors 内部无上提时返回原 links. 克隆 data 避免改动源.
        const remapGroups = layoutControlConfig?.groups
        if (data && data.links && data.links.length > 0 && remapGroups && remapGroups.length > 0) {
          data = {
            ...data,
            links: remapLinksToVisibleAncestors(data.links, remapGroups, data.domainProducts)
          }
        }

        // [FIX 2026-08-02] 语法路由由 diagramType 语义决定 (管道统一后 BO 数据也含 containers)。
        //   旧启发式 `data.containers` 会把 BO 图 (统一管道投影也返回 containers) 误路由到
        //   serviceModuleSyntax → BO 节点无 category 处理 + linkColorMappings 缺失 (B 断言 FAIL)。
        //   SM 图: diagramType='serviceModule' 且数据必含 containers (serviceModuleDiagramBuilder)。
        if (data && data.containers && props.diagramType === 'serviceModule') {
          const result = serviceModuleSyntax.generateMermaidCode(data, relationDescriptions, layoutEngine, layoutType, positions, zoneRowCount, preserveModelOrder, layoutControlConfig)
          if (typeof result === 'object' && result !== null) {
            nodeColorMappings = result.nodeColorMappings || []
            // [FIX 2026-08-02] SM 图补齐 linkColorMappings (与 BO 分支一致):
            //   之前只取 nodeColorMappings → linkColorMappings 恒空 →
            //   updateColorsOnly 的 `linkColorMappings.length > 0` 守卫拦截 →
            //   切换 centerScopeHighlight 时连线颜色不更新 (外部节点连线恒黑)。
            linkColorMappings = result.linkColorMappings || []
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
            neutralCollapseIds = result.neutralCollapseIds || new Set()
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
      setRendering(true)
      // [FIX 2026-08-07] 强制 DOM flush: rendering=true 先把 overlay 刷进 DOM,
      //   再跑大计算 (generateMermaidCode / mermaid.run). 否则非 ELK 路径完全无 await,
      //   Vue scheduler 没机会 commit, overlay 永不显示 → 用户看到几秒钟空白.
      //   nextTick (微任务, Vue DOM 更新完成) + rAF (下一帧浏览器绘制) 保证用户肉眼看到 loading,
      //   才进入后续同步计算。
      await nextTick()
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      // [FIX 2026-08-01] 渲染埋点 — useDiagnostics 记录开始时间, 触发 hooks.
      // chart_diag / E2E 通过 window.__archPage.mermaid.lastRender 一键读取耗时.
      diag.beginRender({
        diagramType: props.diagramType,
        layoutEngine: props.layoutEngine,
        nodeCount: props.diagramData?.nodes?.length || 0,
        linkCount: props.diagramData?.links?.length || 0
      })

      // [v40 关系枚举预加载] 渲染前先预加载 relation_type / direction 枚举
      // 之前 fire-and-forget 时, 用户首次 hover 时 EnumService 还没加载完 → tooltip 显示 code
      // 修复: 在渲染前 await 加载, 后续 hover 一定命中缓存 (L1)
      if (props.diagramData && props.diagramData.links && props.diagramData.links.length > 0) {
        preloadEnums().catch((e) => {
          console.warn('[MermaidComponent] preloadEnums failed:', e?.message || e)
        })
      }

      // [FIX 2026-08-01] effectiveLayoutEngine 提到 renderMermaid 函数顶部 (跨 try + nextTick 访问)
      let effectiveLayoutEngine = props.layoutEngine
      // [FIX 2026-08-02] 前置生成 mermaidCode: 供 L5 code-diff 跳过判断 (spec 4.4)
      let mermaidCode = ''
      if (mermaidContainer.value && props.diagramData) {
        try {
          // 暂时禁用 UnifiedRenderer，因为它缺少样式、tooltip、交互等功能
          // UnifiedRenderer 的 disabled 提升功能已经通过 GroupModel.getFlattenedGroups 修复
          if (props.diagramData._unifiedMermaidCode && false) {
            // [FIX 2026-08-02] 该分支被 `&& false` 短路, 永不执行, 保留仅作意图存档
          } else {
            const positions = props.layoutPositions || []
            const zoneRowCount = props.zoneRowCount || 3

            // [FIX 2026-08-02] 阶段 1: 仅生成 mermaidCode, 不触碰 DOM.
            //   L5 code-diff 跳过检查必须发生在 initializeMermaid + innerHTML 之前:
            //   原实现在写入 <pre> 后才检查 querySelector('svg') — 旧 SVG 已被 innerHTML 销毁,
            //   恒为 null → 跳过分支永不触发 (A8 增量跳过 FAIL 根因, 探针确诊 skip='undef').
            if (props.layoutEngine === 'elk') {
              const elkLoaded = await loadElkLayouts(true)
              if (!elkLoaded) {
                effectiveLayoutEngine = 'dagre'
              } else {
                try {
                  mermaidCode = generateMermaidCode(props.diagramData, 'elk', props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
                } catch (e) {
                  console.error('[MermaidComponent] ELK Error generating mermaid code, falling back to dagre:', e)
                  effectiveLayoutEngine = 'dagre'
                }
              }
            }

            if (!effectiveLayoutEngine || effectiveLayoutEngine !== 'elk') {
              try {
                mermaidCode = generateMermaidCode(props.diagramData, effectiveLayoutEngine || 'dagre', props.layoutType, positions, zoneRowCount, props.preserveModelOrder, effectiveLayoutControlConfig.value)
              } catch (e) {
                console.error('[MermaidComponent] Error generating mermaid code:', e)
              }
            }

            // [FIX 2026-08-02] 阶段 2: L5 code-diff 跳过检查 (此时旧 SVG 仍在 DOM 中, 判断可靠)
            //   mermaidCode 与上次一致且已有 SVG → 渲染结果不会变化, 跳过 mermaid.run() 全量重绘
            //   (大图耗时主要在 mermaid.run). 触发场景: 缓存命中的重渲染 (如切换图表类型后切回),
            //   仅配色变化走 updateColorsOnly 不受影响.
            // [FIX 2026-08-03] GlobalToolbar refresh reload 改用 forceRerender 显式清空 lastRenderedCode
            //   绕过此跳过分支, 不再依赖 _renderNonce 字段 (原方案 mermaid.run() 不带参数无法可靠转换 pre).
            if (mermaidCode && lastRenderedCode !== null && lastRenderedCode === mermaidCode && mermaidContainer.value?.querySelector('svg')) {
              // [E2E 2026-08-02] 暴露增量跳过信号 — chart_e2e A8 断言读取
              //   renderSkippedCount: 累计跳过次数 (每次 code-diff 命中 +1)
              //   lastRenderedCode:   当前已渲染的 mermaid code (与 window.__lastMermaidCode 比对)
              if (typeof window !== 'undefined' && window.__archPage?.mermaid) {
                window.__archPage.mermaid.renderSkippedCount = (window.__archPage.mermaid.renderSkippedCount || 0) + 1
                window.__archPage.mermaid.lastRenderedCode = mermaidCode
              }
              // 同步 data-chart-rendered 标记 (走 diag.endRender → EmbeddedChartView onDiagRenderEnd):
              //   图表已是终态 (旧 SVG 即当前结果), 让 E2E wait_render_stable 不因"无新渲染"空等超时.
              const skipSvg = mermaidContainer.value.querySelector('svg')
              diag.endRender({
                layoutEngine: effectiveLayoutEngine,
                nodeCount: skipSvg?.querySelectorAll('g.node').length || 0,
                edgeCount: skipSvg?.querySelectorAll('path.flowchart-link').length || 0,
                containerCount: skipSvg?.querySelectorAll('g.cluster').length || 0,
                skipped: true
              })
              setRendering(false)
              return
            }

            // [FIX 2026-08-02] 阶段 3: 未命中跳过 → 初始化 + 写入 <pre>, 交给下方 mermaid.run()
            if (mermaidCode) {
              // 关键修复：动态调整 maxTextSize，避免大图表报 'Maximum text size in diagram exceeded'
              const dynamicMaxTextSize = Math.max(configStore.mermaidMaxTextSize || 500000, mermaidCode.length * 2 + 100000)
              initializeMermaid(props.diagramType, props.diagramData, effectiveLayoutEngine || 'dagre', props.layoutType, props.preserveModelOrder, effectiveLayoutControlConfig.value, dynamicMaxTextSize)
              mermaidContainer.value.innerHTML = `<pre class="mermaid">${mermaidCode}</pre>`
              // 记录本次已渲染 code — 下次相同输入命中阶段 2 跳过
              lastRenderedCode = mermaidCode
              if (typeof window !== 'undefined' && window.__archPage?.mermaid) {
                window.__archPage.mermaid.lastRenderedCode = mermaidCode
              }
            }
          }
        } catch (err) {
          console.error('[MermaidComponent] renderMermaid error:', err)
          setRendering(false)
        }

      // [FIX 2026-08-02] nextTick + mermaid.run 位于 if (mermaidContainer.value && props.diagramData)
      //   块内部 — 下方 `} else {` (L730) 匹配此 if, 不能在此闭合 if 块 (原实现即如此)
      nextTick(() => {
        // [FIX 2026-08-03] A1: 整个 nextTick 回调 try/catch 包裹.
        //   之前 nextTick 内同步抛错 (e.g. ReferenceError 引用未定义变量) 会静默失败,
        //   mermaid.run() 没机会执行 → <pre> 保留 mermaid code 文本 (用户看到 text 而非 SVG).
        //   现在 sync error 走 diag 链路 → onError hook → EmbeddedChartView emit render-error → toast.
        //   注意: mermaid.run().then().catch() 内部错误已被 Promise 链 catch 兜底, 此处主要兜 sync 部分.
        try {
          const preEl = mermaidContainer.value?.querySelector('pre.mermaid')
          // [FIX 2026-08-03] 在 mermaid.run() 之前同步重置 transform (instant 模式)。
          //   原实现: setTimeout(autoFitDiagram, 100) 在 mermaid.run().then() 内异步调度,
          //   此时 mermaid.run() 已完成。但 mermaid.run() 内部 ELK layout 会读
          //   .mermaid-content.getBoundingClientRect() (含 zoom transform) 算出大 viewBox,
          //   导致节点 rect/foreignObject 维度被放大 (×zoom scale, 实测 foW 96→441)。
          //   同时 processSvg 内 scheduleEdgeLabelFix (rAF×2 ~32ms) 调度 fixEdgeLabelSize,
          //   该函数用 foreignObject.getCTM() (SVG 文档坐标, 不含 CSS transform) 除
          //   labelBkg.getBoundingClientRect() (viewport 像素, 含 zoom transform),
          //   得到 (真实宽度 × zoom scale), 永久写入 foreignObject width attribute,
          //   导致 edgeLabel 文字被 rect 裁剪, 刷新页面才恢复。
          //   修复: autoFitDiagram(instant=true) 同步重置 scale=1/translate=0,0 在 mermaid.run() 之前,
          //   instant=true 禁用 CSS transition (MermaidComponent.css L180 transition: transform 0.15s)
          //   并 force reflow, 确保 getBoundingClientRect() 立即返回 fit 状态下的正确 BCR,
          //   既阻止 ELK 读到大 BCR, 也让 fixEdgeLabelSize 在 fit 状态下计算正确宽度。
          //   约束: 仅在首次渲染或图表类型切换时重置, 颜色切换等保留用户 zoom 状态。
          const diagramTypeChanged = lastDiagramType !== null && lastDiagramType !== props.diagramType
          // [FIX 2026-08-03] reload (forceRerender) 也走 mermaid.run() 全量重排,
          //   必须在 run() 之前同步 autoFit 重置 transform, 否则 ELK 读含 zoom 的 BCR
          //   → 节点维度放大, 文字变小 (与 chartType 切换前修复的同一根因).
          //   forceAutoFit 由 forceRerender() 设置, 这里消费后立即重置 (避免影响下次普通重绘).
          const _shouldForceAutoFit = forceAutoFit
          forceAutoFit = false
          if (isFirstRender || diagramTypeChanged || _shouldForceAutoFit) {
            interaction.autoFitDiagram(true)
          }
          const _preBefore = mermaidContainer.value?.querySelector('pre.mermaid')
          // [FIX 2026-08-03] mermaid 11 run() 内部检查 data-processed 属性, 有则跳过元素.
          //   reload 时若上次 run() 抛错 (render2 reject), pre 已被设 data-processed=true 但 innerHTML
          //   仍为 mermaid code 文本, 用户看到 text. 显式清除属性 + 显式传 nodes 避免扫描整个 document.
          if (_preBefore) {
            _preBefore.removeAttribute('data-processed')
          }
          const _runOpts = _preBefore ? { nodes: [_preBefore] } : undefined
          mermaid.run(_runOpts)
            .then(() => {
              const svgElAfter = mermaidContainer.value?.querySelector('svg')
              if (svgElAfter) {
                svgProcessor.processSvg(svgElAfter, props, relationDescriptions, mermaidContainer, nodeColorMappings, interaction, handleToggleGroupVisible)

                // [HIGHLIGHT 2026-08-09] 消费展开/折叠后待恢复的高亮目标.
                //   processSvg 已设置 data-code/data-container-code 等定位属性, 此时重新 focusOnTarget
                //   即可恢复被操作元素 (领域/子领域/服务模块) 的高亮态. 消费后立即清空, 避免下次渲染误触.
                if (pendingHighlightTarget) {
                  const { id, type } = pendingHighlightTarget
                  pendingHighlightTarget = null
                  try {
                    annotationOverlay.focusOnTarget(svgElAfter, id, type)
                  } catch (e) {
                    console.warn('[HIGHLIGHT] re-highlight after expand/collapse failed:', e)
                  }
                }

                // [FIX 2026-08-02 v5] 回到原方案: 中心范围高亮 = 中心节点 fill 用 centerScopeColor (指定颜色)
                //   v2 曾改为"分组色 + 粗虚线边框", 用户反馈虚线区分不明显, 改回用颜色区分。
                //   语法层已对中心节点输出 centerScopeColor 的 style 指令, 这里再兜底覆盖一次,
                //   防止个别节点 (如未进 nodeColorMap) 漏染。
                if (props.diagramData?.centerScopeHighlight && nodeColorMappings.length > 0) {
                  const csSet = new Set(props.diagramData.centerScope || [])
                  const csColor = props.diagramData.centerScopeColor || '#808080'
                  nodeColorMappings.forEach(mapping => {
                    if (csSet.has(mapping.nodeCode) || csSet.has(mapping.nodeName)) {
                      const rect = svgElAfter.querySelector(
                        `#${mapping.nodeId} rect, [data-code="${mapping.nodeCode}"] rect, [data-id="${mapping.nodeId}"] rect, g.node[id^="flowchart-${mapping.nodeId}-"] rect`
                      )
                      if (rect) {
                        rect.style.setProperty('fill', csColor, 'important')
                      }
                    }
                  })
                }

                // 设置交互功能
                // 关键修复 v10：传 mermaidContainerEl（真 .mermaid-container）作为 wheel/mousedown 事件目标
                // 之前传 mermaidWrapper，全屏模式下 mermaidWrapper 仍受父级 CSS 限制，事件触不到或无效
                // 关键修复 v15：第 3 个参数必须传 mermaidContainer（.mermaid-content），
                // 之前误传 draggableArea，导致 updateTransform 把 transform 设到 draggle 上而不是 content 上
                // （v10 改 addZoomAndPan 签名时漏改调用方）
                // 关键修复 v19：接收 cleanup 返回值，调用前先清旧 — 否则 wheel/dblclick 监听器累积导致 zoom 步长翻倍
                if (interactionCleanup) { interactionCleanup(); interactionCleanup = null }
                interactionCleanup = interaction.addZoomAndPan(mermaidContainerEl, mermaidWrapper, mermaidContainer)

                // 设置画布布局
                svgProcessor.setupCanvasLayout(mermaidWrapper, mermaidContainer, draggableArea)

                // 只在首次渲染时自动适应，后续更新保持当前缩放状态
                // [FIX 2026-07-31] 切换图表类型 (业务对象图 ↔ 服务模块图) 时也需 autoFit，
                //   否则新 SVG 沿用旧 transform 导致画布视觉缩小。
                //   之前只在 isFirstRender=true 时 autoFit，切换 chartType 后 isFirstRender 已是 false。
                // [FIX 2026-08-03] autoFitDiagram(instant=true) 已移到 mermaid.run() 之前同步执行 (见上方 L464-467),
                //   此处仅更新 isFirstRender / lastDiagramType 状态。
                //   diagramTypeChanged 复用上方计算结果 (同作用域, 同一次渲染)。
                if (isFirstRender || diagramTypeChanged) {
                  isFirstRender = false
                }
                lastDiagramType = props.diagramType
                // [FIX 2026-08-10] 全量渲染完成后刷新颜色快照 (替代手写 last* 赋值)
                colorTracker.snapshot(props.diagramData)
                
                // 渲染完成，重置渲染状态
                setRendering(false)
                // [FIX 2026-08-01] 渲染完成埋点 — chart_diag / E2E 一键读取耗时和元数据
                const finishedSvg = mermaidContainer.value?.querySelector('svg')
                diag.endRender({
                  layoutEngine: effectiveLayoutEngine,
                  nodeCount: finishedSvg?.querySelectorAll('g.node').length || 0,
                  edgeCount: finishedSvg?.querySelectorAll('path.flowchart-link').length || 0,
                  containerCount: finishedSvg?.querySelectorAll('g.cluster').length || 0
                })
                // [FOLD-COLOR 2026-08-08] 中性灰折叠节点提示: 折叠层级 > 颜色分组层级时,
                //   聚合节点无法用单一分组色表达, 走中性灰 classDef. 渲染完成后弹一次提示,
                //   帮助用户理解"为何某折叠节点是灰色". (feature-flag: 无独立开关, 跟随折叠/配色逻辑)
                if (neutralCollapseIds && neutralCollapseIds.size > 0) {
                  ElMessage({
                    message: `存在 ${neutralCollapseIds.size} 个折叠节点包含多个分组，已显示为中性灰`,
                    type: 'info',
                    duration: 3000
                  })
                }
                // [FE1 2026-08-02] 暴露实际渲染色 (nodeCode → fill) 到 diagnostics:
                //   E2E 颜色断言通过 window.__archPage.mermaid.stepMeta.nodeColorMappings 读取权威源,
                //   无需从 SVG fill 反推 (SVG fill 可能被 CSS class 覆盖, 读取不可靠)。
                //   nodeColorMappings 来自 useBusinessObjectSyntax/useServiceModuleSyntax 的 generateMermaidCode 返回。
                if (nodeColorMappings && nodeColorMappings.length > 0) {
                  diag.recordStepMeta('nodeColorMappings', nodeColorMappings)
                }
                // [FE4 2026-08-02] 暴露 link 颜色映射 (BO 图才有):
                //   E2E B9 通过 stepMeta.linkColorMappings 读取权威源, 与 SVG link stroke 抽样对比,
                //   防「节点染色了但边没染色」.
                if (linkColorMappings && linkColorMappings.length > 0) {
                  diag.recordStepMeta('linkColorMappings', linkColorMappings)
                }

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
                    /* 注意：这些规则不适用于.edge-label-clean，因为它有自己的背景规则 */
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
                    /* 隐藏 edgeLabel 内的装饰性path 元素 */
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
                    /* 只让 labelBkg 有背景颜色*/
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
              setRendering(false)
              // [FIX 2026-08-01] 渲染失败埋点
              diag.recordError(err, 'renderMermaid')
              diag.endRender({ error: err?.message || String(err) })
            })
        } catch (err) {
          // [FIX 2026-08-03] A1: nextTick 同步异常兜底 (e.g. ReferenceError / TypeError).
          //   不再静默失败: 走 diag 链路 → onError hook → EmbeddedChartView emit render-error →
          //   RelationshipManagement.handleChartRenderError → ElMessage.error toast.
          console.error('[MermaidComponent] nextTick callback sync error:', err)
          setRendering(false)
          diag.recordError(err, 'renderMermaid.nextTick')
          diag.endRender({ error: err?.message || String(err) })
        }
        })
      } else {
        setRendering(false)
        // [FIX 2026-08-01] 跳过渲染也记录 (避免 lastRender 卡在 null)
        diag.recordWarning('renderMermaid early return: container or diagramData missing', 'renderMermaid')
        diag.endRender({ error: 'no_container_or_diagramData' })
      }
    }

    // [FIX 2026-08-03] forceRerender: GlobalToolbar refresh 触发 reload 时调用.
    //   原 reload 用 _renderNonce 触发 watch → renderMermaid, 但 mermaidCode 相同时
    //   即使 nonce 变化绕过 code-diff 跳过, mermaid.run() 不带参数无法可靠把 <pre> 转成 SVG
    //   (mermaid 11 行为, 表现为图表显示 text 而非 SVG).
    //   改为显式清空 lastRenderedCode 让 code-diff 不命中, 然后直接调 renderMermaid().
    //   与 chartType 切换回来路径等价 (mermaidCode 不同 → code-diff 不命中 → mermaid.run() 成功).
    //   设 forceAutoFit=true: reload 走全量重排, 需在 run() 前重置 transform (与首次渲染同).
    const forceRerender = () => {
      console.log('[MermaidComponent] forceRerender called, clearing lastRenderedCode to bypass code-diff skip')
      // [FIX 2026-08-03] A3: reload 埋点 — 让 E2E / 监控感知 reload 发生.
      //   chart_diag.read('stepMeta') / window.__archPage.mermaid.stepMeta.reload 可读取,
      //   与 renderMermaid 内部 beginRender/endRender 配合, 一次 reload 完整链路可观测.
      diag.recordStepMeta('reload', { source: 'forceRerender', at: Date.now() })
      lastRenderedCode = null
      forceAutoFit = true
      renderMermaid()
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
    
    // 只在新增节点或连线时才重新渲染颜色，否则只更新图表
    // [FIX 2026-08-10] 无参: 内部所有取值均来自 props.diagramData + colorTracker, 不再依赖参数.
    const updateColorsOnly = () => {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) {
        return false
      }

      const currentColorGroupBy = props.diagramData?.colorGroupBy || 'domain'

      // [FIX 2026-07-31] 短路条件需纳入 colorScheme / centerScopeHighlight
      //   之前: 只看 colorGroupBy 和 customColors → 切配色/中心范围时短路 return true → 不更新
      // [FIX 2026-08-10] 改用 colorTracker.changed (last* 快照对比), 替代手写 last* 变量.
      if (!colorTracker.anyChanged(props.diagramData)) {
        return true
      }

      const data = props.diagramData
      const colorGroupBy = currentColorGroupBy

      // [INC 2026-08-09] 折叠视图 (nodeColorMappings 为空) 支持增量变色, 不再回退全量重载。
      //   之前 nodeColorMappings.length===0 直接 return false → 上层回退 renderMermaid
      //   (闪 loading + 重置展开态, 用户看到"切换颜色分组导致折叠")。
      //   现改为: 折叠节点 (COLLAPSE_*/聚合节点, 带 data-container-code) 的颜色基于
      //   「分组上下文 + colorMap(与全量渲染/展开增量同源)」增量更新。
      //   [FIX 2026-08-09 v2] 折叠节点与展开节点/legend 必须共用同一份 colorMap
      //   (buildColorMap 产物, 键=serviceModuleName/domain/subDomain)。此前折叠分支直接
      //   用 data.groupColorMap (colorize 产物, 其 serviceModule 键是 BO 的 name), 键与
      //   展开路径不一致 → 切"按服务模块"时折叠节点/legend 全灰。
      //   objectToModuleMap 供 buildColorMap 推导分组键, 与下方展开分支同源.
      const objectToModuleMap = dataMap.buildObjectToModuleMap(data)

      // 折叠节点编码 → 分组上下文 (domainName/subDomainName/serviceModuleName) 映射。
      //   从 layoutControlConfig.groups 遍历 (与 data-container-code 的 elementCode 同源)。
      //   [FIX 2026-08-09] 祖先上下文传播: 分组对象 (deriveLayoutGroups) 只带 title/elementCode/
      //   groupType, 不带 domainName/subDomainName/serviceModuleName. 若只读 group 自身字段,
      //   每个折叠节点只会拿到自己的 title, 无法表达"折叠 SM + 按 subDomain/domain 分组"应继承
      //   祖先分组 key 的语义. 与语法层 applyUpliftNodeColors 的 nextCtx 传播保持一致:
      //   沿 children/containers 下探时, 记录最近祖先的 domain/subDomain/serviceModule 标题.
      const collapseCtxMap = new Map()
      const walkGroups = (list, ctx) => {
        ;(list || []).forEach((g) => {
          if (!g || typeof g !== 'object') return
          const nextCtx = { ...(ctx || {}) }
          if (g.groupType === 'domain') nextCtx.domain = g.title || g.name
          else if (g.groupType === 'subDomain') nextCtx.subDomain = g.title || g.name
          else if (g.groupType === 'serviceModule') nextCtx.serviceModule = g.title || g.name
          const code = g.elementCode || g.id
          if (code) {
            collapseCtxMap.set(code, {
              domainName: nextCtx.domain || '',
              subDomainName: nextCtx.subDomain || '',
              serviceModuleName: nextCtx.serviceModule || '',
              title: g.title || g.name || '',
              groupType: g.groupType || ''
            })
          }
          walkGroups(g.children, nextCtx)
          walkGroups(g.containers, nextCtx)
        })
      }
      walkGroups(props.layoutControlConfig?.groups, {})

      // [FIX 2026-08-09 v2] 折叠/展开/legend 共用同一份 colorMap (键=serviceModuleName/domain/subDomain)。
      //   用 data.nodes 全量 BO 节点推导 uniqueGroups (折叠视图 nodeColorMappings 非空,
      //   但为统一取色键, 优先用 buildColorMap; 若 nodeColorMappings 为空则回退 data.nodes).
      const colorSchemeColors = colors.getColorScheme(data.colorScheme)
      const buildUnifiedColorMap = (mappings) => colors.buildColorMap(
        mappings,
        objectToModuleMap,
        colorGroupBy,
        colorSchemeColors,
        data.customColors || {}
      )
      // nodeColorMappings 由 syntax 层生成 (含折叠视图), 直接复用它构建 colorMap
      // [FOLD 2026-08-09] 折叠视图 (nodeColorMappings 为空) 时回退用 data.nodes 全量 BO 节点
      //   构建 colorMap (buildColorMapFromNodes), 保证折叠节点/图例有真实分组色, 而非空 Map 全灰.
      const unifiedColorMap = nodeColorMappings.length > 0
        ? buildUnifiedColorMap(nodeColorMappings)
        : colors.buildColorMapFromNodes(data.nodes || [], colorGroupBy, colorSchemeColors, data.customColors || {})

      colors.updateCollapseNodeColors(svg, collapseCtxMap, colorGroupBy, unifiedColorMap, {
        centerScopeHighlight: data.centerScopeHighlight,
        centerScope: data.centerScope || [],
        centerScopeColor: data.centerScopeColor || '#808080',
        centerScopeMarkers: configStore.centerScopeMarkers || {}
      })

      // [OBS 2026-08-09] 颜色增量可观测摘要: 供浏览器验证"切颜色分组后折叠节点/legend 取色是否同源".
      //   期望: 按服务模块分组时 collapse 节点颜色与 legend 项颜色一致 (同 key).
      if (typeof window !== 'undefined') {
        window.__archPage = window.__archPage || {}
        window.__archPage.colorState = {
          colorGroupBy,
          colorScheme: data.colorScheme,
          customColors: data.customColors || {},
          unifiedColorMapKeys: Array.from((unifiedColorMap && typeof unifiedColorMap.keys === 'function')
            ? unifiedColorMap.keys() : Object.keys(unifiedColorMap || {})),
          collapseCtxEntries: Array.from(collapseCtxMap.entries()).map(([code, ctx]) => ({
            code,
            groupType: ctx.groupType,
            domainName: ctx.domainName,
            subDomainName: ctx.subDomainName,
            serviceModuleName: ctx.serviceModuleName
          })),
          nodeColorMappingsCount: nodeColorMappings.length,
          legendRefreshSkipped: !(props.annotationConfig && (props.diagramType === 'businessObject' || props.diagramType === 'serviceModule'))
        }
      }

      if (nodeColorMappings.length > 0) {
        const colorMap = buildUnifiedColorMap(nodeColorMappings)

        // [FIX 2026-07-31] 传 centerScopeHighlight 信息, 让 updateNodeColors 给 centerScope BOs 加边框区分
        colors.updateNodeColors(svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, {
          centerScopeHighlight: data.centerScopeHighlight,
          centerScope: data.centerScope || [],
          centerScopeColor: data.centerScopeColor || '#808080'
        })
        // linkColorMappings 为空时跳过 (很多 BO 图无 link)
        if (linkColorMappings && linkColorMappings.length > 0) {
          colors.updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, {
            centerScopeHighlight: data.centerScopeHighlight,
            centerScope: data.centerScope || [],
            centerScopeColor: data.centerScopeColor || '#808080'
          })
          // [FIX 2026-08-05] 增量改线色后, 同步箭头 marker 颜色跟随线色
          //   (updateLinkColors 只改 path stroke, 箭头 marker 仍留在全量渲染时的旧色 →
          //    改对象范围色/配色后线色变了但箭头色没变).
          svgStyle.syncArrowMarkers(svg, props.diagramType)
        }
      }

      // 更新文字颜色
      const textColorSetting = props.diagramData?.textColor || 'black'
      svgStyle.updateNodeStyles(svg, textColorSetting)
      svgStyle.updateClusterStyles(svg, textColorSetting)

      // [FIX 2026-07-31] 增量刷新颜色图例
      //   之前切 colorGroupBy 只更新 rect fill, 不重建 legend panel → legend 颜色键仍按旧 colorGroupBy 显示
      //   修复: 调 svgProcessor.updateColorLegend 重建 legend (复用 renderAnnotationOverlay 的 legend 部分逻辑)
      // [FOLD 2026-08-09] 移除 nodeColorMappings.length>0 守卫: 折叠视图 nodeColorMappings 为空,
      //   但 data.nodes 全量 BO 节点仍在, 图例应始终按当前 colorGroupBy 重建 (否则折叠层级下图例
      //   停留在旧维度, 用户反馈"切颜色分组后 legend 仍按领域显示")。
      //   传 unifiedColorMap 保证图例键色与折叠节点(updateCollapseNodeColors)同源.
      if (props.annotationConfig && (props.diagramType === 'businessObject' || props.diagramType === 'serviceModule')) {
        try {
          // 同步更新 nodeColorMappings 数组内每个 mapping.color (供 buildColorLegendData 使用)
          // updateNodeColors 已经做了: mapping.color = newColor
          svgProcessor.updateColorLegend(svg, data, props.annotationConfig, nodeColorMappings, props.layoutControlConfig?.groups || null, handleToggleGroupVisible, unifiedColorMap)
        } catch (e) {
          console.warn('[MermaidComponent.updateColorsOnly] legend refresh failed:', e)
        }
      }

      // [FIX 2026-08-10] 增量变色完成后刷新颜色快照 (替代手写 last* 赋值)
      colorTracker.snapshot(data)

      // [C1 2026-08-03] 增量变色路径也发完成标记 — 让 e2e wait_render_stable 可靠等待
      //   之前不发, e2e 只能 sleep 1.2s 兜底, 增量失败时无法捕获 (5 个 WARN)
      //   现在发 incremental=true 标记, e2e 可用 wait_render_stable(timeout=3000) 精确等待
      //   注: svg 变量在 L832 已取, 这里直接复用; L854 的短路 return true 是"无变化"路径, 不发标记
      try {
        diag.endRender({
          layoutEngine: props.layoutEngine,
          nodeCount: svg?.querySelectorAll('g.node').length || 0,
          edgeCount: svg?.querySelectorAll('path.flowchart-link').length || 0,
          containerCount: svg?.querySelectorAll('g.cluster').length || 0,
          incremental: true
        })
      } catch (e) {
        console.warn('[MermaidComponent.updateColorsOnly] endRender failed:', e)
      }

      return true
    }

    // [VIS 2026-08-07] 增量可见性更新: 隐藏/显示分组时【不重跑 ELK 布局】,
    //   直接对已渲染 SVG 的 容器(cluster)/节点(g.node)/连线(path) 做 display 切换。
    //   语义区分: 隐藏(visible=false) 只做展示层隐藏(留空位), 不动布局;
    //   禁用(enabled=false) 走全量渲染(子孙上浮打平+重新布局)。
    //   输入: 当前 layoutControlConfig.groups (含各分组最新 visible 状态)
    // [SCOPE 2026-08-07] 对象范围保护 (组件级共享): 范围内要素及其祖先链不因父分组隐藏而被隐藏。
    //   例: 对象范围=供应链云下采购供应, 隐藏供应链云 → 只隐藏供应链云下其他要素,
    //   采购供应及其中间祖先(供应链计划/供应链云)保持显示。
    //   判断依据 configStore.centerScopeMarkers (每次读取最新, 避免 shallowRef 替换后捕获旧值):
    //     serviceModules: 范围内服务模块 (name/code → true) → 直接范围分组 (整棵子树受保护)
    //     subDomains/domains: hasCenter=true → 含范围内要素的祖先分组
    //   标题可能含祖先路径/编码后缀 (如 "采购供应（供应链计划）"), 取裸名匹配 markers。
    const isDirectScopeGroup = (g) => {
      const scopeMarkers = configStore.centerScopeMarkers
      if (!g || typeof g !== 'object' || !scopeMarkers) return false
      const name = (g.title || g.name || '').replace(/[（(].*$/, '').trim()
      const code = g.elementCode || ''
      return !!scopeMarkers.serviceModules?.has(name) || (!!code && !!scopeMarkers.serviceModules?.has(code))
    }
    const isScopeAncestor = (g) => {
      const scopeMarkers = configStore.centerScopeMarkers
      if (!g || typeof g !== 'object' || !scopeMarkers) return false
      const name = (g.title || g.name || '').replace(/[（(].*$/, '').trim()
      if (scopeMarkers.subDomains?.get(name) === true) return true
      if (scopeMarkers.domains?.get(name) === true) return true
      return false
    }
    const isScopeProtected = (g) => isDirectScopeGroup(g) || isScopeAncestor(g)

    const updateVisibilityOnly = (groups) => {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) return false

      const hiddenNodeCodes = new Set()
      const hiddenContainerCodes = new Set()
      // [VIS 2026-08-07] 聚合/折叠节点 id 集合 (COLLAPSE_<sanitized group id>):
      //   展开到子领域/服务模块时, 子领域/服务模块折叠为聚合节点(渲染为 g.node 而非 g.cluster),
      //   隐藏其所属分组时必须连同这些聚合节点及连到它们的连线一起隐藏(不重跑布局)。
      const hiddenCollapseIds = new Set()

      const collectLeafNodes = (leaf, set) => {
        if (typeof leaf === 'string') { set.add(leaf); return }
        if (!leaf || typeof leaf !== 'object') return
        if (leaf.code) set.add(leaf.code)
        else if (leaf.elementCode) set.add(leaf.elementCode)
        else if (leaf.name) set.add(leaf.name)
        ;(leaf.directNodes || []).forEach((n) => {
          if (typeof n === 'string') set.add(n)
          else if (n && typeof n === 'object') set.add(n.code || n.name)
        })
      }
      const collectGroupNodes = (g, set) => {
        ;(g.containers || []).forEach((c) => collectLeafNodes(c, set))
        ;(g.directNodes || []).forEach((n) => {
          if (typeof n === 'string') set.add(n)
          else if (n && typeof n === 'object') set.add(n.code || n.name)
        })
        ;(g.children || []).forEach((ch) => collectGroupNodes(ch, set))
      }
      // [VIS 2026-08-07] 递归收集分组自身 + 所有子孙分组的 容器code 与 聚合节点id。
      //   隐藏父分组(如领域)时, 其子孙分组(子领域/服务模块)渲染为独立的 g.cluster /
      //   g.node(COLLAPSE_<id>) SVG 元素, 必须一并加入隐藏集合, 否则领域隐藏后
      //   子领域容器/聚合节点仍显示。
      const collectDescendantGroupIds = (g, containerCodes, collapseIds) => {
        ;(g.children || []).forEach((ch) => {
          if (!ch || typeof ch !== 'object') return
          const code = ch.elementCode || ch.id
          if (code) containerCodes.add(code)
          if (ch.id) collapseIds.add(upliftNodeId(ch))
          collectDescendantGroupIds(ch, containerCodes, collapseIds)
        })
        ;(g.containers || []).forEach((c) => {
          if (!c || typeof c !== 'object') return
          const code = c.elementCode || c.id
          if (code) containerCodes.add(code)
          if (c.id) collapseIds.add(upliftNodeId(c))
          collectDescendantGroupIds(c, containerCodes, collapseIds)
        })
      }
      // [SCOPE 2026-08-07] 对象范围保护逻辑见组件级共享函数 isScopeProtected (isDirectScopeGroup/isScopeAncestor)。
      const walk = (list, inheritedHidden) => {
        ;(list || []).forEach((g) => {
          if (!g || typeof g !== 'object') return
          const effectiveHidden = inheritedHidden || g.visible === false
          const shouldHide = effectiveHidden && !isScopeProtected(g)
          if (shouldHide) {
            const code = g.elementCode || g.id
            if (code) hiddenContainerCodes.add(code)
            // [VIS 2026-08-07] 记录隐藏分组的聚合节点 id (用于隐藏 g.node 聚合节点及其连线)
            if (g.id) hiddenCollapseIds.add(upliftNodeId(g))
            collectGroupNodes(g, hiddenNodeCodes)
            // [VIS 2026-08-07] 递归隐藏子孙分组的容器/聚合节点 (子领域/服务模块)
            collectDescendantGroupIds(g, hiddenContainerCodes, hiddenCollapseIds)
          }
          // 叶子容器单独隐藏 (visible=false); 范围内叶子容器受保护
          if (Array.isArray(g.containers)) {
            g.containers.forEach((c) => {
              if (c && typeof c === 'object' && c.visible === false && !isScopeProtected(c)) {
                collectLeafNodes(c, hiddenNodeCodes)
              }
            })
          }
          walk(g.children, effectiveHidden)
          walk(g.containers, effectiveHidden)
        })
      }
      walk(groups, false)

      // [VIS 2026-08-08 v2] 空容器隐藏: 分组本身可见(visible=true)但其整棵子树内容全被隐藏时,
      //   该分组渲染为空盒容器, 应一并隐藏其 g.cluster 容器. 与全量重渲染路径
      //   hasGroupContent 的空内容剪枝保持一致, 保证增量隐/显与全量重排结果一致.
      //   用户场景: 隐藏"销售"下的服务模块/业务对象后, 仅剩"销售"子领域空容器残留.
      const hasVisibleContent = (g) => {
        if (!g || typeof g !== 'object') return false
        if (g.visible === false) return false
        if (g.directNodes && g.directNodes.length > 0) return true
        if (Array.isArray(g.containers)) {
          for (const c of g.containers) {
            if (!c || typeof c !== 'object') continue
            if (c.visible === false) continue
            if ((c.nodes && c.nodes.length > 0)
              || c.elementRef?.code != null
              || c.elementCode != null
              || c.name != null) return true
          }
        }
        if (Array.isArray(g.children)) {
          for (const ch of g.children) {
            if (hasVisibleContent(ch)) return true
          }
        }
        return false
      }
      // 上提/折叠分组渲染为 COLLAPSE_<id> 聚合节点(g.node), 非 g.cluster 容器,
      //   hasVisibleContent 对它们返回 false(无可见子孙), 但不应隐藏其聚合节点.
      //   故仅对有可见内容为空的容器类分组(g.cluster)补充隐藏; 上提分组由
      //   hiddenCollapseIds 单独管理, 不会因本段被误隐藏.
      const collectEmptyGroupContainers = (list) => {
        ;(list || []).forEach((g) => {
          if (!g || typeof g !== 'object') return
          if (g.visible !== false && g._uplift !== true && !hasVisibleContent(g)) {
            const code = g.elementCode || g.id
            if (code) hiddenContainerCodes.add(code)
          }
          collectEmptyGroupContainers(g.children)
        })
      }
      collectEmptyGroupContainers(groups)

      // nodeId ↔ nodeCode 映射
      const nodeIdToCode = new Map()
      nodeColorMappings.forEach((m) => { if (m.nodeId) nodeIdToCode.set(m.nodeId, m.nodeCode) })

      // 1) 节点: 按 data-code 隐藏/显示
      nodeColorMappings.forEach((m) => {
        if (!m.nodeCode) return
        const hide = hiddenNodeCodes.has(m.nodeCode)
        const el = svg.querySelector(`g.node[data-code="${m.nodeCode}"]`)
        if (el) el.style.display = hide ? 'none' : ''
      })

      // 2) 连线: 任一端节点被隐藏则该连线隐藏
      // [VIS 2026-08-07] 隐藏连线时必须连同连线标题(edgeLabel)一起隐藏, 否则连线消失但标题悬空显示。
      //   Mermaid 的 edgeLabel 与 path 同在 g.edgePath / g.flowchart-link 分组内, 故隐藏整个
      //   edge 分组(而非仅 path), 使连线与其标题一起隐/显。
      if (linkColorMappings && linkColorMappings.length > 0) {
        const paths = svg.querySelectorAll('.flowchart-link path, .edgePath path, .edgePaths > path')
        // [LABEL 2026-08-07] Mermaid 11 中连线文字 (edgeLabel) 位于独立 g.edgeLabels > g.edgeLabel 分组,
        //   不在 g.edgePath / g.flowchart-link 内; 隐藏连线分组不会隐藏 label, 须按相同 index 单独隐藏。
        const edgeLabels = svg.querySelectorAll('g.edgeLabel')
        linkColorMappings.forEach((mapping) => {
          const srcCode = nodeIdToCode.get(mapping.sourceId)
          const tgtCode = nodeIdToCode.get(mapping.targetId)
          // [VIS 2026-08-07] 聚合端点 (COLLAPSE_<id>) 不在 nodeColorMappings 中 (nodeIdToCode 查不到),
          //   需用 hiddenCollapseIds 判定端点是否属于隐藏分组。
          const srcHidden = (srcCode && hiddenNodeCodes.has(srcCode)) || hiddenCollapseIds.has(mapping.sourceId)
          const tgtHidden = (tgtCode && hiddenNodeCodes.has(tgtCode)) || hiddenCollapseIds.has(mapping.targetId)
          const hide = srcHidden || tgtHidden
          const pathEl = paths[mapping.index]
          if (pathEl) {
            const edgeGroup = pathEl.closest('g.edgePath, g.flowchart-link') || pathEl
            edgeGroup.style.display = hide ? 'none' : ''
          }
          // [LABEL 2026-08-07] 独立隐藏对应连线文字, 防止连线消失但 label 悬空
          const labelEl = edgeLabels[mapping.index]
          if (labelEl) {
            const labelGroup = labelEl.closest('g.edgeLabel') || labelEl
            labelGroup.style.display = hide ? 'none' : ''
          }
        })
      }

      // 3) 容器: 按 data-container-code 隐藏/显示 (仅处理带 code 的, 未匹配到的不动)
      svg.querySelectorAll('g.cluster, .subgraph').forEach((el) => {
        const code = el.getAttribute('data-container-code')
        if (!code) return
        el.style.display = hiddenContainerCodes.has(code) ? 'none' : ''
      })

      // 3.5) 聚合/折叠节点 (COLLAPSE_<id>, 渲染为 g.node): 按 hiddenCollapseIds 隐藏/显示。
      //   展开到子领域/服务模块时这些分组折叠为聚合节点, 不在 g.cluster 中, 须单独处理。
      //   mermaid SVG 节点 id 形如 "flowchart-COLLAPSE_<safeId>-<N>", 截取到首个 "-"(计数器分隔)即为聚合 id。
      svg.querySelectorAll('g.node[id^="flowchart-COLLAPSE_"]').forEach((el) => {
        const id = el.id || ''
        const cut = id.indexOf('-', 'flowchart-COLLAPSE_'.length)
        const collapseId = cut === -1 ? id.substring('flowchart-'.length) : id.substring('flowchart-'.length, cut)
        el.style.display = hiddenCollapseIds.has(collapseId) ? 'none' : ''
      })

      return true
    }

    // [LEGEND 2026-08-07] 图例项点击分组可见性切换回调 (由 useSvgProcessor → annotationOverlay 图例项 click 触发)。
    //   关键: 不能就地改 live 分组对象后传同一引用, 否则 watcher 的 oldVal/newVal 共享同一已被改的
    //   groups → sigVisibility 相等 → updateVisibilityOnly 不触发。正确做法: 深克隆 store 配置、
    //   在克隆上改 visible, 再以新引用替换 → watcher 触发增量隐/显 (updateVisibilityOnly),
    //   同时 LayoutControlPanel 监听同一 store 配置 → 面板树双向同步。与面板侧隐藏路径保持一致。
    //   [FIX 2026-08-07 v2] 除 store 替换外, 直接调用 updateVisibilityOnly 强制立即隐/显图表,
    //     不依赖 store → computed → prop → watcher 的传播链 (该链在部分场景下不触发)。
    const handleToggleGroupVisible = (name, hidden, groups) => {
      const cfg = configStore.layoutControlConfig
      if (!cfg || !Array.isArray(groups) || groups.length === 0) return
      const ids = new Set(groups.map(g => g.id || g.elementCode))
      // hidden=true 表示"隐藏", 故设置 visible = !hidden
      const visibleState = !hidden
      // [SCOPE 2026-08-07] 隐藏时对象范围保护: 范围内要素及其祖先链保持可见 (修复问题2)。
      //   - 直接范围分组 (isDirectScopeGroup, 如采购供应): 自身不隐藏, 且整棵子树不递归隐藏
      //     (其业务对象均为范围内要素)。
      //   - 范围祖先分组 (isScopeAncestor, 如供应链计划/供应链云): 自身不隐藏, 但仍递归,
      //     使非范围内子孙被隐藏、范围内链保持可见。
      //   这样 store/面板/渲染 三处状态一致, 避免"只在 updateVisibilityOnly 的 SVG 层做保护"
      //   导致重渲染后范围内要素又被隐藏。
      const setVis = (g, v) => {
        if (!g || typeof g !== 'object') return
        const hiding = v === false
        const directScope = hiding && isDirectScopeGroup(g)
        const ancestorScope = hiding && isScopeAncestor(g)
        if (!directScope && !ancestorScope) {
          g.visible = v
        }
        // 直接范围分组: 整棵子树受保护, 不再递归 (范围内业务对象保持可见)
        if (directScope) return
        // 祖先分组或普通分组: 递归 (普通分组整棵隐藏; 祖先分组隐藏非范围内子孙)
        if (Array.isArray(g.children)) g.children.forEach(c => setVis(c, v))
        if (Array.isArray(g.containers)) g.containers.forEach(c => setVis(c, v))
      }
      const walk = (list) => {
        ;(list || []).forEach(g => {
          if (!g || typeof g !== 'object') return
          if (ids.has(g.id) || ids.has(g.elementCode)) setVis(g, visibleState)
          walk(g.children)
          walk((g.containers || []).filter(c => c && typeof c === 'object'))
        })
      }
      const newConfig = JSON.parse(JSON.stringify(cfg))
      walk(newConfig.groups)
      // 1) 先以新引用替换 store → 触发面板树(LayoutControlPanel)双向同步。
      //    必须放在 updateVisibilityOnly 之前(或其异常不影响面板同步), 否则 SVG 隐藏
      //    若抛错会跳过 store 更新, 面板不同步而图表已部分隐藏(表现为"图表OK面板没动")。
      configStore.updateLayoutControlConfig(newConfig)
      // 2) 直接增量隐/显图表 (最可靠, 不依赖 watcher 传播链); 独立 try/catch 隔离异常。
      try {
        updateVisibilityOnly(newConfig.groups)
      } catch (e) {
        console.error('[LEGEND] updateVisibilityOnly failed', e)
      }
    }

    // [CTX 2026-08-07] 右键上下文菜单
    const ctxMenu = reactive({
      visible: false,
      x: 0,
      y: 0,
      groupTitle: '',
      // [FIX 2026-08-08] 新增 elementCode: 用于 executeContextMenuAction 中精确匹配分组,
      //   避免仅靠 groupTitle (标题) 匹配可能因标题重名/空格/编码差异导致 findGroupInTree 找不到.
      elementCode: '',
      // [CTX-GLOBAL 2026-08-10] 空白区域右键 = 全局展开层级菜单 (替代 GlobalToolbar 展开层级下拉).
      //   true 时 groupTitle 显示"展开层级", 各选项为 expandGlobal:<key>.
      isGlobal: false,
      items: []  // { key: string, label: string }
    })

    // 查找分组树中匹配的节点
    function findGroupInTree(list, matcher) {
      if (!Array.isArray(list)) return null
      for (const g of list) {
        if (!g || typeof g !== 'object') continue
        if (matcher(g)) return g
        let found = findGroupInTree(g.children, matcher)
        if (found) return found
        found = findGroupInTree(g.containers, matcher)
        if (found) return found
      }
      return null
    }

    // 根据 SVG target 识别分组元素
    function identifyGroupFromSvg(target) {
      if (!target) return null
      // [FIX 2026-08-07] 持续向上遍历直到找到 cluster 或 node 的 g 元素
      // 右键可能点击到 label/text/rect 等内部元素，最近的 g 是 label 而非 cluster/node
      let el = target
      while (el && el !== document.body) {
        while (el && el.tagName !== 'g' && el !== document.body) {
          el = el.parentElement
        }
        if (!el || el === document.body) {
          debug.debugLog('[CTX] identifyGroupFromSvg: reached body, no g element found')
          return null
        }
        const id = el.getAttribute('id') || ''
        const cls = el.getAttribute('class') || ''
        debug.debugLog('[CTX] identifyGroupFromSvg: found g element, id=' + id + ', class=' + cls)

        // [FIX 2026-08-07] 精确匹配 class 名（split 避免 nodes/cluster-label 等子串误匹配）
        const classList = cls.trim().split(/\s+/)
        const isCluster = classList.includes('cluster') || classList.includes('subgraph')
        const isNode = classList.includes('node')
        if (!isCluster && !isNode) {
          debug.debugLog('[CTX] identifyGroupFromSvg: not a cluster/subgraph or node, continuing up')
          el = el.parentElement
          continue
        }

        // [FIX 2026-08-07 v2] 优先使用 data-container-code 属性获取容器编码
        //   SVG 渲染后 useSvgProcessor 会在 g.cluster 上设置 data-container-code="SCM"，
        //   避免从 ID "G_D_SCM" 解析失败的问题（G_D_/G_SD_/G_SM_ 前缀未完整剥离）。
        // [FIX 2026-08-10] BO 叶子节点 (g.node) 只有 data-code (业务编码, 如 PLD003),
        //   没有 data-container-code. 旧逻辑回退到从内部节点 id 解析 (如 flowchart-N17-11 → N17),
        //   导致 BO 右键 elementCode=N17 而非 PLD003 → "关系高亮"对 BO 完全无效.
        //   现回退到 data-code, 保证 BO 右键能拿到业务编码.
        let elementCode = el.getAttribute('data-container-code') || el.getAttribute('data-code') || ''

        if (!elementCode) {
          // 提取分组 ID: cluster-xxx → xxx
          let groupId = ''
          if (id.startsWith('cluster-')) {
            groupId = id.slice(8)
          } else if (id.startsWith('flowchart-')) {
            groupId = id.slice(10)
          } else if (id.startsWith('node-')) {
            groupId = id.slice(5)
          } else {
            groupId = id
          }
          if (!groupId) {
            // cluster-label 等无 ID 的子元素，继续向上找父 cluster
            debug.debugLog('[CTX] identifyGroupFromSvg: empty groupId, continuing up to parent')
            el = el.parentElement
            continue
          }
          debug.debugLog('[CTX] identifyGroupFromSvg: extracted groupId=' + groupId)

          // [FIX 2026-08-07] 处理 Mermaid 特殊 ID 格式，提取真实的 elementCode
          //   COLLAPSE_SD_MM-28 → SD_MM, G_SCM → SCM
          // [FIX 2026-08-07 v2] COLLAPSE 节点 ID 可能含 SM_/SD_/D_ 前缀
          //   (如 COLLAPSE_SM_SCP, COLLAPSE_SD_SCP, COLLAPSE_D_SCM),
          //   必须进一步剥离组类型前缀, 否则 findGroupInTree 找不到实际 elementCode (如 SCP).
          elementCode = groupId
          if (elementCode.startsWith('COLLAPSE_')) elementCode = elementCode.slice(9)
          // [CTX 2026-08-07] 剥离 COLLAPSE 节点中的组类型前缀 (SM_/SD_/D_)
          // [FIX 2026-08-09] 前缀长度不一: SM_/SD_ 为 3 字符, D_(领域) 为 2 字符.
          //   旧实现统一 slice(3) 会把 D_SCM 错切为 CM(吃掉编码首字符 S), 导致领域折叠节点
          //   (COLLAPSE_D_*) 的 elementCode 无法匹配到真实分组, 双击/右键均静默失效.
          if (elementCode.startsWith('SM_')) elementCode = elementCode.slice(3)
          else if (elementCode.startsWith('SD_')) elementCode = elementCode.slice(3)
          else if (elementCode.startsWith('D_')) elementCode = elementCode.slice(2)
          if (elementCode.startsWith('G_')) elementCode = elementCode.slice(2)
          const dashIdx = elementCode.lastIndexOf('-')
          if (dashIdx > 0 && /^\d+$/.test(elementCode.slice(dashIdx + 1))) {
            elementCode = elementCode.slice(0, dashIdx)
          }
          if (elementCode !== groupId) {
            debug.debugLog('[CTX] identifyGroupFromSvg: normalized elementCode=' + elementCode)
          }
        } else {
          debug.debugLog('[CTX] identifyGroupFromSvg: using data-container-code=' + elementCode)
        }

        // [FIX 2026-08-08 v2] 优先使用 effectiveLayoutControlConfig (渲染所用分组),
        //   回退 configStore.layoutControlConfig.
        //   根因: 右键菜单识别分组时, configStore 可能为空 (初始 {enabled:false, groups:[]}),
        //   而渲染用的 props.layoutControlConfig (来自 EmbeddedChartView 的 computed) 含正确的分组.
        //   用 effectiveLayoutControlConfig.value 确保与渲染分组一致.
        const ctxCfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
        if (!ctxCfg || !Array.isArray(ctxCfg.groups)) {
          debug.debugLog('[CTX] identifyGroupFromSvg: no groups in config')
          return null
        }
        debug.debugLog('[CTX] identifyGroupFromSvg: groups count=' + ctxCfg.groups.length)
        const group = findGroupInTree(ctxCfg.groups, g => {
          const key = g.elementCode || g.id
          return key === elementCode || g.title === elementCode
        })
        if (group) {
          debug.debugLog('[CTX] identifyGroupFromSvg: matched group:', group.title || group.elementCode || group.id)
          return group
        }
        // [REL-HL 2026-08-10] 业务对象节点 (g.node[data-code]) 不在分组树中 (分组树仅含
        //   领域/子领域/服务模块容器), 直接右键到 BO 时返回合成分组, 以展示"关系高亮"菜单.
        //   BO 无折叠/展开子层级, getContextMenuItems 对 businessObject 仅返回"关系高亮".
        if (isNode && elementCode) {
          debug.debugLog('[CTX] identifyGroupFromSvg: BO node fallback, elementCode=' + elementCode)
          return {
            elementCode,
            title: elementCode,
            groupType: 'businessObject',
            isBO: true,
            collapsed: false
          }
        }
        debug.debugLog('[CTX] identifyGroupFromSvg: no matching group for elementCode=' + elementCode + ', continuing up')
        el = el.parentElement
      }
      return null
    }

    // 根据分组类型生成菜单项
    // [REL-HL 2026-08-10] 所有节点 (领域/子领域/服务模块/业务对象) 均提供"关系高亮":
    //   选择后高亮该节点相关的所有连线及相连节点 (见 highlightRelations).
    function getContextMenuItems(group) {
      const gtype = (group.groupType || '').toLowerCase()
      if (gtype === 'domain') {
        return [
          { key: 'highlightRelations', label: '关系高亮' },
          { key: 'collapse', label: '折叠' },
          { key: 'expandSub', label: '展开到子领域' },
          { key: 'expandSM', label: '展开到服务模块' },
          { key: 'expandBO', label: '展开到业务对象' }
        ]
      }
      if (gtype === 'servicemodule' || gtype === 'service_module') {
        return [
          { key: 'highlightRelations', label: '关系高亮' },
          { key: 'collapse', label: '折叠' },
          { key: 'expandBO', label: '展开到业务对象' }
        ]
      }
      if (gtype === 'subdomain' || gtype === 'sub_domain') {
        return [
          { key: 'highlightRelations', label: '关系高亮' },
          { key: 'collapse', label: '折叠' },
          { key: 'expandSM', label: '展开到服务模块' },
          { key: 'expandBO', label: '展开到业务对象' }
        ]
      }
      if (gtype === 'businessobject' || gtype === 'business_object' || gtype === 'bo') {
        // 业务对象节点: 仅提供"关系高亮" (BO 无折叠/展开子层级)
        return [
          { key: 'highlightRelations', label: '关系高亮' }
        ]
      }
      // 自定义等其他类型: 不展示菜单
      return []
    }

    function handleContextMenu(event) {
      debug.debugLog('[CTX] right-click on', event.target.tagName, event.target.id, event.target.className)
      const group = identifyGroupFromSvg(event.target)
      debug.debugLog('[CTX] identifyGroupFromSvg result:', group ? group.title || group.elementCode || group.id : 'null')
      if (!group) {
        // [CTX-GLOBAL 2026-08-10] 空白区域右键: 展示全局"展开层级"菜单 (替代 GlobalToolbar 展开层级下拉).
        //   用户需求: 在图表空白处右键即可切换 领域/子领域/服务模块/业务对象 全局展开层级.
        //   与 services/expandLevel.js EXPAND_LEVELS 的 key 一一对应.
        ctxMenu.isGlobal = true
        ctxMenu.groupTitle = '整体展开层级'
        ctxMenu.elementCode = ''
        ctxMenu.items = [
          { key: 'expandGlobal:domain', label: '展开到领域' },
          { key: 'expandGlobal:subDomain', label: '展开到子领域' },
          { key: 'expandGlobal:serviceModule', label: '展开到服务模块' },
          { key: 'expandGlobal:businessObject', label: '展开到业务对象' }
        ]
        ctxMenu.x = event.clientX
        ctxMenu.y = event.clientY
        ctxMenu.visible = true
        debug.recordInteraction('contextmenu', {
          group: { title: '展开层级', global: true },
          items: ctxMenu.items.map(i => i.key),
          x: event.clientX, y: event.clientY
        })
        return
      }
      ctxMenu.isGlobal = false
      const items = getContextMenuItems(group)
      if (items.length === 0) {
        ctxMenu.visible = false
        return
      }
      ctxMenu.groupTitle = group.title || group.name || group.elementCode || group.id || ''
      ctxMenu.elementCode = group.elementCode || group.id || ''
      ctxMenu.items = items
      ctxMenu.x = event.clientX
      ctxMenu.y = event.clientY
      ctxMenu.visible = true
      // [P1 2026-08-08] 记录右键交互
      debug.recordInteraction('contextmenu', {
        group: { title: group.title || group.elementCode || group.id, collapsed: group.collapsed, groupType: group.groupType },
        items: items.map(i => i.key),
        x: event.clientX, y: event.clientY
      })
    }

    // [DBL 2026-08-08] 双击 toggle: 已折叠 → 展开下一层, 已展开 → 折叠
    //   之前仅处理已折叠节点 (展开), 不处理已展开节点 (折叠), 导致双击展开后无法再次双击折叠。
    function handleDblClick(event) {
      // [DBG 2026-08-08 v4] 记录 event.target 详细 DOM 路径, 排查真实双击与 debug.testDblClick 的差异
      const et = event.target
      const etPath = []
      let cur = et
      while (cur && cur !== document.body) {
        etPath.push((cur.tagName || '') + (cur.id ? '#' + cur.id : '') + (cur.className ? '.' + (typeof cur.className === 'string' ? cur.className : '') : ''))
        cur = cur.parentElement
      }
      etPath.reverse()
      debug.debugLog('[DBL] handleDblClick: event.target=' + (et.tagName || '') + (et.id ? '#' + et.id : '') + ', path=' + etPath.join(' > '))
      const group = identifyGroupFromSvg(et)
      debug.debugLog('[DBL] handleDblClick: group=', group ? group.title || group.elementCode || group.id : 'null', 'collapsed=', group?.collapsed, 'groupType=', group?.groupType)
      if (!group) return

      // [P1 2026-08-08] 记录双击交互
      debug.recordInteraction('dblclick', {
        target: et.tagName + (et.id ? '#' + et.id : ''),
        group: { title: group.title || group.elementCode || group.id, collapsed: group.collapsed, groupType: group.groupType }
      })

      // 设 ctxMenu 供 executeContextMenuAction 读取
      ctxMenu.groupTitle = group.title || group.name || group.elementCode || group.id || ''
      ctxMenu.elementCode = group.elementCode || group.id || ''

      if (group.collapsed === true) {
        // 已折叠 → 展开到下一层 (领域→子领域, 子领域→服务模块, 服务模块→业务对象)
        const gtype = (group.groupType || '').toLowerCase()
        let expandKey = ''
        if (gtype === 'domain') {
          expandKey = 'expandSub'
        } else if (gtype === 'subdomain' || gtype === 'sub_domain') {
          expandKey = 'expandSM'
        } else if (gtype === 'servicemodule' || gtype === 'service_module') {
          expandKey = 'expandBO'
        }
        if (!expandKey) {
          debug.debugLog('[DBL] handleDblClick: no expandKey for gtype=' + gtype)
          return
        }
        debug.debugLog('[DBL] handleDblClick: expanding with key=' + expandKey)
        executeContextMenuAction(expandKey)
      } else {
        // 已展开 → 折叠
        debug.debugLog('[DBL] handleDblClick: collapsing')
        executeContextMenuAction('collapse')
      }
    }

    // 在分组子树内展开到指定层级 (就地修改 collapsed)
    // [FIX 2026-08-09 v4] 语义修正: 子分组用 lv >= targetLevel 折叠"目标层级自身及更深".
    //   根因: 2026-08-08 改成 > 后, "展开到服务模块"(targetLevel=2)时服务模块(lv=2)
    //   因 2>2=false 被展开, 其业务对象随之显示 → 实际展开到了业务对象层级(用户反馈错误).
    //   与 services/expandLevel.js expandGroupsToLevel 的 >= 语义保持一致:
    //     展开到服务模块 = 子领域展开、服务模块折叠为聚合节点、业务对象隐藏.
    function expandSubtreeToLevel(group, targetLevel) {
      const currentLevel = groupLevelOf(group)
      // 目标分组自身(被点击钻取的容器)应展开, 露出其子层级.
      group.collapsed = currentLevel > targetLevel
      // 递归处理 children/containers: 目标层级自身及更深折叠为聚合节点.
      const recurse = (list) => {
        if (!Array.isArray(list)) return
        for (const g of list) {
          if (!g || typeof g !== 'object') continue
          const lv = groupLevelOf(g)
          g.collapsed = lv >= targetLevel
          recurse(g.children)
          recurse(g.containers)
        }
      }
      recurse(group.children)
      recurse(group.containers)
    }

    // [CTX-GLOBAL 2026-08-10] 全局展开到指定层级 (空白区域右键菜单).
    //   替代 GlobalToolbar 的展开层级下拉: 逻辑与 RelationshipManagement.onExpandLevelChange 一致,
    //   写 store.setExpandLevel(key) (expandLevel + expandLevelUserSet=true) + 就地应用
    //   expandGroupsToLevel 到当前渲染分组, 并 updateLayoutControlConfig 触发重渲染.
    //   key ∈ EXPAND_LEVELS.key: domain / subDomain / serviceModule / businessObject.
    function executeGlobalExpand(key) {
      debug.debugLog('[CTX-GLOBAL] executeGlobalExpand: key=' + key)
      configStore.setExpandLevel(key)
      const cfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
      if (cfg && Array.isArray(cfg.groups)) {
        const newConfig = JSON.parse(JSON.stringify(cfg))
        expandGroupsToLevel(newConfig.groups, key)
        configStore.updateLayoutControlConfig(newConfig)
      }
      // [P1 2026-08-08] 记录菜单操作交互
      debug.recordInteraction('menu-click', { key, global: true })
    }

    // [REL-HL 2026-08-10] 关系高亮样式管理.
    //   [FIX 2026-08-10] 取消高亮后节点"变成中性色": 高亮时 label.style.fill / rect.style.stroke
    //   会覆盖颜色分组写入的内联填充色; 旧清除逻辑用 removeProperty 直接删掉内联样式, 导致节点
    //   丢失分组颜色回到中性灰. 现改为"高亮前保存原始内联样式 → 清除时恢复原值", 而非删除.
    //   用 WeakMap 保存 (key=元素), 元素随 SVG 重渲染被 GC, 不泄漏.
    //   [FIX 2026-08-10 v2] 恢复时丢失 `!important` 优先级:
    //     颜色分组 fill 用 `style.setProperty('fill', color, 'important')` 写入 (见 useMermaidColors),
    //     因为 mermaid 语法层 `classDef default fill:#fafafa` 也是 `!important` 内联 CSS, 非 important 会被压制.
    //     旧恢复逻辑 `setProperty(p, orig[p])` 未带 priority 标志 → fill 降级为普通优先级,
    //     被 `.default > rect { fill:#fafafa !important }` 覆盖 → 节点回到中性灰 #fafafa.
    //     修复: 保存时同时记录 priority (getPropertyPriority), 恢复时原样带 priority 写回.
    const relHlOrigStyle = new WeakMap()
    const REL_HL_PROPS = ['filter', 'stroke', 'stroke-width', 'font-weight',
      'font-size', 'fill']
    const saveRelHlOrigStyle = (e) => {
      if (!e || relHlOrigStyle.has(e)) return
      const orig = {}
      REL_HL_PROPS.forEach(p => {
        orig[p] = {
          value: e.style.getPropertyValue(p),
          priority: e.style.getPropertyPriority(p)
        }
      })
      relHlOrigStyle.set(e, orig)
    }
    const restoreRelHlOrigStyle = (e) => {
      if (!e) return
      const orig = relHlOrigStyle.get(e)
      if (orig) {
        REL_HL_PROPS.forEach(p => {
          const o = orig[p]
          if (!o || o.value === '') e.style.removeProperty(p)
          else e.style.setProperty(p, o.value, o.priority)
        })
        relHlOrigStyle.delete(e)
      } else {
        // 无记录 (理论不出现): 兜底删除
        REL_HL_PROPS.forEach(p => e.style.removeProperty(p))
      }
    }

    // [REL-HL DIM 2026-08-10] 相对淡化"非高亮范围"的其余节点/连线, 突出高亮子图。
    //   参考主流图可视化方案 (D3 force graph / AntV G6 / GraphPulse):
    //   目标子图保持全不透明 + 强调 (color/size/shadow), 非目标整体降透明度 (≈0.2~0.3),
    //   形成"聚焦范围内亮、范围外灰"的视觉层级 (research 结论: static highlight + dim 组合最有效).
    const REL_HL_DIM_OPACITY = '0.25'
    const relHlDimOrig = new WeakMap() // el -> 原始 opacity 字符串
    const relHlDimmed = new Set()      // 当前被淡化的元素 (节点 g / cluster / 连线 path)
    const dimElement = (el) => {
      if (!el || relHlDimmed.has(el) || el.hasAttribute('data-rel-hl')) return
      if (!relHlDimOrig.has(el)) relHlDimOrig.set(el, el.style.getPropertyValue('opacity'))
      relHlDimmed.add(el)
      el.style.setProperty('opacity', REL_HL_DIM_OPACITY)
    }
    const restoreDim = (el) => {
      if (!el || !relHlDimmed.has(el)) return
      relHlDimmed.delete(el)
      const orig = relHlDimOrig.get(el)
      if (orig === undefined || orig === '') el.style.removeProperty('opacity')
      else el.style.setProperty('opacity', orig)
      relHlDimOrig.delete(el)
    }

    // [REL-HL 2026-08-10] 清除"关系高亮": 恢复高亮覆盖前的原始内联样式 (而非删除),
    //   确保节点颜色分组的填充色不被破坏.
    function clearRelationsHighlight() {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) return
      svg.querySelectorAll('[data-rel-hl]').forEach(el => {
        el.removeAttribute('data-rel-hl')
        restoreRelHlOrigStyle(el)
        // 节点容器: 子元素 rect/polygon + label 是真正着色点, 必须一并恢复
        el.querySelectorAll('rect, polygon, .nodeLabel, .cluster-label, text').forEach(restoreRelHlOrigStyle)
      })
      // [DIM 2026-08-10] 恢复被相对淡化的其余节点/连线的不透明度
      relHlDimmed.forEach(restoreDim)
    }

    // [REL-HL 2026-08-10] 记录最近一次"关系高亮"应用时间, 供 closeContextMenu 判断
    //   是否属于"点击菜单项触发高亮"的同一事件 (避免误清除刚应用的高亮).
    let lastRelHlAt = 0

    // [REL-HL 2026-08-10] 高亮指定节点相关的所有连线及相连节点 (右键菜单"关系高亮").
    //   直接基于渲染后的 SVG 结构, 不依赖 diagramData.links (折叠后连线已按可见祖先重映射):
    //   - 可见节点: g.node[data-container-code|data-code] (折叠的领域/子领域/服务模块聚合 与 业务对象)
    //   - 连线: g.edgeLabel 文本为 "<源编码>-<目标编码>" (如 "PLAM-DP"), 高亮按此解析端点编码;
    //            edgeLabel 与 g.edges.edgePaths > path 按 document 顺序一一对应.
    //
    // [REL-HL v2 2026-08-10] 修复"高亮关系不完整" (混合颗粒度):
    //   当右键节点是"服务模块等聚合容器"、但其相连边因另一端展开到业务对象而被重映射为
    //   更细颗粒度时, 边标签端点会使用该容器下的 BO 编码 (如折叠需求计划 DP 时, 边标签为
    //   "DP01-SMKQM04" 而非 "DP-SMKQM"). 旧实现仅做端点 === 右键编码 的精确匹配 → DP01 !== DP,
    //   整条边及其另一端的 计划单 都不会被高亮.
    //   修复: 由 domainProducts + nodes.serviceModule 构建"编码→子孙"映射, 计算右键编码的
    //   整棵子树编码集合 scope; 只要边的任一端点 ∈ scope 即视为该节点相关连线. 另一端点
    //   解析到其最近可见祖先后加入高亮节点 (保证跨层级另一端的可见节点也能被高亮).
    //
    // [REL-HL v2 颜色调整 (用户要求)]:
    //   - 连线高亮采用原色 (只加粗 + 轻微描边发光, 不改 stroke 颜色)
    //   - 节点高亮采用"选择后同样的颜色" #FF6B6B (红, 与应用内连线/节点高亮 useTooltip 一致)
    function buildRelHlMaps() {
      // code → Set(直接子 code)
      const childrenMap = new Map()
      // code → 直接父 code
      const parentMap = new Map()
      const addChild = (p, c) => {
        if (!p || !c || p === c) return
        if (!childrenMap.has(p)) childrenMap.set(p, new Set())
        childrenMap.get(p).add(c)
        parentMap.set(c, p)
      }
      // 1) domainProducts: 领域 → 模块 → 子模块 → BO
      ;(props.diagramData?.domainProducts || []).forEach(domain => {
        ;(domain.modules || []).forEach(module => {
          addChild(domain.code, module.code)
          ;(module.submodules || []).forEach(sub => {
            addChild(module.code, sub.code)
            ;(sub.businessObjects || []).forEach(bo => addChild(sub.code, bo.code))
          })
          ;(module.businessObjects || []).forEach(bo => addChild(module.code, bo.code))
        })
        ;(domain.businessObjects || []).forEach(bo => addChild(domain.code, bo.code))
      })
      // 2) nodes.serviceModule (BO → 服务模块编码), 兜底覆盖 domainProducts 未含的 BO
      ;(props.diagramData?.nodes || []).forEach(n => {
        const sm = n.serviceModule
        if (sm && n.code) addChild(sm, n.code)
      })
      return { childrenMap, parentMap }
    }

    // 计算 root 的整棵子树编码集合 (含自身), 供"相关边"匹配.
    function subtreeCodes(root, childrenMap) {
      const result = new Set([root])
      const queue = [root]
      while (queue.length) {
        const cur = queue.shift()
        const kids = childrenMap.get(cur)
        if (!kids) continue
        kids.forEach(k => {
          if (!result.has(k)) { result.add(k); queue.push(k) }
        })
      }
      return result
    }

    // 将端点编码解析到最近可见祖先 (用于另一端点未展开为独立节点时, 高亮其可见聚合容器)
    function resolveVisibleAncestor(code, codeToEl, parentMap) {
      if (!code) return null
      if (codeToEl.has(code)) return code
      let cur = code
      let guard = 0
      while (cur && guard < 12) {
        cur = parentMap.get(cur)
        guard++
        if (cur && codeToEl.has(cur)) return cur
      }
      return null
    }

    function highlightRelations(code) {
      clearRelationsHighlight()
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg || !code) {
        debug.debugLog('[REL-HL] highlightRelations: no svg or code, abort')
        return
      }
      const codeStr = String(code)
      debug.debugLog('[REL-HL] highlightRelations: code=' + codeStr)

      // [FIX 2026-08-10] 先清除 useTooltip 的"选择高亮"再应用关系高亮.
      //   否则 saveRelHlOrigStyle 会把选择高亮样式 (stroke/filter/fontWeight) 误存为"原始样式",
      //   点击空白清除关系高亮时 restoreRelHlOrigStyle 会把这些样式错误恢复 → 该节点残留高亮.
      //   注意: 必须用 svgProcessor 内部 tooltip 实例 (选择高亮保存在其中), 而非本组件 tooltip.
      svgProcessor.clearSelectionHighlight?.()
      // [FIX 2026-08-10] 同时清除 annotationOverlay 的"节点点击高亮" (.annotation-highlighted).
      //   用户"先点击节点 DP01" 触发的是 annotationOverlay.highlightTargetElement 的独立高亮,
      //   与 useTooltip 选择高亮是两套机制。同样需在关系高亮应用前清掉, 否则其样式会被误存为
      //   "原始样式", 清除关系高亮时恢复 → 该节点残留高亮.
      svgProcessor.clearAnnotationHighlight?.(svg)

      // 1) 解析边标签 "<a>-<b>" 得到两个端点编码
      const parseEdge = (text) => {
        const parts = (text || '').split('-').map(p => p.trim())
        if (parts.length < 2) return ['', '']
        return [parts[0], parts[parts.length - 1]]
      }

      // 2) 收集可见节点元素 (code -> el): g.node 优先 data-container-code, 回退 data-code
      const codeToEl = new Map()
      svg.querySelectorAll('g.node').forEach(el => {
        const c = el.getAttribute('data-container-code') || el.getAttribute('data-code')
        if (c && !codeToEl.has(c)) codeToEl.set(c, el)
      })
      // 领域容器 (g.cluster[data-container-code]) 也可作为高亮目标 (右键领域时自身高亮)
      svg.querySelectorAll('g.cluster[data-container-code]').forEach(el => {
        const c = el.getAttribute('data-container-code')
        if (c && !codeToEl.has(c)) codeToEl.set(c, el)
      })

      // 3) [v2] 构建层级映射, 计算右键编码的子树 scope (含自身), 供相关边匹配
      const { childrenMap, parentMap } = buildRelHlMaps()
      const scope = subtreeCodes(codeStr, childrenMap)
      debug.debugLog('[REL-HL] scope subtree size=' + scope.size, [...scope].slice(0, 12))

      // 4) 遍历连线: edgeLabel ↔ edgePath 按 document 顺序对应
      const edgeLabels = Array.from(svg.querySelectorAll('g.edgeLabel'))
      const edgePaths = Array.from(svg.querySelectorAll('g.edges.edgePaths > path'))
      const connected = new Set([codeStr])
      const hlEdges = new Set()
      edgeLabels.forEach((labelEl, idx) => {
        const [a, b] = parseEdge(labelEl.textContent || '')
        const aIn = a && scope.has(a)
        const bIn = b && scope.has(b)
        if (aIn || bIn) {
          const pathEl = edgePaths[idx]
          if (pathEl) hlEdges.add(pathEl)
          // 另一端点解析到最近可见祖先后加入高亮节点
          if (aIn && b) { const v = resolveVisibleAncestor(b, codeToEl, parentMap); if (v) connected.add(v) }
          if (bIn && a) { const v = resolveVisibleAncestor(a, codeToEl, parentMap); if (v) connected.add(v) }
        }
      })
      debug.debugLog('[REL-HL] connected nodes:', [...connected], '| edges:', hlEdges.size)

      // 5) 高亮相连的可见节点 (含自身) — 采用"选择后同样的颜色" #FF6B6B (红),
      //    与应用内连线/节点高亮 (useTooltip.highlightNode) 一致.
      const applyNodeHl = (el) => {
        if (el.hasAttribute('data-rel-hl')) return
        el.setAttribute('data-rel-hl', '1')
        const rect = el.querySelector('rect, polygon')
        if (rect) {
          saveRelHlOrigStyle(rect)
          rect.style.filter = 'drop-shadow(0 0 10px rgba(255, 107, 107, 0.85))'
          rect.style.stroke = '#FF6B6B'
          rect.style.strokeWidth = '2px'
        }
        const label = el.querySelector('.nodeLabel, .cluster-label, text')
        if (label) {
          saveRelHlOrigStyle(label)
          label.style.fontWeight = 'bold'
          label.style.fill = '#FF6B6B'
        }
      }
      connected.forEach(c => {
        const el = codeToEl.get(c)
        if (el) applyNodeHl(el)
      })

      // 6) 高亮相连连线 — 采用原色 (不改 stroke, 仅加粗 + 轻微发光使其醒目)
      hlEdges.forEach(pathEl => {
        if (!pathEl.hasAttribute('data-rel-hl')) {
          pathEl.setAttribute('data-rel-hl', '1')
          saveRelHlOrigStyle(pathEl)
          pathEl.style.strokeWidth = '3px'
          pathEl.style.filter = 'drop-shadow(0 0 4px rgba(0, 0, 0, 0.35))'
        }
      })

      // 7) [DIM 2026-08-10] 相对淡化"非高亮范围"的其余节点/连线, 突出高亮子图。
      //   高亮子图保持全不透明, 范围外整体降透明度 (0.25), 形成"范围内亮、范围外灰"层级。
      //   仅淡化可见节点 (codeToEl) 中不属于 connected 的, 以及未被高亮的连线 path。
      const dimSet = new Set(connected)
      codeToEl.forEach((el, c) => {
        if (!dimSet.has(c)) dimElement(el)
      })
      edgePaths.forEach(pathEl => {
        if (!hlEdges.has(pathEl)) dimElement(pathEl)
      })
      // [DIM 2026-08-10] 关系连线名称标题 (edgeLabel) 也随其连线一并淡化。
      //   edgeLabel 与 edgePath 按 document 顺序一一对应, 连线被淡化则该标题也淡化。
      edgeLabels.forEach((labelEl, idx) => {
        const pathEl = edgePaths[idx]
        if (!pathEl || !hlEdges.has(pathEl)) dimElement(labelEl)
      })

      debug.recordInteraction('highlight-relations', { code: codeStr, connected: [...connected], edges: hlEdges.size, dimmed: relHlDimmed.size })
      lastRelHlAt = Date.now()
    }

    function executeContextMenuAction(key) {
      ctxMenu.visible = false
      // [CTX-GLOBAL 2026-08-10] 空白区域右键的全局展开层级项 (expandGlobal:<key>)
      //   直接走全局展开, 不依赖具体分组.
      if (typeof key === 'string' && key.startsWith('expandGlobal:')) {
        executeGlobalExpand(key.slice('expandGlobal:'.length))
        return
      }
      // [REL-HL 2026-08-10] "关系高亮": 高亮该节点相关的所有连线及相连节点.
      //   仅依赖 ctxMenu.elementCode (右键节点的编码), 无需在分组树中定位目标.
      if (key === 'highlightRelations') {
        highlightRelations(ctxMenu.elementCode)
        return
      }
      // [FIX 2026-08-08 v2] 与 identifyGroupFromSvg 保持一致: 优先用 effectiveLayoutControlConfig
      const ctxCfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
      debug.debugLog('[CTX] executeContextMenuAction: key=' + key + ', title=' + ctxMenu.groupTitle + ', code=' + ctxMenu.elementCode + ', hasCfg=' + !!ctxCfg)
      if (!ctxCfg || !Array.isArray(ctxCfg.groups)) return

      // 从当前 ctxMenu 的 groupTitle/elementCode 重新查找分组 (因为配置可能已变更)
      const title = ctxMenu.groupTitle
      const code = ctxMenu.elementCode
      const group = findGroupInTree(ctxCfg.groups, g => {
        const gt = g.title || g.name || g.elementCode || g.id
        return gt === title || (code && (g.elementCode === code || g.id === code))
      })
      debug.debugLog('[CTX] executeContextMenuAction: found group in ctxCfg=' + (group ? group.title || group.elementCode || group.id : 'null'))
      if (!group) return

      const newConfig = JSON.parse(JSON.stringify(ctxCfg))
      // 在新配置中查找同名分组
      const target = findGroupInTree(newConfig.groups, g => {
        const gt = g.title || g.name || g.elementCode || g.id
        return gt === title || (code && (g.elementCode === code || g.id === code))
      })
      debug.debugLog('[CTX] executeContextMenuAction: found target in newConfig=' + (target ? target.title || target.elementCode || target.id : 'null') + ', collapsed before=' + target?.collapsed)
      if (!target) return

      if (key === 'collapse') {
        target.collapsed = true
      } else if (key === 'expandSub') {
        // 展开到子领域: targetLevel = 1 (subDomain)
        expandSubtreeToLevel(target, 1)
      } else if (key === 'expandSM') {
        // 展开到服务模块: targetLevel = 2 (service module)
        expandSubtreeToLevel(target, 2)
      } else if (key === 'expandBO') {
        // 展开到业务对象: targetLevel = 99 (全展开)
        expandSubtreeToLevel(target, 99)
      }

      debug.debugLog('[CTX] executeContextMenuAction: target collapsed after=' + target.collapsed + ', updating store')
      // 更新 store 触发重渲染
      configStore.updateLayoutControlConfig(newConfig)
      // [CTX-FIX 2026-08-09] 标记用户已手动调整分组折叠/展开.
      //   否则渲染层 layoutControlConfig computed 仍会按对象范围套用默认展开
      //   (applyDefaultExpandByScope / expandGroupsToLevel), 无条件覆盖用户此处的 collapsed,
      //   导致双击/右键"折叠/展开"后图表无任何变化.
      configStore.markGroupManualSet()
      // [P1 2026-08-08] 记录菜单操作交互
      debug.recordInteraction('menu-click', {
        key,
        group: { title: ctxMenu.groupTitle, code: ctxMenu.elementCode },
        collapsed: target.collapsed
      })

      // [HIGHLIGHT 2026-08-09] 展开/折叠后保持被操作元素的高亮态.
      //   updateLayoutControlConfig 触发 layoutControlConfig watch → renderMermaid (异步重建 SVG),
      //   高亮 class 会丢失. 这里缓存被操作分组的目标, 待渲染完成在 renderMermaid.then 内重新高亮.
      const highlightId = ctxMenu.elementCode || target.elementCode || target.id
      if (highlightId) {
        pendingHighlightTarget = { id: highlightId, type: 'container' }
      }
    }

    // 点击页面其他位置关闭右键菜单 + 批量解除关系高亮
    // [REL-HL v2 2026-08-10] 点击图表空白区域 (非节点/连线/右键菜单) 时批量清除关系高亮.
    //   用 lastRelHlAt 防止"点击右键菜单项触发高亮"的同一事件在冒泡到 document 时,
    //   因菜单项已从 DOM 卸载 (closest('.mermaid-ctx-menu') 失效) 而误把刚应用的高亮清掉.
    function closeContextMenu(e) {
      if (ctxMenu.visible) {
        const wrapper = mermaidWrapper.value
        if (wrapper && wrapper.contains(e.target)) {
          // 在 mermaid-wrapper 内的点击, 如果是右键菜单元素本身则忽略
          const menuEl = wrapper.querySelector('.mermaid-ctx-menu')
          if (menuEl && menuEl.contains(e.target)) return
        }
        ctxMenu.visible = false
      }
      const hasClosest = e.target && typeof e.target.closest === 'function'
      const content = hasClosest ? e.target.closest('.mermaid-content') : null
      if (content && Date.now() - lastRelHlAt > 400
          && !e.target.closest('g.node, g.cluster, g.edgeLabel, g.edgePath, g.edges, .mermaid-ctx-menu')) {
        clearRelationsHighlight()
      }
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
          // [FIX 2026-08-02] 结构 diff 需忽略颜色派生字段 (color/textColor/isCenter):
          //   统一管道 colorize 会把它们烘进节点对象, 若直接比对, 切换颜色分组/配色时
          //   nodesChanged=true → 走全量 renderMermaid (mermaid.run 重排 + 缩放重置),
          //   而升级前节点无这些字段 → 走 updateColorsOnly 增量变色 (直接改 SVG fill)。
          //   颜色增量路径 (updateColorsOnly) 基于 nodeColorMappings + 当前 colorGroupBy/
          //   colorScheme/customColors 重算, 不依赖节点内烘焙色, 因此忽略是安全的。
          const stripColorDerived = (list) => (list || []).map((n) => {
            if (!n || typeof n !== 'object') return n
            const { color, textColor, isCenter, ...rest } = n
            return rest
          })
          const nodesChanged = JSON.stringify(stripColorDerived(newVal.nodes)) !== JSON.stringify(stripColorDerived(oldVal.nodes))
          const linksChanged = JSON.stringify(newVal.links) !== JSON.stringify(oldVal.links)
          const textColorChanged = newVal?.textColor !== oldVal?.textColor
          // [FIX 2026-08-10] 颜色字段 (colorGroupBy/colorScheme/centerScopeHighlight/customColors)
          //   统一用 colorTracker.changed 基于 last* 快照对比, 而非失效的 oldVal.
          //   根因: centerScopeHighlight 走"原地修改"(引用不变), deep watch 时 oldVal===newVal,
          //   基于 oldVal 的 diff 恒 false → 颜色变化识别失效 → 恒全量 renderMermaid().
          //   tracker 用 last* 快照对比, 任何颜色字段(含未来改原地修改的)都能正确识别
          //   → 走 updateColorsOnly 增量变色. textColor 不走原地修改且 tracker 不含此字段,
          //   故保留 oldVal 判断.
          const colorChanged = colorTracker.changed(newVal)
          const colorConfigChanged = colorChanged.colorGroupBy || colorChanged.customColors
            || colorChanged.colorScheme || colorChanged.centerScopeHighlight

          // 如果节点和连线没变，只是颜色相关配置变化，则只更新颜色
          if (!nodesChanged && !linksChanged && (colorConfigChanged || textColorChanged)) {
            // 如果只是文字颜色变化，不需要重新生成颜色映射
            const onlyTextChanged = textColorChanged && !colorConfigChanged
            if (onlyTextChanged) {
              const svg = mermaidContainer.value?.querySelector('svg')
              if (svg) {
                svgStyle.updateNodeStyles(svg, newVal?.textColor || 'black')
                svgStyle.updateClusterStyles(svg, newVal?.textColor || 'black')
              }
              return
            }
            const updated = updateColorsOnly()
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

    // [FIX 2026-08-04] 监听 layoutControlConfig 变化 (用户在布局设置面板调整方向/引擎/分组)
    //   之前无此 watch, 用户切换布局方向或禁用分组后图表不重新渲染.
    // [FIX 2026-08-04 v2] 颜色变更 (colorScheme/colorGroupBy/centerScopeHighlight) 会让
    //   generateDiagram() → 新 diagramData → layoutControlConfig computed 重新求值 →
    //   返回新对象. 但布局字段 (direction/engine/groups结构) 并未改变, 此时应由
    //   diagramData watch 的 updateColorsOnly 增量路径处理, 不能走全量 renderMermaid.
    //   方案: 只在布局相关字段实际变化时才触发 renderMermaid.
    watch(
      () => props.layoutControlConfig,
      (newVal, oldVal) => {
        if (!newVal || !oldVal || !props.diagramData || !mermaidContainer.value) return
        // 方向或引擎变化 → 全量重渲染
        if (newVal.overallDirection !== oldVal.overallDirection ||
            newVal.layoutEngine !== oldVal.layoutEngine) {
          // [FIX 2026-08-04] 方向/引擎切换也需在 mermaid.run() 前重置 zoom transform。
          //   与「切换图表类型文字变小」同一根因: 不重置则 ELK 读含 zoom 的 BCR →
          //   节点维度放大, 文字变小。forceAutoFit 由 nextTick 内 autoFit 分支消费后重置。
          forceAutoFit = true
          renderMermaid()
          return
        }
        // groups 结构变化 (enabled/collapsed/containers 迁移/重命名/排序) → 全量重渲染
        // [FIX 2026-08-04 v3] 递归签名: 原签名只含 elementCode/enabled/visible/顶层 containers,
        //   遗漏 title (重命名不触发) 与 children (子分组移动/排序不触发)。现递归捕获标题、
        //   嵌套 children 与容器顺序, 任何布局结构调整都会触发 renderMermaid。
        // [HIDE 2026-08-07] 结构签名剔除 visible: 隐藏/显示是"增量"操作 (不动 ELK 布局,
        //   留空位), 不该触发全量重排。visible 变化单独走 updateVisibilityOnly 增量路径,
        //   避免每次隐/显都闪整屏 loading。disabled 语义不变 (enabled=false 走全量重排打平)。
        const sigGroup = (g) => ({
          id: g.elementCode || g.id,
          title: g.title,
          en: g.enabled,
          // [EXPAND 2026-08-05] 树折叠参与渲染: collapsed 必须进签名, 否则"折叠/展开"切换不触发重渲染.
          //   历史: 之前注释"无需单独捕获 collapsed (已移除显式折叠)" → 折叠时顺带改了 enabled
          //   仍能触发, 但恢复展开只改 collapsed → 签名不变 → 图表不刷新 (self-test 复现).
          //   现 collapsed=true (树折叠) 由 computeUplift 视为强制上提, 必须纳入变化检测.
          co: g.collapsed === true,
          cont: (g.containers || []).map(c => typeof c === 'string' ? c : (c.id || c.elementCode)),
          // [MOVE 2026-08-04] unified 叶子存 directNodes (SM/BO code), 面板拖拽移动叶子即是
          //   directNodes 迁移. 签名必须捕获 directNodes, 否则叶子移动到另一分组时签名不变,
          //  不会触发 renderMermaid → 图表无变化.
          dn: (g.directNodes || []).map(n => typeof n === 'object' ? (n.id || n.code || n.name) : n),
          ch: (g.children || []).map(sigGroup)
        })
        const sig = (cfg) => JSON.stringify((cfg?.groups || []).map(sigGroup))
        const newSig = sig(newVal)
        const oldSig = sig(oldVal)
        console.log('[WATCH] layoutControlConfig sig changed=' + (newSig !== oldSig) + ', newSig=' + newSig.slice(0, 200) + ', oldSig=' + oldSig.slice(0, 200))
        if (newSig !== oldSig) {
          // [FIX 2026-08-04] 分组禁用也需在 mermaid.run() 前重置 zoom transform。
          //   与方向/引擎切换同一根因: 用户已缩放时启用/禁用分组, 不重置则 ELK 读含 zoom 的
          //   BCR → 节点维度放大, 文字变小。forceAutoFit 由 nextTick 内 autoFit 分支消费后重置。
          forceAutoFit = true
          renderMermaid()
          return
        }
        // [HIDE 2026-08-07] 仅 visible 变化 → 增量隐/显 (不动布局, 不触发整屏 loading)。
        //   隐藏与禁用的区别: 隐藏 retain 空位 (容器/连线 display:none), 禁用走全量重排打平。
        const sigGroupVisibility = (g) => ({
          id: g.elementCode || g.id,
          v: g.visible,
          ch: (g.children || []).map(sigGroupVisibility),
          cont: (g.containers || [])
            .filter(c => c && typeof c === 'object' && Object.prototype.hasOwnProperty.call(c, 'visible'))
            .map(c => ({ id: c.id || c.elementCode, v: c.visible }))
        })
        const sigVisibility = (cfg) => JSON.stringify((cfg?.groups || []).map(sigGroupVisibility))
        if (sigVisibility(newVal) !== sigVisibility(oldVal)) {
          updateVisibilityOnly(newVal.groups)
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
        // [O2 2026-08-02] 原 console.log 每次备注过滤/中心范围切换都刷屏,
        //   改为 diag.recordStepMeta — chart_diag / window.__archPage.mermaid.stepMeta 可读, 不污染 console
        diag.recordStepMeta('annotationConfigChanged', {
          filter: newVal.annotationCategoryFilter,
          panel: newVal.annotationPanelPosition,
          icons: newVal.showAnnotationIcons
        })
        // 重跑 processSvg (它内部会调 renderAnnotationOverlay)
        // 主线不受影响: annotation overlay 移除+重新渲染, 其他 SVG 元素不动 (renderAnnotationOverlay 内部 removeAnnotationLayers 后重画)
        // [FIX 2026-07-31] 传 interaction 让 annotation 点击居中能正常工作
        svgProcessor.processSvg(svgEl, props, relationDescriptions, mermaidContainer, nodeColorMappings, interaction, handleToggleGroupVisible)
      },
      { deep: true }
    )

    // [FOCUS 2026-08-05] 布局设置面板 → 图表联动: 监听 chartFocusRequest, 高亮 + 居中目标元素
    //   复用 annotationOverlay.focusOnTarget (高亮) + interaction.centerElement (居中),
    //   行为与"点击备注面板项"完全一致。seq 自增保证连续聚焦同一目标也能响应。
    watch(
      () => configStore.chartFocusRequest.seq,
      () => {
        const { type, id } = configStore.chartFocusRequest
        if (!type || !id) return
        const svg = mermaidContainer.value?.querySelector('svg')
        if (!svg) return
        const targetEl = annotationOverlay.focusOnTarget(svg, id, type)
        if (targetEl) {
          interaction.centerElement(svg, targetEl)
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

    // [DEBUG 2026-08-07] Ctrl+Shift+D 快捷键处理器 (在 setup 级别定义, 供 onMounted/onBeforeUnmount 共享)
    let _debugKeydownHandler = null

    // 组件挂载后初始化
    // [DEBUG 2026-08-07] 安装调试助手到 window.__archPage.debug (仅 ?mode=debug)
    //   提供浏览器控制台直接排查的能力, 无需增删 console.log/HMR 等待。
    //   用法: 在浏览器控制台输入:
    //     __archPage.debug.dump()                 // 全量状态
    //     __archPage.debug.inspectGroups()         // 分组列表(含visible/collapsed)
    //     __archPage.debug.findGroup('SD_MM')      // 按编码/标题查找分组
    //     __archPage.debug.testRightClick('g.cluster') // 模拟右键 SVG 元素
    //     __archPage.debug.checkVisibility()       // 隐藏状态

    // [DBG 2026-08-08] 浮动调试面板回调: 直接调用 window.__archPage.debug 方法
    //   与 installDebugHelpers 中安装的调试工具复用, 面板按钮作为可视化入口
    const debugDump = () => { const r = window.__archPage?.debug?.dump?.(); debug.debugLog('[DBG-Panel] dump:', r) }
    const debugInspectGroups = () => { const r = window.__archPage?.debug?.inspectGroups?.(); debug.debugLog('[DBG-Panel] inspectGroups:', r) }
    const debugInspectRendering = () => { const r = window.__archPage?.debug?.inspectRenderingGroups?.(); debug.debugLog('[DBG-Panel] inspectRenderingGroups:', r) }
    const debugIdentifyCollapse = () => { const r = window.__archPage?.debug?.identifyCollapseNodes?.(); debug.debugLog('[DBG-Panel] identifyCollapseNodes:', r) }
    const debugVerifyChart = () => { const r = window.__archPage?.debug?.verifyChart?.(); debug.debugLog('[DBG-Panel] verifyChart:', r) }
    const debugTestRightClick = () => { const r = window.__archPage?.debug?.testRightClick?.('g.cluster, g.node'); debug.debugLog('[DBG-Panel] testRightClick:', r) }
    const debugTestDblClick = () => { const r = window.__archPage?.debug?.testDblClick?.('g.node[id*="COLLAPSE_"], g.cluster'); debug.debugLog('[DBG-Panel] testDblClick:', r) }
    const debugExpandSCP = () => { const r = window.__archPage?.debug?.expandGroup?.('SCP', 2); debug.debugLog('[DBG-Panel] expandGroup SCP→2:', r) }
    const debugCollapseSCP = () => { const r = window.__archPage?.debug?.collapseGroup?.('SCP'); debug.debugLog('[DBG-Panel] collapseGroup SCP:', r) }

    // [FIX 2026-08-08 v3] 调试助手安装: 仅 ?mode=debug 时暴露到 window.__archPage.debug
    //   生产环境: window.__archPage.debug 为 undefined, 零污染
    const installDebugHelpers = () => {
      if (!debug.isDebug) return
      const flatten = (list, depth = 0) => {
        if (!Array.isArray(list)) return []
        return list.flatMap(g => {
          if (!g || typeof g !== 'object') return []
          const item = { ...g, _depth: depth }
          return [item, ...flatten(g.children, depth + 1), ...flatten(g.containers, depth + 1)]
        })
      }
      // [OBS 2026-08-09] 渲染真相 (effectiveLayoutControlConfig, 实际渲染依据) 与 store 的 collapsed 一致性比对.
      //   背景: inspectGroups 读 configStore.layoutControlConfig, inspectRenderingGroups 读
      //   effectiveLayoutControlConfig(props), 二者可能显示不同 collapsed, 误导排查(见 2026-08-09
      //   领域双击排查: store 说 SCM.collapsed=true、渲染说 false). 此比对一次给出差异清单.
      const computeCollapsedDivergences = () => {
        const storeCfg = configStore.layoutControlConfig
        const renderCfg = effectiveLayoutControlConfig.value
        const storeMap = new Map()
        ;(storeCfg?.groups ? flatten(storeCfg.groups) : []).forEach(g => {
          if (g.elementCode || g.id) storeMap.set(g.elementCode || g.id, g.collapsed === true)
        })
        const renderMap = new Map()
        ;(renderCfg?.groups ? flatten(renderCfg.groups) : []).forEach(g => {
          if (g.elementCode || g.id) renderMap.set(g.elementCode || g.id, g.collapsed === true)
        })
        const all = new Set([...storeMap.keys(), ...renderMap.keys()])
        const divergences = []
        all.forEach(code => {
          const s = storeMap.get(code)
          const r = renderMap.get(code)
          if (s !== undefined && r !== undefined && s !== r) {
            divergences.push({ code, storeCollapsed: s, renderCollapsed: r })
          }
        })
        // [OBS 2026-08-09] store/渲染 collapsed 不一致时显式告警(可排查), 不静默.
        //   触发点: 排查"store 说折叠了、图表却显示展开"一类问题, 一次给出差异清单.
        if (divergences.length > 0) {
          debug.debugWarn('[DBG] store/渲染 collapsed 不一致 ' + divergences.length + ' 处:', divergences)
        }
        return divergences
      }
      const api = {
        // [DBG 2026-08-09] 暴露 configStore 供浏览器脚本直接驱动配置切换 (仅 ?mode=debug).
        //   用途: 一键脚本"双击展开→切 centerScopeHighlight→校验是否折叠"决定性复现, 避免多轮 UI 操作.
        store: configStore,
        // [DBG 2026-08-10] 暴露当前 diagramData (nodes/links/domainProducts), 供关系高亮子树构建校验.
        getDiagramData: () => props.diagramData,
        // 全量状态 dump
        dump: () => {
          const cfg = configStore.layoutControlConfig
          const svg = mermaidContainer.value?.querySelector('svg')
          return {
            layoutControlConfig: cfg ? { groupsCount: cfg.groups?.length, groups: flatten(cfg.groups) } : null,
            ctxMenu: { ...ctxMenu },
            svg: svg ? {
              clusters: Array.from(svg.querySelectorAll('g.cluster')).map(e => ({ id: e.id, code: e.getAttribute('data-container-code'), class: e.className })),
              nodes: Array.from(svg.querySelectorAll('g.node')).map(e => ({ id: e.id, code: e.getAttribute('data-code'), class: e.className })),
              collapseNodes: Array.from(svg.querySelectorAll('g.node[id^="flowchart-COLLAPSE_"]')).map(e => ({ id: e.id }))
            } : null,
            centerScopeMarkers: configStore.centerScopeMarkers || null
          }
        },
        // 分组列表 (flat)
        inspectGroups: () => {
          const cfg = configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return []
          return flatten(cfg.groups).map(g => ({
            title: g.title, code: g.elementCode || g.id, groupType: g.groupType,
            visible: g.visible, collapsed: g.collapsed, _depth: g._depth
          }))
        },
        // 按编码/标题查找分组
        findGroup: (key) => {
          const cfg = configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return null
          return findGroupInTree(cfg.groups, g => {
            const gt = g.title || g.name || g.elementCode || g.id
            return gt === key || g.elementCode === key || g.id === key
          })
        },
        // 模拟右键 SVG 元素 (selector 如 'g.cluster', 'g.node', 'text')
        testRightClick: (selector) => {
          const svg = mermaidContainer.value?.querySelector('svg')
          if (!svg) return { error: 'no SVG' }
          const el = selector ? svg.querySelector(selector) : svg.querySelector('g.cluster, g.node, text, rect')
          if (!el) return { error: `no element matching "${selector}"` }
          const event = new MouseEvent('contextmenu', {
            bubbles: true, cancelable: true, clientX: 100, clientY: 100, button: 2
          })
          Object.defineProperty(event, 'target', { value: el, writable: true })
          handleContextMenu(event)
          return { triggered: true, target: el.tagName + (el.id ? '#' + el.id : ''), ctxMenu: { show: ctxMenu.show, groupTitle: ctxMenu.groupTitle, elementCode: ctxMenu.elementCode, x: ctxMenu.x, y: ctxMenu.y } }
        },
        // [DBL 2026-08-08] 模拟双击 SVG 元素 (测试双击展开)
        testDblClick: (selector) => {
          const svg = mermaidContainer.value?.querySelector('svg')
          if (!svg) return { error: 'no SVG' }
          const el = selector ? svg.querySelector(selector) : svg.querySelector('g.cluster, g.node, text, rect')
          if (!el) return { error: `no element matching "${selector}"` }
          const event = new MouseEvent('dblclick', {
            bubbles: true, cancelable: true, clientX: 100, clientY: 100
          })
          Object.defineProperty(event, 'target', { value: el, writable: true })
          handleDblClick(event)
          // 返回 store 快照辅助诊断
          const cfg = configStore.layoutControlConfig
          const targetCode = el.getAttribute('data-container-code') || ''
          const groups = cfg?.groups || []
          const flat = (list) => { const r = []; (list||[]).forEach(g => { if(g) { r.push({id:g.elementCode||g.id,co:g.collapsed}); flat(g.children).forEach(x=>r.push(x)); flat(g.containers).forEach(x=>r.push(x)); } }); return r }
          const allGroups = flat(groups)
          return { triggered: true, target: el.tagName + (el.id ? '#' + el.id : ''), targetCode, storeGroups: allGroups }
        },
        // 隐藏状态检查
        checkVisibility: () => {
          const cfg = configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return []
          return flatten(cfg.groups).filter(g => g.visible === false).map(g => ({
            title: g.title, code: g.elementCode || g.id, groupType: g.groupType
          }))
        },
        // [DBG 2026-08-08] 直接展开分组到指定层级 (绕过右键菜单, 直接操作 store)
        //   用法: __archPage.debug.expandGroup('SCP', 2)  // 展开 "供应链计划" 到服务模块
        //   level: 0=领域, 1=子领域, 2=服务模块, 99=业务对象
        expandGroup: (code, level) => {
          const cfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return { error: 'no groups in config' }
          const group = findGroupInTree(cfg.groups, g => g.elementCode === code || g.id === code)
          if (!group) return { error: `group not found: ${code}`, groups: flatten(cfg.groups).map(g => ({ code: g.elementCode || g.id, title: g.title })) }
          const newConfig = JSON.parse(JSON.stringify(cfg))
          const target = findGroupInTree(newConfig.groups, g => g.elementCode === code || g.id === code)
          if (!target) return { error: 'target not found in clone' }
          expandSubtreeToLevel(target, level)
          debug.debugLog('[DBG] expandGroup: code=' + code + ', level=' + level + ', target collapsed after=' + target.collapsed)
          configStore.updateLayoutControlConfig(newConfig)
          // [P1 2026-08-08] 记录调试面板操作
          debug.recordInteraction('expandGroup', { code, level, collapsed: target.collapsed })
          return { target: target.title || target.elementCode || target.id, collapsed: target.collapsed, level }
        },
        // [DBG 2026-08-08] 直接切换分组可见性 (复用 handleToggleGroupVisible 的 store 更新 + 增量隐/显流程)
        //   用法: __archPage.debug.setGroupVisible('SCM', false)  // 隐藏供应链云
        setGroupVisible: (code, visible) => {
          const cfg = configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return { error: 'no groups' }
          const newConfig = JSON.parse(JSON.stringify(cfg))
          const setVis = (g, v) => {
            if (!g || typeof g !== 'object') return
            const hiding = v === false
            const directScope = hiding && isDirectScopeGroup(g)
            const ancestorScope = hiding && isScopeAncestor(g)
            if (!directScope && !ancestorScope) g.visible = v
            if (directScope) return
            if (Array.isArray(g.children)) g.children.forEach(c => setVis(c, v))
            if (Array.isArray(g.containers)) g.containers.forEach(c => setVis(c, v))
          }
          const findAndSet = (list) => {
            ;(list || []).forEach(g => {
              if (!g || typeof g !== 'object') return
              if (g.elementCode === code || g.id === code) setVis(g, visible)
              findAndSet(g.children)
              findAndSet(g.containers)
            })
          }
          findAndSet(newConfig.groups)
          configStore.updateLayoutControlConfig(newConfig)
          try {
            updateVisibilityOnly(newConfig.groups)
          } catch (e) {
            return { error: 'updateVisibilityOnly failed: ' + (e?.message || e) }
          }
          return { code, visible, done: true }
        },
        // [DBG 2026-08-08] 直接折叠分组
        collapseGroup: (code) => {
          const cfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return { error: 'no groups in config' }
          const group = findGroupInTree(cfg.groups, g => g.elementCode === code || g.id === code)
          if (!group) return { error: `group not found: ${code}` }
          const newConfig = JSON.parse(JSON.stringify(cfg))
          const target = findGroupInTree(newConfig.groups, g => g.elementCode === code || g.id === code)
          if (!target) return { error: 'target not found in clone' }
          target.collapsed = true
          configStore.updateLayoutControlConfig(newConfig)
          // [P1 2026-08-08] 记录调试面板操作
          debug.recordInteraction('collapseGroup', { code, collapsed: true })
          return { target: target.title || target.elementCode || target.id, collapsed: true }
        },
        // [DBG 2026-08-08] 切换全局展开层级 (等价于工具栏/图表设置的"展开层级"下拉, 替代已废弃的 chartType)
        //   用法: __archPage.debug.setExpandLevel('serviceModule')  // 展开到服务模块
        //   key ∈ EXPAND_LEVELS: domain(领域)/subDomain(子领域)/serviceModule(服务模块)/businessObject(业务对象)
        setExpandLevel: (key) => {
          const cfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
          if (!cfg || !Array.isArray(cfg.groups)) return { error: 'no groups in config' }
          const newConfig = JSON.parse(JSON.stringify(cfg))
          expandGroupsToLevel(newConfig.groups, key)
          configStore.setExpandLevel(key || 'businessObject')
          configStore.updateLayoutControlConfig(newConfig)
          debug.debugLog('[DBG] setExpandLevel: key=' + key)
          debug.recordInteraction('setExpandLevel', { key })
          return { key, collapsedCount: flatten(newConfig.groups).filter(g => g.collapsed === true).length }
        },
        // [REL-HL 2026-08-10] 调试: 执行"关系高亮" (等价于右键菜单"关系高亮")
        //   用法: __archPage.debug.highlightRelations('PO201')  // 高亮该节点相关连线与相连节点
        //         __archPage.debug.clearRelationsHighlight()   // 清除
        highlightRelations: (code) => {
          highlightRelations(code)
          return { code, applied: true }
        },
        clearRelationsHighlight: () => {
          clearRelationsHighlight()
          return { cleared: true }
        },
        // [DBG 2026-08-08] 调试: 检查 SVG 中 COLLAPSE 节点的识别结果
        identifyCollapseNodes: () => {
          const svg = mermaidContainer.value?.querySelector('svg')
          if (!svg) return { error: 'no SVG' }
          const collapseNodes = svg.querySelectorAll('g.node[id*="COLLAPSE_"]')
          return Array.from(collapseNodes).map(el => {
            const code = el.getAttribute('data-container-code') || ''
            const id = el.getAttribute('id') || ''
            // 模拟 identifyGroupFromSvg 的结果
            const group = identifyGroupFromSvg(el)
            return { id, dataContainerCode: code, identified: group ? { title: group.title, code: group.elementCode || group.id, collapsed: group.collapsed, groupType: group.groupType } : null }
          })
        },
        // [DBG 2026-08-08] 查看渲染配置 (effectiveLayoutControlConfig) 的分组状态
        inspectRenderingGroups: () => {
          const cfg = effectiveLayoutControlConfig.value
          if (!cfg || !Array.isArray(cfg.groups)) return { error: 'no rendering groups' }
          return flatten(cfg.groups).map(g => ({
            title: g.title, code: g.elementCode || g.id, groupType: g.groupType,
            visible: g.visible, collapsed: g.collapsed, _depth: g._depth
          }))
        },
        // [VIS-AUDIT 2026-08-08] 可见性审计: 一次性输出定位"空容器残留"问题所需的三份关键信息,
        //   并返回 JSON 字符串(browser_evaluate 可稳定读取, 避免复杂对象序列化失败):
        //   1) 分组树: elementCode/title/visible/_uplift/是否被判定为空容器
        //   2) SVG 容器: 实际 data-container-code + 当前 display 状态
        //   3) 逐容器比对: 分组树 elementCode 是否存在于 SVG data-container-code 集合
        //   用法: window.__archPage.debug.auditVisibility()
        auditVisibility: () => {
          const svg = mermaidContainer.value?.querySelector('svg')
          if (!svg) return JSON.stringify({ error: 'no SVG' })
          const cfg = effectiveLayoutControlConfig.value
          const groups = cfg?.groups || configStore.layoutControlConfig?.groups || []
          // 与 updateVisibilityOnly 内 hasVisibleContent 保持一致的递归判定
          const hasVisibleContent = (g) => {
            if (!g || typeof g !== 'object') return false
            if (g.visible === false) return false
            // [FIX 2026-08-09] 折叠子分组算作内容: collapsed=true 的子分组会在父容器内
            //   渲染为 COLLAPSE_<id> 聚合节点 (见 groupedLayout 容器级折叠逻辑), 故父容器
            //   并非空盒. 此前未识别折叠子节点导致 SCP(6 个子服务模块全折叠)被误判为空容器,
            //   verifyChart 的 empty-container 检查对正常折叠图误报. 与 hasGroupContent 语义对齐.
            if (g.collapsed === true) return true
            if (g.directNodes && g.directNodes.length > 0) return true
            if (Array.isArray(g.containers)) {
              for (const c of g.containers) {
                if (!c || typeof c !== 'object') continue
                if (c.visible === false) continue
                if ((c.nodes && c.nodes.length > 0)
                  || c.elementRef?.code != null
                  || c.elementCode != null
                  || c.name != null) return true
              }
            }
            if (Array.isArray(g.children)) {
              for (const ch of g.children) {
                if (hasVisibleContent(ch)) return true
              }
            }
            return false
          }
          const flatAudit = (list, depth = 0) => {
            if (!Array.isArray(list)) return []
            const out = []
            ;(list || []).forEach(g => {
              if (!g || typeof g !== 'object') return
              out.push({
                code: g.elementCode || g.id,
                title: g.title || g.name,
                groupType: g.groupType,
                visible: g.visible,
                _uplift: g._uplift === true,
                empty: g.visible !== false && g._uplift !== true && !hasVisibleContent(g),
                depth
              })
              out.push(...flatAudit(g.children, depth + 1))
              out.push(...flatAudit(g.containers, depth + 1))
            })
            return out
          }
          const groupInfo = flatAudit(groups)
          const svgContainerCodes = Array.from(svg.querySelectorAll('g.cluster, .subgraph'))
            .map(el => ({ code: el.getAttribute('data-container-code') || '', display: el.style.display || 'inline' }))
            .filter(c => c.code)
          const svgCodeSet = new Set(svgContainerCodes.map(c => c.code))
          const noSvgMatch = groupInfo
            .filter(g => g.code && !svgCodeSet.has(g.code))
            .map(g => ({ code: g.code, title: g.title, groupType: g.groupType }))
          return JSON.stringify({
            groups: groupInfo,
            svgContainers: svgContainerCodes,
            groupCodesWithoutSvgMatch: noSvgMatch,
            svgCodesWithoutGroup: Array.from(svgCodeSet).filter(c => !groupInfo.some(g => g.code === c))
          })
        },
        // [OBS 2026-08-09] store/渲染 collapsed 一致性比对: 返回差异清单(排查"store折叠/图表展开"类问题).
        computeCollapsedDivergences,
        // [LOGS 2026-08-09] 取回最近调试日志(倒序). 生产模式返回 []. 供 E2E/手动排查读取.
        getLogs: debug.getLogs,
        // [VERIFY 2026-08-09] 一键自检: 断言三项渲染可验证标准, 返回 { pass, failures[], checks }.
        //   1) COLLAPSE 聚合节点全部可识别到分组 (identifyCollapseNodes)
        //   2) store/渲染 collapsed 冲突方向: store 说折叠(或冲突真凶) 但渲染未折叠 → fail;
        //      渲染折叠而 store 未折叠 = 范围默认折叠(正常), 仅计入 checks 不 fail.
        //   3) 无异常空容器/缺 SVG 容器: 已折叠分组(聚合为节点)合法无容器, 排除后仍异常才 fail.
        //   用法: window.__archPage.debug.verifyChart()
        verifyChart: () => {
          const failures = []
          const checks = {}
          // 已折叠分组集合(渲染侧依据). 折叠容器被聚合为 COLLAPSE_ 节点 → 本就不该有 SVG 容器,
          //   空容器/缺 SVG 判定须排除, 否则健康的范围默认折叠图永远 fail.
          const renderCfg = effectiveLayoutControlConfig.value
          const collapsedSet = new Set()
          ;(renderCfg?.groups ? flatten(renderCfg.groups) : []).forEach(g => {
            if (g.collapsed === true && (g.elementCode || g.id)) collapsedSet.add(g.elementCode || g.id)
          })
          // ---- 检查1: COLLAPSE 节点可识别 ----
          const collapseRes = api.identifyCollapseNodes()
          if (collapseRes.error) {
            failures.push({ type: 'collapse-identify', message: collapseRes.error })
          } else {
            const unresolved = collapseRes.filter(c => !c.identified)
            checks.collapseTotal = collapseRes.length
            checks.collapseUnresolved = unresolved.length
            if (unresolved.length > 0) {
              failures.push({
                type: 'collapse-identify',
                message: `${unresolved.length}/${collapseRes.length} 个 COLLAPSE 节点未能识别到分组`,
                details: unresolved.map(u => u.id)
              })
            }
          }
          // ---- 检查2: store/渲染 collapsed 冲突方向 ----
          const divergences = computeCollapsedDivergences()
          // 真凶方向: store 折叠但渲染未折叠 → 用户折叠了但图表显示展开 (见 2026-08-09 SCM 排查).
          // 反向(渲染折叠/store未折叠)是范围默认折叠或渲染层默认, 属正常, 仅计数.
          const badDivergences = divergences.filter(d => d.storeCollapsed === true && d.renderCollapsed === false)
          checks.divergenceCount = divergences.length
          checks.badDivergenceCount = badDivergences.length
          if (badDivergences.length > 0) {
            failures.push({
              type: 'store-render-divergence',
              message: `${badDivergences.length} 处分组 store 折叠但渲染未折叠 (用户折叠未生效)`,
              details: badDivergences
            })
          }
          // ---- 检查3: 无异常空容器/缺 SVG (排除已折叠分组) ----
          const auditStr = api.auditVisibility()
          let audit = null
          try { audit = JSON.parse(auditStr) } catch (e) { audit = null }
          if (!audit || audit.error) {
            failures.push({ type: 'empty-container', message: audit?.error || 'auditVisibility 无法解析' })
          } else {
            const emptyContainers = (audit.groups || []).filter(g => g.empty === true && !collapsedSet.has(g.code))
            const noSvgMatch = (audit.groupCodesWithoutSvgMatch || []).filter(g => g.code && !collapsedSet.has(g.code))
            checks.emptyContainerCount = emptyContainers.length
            checks.emptyCollapsedExcluded = (audit.groups || []).filter(g => g.empty === true && collapsedSet.has(g.code)).length
            checks.groupCodeWithoutSvgMatch = noSvgMatch.length
            if (emptyContainers.length > 0) {
              failures.push({
                type: 'empty-container',
                message: `${emptyContainers.length} 个未折叠空容器残留 (visible 但无可见内容)`,
                details: emptyContainers.map(g => ({ code: g.code, title: g.title, groupType: g.groupType }))
              })
            }
            if (noSvgMatch.length > 0) {
              failures.push({
                type: 'group-no-svg-match',
                message: `${noSvgMatch.length} 个未折叠分组无对应 SVG 容器 (应渲染却缺失)`,
                details: noSvgMatch
              })
            }
          }
          // ---- 检查4: 语义级校验 — 渲染 BO 数 vs 范围预期 (拦截"全量加载/范围过滤失效") ----
          //   交叉比对 scopeState.finalBoCodesCount (预期范围内 BO 数) 与 SVG 中实际渲染的
          //   g.node[data-code] 数. 用于最终确认"范围过滤是否生效/是否误回退到全量加载",
          //   比结构一致性检查更能直接反映用户可见结果.
          //   注意: 展开层级 < businessObject 时, 范围内 BO 被折叠进 COLLAPSE 节点,
          //   此时渲染 BO 数会 < 预期 (正常). 故严格断言相等仅当 expandLevelUserSet=true 且
          //   expandLevel=businessObject (用户显式展开到业务对象层). 用户未显式设置时
          //   (expandLevelUserSet=false), store 默认 businessObject 但实际走"范围默认折叠"
          //   (范围内→服务模块/范围外→子领域), 渲染 BO 数必然 < 预期, 属正常, 仅计数.
          //   超量 (渲染 BO 数 > 预期) 恒为异常 — 范围过滤失效/全量加载 (见项目铁律 2026-08-08).
          try {
            const scopeState = window.__archPage?.scopeState
            const expectedBo = (scopeState && typeof scopeState.finalBoCodesCount === 'number') ? scopeState.finalBoCodesCount : null
            const expandState = window.__archPage?.expandState
            const expandLevel = expandState?.expandLevel
            const expandLevelUserSet = expandState?.expandLevelUserSet === true
            const svgEl = mermaidContainer.value?.querySelector('svg')
            const renderedBoCount = svgEl
              ? Array.from(svgEl.querySelectorAll('g.node[data-code]'))
                  .filter(n => !(n.id || '').includes('COLLAPSE_'))
                  .length
              : 0
            checks.scopeExpectedBo = expectedBo
            checks.renderedBoCount = renderedBoCount
            checks.expandLevel = expandLevel
            checks.expandLevelUserSet = expandLevelUserSet
            // 超量: 无论展开层级如何, 渲染 BO 数都不应超过范围预期 (否则 = 全量/越界加载)
            if (expectedBo != null && renderedBoCount > expectedBo) {
              failures.push({
                type: 'semantic-bo-overflow',
                message: `渲染 BO 数 ${renderedBoCount} > 范围预期 ${expectedBo} (范围过滤失效或回退全量加载)`,
                details: { renderedBoCount, expectedBo, expandLevel }
              })
            }
            // 用户显式展开到业务对象层时, 应恰好等于范围预期
            if (expectedBo != null && expandLevelUserSet && expandLevel === 'businessObject' && renderedBoCount !== expectedBo) {
              failures.push({
                type: 'semantic-bo-count-mismatch',
                message: `用户展开到业务对象层但渲染 BO 数 ${renderedBoCount} ≠ 范围预期 ${expectedBo}`,
                details: { renderedBoCount, expectedBo, expandLevel, expandLevelUserSet }
              })
            }
          } catch (e) {
            // 语义检查失败不应阻断整个 verifyChart, 降级为 checks 记录
            checks.semanticCheckError = e?.message || String(e)
          }
          const pass = failures.length === 0
          debug.debugLog('[VERIFY] verifyChart ' + (pass ? 'PASS' : 'FAIL') + ' checks=', checks)
          if (!pass) debug.debugWarn('[VERIFY] verifyChart FAIL:', failures)
          return { pass, failures, checks }
        },
        // [E2E 2026-08-08] 等待图表渲染完成 (替代 openEmbeddedChartView 的固定 waitForTimeout)
        waitForChartReady: (timeout = 30000) => {
          const start = Date.now()
          return new Promise((resolve, reject) => {
            const poll = () => {
              const svg = mermaidContainer.value?.querySelector('svg')
              const content = document.querySelector('.mermaid-content')
              if (svg && svg.isConnected && content) {
                const transform = content.style.transform || ''
                resolve({ svgId: svg.id, transform, elapsed: Date.now() - start })
                return
              }
              if (Date.now() - start > timeout) {
                reject(new Error(`waitForChartReady timeout ${timeout}ms`))
                return
              }
              setTimeout(poll, 200)
            }
            poll()
          })
        },
        // [REC 2026-08-09] 交互记录器暴露: 修复"记录却无法取回/回放"的死代码缺口.
        //   handleDblClick/handleContextMenu/menu-click 已在 recordInteraction 埋点,
        //   但 interactionHistory/replay 从未暴露到 __archPage.debug → 排查时只能读 console.
        //   此处暴露全部接口, 使交互序列可检索、可回放、可逐步执行 (仅 ?mode=debug 生效).
        //   用法:
        //     __archPage.debug.getHistory()        // 全部交互记录 (时间倒序)
        //     __archPage.debug.replay(500)         // 回放全部记录 (间隔 500ms)
        //     __archPage.debug.stepForward()       // 前进一步
        //     __archPage.debug.stepBackward()      // 后退一步
        //     __archPage.debug.clearHistory()      // 清空记录
        getHistory: () => (debug.interactionHistory ? debug.interactionHistory.value.slice().reverse() : []),
        clearHistory: () => { debug.clearHistory(); return { cleared: true } },
        replay: (delay) => debug.replay(delay),
        stepForward: () => debug.stepForward(),
        stepBackward: () => debug.stepBackward(),
        // [ERR 2026-08-09] 统一错误聚合: 一次看全所有错误, 避免"渲染错误(__archPage.mermaid.errors)
        //   与全局 Vue 错误(window.__appErrors)"两处分离翻找. 返回结构化结果供排查/E2E.
        //   用法: window.__archPage.debug.errors()
        errors: () => {
          const renderErrors = (window.__archPage?.mermaid?.errors || []).map(e => ({ source: 'render', ...e }))
          const appErrors = (window.__appErrors || []).map(e => ({ source: 'app', ...e }))
          return { render: renderErrors, app: appErrors, total: renderErrors.length + appErrors.length }
        },
      }
      // 注册到 window.__archPage.debug (仅 ?mode=debug 时生效)
      debug.registerDebugAPI({ debug: api })
      // [REC 2026-08-09] 回放事件监听: useDebugMode.replay/stepForward 通过
      //   window.dispatchEvent('debug:replay-step') 广播, 此处监听并回放真实交互.
      //   使交互记录器从"只记录"升级为"可回放可逐步执行" (仅 ?mode=debug 生效).
      window.addEventListener('debug:replay-step', (ev) => {
        const step = ev?.detail?.step
        if (!step) return
        debug.debugLog('[REC] 回放步骤 ' + step.index + ': ' + step.type, step.data)
      })
    }

    onMounted(() => {
      // [FIX 2026-08-01] 安装 diagnostics 到 window.__archPage.mermaid,
      //   chart_diag / E2E 可一键读取 lastRender / stepTimings / errors.
      installDiagnosticsToWindow()
      // [OBS 2026-08-09] 聚合诊断入口 diag() + verify(): 任意模式可用 (只读, 不依赖 ?mode=debug).
      //   目的: 把 store / chartConfig / 渲染树三份布局的 collapsed·enabled·visible 并排,
      //   并逐 group 对比差异(divergences). 直接服务"双击展开→切 centerScopeHighlight→是否折叠"
      //   类状态漂移问题的快速定位 (见 docs/observability-improvement-plan.md P1-2 / P0-2).
      //   用法(浏览器 console):
      //     window.__archPage.diag()      -> 三份布局快照 + divergences
      //     window.__archPage.verify()    -> { pass, checks, divergences } 结构化断言
      const flattenGroups = (list) => {
        const out = []
        const walk = (items) => {
          if (!Array.isArray(items)) return
          for (const g of items) {
            if (!g || typeof g !== 'object') continue
            out.push({
              key: g.elementCode || g.id,
              type: g.groupType || g.type,
              title: g.title || g.name || '',
              collapsed: !!g.collapsed,
              enabled: g.enabled !== false,
              visible: g.visible !== false
            })
            walk(g.children)
            walk((g.containers || []).filter(c => c && typeof c === 'object'))
          }
        }
        walk(list)
        return out
      }
      const buildDiag = () => {
        // 返回必须完全 JSON 可序列化 (browser_evaluate / console 可直接取). 部分状态
        //   (expandState/colorState) 可能含函数/DOM 引用, 逐字段 JSON 安全清洗.
        const safe = (v) => {
          if (v === undefined) return undefined
          try { return JSON.parse(JSON.stringify(v)) } catch (e) { return { __unserializable: true } }
        }
        const storeGroups = configStore.layoutControlConfig?.groups
        const chartGroups = (window.__archPage?.chartConfig?.layoutControl?.groups) || []
        const renderCfg = effectiveLayoutControlConfig.value
        const store = flattenGroups(storeGroups)
        const chart = flattenGroups(chartGroups)
        const render = flattenGroups(renderCfg?.groups)
        const byKey = {}
        const mergeKey = (arr, src) => arr.forEach(g => {
          byKey[g.key] = byKey[g.key] || {}
          byKey[g.key][src] = g
        })
        mergeKey(store, 'store'); mergeKey(chart, 'chart'); mergeKey(render, 'render')
        const divergences = Object.entries(byKey)
          .filter(([k, v]) => {
            const flags = [v.store?.collapsed, v.chart?.collapsed, v.render?.collapsed].filter(x => x !== undefined)
            return flags.length >= 2 && new Set(flags).size > 1
          })
          .map(([k, v]) => ({
            key: k,
            title: (v.store || v.chart || v.render)?.title,
            store: v.store?.collapsed,
            chart: v.chart?.collapsed,
            render: v.render?.collapsed
          }))
        return {
          ts: Date.now(),
          config: {
            centerScopeHighlight: configStore.centerScopeHighlight,
            colorGroupBy: configStore.colorGroupBy,
            expandLevel: configStore.expandLevel,
            groupManualSet: configStore.groupManualSet
          },
          expandState: safe(window.__archPage?.expandState),
          colorState: safe(window.__archPage?.colorState),
          renderMeta: {
            renderSkippedCount: window.__archPage?.mermaid?.renderSkippedCount,
            lastRenderedCode: window.__archPage?.mermaid?.lastRenderedCode,
            lastRender: safe(window.__archPage?.mermaid?.lastRender)
          },
          store, chart, render,
          divergences
        }
      }
      window.__archPage.diag = buildDiag

      // [OBS 2026-08-09 行为级] 抓取当前已渲染 SVG 的"节点签名".
      //   目的: 为"切换区分/不区分等颜色操作后是否发生了全量重建"提供机器客观判据.
      //   原理: 全量重建 (mermaid.run) 会重新生成 SVG 节点 id 集合 → 签名变化;
      //   纯增量变色 (updateColorsOnly) 不改节点结构 → 签名不变.
      //   用法: 展开某分组后 const b = __archPage.captureNodeSignature(); 切换后
      //         __archPage.verify({ before: b, expandKeys: [...] }) 断言未重建.
      const captureNodeSignature = () => {
        const svg = mermaidContainer.value?.querySelector('svg')
        if (!svg) return null
        const nodeIds = Array.from(svg.querySelectorAll('g.node')).map(g => g.id || '').filter(Boolean).sort()
        const clusterIds = Array.from(svg.querySelectorAll('g.cluster')).map(g => g.id || '').filter(Boolean).sort()
        const edgeCount = svg.querySelectorAll('path.flowchart-link').length
        let hash = 0
        const str = JSON.stringify({ nodeIds, clusterIds, edgeCount })
        for (let i = 0; i < str.length; i++) {
          hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
        }
        return { hash: hash >>> 0, nodeCount: nodeIds.length, clusterCount: clusterIds.length, edgeCount, nodeIds: nodeIds.slice(0, 60) }
      }
      window.__archPage.captureNodeSignature = captureNodeSignature

      // [OBS 2026-08-09 行为级] verify 升级: 在原有"三份状态一致性"基础上, 新增行为级断言.
      //   用法:
      //     __archPage.verify()                                    // 仅状态一致性 (原)
      //     __archPage.verify({ before })                          // + 未发生全量重建
      //     __archPage.verify({ expandKeys: ['SD_MM','SM_PUM'] })  // + 指定分组保持展开
      //     __archPage.verify({ before, expandKeys })              // 组合 (dogfood 主用例)
      //   所有字段 JSON 可序列化, 可被脚本/console 直接断言.
      window.__archPage.verify = (opts = {}) => {
        const d = buildDiag()
        const checks = [
          { name: 'three-source-collapsed-consistency', pass: d.divergences.length === 0, detail: d.divergences },
          { name: 'has-store-layout', pass: d.store.length > 0, detail: d.store.length },
          { name: 'has-render-layout', pass: d.render.length > 0, detail: d.render.length }
        ]
        const sigNow = captureNodeSignature()
        // 行为断言 1: 传入 before 签名 → 未发生全量重建 (节点签名未变)
        if (opts.before && opts.before.nodeSignature) {
          const beforeSig = opts.before.nodeSignature
          const sigChanged = !sigNow || beforeSig.hash !== sigNow.hash
          checks.push({ name: 'no-full-rebuild', pass: !sigChanged, detail: { before: beforeSig, now: sigNow, sigChanged } })
        }
        // 行为断言 2: 指定分组在 store/chart/render 三份中均保持展开 (collapsed=false)
        if (Array.isArray(opts.expandKeys) && opts.expandKeys.length) {
          for (const key of opts.expandKeys) {
            const collapsedIn = (src) => d[src].filter(g => g.key === key).map(g => g.collapsed)
            const store = collapsedIn('store')
            const chart = collapsedIn('chart')
            const render = collapsedIn('render')
            const present = store.length || chart.length || render.length
            const expanded = (store.length ? store.every(x => !x) : true)
              && (chart.length ? chart.every(x => !x) : true)
              && (render.length ? render.every(x => !x) : true)
            checks.push({ name: `expanded-kept:${key}`, pass: present > 0 && expanded, detail: { store, chart, render } })
          }
        }
        const pass = checks.every(c => c.pass)
        return { pass, checks, divergences: d.divergences, nodeSignature: sigNow }
      }
      // [DEBUG 2026-08-07] 安装调试助手到 window.__archPage.debug
      installDebugHelpers()

      // ============================================================
      // [OBS 2026-08-10] 可发现性入口: 统一注册到 window.__archPage, 任意模式可用.
      //   目的: 让图表展示模块的诊断/验证能力"非常容易被知道"——一条 help() 列出全部能力,
      //   新接触的开发者先在 console 敲 __archPage.help() 即可。
      // ============================================================
      window.__archPage = window.__archPage || {}
      // 打开状态真相面板 (任意模式)
      window.__archPage.openTruthPanel = openTruthPanel
      // 生成"当前折叠态 + 区分/不区分"的可复现链接 (复制到剪贴板前先返回)
      window.__archPage.exportUrl = () => {
        const d = (window.__archPage.diag && window.__archPage.diag()) || null
        const fold = {}
        ;(d?.store || []).forEach(g => { if (g.key) fold[g.key] = !!g.collapsed })
        const url = new URL(window.location.href)
        url.searchParams.set('fold', JSON.stringify(fold))
        url.searchParams.set('scopeHighlight', d?.config?.centerScopeHighlight ? '1' : '0')
        return url.toString()
      }
      // 能力清单 (可发现性核心): 列出所有诊断/验证/复现 API
      window.__archPage.help = () => ({
        diag: 'diag() — store/chart/渲染树 三份状态 + divergences 分歧清单',
        verify: 'verify({before, expandKeys}) — 行为级断言 {pass, checks}',
        captureNodeSignature: 'captureNodeSignature() — SVG 节点签名 (判定是否全量重建)',
        openTruthPanel: 'openTruthPanel() — 打开状态真相面板 (可视化三份状态+差异高亮)',
        exportUrl: 'exportUrl() — 生成当前折叠态+区分/不区分的可复现链接',
        help: 'help() — 本能力清单',
        debug: 'debug.* — 调试助手 (仅 ?mode=debug)',
        mermaid: 'mermaid.* — 渲染元数据 (lastRender/renderSkippedCount/...)',
        chartConfig: 'chartConfig — 图表配置 (可直接改字段驱动)',
        reload: 'reload() — 强制 mermaid 全量重绘'
      })

      // [OBS 2026-08-10] P1-1 URL 状态应用: 支持 ?fold=<json>&scopeHighlight=0|1 精确复现.
      //   例: /system/archdata?preset=scp&fold={"MM":false,"SCP":true}&scopeHighlight=1
      //   fold 的 value 即 collapsed 布尔 (false=展开, true=折叠), key 为分组 elementCode/id.
      const params = new URLSearchParams(window.location.search)
      const foldRaw = params.get('fold')
      const shRaw = params.get('scopeHighlight')
      let foldApplied = false

      // 1) scopeHighlight: 不依赖 groups, 挂载即可应用
      const applyScopeHighlight = () => {
        if (shRaw === '0' || shRaw === '1') {
          configStore.updateCenterScopeHighlight(shRaw === '1')
        }
      }

      // 2) fold: 深拷贝 store 分组树, 按 key 设置 collapsed, 整体替换 (同双击/右键链路),
      //    并 markGroupManualSet 保留该状态, 避免被默认展开覆盖.
      //    [FIX 2026-08-10] 依赖 layoutControlConfig.groups 已就绪 (父组件异步加载架构数据后填充),
      //      故用 watch 等待首次非空, 而非 onMounted nextTick (过早时 groups 为空 → fold 静默失败).
      const applyFold = (cfg) => {
        if (foldApplied || !foldRaw || !cfg || !Array.isArray(cfg.groups)) return
        try {
          const fold = JSON.parse(foldRaw)
          const deep = JSON.parse(JSON.stringify(cfg))
          const walk = (groups) => {
            for (const g of groups) {
              const key = g.elementCode || g.id
              if (key && Object.prototype.hasOwnProperty.call(fold, key)) {
                g.collapsed = !!fold[key]
              }
              walk(g.children || [])
              walk((g.containers || []).filter(c => c && typeof c === 'object'))
            }
          }
          walk(deep.groups)
          configStore.updateLayoutControlConfig(deep)
          configStore.markGroupManualSet()
          foldApplied = true
          // 状态已改, 触发一次重渲染
          if (props.diagramData) renderMermaid()
        } catch (e) {
          console.warn('[URL-state] fold 解析失败:', foldRaw, e)
        }
      }

      applyScopeHighlight()
      // fold 等待 groups 首次就绪后应用 (updateLayoutControlConfig 整体替换会再触发本 watch,
      //   foldApplied 标志防止重复应用)
      watch(() => configStore.layoutControlConfig?.groups, (g) => {
        if (Array.isArray(g) && g.length) applyFold(configStore.layoutControlConfig)
      }, { immediate: true })

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
      // [CTX 2026-08-07] 右键菜单: 全局点击关闭
      document.addEventListener('click', closeContextMenu)
      // [DEBUG 2026-08-07] Ctrl+Shift+D 一键 dump 状态到控制台 (仅 ?mode=debug)
      _debugKeydownHandler = (e) => {
        // [OBS 2026-08-10] Ctrl+Shift+T: 任意模式打开状态真相面板 (可排查/可验证, 不依赖 debug)
        if (e.ctrlKey && e.shiftKey && e.key === 'T') {
          e.preventDefault()
          openTruthPanel()
          return
        }
        if (!debug.isDebug) return
        if (e.ctrlKey && e.shiftKey && e.key === 'D') {
          e.preventDefault()
          const dump = window.__archPage?.debug?.dump
          if (dump) {
            const state = dump()
            console.log('=== [DEBUG] Ctrl+Shift+D dump ===')
            console.log('layoutControlConfig:', JSON.stringify(state.layoutControlConfig, null, 2).slice(0, 2000) + '...')
            console.log('ctxMenu:', state.ctxMenu)
            console.log('svg clusters:', state.svg?.clusters?.length)
            console.log('svg nodes:', state.svg?.nodes?.length)
            console.log('collapsed groups:', state.layoutControlConfig?.groups?.filter?.(g => g.collapsed)?.length)
            console.log('hidden groups:', state.layoutControlConfig?.groups?.filter?.(g => g.visible === false)?.length)
            console.log('=== end dump ===')
          }
        }
      }
      document.addEventListener('keydown', _debugKeydownHandler)
    })

    onBeforeUnmount(() => {
      clearTimeout(resizeDebounceTimer)
      window.removeEventListener('resize', handleWindowResize)
      // 关键修复 v9：清理 fullscreenchange 监听
      document.removeEventListener('fullscreenchange', handleFullscreenChange)
      // [CTX 2026-08-07] 右键菜单: 清理全局点击关闭
      document.removeEventListener('click', closeContextMenu)
      // [DEBUG 2026-08-07] 清理键盘快捷键
      if (_debugKeydownHandler) document.removeEventListener('keydown', _debugKeydownHandler)
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

    // 导出为原生格式
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
        const overallDirection = effectiveLayoutControlConfig.value?.overallDirection || 'TB'
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
          // [FIX 2026-07-30] maxEdges 必须为 TOP-LEVEL 配置 (mermaid 11 secure 项)
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
            const maxScale = 10;
            
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
          // [FIX 2026-07-30] maxEdges 必须为 TOP-LEVEL 配置 (mermaid 11 secure 项)
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
    mermaid.initialize({ startOnLoad: false, maxTextSize: ${config.maxTextSize} });

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

      // [BUG-V034 十一轮修复 2026-06-29] 提升 PDF 清晰度
      //   之前 scale=1.5 + MAX_SVG_DIMENSION=2400, 大图降级到 renderScale=0.3, 模糊
      //   现在 scale=2 + MAX_SVG_DIMENSION=6400, 同样大图 renderScale=0.8, 清晰度提升 7x
      //   canvas 像素上限 100M (6400×6400×4byte=164MB, 可接受)
      const scale = 2
      const padding = 20

      try {
        // ============================================================
        // [BUG-V034 十轮修复 2026-06-29] 改回 SVG → Image 路径（避免九轮卡死）
        //   九轮: html2canvas 整段渲染 → 大图遍历 SVG 内部 DOM → 10-30s 卡死
        //   本轮: SVG → Image 走 SVG 渲染管线（毫秒级） + 移除 <style> 块（避污染）
        // ============================================================

        // 获取 SVG 实际尺寸
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
        svgCloneForExport.setAttribute('width', String(exportSvgWidth))
        svgCloneForExport.setAttribute('height', String(exportSvgHeight))

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
        // [十一轮] MAX_SVG_DIMENSION 2400→6400, 提升大图清晰度
        //   canvas 像素上限 100M (6400×6400≈41M 像素 × 4byte = 164MB, 可接受)
        //   8000×4000 SVG: 旧 renderScale=0.3 (2400px), 新 renderScale=0.8 (6400px), 清晰度 +7x
        const MAX_SVG_DIMENSION = 6400
        const MAX_CANVAS_PIXELS = 100_000_000  // 100M 像素上限, 防内存爆炸
        let renderScale = scale
        const scaledW = exportSvgWidth * scale
        const scaledH = exportSvgHeight * scale
        if (scaledW > MAX_SVG_DIMENSION || scaledH > MAX_SVG_DIMENSION) {
          renderScale = Math.min(MAX_SVG_DIMENSION / exportSvgWidth, MAX_SVG_DIMENSION / exportSvgHeight)
        }
        // 双重保护: canvas 总像素超 100M 时再降级
        if (exportSvgWidth * renderScale * exportSvgHeight * renderScale > MAX_CANVAS_PIXELS) {
          const pixelRatio = Math.sqrt(MAX_CANVAS_PIXELS / (exportSvgWidth * exportSvgHeight))
          renderScale = Math.min(renderScale, pixelRatio)
        }
        if (renderScale !== scale) {
          console.log('[BUG-V034 十一轮诊断] SVG 降级, scale=', scale, '→', renderScale.toFixed(3),
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
        // [BUG-V034 九轮修复 2026-06-29] finalCanvas 来源说明
        //   finalCanvas 现在直接来自 html2canvas(pdfWrapper) 的输出
        //   html2canvas 走 DOM→canvas 路径, 完全绕开 SVG→Image→canvas 污染链
        //   → toDataURL 应正常返回 PNG data URL (前 23 字符 "data:image/png;base64,")
        console.log('[BUG-V034 九轮诊断] finalCanvas 尺寸:', finalCanvas.width, 'x', finalCanvas.height)
        let imgData
        try {
          imgData = finalCanvas.toDataURL('image/png')
          console.log('[BUG-V034 九轮诊断] toDataURL 返回长度:', imgData.length, '| 前 30 字符:', imgData.slice(0, 30))
        } catch (e) {
          console.error('[BUG-V034 九轮诊断] toDataURL 抛错:', e?.name, e?.message)
          throw e
        }
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
      relayoutCanvas: relayoutAfterSizeChange,
      // [FIX 2026-08-03] GlobalToolbar refresh reload 调用, 绕过 code-diff 跳过强制 mermaid.run() 重绘
      forceRerender,
      exportAsImage,
      exportAsNative,
      exportAsHtmlSimple,
      exportAsHtmlFull,
      exportAsPdf,
      copyToClipboard,
      // [FIX 2026-08-07] 必须暴露 rendering 给模板: 模板 v-if="rendering" 控制 overlay (loading 转圈)
      //   与 :class={ 'is-rendering': rendering } 隐藏未完成 SVG。此前未导出 → v-if 恒为 undefined/false,
      //   overlay 永不渲染 → 用户看不到 loading; is-rendering 也失效 → 渲染期 SVG 裸露 (堆叠图闪烁)。
      rendering,
      // [CTX 2026-08-07] 右键上下文菜单
      ctxMenu,
      handleContextMenu,
      executeContextMenuAction,
      // [FIX 2026-08-08] 必须暴露 handleDblClick 给模板: @dblclick.prevent="handleDblClick"
      //   之前未返回 → 模板绑定为 undefined → 实际双击 Vue 什么都不做
      handleDblClick,
      // [P0 2026-08-08] 调试模式门控: 模板中通过 debug.isDebug / debug.debugPanelVisible 等访问
      debug,
      // [OBS 2026-08-10] 状态真相面板 (任意模式)
      truthPanelVisible,
      openTruthPanel
    }
  }
}
</script>



