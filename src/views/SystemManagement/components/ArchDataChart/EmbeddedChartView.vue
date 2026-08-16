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
    - 现在由 ArchDataManagement 持有，通过 props.chartConfig 传入
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
import { ElMessage } from 'element-plus'
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
import { buildServiceModuleGroupsFromDomainProducts, extractGroupStates as sharedExtractGroupStates, applyGroupStates as sharedApplyGroupStates, groupStateKey } from '@/services/groupModel/layoutPanelAdapter.js'
// [优化 2026-08-05] 布局面板编辑 → 渲染树的合并逻辑（纯函数, 可单测）
import { applyContainerMembership, applyGroupTitlesAndOrder } from '@/services/hierarchyTree/layoutMergeLogic.js'
// [SCOPE-DEFAULT 2026-08-08] 展开层级共享工具: 用户未显式设置时, 在渲染层按对象范围套用默认展开.
import { applyDefaultExpandByCount, expandGroupsToLevel } from '@/services/expandLevel.js'
// [ELK-GROUP 2026-08-12] 面板"无关系/有关系"系统自动分组注入渲染树 (驱动面板切换).
import { injectElkSubGroups } from './elkSubGroupsInjector.js'
import { useDebugMode } from '@/composables/useDebugMode.js'

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
  // [重构 2026-07-28] chartConfig 提升为父组件（ArchDataManagement）持有，
  // 业务侧通过 GlobalToolbar 的 chart-config slot 渲染 ChartMiniToolbar，
  // EmbeddedChartView 仅消费，确保 toolbar 与 chart 视图同步刷新。
  chartConfig: {
    type: Object,
    required: true
  },
  // [FIX 2026-08-13] 关系范围透传: 之前本组件硬编码 relationIds: []，导致
  //   "范围内关系不按关系范围选择展示" + "变更关系范围后刷新图表没变"。
  //   现从 ArchDataChartSwitcher 的 context.chartData 透传，与老图表页 (AADiagramApp) 同源。
  relationTypeFilter: {
    type: Array,
    default: () => []
  },
  relationIds: {
    type: Array,
    default: () => []
  },
  relationCategoryTypes: {
    type: Array,
    default: () => []
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
//   注意: 引用的是父组件 (ArchDataManagement) 的同一 reactive 对象。
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
const debugMode = useDebugMode()  // [PERF 2026-08-13] debugSteps 分步快照仅 ?mode=debug 时深拷贝

const {
  loading,
  error,
  diagramData,
  generateDiagram,
  initFromArchDataManager,
  updateRelationScope
} = useDiagramData()

// [E2E 2026-08-02] 暴露 generateDiagram — 供 E2E 触发"相同输入重渲染"验证 L5 增量跳过
//   (Task 8 spec 4.4: mermaidCode 与上次一致时跳过 mermaid.run 全量重绘)。
//   用法: window.__archPage.generateDiagram() → 新 diagramData 引用 → MermaidComponent
//   watch 触发 renderMermaid → code-diff 相同 → renderSkippedCount+1 / lastRender 不更新。
if (typeof window !== 'undefined') {
  window.__archPage = window.__archPage || {}
  window.__archPage.generateDiagram = generateDiagram
  // [FIX 2026-08-03] 暴露 reload (调 mermaidRef.forceRerender), 供 GlobalToolbar refresh 触发图表 reload.
  //   slot ref 不绑定到父组件, 改用 window 暴露更可靠.
  //   改用 forceRerender: 原 _renderNonce 方案 mermaid.run() 不带参数无法可靠把 <pre> 转 SVG (显示 text).
  /**
   * 触发图表 reload (强制 mermaid.run() 全量重绘 SVG).
   *
   * 调用路径: GlobalToolbar refresh → ArchDataManagement.handleToolbarAction('refresh')
   *   → window.__archPage.reload() → MermaidComponent.forceRerender()
   *   → 清空 lastRenderedCode (绕过 code-diff 跳过) + 设 forceAutoFit=true (重置 transform)
   *   → renderMermaid() → mermaid.run() 重绘 SVG.
   *
   * 失败处理: mermaid.run().catch() / nextTick try/catch → diag.recordError + endRender({error})
   *   → diag.hooks.onError → emit('render-error') → ArchDataManagement.handleChartRenderError
   *   → ElMessage.error toast (非静默失败).
   *
   * 不调 generateDiagram: 避免两次引用变化 (第一次 code-diff 跳过 + 第二次 isRendering 跳过).
   * 数据刷新由 MOMP.refresh → embeddedChartContext 变化 → watch generateDiagram 链路处理.
   *
   * [B6 2026-08-03] 这是 reload 的唯一入口 (slot ref 链路已移除, 见文件底部 defineExpose 注释).
   *
   * @returns {void}
   */
  window.__archPage.reload = () => {
    if (mermaidRef.value && typeof mermaidRef.value.forceRerender === 'function') {
      mermaidRef.value.forceRerender()
    }
  }
  // [E2E 2026-08-02] 暴露 diagramData 引用 (只读诊断: 统一管道输出节点结构 / domain / subDomain,
  //   以及颜色映射链路 buildObjectToModuleMap 的输入), chart_diag / probe 脚本读取验证。
  window.__archPage.diagramData = diagramData
  // [DBG 2026-08-10] 临时暴露 configStore 引用, 供诊断脚本检查别名/状态
  window.__archPage.storeProxy = configStore
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
      // [FIX 2026-08-03] 应用用户在 LayoutControlPanel 的 enabled/visible 配置到 unified.groups.
      //   deriveLayoutGroups (layoutGroupsDeriver.js L44) 硬编码 enabled=true/visible=true,
      //   不读 chartConfig.layoutControl.groups → 用户 disable "供应链云" 后图表无变化.
      //   修复: 用 extractGroupStates 从 chartConfig.layoutControl.groups 提取状态,
      //   applyGroupStates 应用到 unified.groups (按 elementCode 匹配, 与切换图表类型状态迁移同链路).
      //   深拷贝避免污染 diagramData (unified.groups 是 diagramData 的引用).
      // [FIX 2026-08-10] 折叠状态源必须以 configStore.layoutControlConfig 为权威:
      //   双击/右键菜单修改分组 collapsed 走 configStore.updateLayoutControlConfig(newConfig),
      //   该方法整体替换对象, 使 configStore.layoutControlConfig 与 chartConfig.layoutControl
      //   成为不同引用 (chartConfig 保留旧的、被替换前的 groups). 若此处从 chartConfig 取
      //   userStates, 会在"双击展开 → 切区分/不区分(触发本 computed 重算)"时读到旧引用中
      //   已折叠的 MM → sharedApplyGroupStates 把 MM 重新折叠 (用户反馈的 flaky 折叠 bug).
      //   改为优先从 configStore.layoutControlConfig 取 (同步更新, 权威), 兜底 chartConfig.
      const userStates = sharedExtractGroupStates(
        configStore.layoutControlConfig?.groups || chartConfig.layoutControl?.groups
      )
      const mergedGroups = JSON.parse(JSON.stringify(unified.groups))
      // [PERF 2026-08-13] debugSteps 分步快照仅 ?mode=debug 时深拷贝, 生产返回 null,
      //   避免每次 computed 重算 6 次 JSON 深拷贝 (~37ms, 大图 408 分组树).
      const snapDebug = (groups) => debugMode.isDebug ? deepCloneForDebug(groups) : null
      // [DEBUG 2026-08-05] 分步快照捕获, 供浏览器定位"哪一步合并出错":
      //   before(派生树) → afterStates(状态) → afterMembership(归属) → afterTitles(标题/顺序)
      //   替代旧的单点 debugLayout(只含最终 mergedGroups), 避免问题定位只能靠多轮试错.
      const debugSteps = {
        before: snapDebug(mergedGroups),
        afterStates: null,
        afterMembership: null,
        afterTitles: null
      }
      if (userStates.size > 0) {
        sharedApplyGroupStates(mergedGroups, userStates)
      }
      debugSteps.afterStates = snapDebug(mergedGroups)
      // [MOVE 2026-08-04] 用户把节点/容器拖拽到另一个分组下 → 基于新树结构生成图表。
      //   unified.groups 的容器归属来自投影容器树（派生），不反映用户在面板的拖拽移动，
      //   这里按容器 id/elementCode 重建每个分组的容器归属，追随面板树结构。
      applyContainerMembership(mergedGroups, chartConfig.layoutControl?.groups)
      debugSteps.afterMembership = snapDebug(mergedGroups)
      // [FIX 2026-08-04] 用户在布局面板的"重命名标题 / 拖拽排序"也需反映到图表。
      //   unified.groups 的 title/顺序来自 deriveLayoutGroups（投影容器树派生），
      //   不反映用户在面板的编辑。这里按 elementCode 覆盖标题并按面板顺序重排。
      applyGroupTitlesAndOrder(mergedGroups, chartConfig.layoutControl?.groups)
      debugSteps.afterTitles = snapDebug(mergedGroups)
      // [ELK-GROUP 2026-08-12] 把面板树中"无关系/有关系"系统自动分组注入到渲染树
      //   (deriveLayoutGroups 服务模块仅存扁平 directNodes, 不含 ELK 子分组 → 面板切换无效果).
      //   注入后: enabled+visible → 分组盒; enabled+hidden → 无边框分组(节点仍渲染); disabled → 打平.
      //   必须在此 (applyContainerMembership/applyGroupTitlesAndOrder 之后、展开层级之前) 执行,
      //   使 ELK 子分组携带面板最新 enabled/visible 状态参与渲染.
      injectElkSubGroups(mergedGroups, configStore.layoutControlConfig?.groups || chartConfig.layoutControl?.groups)
      debugSteps.afterElk = snapDebug(mergedGroups)
      // [SCOPE-DEFAULT 2026-08-08] 用户未显式选择过展开层级时, 在渲染层强制套用对象范围默认展开:
      //   - 对象范围内分组 → 折叠到服务模块(聚合节点)
      //   - 对象范围外分组 → 折叠到子领域
      //   规避 useDiagramData 生成时 centerScope 未就绪 / 异步时序导致的漏折叠(初始加载仍显示业务对象).
      //   仅当用户未干预(expandLevelUserSet=false)才套用, 用户显式选过则尊重用户选择, 不覆盖.
      //   注意: 需在 sharedApplyGroupStates 之后执行, 因为面板树 collapsed 来自用户折叠, 不得被覆盖.
      // [FIX 2026-08-09] 仅 centerScope 非空才套用默认折叠, 避免空范围误告警
      //   (applyDefaultExpandByScope 现会在谓词无命中时 console.warn).
      // [FIX 2026-08-09] 用户已手动调整过分组折叠/展开(双击/右键)时,
      //   尊重用户 per-group collapsed(已由上方 sharedApplyGroupStates 应用),
      //   不再套用范围默认展开/全局展开, 避免无条件覆盖用户操作导致图表无变化.
      if (configStore.groupManualSet) {
        // 不套用任何默认展开, 用户手动状态由 sharedApplyGroupStates 已写入 mergedGroups.
      } else if (!configStore.expandLevelUserSet) {
        // [DEFAULT-LEVEL 2026-08-12] 系统默认展开层级（按分组数量自适应）:
        //   >1 领域→领域; 否则 >1 子领域→子领域; 否则 >1 服务模块→服务模块; 否则→业务对象.
        //   取代原"对象范围默认折叠"(applyDefaultExpandByScope): 对任意范围都给出更自然的初始层级.
        //   就地应用 + 同步 store.expandLevel（不置 userSet, 用户后续显式选择仍可覆盖）.
        const defaultResult = applyDefaultExpandByCount(mergedGroups)
        if (configStore.expandLevel !== defaultResult.level) {
          configStore.setDefaultExpandLevel(defaultResult.level)
        }
      } else {
        // [SCOPE-DEFAULT 2026-08-08] 用户显式选择过展开层级(工具栏/图表设置):
        //   在渲染层按 store.expandLevel 就地应用展开, 确保用户选择必定生效.
        //   防御: 工具栏只改面板树 collapsed(经 userStates→mergedGroups 按 elementCode 匹配),
        //   若面板树与 unified 树 elementCode 不一致会导致状态丢失(仍显示业务对象), 此处兜底.
        //   注意: 全局展开层级选择会统一覆盖各分组 collapsed, 与该语义一致.
        expandGroupsToLevel(mergedGroups, configStore.expandLevel)
      }
      debugSteps.afterScopeExpand = snapDebug(mergedGroups)
      // [VIS-RESET 2026-08-14 简化] 重渲染即重置隐藏 (用户确认的设计意图):
      //   渲染层强制所有用户分组 visible=true。增量隐藏/显示由 MermaidComponent.updateVisibilityOnly
      //   基于 store visible 直接操作 SVG (不依赖渲染层 visible)，故任何全量重渲染
      //   (双击展开/折叠、右键、切换展开层级/方向/引擎、禁用分组等) 时，隐藏的分组一律重新显示，
      //   需用户再次手动隐藏。该设计消除了"隐藏聚合节点缺失/被 mermaid style 补建/取消隐藏无法恢复"
      //   等一整套跨重渲染保持隐藏的复杂 bug。
      //   ELK 系统自动分组 (无关系/有关系, _elkGroup=inner/boundary) visible=false 是
      //   "无边框但节点渲染"的布局语义，非用户隐藏，保留不动。
      const forceAllGroupsVisible = (groups) => {
        const walk = (list) => {
          ;(list || []).forEach(g => {
            if (!g || typeof g !== 'object') return
            const isSystemAuto = g._elkGroup === 'inner' || g._elkGroup === 'boundary'
            if (!isSystemAuto) g.visible = true
            walk(g.children)
            walk(g.containers)
          })
        }
        walk(groups)
      }
      forceAllGroupsVisible(mergedGroups)
      // [DEBUG 2026-08-04] 调试钩子, 供浏览器检查面板树与合并树各步骤结构
      if (typeof window !== 'undefined') {
        window.__archPage = window.__archPage || {}
        // [OBS 2026-08-08] 展开层级可观测摘要: 一行即可判断"展开到服务模块"是否生效.
        //   期望服务模块态: collapsedCount>0 且 collapsedSizes 覆盖 serviceModule 层级分组.
        window.__archPage.expandState = {
          expandLevel: configStore.expandLevel,
          expandLevelUserSet: configStore.expandLevelUserSet,
          scopeBoCount: (configStore.centerScope || []).length,
          collapsedCount: countCollapsed(mergedGroups),
          collapsedSizes: countCollapsedByLevel(mergedGroups)
        }
        window.__archPage.debugLayout = {
          panelGroups: chartConfig.layoutControl?.groups,
          ...debugSteps,
          chartType: chartConfig.chartType,
          disabledBoCodes: collectDisabledBoCodes(chartConfig.layoutControl?.groups)
        }
      }
      // [FOLD 2026-08-05] FR-005: 收集"被禁用的 BO 叶"的业务编码集合.
      //   mergedGroups 里 BO 叶是 directNodes (code), 无独立 enabled 状态; 而用户在面板
      //   禁用的是容器表示 (isVirtual=true 的容器, nodes=[code]). 这里从面板树收集被禁用
      //   BO 叶的 code, 透传给渲染层, 供 useBusinessObjectSyntax 隐藏对应节点并丢弃其连线.
      const disabledBoCodes = collectDisabledBoCodes(chartConfig.layoutControl?.groups)
      return {
        enabled: true,
        layoutType: 'default',
        // [SIMPLE 2026-08-15] 引擎统一以 chartConfig.layoutEngine 为权威 (与 MermaidComponent
        //   :layout-engine 同源), 不再优先 layoutControl.engine — 避免 layoutControl 被侧边栏等
        //   Object.assign 重建时 engine 回退默认(直线)而 layoutEngine 仍为曲线 → 配置/图表失步.
        layoutEngine: chartConfig.layoutEngine || 'elk',
        overallDirection: chartConfig.layoutControl?.overallDirection || unified.overallDirection || 'TB',
        preserveOrder: chartConfig.layoutControl?.preserveOrder ?? true,
        disabledBoCodes,
        groups: mergedGroups.map(g => normalizeGroupForRendering(g))
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
        layoutEngine: chartConfig.layoutEngine || 'elk',
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
    layoutEngine: chartConfig.layoutEngine || 'elk',
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

// [DEBUG 2026-08-05] 深拷贝分组树快照, 供 debugLayout 分步对比（不污染 diagramData 引用）。
function deepCloneForDebug(groups) {
  return JSON.parse(JSON.stringify(groups))
}

// [FOLD 2026-08-05] FR-005: 从面板分组树收集"被禁用的 BO 叶"的业务编码集合.
//   BO 叶在面板树中表示为 isVirtual=true 的容器 (nodes=[业务编码]); 用户禁用 (enabled=false)
//   后, 渲染层无法从 mergedGroups (BO 叶是 directNodes) 感知, 故在此显式收集并透传.
function collectDisabledBoCodes(groups) {
  const codes = []
  if (!groups) return codes
  const addCode = (c) => { if (c != null && String(c).trim()) codes.push(String(c)) }
  function walk(items) {
    if (!items) return
    for (const it of items) {
      if (!it) continue
      if (it.containers && it.containers.length) {
        for (const c of it.containers) {
          if (c && typeof c === 'object' && c.isVirtual === true && c.enabled === false) {
            if (c.nodes && c.nodes.length) c.nodes.forEach(addCode)
            if (c.elementRef?.code != null) addCode(c.elementRef.code)
            if (c.elementCode != null) addCode(c.elementCode)
          }
        }
      }
      walk(it.children)
      walk(it.containers)
    }
  }
  walk(groups)
  return codes
}

// [OBS 2026-08-08] 统计渲染树 collapsed=true 的分组总数 (供展开层级可观测).
function countCollapsed(groups) {
  let n = 0
  function walk(list) {
    if (!Array.isArray(list)) return
    for (const g of list) {
      if (!g) continue
      if (g.collapsed === true) n++
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(groups)
  return n
}

// [OBS 2026-08-08] 按 groupType 汇总各层级 collapsed 分组数.
//   期望"展开到服务模块": { serviceModule: >0, custom: >0 } (BO 叶容器折叠), domain/subDomain=0.
function countCollapsedByLevel(groups) {
  const out = { domain: 0, subDomain: 0, serviceModule: 0, other: 0 }
  function walk(list) {
    if (!Array.isArray(list)) return
    for (const g of list) {
      if (!g) continue
      if (g.collapsed === true) {
        const t = g.groupType ? String(g.groupType).toLowerCase() : ''
        if (t === 'domain') out.domain++
        else if (t === 'subdomain') out.subDomain++
        else if (t === 'servicemodule') out.serviceModule++
        else out.other++
      }
      walk(g.children)
      walk(g.containers)
    }
  }
  walk(groups)
  return out
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

// [FIX 2026-08-11 反向同步] 监听 configStore.centerScopeHighlight → 写回 chartConfig.
//   根因: 右键"颜色设置"子菜单切换"区分/不区分对象范围"走 configStore.updateCenterScopeHighlight,
//   只更新 store, 不写 chartConfig. 而图例 updateColorLegend 读 annotationConfig
//   (= chartConfig.centerScopeHighlight), toolbar 下拉也读 chartConfig → 两者都停留在旧值,
//   表现为"切换后节点变色但图例/下拉不变". 反向同步保证 chartConfig 始终反映 store
//   (权威源), 图例与工具栏均正确. 与上方 chartConfig→store 同步互为逆, 因同值写入
//   各自 oldVal===newVal 短路, 不会死循环.
watch(() => configStore.centerScopeHighlight, (newVal, oldVal) => {
  if (newVal === oldVal) return
  if (chartConfig.centerScopeHighlight !== newVal) {
    chartConfig.centerScopeHighlight = newVal
  }
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
//   跳过 watch 触发的处理，避免循环刷新。
let _skipLayoutControlWatch = false
// [E1 2026-08-02] 防抖定时器: 布局面板拖拽分组时 groups 深层连续变化,
//   store 写入合并为拖拽停顿后的单次调用。
// [P0 2026-08-05] 移除 generateDiagram —— 布局变更不改变 nodes/links 数据。
//   布局变更已被两条更轻的链路消费:
//     1) 下方 layoutControlConfig computed 响应式读 chartConfig.layoutControl → 新 prop
//        → MermaidComponent watch(layoutControlConfig) → renderMermaid (仅重排)。
//     2) 若分布局只改颜色派生字段, 走 diagramData watch 的 updateColorsOnly 增量。
//   之前的 generateDiagram 会重新 fetch + 重建 diagramData + 再触发全量渲染, 纯属冗余。
//   这里仅保留 store 同步, 供需要消费 configStore.layoutControlConfig 的组件保持一致性。
let _layoutControlTimer = null
watch(
  () => chartConfig.layoutControl,
  (newLayout) => {
    if (!newLayout) return
    if (_skipLayoutControlWatch) return
    // [E1 2026-08-02] 250ms 防抖合并连续拖拽 (仅合并 store 写入)
    clearTimeout(_layoutControlTimer)
    _layoutControlTimer = setTimeout(() => {
      configStore.updateLayoutControlConfig(newLayout)
      // [T3 2026-08-02] 触发来源标注 — chart_diag / window.__archPage.mermaid.stepMeta 可读
      diag.recordStepMeta('layoutControlUpdate', { source: 'layoutControl-debounced', at: Date.now() })
    }, 250)
  },
  { deep: true }
)

// ============================================================
// [LEGEND-SYNC 2026-08-07] 图例点击隐藏 → store 变化 → 反向同步回 chartConfig.layoutControl。
//   问题1根因: 图表设置面板 (LayoutControlPanel) 绑定的是 chartConfig.layoutControl
//   (RelationScopeTree.vue :model-value="injectedChartConfig.layoutControl"),
//   而图例点击 (MermaidComponent.handleToggleGroupVisible) 只更新 configStore.layoutControlConfig。
//   若不反向同步, 面板不同步 (图表已隐藏但面板眼睛图标不变)。
//   方案: 仅把 store 分组中的 visible 状态按 elementCode/id 写回 chartConfig.layoutControl,
//   不覆盖结构 (enabled/containers/children 以面板为权威)。仅当值不同才赋值 → 无无限循环。
// ============================================================
// [FIX 2026-08-12 键碰撞] 匹配键升级为复合键 elementCode::groupType (复用 layoutPanelAdapter.groupStateKey):
//   SM/ITTF 等编码在"子领域"与"服务模块"两个层级重复出现
//   (子领域"销售"=SM 与 服务模块"服务管理"=SM; 子领域"内部交易"=ITTF 与
//   服务模块"内部交易"=ITTF). 旧实现仅用 elementCode 作 Map 键 → srcMap['SM'] 被
//   服务模块覆盖 → 子领域 expanded/collapsed 状态同步失败 → 双击展开子领域下的
//   服务模块后, 面板树中的子领域保持陈旧折叠值, 250ms 后经 layoutControl deep watch
//   写回 store → "内部交易整体折叠". collect 与 apply 必须共用同一键函数。
// ============================================================
function syncVisibilityToChartConfig(srcGroups, dstGroups) {
  if (!Array.isArray(srcGroups) || !Array.isArray(dstGroups)) return
  const srcMap = new Map()
  const collect = (list) => {
    ;(list || []).forEach(g => {
      if (!g || typeof g !== 'object') return
      const key = groupStateKey(g)
      if (key) srcMap.set(key, g)
      collect(g.children)
      collect((g.containers || []).filter(c => c && typeof c === 'object'))
    })
  }
  collect(srcGroups)
  let syncedCount = 0
  const apply = (list) => {
    ;(list || []).forEach(g => {
      if (!g || typeof g !== 'object') return
      const key = groupStateKey(g)
      const src = key ? srcMap.get(key) : null
      if (src && src.visible !== g.visible) {
        g.visible = src.visible
      }
      // [CTX 2026-08-07] 同步折叠状态: 右键菜单"折叠/展开"修改了 configStore 中分组的 collapsed,
      //   必须同步回 chartConfig.layoutControl, 否则 layoutControlConfig computed 读不到变化,
      //   MermaidComponent 不会重渲染.
      if (src && src.collapsed !== undefined && src.collapsed !== g.collapsed) {
        console.log('[SYNC] syncVisibilityToChartConfig: syncing collapsed for ' + (g.title || g.elementCode || g.id) + ' from ' + g.collapsed + ' to ' + src.collapsed)
        g.collapsed = src.collapsed
        syncedCount++
      }
      apply(g.children)
      apply((g.containers || []).filter(c => c && typeof c === 'object'))
    })
  }
  apply(dstGroups)
}
let _syncingStoreToChart = false
watch(
  () => configStore.layoutControlConfig,
  (newCfg) => {
    if (!newCfg || !chartConfig.layoutControl) return
    if (_syncingStoreToChart) return
    _syncingStoreToChart = true
    try {
      syncVisibilityToChartConfig(newCfg.groups, chartConfig.layoutControl.groups)
    } finally {
      _syncingStoreToChart = false
    }
  },
  { deep: true }
)

// ============================================================
// [布局设置 sidebar 整合] 将 containers/domainProducts/links 同步到 store
//   RelationScopeTree 第 4 个 CollapsiblePanel 从 store 读取后传给 LayoutControlPanel
//   注意: watch 必须放在 containers/domainProducts/links 声明之后 (TDZ),
//         见下方 L976 附近的 watch 块。
// ============================================================

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
    // [SIMPLE 2026-08-15] 用户手动切回 dagre → 重置自动回退标志, 允许新一轮回退尝试
    if (newEngine === 'dagre') {
      _dagreFallbackDone = false
    }
    diag.recordStepMeta('generateDiagram', { source: 'layoutEngine', at: Date.now() })
    if (diagramData.value) generateDiagram()
  }
)

// ============================================================
// [重构 2026-07-28] handle* 函数已移除：
//   ChartMiniToolbar 的 emit('update:chartType' 等) 现在由父组件 ArchDataManagement 接收，
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
// [SIMPLE 2026-08-15] dagre→ELK 自动回退标志: 仅回退一次, 用户手动切回曲线时重置
let _dagreFallbackDone = false

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
  // [SIMPLE 2026-08-15] dagre(曲线) 渲染失败 → 自动回退 ELK(直线) 并同步面板.
  //   根因: mermaid dagre 在元素过多时无法完成布局 (报 text syntax error), ELK 可处理.
  //   仅在 dagre 且疑似规模类错误时回退一次 (防循环), 用户手动切回曲线时重置.
  const errMsg = String(entry?.message || entry || '')
  const isLikelyScaleError = /text|size|syntax|maximum|edge|too (many|large)|layered/i.test(errMsg)
  if (chartConfig.layoutEngine === 'dagre' && !_dagreFallbackDone && isLikelyScaleError) {
    _dagreFallbackDone = true
    chartConfig.layoutEngine = 'elk'
    chartConfig.layoutControl.engine = 'elk'
    ElMessage.warning('曲线(Dagre)布局在元素过多时无法渲染，已自动切换为直线(ELK)布局。')
    return
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

  // 把 scopeIds 转换成 hierarchyFilter + relationTypeFilter/relationIds（复用老链路）
  // [FIX 2026-08-13] 关系范围不再硬编码为空，改从 props 透传。
  await initFromArchDataManager(buildArchData())
  // [PERF 2026-08-13] 记录首次 init 的版本, 供后续 watch 区分"版本变化(完整 init)"与"关系变化(轻量 update)"。
  _lastVersionId = props.versionId
  // [PERF 2026-08-14] 记录首次 init 的对象范围 (hierarchyFilter), 供 watch 区分"对象范围变化(完整 init)"。
  _lastHierarchyFilter = JSON.stringify(props.hierarchyFilter || {})

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
  console.log('[DBG-syncLayout] called force=' + force + ' genId=' + genId + ' chartType=' + chartConfig.chartType + ' stack=' + new Error().stack.split('\n').slice(1,4).join(' < ').slice(0,200))
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
// 初始化数据源：从 props 组装 archData（versionId + 对象范围 + 关系范围）
// [FIX 2026-08-13] 关系范围字段不再硬编码为空，改从 props 透传。
// ============================================================
function buildArchData() {
  return {
    versionId: Number(props.versionId),
    hierarchyFilter: props.hierarchyFilter || {},
    relationTypeFilter: props.relationTypeFilter || [],
    relationIds: props.relationIds || [],
    relationCategoryTypes: props.relationCategoryTypes || []
  }
}

// 重新初始化图表数据（完整: 版本/对象范围变化时用）
async function reinitChart() {
  await initFromArchDataManager(buildArchData())
  await generateDiagram()
  // [FIX 2026-07-29 v3] 重新预生成分组布局数据模型
  //   此时需要先把 chartConfig.layoutControl.groups 清空（让 syncLayoutControlFromDiagramData 真正写入新数据）
  if (chartConfig.layoutControl) {
    chartConfig.layoutControl.groups = []
  }
  await syncLayoutControlFromDiagramData()
}

// 关系范围变更的轻量刷新（跳过 architecture/preview 重拉）
async function reapplyRelationScope() {
  // [LOG 2026-08-13] 关键日志: 关系范围变更触发轻量刷新.
  console.log('[reapplyRelationScope] 关系范围变更触发轻量刷新: relationIds=' + JSON.stringify(props.relationIds || []))
  await updateRelationScope(buildArchData())
  await generateDiagram()
  if (chartConfig.layoutControl) {
    chartConfig.layoutControl.groups = []
  }
  await syncLayoutControlFromDiagramData()
}

// ============================================================
// 监听数据源 props 变化（版本 + 关系范围）→ 防抖刷新
// [FIX 2026-08-13] 之前只监听 versionId, 关系范围变化不会触发重初始化。
// [PERF 2026-08-13] 用户多选关系范围时, 每次勾选都 emit scope-change → 连续触发刷新,
//   用防抖 (400ms) 合并连续变更, 只对最后一次执行刷新; 版本变化走完整 init,
//   仅关系变化走轻量 update (跳过 preview 重拉, 提升刷新性能)。
// [PERF 2026-08-14] dataSourceKey 纳入 hierarchyFilter (对象范围):
//   之前不含 hierarchyFilter → 对象范围变化不触发刷新 / 或走 reapplyRelationScope 用
//   旧 hierarchyFilter 的 basePreviewData (preview 在后端按 hierarchyFilter 过滤) →
//   图表显示旧对象范围的数据 (真实缺陷)。现纳入并在下方区分:
//   - version / hierarchyFilter 变化 → reinitChart (完整 init, 用新 filter 重拉 preview)
//   - 仅 relation 字段变化 → reapplyRelationScope (轻量, 跳过 preview 重拉)
//   复用本 watch 的 400ms 防抖 (连续勾选对象/关系范围只刷新最后一次)。
// ============================================================
const dataSourceKey = computed(() => JSON.stringify({
  versionId: props.versionId,
  hierarchyFilter: props.hierarchyFilter || {},
  relationIds: props.relationIds || [],
  relationTypeFilter: props.relationTypeFilter || [],
  relationCategoryTypes: props.relationCategoryTypes || []
}))

let _lastVersionId = null
let _lastHierarchyFilter = null
let _dataSourceDebounceTimer = null
watch(dataSourceKey, () => {
  if (!props.versionId) return
  clearTimeout(_dataSourceDebounceTimer)
  _dataSourceDebounceTimer = setTimeout(async () => {
    const versionChanged = _lastVersionId !== null && props.versionId !== _lastVersionId
    const filterKey = JSON.stringify(props.hierarchyFilter || {})
    const filterChanged = _lastHierarchyFilter !== null && filterKey !== _lastHierarchyFilter
    _lastVersionId = props.versionId
    _lastHierarchyFilter = filterKey
    if (versionChanged || filterChanged) {
      await reinitChart()
    } else {
      await reapplyRelationScope()
    }
  }, 400)
})

// ============================================================
// [FIX 2026-07-28] 暴露给 LayoutControlPanel 的数据：
//   containers: 嵌套格式 [{ name, nodes: [{id, name, code}] }]，供拖拽到分组
//   domainProducts: 领域树 [{name, modules: [{name, submodules: [...}]}]，供"按领域自动分组"
//   links: 关系连线数组 [{source, target, ...}]，供 ELK 分离策略（有/无关系）
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
      nodes: diagramNodes.map(n => n.code || n.id || n.name),
      nodeNames: Object.fromEntries(
        diagramNodes.map(n => [n.code || n.id || n.name, n.name || n.code || n.id])
      )
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
        nodeNames: Object.fromEntries(
          Array.from(boCodes).map(code => {
            const node = diagramNodes.find(n => (n.code || n.id) === code)
            return [code, node?.name || code]
          })
        ),
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
// [布局设置 sidebar 整合] 将 containers/domainProducts/links 同步到 store
//   RelationScopeTree 第 4 个 CollapsiblePanel 从 store 读取后传给 LayoutControlPanel
//   immediate: true 确保首次渲染即写入 (chart 视图打开时 panel 立即可用)
//   [FIX 2026-08-04] 移到此位置 (在 containers/domainProducts/links 声明之后),
//                    避免TDZ ReferenceError: Cannot access 'containers' before initialization.
// ============================================================
watch(
  [containers, domainProducts, links],
  ([c, dp, l]) => {
    configStore.updateChartDataSnapshot({
      containers: c,
      domainProducts: dp,
      links: l,
      // [FIX 2026-08-05] 透传与图表同源的分组色映射 (colorize 输出), 供色点取默认色
      groupColorMap: diagramData.value?.diagramData?.groupColorMap || diagramData.value?.groupColorMap || {}
    })
  },
  { immediate: true }
)

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
  // [PERF 2026-08-13] 清理关系范围防抖定时器
  if (_dataSourceDebounceTimer) {
    clearTimeout(_dataSourceDebounceTimer)
    _dataSourceDebounceTimer = null
  }
  // [E1 2026-08-02] 清理布局控制防抖定时器
if (_layoutControlTimer) {
  clearTimeout(_layoutControlTimer)
  _layoutControlTimer = null
}
})

// [FIX 2026-08-03] GlobalToolbar refresh 触发图表 reload:
//   原 refresh 只调 MOMP.refresh (刷新元数据列表), 图表 reload 链路断裂.
//   现 expose reload 方法: 调 MermaidComponent.forceRerender (清空 lastRenderedCode 让
//   code-diff 不命中 → mermaid.run() 全量重绘), 用户视觉上看到 reload.
//   不用 _renderNonce + watch: mermaidCode 相同时 mermaid.run() 不带参数无法可靠转换 <pre> (显示 text).
//   不调 generateDiagram: 避免两次引用变化 (第一次 code-diff 跳过 + 第二次 isRendering 跳过).
//   数据刷新由 MOMP.refresh → embeddedChartContext 变化 → watch generateDiagram 链路处理.
//
// [B6 2026-08-03] reload 唯一入口统一为 window.__archPage.reload (见上方 onMounted 内赋值).
//   原本同时存在 EmbeddedChartView.defineExpose.reload + ArchDataChartSwitcher.defineExpose.reload
//   两条 slot ref 链路, 但 slot ref 不绑定到父组件 (ArchDataManagement 无法稳定拿到实例),
//   实际调用方 (ArchDataManagement.handleToolbarAction('refresh')) 走 window 暴露.
//   现移除 slot ref 链路, 仅保留 window.__archPage.reload, 避免"两条路径谁生效"歧义.
//   defineExpose 仍保留 containers/domainProducts/links/syncLayoutControlFromDiagramData (LayoutControlPanel 用).

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