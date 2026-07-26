<!--
  EmbeddedChartView - 嵌入式图表视图

  所属模块：嵌入式图表视图（Phase 4 升级版）
  主要功能：
    - 嵌入到架构数据管理页 detail 区
    - 顶部 ChartMiniToolbar 配置工具栏（高频配置）
    - 主体 mermaid 画布（通过 useReactiveRenderer 响应式渲染）
    - 数据预加载（通过 useChartPreview，0 网络延迟切换数据范围）
    - 节点点击 → emit

  契约：见 chart-data-flow-and-interaction-upgrade.md §5.10.3 ②

  Phase 4 升级内容：
    - 替换内部 loadChartData (fetchPreviewData) 为 useChartPreview
    - chartDataStore 预加载全量数据
    - scopeIds 变化时 filterFlattenData 前端过滤（0 网络延迟）
    - preload 失败时降级到懒加载（buildPreviewDataFromArchData with hierarchyFilter）

  Phase 5 升级内容：
    - 用 MermaidCanvas 组件替换 <pre> 临时渲染
    - MermaidCanvas 内部处理 mermaid.run() + 视口保持 + try-catch
    - 契约 5.10.4 ④: mermaid 库渲染失败 try-catch (phase=parse/render)
    - 契约 5.4.2: preserveViewport 跨渲染保留 scrollLeft/scrollTop + transform

  Props:
    - scopeIds: Layer 1 数据范围（只读）
    - versionId: 版本 ID
    - hierarchyFilter: 转换契约（scopeIds → fetchPreviewData 的 filter，懒加载降级时使用）
    - initialChartConfig: 可选初始配置

  Emits:
    - node-click: 节点点击
    - config-change: chartConfig 变化（可用于 URL 同步）
    - render-complete: 渲染完成
    - render-error: 渲染失败
-->
<template>
  <div class="embedded-chart-view">
    <!-- 顶部 mini 工具栏：高频配置 -->
    <ChartMiniToolbar
      v-model:chart-type="chartConfig.chartType"
      v-model:color-scheme="chartConfig.colorScheme"
      v-model:color-group-by="chartConfig.colorGroupBy"
      v-model:show-annotation-icon="chartConfig.showAnnotationIcon"
      @open-fullscreen="handleOpenFullscreen"
    />

    <!-- 主体：mermaid 画布 -->
    <div class="embedded-chart-view__body">
      <div v-if="dataLoading" class="embedded-chart-view__loading">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>加载架构数据中...</span>
        <span v-if="usingFallback" class="embedded-chart-view__hint">（预加载失败，使用懒加载降级）</span>
      </div>

      <div v-else-if="dataError" class="embedded-chart-view__error">
        <el-icon :size="32"><WarningFilled /></el-icon>
        <span>{{ dataError.message || '图表加载失败' }}</span>
        <el-button type="primary" size="small" @click="handleReload">重试</el-button>
      </div>

      <div v-else-if="renderError && !mermaidText" class="embedded-chart-view__error">
        <el-icon :size="32"><WarningFilled /></el-icon>
        <span>{{ renderError.message || '图表渲染失败' }}</span>
        <el-button type="primary" size="small" @click="handleForceRender">重试渲染</el-button>
      </div>

      <div v-else-if="!mermaidText" class="embedded-chart-view__empty">
        <el-icon :size="32"><DataLine /></el-icon>
        <span>暂无数据，请检查左侧对象范围选择</span>
      </div>

      <div v-else class="embedded-chart-view__canvas">
        <!-- Phase 5: 用 MermaidCanvas 组件替换 <pre> 临时渲染 -->
        <!-- 契约：MermaidCanvas 内部处理 mermaid.run() + 视口保持 + try-catch -->
        <MermaidCanvas
          :mermaid-text="mermaidText"
          :loading="renderLoading"
          :preserve-viewport="true"
          :chart-type="chartConfig.chartType"
          @node-click="handleNodeClick"
          @render-complete="handleRenderComplete"
          @render-error="handleRenderError"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
/**
 * EmbeddedChartView - 嵌入式图表视图（Phase 4 升级版）
 *
 * 数据流：
 *   1. props.versionId + props.scopeIds → useChartPreview
 *   2. useChartPreview 调用 chartDataStore.preload（带 TTL 缓存）
 *   3. preload 成功 → filterFlattenData(fullData, scopeIds) → rawData (ref)
 *      preload 失败 → fallbackToLazyLoad (用 hierarchyFilter 直接 fetchPreviewData)
 *   4. rawData + chartConfig → useReactiveRenderer → mermaidText (ref)
 *   5. 监听 mermaidText 变化 → emit('render-complete')
 *
 *   注: scopeIds 变化时只触发 filterFlattenData（前端计算），不触发网络请求
 */
import { reactive, watch, onMounted, toRef } from 'vue'
import { useRouter } from 'vue-router'
import { Loading, WarningFilled, DataLine } from '@element-plus/icons-vue'
import { useTabStore } from '@/stores/tabStore'
import { useChartArchDataStore } from '@/stores/chartArchDataStore'
import { useChartPreview } from '@/views/AADiagramApp/composables/useChartPreview'
import { useReactiveRenderer } from '@/views/AADiagramApp/composables/useReactiveRenderer'
import ChartMiniToolbar from './ChartMiniToolbar.vue'
import MermaidCanvas from './MermaidCanvas.vue'

const props = defineProps({
  // Layer 1: scopeIds（只读，不得反向写入）
  scopeIds: {
    type: Object,
    required: true
  },
  versionId: {
    type: [Number, String],
    required: true
  },
  // 转换契约（scopeIds → fetchPreviewData 的 filter）
  // 用途：preload 失败时降级到懒加载，需要 hierarchyFilter 调用 buildPreviewDataFromArchData
  hierarchyFilter: {
    type: Object,
    required: true
  },
  // 可选初始配置
  initialChartConfig: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits([
  'node-click',
  'config-change',
  'render-complete',
  'render-error'
])

const router = useRouter()
const tabStore = useTabStore()
const chartStore = useChartArchDataStore()

// ============================================================
// Layer 3: chartConfig（reactive，由 useReactiveRenderer 监听）
// ============================================================
const chartConfig = reactive({
  chartType: props.initialChartConfig.chartType || 'businessObject',
  colorScheme: props.initialChartConfig.colorScheme || 'default',
  colorGroupBy: props.initialChartConfig.colorGroupBy || 'domain',
  showAnnotationIcon: props.initialChartConfig.showAnnotationIcon || false,
  layoutEngine: props.initialChartConfig.layoutEngine || 'dagre',
  direction: props.initialChartConfig.direction || 'TD',
  centerScope: props.initialChartConfig.centerScope || []
})

// ============================================================
// useChartPreview：数据预加载 + 前端过滤
// 注：useChartPreview 内部 watch(versionId) 和 watch(scopeIds)
//     自动处理版本切换和范围切换
// ============================================================
const versionIdRef = toRef(props, 'versionId')
const scopeIdsRef = toRef(props, 'scopeIds')

const {
  rawData,
  loading: dataLoading,
  error: dataError,
  usingFallback,
  reload: reloadChartPreview,
  preloadData
} = useChartPreview(versionIdRef, scopeIdsRef)

// ============================================================
// useReactiveRenderer：响应式渲染引擎
// 注：rawData 由 useChartPreview 提供，useReactiveRenderer 内部 watch 自动触发渲染
// ============================================================
const {
  mermaidText,
  loading: renderLoading,
  error: renderError,
  forceRender,
  lastChangeType
} = useReactiveRenderer(rawData, chartConfig)

// ============================================================
// MermaidCanvas 事件透传
// 注: mermaidText 变化由 MermaidCanvas 内部 watch + mermaid.run() 处理
//     EmbeddedChartView 只透传事件给父组件
// ============================================================
function handleNodeClick(payload) {
  emit('node-click', payload)
}

function handleRenderComplete(payload) {
  // payload: { nodeCount, elapsedMs }
  emit('render-complete', {
    ...payload,
    mermaidLength: mermaidText.value?.length || 0,
    lastChangeType: lastChangeType.value
  })
}

function handleRenderError(payload) {
  // payload: { error, phase }
  // 注: phase='parse'/'render' 来自 MermaidCanvas 的 try-catch
  emit('render-error', { ...payload, source: 'mermaid-canvas' })
}

// ============================================================
// 监听 dataError → emit render-error (load 阶段)
// ============================================================
watch(dataError, (err) => {
  if (err) emit('render-error', { error: err, phase: 'load' })
})

// ============================================================
// 兼容 watch: renderError 来自 useReactiveRenderer
// 注: useReactiveRenderer 内部错误（如 buildGroupsFromFlatten 抛错）
//     不同于 MermaidCanvas 的 phase=parse/render
// ============================================================
watch(renderError, (err) => {
  if (err) emit('render-error', { error: err, phase: 'engine' })
})

// ============================================================
// 监听 chartConfig 变化 → emit config-change
// 注：useReactiveRenderer 已监听 chartConfig 用于渲染
//     这里仅用于 emit 给父组件（如 URL 同步）
// ============================================================
watch(chartConfig, () => {
  emit('config-change', { ...chartConfig })
})

onMounted(async () => {
  // 触发首次预加载（useChartPreview 内部 watch versionId 不会立即触发）
  await preloadData()
})

// ============================================================
// 手动触发重新加载（用于错误恢复）
// ============================================================
async function handleReload() {
  await reloadChartPreview()
}

// ============================================================
// 手动触发渲染（用于错误恢复）
// ============================================================
async function handleForceRender() {
  await forceRender('scope')
}

// ============================================================
// 跳转到全屏图表页（fallback）
// ============================================================
function handleOpenFullscreen() {
  // 把当前 chartConfig 持久化到 chartStore，跳转到 /archdata-chart
  if (rawData.value) {
    chartStore.setArchData({
      flattenData: rawData.value,
      chartConfig: { ...chartConfig }
    })
  }

  const chartTabId = '/archdata-chart'
  const existingTab = tabStore.tabs.find(t => t.id === chartTabId)
  if (existingTab) {
    existingTab.closable = true
    existingTab.pinned = false
    tabStore.switchTab(chartTabId)
  } else {
    tabStore.openTab({
      id: chartTabId,
      label: '架构数据图表',
      path: chartTabId,
      pinned: false
    })
  }
  router.push(chartTabId)
}
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
  min-height: 0;
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
  /* Phase 5: 把 padding/overflow 交给 MermaidCanvas 内部管理 */
}
</style>
