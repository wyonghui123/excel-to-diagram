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
        <button class="toolbar-btn toolbar-btn--primary" @click="exportAsHtmlFull" title="导出 HTML（可直接双击打开）">
          <AppIcon name="export" size="sm" />
          <span class="toolbar-btn-label">HTML</span>
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
          <div ref="mermaidContainer" class="mermaid-content" :class="[diagramType, { 'hide-tails': shouldHideTails }, { 'is-rendering': rendering, 'is-fold-rendering': foldRendering }]"></div>
        </div>
      </div>
      <!-- [UX 2026-08-05] 渲染覆盖层: mermaid.run() 期间 SVG 元素堆叠在中心,
           显示转圈覆盖层 + 隐藏未完成 SVG, 渲染完成后淡入, 消除"堆叠中心"闪烁 -->
      <!-- [ESCALATE 2026-08-17] 折叠/展开长耗时渲染 (超 FOLD_ESCALATE_MS 未完成) 也触发此遮罩,
           复用整屏"图表渲染中"提示, 解决角落小指示器对 10s 级渲染感知不足的问题 -->
      <transition name="rendering-fade">
        <div v-if="rendering || foldRenderingEscalated" class="mermaid-rendering-overlay">
          <el-icon class="mermaid-loading-icon" :size="28"><Loading /></el-icon>
          <span class="mermaid-loading-text">图表渲染中<span class="mermaid-loading-dots"><i></i><i></i><i></i></span></span>
        </div>
      </transition>
      <!-- [UX 2026-08-13] 折叠/展开渲染的轻量等待反馈: 延迟 500ms 显示的角落指示器.
           不遮罩整图 (旧图缓冲层持续可见), 长耗时渲染时给用户"正在渲染"信号, 避免误以为没点上 -->
      <transition name="fold-loading-fade">
        <div v-if="foldLoadingVisible" class="mermaid-fold-loading">
          <el-icon class="mermaid-fold-loading-icon" :size="16"><Loading /></el-icon>
          <span class="mermaid-fold-loading-text">渲染中...</span>
        </div>
      </transition>
      <!-- [CTX 2026-08-07] 右键上下文菜单: 按分组类型展示折叠/展开选项
           [CTX-COLOR 2026-08-11] 扩展支持子菜单项类型: divider 分隔线 / header 标题 /
           checked 当前值勾选 / back 返回 / submenu 子菜单指示(›), 见 buildColorSubmenuItems -->
      <!-- [FIX 2026-08-11] @click.stop: 阻止菜单内点击冒泡到 document 的 closeContextMenu.
           否则点击"颜色设置"时 enterColorSubmenu 触发重渲染替换 items, 原点击元素被卸载,
           closeContextMenu 中 wrapper.contains(e.target) 变 false → ctxMenu.visible=false
           → 菜单立即关闭, 表现为"子菜单没展开". -->
      <!-- [UX 2026-08-11] 多级菜单改为"悬停展开"最佳实践 (替代旧的点击进入+返回按钮):
           悬停带 › 的子菜单项时, 右侧滑出下级面板; 点击叶子项执行动作并关闭菜单.
           与 Windows/macOS/VS Code/Element Plus 等标准上下文菜单行为一致. -->
      <div v-if="ctxMenu?.visible" class="mermaid-ctx-menu"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        @click.stop
        @mouseleave="onMenuMouseLeave">
        <div v-if="ctxMenu.groupTitle" class="ctx-menu-header">{{ ctxMenu.groupTitle }}</div>
        <div v-if="ctxMenu.groupTitle" class="ctx-menu-divider"></div>
        <template v-for="(item, idx) in ctxMenu.items" :key="item.key ?? 'sep-' + idx">
          <div v-if="item.divider" class="ctx-menu-divider"></div>
          <div v-else-if="item.header" class="ctx-menu-header-sm">{{ item.header }}</div>
          <div v-else
            class="ctx-menu-item"
            :class="{ 'ctx-menu-item--submenu': hasSubmenu(item) }"
            @mouseenter="onItemMouseEnter($event, item)"
            @mouseleave="onItemMouseLeave($event, item)"
            @click="executeContextMenuAction(item.key)">
            <span v-if="item.checked" class="ctx-menu-check">✓</span>
            <span v-else class="ctx-menu-check-placeholder"></span>
            <span class="ctx-menu-label">{{ item.label }}</span>
            <span v-if="hasSubmenu(item)" class="ctx-menu-submenu-arrow">›</span>
          </div>
        </template>
        <!-- 悬停展开的子菜单面板 (子菜单项不再替换当前菜单, 而是作为独立面板滑出) -->
        <div v-if="submenuState.visible" ref="submenuRef" class="ctx-submenu"
          :style="{ left: submenuState.left + 'px', top: submenuState.top + 'px' }"
          @mouseenter="onSubmenuEnter"
          @mouseleave="onSubmenuLeave">
          <template v-for="(child, cidx) in submenuState.items" :key="child.key ?? 'csep-' + cidx">
            <div v-if="child.divider" class="ctx-menu-divider"></div>
            <div v-else-if="child.header" class="ctx-menu-header-sm">{{ child.header }}</div>
            <div v-else class="ctx-menu-item" @click="executeContextMenuAction(child.key)">
              <span v-if="child.checked" class="ctx-menu-check">✓</span>
              <span v-else class="ctx-menu-check-placeholder"></span>
              <span class="ctx-menu-label">{{ child.label }}</span>
            </div>
          </template>
        </div>
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
import { isFeatureEnabled } from '../utils/featureFlags.js'

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
import { buildContextMenuItems, buildGlobalExpandItems } from '../composables/useMermaid/contextMenu/contextMenuItems.js'
import { collectHiddenState } from '../composables/useMermaid/visibility/collectHiddenState.js'
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
    // [FIX 2026-08-13] 竞态守卫由"丢弃"改为"latest-wins 待重跑":
    //   isRendering=true 时收到的渲染请求不再被静默丢弃, 而是标记 pendingRerender;
    //   当前渲染结束 (setRendering(false)) 后自动按最新状态重跑一次.
    //   修复: 快速连续切换 chartType (BO→SM→BO) 时, 最后选择的 BO 渲染被丢弃,
    //   导致 chartConfig 已是 businessObject 但 SVG 仍停留在 SM 图 (状态不一致).
    let pendingRerender = false
    // [UX 2026-08-05] 渲染覆盖层状态 (转圈 + SVG 淡入):
    //   mermaid.run() 期间 SVG 元素尚未布局定位 (全部堆叠在中心), 用户体验差.
    //   rendering 为响应式 ref, 模板据此显示覆盖层 + 隐藏未完成 SVG; 渲染完成后淡入.
    //   setRendering 统一封装 (isRendering 防重入 guard + rendering 覆盖层开关), 避免遗漏退出点.
    const rendering = ref(false)
    // [FOLD-OVERLAP 2026-08-12] 折叠渲染期间隐藏新 SVG (与 is-rendering 同等效果),
    //   但不触发 loading 遮罩 (rendering 保持 false). 根因: 折叠渲染跳过遮罩后,
    //   .mermaid-content 缺少 is-rendering class, CSS 规则不生效, 新 SVG 在 mermaid.run()
    //   布局完成前全部堆叠在中心且完全可见, 用户透过缓冲层看到底层元素重叠.
    const foldRendering = ref(false)
    // [UX 2026-08-13] 折叠/展开渲染的轻量等待反馈: 折叠渲染跳过整屏遮罩 (旧图平滑过渡),
    //   但长耗时渲染 (如展开到业务对象数十秒) 时用户无任何"正在渲染"信号, 会误以为没点上.
    //   方案: 折叠渲染开始后延迟 FOLD_LOADING_DELAY_MS 显示角落小指示器 (不遮罩整图),
    //   快速折叠 (数十 ms) 不闪, 慢速渲染 (服务模块/业务对象) 才提示. 渲染结束即清除.
    const FOLD_LOADING_DELAY_MS = 500
    const foldLoadingVisible = ref(false)
    let foldLoadingTimer = null
    // [ESCALATE 2026-08-17] 长耗时折叠/展开渲染升级整屏遮罩:
    //   角落小指示器 (foldLoadingVisible) 对 10s 级渲染太弱, 用户感知不到反馈.
    //   折叠渲染开始 FOLD_ESCALATE_MS 后仍未完成 → foldRenderingEscalated=true,
    //   触发与全量渲染相同的整屏"图表渲染中"遮罩 (模板 v-if 或关系, CSS 复用).
    //   快速折叠 (<阈值) 不升级, 保持"不闪整屏 loading"的平滑体验.
    const FOLD_ESCALATE_MS = 2000
    const foldRenderingEscalated = ref(false)
    let foldEscalateTimer = null
    const scheduleFoldEscalate = () => {
      if (foldEscalateTimer) clearTimeout(foldEscalateTimer)
      foldEscalateTimer = setTimeout(() => {
        foldEscalateTimer = null
        foldRenderingEscalated.value = true
      }, FOLD_ESCALATE_MS)
    }
    const cancelFoldEscalate = () => {
      if (foldEscalateTimer) { clearTimeout(foldEscalateTimer); foldEscalateTimer = null }
      foldRenderingEscalated.value = false
    }
    const showFoldLoading = () => {
      if (foldLoadingTimer) clearTimeout(foldLoadingTimer)
      foldLoadingTimer = setTimeout(() => { foldLoadingVisible.value = true }, FOLD_LOADING_DELAY_MS)
      scheduleFoldEscalate()  // [ESCALATE 2026-08-17] 超时升级整屏遮罩
    }
    const hideFoldLoading = () => {
      if (foldLoadingTimer) { clearTimeout(foldLoadingTimer); foldLoadingTimer = null }
      foldLoadingVisible.value = false
      cancelFoldEscalate()  // [ESCALATE 2026-08-17] 渲染结束统一清除升级状态
    }
    const setRendering = (v) => {
      isRendering = v
      rendering.value = v
      // [A1 2026-08-10] 渲染完成 (v=false) 时释放折叠缓冲层, 露出新图 (交叉过渡由 CSS 完成).
      //   放在 setRendering 统一出口, 保证所有完成/错误路径都会释放, 不留残留覆盖层.
      if (!v && foldBufferLayer) {
        releaseFoldBuffer()
      }
      // [FOLD-OVERLAP 2026-08-12] 渲染完成时同步清除折叠渲染标记
      if (!v) {
        foldRendering.value = false
        hideFoldLoading()  // [UX 2026-08-13] 折叠渲染结束, 隐藏角落等待指示器
      }
      // [FIX 2026-08-13] latest-wins: 渲染结束 (v=false) 且期间有请求被丢弃时,
      //   按最新状态重跑一次, 保证最后一次配置变更 (如 chartType) 生效.
      //   仅在 renderMermaid 内 setRendering(false) 时触发, 避免死循环:
      //   pendingRerender 被消费后即复位, 重跑若未被再次丢弃则不再重入.
      if (!v && pendingRerender) {
        pendingRerender = false
        nextTick(() => renderMermaid())
      }
    }
    // [A1 2026-08-10] 方案 A: 折叠/展开渲染的"跳过整屏 loading + 双缓冲平滑过渡"状态.
    //   foldRenderPending = true  → 下一次 renderMermaid 由折叠/展开触发, 不闪转圈遮罩.
    //   foldBufferSvg = 渲染前克隆的旧 SVG, 作为缓冲层保留在 mermaid-wrapper 中,
    //   新图 mermaid.run() 完成后交叉过渡 (旧图淡出 + 新图淡入), 避免"折叠闪整屏 loading + 空白".
    //   消费后立即重置, 不影响后续普通全量渲染 (方向/引擎/分组结构等仍走原 loading).
    let foldRenderPending = false
    let foldBufferLayer = null  // [A1] 折叠渲染时保留的旧 SVG 缓冲层 (DOM 元素), 新图就绪后移除

    // [A1 2026-08-10] 方案 A: 折叠缓冲层 — 克隆当前 SVG 到 mermaid-wrapper 作为占位背景.
    //   折叠/展开渲染期间不闪转圈遮罩, 旧图 (克隆) 持续可见, 消除"折叠瞬间空白闪烁".
    //   注意: 克隆为深拷贝快照 (独立 DOM), 不参与交互/高亮; 新图就绪后 releaseFoldBuffer 移除.
    const captureFoldBuffer = () => {
      const wrapper = mermaidWrapper.value
      const content = mermaidContainer.value
      const svg = content?.querySelector('svg')
      if (!wrapper || !svg || !content) return
      // 清除旧的残留缓冲层 (防御: 理论不出现).
      // [FIX 2026-08-13] 不能只依赖 foldBufferLayer ref: releaseFoldBuffer 会先置 null,
      //   若前一个 --leaving 层的 setTimeout(300ms)/transitionend 清理尚未触发 (标签页节流/HRM),
      //   它会成为孤儿 DOM, 且其无 cluster 的克隆树会被 snapshot()/E2E 误统计 (81 vs 41 根因).
      //   故按 wrapper 内所有 .mermaid-fold-buffer 统一清除, 而非仅引用指向的那一个.
      wrapper.querySelectorAll('.mermaid-fold-buffer').forEach((el) => {
        if (el.parentNode) el.parentNode.removeChild(el)
      })
      foldBufferLayer = null
      const layer = document.createElement('div')
      layer.className = 'mermaid-fold-buffer'
      // [FOLD-OVERLAP 2026-08-12] 捕获 content 的 pan/zoom transform 并应用到缓冲层,
      //   使克隆的旧图与新 SVG 在同一视觉位置渲染. 之前未复制 transform, 用户平移/缩放后
      //   克隆图在 wrapper 原点位置, 新图在 transform 偏移位置, 过渡期间两者错位重叠可见.
      const contentTransform = content.style.transform
      if (contentTransform) {
        layer.style.transform = contentTransform
      }
      // 深克隆 SVG (保留 viewBox/样式), 作为折叠期间可见的旧图占位
      layer.appendChild(svg.cloneNode(true))
      // 插入到 wrapper 内 (遮罩层之下, 内容层之上), 与渲染覆盖层同层定位
      wrapper.appendChild(layer)
      foldBufferLayer = layer
    }

    // [A1 2026-08-10] 释放折叠缓冲层: 新图渲染完成, 移除旧图占位, 露出新图.
    //   移除时给缓冲层加淡出 class, 由 CSS transition 完成旧图淡出 (交叉过渡).
    const releaseFoldBuffer = () => {
      const layer = foldBufferLayer
      foldBufferLayer = null
      if (!layer || !layer.parentNode) return
      const done = () => {
        if (layer.parentNode) layer.parentNode.removeChild(layer)
      }
      layer.classList.add('mermaid-fold-buffer--leaving')
      // 等待 CSS 淡出过渡完成后移除 DOM; 兜底定时器防止 transition 未触发残留
      const t = setTimeout(done, 300)
      layer.addEventListener('transitionend', () => {
        clearTimeout(t)
        done()
      })
    }

    let lastRenderData = null  // 上次渲染的数据，用于检测变化
    // [FIX 2026-08-02] L5 渲染跳过 (spec 4.4): 上次生成的 mermaidCode, code-diff 用
    let lastRenderedCode = null
    // [SIMPLE 2026-08-15] 追踪最近一次关联点设置 (diagramData.hideLinkLabelTails).
    //   关联点切换只改 diagramData 字段, 不改变 mermaid code → code-diff 会跳过 mermaid.run,
    //   processSvg 无法用新值重算拖尾线 → 需清空 lastRenderedCode 强制重绘 (问题2: 直线+手动打开
    //   关联点立即生效, 无需等刷新).
    let lastTailSetting = null
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

    // [SIMPLE 2026-08-15] 拖尾线(关系连线关联点)可见性 — 模板 hide-tails 类绑定:
    //   true → 隐藏; false → 始终显示(直线/ELK 下手动打开也显示);
    //   null/undefined(自动) → 跟随引擎: ELK(直线)隐藏, Dagre(曲线)显示.
    const shouldHideTails = computed(() => {
      const tailSetting = props.diagramData?.hideLinkLabelTails
      return tailSetting === true || (tailSetting !== false && props.layoutEngine === 'elk')
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
      // 防止无限循环: 忙时标记"待重跑"而非丢弃 (latest-wins, 保证最后一次选择胜出)
      if (isRendering) {
        pendingRerender = true
        return
      }
      // [A1 2026-08-10] 方案 A: 折叠/展开渲染不闪整屏 loading.
      //   消费 foldRenderPending: 折叠时跳过转圈遮罩 (rendering 保持 false), 并克隆旧 SVG
      //   到缓冲层, 新图 mermaid.run() 完成后交叉过渡, 避免"折叠闪 loading + 空白闪烁".
      //   消费后立即重置, 不影响后续普通全量渲染.
      const isFoldRender = foldRenderPending
      foldRenderPending = false
      if (isFoldRender) {
        // 仅防重入 guard, 不触发转圈遮罩 (rendering 保持 false)
        isRendering = true
        // [FOLD-OVERLAP 2026-08-12] 设置折叠渲染标记, 给 .mermaid-content 加 is-fold-rendering class,
        //   使 CSS 规则 `.mermaid-content.is-fold-rendering svg { opacity: 0 }` 生效,
        //   隐藏 mermaid.run() 期间堆叠在中心的新 SVG 元素, 避免透过缓冲层看到重叠.
        foldRendering.value = true
        showFoldLoading()  // [UX 2026-08-13] 延迟 500ms 显示角落等待指示器 (快速折叠不闪)
        captureFoldBuffer()
        // 必须等 DOM 更新 (class 刷进 .mermaid-content) 再开始渲染, 否则 mermaid.run()
        // 写新 SVG 时 class 还没生效, 新元素仍然可见.
        await nextTick()
      } else {
        setRendering(true)
      }
      // [FIX 2026-08-07] 强制 DOM flush: rendering=true 先把 overlay 刷进 DOM,
      //   再跑大计算 (generateMermaidCode / mermaid.run). 否则非 ELK 路径完全无 await,
      //   Vue scheduler 没机会 commit, overlay 永不显示 → 用户看到几秒钟空白.
      //   nextTick (微任务, Vue DOM 更新完成) + rAF (下一帧浏览器绘制) 保证用户肉眼看到 loading,
      //   才进入后续同步计算。
      // [A1 2026-08-10] 折叠渲染跳过此等待 (无遮罩可刷, 且要尽快开始渲染).
      if (!isFoldRender) {
        await nextTick()
        await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      }
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
          // [PERF OBS 2026-08-13] 补齐 syntax_gen 计时 (generateMermaidCode 耗时),
          //   与 useMermaidRenderer 的 syntax_gen 口径一致, 量化大图语法生成开销.
          const tSyntax = diag.time('syntax_gen')
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

            diag.endStep('syntax_gen', tSyntax)

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
                // [OBS 2026-08-13] 源码 subgraph 数: 与 data-container-count(实际 g.cluster) 比对,
                //   一条 evaluate 即可定位"源码有 subgraph 但 SVG 无容器"的渲染丢失问题.
                window.__archPage.mermaid.subgraphInSrc = (mermaidCode.match(/subgraph/g) || []).length
              }
              // [VIS-RESET 2026-08-14 简化] 重渲染即重置隐藏: 即使 code-diff 跳过 mermaid.run(),
              //   旧 SVG 上 updateVisibilityOnly 设置的 display:none 必须清除, 否则被隐藏的分组
              //   因跳过 mermaid.run() 而保持隐藏 (store 已重置 visible=true, 但 SVG 残留 none).
              //   清除范围: 所有 g.node / g.cluster / g.edgePath 的 style.display (updateVisibilityOnly
              //   设置的是 '' 或 'none', 清除后回归默认渲染态).
              const skipSvg = mermaidContainer.value.querySelector('svg')
              skipSvg?.querySelectorAll('g.node, g.cluster, g.edgePath, g.flowchart-link, g.edgeLabel').forEach(el => {
                if (el.style.display === 'none') el.style.display = ''
              })
              // 同步 data-chart-rendered 标记 (走 diag.endRender → EmbeddedChartView onDiagRenderEnd):
              //   图表已是终态 (旧 SVG 即当前结果), 让 E2E wait_render_stable 不因"无新渲染"空等超时.
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
                // [OBS 2026-08-13] 源码 subgraph 数 (见上方跳过分支说明)
                window.__archPage.mermaid.subgraphInSrc = (mermaidCode.match(/subgraph/g) || []).length
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
          // [PERF OBS 2026-08-13] 主渲染路径 mermaid.run() (ELK 布局) 计时.
          //   此前该路径未埋点, 主导成本 (~87% 渲染耗时) 在 stepTimings 中不可见,
          //   导致性能回归无法量化. 此处补记 syntax_gen + mermaid_run 两步.
          const _tRun = diag.time('mermaid_run')
          mermaid.run(_runOpts)
            .then(() => {
              diag.endStep('mermaid_run', _tRun)
              const svgElAfter = mermaidContainer.value?.querySelector('svg')
              if (svgElAfter) {
                svgProcessor.processSvg(svgElAfter, props, relationDescriptions, mermaidContainer, nodeColorMappings, interaction, handleToggleGroupVisible, legendItemColorChangeHandler)

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

                // [REL-HL 2026-08-16] 连线交互: 左击→高亮连线+源/目标(不淡化); 右击→弹菜单, 选"高亮关系"才淡化.
                //   只在首次渲染后绑定 (svg 引用唯一), 避免重复绑定.
                const bindEdgeFocus = (svg) => {
                  if (!svg || svg.getAttribute('data-edge-focus-bound')) return
                  svg.setAttribute('data-edge-focus-bound', '1')
                  const edgeIdxFromTarget = (e) => {
                    // 优先: 连线标签 (g.edgeLabel 分组) — 注意 .edgeLabel 类在 <span> 上, 必须取最近 g.edgeLabel 分组做索引
                    const labelGroup = e.target.closest('g.edgeLabel')
                    if (labelGroup) return Array.from(svg.querySelectorAll('g.edgeLabel')).indexOf(labelGroup)
                    // 其次: 连线 path (可能直接命中 path, 或命中 g.edgePath/g.edgePaths 容器)
                    const edgePaths = getAppEdgePaths(svg)
                    const hitEl = e.target.closest('path.flowchart-link, path.edge-thickness-normal, g.edgePath, g.edgePaths, g.edges, .edgePath, .edgePaths')
                    if (hitEl) {
                      const realPath = hitEl.tagName === 'path' ? hitEl : (hitEl.querySelector && hitEl.querySelector('path'))
                      if (realPath) return edgePaths.indexOf(realPath)
                    }
                    return -1
                  }
                  svg.addEventListener('click', (e) => {
                    // [FIX 2026-08-16] 拖拽后的 click 不触发连线高亮 (只有纯粹点击才处理)
                    if (window.__mermaidDrag && window.__mermaidDrag.wasDrag) return
                    const idx = edgeIdxFromTarget(e)
                    if (idx >= 0) {
                      e.stopPropagation()
                      // 左击选中: 高亮连线+源/目标, 不淡化其余
                      highlightEdgeFocus(svg, idx, false)
                    }
                  })
                  svg.addEventListener('contextmenu', (e) => {
                    const idx = edgeIdxFromTarget(e)
                    if (idx >= 0) {
                      e.preventDefault()
                      e.stopPropagation()
                      // 右击连线 → 弹菜单: 标题=连线标签(XXX-YYY), 分隔线, 选项"关系高亮"(选中后连线+源/目标+其余淡化)
                      const labels = svg.querySelectorAll('g.edgeLabel')
                      const labelText = (labels[idx] && (labels[idx].textContent || '').trim()) || '关系高亮'
                      ctxMenu.visible = false
                      closeSubmenu()
                      ctxMenu.isGlobal = false
                      ctxMenu.groupTitle = labelText.slice(0, 60)
                      ctxMenu.elementCode = ''
                      ctxMenu.edgeIdx = idx
                      ctxMenu.items = [
                        { key: 'edgeFocus', label: '关系高亮' }
                      ]
                      ctxMenu.x = e.clientX
                      ctxMenu.y = e.clientY
                      ctxMenu.visible = true
                    }
                  })
                }
                bindEdgeFocus(svgElAfter)

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

                  // [SIMPLE 2026-08-15] 拖尾线(关系连线关联点)可见性:
                  //   true → 隐藏; false → 始终显示(直线/ELK 下手动打开也显示);
                  //   null/undefined(自动) → 跟随引擎: ELK(直线)隐藏, Dagre(曲线)显示.
                  const tailSetting = props.diagramData?.hideLinkLabelTails
                  const shouldHideTails = tailSetting === true ||
                    (tailSetting !== false && props.layoutEngine === 'elk')

                  if (shouldHideTails) {
                    // [FIX 2026-08-12] 立即隐藏拖尾线+dot, 消除首屏 2s 闪烁 (用户反馈:
                    //   "渲染最开始的很短时间内有拖尾线 + dot 展示, 很快又消失").
                    //   原实现 setTimeout(...,2000) 导致 ELK 下首屏拖尾线残留 2s.
                    //   保留延迟重跑: mermaid 部分 edgeLabel/拖尾元素异步渲染, 兜底清除迟到元素.
                    hideLinkLabelTails()
                    setTimeout(() => hideLinkLabelTails(), 500)
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
              diag.endStep('mermaid_run', _tRun)  // [PERF OBS 2026-08-13] 失败也关闭计时
              // [FIX 2026-08-01] 渲染失败埋点
              diag.recordError(err, 'renderMermaid')
              diag.endRender({ error: err?.message || String(err) })
            })
        } catch (err) {
          // [FIX 2026-08-03] A1: nextTick 同步异常兜底 (e.g. ReferenceError / TypeError).
          //   不再静默失败: 走 diag 链路 → onError hook → EmbeddedChartView emit render-error →
          //   ArchDataManagement.handleChartRenderError → ElMessage.error toast.
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
      // [FIX 2026-08-12 同码歧义] 键升级为复合键 code::groupType (与 identifyGroupFromSvg / groupStateKey 同规则)。
      //   子领域与服务模块可能同码 (子领域"内部交易"=ITTF 与服务模块"内部交易"=ITTF;
      //   子领域"销售"=SM 与服务模块"服务管理"=SM)。旧实现用 code 单一键, 后遍历的同码服务模块
      //   覆盖子领域条目 → updateCollapseNodeColors 取到错误上下文: 按服务模块分组时子领域聚合节点
      //   显示服务模块色(应为中性灰), 按领域分组时"销售"子领域取到"服务管理"所在领域色(应为供应链云)。
      //   保留纯 code 条目作为兜底 (仅首个同码条目, 不覆盖), 供 id 无层级标记的聚合节点查询。
      const collapseCtxKey = (item) => {
        const base = item.elementCode || item.id
        if (base == null) return null
        const raw = item.groupType || item.type || ''
        const gt = String(raw).toLowerCase().replace(/_/g, '')
        return gt ? `${String(base)}::${gt}` : String(base)
      }
      const ctxEntry = (g, ctx) => ({
        domainName: ctx.domain || '',
        subDomainName: ctx.subDomain || '',
        serviceModuleName: ctx.serviceModule || '',
        title: g.title || g.name || '',
        groupType: g.groupType || ''
      })
      // [FIX 2026-08-11 容器连线增量变色] collapseNodeMap: COLLAPSE_<sanitized g.id> → 分组上下文,
      //   供 updateLinkColors 解析容器/聚合连线端点 (与语法层 COLLAPSE_${sanitizeId(g.id)} 同规则).
      const collapseNodeMap = new Map()
      const walkGroups = (list, ctx) => {
        ;(list || []).forEach((g) => {
          if (!g || typeof g !== 'object') return
          const nextCtx = { ...(ctx || {}) }
          if (g.groupType === 'domain') nextCtx.domain = g.title || g.name
          else if (g.groupType === 'subDomain') nextCtx.subDomain = g.title || g.name
          else if (g.groupType === 'serviceModule') nextCtx.serviceModule = g.title || g.name
          const code = g.elementCode || g.id
          if (code) {
            const entry = ctxEntry(g, nextCtx)
            const composite = collapseCtxKey(g)
            if (composite) collapseCtxMap.set(composite, entry)
            // 纯 code 兜底条目: 仅首个同码分组保留 (避免被后遍历的同码服务模块覆盖)
            if (!collapseCtxMap.has(String(code))) {
              collapseCtxMap.set(String(code), entry)
            }
          }
          if (g.id != null) {
            const collapseId = `COLLAPSE_${String(g.id).replace(/[^\w\u4e00-\u9fff]/g, '_')}`
            collapseNodeMap.set(collapseId, {
              code,
              groupType: g.groupType || '',
              domainName: nextCtx.domain || '',
              subDomainName: nextCtx.subDomain || '',
              serviceModuleName: nextCtx.serviceModule || ''
            })
          }
          walkGroups(g.children, nextCtx)
          walkGroups(g.containers, nextCtx)
        })
      }
      walkGroups(props.layoutControlConfig?.groups, {})

      // [FIX 2026-08-09 v2] 折叠/展开/legend 共用同一份 colorMap (键=serviceModuleName/domain/subDomain)。
      //   [FIX 2026-08-13 范围外节点中性 bug] 统一改用 data.nodes 全量 BO 节点构建 colorMap,
      //   不再优先用 nodeColorMappings (buildColorMap)。
      //   根因: nodeColorMappings 在 syntax 层会跳过被折叠隐藏的 BO (hiddenBoIds), 而"对象范围外
      //   且折叠到子领域"的 BO 恰好被隐藏 → buildColorMap 只收集到范围内领域, 范围外领域键缺失 →
      //   updateCollapseNodeColors 取色失败 → 范围外聚合节点全部回退 #fafafa 中性灰。
      //   data.nodes 是完整 BO 集 (category==='object' 全量), 含折叠/范围外 BO, 与全量渲染
      //   colorMap (useBusinessObjectSyntax 遍历 businessObjectNodes) 同源, 覆盖全部领域。
      const colorSchemeColors = colors.getColorScheme(data.colorScheme)
      const unifiedColorMap = colors.buildColorMapFromNodes(
        data.nodes || [],
        colorGroupBy,
        colorSchemeColors,
        data.customColors || {},
        objectToModuleMap
      )

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
        const colorMap = unifiedColorMap

        // [FIX 2026-07-31] 传 centerScopeHighlight 信息, 让 updateNodeColors 给 centerScope BOs 加边框区分
        colors.updateNodeColors(svg, nodeColorMappings, objectToModuleMap, colorGroupBy, colorMap, {
          centerScopeHighlight: data.centerScopeHighlight,
          centerScope: data.centerScope || [],
          centerScopeColor: data.centerScopeColor || '#808080'
        })
      }
      // [FIX 2026-08-11 容器连线增量变色] 连线颜色更新移出 nodeColorMappings 守卫:
      //   折叠视图 nodeColorMappings 为空但 linkColorMappings 仍有容器连线 (COLLAPSE_<id>),
      //   旧实现因守卫拦截而永不执行 → 改分组色后容器连线不变色. 现通过 collapseNodeMap
      //   解析容器端点, 与 updateCollapseNodeColors 同源 (colorMap + centerScopeMarkers).
      // linkColorMappings 为空时跳过 (很多 BO 图无 link)
      if (linkColorMappings && linkColorMappings.length > 0) {
        colors.updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, colorGroupBy, unifiedColorMap, {
          centerScopeHighlight: data.centerScopeHighlight,
          centerScope: data.centerScope || [],
          centerScopeColor: data.centerScopeColor || '#808080',
          collapseNodeMap,
          centerScopeMarkers: configStore.centerScopeMarkers || {}
        })
        // [FIX 2026-08-05] 增量改线色后, 同步箭头 marker 颜色跟随线色
        //   (updateLinkColors 只改 path stroke, 箭头 marker 仍留在全量渲染时的旧色 →
        //    改对象范围色/配色后线色变了但箭头色没变).
        svgStyle.syncArrowMarkers(svg, props.diagramType)
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
          svgProcessor.updateColorLegend(svg, data, props.annotationConfig, nodeColorMappings, props.layoutControlConfig?.groups || null, handleToggleGroupVisible, unifiedColorMap, legendItemColorChangeHandler)
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

      // [REFACTOR 2026-08-14] 隐藏集合收集逻辑抽到纯函数 collectHiddenState.js (可单元测试,
      //   回归保护 ELK 系统分组误判为用户隐藏 bug). 见该模块顶部注释.
      const { hiddenNodeCodes, hiddenContainerCodes, hiddenCollapseIds } = collectHiddenState(
        groups,
        { isScopeProtected },
      )

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

      // [FOLD-ANN 2026-08-18] 增量隐藏/显示后联动刷新备注面板:
      //   被隐藏分组的元素备注项同步消失, 恢复显示时同步回归 (无需全量重渲染)。
      try { annotationOverlay.refreshAnnotationPanelVisibility(svg) } catch (e) {
        console.warn('[updateVisibilityOnly] refreshAnnotationPanelVisibility failed:', e)
      }

      return true
    }

    // [VIS-RESET 2026-08-14 简化] 清除 SVG 上 updateVisibilityOnly 设置的 display:none 残留.
    //   用于"重渲染操作" (切换展开层级/方向/引擎等) 后, 即使渲染结果与上次相同 (code-diff 跳过
    //   renderMermaid / watch 无变化), 也要恢复被隐藏分组的显示 (渲染层已强制 visible=true).
    const clearSvgHidden = () => {
      const svg = mermaidContainer.value?.querySelector('svg')
      if (!svg) return
      svg.querySelectorAll('g.node, g.cluster, g.edgePath, g.flowchart-link, g.edgeLabel').forEach(el => {
        if (el.style.display === 'none') el.style.display = ''
      })
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

    // [LEGEND-COLOR 2026-08-11] 方案A: 图例项色块改色 handler.
    //   写入 store.customColors[colorKey] → useDiagramData 重建 diagramData(customColors)
    //   → 本组件 watcher 检测 colorChanged.customColors → updateColorsOnly 增量变色 (不重排).
    //   color=null 表示"恢复默认" (删除该分组自定义色, 回退配色方案默认).
    //   [FLAG 2026-08-11] 受 feature flag legendItemColor 控制: flag 关闭时传 null,
    //   annotationOverlay 不附加色块可编辑 affordance (悬停环/铅笔/点击), 可快速回退.
    // [LEGEND-COLOR v2 2026-08-11] 对象范围项 (colorKey='__centerScope__') 改色走
    //   store.updateCenterScopeColor (更新 centerScopeColor), 而非 customColors.
    //   color=null 表示"恢复默认" (回退 #808080). 该字段已纳入 colorStateTracker 快照,
    //   改色 → useDiagramData 重建 → 本组件 watcher 检测 colorChanged.centerScopeColor
    //   → updateColorsOnly 增量变色 (同时重算中心相关连线颜色).
    const handleLegendItemColorChange = (colorKey, color) => {
      if (!colorKey) return
      if (colorKey === '__centerScope__') {
        configStore.updateCenterScopeColor(color || '#808080')
        return
      }
      const next = { ...configStore.customColors }
      if (color) next[colorKey] = color
      else delete next[colorKey]
      configStore.updateCustomColors(next)
    }
    const legendItemColorChangeHandler = isFeatureEnabled('legendItemColor') ? handleLegendItemColorChange : null

    // [CTX 2026-08-07] 右键上下文菜单
    const ctxMenu = reactive({
      visible: false,
      x: 0,
      y: 0,
      groupTitle: '',
      // [FIX 2026-08-08] 新增 elementCode: 用于 executeContextMenuAction 中精确匹配分组,
      //   避免仅靠 groupTitle (标题) 匹配可能因标题重名/空格/编码差异导致 findGroupInTree 找不到.
      elementCode: '',
      // [EDGE-HL 2026-08-16] 右击连线菜单: 记录被右击连线的索引, 供 "edgeFocus" 菜单项执行聚焦高亮.
      edgeIdx: null,
      // [CTX-GLOBAL 2026-08-10] 空白区域右键 = 全局展开层级菜单 (替代 GlobalToolbar 展开层级下拉).
      //   true 时 groupTitle 显示"展开层级", 各选项为 expandGlobal:<key>.
      isGlobal: false,
      // items: { key, label, checked?, divider?, header? } 或 { key, label, children: [...] } (子菜单项)
      items: []
    })

    // [UX 2026-08-11] 悬停子菜单状态: 子菜单项悬停时滑出的独立面板.
    //   替代旧的"点击进入 + 返回按钮"(backStack) 模式.
    const submenuState = reactive({
      visible: false,
      left: 0,
      top: 0,
      openKey: '',   // 当前展开的子菜单项 key
      anchorRect: null, // 父菜单项 rect, 用于右侧溢出时向左翻转定位
      items: []      // 子菜单面板内的项
    })
    const submenuRef = ref(null)
    let submenuCloseTimer = null

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
        // [FIX 2026-08-12 同码歧义] 聚合节点 id 含层级前缀 (flowchart-COLLAPSE_SD_ITTF-26 子领域 /
        //   COLLAPSE_SM_ITTF-26 服务模块 / COLLAPSE_D_SCM 领域), 而 data-container-code 仅编码
        //   ("ITTF"). 子领域与服务模块可能同码 (例: 子领域"内部交易"=ITTF 与服务模块"内部交易"=ITTF),
        //   单一 elementCode 匹配 findGroupInTree 会命中树中第一个同码分组(子领域), 导致双击
        //   服务模块聚合节点被识别为子领域 → handleDblClick 判定其 collapsed 后折叠整棵子树
        //   (用户反馈: "展开服务模块后, 内部交易整体折叠").
        //   修复: 从 id 推断层级前缀后, 按 code::groupType 复合键精确匹配 (与 layoutPanelAdapter.groupStateKey 一致).
        let inferredGroupType = ''
        const gtMatch = id.match(/(?:COLLAPSE_|G_)(D|SD|SM)_/)
        if (gtMatch) {
          const prefix = gtMatch[1]
          if (prefix === 'D') inferredGroupType = 'domain'
          else if (prefix === 'SD') inferredGroupType = 'subDomain'
          else if (prefix === 'SM') inferredGroupType = 'serviceModule'
        }
        const group = findGroupInTree(ctxCfg.groups, g => {
          const key = g.elementCode || g.id
          if (key !== elementCode && g.title !== elementCode) return false
          if (inferredGroupType) {
            const gt = String(g.groupType || g.type || '').toLowerCase().replace(/_/g, '')
            const want = inferredGroupType.toLowerCase().replace(/_/g, '')
            return gt === want
          }
          return true
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
    // [UX 2026-08-14] 折叠/展开 (容器核心操作) 放首位, "关系高亮" 用分隔线归为第二组.
    // [REFACTOR 2026-08-14] 逻辑抽到纯函数 contextMenuItems.js (可单元测试)
    const getContextMenuItems = (group) => buildContextMenuItems(group)

    // [CTX-HL 2026-08-14] 右击对象临时高亮 (如同"选中"): 复用 annotationOverlay 选中高亮样式
    //   (.annotation-highlighted + 红色 drop-shadow + 加粗), 只动 SVG, 不同步备注面板.
    //   生命周期 (用户确认: 临时高亮): 弹菜单时高亮右击的容器/节点; 菜单关闭 / 执行菜单项 /
    //   再次右击其他对象时清除, 不改变左键选中状态.
    let _ctxHighlightedEl = null
    const clearRightClickHighlight = () => {
      if (_ctxHighlightedEl) {
        _ctxHighlightedEl.classList.remove('annotation-highlighted')
        const rect = _ctxHighlightedEl.querySelector('rect, polygon')
        if (rect) rect.style.removeProperty('filter')
        const label = _ctxHighlightedEl.querySelector('.nodeLabel, .cluster-label, text')
        if (label) {
          label.style.removeProperty('font-weight')
          label.style.removeProperty('font-size')
          label.style.removeProperty('fill')
        }
        _ctxHighlightedEl = null
      }
    }
    const highlightRightClicked = (target) => {
      clearRightClickHighlight()
      if (!target) return false
      // 从 target 向上找最近的 g.cluster (容器) 或 g.node (节点)
      let el = target
      while (el && el !== document.body) {
        if (el.tagName === 'g') {
          const cls = (el.getAttribute('class') || '').trim().split(/\s+/)
          if (cls.includes('cluster') || cls.includes('subgraph') || cls.includes('node')) {
            // [CTX-HL v2 2026-08-14] 与 annotationOverlay.highlightElement 完全一致,
            //   保证"如同选中高亮": 容器 label 16px / 节点 label 18px.
            const isContainer = cls.includes('cluster') || cls.includes('subgraph')
            el.classList.add('annotation-highlighted')
            const rect = el.querySelector('rect, polygon')
            if (rect) rect.style.filter = 'drop-shadow(0 0 12px rgba(255, 80, 80, 0.9))'
            const label = el.querySelector(isContainer ? '.cluster-label, text' : '.nodeLabel, text')
            if (label) {
              label.style.fontWeight = 'bold'
              label.style.fontSize = isContainer ? '16px' : '18px'
              label.style.fill = '#ff4444'
            }
            _ctxHighlightedEl = el
            return true
          }
        }
        el = el.parentElement
      }
      return false
    }

    function handleContextMenu(event) {
      debug.debugLog('[CTX] right-click on', event.target.tagName, event.target.id, event.target.className)
      const group = identifyGroupFromSvg(event.target)
      debug.debugLog('[CTX] identifyGroupFromSvg result:', group ? group.title || group.elementCode || group.id : 'null')
      if (!group) {
        // [CTX-HL 2026-08-14] 空白区域右键 → 清除右击高亮
        clearRightClickHighlight()
        // [CTX-GLOBAL 2026-08-10] 空白区域右键: 展示全局"展开层级"菜单 (替代 GlobalToolbar 展开层级下拉).
        //   用户需求: 在图表空白处右键即可切换 领域/子领域/服务模块/业务对象 全局展开层级.
        //   与 services/expandLevel.js EXPAND_LEVELS 的 key 一一对应.
        // [UX 2026-08-14] 去掉大标题"整体展开层级" (与 4 个展开项语义重复),
        //   改为小分组标题 "展开层级" (header), 与颜色子菜单内部分组风格一致.
        // [CTX-COLOR 2026-08-11] 增加"颜色设置"子菜单入口 (受 feature flag ctxMenuColor 控制,
        //   可 ?ff_ctxMenuColor=0 快速回退). 点击后切换到颜色子菜单, 见 enterColorSubmenu.
        ctxMenu.isGlobal = true
        ctxMenu.groupTitle = ''
        ctxMenu.elementCode = ''
        closeSubmenu()
        // [REFACTOR 2026-08-14] 全局展开项抽到纯函数 contextMenuItems.js (可单元测试)
        const globalItems = buildGlobalExpandItems()
        if (isFeatureEnabled('ctxMenuColor')) {
          globalItems.push({ divider: true })
          // [UX 2026-08-11] 颜色设置改为子菜单项 (children), 悬停即展开, 无需点击进入+返回.
          globalItems.push({ key: 'color:open', label: '颜色设置', children: buildColorSubmenuItems() })
        }
        ctxMenu.items = globalItems
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
      closeSubmenu()
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
      // [CTX-HL 2026-08-14] 右击分组成功 → 临时高亮被操作对象 (复用选中高亮样式)
      highlightRightClicked(event.target)
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
        // [UX 2026-08-14] 双击已展开容器不再折叠: 容器折叠仅能通过右键菜单.
        //   用户需求: "双击容器不要折叠 (容器只能通过右击来折叠)".
        //   双击仅作为"展开"手势: 已折叠 → 展开下一层; 已展开 → 不执行任何操作.
        //   (原 2026-08-12 的双击 toggle 折叠行为已移除.)
        debug.debugLog('[DBL] handleDblClick: already expanded, dblclick does NOT collapse (collapse only via right-click)')
        return
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
          // [VIS-RESET 2026-08-14] 移除图例隐藏重置: 双击/右键展开是局部操作,
          //   应保留用户主动隐藏(visible=false), 仅"用户显式切换全局展开层级"才重置
          //   (见 services/expandLevel.js expandGroupsToLevel 的 resetVisible 选项).
          //   2026-08-12 旧逻辑在此重置会导致"隐藏财务云 → 双击服务模块后财务云重显".
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
    //   替代 GlobalToolbar 的展开层级下拉: 逻辑与 ArchDataManagement.onExpandLevelChange 一致,
    //   写 store.setExpandLevel(key) (expandLevel + expandLevelUserSet=true) + 就地应用
    //   expandGroupsToLevel 到当前渲染分组, 并 updateLayoutControlConfig 触发重渲染.
    //   key ∈ EXPAND_LEVELS.key: domain / subDomain / serviceModule / businessObject.
    function executeGlobalExpand(key) {
      debug.debugLog('[CTX-GLOBAL] executeGlobalExpand: key=' + key)
      configStore.setExpandLevel(key)
      const cfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
      if (cfg && Array.isArray(cfg.groups)) {
        const newConfig = JSON.parse(JSON.stringify(cfg))
        // [VIS-RESET 2026-08-14] 显式切换全局展开层级 → 重置用户图例隐藏(2026-08-12 旧规则).
        expandGroupsToLevel(newConfig.groups, key, { resetVisible: true })
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
      // [REL-HL OBS 2026-08-13] 打 data-rel-dim 标记: 让 E2E 可查询"被淡化范围",
      //   无需扫 inline opacity (脆弱, 与其他 opacity 用法混淆).
      el.setAttribute('data-rel-dim', '1')
      el.style.setProperty('opacity', REL_HL_DIM_OPACITY)
    }
    const restoreDim = (el) => {
      if (!el || !relHlDimmed.has(el)) return
      relHlDimmed.delete(el)
      el.removeAttribute('data-rel-dim')
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
      // [REL-HL OBS 2026-08-13] 同步权威状态快照
      relHlState = { active: false, code: null, connectedNodeCount: 0, hlEdgeCount: 0, dimmedCount: 0 }
    }

    // [REL-HL 2026-08-10] 记录最近一次"关系高亮"应用时间, 供 closeContextMenu 判断
    //   是否属于"点击菜单项触发高亮"的同一事件 (避免误清除刚应用的高亮).
    let lastRelHlAt = 0

    // [REL-HL OBS 2026-08-13] 关系高亮权威状态快照, 供 window.__archPage.relationHighlight()
    //   一条 evaluate 读取 (替代 E2E 扫描 DOM 的脆弱断言).
    let relHlState = { active: false, code: null, connectedNodeCount: 0, hlEdgeCount: 0, dimmedCount: 0 }

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
      // [REL-HL OBS 2026-08-13] 同步权威状态快照 (供 window.__archPage.relationHighlight())
      relHlState = { active: true, code: codeStr, connectedNodeCount: connected.size, hlEdgeCount: hlEdges.size, dimmedCount: relHlDimmed.size }
    }

    // [EDGE-HL 2026-08-16] 应用内边路径统一选择器 (兼容 mermaid 11 各版本边结构)
    const getAppEdgePaths = (svg) => Array.from(svg.querySelectorAll('path.flowchart-link, path.edge-thickness-normal, g.edges > g.edgePaths > path, g.edgePaths > path, .edgePath path'))

    // [REL-HL 2026-08-16] 单条连线聚焦: 高亮该连线 + 源/目标节点.
    //   dimOthers=true (右击菜单项"高亮关系") 时其余元素整体淡化; false (左击选中) 时不高亮不淡化.
    //   与 highlightRelations 共享同一套样式管理 (saveRelHlOrigStyle / dimElement).
    function highlightEdgeFocus(svg, edgeIdx, dimOthers = true) {
      clearRelationsHighlight()
      svgProcessor.clearSelectionHighlight?.()
      svgProcessor.clearAnnotationHighlight?.(svg)
      const edgePaths = getAppEdgePaths(svg)
      const edgeLabels = svg.querySelectorAll('g.edgeLabel')
      const pathEl = edgePaths[edgeIdx]
      if (!pathEl) return
      const codeToEl = new Map()
      svg.querySelectorAll('g.node').forEach((el) => {
        const c = el.getAttribute('data-container-code') || el.getAttribute('data-code')
        if (c && !codeToEl.has(c)) codeToEl.set(c, el)
      })
      svg.querySelectorAll('g.cluster[data-container-code]').forEach((el) => {
        const c = el.getAttribute('data-container-code')
        if (c && !codeToEl.has(c)) codeToEl.set(c, el)
      })
      const connected = new Set()
      const labelEl = edgeLabels[edgeIdx]
      const parts = labelEl ? (labelEl.textContent || '').split('-').map(p => p.trim()) : []
      // 复用 highlightRelations 的层级映射与"解析到最近可见祖先"逻辑
      const { parentMap } = buildRelHlMaps()
      const resolveVisible = (code) => resolveVisibleAncestor(code, codeToEl, parentMap)
      if (parts.length >= 2) {
        const a = resolveVisible(parts[0])
        const b = resolveVisible(parts[parts.length - 1])
        if (a) connected.add(a)
        if (b) connected.add(b)
      }
      // 高亮连线
      pathEl.setAttribute('data-rel-hl', '1')
      saveRelHlOrigStyle(pathEl)
      pathEl.style.strokeWidth = '3px'
      pathEl.style.filter = 'drop-shadow(0 0 4px rgba(255, 107, 107, 0.9))'
      // 高亮源/目标节点
      connected.forEach((c) => {
        const el = codeToEl.get(c)
        if (!el) return
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
      })
      // 淡化其余 (仅 dimOthers=true; 左击选中不高亮不淡化): 其余连线 + 其余节点 + 其余连线标题
      if (dimOthers) {
        const hlEdges = new Set([pathEl])
        edgePaths.forEach(p => { if (!hlEdges.has(p)) dimElement(p) })
        edgeLabels.forEach((l, idx) => { const p = edgePaths[idx]; if (!p || !hlEdges.has(p)) dimElement(l) })
        codeToEl.forEach((el, c) => { if (!connected.has(c)) dimElement(el) })
      }
      lastRelHlAt = Date.now()
      relHlState = { active: true, code: parts.slice(0, 2).join('-'), connectedNodeCount: connected.size, hlEdgeCount: 1, dimmedCount: relHlDimmed.size }
    }

    // [CTX-COLOR 2026-08-11] 构建"颜色设置"子菜单项 (含当前值勾选标记 checked).
    //   三种颜色控制: 颜色分组维度 / 配色方案 / 区分对象范围. 所有项通过
    //   executeContextMenuAction 的 setColorGroupBy:/setColorScheme:/setScopeHighlight: 分发,
    //   调用 configStore setter 驱动增量变色 (updateColorsOnly, 不重排布局).
    function buildColorSubmenuItems() {
      const cb = configStore.colorGroupBy || 'domain'
      const cs = configStore.colorScheme || 'default'
      const hl = !!configStore.centerScopeHighlight
      const schemeKeys = Object.keys(colors.COLOR_SCHEMES || {})
      // [FIX 2026-08-11] 配色方案显示中文标签 (原直接用英文 key).
      const schemeLabels = {
        default: '默认', vibrant: '鲜艳', pastel: '柔和', warm: '温暖',
        cool: '冷色', business: '商务', nature: '自然'
      }
      // [UX 2026-08-11] 作为"颜色设置"子菜单项的子级 (children), 不再含"返回"项.
      return [
        { divider: true },
        { header: '颜色分组维度' },
        { key: 'setColorGroupBy:domain', label: '按领域', checked: cb === 'domain' },
        { key: 'setColorGroupBy:subDomain', label: '按子领域', checked: cb === 'subDomain' },
        { key: 'setColorGroupBy:serviceModule', label: '按服务模块', checked: cb === 'serviceModule' },
        { divider: true },
        { header: '配色方案' },
        ...schemeKeys.map(s => ({ key: 'setColorScheme:' + s, label: schemeLabels[s] || s, checked: cs === s })),
        { divider: true },
        { header: '区分对象范围' },
        { key: 'setScopeHighlight:1', label: '区分', checked: hl === true },
        { key: 'setScopeHighlight:0', label: '不区分', checked: hl === false }
      ]
    }

    // [UX 2026-08-11] 悬停子菜单支持函数 (替代旧的 enterColorSubmenu/backFromSubmenu 点击+返回模式).
    function hasSubmenu(item) {
      return !!item && Array.isArray(item.children) && item.children.length > 0
    }

    function clearSubmenuTimer() {
      if (submenuCloseTimer) {
        clearTimeout(submenuCloseTimer)
        submenuCloseTimer = null
      }
    }

    function closeSubmenu() {
      clearSubmenuTimer()
      submenuState.visible = false
      submenuState.items = []
      submenuState.openKey = ''
      submenuState.anchorRect = null
    }

    function onItemMouseEnter(e, item) {
      if (!hasSubmenu(item)) return
      clearSubmenuTimer()
      if (submenuState.visible && submenuState.openKey === item.key && submenuState.items === item.children) {
        return // 已展开同一子菜单, 不重复定位
      }
      const rect = e.currentTarget.getBoundingClientRect()
      submenuState.items = item.children
      submenuState.openKey = item.key
      submenuState.anchorRect = rect
      submenuState.visible = true
      // 先渲染再钳制位置, 避免子菜单滑出视口
      nextTick(() => positionSubmenu())
    }

    // [UX 2026-08-11] 定位子菜单: 默认对齐父项右侧；右侧溢出则向左翻转; 底部溢出则上移.
    function positionSubmenu() {
      const el = submenuRef.value
      const anchor = submenuState.anchorRect
      if (!el || !anchor) return
      const vw = window.innerWidth
      const vh = window.innerHeight
      let left = anchor.right - 2
      // 先按初始位置测量实际宽高
      el.style.visibility = 'hidden'
      el.style.left = left + 'px'
      el.style.top = anchor.top + 'px'
      const w = el.offsetWidth
      const h = el.offsetHeight
      // 水平: 右侧溢出 → 翻转到父项左侧
      if (left + w > vw - 4) {
        left = Math.max(4, anchor.left - w - 2)
      }
      // 垂直: 底部溢出 → 上移 (保持尽量贴合父项)
      let top = anchor.top
      if (top + h > vh - 4) {
        top = Math.max(4, vh - h - 4)
      }
      el.style.left = left + 'px'
      el.style.top = top + 'px'
      el.style.visibility = 'visible'
    }

    function onItemMouseLeave(e, item) {
      if (!hasSubmenu(item)) return
      // 若鼠标正移入子菜单面板, 不关闭 (面板与父项有间隙, 用延迟容错)
      if (submenuState.visible && submenuState.openKey === item.key) {
        const related = e.relatedTarget
        if (related && submenuRef.value && submenuRef.value.contains(related)) {
          clearSubmenuTimer()
          return
        }
      }
      clearSubmenuTimer()
      submenuCloseTimer = setTimeout(() => closeSubmenu(), 150)
    }

    function onSubmenuEnter() {
      clearSubmenuTimer()
    }

    function onSubmenuLeave() {
      clearSubmenuTimer()
      submenuCloseTimer = setTimeout(() => closeSubmenu(), 120)
    }

    function onMenuMouseLeave() {
      // 鼠标离开整个菜单(非移入子菜单)时关闭子菜单
      clearSubmenuTimer()
      closeSubmenu()
    }

    function executeContextMenuAction(key) {
      // [UX 2026-08-11] 子菜单父项可由悬停展开; 若被点击, 仅保持现状不执行动作也不关闭菜单.
      if (key === 'color:open') {
        return
      }
      ctxMenu.visible = false
      closeSubmenu()
      // [CTX-HL 2026-08-14] 执行菜单项 → 清除右击临时高亮 (操作后图表可能重渲染, 残留高亮无意义)
      clearRightClickHighlight()
      // [CTX-GLOBAL 2026-08-10] 空白区域右键的全局展开层级项 (expandGlobal:<key>)
      //   直接走全局展开, 不依赖具体分组.
      if (typeof key === 'string' && key.startsWith('expandGlobal:')) {
        executeGlobalExpand(key.slice('expandGlobal:'.length))
        return
      }
      // [CTX-COLOR 2026-08-11] 颜色设置子菜单项: 调用 store setter 驱动增量变色
      //   链路: configStore.updateColorGroupBy/updateColorScheme → useDiagramData 合并 watch
      //     → generateDiagram → MermaidComponent 检测颜色变化 → updateColorsOnly 增量 (不重排).
      //     updateCenterScopeHighlight → 浅更新 diagramData → 增量变色.
      if (typeof key === 'string' && key.startsWith('setColorGroupBy:')) {
        configStore.updateColorGroupBy(key.slice('setColorGroupBy:'.length))
        return
      }
      if (typeof key === 'string' && key.startsWith('setColorScheme:')) {
        configStore.updateColorScheme(key.slice('setColorScheme:'.length))
        return
      }
      if (typeof key === 'string' && key.startsWith('setScopeHighlight:')) {
        const val = key.slice('setScopeHighlight:'.length) === '1'
        configStore.updateCenterScopeHighlight(val)
        return
      }
      // [REL-HL 2026-08-10] "关系高亮": 高亮该节点相关的所有连线及相连节点.
      //   仅依赖 ctxMenu.elementCode (右键节点的编码), 无需在分组树中定位目标.
      if (key === 'highlightRelations') {
        highlightRelations(ctxMenu.elementCode)
        return
      }
      // [EDGE-HL 2026-08-16] 右击连线菜单项: 高亮该连线 + 源/目标节点 + 其余淡化.
      if (key === 'edgeFocus') {
        const svg = mermaidContainer.value?.querySelector('svg')
        if (svg && ctxMenu.edgeIdx != null) highlightEdgeFocus(svg, ctxMenu.edgeIdx, true)
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
        // [VIS-RESET 2026-08-14] 移除图例隐藏重置: 右键折叠是局部操作, 应保留用户主动隐藏
        //   (visible=false). 2026-08-12 旧逻辑在此重置会导致"隐藏外部领域云 → 折叠/展开后重显".
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
        closeSubmenu()
        // [CTX-HL 2026-08-14] 菜单因点击其他位置而关闭 → 同步清除右击临时高亮
        //   (生命周期: 菜单打开即高亮, 菜单关闭/执行菜单项/再次右击即清除; 此处幂等, 兼容
        //    执行菜单项后 closeSubmenu 已清、再冒泡到本函数的场景)
        clearRightClickHighlight()
      }
      const hasClosest = e.target && typeof e.target.closest === 'function'
      const content = hasClosest ? e.target.closest('.mermaid-content') : null
      // [FIX 2026-08-16] 拖拽后的 click 不取消高亮: 仅"纯粹点击"(无拖拽位移) 才清除关系高亮.
      //   拖拽由 useInteraction 的 window.__mermaidDrag.wasDrag 标记 (位移>8px).
      const wasDrag = !!(typeof window !== 'undefined' && window.__mermaidDrag && window.__mermaidDrag.wasDrag)
      // [FIX 2026-08-16] 容器点击也取消高亮: 排除列表去掉 g.cluster/.subgraph (分组容器)
      //   与 g.node (节点点击本身会重新聚焦选中), 让"点击图表任意位置"都能清除关系/连线高亮,
      //   不必非得点空白位置. 仅排除"会重新聚焦"的连线/右键菜单.
      if (content && !wasDrag && Date.now() - lastRelHlAt > 400
          && !e.target.closest('g.edgeLabel, g.edgePath, g.edges, .mermaid-ctx-menu')) {
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
        // [SIMPLE 2026-08-15] diff 变量提升到块外, 供下方"纯关联点变化增量刷新"判断复用
        let nodesChanged = false
        let linksChanged = false
        let textColorChanged = false
        let colorConfigChanged = false
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
          nodesChanged = JSON.stringify(stripColorDerived(newVal.nodes)) !== JSON.stringify(stripColorDerived(oldVal.nodes))
          linksChanged = JSON.stringify(newVal.links) !== JSON.stringify(oldVal.links)
          textColorChanged = newVal?.textColor !== oldVal?.textColor
          // [FIX 2026-08-10] 颜色字段 (colorGroupBy/colorScheme/centerScopeHighlight/customColors)
          //   统一用 colorTracker.changed 基于 last* 快照对比, 而非失效的 oldVal.
          //   根因: centerScopeHighlight 走"原地修改"(引用不变), deep watch 时 oldVal===newVal,
          //   基于 oldVal 的 diff 恒 false → 颜色变化识别失效 → 恒全量 renderMermaid().
          //   tracker 用 last* 快照对比, 任何颜色字段(含未来改原地修改的)都能正确识别
          //   → 走 updateColorsOnly 增量变色. textColor 不走原地修改且 tracker 不含此字段,
          //   故保留 oldVal 判断.
          const colorChanged = colorTracker.changed(newVal)
          colorConfigChanged = colorChanged.colorGroupBy || colorChanged.customColors
            || colorChanged.colorScheme || colorChanged.centerScopeHighlight || colorChanged.centerScopeColor

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

        // [SIMPLE 2026-08-15] 关联点设置变化:
        //   纯关联点变化 (节点/连线/颜色均未变) → 增量更新拖尾线, 不触发 mermaid.run 全量重绘.
        //   否则 → 清空 lastRenderedCode 强制重绘 (deep watch 原地修改 oldVal===newVal, 用 lastTailSetting 追踪).
        const currentTail = newVal?.hideLinkLabelTails ?? null
        if (currentTail !== lastTailSetting) {
          lastTailSetting = currentTail
          if (!nodesChanged && !linksChanged && !colorConfigChanged && !textColorChanged) {
            const svg = mermaidContainer.value?.querySelector('svg')
            if (svg && typeof svgProcessor.refreshTrailingDottedLines === 'function') {
              svgProcessor.refreshTrailingDottedLines(svg, props.diagramType, shouldHideTails.value)
              return
            }
          }
          lastRenderedCode = null
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
        // [ELK-GROUP 2026-08-12] 例外: 系统自动分组(无关系/有关系, _elkGroup=inner/boundary)
        //   的 visible 决定是否渲染"有标题盒"(enabled+visible → subgraph[title]), 属结构变化,
        //   必须参与签名触发全量重排. 否则 visible 变化走 updateVisibilityOnly 只 toggle display,
        //   无法新增/移除标题盒 → 面板"显示/隐藏"切换无效果 (用户反馈的 bug).
        const isElkSystemAuto = (g) => !!g && (g._elkGroup === 'inner' || g._elkGroup === 'boundary')
        const sigGroup = (g) => ({
          id: g.elementCode || g.id,
          title: g.title,
          en: g.enabled,
          v: isElkSystemAuto(g) ? g.visible : undefined,
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
        // [A1 2026-08-10] 方案 A: 折叠识别签名 — 剔除 collapsed (co) 字段.
        //   若"无折叠签名"相同而"含折叠签名"不同 → 本次结构变化仅来自折叠/展开,
        //   置位 foldRenderPending, 使 renderMermaid 跳过整屏 loading + 走双缓冲平滑过渡.
        const sigNoFold = (g) => ({
          id: g.elementCode || g.id,
          title: g.title,
          en: g.enabled,
          v: isElkSystemAuto(g) ? g.visible : undefined,
          cont: (g.containers || []).map(c => typeof c === 'string' ? c : (c.id || c.elementCode)),
          dn: (g.directNodes || []).map(n => typeof n === 'object' ? (n.id || n.code || n.name) : n),
          ch: (g.children || []).map(sigNoFold)
        })
        const sigNoFoldStr = (cfg) => JSON.stringify((cfg?.groups || []).map(sigNoFold))
        const newSig = sig(newVal)
        const oldSig = sig(oldVal)
        console.log('[WATCH] layoutControlConfig sig changed=' + (newSig !== oldSig) + ', newSig=' + newSig.slice(0, 200) + ', oldSig=' + oldSig.slice(0, 200))
        if (newSig !== oldSig) {
          // [A1 2026-08-10] 仅折叠/展开变化 → 双缓冲平滑过渡 (不闪整屏 loading)
          if (sigNoFoldStr(newVal) === sigNoFoldStr(oldVal)) {
            foldRenderPending = true
          }
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
          // [VIS 2026-08-14] 取消隐藏 (visible: false→true) 时, 若该分组的聚合节点/容器未在 SVG 中
          //   (前一次全量重渲染在隐藏态跳过了它 — applyUpliftNodeColors/buildUpliftAncestorMap 已跳过
          //   visible=false 分组), 增量 updateVisibilityOnly 只能 toggle display 已存在元素, 无法恢复
          //   缺失的聚合节点 → 需全量重渲染重新生成. 用户反馈: 隐藏采购云 → 双击供应链云(全量重渲染,
          //   采购云聚合节点未生成) → 取消隐藏采购云 → 采购云不出现.
          const oldHiddenCodes = new Set()
          const collectOldHidden = (list) => {
            ;(list || []).forEach(g => {
              if (!g || typeof g !== 'object') return
              if (g.visible === false && !isElkSystemAuto(g)) oldHiddenCodes.add(g.elementCode || g.id)
              collectOldHidden(g.children)
            })
          }
          collectOldHidden(oldVal?.groups)
          let unhideMissing = false
          if (oldHiddenCodes.size > 0) {
            const svg = mermaidContainer.value?.querySelector('svg')
            const checkUnhide = (list) => {
              ;(list || []).forEach(g => {
                if (!g || typeof g !== 'object' || unhideMissing) return
                const code = g.elementCode || g.id
                if (g.visible !== false && code && oldHiddenCodes.has(code)) {
                  const safeId = String(g.id).replace(/[^\w\u4e00-\u9fff]/g, '_')
                  const collapseId = `COLLAPSE_${safeId}`
                  const hasCollapse = svg && !!svg.querySelector(`g.node[id^="flowchart-${collapseId}"], g.node[id*="${collapseId}"]`)
                  const hasContainer = svg && !!svg.querySelector(`[data-container-code="${code}"]`)
                  if (!hasCollapse && !hasContainer) { unhideMissing = true; return }
                }
                checkUnhide(g.children)
              })
            }
            checkUnhide(newVal?.groups)
          }
          if (unhideMissing) {
            renderMermaid()
          } else {
            updateVisibilityOnly(newVal.groups)
          }
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

    // [VIS-RESET 2026-08-14 简化] 切换全局展开层级 = "重渲染操作": 渲染层已强制所有分组
    //   visible=true, 即使展开结果与当前相同 (code-diff 跳过 renderMermaid / watch 无变化),
    //   也须清除 SVG 上 updateVisibilityOnly 残留的 display:none, 恢复被隐藏分组的显示.
    //   覆盖入口: 面板展开层级下拉 / 空白右键全局展开 (executeGlobalExpand) / debug.setExpandLevel.
    watch(
      () => configStore.expandLevel,
      () => {
        if (!props.diagramData || !mermaidContainer.value) return
        clearSvgHidden()
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
        svgProcessor.processSvg(svgEl, props, relationDescriptions, mermaidContainer, nodeColorMappings, interaction, handleToggleGroupVisible, legendItemColorChangeHandler)
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
        // [DBG 2026-08-14] 读取 effectiveLayoutControlConfig (渲染树来源) 中分组状态,
        //   用于排查"隐藏外部领域后双击被重置"问题: 对比渲染树与 store 的 visible 差异.
        getEffectiveGroup: (code) => {
          const cfg = effectiveLayoutControlConfig.value || configStore.layoutControlConfig
          const readFin = (list) => {
            if (!Array.isArray(list)) return null
            let r = null
            const walk = (l) => { (l||[]).forEach(g => { if (!g || typeof g !== 'object') return; if ((g.elementCode === code || g.id === code) && !r) r = { visible: g.visible, collapsed: g.collapsed, groupType: g.groupType }; walk(g.children); walk(g.containers); }) }
            walk(list); return r
          }
          // 向上找父组件(EmbeddedChartView)的 setupState.layoutControlConfig 与 props 对比
          let parentLcc = null
          let parentName = null
          let inst = mermaidContainer.value && mermaidContainer.value.__vueParentComponent
          let p = inst ? inst.parent : null
          let guard = 0
          while (p && guard++ < 10) {
            const ss = p.setupState
            const nm = (p.type && (p.type.__name || p.type.name)) || null
            if (nm) parentName = parentName ? parentName + '>' + nm : nm
            if (ss && ss.layoutControlConfig !== undefined) { parentLcc = ss.layoutControlConfig; break }
            p = p.parent
          }
          const g = findGroupInTree(cfg.groups, x => x.elementCode === code || x.id === code)
          const dl = window.__archPage && window.__archPage.debugLayout
          return {
            effective: g ? { visible: g.visible, collapsed: g.collapsed, groupType: g.groupType } : null,
            hasPropLayoutCfg: !!props.layoutControlConfig,
            propLayoutFin: props.layoutControlConfig ? readFin(props.layoutControlConfig.groups) : null,
            hasDiagramDataCfg: !!(props.diagramData && props.diagramData.layoutControlConfig),
            diagramDataFin: (props.diagramData && props.diagramData.layoutControlConfig) ? readFin(props.diagramData.layoutControlConfig.groups) : null,
            parentLccFin: parentLcc ? readFin(parentLcc.groups) : null,
            parentLccFound: !!parentLcc,
            parentName,
            debugAfterStatesFin: dl && dl.afterStates ? readFin(dl.afterStates) : null,
            debugHas: !!dl,
            debugPanelGroupsFin: dl && dl.panelGroups ? readFin(dl.panelGroups) : null,
            storeFin: configStore.layoutControlConfig ? readFin(configStore.layoutControlConfig.groups) : null
          }
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
          // [FIX 2026-08-14] 与右键"展开到X"语义一致: 标记用户已手动调整折叠/展开,
          //   否则渲染层 layoutControlConfig computed 仍按默认展开层级覆盖 probe 的展开,
          //   导致探针/脚本静默失败 (图表根本没展开到目标层级). 详见 chart_debug_cookbook.
          configStore.markGroupManualSet()
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
          // [VIS-RESET 2026-08-14] 调试入口等价于用户显式切换全局展开层级 → 重置隐藏.
          expandGroupsToLevel(newConfig.groups, key, { resetVisible: true })
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
        // [EXP-VERIFY 2026-08-16] 图表连线诊断: 一条 evaluate 判断当前图表是否有连线/标签.
        //   用途: 验证连线类功能(高亮/导出连线/标签热点)前先确认当前范围有连线 —
        //   SCP 子领域等范围 links=0 (无连线), 需换含连线的范围(如 PLAM 展开到 BO)才能验证连线功能.
        chartLinks: () => {
          const svg = mermaidContainer.value?.querySelector('svg')
          const d = props.diagramData || {}
          return {
            links: Array.isArray(d.links) ? d.links.length : 0,
            nodes: Array.isArray(d.nodes) ? d.nodes.length : 0,
            edgeLabels: svg ? svg.querySelectorAll('g.edgeLabel').length : 0,
            edgePaths: svg ? svg.querySelectorAll('g.edges.edgePaths > path').length : 0,
            scope: (d && d.scopeCode) || (props.scopeCode) || null
          }
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
        // [OBS 2026-08-12] 分歧检测扩展: 不再只比 collapsed, 同时对比 enabled/visible.
        //   背景: ELK 系统自动分组(无关系/有关系) bug 里, 面板切换 enabled/visible
        //   是否真正驱动渲染树 (injectElkSubGroups) 无法从 diag() 看出来——旧实现只报 collapsed
        //   分歧, 即便面板 enabled 变了但渲染树未跟随也无任何提示.
        //   现每条分歧带 field 标记 (collapsed/enabled/visible), 仅当某字段在 ≥2 个数据源
        //   中值不一致时上报. verify() 的"三源折叠一致性"仍只统计 field==='collapsed'.
        const DIVERGENCE_FIELDS = ['collapsed', 'enabled', 'visible']
        const divergences = Object.entries(byKey)
          .flatMap(([k, v]) => {
            const title = (v.store || v.chart || v.render)?.title
            const out = []
            for (const field of DIVERGENCE_FIELDS) {
              const flags = [v.store?.[field], v.chart?.[field], v.render?.[field]].filter(x => x !== undefined)
              if (flags.length >= 2 && new Set(flags).size > 1) {
                out.push({
                  key: k,
                  field,
                  title,
                  store: v.store?.[field],
                  chart: v.chart?.[field],
                  render: v.render?.[field]
                })
              }
            }
            return out
          })
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
          // 折叠一致性只统计 collapsed 分歧 (不掺入 enabled/visible, 保持原语义)
          { name: 'three-source-collapsed-consistency', pass: d.divergences.filter(x => x.field === 'collapsed').length === 0, detail: d.divergences.filter(x => x.field === 'collapsed') },
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
      // 生成"当前完整状态快照"的可复现链接 (复制到剪贴板前先返回)
      // [OBS 2026-08-15] 扩展编码: 除 fold/scopeHighlight 外, 新增 colorGroupBy/colorScheme/expandLevel/customColors.
      //   例: /system/archdata?preset=scp&fold={"MM":false}&scopeHighlight=1&cfg=eyJjb2xvckdyb3VwQnk...&expandLevel=subDomain
      //   这样一条链接即可精确复现折叠态+配色+颜色分组+展开层级+区分开关的完整状态.
      window.__archPage.exportUrl = () => {
        const d = (window.__archPage.diag && window.__archPage.diag()) || null
        const fold = {}
        ;(d?.store || []).forEach(g => { if (g.key) fold[g.key] = !!g.collapsed })
        const url = new URL(window.location.href)
        url.searchParams.set('fold', JSON.stringify(fold))
        url.searchParams.set('scopeHighlight', d?.config?.centerScopeHighlight ? '1' : '0')
        // 编码颜色配置 (简化: 仅 encode 非默认值, 减少 URL 长度)
        const cs = configStore
        const cfgParts = {}
        if (cs.colorGroupBy && cs.colorGroupBy !== 'domain') cfgParts.cg = cs.colorGroupBy
        if (cs.colorScheme && cs.colorScheme !== 'default') cfgParts.cs = cs.colorScheme
        if (cs.expandLevel && cs.expandLevel !== 'businessObject') cfgParts.el = cs.expandLevel
        // customColors 非空时编码 (仅保留有值的键, 减少长度)
        const cc = cs.customColors || {}
        const ccKeys = Object.keys(cc)
        if (ccKeys.length > 0) {
          cfgParts.cc = JSON.stringify(cc)
        }
        if (Object.keys(cfgParts).length > 0) {
          url.searchParams.set('cfg', btoa(JSON.stringify(cfgParts)))
        }
        return url.toString()
      }
      // [EXP-VERIFY 2026-08-16] 导出 HTML 钩子: 直接返回完整 HTML 字符串, 免去下载/加载链路.
      //   用法: const html = await window.__archPage.exportHtmlFull()
      //   探针取到字符串后, 可直接落盘 + 浏览器加载, 或提取内联脚本做语法检查.
      window.__archPage.exportHtmlFull = () => exportAsHtmlFull({ returnHtml: true })
      // [REL-HL OBS 2026-08-13] 关系高亮权威状态快照: 一条 evaluate 读取, 替代扫描 DOM.
      //   返回 {active, code, connectedNodeCount, hlEdgeCount, dimmedCount}.
      window.__archPage.relationHighlight = () => ({ ...relHlState })

      // [OBS 2026-08-13] 整体展开/折叠不变式断言助手: 返回"树各层分组计数 + 实际 SVG 容器/节点数",
      //   供 E2E 一键断言"展开到某层后容器数是否符合预期", 替代脆弱的 DOM 扫描与多探针比对.
      //   containerCount 期望 = 应渲染为容器的分组数 (比目标层更粗的分组); businessObject 全展开时 = 全部非 BO 分组数.
      window.__archPage.assertExpandInvariant = (level) => {
        const LEVEL_IDX = { domain: 0, subDomain: 1, serviceModule: 2, businessObject: 3 }
        const tree = { domain: 0, subDomain: 0, serviceModule: 0, businessObject: 0 }
        const walk = (list) => {
          for (const g of list || []) {
            if (!g || typeof g !== 'object') continue
            const t = g.groupType
            if (t && Object.prototype.hasOwnProperty.call(tree, t)) tree[t]++
            walk(g.children)
            walk((g.containers || []).filter(c => c && typeof c === 'object'))
          }
        }
        walk(configStore.layoutControlConfig?.groups || [])
        const svg = mermaidContainer.value?.querySelector('svg')
        const actualContainer = svg ? svg.querySelectorAll('g.cluster').length : -1
        const actualNode = svg ? svg.querySelectorAll('g.node').length : -1
        const tIdx = LEVEL_IDX[level]
        const totalNonBo = tree.domain + tree.subDomain + tree.serviceModule
        const expectedContainer = (tIdx >= 3) ? totalNonBo
          : Object.entries(tree).reduce((acc, [k, v]) => acc + (LEVEL_IDX[k] < tIdx ? v : 0), 0)
        return {
          level,
          expandLevel: configStore.expandLevel || null,
          tree,
          expected: { containerCount: expectedContainer },
          actual: { containerCount: actualContainer, nodeCount: actualNode },
          containerMatch: actualContainer === expectedContainer,
          pass: actualContainer === expectedContainer,
          note: 'containerCount 期望 = 应渲染为容器的分组数 (比目标层更粗的分组); 空容器隐藏/ELK 自动分组可能造成偏差'
        }
      }

      // 能力清单 (可发现性核心): 列出所有诊断/验证/复现 API
      window.__archPage.help = () => ({
        diag: 'diag() — store/chart/渲染树 三份状态 + divergences 分歧清单',
        verify: 'verify({before, expandKeys}) — 行为级断言 {pass, checks}',
        captureNodeSignature: 'captureNodeSignature() — SVG 节点签名 (判定是否全量重建)',
        relationHighlight: 'relationHighlight() — 关系高亮状态快照 {active, code, connectedNodeCount, hlEdgeCount, dimmedCount}',
        assertExpandInvariant: 'assertExpandInvariant(level) — 展开/折叠不变式: 树各层计数 + 实际容器/节点数 + 期望比对',
        openTruthPanel: 'openTruthPanel() — 打开状态真相面板 (可视化三份状态+差异高亮)',
        exportUrl: 'exportUrl() — 生成当前折叠态+区分/不区分的可复现链接',
        help: 'help() — 本能力清单',
        debug: 'debug.* — 调试助手 (仅 ?mode=debug)',
        debugLayout: 'debugLayout — 合并分步快照 (before/afterStates/afterMembership/afterTitles/afterElk/afterScopeExpand) + panelGroups, 排查面板→渲染树合并',
        mermaid: 'mermaid.* — 渲染元数据 (lastRender/renderSkippedCount/...)',
        chartConfig: 'chartConfig — 图表配置 (可直接改字段驱动)',
        reload: 'reload() — 强制 mermaid 全量重绘',
        // [OBS 2026-08-15] 补齐此前遗漏的能力入口 (排查时易踩坑/需多次组合 API)
        getDiagramData: 'getDiagramData() — 当前 diagramData 值 (ref 解包, 直接读 nodes/links; 避免 __archPage.diagramData 是 ref 需 .value 的陷阱)',
        getColorState: 'getColorState() — 实时颜色配置快照 (colorGroupBy/colorScheme/highlight/centerScopeColor/customColors/isCenter 统计; 不依赖增量路径副作用 colorState)',
        getExpandState: 'getExpandState() — 实时展开层级/折叠统计快照 (expandLevel/userSet/groupManualSet/collapsed 分层计数)',
        whyHidden: 'whyHidden(code) — 诊断某 BO/分组为何不可见: 是否在数据/中心范围/SVG, 父分组 visible/collapsed 祖先链, 给出原因清单',
        focusElement: "focusElement(type, id) — 高亮+居中图表元素 ('container'/'node'); TruthPanel 表格行点击即调用"
      })

      // [OBS 2026-08-15] 实时可观测助手 (任意模式, 不依赖增量路径副作用):
      //   - getDiagramData(): 解包 diagramData ref, 避免 `__archPage.diagramData.nodes` 返回 undefined 的坑.
      //   - getColorState(): 实时颜色配置 + isCenter 统计; 替代只在 updateColorsOnly 写入的 colorState
      //     (全量渲染后为 null, 排查"切色后节点/图例是否正确"时无从读起).
      //   - getExpandState(): 实时展开层级 + 折叠分层计数.
      const getDiagramData = () => {
        const raw = window.__archPage?.diagramData
        return (raw && raw.value) ? raw.value : raw
      }
      const getColorState = () => {
        const d = getDiagramData() || {}
        const nodes = d.nodes || []
        const centerSet = new Set(configStore.centerScope || [])
        return {
          colorGroupBy: configStore.colorGroupBy,
          colorScheme: configStore.colorScheme,
          centerScopeHighlight: configStore.centerScopeHighlight,
          centerScopeColor: configStore.centerScopeColor,
          customColors: configStore.customColors || {},
          nodeTextColor: configStore.nodeTextColor,
          centerScopeCount: (configStore.centerScope || []).length,
          nodeCount: nodes.length,
          centerNodeCount: nodes.filter(n => centerSet.has(n.code)).length,
          // 图例"对象范围"项是否应出现 (与 buildColorLegendData hasCenterNodes 口径一致)
          legendShouldShowCenterScope: !!configStore.centerScopeHighlight && nodes.some(n => centerSet.has(n.code))
        }
      }
      const getExpandState = () => {
        const cfg = configStore.layoutControlConfig
        let collapsedCount = 0
        const byLevel = { domain: 0, subDomain: 0, serviceModule: 0, other: 0 }
        const walk = (list) => {
          for (const g of list || []) {
            if (!g || typeof g !== 'object') continue
            if (g.collapsed === true) {
              collapsedCount++
              const t = String(g.groupType || '').toLowerCase()
              if (t === 'domain') byLevel.domain++
              else if (t === 'subdomain') byLevel.subDomain++
              else if (t === 'servicemodule') byLevel.serviceModule++
              else byLevel.other++
            }
            walk(g.children)
            walk((g.containers || []).filter(c => c && typeof c === 'object'))
          }
        }
        walk(cfg?.groups || [])
        return {
          expandLevel: configStore.expandLevel,
          expandLevelUserSet: configStore.expandLevelUserSet,
          groupManualSet: configStore.groupManualSet,
          collapsedCount,
          byLevel
        }
      }
      // [OBS 2026-08-15] 一键诊断: 某 BO/分组"为什么不可见".
      //   用法: __archPage.whyHidden('PO201') / __archPage.whyHidden('SCM')
      //   返回: 是否在数据/中心范围/SVG + 分组树祖先链 (type/title/code/visible/collapsed) + 原因清单.
      //   背景: 用户反馈"某对象/领域没显示"时, 排查需组合多个 API + 猜数据流; 这里一次给结论.
      const whyHidden = (code) => {
        const codeStr = String(code == null ? '' : code)
        const d = getDiagramData() || {}
        const nodes = d.nodes || []
        const store = configStore
        const out = {
          code: codeStr,
          inDiagramNodes: false,
          inCenterScope: false,
          inSvg: false,
          groupChain: [],
          hiddenParents: [],
          foldedAncestor: null,
          reasons: []
        }
        // 1) 是否在当前图表数据 (nodes) 中
        const node = nodes.find(n => String(n.code || '') === codeStr || String(n.name || '') === codeStr)
        out.inDiagramNodes = !!node
        // 2) 是否在中心范围
        out.inCenterScope = (store.centerScope || []).some(c => String(c) === codeStr)
        // 3) 分组树祖先链 (含 visible/collapsed/enabled)
        const chain = []
        const findInGroup = (g) => {
          if (!g || typeof g !== 'object') return false
          const keys = [g.elementCode, g.id, g.title, g.name].filter(k => k != null).map(String)
          if (keys.includes(codeStr)) {
            chain.push({ type: g.groupType || g.type || 'group', title: g.title || g.name || '', code: g.elementCode || g.id, visible: g.visible, collapsed: g.collapsed, enabled: g.enabled })
            return true
          }
          // 容器内 BO 叶
          for (const c of (g.containers || [])) {
            if (!c || typeof c !== 'object') continue
            const cNodes = (c.nodes || []).map(n => String(typeof n === 'object' ? (n.code || n.id || n.name) : n))
            const cKeys = [c.elementCode, c.elementRef?.code, c.id, c.name].filter(k => k != null).map(String)
            if (cNodes.includes(codeStr) || cKeys.includes(codeStr)) {
              chain.push({ type: 'container', title: c.name || c.title || '', code: c.elementCode || c.id, visible: c.visible, collapsed: c.collapsed, enabled: c.enabled })
              chain.push({ type: g.groupType || g.type || 'group', title: g.title || g.name || '', code: g.elementCode || g.id, visible: g.visible, collapsed: g.collapsed, enabled: g.enabled })
              return true
            }
          }
          for (const ch of (g.children || [])) {
            if (findInGroup(ch)) {
              chain.push({ type: g.groupType || g.type || 'group', title: g.title || g.name || '', code: g.elementCode || g.id, visible: g.visible, collapsed: g.collapsed, enabled: g.enabled })
              return true
            }
          }
          return false
        }
        ;(store.layoutControlConfig?.groups || []).some(findInGroup)
        out.groupChain = chain
        out.hiddenParents = chain.filter(c => c.visible === false).map(c => `${c.type}:${c.title}`)
        out.foldedAncestor = chain.find(c => c.collapsed === true && c.type !== 'container') || null
        // 4) SVG 是否存在该元素
        const svg = mermaidContainer.value?.querySelector('svg')
        if (svg) {
          out.inSvg = !!svg.querySelector(`g.node[data-code="${codeStr}"]`)
          if (!out.inSvg) out.inSvg = !!svg.querySelector(`g.cluster[data-container-code="${codeStr}"], g.node[data-container-code="${codeStr}"]`)
        }
        // 5) 归纳原因
        if (!out.inDiagramNodes) {
          out.reasons.push('不在当前图表 nodes — 未选中/被对象范围·关系范围过滤 (若应出现, 查 scope/关系选择)')
        } else if (out.inCenterScope && !out.inSvg && out.hiddenParents.length === 0 && !out.foldedAncestor) {
          // [OBS 2026-08-15] 细化: 展开层级比"业务对象"更粗时, BO 被折叠进聚合节点属正常,
          //   不应误报"渲染层丢弃"; 仅当已展开到业务对象仍无元素才算异常.
          const expandLevel = configStore.expandLevel
          if (expandLevel && expandLevel !== 'businessObject') {
            out.reasons.push(`折叠进聚合节点 (当前展开层级=${expandLevel}, 展开到"业务对象"后可显示)`)
          } else {
            out.reasons.push('已展开到业务对象但 SVG 无此元素且无隐藏/折叠祖先 — 可能渲染层丢弃 (查 hiddenBoIds/ELK 逻辑)')
          }
        }
        if (out.hiddenParents.length > 0) {
          out.reasons.push(`父分组 visible=false: ${out.hiddenParents.join(' > ')} (图例/面板取消隐藏可恢复)`)
        }
        if (out.foldedAncestor) {
          out.reasons.push(`折叠进聚合节点: ${out.foldedAncestor.type}:${out.foldedAncestor.title} (展开该分组后可显示)`)
        }
        if (out.inDiagramNodes && !out.inSvg && out.reasons.length === 0) {
          out.reasons.push('在数据中但 SVG 无元素 — 未找到明确原因, 用 TruthPanel/diag() 进一步核对三份状态')
        }
        return out
      }
      window.__archPage.getDiagramData = getDiagramData
      window.__archPage.getColorState = getColorState
      window.__archPage.getExpandState = getExpandState
      window.__archPage.whyHidden = whyHidden
      // [OBS 2026-08-15] 图表定位助手: 高亮 + 居中某元素 (经 chartFocusRequest 走 focusOnTarget+centerElement).
      //   用法: __archPage.focusElement('container', 'SCM') — 容器/分组用 'container' + 标题或编码,
      //         __archPage.focusElement('node', 'PO201') — 业务对象节点用 'node' + 编码.
      //   供 TruthPanel 的 whyHidden 诊断结果点击联动 (见 TruthPanel.vue 诊断区).
      window.__archPage.focusElement = (type, id) => {
        if (!type || id == null) return false
        configStore.requestChartFocus({ type, id })
        return true
      }

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

      // 3) cfg (完整状态快照, 由 exportUrl 生成): base64(JSON {cg:colorGroupBy, cs:colorScheme, el:expandLevel, cc:customColors}).
      //    [OBS 2026-08-15] 与 fold/scopeHighlight 组合, 一条链接精确复现配色+颜色分组+展开层级+自定义色.
      const cfgRaw = params.get('cfg')
      let cfgApplied = false
      const applyCfg = () => {
        if (cfgApplied || !cfgRaw) return
        let cfg
        try {
          cfg = JSON.parse(atob(cfgRaw))
        } catch (e) {
          console.warn('[URL-state] cfg 解析失败:', cfgRaw, e)
          return
        }
        const c = window.__archPage?.chartConfig
        // 颜色分组 / 配色: 通过 chartConfig 走既有 watch 链 (→ store 同步 → generateDiagram),
        //   避免直接改 store 与 EmbeddedChartView 的 watch 双触发竞态.
        if (cfg.cg && ['domain', 'subDomain', 'serviceModule'].includes(cfg.cg)) {
          if (c) c.colorGroupBy = cfg.cg
          else configStore.updateColorGroupBy(cfg.cg)
        }
        if (cfg.cs && colors.COLOR_SCHEMES[cfg.cs]) {
          if (c) c.colorScheme = cfg.cs
          else configStore.updateColorScheme(cfg.cs)
        }
        // 展开层级: setExpandLevel 置 expandLevelUserSet=true (防自适应默认展开覆盖), 渲染层自动消费.
        if (cfg.el && ['domain', 'subDomain', 'serviceModule', 'businessObject'].includes(cfg.el)) {
          configStore.setExpandLevel(cfg.el)
        }
        // 自定义色 (仅当 URL 携带时应用)
        if (cfg.cc && typeof cfg.cc === 'object' && !Array.isArray(cfg.cc)) {
          configStore.updateCustomColors(cfg.cc)
          if (c && !c.customColors) c.customColors = cfg.cc
        }
        cfgApplied = true
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
      // fold/cfg 等待 groups 首次就绪后应用 (updateLayoutControlConfig 整体替换会再触发本 watch,
      //   foldApplied/cfgApplied 标志防止重复应用)
      watch(() => configStore.layoutControlConfig?.groups, (g) => {
        if (Array.isArray(g) && g.length) {
          applyFold(configStore.layoutControlConfig)
          applyCfg()
        }
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
            // [A5 2026-08-16] 与应用内一致: 上限 10→20 (对齐 Miro 2000%), 看清大图 BO 文字
            const maxScale = 20;
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
            // [EXP-HTML 2026-08-16] 移除强制容器上色后处理:
            //   容器填充由 mermaid 代码内的 LEVEL_STYLES 渲染 (与应用内一致的灰白灰层叠 + #333333 描边),
            //   此处不再覆盖, 保证导出与应用完全一致.
            
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
    // [EXP-VERIFY 2026-08-16] 导出 HTML 支持 returnHtml 模式: 测试钩子可直接取字符串, 免去下载/加载链路.
    //   用法: await window.__archPage.exportHtmlFull()  → 返回当前图表对应的完整导出 HTML 字符串
    const exportAsHtmlFull = async (opts = {}) => {
      if (props.diagramData) {
        if (!opts.returnHtml) showToast('正在生成彩色版，请稍候...')

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
          // [LEGEND-SECTION 2026-08-15] 节标题项: 渲染为"标签 + 分隔线", 与画布图例一致
          if (item.isSection) {
            return `<div class="legend-section">
              <span class="legend-section-label">${item.name || ''}</span>
              <span class="legend-section-line"></span>
            </div>`
          }
          const sep = (item.isCenter && idx < colorLegendDataFull.length - 1)
            ? '<div class="legend-sep"></div>'
            : ''
          return `<div class="legend-item" title="点击隐藏/显示该分组: ${item.name || ''}" data-legend-name="${item.name || ''}">
            <span class="legend-dot" style="background:${item.color || '#e0e0e0'}"></span>
            <span class="legend-name">${item.name || ''}</span>
          </div>${sep}`
        }).join('')
        const legendHtmlFull = colorLegendDataFull.length > 0
          ? `<div class="color-legend-panel" data-annotation-layer="legend">
              <div class="color-legend-title">
                <span>图例</span>
                <span class="color-legend-close" id="export-legend-close" title="隐藏图例">&times;</span>
              </div>
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
        
        // [EXP-INTERACT 2026-08-16] 嵌入导出交互所需的编码映射 (节点 data-code / 容器
        //   data-container-code 标题匹配 / 关系层级 子→父 映射), 供导出 HTML 内联脚本
        //   复刻应用内交互: 节点/容器识别、关系高亮 (相关连线+源/目标节点)、右键高亮。
        //   数据均为纯 JSON 可序列化对象 (编码/标题/层级), 不泄漏 DOM/函数引用。
        const exportNodeCodes = [...new Set((props.diagramData?.nodes || []).map(n => n.code).filter(Boolean))]
        const exportGroupTitleCode = {}
        const collectExportTitles = (list) => {
          ;(list || []).forEach((g) => {
            if (!g || typeof g !== 'object') return
            const title = g.title || g.name
            const code = g.elementCode || g.id
            if (title && code && !exportGroupTitleCode[title]) exportGroupTitleCode[title] = code
            collectExportTitles(g.children)
            collectExportTitles(g.containers)
          })
        }
        collectExportTitles(effectiveLayoutControlConfig.value?.groups || [])
        const exportChildrenMap = {}
        const exportParentMap = {}
        const exportAddChild = (p, c) => {
          if (!p || !c || p === c) return
          if (!exportChildrenMap[p]) exportChildrenMap[p] = []
          if (!exportChildrenMap[p].includes(c)) exportChildrenMap[p].push(c)
          exportParentMap[c] = p
        }
        ;(props.diagramData?.domainProducts || []).forEach(domain => {
          ;(domain.modules || []).forEach(module => {
            exportAddChild(domain.code, module.code)
            ;(module.submodules || []).forEach(sub => {
              exportAddChild(module.code, sub.code)
              ;(sub.businessObjects || []).forEach(bo => exportAddChild(sub.code, bo.code))
            })
            ;(module.businessObjects || []).forEach(bo => exportAddChild(module.code, bo.code))
          })
          ;(domain.businessObjects || []).forEach(bo => exportAddChild(domain.code, bo.code))
        })
        ;(props.diagramData?.nodes || []).forEach(n => {
          if (n.serviceModule && n.code) exportAddChild(n.serviceModule, n.code)
        })

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
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-weight: bold;
      margin-bottom: 6px;
      border-bottom: 1px solid #eee;
      padding-bottom: 4px;
    }
    /* [EXP-INTERACT 2026-08-16] 图例隐藏/唤出 (与应用内一致) + 交互高亮样式 */
    .color-legend-close {
      cursor: pointer;
      font-size: 14px;
      line-height: 1;
      color: #999;
      padding: 0 2px;
      user-select: none;
    }
    .color-legend-close:hover { color: #666; }
    .color-legend-toggle {
      position: fixed;
      top: 60px;
      left: 20px;
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid #ddd;
      border-radius: 4px;
      padding: 4px 10px;
      font-size: 12px;
      color: #666;
      cursor: pointer;
      z-index: 100;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      user-select: none;
    }
    .exp-hl-edge {
      stroke-width: 4px !important;
      filter: drop-shadow(0 0 4px rgba(255, 107, 107, 0.9)) !important;
    }
    .exp-hl-node rect, .exp-hl-node polygon {
      stroke: #FF6B6B !important;
      stroke-width: 2px !important;
      filter: drop-shadow(0 0 10px rgba(255, 107, 107, 0.85)) !important;
    }
    .exp-hl-node .nodeLabel, .exp-hl-node .cluster-label, .exp-hl-node text {
      font-weight: bold !important;
      fill: #FF6B6B !important;
    }
    .exp-dim { opacity: 0.1 !important; }
    .exp-dim-line { opacity: 0.02 !important; }
    /* [EXP-DIM 2026-08-16] 连线淡化再加强: 更透明 + 更浅 + 更细 (用户反馈"不明显") */
    path.exp-dim-line { stroke: #e6e6e6 !important; stroke-width: 1px !important; }
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
    .legend-section {
      display: flex;
      align-items: center;
      gap: 6px;
      margin: 6px 0 2px;
    }
    .legend-section-label {
      font-size: 11px;
      color: #909399;
      white-space: nowrap;
    }
    .legend-section-line {
      flex: 1;
      height: 1px;
      background: #e5e7eb;
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
    // [EXP-DRAG 2026-08-16] 拖拽标记: 拖拽平移结束浏览器会 fire click, 若不做守卫会误清高亮
    //   (与应用内 window.__mermaidDrag.wasDrag 对齐: 位移 >8px 视为拖拽, 只有纯粹点击才清高亮).
    let expWasDrag = false;
    let downX = 0;
    let downY = 0;
    // [EXP-FIT 2026-08-16] minScale 改为 let: 渲染后按图表实际尺寸动态设为 fitScale×0.2,
    //   保证元素很多时也能缩到全貌 (原固定 0.1 对大图不够).
    let minScale = 0.1;
    // [A5 2026-08-16] 与应用内一致: 上限 10→20 (对齐 Miro 2000%), 看清大图 BO 文字
    const maxScale = 20;
    let fitScale = 1;
    
    // [EXP-INTERACT 2026-08-16] 嵌入编码映射 (来自应用侧生成, 见 exportAsHtmlFull):
    //   EXPORT_NODES: 所有 BO 业务编码; EXPORT_GROUPS: 分组标题→elementCode;
    //   EXPORT_CHILDREN/EXPORT_PARENT: 编码层级 子→父 映射 (关系高亮用).
    const EXPORT_NODES = ${JSON.stringify(exportNodeCodes).replace(/<\//g, '<\\/')};
    const EXPORT_GROUPS = ${JSON.stringify(exportGroupTitleCode).replace(/<\//g, '<\\/')};
    const EXPORT_CHILDREN = ${JSON.stringify(exportChildrenMap).replace(/<\//g, '<\\/')};
    const EXPORT_PARENT = ${JSON.stringify(exportParentMap).replace(/<\//g, '<\\/')};

    // 渲染后为节点/容器打业务编码属性 (复刻应用内 addNodeCodeAttributes/addContainerCodeAttributes 的简化版)
    const exportTagElements = (svg) => {
      const nodeSet = new Set(EXPORT_NODES);
      // [EXP-HL 2026-08-16] mermaid 用 br 换行 (textContent 无换行符), 按"标签文本以编码结尾"匹配, 长编码优先.
      const nodeList = EXPORT_NODES.slice().sort((a, b) => b.length - a.length);
      svg.querySelectorAll('g.node').forEach((node) => {
        const label = node.querySelector('.nodeLabel');
        if (!label) return;
        const text = (label.textContent || '').trim();
        const nl = text.lastIndexOf('\\n');
        const tail = nl >= 0 ? text.slice(nl + 1).trim() : '';
        if (tail && nodeSet.has(tail)) { node.setAttribute('data-code', tail); return; }
        const matched = nodeList.find(c => c && text.endsWith(c));
        if (matched) { node.setAttribute('data-code', matched); return; }
        const m1 = text.match(/(?:领域|子领域|服务模块)\\s*([^\\s]+)/);
        const m2 = text.match(/[（(]([^）)]+)[）)]/);
        const code = (m1 && m1[1]) || (m2 && m2[1]) || '';
        const isCollapse = (node.id || '').indexOf('COLLAPSE_') !== -1;
        // [EXP-HL 2026-08-16] 折叠/聚合节点 (领域/子领域/服务模块): 标签编码是分组编码
        //   (非 BO 编码, 不在 EXPORT_NODES 内), 直接打 data-container-code 即可供右键关系高亮识别.
        if (isCollapse && code) {
          node.setAttribute('data-container-code', code);
          return;
        }
        if (code && nodeSet.has(code)) {
          node.setAttribute('data-code', code);
        }
      });
      svg.querySelectorAll('g.cluster, .subgraph').forEach((c) => {
        const titleEl = c.querySelector('.cluster-label, text');
        if (!titleEl) return;
        const t = (titleEl.textContent || '').trim().replace(/^[<{\\[]/, '').replace(/[>}\\]]$/, '');
        const name = t.split('\\n')[0].trim();
        const code = EXPORT_GROUPS[name] || EXPORT_GROUPS[t];
        if (code) c.setAttribute('data-container-code', code);
      });
    };

    // [EXP-FIT 2026-08-16] 按图表实际尺寸 fit 到视口 (初始即见全貌), 并动态下探 minScale
    const fitToScreen = (svg) => {
      if (!svg) return;
      try {
        const bbox = svg.getBBox();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        if (!bbox || !bbox.width || !bbox.height) return;
        fitScale = Math.min(vw / bbox.width, vh / bbox.height) * 0.92;
        if (!isFinite(fitScale) || fitScale <= 0) fitScale = 1;
        minScale = fitScale * 0.2;
        scale = fitScale;
        translateX = (vw - bbox.width * fitScale) / 2 - bbox.x * fitScale;
        translateY = (vh - bbox.height * fitScale) / 2 - bbox.y * fitScale;
        updateTransform(svg);
      } catch (err) { /* fit 失败时保持默认 */ }
    };

    // [EXP-HL 2026-08-16] 关系高亮: 解析边标签 "<源>-<目标>", 高亮相关连线 + 源/目标节点, 淡化其余
    const exportSubtreeCodes = (root) => {
      const res = new Set([root]);
      const queue = [root];
      while (queue.length) {
        const cur = queue.shift();
        const kids = EXPORT_CHILDREN[cur];
        if (!kids) continue;
        kids.forEach((k) => { if (!res.has(k)) { res.add(k); queue.push(k); } });
      }
      return res;
    };
    const exportResolveVisible = (code, codeToEl) => {
      if (!code) return null;
      if (codeToEl.has(code)) return code;
      let cur = code;
      let guard = 0;
      while (cur && guard < 12) {
        cur = EXPORT_PARENT[cur];
        guard++;
        if (cur && codeToEl.has(cur)) return cur;
      }
      return null;
    };
    let exportRelHl = { nodes: [], edges: [], dims: [], labels: [] };
    const clearExportRelationsHl = () => {
      exportRelHl.nodes.forEach((el) => el.classList.remove('exp-hl-node'));
      exportRelHl.edges.forEach((el) => el.classList.remove('exp-hl-edge'));
      // [FIX 2026-08-16] dims 里既含节点(exp-dim)也含连线 path(exp-dim-line), 必须两个类都清,
      //   否则清除高亮时连线残留淡化样式 (表现为"淡化不稳定/残留").
      // [EXP-DIM 2026-08-16] 连线 path 同时还原箭头 marker (淡化时临时指向 -dim 变体).
      exportRelHl.dims.forEach((el) => {
        el.classList.remove('exp-dim');
        el.classList.remove('exp-dim-line');
        if (el.tagName === 'path') exportRestoreEdgeMarkers(el);
      });
      exportRelHl.labels.forEach((el) => el.classList.remove('exp-dim-line'));
      exportRelHl = { nodes: [], edges: [], dims: [], labels: [] };
    };
    // [EXP-HL 2026-08-16] 真实 mermaid 边路径: path.flowchart-link (g.edgePaths 内为兜底).
    //   data-edge-hit 是透明命中带 (见 addEdgeHitAreas), 必须排除以免索引错位.
    // [EXP-DIM 2026-08-16] 选择器放宽到 g.edgePaths/.edgePath 后代, 兼容不同 mermaid 版本
    //   边 DOM 结构 (直接/嵌套), 避免个别连线漏淡化造成"时隐时现"的不稳定.
    const exportGetEdgePaths = (svg) => Array.from(svg.querySelectorAll('path.flowchart-link, path.edge-thickness-normal, g.edgePaths path, .edgePath path')).filter(p => !p.hasAttribute('data-edge-hit'));

    // [EXP-HL 2026-08-16] 给每条边加透明加宽的命中带 (stroke 16px), 解决"细线难点中"导致点击连线不高亮.
    //   命中带置于真实 path 之后 (SVG 后绘者在上), pointer-events: stroke → 点线及附近都命中;
    //   点击命中带在事件委托里按 data-edge-hit 索引映射回真实 path.
    const addEdgeHitAreas = (svg) => {
      const paths = exportGetEdgePaths(svg);
      paths.forEach((realPath, idx) => {
        if (realPath.getAttribute('data-hit-added')) return;
        realPath.setAttribute('data-hit-added', '1');
        const hit = realPath.cloneNode(false);
        hit.removeAttribute('id');
        hit.removeAttribute('data-relation-code');
        hit.classList.remove('flowchart-link', 'edge-thickness-normal', 'edge-pattern-solid');
        hit.setAttribute('data-edge-hit', String(idx));
        hit.setAttribute('stroke', 'transparent');
        hit.setAttribute('stroke-width', '16');
        hit.setAttribute('fill', 'none');
        hit.style.pointerEvents = 'stroke';
        hit.style.cursor = 'pointer';
        if (realPath.nextSibling) realPath.parentNode.insertBefore(hit, realPath.nextSibling);
        else realPath.parentNode.appendChild(hit);
      });
    };

    // [EXP-LEGEND 2026-08-16] 图例项点击 → 隐藏/显示该分组下的所有元素 (节点/折叠节点/分组容器/相关连线).
    //   与应用内"图例项点击切换分组 visible"语义一致 (增量隐藏, 不重排布局).
    const exportLegendToggle = (name, hidden) => {
      const svg = document.querySelector('.mermaid svg');
      if (!svg) return;
      let code = EXPORT_GROUPS[name] || EXPORT_GROUPS[(name || '').replace(/[（(].*$/, '').trim()];
      if (!code && EXPORT_CHILDREN[name]) code = name;
      if (!code) return;
      const scope = exportSubtreeCodes(code);
      const display = hidden ? 'none' : '';
      svg.querySelectorAll('g.node').forEach((el) => {
        const c = el.getAttribute('data-container-code') || el.getAttribute('data-code');
        if (c && scope.has(c)) el.style.display = display;
      });
      svg.querySelectorAll('g.cluster[data-container-code], .subgraph[data-container-code]').forEach((el) => {
        const c = el.getAttribute('data-container-code');
        if (c && scope.has(c)) el.style.display = display;
      });
      const labels = Array.from(svg.querySelectorAll('g.edgeLabel'));
      const paths = exportGetEdgePaths(svg);
      labels.forEach((labelEl, idx) => {
        const parts = (labelEl.textContent || '').split('-').map((p) => p.trim());
        if (parts.length < 2) return;
        const a = parts[0];
        const b = parts[parts.length - 1];
        if (scope.has(a) || scope.has(b)) {
          const pathEl = paths[idx];
          if (pathEl) {
            pathEl.style.display = display;
            // 同步隐藏该连线的透明命中带 (否则隐藏线仍可点击, 触发高亮一个不可见的线)
            const hit = pathEl.nextElementSibling;
            if (hit && hit.hasAttribute('data-edge-hit')) hit.style.display = display;
          }
          labelEl.style.display = display;
        }
      });
    };
    // [EXP-HL 2026-08-16] 构建 编码→SVG元素 映射 (节点 data-code / 折叠 data-container-code / 分组容器)
    const exportBuildCodeToEl = (svg) => {
      const codeToEl = new Map();
      svg.querySelectorAll('g.node').forEach((el) => {
        const c = el.getAttribute('data-container-code') || el.getAttribute('data-code');
        if (c && !codeToEl.has(c)) codeToEl.set(c, el);
      });
      svg.querySelectorAll('g.cluster[data-container-code], .subgraph[data-container-code]').forEach((el) => {
        const c = el.getAttribute('data-container-code');
        if (c && !codeToEl.has(c)) codeToEl.set(c, el);
      });
      return codeToEl;
    };

    // [EXP-HL 2026-08-16] 其余全部透明化: 未高亮连线 + 未高亮连线标题 + 未高亮节点/容器.
    //   hlEdges=已高亮连线集合; connected=已高亮节点编码集合; codeToEl=编码→元素.
    //   注意: 已高亮节点的祖先分组不淡化 (否则父级 opacity 0.25 会弱化子节点的高亮红框).
    //   mermaid 中 g.cluster 与 g.node 是 DOM 兄弟 (非父子), 不能用 el.contains 判断祖先,
    //   改用 EXPORT_PARENT 编码链判断"候选编码是否为已高亮编码的祖先".
    const exportIsAncestorCode = (code, descendant) => {
      let cur = descendant;
      let guard = 0;
      while (cur && guard < 12) {
        cur = EXPORT_PARENT[cur];
        guard++;
        if (cur === code) return true;
      }
      return false;
    };
    // [EXP-DIM 2026-08-16] 箭头 marker 淡化: mermaid 的箭头 marker 在 <defs> 内,
    //   给 path 设 opacity 只淡化描边, 不淡化 marker (箭头). 这里创建浅色变体 marker,
    //   临时把 path 的 marker-end/start 指向该变体, 清除时换回原 marker.
    const exportDimEdgeMarkers = (path) => {
      const svg = path.closest('svg');
      if (!svg) return;
      const defs = svg.querySelector('defs');
      if (!defs) return;
      ['marker-end', 'marker-start'].forEach((attr) => {
        const markerUrl = path.getAttribute(attr);
        if (!markerUrl) return;
        const match = markerUrl.match(/#([^)]+)/);
        if (!match) return;
        const origId = match[1];
        const dimId = origId + '-dim';
        // 同一颜色的变体 marker 只创建一次
        if (!defs.querySelector('#' + dimId)) {
          const orig = defs.querySelector('#' + origId);
          if (!orig) return;
          const clone = orig.cloneNode(true);
          clone.id = dimId;
          // [EXP-DIM 2026-08-16] 箭头必须跟着线一起"消失": 近白色 + 低透明度.
          //   之前用 #cccccc 全透明度的 marker, 线的 opacity 在部分浏览器不作用于 marker,
          //   导致"线透明了箭头还明显" → 用户感知连线淡化不足.
          clone.setAttribute('opacity', '0.35');
          clone.querySelectorAll('*').forEach((el) => {
            const fill = el.getAttribute('fill');
            if (fill && fill !== 'none') el.setAttribute('fill', '#eeeeee');
            const stroke = el.getAttribute('stroke');
            if (stroke && stroke !== 'none') el.setAttribute('stroke', '#eeeeee');
          });
          defs.appendChild(clone);
        }
        path.setAttribute('data-marker-orig-' + attr, markerUrl);
        path.setAttribute(attr, 'url(#' + dimId + ')');
      });
    };
    const exportRestoreEdgeMarkers = (path) => {
      ['marker-end', 'marker-start'].forEach((attr) => {
        const orig = path.getAttribute('data-marker-orig-' + attr);
        if (orig) {
          path.setAttribute(attr, orig);
          path.removeAttribute('data-marker-orig-' + attr);
        }
      });
    };
    const exportDimOthers = (svg, hlEdges, connected, codeToEl) => {
      const edgePaths = exportGetEdgePaths(svg);
      const edgeLabels = Array.from(svg.querySelectorAll('g.edgeLabel'));
      edgePaths.forEach((p) => { if (!hlEdges.has(p)) { p.classList.add('exp-dim-line'); exportDimEdgeMarkers(p); exportRelHl.dims.push(p); } });
      edgeLabels.forEach((l, idx) => { const p = edgePaths[idx]; if (!p || !hlEdges.has(p)) { l.classList.add('exp-dim-line'); exportRelHl.labels.push(l); } });
      const connectedArr = Array.from(connected);
      codeToEl.forEach((el, c) => {
        if (connected.has(c)) return;
        const isAncestorOfHl = connectedArr.some((d) => c !== d && exportIsAncestorCode(c, d));
        if (isAncestorOfHl) return;
        el.classList.add('exp-dim');
        exportRelHl.dims.push(el);
      });
    };

    const applyExportRelationsHl = (code, svg) => {
      clearExportRelationsHl();
      if (!svg || !code) return;
      const codeToEl = exportBuildCodeToEl(svg);
      const scope = exportSubtreeCodes(String(code));
      const edgeLabels = Array.from(svg.querySelectorAll('g.edgeLabel'));
      const edgePaths = exportGetEdgePaths(svg);
      const connected = new Set([String(code)]);
      const hlEdges = new Set();
      edgeLabels.forEach((labelEl, idx) => {
        const parts = (labelEl.textContent || '').split('-').map((p) => p.trim());
        if (parts.length < 2) return;
        const a = parts[0];
        const b = parts[parts.length - 1];
        const aIn = a && scope.has(a);
        const bIn = b && scope.has(b);
        if (aIn || bIn) {
          const pathEl = edgePaths[idx];
          if (pathEl) hlEdges.add(pathEl);
          // [EXP-HL 2026-08-16] 端点两侧都解析到可见元素并加入高亮:
          //   右击容器时, 容器内那一侧端点 (BO/子分组) 也要高亮, 不能只高亮外侧端点.
          const va = a && exportResolveVisible(a, codeToEl); if (va) connected.add(va);
          const vb = b && exportResolveVisible(b, codeToEl); if (vb) connected.add(vb);
        }
      });
      connected.forEach((c) => {
        const el = codeToEl.get(c);
        if (el) { el.classList.add('exp-hl-node'); exportRelHl.nodes.push(el); }
      });
      hlEdges.forEach((pathEl) => {
        if (!pathEl.classList.contains('exp-hl-edge')) {
          pathEl.classList.add('exp-hl-edge');
          exportRelHl.edges.push(pathEl);
        }
      });
      exportDimOthers(svg, hlEdges, connected, codeToEl);
    };

    // [EXP-HL 2026-08-16] 点击单条连线/连线标签 → 高亮该连线 + 源/目标节点 + 其余(含其余连线)透明化 (类似关系高亮)
    const applyExportEdgeHl = (edgeIdx, svg) => {
      clearExportRelationsHl();
      clearExportEdgeHl();
      const edgePaths = exportGetEdgePaths(svg);
      const edgeLabels = Array.from(svg.querySelectorAll('g.edgeLabel'));
      const pathEl = edgePaths[edgeIdx];
      if (!pathEl) return;
      pathEl.classList.add('exp-hl-edge');
      exportHlEdge = pathEl;
      const codeToEl = exportBuildCodeToEl(svg);
      const connected = new Set();
      const labelEl = edgeLabels[edgeIdx];
      const parts = (labelEl ? (labelEl.textContent || '') : '').split('-').map((p) => p.trim());
      if (parts.length >= 2) {
        const a = exportResolveVisible(parts[0], codeToEl);
        const b = exportResolveVisible(parts[parts.length - 1], codeToEl);
        if (a) connected.add(a);
        if (b) connected.add(b);
      }
      connected.forEach((c) => {
        const el = codeToEl.get(c);
        if (el) { el.classList.add('exp-hl-node'); exportRelHl.nodes.push(el); }
      });
      exportDimOthers(svg, new Set([pathEl]), connected, codeToEl);
    };

    // [EXP-HL 2026-08-16] 点击连线高亮 (应用内 annotation 点击连线一致)
    let exportHlEdge = null;
    const clearExportEdgeHl = () => {
      if (exportHlEdge) {
        exportHlEdge.classList.remove('exp-hl-edge');
        exportHlEdge = null;
      }
    };
    
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
        // [EXP-DRAG 2026-08-16] 记录按下起点 + 重置拖拽标记 (位移从按下起累计)
        expWasDrag = false;
        downX = e.clientX;
        downY = e.clientY;
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

      // [EXP-DRAG 2026-08-16] 从按下起总位移 >8px → 标记为拖拽, 供 click 判断不清高亮
      if (!expWasDrag) {
        const moved = Math.abs(e.clientX - downX) + Math.abs(e.clientY - downY);
        if (moved > 8) expWasDrag = true;
      }
      
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

        // [EXP-INTERACT 2026-08-16] 渲染稳定后接线导出交互:
        //   1) 节点/容器打业务编码属性 (右键关系高亮前置)  2) fit 到视口 (见全貌) + 动态 minScale
        //   3) 图例可点击隐藏/唤出  4) 点击连线高亮  5) 右键元素→高亮相关连线+源/目标节点  6) 双击空白恢复 fit
        setTimeout(() => {
          const svg = document.querySelector('.mermaid svg');
          if (!svg) return;
          
          exportTagElements(svg);
          fitToScreen(svg);
          
          // 3) 图例隐藏/唤出 (与应用内一致)
          const legendPanel = document.querySelector('.color-legend-panel');
          const legendClose = document.getElementById('export-legend-close');
          let legendToggle = null;
          if (legendPanel && legendClose) {
            legendClose.addEventListener('click', (e) => {
              e.stopPropagation();
              legendPanel.style.display = 'none';
              if (!legendToggle) {
                legendToggle = document.createElement('div');
                legendToggle.className = 'color-legend-toggle';
                legendToggle.textContent = '图例';
                legendToggle.title = '显示图例';
                legendToggle.addEventListener('click', () => {
                  legendPanel.style.display = '';
                  if (legendToggle) { legendToggle.remove(); legendToggle = null; }
                });
                document.body.appendChild(legendToggle);
              }
            });
          }
          
          // [EXP-HL 2026-08-16] 连线加透明命中带: 细线难点中, 加宽可点区域 (点击连线高亮的前提).
          addEdgeHitAreas(svg);
          
          // 图例项点击 → 切换分组可见性 (隐藏/显示该分组下所有元素, 与应用内图例项一致)
          const legendHidden = new Map();
          document.querySelectorAll('.color-legend-list .legend-item').forEach((item) => {
            const name = item.getAttribute('data-legend-name');
            if (!name) return;
            item.style.cursor = 'pointer';
            item.addEventListener('click', (e) => {
              e.stopPropagation();
              const hidden = !(legendHidden.get(name) || false);
              legendHidden.set(name, hidden);
              exportLegendToggle(name, hidden);
              item.style.opacity = hidden ? '0.4' : '';
              item.style.background = hidden ? 'rgba(0,0,0,0.04)' : '';
              const nm = item.querySelector('.legend-name');
              if (nm) nm.style.textDecoration = hidden ? 'line-through' : '';
              item.title = hidden ? '点击显示该分组' : '点击隐藏该分组';
            });
          });
          
          // [EXP-HL 2026-08-16] 点击: 连线/连线标签→高亮该线+源/目标节点+其余透明化; 节点/容器→关系高亮
          svg.addEventListener('click', (e) => {
            // [EXP-DRAG 2026-08-16] 拖拽后的 click 不取消/不触发高亮 (与 UI 一致):
            //   拖拽平移结束鼠标落在连线上, 浏览器 fire click, 若不守卫会误清当前高亮.
            if (expWasDrag) return;
            clearExportRelationsHl();
            clearExportEdgeHl();
            // 1) 命中带 / 连线标签 / 连线 path → 高亮该连线 + 源/目标节点 + 其余透明化
            let edgeIdx = -1;
            const hitEl = e.target.closest('[data-edge-hit]');
            if (hitEl) {
              edgeIdx = parseInt(hitEl.getAttribute('data-edge-hit'), 10);
            } else {
              // [FIX 2026-08-16] 标签文字点击热点: 必须 closest('g.edgeLabel') 而非 closest('.edgeLabel').
              //   根因: mermaid 标签文字是 <span class="edgeLabel">, 用 .edgeLabel 会命中 span 自身,
              //   而 indexOf 是在 g.edgeLabel 分组列表上查 → 返回 -1 → 点文字无任何高亮.
              //   closest('g.edgeLabel') 从 span 上溯到分组, 与应用内 bindEdgeFocus 一致.
              const labelG = e.target.closest('g.edgeLabel');
              if (labelG) {
                edgeIdx = Array.from(svg.querySelectorAll('g.edgeLabel')).indexOf(labelG);
              } else {
                const textEl = e.target.closest('.edgeLabel');
                if (textEl) {
                  // 兜底: 标签文字不在 g.edgeLabel 内 (兼容不同 mermaid 版本), 按文本匹配
                  const t = (textEl.textContent || '').trim();
                  edgeIdx = Array.from(svg.querySelectorAll('g.edgeLabel')).findIndex((gg) => (gg.textContent || '').trim() === t);
                } else {
                  // 点击连线本身 (path) → 按真实边路径索引 (label 分支修复时不能丢此分支)
                  const pathEl = e.target.closest('path.flowchart-link, path[data-relation-code]');
                  if (pathEl) edgeIdx = exportGetEdgePaths(svg).indexOf(pathEl);
                }
              }
            }
            if (edgeIdx >= 0) { applyExportEdgeHl(edgeIdx, svg); return; }
            // 2) 节点 → 关系高亮 (左击仅节点; 容器/分组只支持右击)
            const nodeEl = e.target.closest('g.node');
            if (nodeEl) {
              const code = nodeEl.getAttribute('data-container-code') || nodeEl.getAttribute('data-code');
              if (code) applyExportRelationsHl(code, svg);
            }
          });
          // [EXP-HL 2026-08-16] 右键: 与左击一致, 对节点/容器做关系高亮
          svg.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            clearExportRelationsHl();
            clearExportEdgeHl();
            const target = e.target.closest('g.node') || e.target.closest('g.cluster, .subgraph');
            if (!target) return;
            const code = target.getAttribute('data-container-code') || target.getAttribute('data-code');
            if (!code) return;
            applyExportRelationsHl(code, svg);
          });
          
          // 6) 双击空白 → 恢复 fit (与应用内双击空白 autoFit 一致)
          svg.addEventListener('dblclick', (e) => {
            const onEl = e.target.closest('g.node, g.cluster, .subgraph, .edgeLabel');
            if (!onEl) fitToScreen(svg);
          });
        }, 600);

        // [EXP-VERIFY 2026-08-16] 导出页自暴露状态快照: 探针加载导出 HTML 后一条 evaluate 读取
        //   连线/标签/高亮/淡化状态, 替代扫描 DOM 的脆弱断言.
        //   用法(在导出页): window.__exportHl.snapshot()  /  window.__exportHl.dimLineOpacity()
        window.__exportHl = {
          snapshot() {
            const svg = document.querySelector('.mermaid svg');
            if (!svg) return { error: 'no svg' };
            const paths = Array.from(svg.querySelectorAll('path.flowchart-link, g.edgePaths path, .edgePath path')).filter(p => !p.hasAttribute('data-edge-hit'));
            return {
              paths: paths.length,
              labels: Array.from(svg.querySelectorAll('g.edgeLabel')).map(l => (l.textContent || '').trim()),
              hlEdge: svg.querySelectorAll('.exp-hl-edge').length,
              hlNode: svg.querySelectorAll('.exp-hl-node').length,
              dimLine: svg.querySelectorAll('path.exp-dim-line').length,
              dim: svg.querySelectorAll('.exp-dim').length
            };
          },
          dimLineOpacity() {
            const svg = document.querySelector('.mermaid svg');
            const p = svg && svg.querySelector('path.exp-dim-line');
            return p ? getComputedStyle(p).opacity : null;
          }
        };
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
        // [EXP-VERIFY 2026-08-16] returnHtml 模式: 不下载, 直接返回字符串 (测试钩子用)
        if (opts.returnHtml) return htmlContent
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
            // [LEGEND-SECTION 2026-08-15] 节标题项: 渲染为纯文本标题, 占整行
            if (item.isSection) {
              const sectionDiv = document.createElement('div')
              sectionDiv.textContent = item.name || ''
              sectionDiv.style.cssText = 'flex-basis: 100%; font-size: 26px; color: #888; margin: 4px 0; letter-spacing: 1px;'
              legendGrid.appendChild(sectionDiv)
              return
            }
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
      // [FOLD-OVERLAP 2026-08-12] 必须暴露 foldRendering 给模板: 模板 :class 中
      //   { 'is-fold-rendering': foldRendering } 依赖此绑定。此前未暴露 → 模板取 undefined →
      //   class 永不生效 → 折叠渲染期间新 SVG 堆叠中心可见 (与 rendering 曾犯同样的错误, 见上).
      foldRendering,
      // [UX 2026-08-13] 折叠渲染角落等待指示器: 模板 v-if="foldLoadingVisible" 依赖此绑定.
      foldLoadingVisible,
      // [ESCALATE 2026-08-17] 折叠渲染长耗时升级整屏遮罩: 模板 v-if="rendering || foldRenderingEscalated"
      //   依赖此绑定. 与 foldLoadingVisible 类似, 不暴露则模板取 undefined → 升级遮罩永不显示.
      foldRenderingEscalated,
      // [CTX 2026-08-07] 右键上下文菜单
      ctxMenu,
      handleContextMenu,
      executeContextMenuAction,
      // [UX 2026-08-11] 悬停子菜单: 模板 v-for 中调用 hasSubmenu + 事件绑定 onItemMouseEnter 等,
      //   必须在此暴露, 否则模板从 _ctx 取到 undefined → "_ctx.hasSubmenu is not a function".
      hasSubmenu,
      submenuState,
      submenuRef,
      onItemMouseEnter,
      onItemMouseLeave,
      onSubmenuEnter,
      onSubmenuLeave,
      onMenuMouseLeave,
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



