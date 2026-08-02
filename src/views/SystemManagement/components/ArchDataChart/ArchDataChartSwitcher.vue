<!--
  ArchDataChartSwitcher - 架构数据图表视图切换器

  所属模块：嵌入式图表视图（Phase 2）
  主要功能：
    - 接收 MultiObjectManagementPage 的 detailContent slot context
    - 渲染 EmbeddedChartView（list 视图由 MultiObjectManagementPage 内部处理，本组件仅渲染 chart 部分）
    - 转发节点点击事件

  契约：见 chart-data-flow-and-interaction-upgrade.md §5.10.3 ①

  设计原则（§5.0.2 ⑤ 通用组件零侵入）：
    - 本组件是"业务组件"，承担视图切换的复杂度
    - MultiObjectManagementPage 通用组件仅提供 detailContent slot，不知道图表视图的具体实现
    - 业务方（RelationshipManagement.vue）通过 detailContent slot 注入本组件

  Props:
    - context: MultiObjectManagementPage 提供的 slot scope 对象

  Emits:
    - update:view-mode: 业务侧切换 viewMode 时触发（本组件不直接修改 context，由父组件处理）
    - node-click: 图表节点点击
-->
<template>
  <div class="arch-data-chart-switcher">
    <EmbeddedChartView
      ref="embeddedChartRef"
      v-if="context.versionId"
      :scope-ids="context.scopeIds"
      :version-id="context.versionId"
      :hierarchy-filter="context.chartData.hierarchyFilter"
      :chart-config="chartConfig"
      @node-click="handleNodeClick"
      @render-complete="handleRenderComplete"
      @render-error="handleRenderError"
    />
    <div v-else class="arch-data-chart-switcher__empty">
      <el-icon :size="48"><Connection /></el-icon>
      <span>请先选择产品和版本</span>
    </div>

    <!-- [FIX 2026-07-31] 布局设置抽屉：回溯修复丢失的 LayoutControlPanel 功能
         之前 EmbeddedChartView 注释说"布局抽屉已上移到 ArchDataChartSwitcher"，
         但本组件从未实际渲染抽屉 → 功能丢失。现在补回。 -->
    <el-drawer
      v-model="drawerVisible"
      title="布局设置"
      direction="rtl"
      size="380px"
      :destroy-on-close="false"
      :append-to-body="true"
    >
      <LayoutControlPanel
        v-if="embeddedChartRef && drawerVisible"
        :containers="embeddedChartRef.containers"
        :domain-products="embeddedChartRef.domainProducts"
        :links="embeddedChartRef.links"
        :chart-type="chartConfig.chartType"
        :model-value="chartConfig.layoutControl"
        @update:model-value="(v) => Object.assign(chartConfig.layoutControl, v)"
      />
    </el-drawer>
  </div>
</template>

<script setup>
/**
 * ArchDataChartSwitcher - 业务侧视图切换器
 *
 * 注：list 视图由 MultiObjectManagementPage 内部渲染（v-show 控制），
 *     本组件仅渲染 chart 部分（EmbeddedChartView）。
 *
 * 设计理由（v2.3 §5.0.2 ⑤）：
 *   - list 视图是通用功能，由通用组件 MultiObjectManagementPage 处理
 *   - chart 视图是业务功能，由业务组件 ArchDataChartSwitcher 处理
 *   - 这样通用组件不需要知道图表视图的具体实现，保持零侵入
 *
 * [A8 2026-07-30] EmbeddedChartView 改为 defineAsyncComponent 懒加载：
 *   EmbeddedChartView 的 import 链会触发 chartDataStore / useReactiveRenderer 等模块 evaluate，
 *   这些模块当前还有未导出的引用（如 buildGroupsFromFlatten、previewDataToFlatten），
 *   在路由初始化时若被同步导入会 SyntaxError 阻止页面加载。
 *   改为懒加载后仅在 viewMode='chart' 时才评估这些 import，绕过初始化错误。
 *
 * [FIX 2026-07-30 restore] chartConfig 提升为本组件持有，EmbeddedChartView 通过 prop 消费。
 *   之前 EmbeddedChartView 内部 reactive 创建 chartConfig（与 GlobalToolbar 状态分散），
 *   现统一在本组件持有，确保 toolbar（chart-config slot）与 chart 视图共享单一数据源。
 */
import { defineAsyncComponent, reactive, ref, computed } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import LayoutControlPanel from '@/views/AADiagramApp/components/LayoutControlPanel.vue'
import { createDefaultChartConfig } from './chartConfigDefaults.js'

const EmbeddedChartView = defineAsyncComponent(() =>
  import('./EmbeddedChartView.vue').catch(err => {
    console.error('[ArchDataChartSwitcher] failed to load EmbeddedChartView:', err)
    return import('./EmbeddedChartView.vue')
  })
)

const props = defineProps({
  // MultiObjectManagementPage 的 detailContent slot context
  // 结构见 chart-data-flow-and-interaction-upgrade.md §5.10.3 ①
  context: {
    type: Object,
    required: true
  },
  // [FIX 2026-07-30 v2] chartConfig 由父组件（RelationshipManagement）持有，
  // 让 GlobalToolbar（chart-config slot）和 EmbeddedChartView 共享同一份配置。
  // 本组件只是透传者，不创建新 chartConfig。
  // 兜底：当父组件没传时仍能用本地默认（向后兼容旧用法）
  chartConfig: {
    type: Object,
    default: null
  },
  // [FIX 2026-07-31] 布局设置抽屉可见性：由 ChartMiniToolbar 的"布局设置"按钮控制
  layoutDrawerVisible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits([
  'update:view-mode',          // 业务侧切换 viewMode（如 ESC 键返回 list）
  'node-click',                // 图表节点点击
  'render-complete',           // 渲染完成
  'render-error',              // 渲染失败
  'update:layoutDrawerVisible' // 布局抽屉可见性变化
])

// [FIX 2026-07-31] 布局抽屉 v-model 代理
const drawerVisible = computed({
  get: () => props.layoutDrawerVisible,
  set: (v) => emit('update:layoutDrawerVisible', v)
})

// EmbeddedChartView 组件实例引用（用于获取 containers/domainProducts/links）
const embeddedChartRef = ref(null)

// [FIX 2026-07-30 v2] chartConfig 直接用 props.chartConfig（父组件持有）。
// 兜底：若父组件没传，本地 reactive 默认值（向后兼容）
// [T1 2026-08-02] 默认值统一走 chartConfigDefaults.js 工厂（原 _localDefaultChartConfig
//   结构较旧: 缺 centerScopeHighlight/preserveOrder, 有废弃的 annotationConfig 字段）
const _localDefaultChartConfig = reactive(createDefaultChartConfig())
const chartConfig = props.chartConfig || _localDefaultChartConfig


function handleNodeClick(payload) {
  emit('node-click', payload)
}

function handleRenderComplete(payload) {
  emit('render-complete', payload)
}

function handleRenderError(payload) {
  emit('render-error', payload)
}
</script>

<style lang="scss" scoped>
.arch-data-chart-switcher {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.arch-data-chart-switcher__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--spacing-sm);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}
</style>
