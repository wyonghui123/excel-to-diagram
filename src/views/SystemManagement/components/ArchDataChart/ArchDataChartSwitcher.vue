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
      v-if="context.versionId"
      :scope-ids="context.scopeIds"
      :version-id="context.versionId"
      :hierarchy-filter="context.chartData.hierarchyFilter"
      @node-click="handleNodeClick"
      @render-complete="handleRenderComplete"
      @render-error="handleRenderError"
    />
    <div v-else class="arch-data-chart-switcher__empty">
      <el-icon :size="48"><Connection /></el-icon>
      <span>请先选择产品和版本</span>
    </div>
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
 */
import { Connection } from '@element-plus/icons-vue'
import EmbeddedChartView from './EmbeddedChartView.vue'

const props = defineProps({
  // MultiObjectManagementPage 的 detailContent slot context
  // 结构见 chart-data-flow-and-interaction-upgrade.md §5.10.3 ①
  context: {
    type: Object,
    required: true
  }
})

const emit = defineEmits([
  'update:view-mode',  // 业务侧切换 viewMode（如 ESC 键返回 list）
  'node-click',        // 图表节点点击
  'render-complete',   // 渲染完成
  'render-error'       // 渲染失败
])

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
