<!--
  EmbeddedChartView - 嵌入式图表视图

  所属模块：架构数据管理页嵌入式图表

  [FIX 2026-07-27] 重写为复用老图表链路
    - 之前使用 useReactiveRenderer + MermaidCanvas 自研管线，
      经过 6 轮叠加修复仍无法正确渲染（缺颜色、SVG 16x16 等）
    - 现在改用 useDiagramData + MermaidComponent，
      这是 /archdata-chart 路由（老图表展示第三步骤）使用的同一套链路，
      经过了充分验证

  [重构 2026-07-28] chartConfig 提升为父组件持有
    - 之前 chartConfig 在本组件内部 reactive 创建
    - 现在由 RelationshipManagement 持有，通过 props.chartConfig 传入
    - 业务侧通过 GlobalToolbar 的 chart-config slot 渲染 ChartMiniToolbar，
      确保 toolbar 与 chart 视图共享单一数据源

  Props:
    - versionId: 版本 ID
    - hierarchyFilter: 转换契约（scopeIds → fetchPreviewData 的 filter）
    - chartConfig: 图表配置（业务侧持有，本组件仅消费）

  Emits:
    - node-click: 节点点击
    - render-complete: 渲染完成
    - render-error: 渲染失败
-->
<template>
  <div class="embedded-chart-view">
    <!-- [FIX 2026-07-30 v2] ChartMiniToolbar 由 GlobalToolbar 的 chart-config slot 渲染
         （按业务要求：图表配置按钮在 GlobalToolbar，不在 chart view 内部） -->
    <!-- 主体：mermaid 画布（复用老 MermaidComponent 组件） -->
    <div class="embedded-chart-view__body">
      <div v-if="loading" class="embedded-chart-view__loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载架构数据中...</span>
      </div>

      <div v-else-if="error" class="embedded-chart-view__error">
        <el-icon :size="32"><WarningFilled /></el-icon>
        <span>{{ error.message || '图表加载失败' }}</span>
        <el-button type="primary" size="small" @click="generateDiagram">重试</el-button>
      </div>

      <div v-else-if="!diagramData" class="embedded-chart-view__empty">
        <el-icon :size="32"><DataLine /></el-icon>
        <span>暂无数据，请检查左侧对象范围选择</span>
      </div>

      <div v-else ref="canvasContainerRef" class="embedded-chart-view__canvas">
        <!-- [FIX 2026-07-27] 用老图表的 MermaidComponent 渲染 diagramData
             它包含完整的颜色/注解/布局逻辑，与老图表展示第三步骤一致 -->
        <!-- [FIX 2026-07-29 画布缩小] 加 ref，ResizeObserver 触发时调用 relayoutCanvas -->
        <MermaidComponent
          ref="mermaidRef"
          :diagram-data="diagramData"
          :diagram-type="chartConfig.chartType"
          :layout-engine="chartConfig.layoutEngine"
          :layout-type="'default'"
          :preserve-model-order="false"
          :layout-control-config="layoutControlConfig"
          :annotation-config="annotationConfig"
        />
      </div>
    </div>

    <!-- [FIX 2026-07-28] 布局抽屉已上移到 ArchDataChartSwitcher 顶级
         （避免 v-if=context.versionId 阻止 drawer DOM 创建）。 -->
  </div>
</template>

<script setup>
import { reactive, computed, watch, onMounted, onBeforeUnmount, ref, nextTick } from 'vue'
import { Loading, WarningFilled, DataLine } from '@element-plus/icons-vue'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'
import { useDiagnostics } from '@/composables/useMermaid/core/useDiagnostics.js'
import { createDefaultChartConfig } from './chartConfigDefaults.js'
import { useDiagramData } from '@/views/AADiagramApp/composables/useDiagramData'
// [FIX 2026-07-27] 用老图表组件替换自研 MermaidCanvas
// [重构 2026-07-28] ChartMiniToolbar 不再在本组件内部使用，移到 GlobalToolbar slot
import MermaidComponent from '@/components/MermaidComponent.vue'
// [FIX 2026-07-28] 布局抽屉已上移到 ArchDataChartSwitcher，本组件不再引入 LayoutControlPanel。
// [FIX 2026-07-29 v4] 复用 services 中的自动分组工具（与 LayoutControlPanel 共享）
import { buildBusinessObjectGroups } from '@/services/autoGrouping/businessObjectAutoGrouper.js'
import { buildAnnotationFilterFromScope } from '@/services/scopeToFilter.js'
// [FIX 2026-07-30 v8] SM 图分组构建 + 状态迁移共享函数（layoutPanelAdapter.js）
import { buildServiceModuleGroupsFromDomainProducts, extractGroupStates as sharedExtractGroupStates, applyGroupStates as sharedApplyGroupStates } from '@/services/groupModel/layoutPanelAdapter.js'

const props = defineProps({
  scopeIds: {
    type: Object,
    required: true
  },
  versionId: {
    type: [Number, String],
    required: true
  },
  hierarchyFilter: {
    type: Object,
    required: true
  },
  // [重构 2026-07-28] chartConfig 提升为父组件（RelationshipManagement）持有，
  // 业务侧通过 GlobalToolbar 的 chart-config slot 渲染 ChartMiniToolbar，
  // EmbeddedChartView 仅消费，确保 toolbar 与 chart 视图同步刷新。
  chartConfig: {
    type: Object,
    required: true
  }
  // [FIX 2026-07-28] layoutDrawerVisible 已移到 ArchDataChartSwitcher 处理，本组件不再关注。
})

const emit = defineEmits([
  'node-click',
  'render-complete',
  'render-error'
])

// ============================================================
// chartConfig（reactive）
// [重构 2026-07-28] 提升为父组件持有，本组件通过 props.chartConfig 引用，
// 直接访问 props.chartConfig（reactive object from parent）即可。
// 不再内部创建 local chartConfig，避免状态分散。
// [FIX 2026-07-28] 兜底处理：父组件的 chartConfig 可能因 reactive 初始化时机问题
//   临时为 undefined，用 reactive 创建 local fallback 避免 computed 抛错。
// [Phase 1 修复 2026-07-28] fallback 字段对齐 Pinia layoutControlConfig 契约：
//   新增 overallDirection/preserveOrder，layoutEngine→engine。
// [T1 2026-08-02] fallback 默认值统一走 chartConfigDefaults.js 工厂
// ============================================================
const chartConfig = props.chartConfig ?? reactive(createDefaultChartConfig())

// [FE3 2026-08-02] 暴露 chartConfig 到 __archPage — E2E 配置切换入口。
//   E2E 直接改 window.__archPage.chartConfig.colorScheme = 'vibrant'
//   触发下方 watcher → configStore.updateColorScheme → generateDiagram,
//   避免操作 Element Plus 下拉弹层的脆弱 UI 交互。
//   注意: 引用的是父组件 (RelationshipManagement) 的同一 reactive 对象。
if (typeof window !== 'undefined') {
  window.__archPage = window.__archPage || {}
  window.__archPage.chartConfig = chartConfig
}

// ============================================================
// useDiagramData：复用老图表的核心数据逻辑
// 输入：versionId + hierarchyFilter + relationTypeFilter
// 输出：diagramData（喂给 MermaidComponent）
// ============================================================
const configStore = useDiagramConfigStore()
const diag = useDiagnostics()  // [O1/V2 2026-08-02] 监听 MermaidComponent 渲染结束 (SVG 级口径)

const {
  loading,
  error,
  diagramData,
  generateDiagram,
  initFromArchDataManager
} = useDiagramData()

// [E2E 2026-08-02] 暴露 generateDiagram — 供 E2E 触发"相同输入重渲染"验证 L5 增量跳过
//   (Task 8 spec 4.4: mermaidCode 与上次一致时跳过 mermaid.run 全量重绘)。
//   用法: window.__archPage.generateDiagram() → 新 diagramData 引用 → MermaidComponent
//   watch 触发 renderMermaid → code-diff 相同 → renderSkippedCount+1 / lastRender 不更新。
if (typeof window !== 'undefined') {
  window.__archPage = window.__archPage || {}
  window.__archPage.generateDiagram = generateDiagram
}

// [FIX 2026-07-29 画布缩小] 监听画布容器尺寸变化，调用 MermaidComponent.relayoutCanvas
//   重设 .mermaid-wrapper / .draggable-area 的 inline style 尺寸。
//
//   根因：MermaidComponent 内部 handleWindowResize 只监听 window resize，
//   drawer 打开/关闭、tab 切换、splitter 拖动等场景不会触发 window resize，
//   导致 wrapper 的 inline style 仍是旧尺寸 → SVG 按旧尺寸渲染 → 视觉画布缩小。
//
//   方案：用 ResizeObserver 监听 .embedded-chart-view__canvas（本组件画布容器），
//   尺寸变化且稳定后调用 MermaidComponent 暴露的 relayoutCanvas 方法：
//     1) setupCanvasLayout 重新读取 .mermaid-container 尺寸，设置 wrapper/draggable-area
//     2) autoFitDiagram 重置 SVG transform（scale=1, translate=0,0），让 SVG fit 新容器
//
//   对比旧方案（generateDiagram）：
//   - 轻量：不重新生成 diagramData，不重新跑 mermaid.run
//   - 不受 MermaidComponent watch 的 isRendering 防重入影响
//   - 时序简单：ResizeObserver → relayoutCanvas，无异步 watch 链路
const canvasContainerRef = ref(null)
const mermaidRef = ref(null)
let resizeObserver = null
let resizeTimer = null
const onCanvasResize = () => {
  if (!canvasContainerRef.value || !mermaidRef.value) return
  // debounce 150ms 防止快速连续变化（如 drawer 动画过程中）触发多次
  clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (mermaidRef.value && typeof mermaidRef.value.relayoutCanvas === 'function') {
      mermaidRef.value.relayoutCanvas()
    }
  }, 150)
}

// ============================================================
// layoutControlConfig：BO 图用最小配置 (groups: []) 强制走 subgraph 路径
//   不从 diagramData.layoutControlConfig 取, 因为 useDiagramData 给 BO 图的
//   layoutControlConfig 来自 groupModel.toMermaidConfig() 含 groups, 会让
//   useBusinessObjectSyntax 走 groupedLayout 路径, 但那条路径颜色硬编码不染色
//   之前用 { enabled:true, groups:[] } 是对的, 强制走 subgraph 路径, 由 nodeColorMap 取色
// [FIX 2026-07-28] 动态 groups：现在 chartConfig.layoutControl 由 LayoutControlPanel 维护，
//   并通过 v-model 同步回这里。groups 不再硬编码 []，实时反映用户在面板里的拖拽结果。
// [Phase 1 修复 2026-07-28] 透传 overallDirection/preserveOrder 字段；
//   engine 字段优先从 chartConfig.layoutControl.engine 取（与 Pinia store 对齐），
//   fallback 到 chartConfig.layoutEngine（向后兼容）。
// ============================================================
const layoutControlConfig = computed(() => {
  const rawGroups = chartConfig.layoutControl?.groups || []

  // [FIX 2026-08-02 方案A] SM 图统一管道: 渲染容器层级必须用 unifiedLayoutConfig
  //   (deriveLayoutGroups 从投影容器树派生, D→SD→directNodes)。
  //   不能用 chartConfig.layoutControl.groups: 旧 SM 分组树 (syncLayoutControlFromDiagramData
  //   经 buildServiceModuleGroupsFromDomainProducts 写入) 含 SM 终端 group (SM_xxx→inner/boundary),
  //   groupedLayout 会为每个 SM 生成 G_SM_xxx subgraph → 复现"同一 SM 既容器又节点"重复渲染。
  // [Task 10 2026-08-02] BO 图同迁移到统一管道: D→SD→SM→BO 容器层级由投影容器树派生,
  //   渲染同样必须用 unifiedLayoutConfig。groupType 标记区分管道产物 (deriveLayoutGroups 输出),
  //   旧 groupModel/legacy 分组 (含 type 字段、无 groupType) 不受影响, 继续走下方逻辑。
  if (chartConfig.chartType === 'serviceModule' || chartConfig.chartType === 'businessObject') {
    const d = diagramData.value
    const unified = d?.diagramData?.layoutControlConfig || d?.layoutControlConfig
    if (unified && unified.enabled && unified.groups && unified.groups.length > 0
        && unified.groups.some(g => g && g.groupType)) {
      return {
        enabled: true,
        layoutType: 'default',
        layoutEngine: chartConfig.layoutControl?.engine || chartConfig.layoutEngine,
        overallDirection: unified.overallDirection || chartConfig.layoutControl?.overallDirection || 'TB',
        preserveOrder: chartConfig.layoutControl?.preserveOrder ?? true,
        groups: unified.groups.map(g => normalizeGroupForRendering(g))
      }
    }
  }

  // [FIX 2026-07-29] 当用户没创建分组时 (rawGroups 为空)，fallback 到 diagramData
  //   自动构建的分组 (useDiagramData.generateDiagram 内部通过 groupModel.toMermaidConfig()
  //   生成，存在 diagramData.layoutControlConfig)。
  //
  //   根因：之前直接用空 groups，导致 useBusinessObjectSyntax 走 else 分支，
  //   只生成 moduleGroups 级扁平 subgraph (按服务模块分组)，
  //   缺少 subDomain 级嵌套容器 (领域→子领域→服务模块 三层结构)。
  //   修复后：用 diagramData 自动构建的 groups (含领域/子领域/服务模块嵌套)，
  //   走 routeLayout 路径，生成正确的嵌套 subgraph。
  if (rawGroups.length === 0) {
    const d = diagramData.value
    const autoConfig = d?.diagramData?.layoutControlConfig || d?.layoutControlConfig
    if (autoConfig && autoConfig.groups && autoConfig.groups.length > 0) {
      const autoGroups = autoConfig.groups.map(g => normalizeGroupForRendering(g))
      return {
        enabled: true,
        layoutType: 'default',
        layoutEngine: chartConfig.layoutControl?.engine || chartConfig.layoutEngine,
        overallDirection: chartConfig.layoutControl?.overallDirection || autoConfig.overallDirection || 'TB',
        preserveOrder: chartConfig.layoutControl?.preserveOrder ?? true,
        groups: autoGroups
      }
    }
  }

  // [FIX 2026-07-29 v3] 移除 normalizeGroupForRendering 强制改 enabled=true 的逻辑
//
// 历史（v1 2026-07-28）：LayoutControlPanel 自动分组默认给 domain 设 enabled=false, visible=false
//   想用 disabled 表达"不显示边框"，但导致 groupedLayout 跳过整个 group（包括 children）。
//   之前的临时修复是把 disabled 强制改回 enabled=true，但这破坏了用户主动 disable 的语义。
//
// 历史（v2 2026-07-29）：disabled 直接 return 不渲染，与 SM 图"完全消失"语义一致。
//   但 BO 图 default-disabled 设计导致图表变成空。
//
// 当前（v3 2026-07-29）：LayoutControlPanel.handleBusinessObjectAutoGroup 改为默认
//   enabled=true, visible=true。disable 边框的语义单独通过 visible=false 表达。
//   尊重用户显式 disable 的语义（disabled group + children 完全消失），与 SM 图一致。
//
//   关于 normalizeGroupForRendering：保留函数（不再强制改 enabled），
//   仅为可能的字段兼容（如 fill/stroke 兼容）。group.enabled 直接透传给 groupedLayout。
const groups = rawGroups.map(g => normalizeGroupForRendering(g))

  return {
    enabled: true,
    layoutType: 'default',
    layoutEngine: chartConfig.layoutControl?.engine || chartConfig.layoutEngine,
    overallDirection: chartConfig.layoutControl?.overallDirection || 'TB',
    preserveOrder: chartConfig.layoutControl?.preserveOrder ?? true,
    groups
  }
})

// [Phase 1 修复 v3] 递归保留嵌套结构，让 routeLayout 渲染嵌套 subgraph
//   [FIX 2026-07-29] 不再强制把 enabled: false 改为 enabled: true。尊重用户的 disabled 状态，
//   让 groupedLayout.js 走"disabled 不创建外层 subgraph"的逻辑（groupedLayout.js line 170-249）。
function normalizeGroupForRendering(group) {
  if (!group) return group
  const cloned = { ...group }
  if (Array.isArray(cloned.children)) {
    cloned.children = cloned.children.map(c => normalizeGroupForRendering(c))
  }
  if (Array.isArray(cloned.containers)) {
    cloned.containers = cloned.containers.map(c => ({ ...c }))
  }
  // 之前这里会强制 enabled=false → enabled=true，但破坏了用户 disabled 意图。
  // 现在保留原值，让下游 render 决定如何处理 disabled。
  return cloned
}

// ============================================================
// annotationConfig：触发 MermaidComponent 内部 renderAnnotationOverlay
//   包含 centerScopeHighlight + showAnnotationIcons
//   没有它 → overlayColorLegend 不会被调用 → legend 不显示
//
// [FIX 2026-07-31] annotationCategoryFilter 从 scopeIds 实时派生（回溯修复丢失功能）：
//   buildAnnotationFilterFromScope 之前只定义+测试，从未被生产代码调用。
//   用户在 RelationFilterSection 选了"备注类型"下拉多选后，选择存入
//   scopeIds.globalFilters.annotation_category，但从未传到图表渲染管线。
//   现在通过本 computed 将 scopeIds → annotationCategoryFilter 接通。
// ============================================================
const annotationConfig = computed(() => ({
  // [FIX 2026-07-31] 从 chartConfig 读取, 不再硬编码 true
  //   用户可通过 ChartMiniToolbar 的"中心范围"下拉切换
  centerScopeHighlight: chartConfig.centerScopeHighlight !== false,
  // [2026-08-02] "显示备注图标"按钮已移除: showIcons 从未被读取 (图标绘制是死代码), 恒为 false.
  //   备注展示由"备注类型"过滤 + 底部备注面板 + 悬停 tooltip 承担, 不再依赖本开关.
  showAnnotationIcons: false,
  // [FIX 2026-07-31 v2] 优先级: chartConfig.annotationCategoryFilter (toolbar 直接选) > scopeIds.globalFilters
  //   - 配置阶段用户在 RelationFilterSection 选: 存入 scopeIds.globalFilters.annotation_category (老通道)
  //   - 图表视图用户从 toolbar 直接选: 存在 chartConfig.annotationCategoryFilter (新通道)
  //   - 两个通道合并去重, toolbar 优先 (即: 任何在 toolbar 选了的不为空时, scopeIds 被忽略)
  annotationCategoryFilter: (() => {
    const fromToolbar = chartConfig.annotationCategoryFilter || []
    if (fromToolbar.length > 0) return fromToolbar
    return buildAnnotationFilterFromScope(props.scopeIds)
  })(),
  legendPosition: 'top-left'
}))

// ============================================================
// 监听 chartType 变化 → 同步到 configStore + 重新生成
// ============================================================
// [E3 2026-08-02] 图表类型切换代数: 每次切换自增, 防止旧切换的异步同步
//   在切换后覆盖新图表类型的 groups (竞态: 快速连点 BO↔SM 时旧同步晚到)
let _chartTypeGenId = 0
watch(() => chartConfig.chartType, async (newType) => {
  const genId = ++_chartTypeGenId
  // [FIX 2026-07-29 v6.2] 在任何重置/重新生成之前，先快照旧 groups 的 enabled/visible 状态
  //   原因：generateDiagram() 会触发 LayoutControlPanel.onMounted 的 handleAutoGroupByDomain
  //   重置 groups（把所有 enabled 重置为 true），导致 syncLayoutControlFromDiagramData(true)
  //   调用 extractGroupStates 时旧 groups 已经被清空/重置。
  //   修复：在 watch 最开头先快照，然后传给 syncLayoutControlFromDiagramData 应用。
  const preservedGroupStates = sharedExtractGroupStates(chartConfig.layoutControl?.groups)

  configStore.updateChartType(newType)
  diag.recordStepMeta('generateDiagram', { source: 'chartType', at: Date.now() })
  // [FIX 2026-07-27] 同步后必须重新生成图表
  //   之前只调 updateChartType，没调 generateDiagram，切换无效果
  if (diagramData.value) await generateDiagram()
  // [E3 2026-08-02] 期间又切换了图表类型 → 丢弃本次同步 (旧 groups 不覆盖新状态)
  if (genId !== _chartTypeGenId) return
  // [FIX 2026-07-29 v6] 切换图表类型后强制重新生成 groups 并迁移旧 enabled/visible 状态
  //   之前只调 generateDiagram，没调 syncLayoutControlFromDiagramData，导致切换后 groups 为空。
  //   现在用 force=true 强制重新生成对应图表类型的 groups，同时把旧 groups 的 enabled/visible
  //   状态迁移到新 groups（按 elementCode 匹配），保留用户的 disable 配置。
  //   这样切换到 SM 图后，BO 图中 disable 的供应链云仍然是 disabled。
  //   [FIX v6.2] 状态从 watch 入口处快照获取（避免被 generateDiagram 重置后丢失）。
  await syncLayoutControlFromDiagramData(true, preservedGroupStates, genId)
})

// ============================================================
// 监听 colorScheme/colorGroupBy 变化 → 同步到 configStore
// [FIX 2026-07-27] 去掉手动 generateDiagram() 调用
//   useDiagramData 内部已有 watcher 监听 diagramConfig.value.colorGroupBy
//   会自动调 generateDiagram()，这里再调一次会导致双重触发
// ============================================================
watch(() => chartConfig.colorScheme, (newScheme, oldScheme) => {
  if (newScheme === oldScheme) return
  configStore.updateColorScheme(newScheme)
  diag.recordStepMeta('generateDiagram', { source: 'colorScheme', at: Date.now() })
})

watch(() => chartConfig.colorGroupBy, (newGroupBy, oldGroupBy) => {
  if (newGroupBy === oldGroupBy) return
  configStore.updateColorGroupBy(newGroupBy)
  diag.recordStepMeta('generateDiagram', { source: 'colorGroupBy', at: Date.now() })
})

// [NEW 2026-07-31] 监听 chartConfig.centerScopeHighlight → 同步到 configStore
//   用户需求: 在 ChartMiniToolbar 增加"区分中心范围"下拉, 默认 true
//   store 变化后 useDiagramData watch (L1949-1956) 会自动调 generateDiagram()
watch(() => chartConfig.centerScopeHighlight, (newVal, oldVal) => {
  if (newVal === oldVal) return
  configStore.updateCenterScopeHighlight(newVal)
  diag.recordStepMeta('generateDiagram', { source: 'centerScopeHighlight', at: Date.now() })
})

// ============================================================
// [Phase 1 修复 2026-07-28] 监听 chartConfig.layoutControl 变化 → 同步到 configStore
//   LayoutControlPanel 修改 groups/overallDirection/engine 后，
//   通过 ArchDataChartSwitcher.onLayoutConfigUpdate 写回 chartConfig.layoutControl。
//   这里同步到 configStore.layoutControlConfig，useDiagramData 内部 watch 会被触发
//   调用 generateDiagram() 重新生成图表，实现"配置变化→重渲染"闭环。
//
//   关键：deep watch，因为 LayoutControlPanel 修改的是 groups 数组内部的字段
//   （enabled/visible/containers 等），不是整体替换 layoutControl 对象。
// ============================================================
// [FIX 2026-07-29 v3] 标志位：syncLayoutControlFromDiagramData 主动写入 chartConfig.layoutControl 时
//   跳过 watch 触发的 generateDiagram，避免循环刷新。
let _skipLayoutControlWatch = false
// [E1 2026-08-02] 防抖定时器: 布局面板拖拽分组时 groups 深层连续变化,
//   每次都全量 generateDiagram + mermaid.run 开销极大, 合并为拖拽停顿后的单次渲染
let _layoutControlTimer = null
watch(
  () => chartConfig.layoutControl,
  (newLayout) => {
    if (!newLayout) return
    if (_skipLayoutControlWatch) return
    // [E1 2026-08-02] 250ms 防抖合并连续拖拽
    clearTimeout(_layoutControlTimer)
    _layoutControlTimer = setTimeout(async () => {
      configStore.updateLayoutControlConfig(newLayout)
      // [T3 2026-08-02] 触发来源标注 — chart_diag / window.__archPage.mermaid.stepMeta 可读
      diag.recordStepMeta('generateDiagram', { source: 'layoutControl-debounced', at: Date.now() })
      try {
        await generateDiagram()
      } catch (e) {
        console.error('[EmbeddedChartView] generateDiagram after layoutControl change failed:', e)
      }
    }, 250)
  },
  { deep: true }
)

// [Phase 1 修复 2026-07-28] 监听 chartConfig.layoutEngine 变化
//   关系连线模式 elk/dagre 切换，同步到 configStore 并重新生成
watch(
  () => chartConfig.layoutEngine,
  (newEngine, oldEngine) => {
    if (newEngine === oldEngine) return
    configStore.updateLayoutEngine(newEngine)
    // 同步到 layoutControl.engine（保持字段一致）
    if (chartConfig.layoutControl) {
      chartConfig.layoutControl.engine = newEngine
    }
    diag.recordStepMeta('generateDiagram', { source: 'layoutEngine', at: Date.now() })
    if (diagramData.value) generateDiagram()
  }
)

// ============================================================
// [重构 2026-07-28] handle* 函数已移除：
//   ChartMiniToolbar 的 emit('update:chartType' 等) 现在由父组件 RelationshipManagement 接收，
//   父组件负责更新 chartConfig 后通过 props 传回本组件。
//   本组件只负责：
//     1) 同步 chartConfig 到 configStore（触发 useDiagramData 重新生成）
//     2) 监听 chartConfig 自身变化
//   直接修改 props.chartConfig 即可（Vue 3 reactive object 引用透明）。

// ============================================================
// [O1/V2 2026-08-02] 渲染完成/失败 → emit (SVG 级口径)
//   - 之前 watch(diagramData) 报的是数据级 nodeCount (diagramData.nodes.length),
//     与真实渲染出的 SVG 节点数不一致, 且 render-complete 事件无人消费。
//   - 现在通过 diag.hooks 监听 MermaidComponent 的真实渲染结束:
//     diag.endRender 已统计 SVG 级 nodeCount/edgeCount/containerCount
//     (g.node / path.flowchart-link / g.cluster), 口径与人工验证一致。
//   - 渲染错误走 diag.recordError → onError hook → emit render-error。
// ============================================================
let _prevDiagOnRenderEnd = null
let _prevDiagOnError = null

const onDiagRenderEnd = (info) => {
  // [FE2 2026-08-02] DOM 渲染完成标记 — E2E 用 wait_for_selector 替代轮询, 更快更稳。
  //   data-chart-rendered: 'true' / data-node-count: SVG 级节点数
  if (canvasContainerRef.value) {
    canvasContainerRef.value.setAttribute('data-chart-rendered', 'true')
    canvasContainerRef.value.setAttribute('data-node-count', String(info?.nodeCount ?? 0))
    canvasContainerRef.value.setAttribute('data-edge-count', String(info?.edgeCount ?? 0))
    canvasContainerRef.value.setAttribute('data-container-count', String(info?.containerCount ?? 0))
  }
  if (info?.error) {
    emit('render-error', { error: info.error, phase: 'mermaid', durationMs: info.durationMs ?? null })
    return
  }
  emit('render-complete', {
    nodeCount: info?.nodeCount ?? 0,
    edgeCount: info?.edgeCount ?? 0,
    containerCount: info?.containerCount ?? 0,
    durationMs: info?.durationMs ?? null,
    source: 'mermaid-svg'
  })
}

const onDiagError = (entry) => {
  if (canvasContainerRef.value) {
    canvasContainerRef.value.setAttribute('data-chart-rendered', 'false')
    canvasContainerRef.value.setAttribute('data-error', String(entry?.message || entry))
  }
  emit('render-error', { error: entry, phase: entry?.context || 'mermaid' })
}

// 加载阶段错误 (useDiagramData 的 fetch 失败) 不走 diag 链路, 单独 watch
watch(error, (err) => {
  if (err) emit('render-error', { error: err, phase: 'load' })
})

// ============================================================
// 初始化：从 arch data 注入数据
// ============================================================
onMounted(async () => {
  // [O1/V2 2026-08-02] 安装 diag hooks (模块单例, 先保存旧值, 卸载时恢复)
  _prevDiagOnRenderEnd = diag.hooks.onRenderEnd
  _prevDiagOnError = diag.hooks.onError
  diag.hooks.onRenderEnd = onDiagRenderEnd
  diag.hooks.onError = onDiagError

  await configStore.updateChartType(chartConfig.chartType)

  // 把 scopeIds 转换成 hierarchyFilter + relationTypeFilter（复用老链路）
  const archData = {
    versionId: Number(props.versionId),
    hierarchyFilter: props.hierarchyFilter || {},
    relationTypeFilter: [],
    relationIds: [],
    relationCategoryTypes: []
  }
  await initFromArchDataManager(archData)

  // 初始化后触发首次图表生成
  await generateDiagram()

  // [FIX 2026-07-29 v3] 预生成"分组布局数据模型" → 写回 chartConfig.layoutControl
  //   架构设计：
  //     1. 自动分组（build groups）应在 mermaid 展示前完成，与"点击布局设置"解耦
  //     2. LayoutControlPanel 仅负责"修改"分组，不负责"创建"
  //     3. mermaid 展示响应 chartConfig.layoutControl 变化（已通过 deep watch + generateDiagram 实现）
  //
  //   修复：
  //     - generateDiagram 内部已通过 groupModel.toMermaidConfig() 自动构建 groups
  //       （diagramData.layoutControlConfig.groups）
  //     - 这里把它写回 chartConfig.layoutControl（同时同步 configStore.layoutControlConfig）
  //     - 这样 LayoutControlPanel.onMounted 时 groups 已有值，不会再触发自动分组初始化
  //     - 用户点击布局设置 = 仅打开抽屉，不再触发图表刷新
  await syncLayoutControlFromDiagramData()

  // [FIX 2026-07-29 画布缩小] 注册 ResizeObserver 监听画布容器尺寸变化
  //   父容器尺寸变化（drawer 打开/关闭、tab 切换等）时调用 mermaidRef.relayoutCanvas
  //   重设 wrapper/draggable-area 尺寸，让 SVG 按新容器尺寸 fit
  //   用 nextTick 等待 v-else 链生效（diagramData 有值后 .embedded-chart-view__canvas 才挂载）
  await nextTick()
  if (canvasContainerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(onCanvasResize)
    resizeObserver.observe(canvasContainerRef.value)
  }
})

/**
 * [FIX 2026-07-29 v4] 预生成分组布局数据模型
 *   触发时机：EmbeddedChartView.onMounted（首次 generateDiagram 后）
 *
 * 关键：调用 services.buildBusinessObjectGroups(containers, links) 生成 LayoutControlPanel
 *   期望的嵌套结构（domain→subDomain→serviceModule→containers）。
 *
 *   之前（v3）这里用 groupModel.toMermaidConfig() 的输出（扁平结构），导致：
 *     1. LayoutControlPanel 打开后看不到正确的嵌套分组（领域下直接是子领域节点）
 *     2. 业务对象节点都在待分配区域（groupModel.toMermaidConfig 不把 BO 节点放到 containers）
 *
 *   修复：直接调用 buildBusinessObjectGroups 生成 LayoutControlPanel 期望的结构。
 *     这套结构与 LayoutControlPanel.handleBusinessObjectAutoGroup 输出完全一致，
 *     LayoutControlPanel 打开后能正确显示 domain→subDomain→serviceModule 嵌套。
 *
 * [FIX 2026-07-29 v5] SM 图改为通过 adaptGroupModelForLayoutPanel 把 GroupModel.toMermaidConfig
 *   输出转换为 LayoutControlPanel 期望格式。这样 SM 图首次打开布局抽屉时 groups 已有值，
 *   不再触发 handleServiceModuleAutoGroup → emitUpdate → 图表刷新。
 *   [FIX 2026-07-30 v8] 改为用 buildServiceModuleGroupsFromDomainProducts 从 domainProducts 直接构建，
 *   不再依赖 GroupModel.toMermaidConfig 输出（该输出会过滤 disabled 分组，导致状态迁移失败）。
 *
 * 同步内容：
 *   - chartConfig.layoutControl.groups（嵌套分组树）
 *   - chartConfig.layoutControl.overallDirection（整体方向）
 *   - chartConfig.layoutControl.engine（elk/dagre）
 *   - configStore.layoutControlConfig（同上，让 useDiagramData 内部 watch 看到一致状态）
 *
 * 仅在 chartConfig.layoutControl.groups 为空时执行（避免覆盖用户已有配置）。
 * - BO 图：buildBusinessObjectGroups 路径（保持原逻辑）
 * - SM 图：buildServiceModuleGroupsFromDomainProducts 路径（v8，从 domainProducts 直接构建）
 */
async function syncLayoutControlFromDiagramData(force = false, preservedStates = null, genId = null) {
  // [FIX 2026-07-29 v3] 仅在 BO 图时同步（SM 图走 LayoutControlPanel.handleServiceModuleAutoGroup）
  // [FIX 2026-07-29 v5] SM 图改为通过 adaptGroupModelForLayoutPanel 预填充 groups，
  //   避免首次打开布局抽屉时 LayoutControlPanel.onMounted 检测 groups 为空 → 触发
  //   handleServiceModuleAutoGroup → emitUpdate → generateDiagram → 图表刷新。
  //   [FIX 2026-07-30 v8] 改为用 buildServiceModuleGroupsFromDomainProducts 从 domainProducts 直接构建，
  //   不再依赖 GroupModel.toMermaidConfig 输出（该输出会过滤 disabled 分组，导致状态迁移失败）。
  //   BO 图保持原 buildBusinessObjectGroups 路径不变（GroupModel 输出会丢失 BO 终端节点）。
  const isBO = chartConfig.chartType === 'businessObject'
  const isSM = chartConfig.chartType === 'serviceModule'
  if (!isBO && !isSM) return

  // [FIX 2026-07-29 v6] 切换图表类型时（force=true），强制重新生成对应图表类型的 groups，
  //   但保留旧 groups 中各分组的 enabled/visible 状态（按 elementCode 匹配）。
  //   原因：BO 图和 SM 图的 groups 结构不同（BO 图终端是 BUSINESS_OBJECT，SM 图终端是 SERVICE_MODULE），
  //   切换时必须重新生成。但如果不清空 groups，syncLayoutControlFromDiagramData 的"仅 groups 为空时同步"
  //   检查会直接 return，导致 SM 图用着 BO 图的 groups 结构，LayoutControlPanel.onMounted 检测
  //   totalSmInGroups !== totalSmInSource → needReGroup=true → handleAutoGroupByDomain → 所有 enabled 重置。
  //   修复：force=true 时跳过"仅 groups 为空时同步"检查，重新生成 groups，并迁移旧 enabled/visible 状态。
  if (!force) {
    // 仅在 chartConfig.layoutControl.groups 为空时同步（避免覆盖已有配置）
    if (chartConfig.layoutControl?.groups && chartConfig.layoutControl.groups.length > 0) {
      return
    }
  }

  // [FIX 2026-07-29 v6.2] 状态优先用调用方传入的快照（preservedStates），
  //   避免在 generateDiagram() 之后旧 groups 已被重置导致 extractGroupStates 拿不到状态。
  //   如果调用方没传（force=false 或其他调用路径），才从当前 chartConfig.layoutControl.groups 提取。
  const oldGroupStates = force ? (preservedStates || sharedExtractGroupStates(chartConfig.layoutControl?.groups)) : null

  // 等待 diagramData 准备好（useDiagramData.generateDiagram 是 async）。
  //   最多等 5 秒（每次 200ms 轮询）。
  //   - BO 图：等 nodes + domainProducts（用于 buildBusinessObjectGroups）
  //   - SM 图：[FIX v8] 等 domainProducts（用于 buildServiceModuleGroupsFromDomainProducts）
  let waitCount = 0
  while (waitCount < 25 && !isDiagramReadyForSync()) {
    await new Promise(r => setTimeout(r, 200))
    waitCount++
  }
  // [V3 2026-08-02] 超时可见化: 之前 5s 轮询超时后静默 return, 排查时序问题时
  //   无法区分"等到了"还是"超时跳过"。现在记录 warning (chart_diag 可读)。
  if (waitCount >= 25) {
    diag.recordWarning(`syncLayoutControlFromDiagramData 等待 diagramData 超时 (5s), chartType=${chartConfig.chartType}`, 'syncLayoutControl')
  }

  // 等 nextTick 让 computed 重新计算
  await nextTick()

  let groups = []
  if (isBO) {
    // BO 图：从 containers/links 派生（保持原逻辑）
    const containersData = containers.value || []
    const linksData = links.value || []

    // [FIX 2026-07-29 v4] 如果 wait loop 后 containers 还是 fallback（dps 仍为空），
    //   说明 useDiagramData.generateDiagram 是异步链式调用，5 秒内未能 ready。
    //   直接 return 不写入 D_未分类（避免错误分组污染 chartConfig.layoutControl.groups）。
    if (containersData.length === 1 && containersData[0]?.id === 'virtual') {
      return
    }
    if (!containersData.length) return

    groups = buildBusinessObjectGroups(containersData, linksData)
  } else if (isSM) {
    // [FIX 2026-07-30 v8] SM 图：从 domainProducts 直接构建分组树，不依赖 GroupModel.toMermaidConfig 输出。
    //   之前用 adaptGroupModelForLayoutPanel 转换 GroupModel 输出，但 GroupModel.toMermaidConfig 会过滤
    //   disabled 分组（L466-468 返回 null），导致 disabled 的"供应链云"在 SM 图 groups 中丢失，
    //   applyGroupStates 找不到匹配项 → 状态迁移失败 → 切回 BO 图时 disabled 状态丢失（循环依赖）。
    //   修复：改用 buildServiceModuleGroupsFromDomainProducts 从 domainProducts 直接构建，
    //   保留所有 domain（包括 disabled 的），与 LayoutControlPanel.handleServiceModuleAutoGroup 共享逻辑。
    const d = diagramData.value
    const dps = d?.diagramData?.domainProducts || d?.domainProducts || []
    if (!dps.length) return
    groups = buildServiceModuleGroupsFromDomainProducts(dps)
  }

  if (!groups || groups.length === 0) return

  // [FIX 2026-07-29 v6] 切换图表类型时（force=true），把旧 groups 的 enabled/visible 状态
  //   迁移到新 groups（按 elementCode 匹配），保留用户的 disable 配置。
  if (force && oldGroupStates && oldGroupStates.size > 0) {
    sharedApplyGroupStates(groups, oldGroupStates)
  }

  // [E3 2026-08-02] 期间发生了更新的图表类型切换 → 放弃本次写入 (旧 groups 不覆盖新状态)
  if (genId !== null && genId !== _chartTypeGenId) return

  // [FIX 2026-07-29 v3] 跳过 watch 触发的循环刷新（写入前设标志，写入后清标志）
  // [T2 2026-08-02] try/finally 包裹: 之前靠 await nextTick 后复位, 若写入抛异常
  //   标志位永远停留 true, 导致后续 layoutControl 变更全部被跳过 (难排查的隐性失效)
  _skipLayoutControlWatch = true
  try {
    // 写入 chartConfig.layoutControl
    if (chartConfig.layoutControl) {
      chartConfig.layoutControl.groups = JSON.parse(JSON.stringify(groups))
      chartConfig.layoutControl.overallDirection = chartConfig.layoutControl.overallDirection || 'TB'
      chartConfig.layoutControl.engine = chartConfig.layoutControl.engine || 'elk'
      chartConfig.layoutControl.enabled = true
    }

    // 同步到 configStore（让 useDiagramData 内部 watch 看到一致状态）
    configStore.updateLayoutControlConfig(chartConfig.layoutControl)
  } finally {
    // 下一帧后清标志（让后续 watch 触发正常）
    await nextTick()
    _skipLayoutControlWatch = false
  }
}

/**
 * 判断 diagramData 是否满足 syncLayoutControlFromDiagramData 的前置条件
 * - BO 图：需要 nodes + domainProducts（buildBusinessObjectGroups 的输入）
 * - SM 图：[FIX v8] 需要 domainProducts（buildServiceModuleGroupsFromDomainProducts 的输入）
 *   之前需要 layoutControlConfig.groups（GroupModel.toMermaidConfig 输出），但该输出会过滤
 *   disabled 分组，不适合作为面板数据源，已改用 domainProducts 直接构建。
 */
function isDiagramReadyForSync() {
  const d = diagramData.value
  if (!d) return false
  if (chartConfig.chartType === 'businessObject') {
    return d.nodes && d.nodes.length > 0 && d.domainProducts && d.domainProducts.length > 0
  }
  if (chartConfig.chartType === 'serviceModule') {
    // [FIX v8] SM 图改用 domainProducts 作为数据源（不再依赖 GroupModel.toMermaidConfig 输出）
    const dps = d?.diagramData?.domainProducts || d?.domainProducts
    return !!(dps && dps.length > 0)
  }
  return false
}

// ============================================================
// 监听 versionId 变化 → 重新初始化
// ============================================================
watch(() => props.versionId, async (newVersionId) => {
  if (!newVersionId) return
  await initFromArchDataManager({
    versionId: Number(newVersionId),
    hierarchyFilter: props.hierarchyFilter || {},
    relationTypeFilter: [],
    relationIds: [],
    relationCategoryTypes: []
  })
  await generateDiagram()
  // [FIX 2026-07-29 v3] 版本切换也要重新预生成分组布局数据模型
  //   此时需要先把 chartConfig.layoutControl.groups 清空（让 syncLayoutControlFromDiagramData 真正写入新版本数据）
  if (chartConfig.layoutControl) {
    chartConfig.layoutControl.groups = []
  }
  await syncLayoutControlFromDiagramData()
})

// ============================================================
// [FIX 2026-07-28] 暴露给 LayoutControlPanel 的数据：
//   containers: 嵌套格式 [{ name, nodes: [{id, name, code}] }]，供拖拽到分组
//   domainProducts: 领域树 [{name, modules: [{name, submodules: [...}]}]，供"按领域自动分组"
//   links: 关系连线数组 [{source, target, ...}]，供 ELK 分离策略（有/无外部关系）
// 父级 ArchDataChartSwitcher 在 drawer 渲染时通过 ref 拿这些传给 LayoutControlPanel。
//
// [Phase 1 修复 2026-07-28] 修复数据缺失：
//   1. containers 保持原结构（嵌套大容器）
//   2. domainProducts 不再硬编码 []，从 diagramData.domainProducts 派生
//      业务对象图：直接取 diagramData.domainProducts（buildDiagramData 已填充）
//      服务模块图：同样取 diagramData.domainProducts
//   3. 新增 links：从 diagramData.links 派生（buildDiagramData 已填充）
//      LayoutControlPanel.handleBusinessObjectAutoGroup 会用 links 计算
//      nodesWithExternalLinks，从而产生 inner/boundary 子分组（ELK 分离策略）。
// ============================================================
// [Phase 1 修复 v3 2026-07-28] containers 从 domainProducts + nodes 反推嵌套结构
//   之前扁平虚拟大容器导致"未分类"问题。改用老路由契约：
//   [{ id: subDomainCode, name: subDomainName, domain, domainCode,
//      nodes: [boCode], serviceModuleMap: { smName: { code, nodes: [boCode] } } }]
const containers = computed(() => {
  const d = diagramData.value
  if (!d) return []

  // [FIX 2026-07-29] 服务模块图：直接用 diagramData.containers
  //   buildServiceModuleDiagramData 返回的 containers 是 subDomain 级容器，
  //   每个容器包含 nodes (服务模块数组 {id, name, code})。
  //   之前从 domainProducts 反推，但 buildServiceModuleDiagramData 不返回 domainProducts，
  //   导致服务模块图的布局设置抽屉拿不到待分配元素。
  if (chartConfig.chartType === 'serviceModule') {
    const smContainers = d.diagramData?.containers || d.containers || []
    if (smContainers.length > 0) {
      return smContainers.map(c => ({
        id: c.id,
        name: c.name,
        domain: c.domain,
        domainCode: c.domain,
        fullTitle: c.fullTitle || (c.domain ? `${c.domain} / ${c.name}` : c.name),
        nodes: (c.nodes || []).map(n => typeof n === 'string' ? n : (n.code || n.id || n.name)),
        serviceModuleMap: {}
      }))
    }
    // fallback: 服务模块图的 nodes 直接作为虚拟容器
    const smNodes = d.diagramData?.nodes || d.nodes || []
    if (smNodes.length > 0) {
      return [{
        id: 'virtual',
        name: '服务模块节点',
        nodes: smNodes.map(n => n.code || n.id || n.name)
      }]
    }
    return []
  }

  // 业务对象图：从 domainProducts 反推嵌套容器结构
  const diagramNodes = d.diagramData?.nodes || d.nodes || []
  const dps = d.diagramData?.domainProducts || d.domainProducts || []

  if (dps.length === 0) {
    return [{
      id: 'virtual',
      name: '业务对象节点',
      nodes: diagramNodes.map(n => n.code || n.id || n.name)
    }]
  }

  const result = []
  dps.forEach(domain => {
    const domainName = domain.name || '未分类'
    const domainCode = domain.code || domainName

    ;(domain.modules || []).forEach(subDomain => {
      const subDomainName = subDomain.name || '未分类'
      const subDomainCode = subDomain.code || subDomainName

      const boCodes = new Set()
      const serviceModuleMap = {}

      // 路径 A：从 subDomain.submodules[].businessObjects 收集
      if (subDomain.submodules?.length) {
        subDomain.submodules.forEach(sm => {
          const smName = sm.name || sm.code || '未分类'
          const smCode = sm.code || smName
          ;(sm.businessObjects || []).forEach(bo => {
            const boCode = typeof bo === 'string' ? bo : (bo.code || bo.name)
            if (boCode) {
              boCodes.add(boCode)
              if (!serviceModuleMap[smName]) {
                serviceModuleMap[smName] = { code: smCode, nodes: [] }
              }
              if (!serviceModuleMap[smName].nodes.includes(boCode)) {
                serviceModuleMap[smName].nodes.push(boCode)
              }
            }
          })
        })
      }

      // 路径 B（无条件执行，作为兜底补充）：按 nodes.domain/subDomain 匹配
      //   即便路径 A 已经收集了一些 bo，路径 B 会把缺失的节点补全
      //   并按节点自身的 serviceModuleName 填充 serviceModuleMap
      diagramNodes.forEach(n => {
        const nodeDomain = n.domain || ''
        const nodeSubDomain = n.subDomain || ''
        // 宽松匹配：BO 上 domain/subDomain 可能为空
        const matchDomain = !nodeDomain || nodeDomain === domainName
        const matchSubDomain = !nodeSubDomain || nodeSubDomain === subDomainName
        if (!matchDomain || !matchSubDomain) return
        const boCode = n.code || n.id || n.name
        if (!boCode) return
        boCodes.add(boCode)
        // 同时填充 serviceModuleMap（用节点自己的 serviceModuleName）
        const smName = n.serviceModuleName || n.serviceModule || subDomainName
        if (!serviceModuleMap[smName]) {
          serviceModuleMap[smName] = { code: smName, nodes: [] }
        }
        if (!serviceModuleMap[smName].nodes.includes(boCode)) {
          serviceModuleMap[smName].nodes.push(boCode)
        }
      })

      if (boCodes.size === 0) return

      // 路径 B fallback：把 boCodes 按节点自身的 serviceModule 分桶
      if (Object.keys(serviceModuleMap).length === 0) {
        diagramNodes.forEach(n => {
          const boCode = n.code || n.id || n.name
          if (!boCodes.has(boCode)) return
          const smName = n.serviceModuleName || n.serviceModule || subDomainName
          if (!serviceModuleMap[smName]) {
            serviceModuleMap[smName] = { code: smName, nodes: [] }
          }
          if (!serviceModuleMap[smName].nodes.includes(boCode)) {
            serviceModuleMap[smName].nodes.push(boCode)
          }
        })
      }

      result.push({
        id: subDomainCode,
        name: subDomainName,
        domain: domainName,
        domainCode: domainCode,
        nodes: Array.from(boCodes),
        serviceModuleMap
      })
    })
  })

  return result
})

// [Phase 1 修复 2026-07-28] domainProducts 从 diagramData 派生
//   diagramData 由 buildDiagramData 构造，已包含 domainProducts 字段
//   结构同老路由：[{ name, code, modules: [{ name, code, submodules: [{name, code, businessObjects: []}] }] }]
const domainProducts = computed(() => {
  const d = diagramData.value
  if (!d) return []
  // [FIX 2026-07-29] buildServiceModuleDiagramData 现在返回 domainProducts
  //   之前不返回，导致服务模块图 LayoutControlPanel 的"按领域自动分组"拿不到领域树
  return d.diagramData?.domainProducts || d.domainProducts || []
})

// [Phase 1 修复 2026-07-28] links 从 diagramData 派生
//   LayoutControlPanel.handleBusinessObjectAutoGroup 用 links 计算
//   nodesWithExternalLinks Set，产生 inner/boundary 子分组
const links = computed(() => {
  const d = diagramData.value
  if (!d) return []
  return d.diagramData?.links || d.links || []
})

// ============================================================
// [FIX 2026-07-28 画布缩小] 组件卸载时清理 ResizeObserver + 防抖定时器
//   避免组件销毁后 observer 仍在监听已移除的 DOM，触发异常或内存泄漏
// ============================================================
onBeforeUnmount(() => {
  // [O1/V2 2026-08-02] 恢复 diag hooks (模块单例, 避免影响老图表路由)
  diag.hooks.onRenderEnd = _prevDiagOnRenderEnd
  diag.hooks.onError = _prevDiagOnError
  _prevDiagOnRenderEnd = null
  _prevDiagOnError = null

  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (resizeTimer) {
    clearTimeout(resizeTimer)
    resizeTimer = null
  }
  // [E1 2026-08-02] 清理布局控制防抖定时器
  if (_layoutControlTimer) {
    clearTimeout(_layoutControlTimer)
    _layoutControlTimer = null
  }
})

defineExpose({
  containers,
  domainProducts,
  links,
  // [FIX 2026-07-29 v3] 暴露给外部调用（如测试或外部触发）
  //   把当前 diagramData.layoutControlConfig 同步到 chartConfig.layoutControl
  syncLayoutControlFromDiagramData
})

</script>

<style lang="scss" scoped>
.embedded-chart-view {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--color-bg-primary, #fff);
}

.embedded-chart-view__body {
  flex: 1;
  min-height: 600px;
  overflow: auto;
  position: relative;
}

.embedded-chart-view__loading,
.embedded-chart-view__error,
.embedded-chart-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--spacing-md);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.embedded-chart-view__canvas {
  width: 100%;
  height: 100%;
  position: relative;
}
</style>