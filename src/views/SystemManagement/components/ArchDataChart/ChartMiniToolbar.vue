<!--
  ChartMiniToolbar - 图表顶部高频配置工具栏

  所属模块：嵌入式图表视图（Phase 2）
  主要功能：
    - 图表类型切换（业务对象图 / 服务模块图）
    - 颜色方案选择
    - 颜色分组维度选择（领域 / 子领域 / 服务模块）
    - 备注图标显示开关
    - 全屏按钮（跳转到 /archdata-chart）

  契约：见 chart-data-flow-and-interaction-upgrade.md §5.10.3 ③

  Phase 2 实现：
    - 简化版: 4 个 el-select 下拉 + 1 个全屏按钮
    - v-model 双向绑定 chartConfig 各字段
  Phase 3 升级计划：
    - 增加 layoutEngine / direction / centerScope 配置
    - 增加"配色预览"小色块
-->
<template>
  <div class="chart-mini-toolbar">
    <!-- 图表类型 -->
    <el-select
      :model-value="chartType"
      size="small"
      class="cmt-select"
      @update:model-value="handleUpdate('chart-type', $event)"
    >
      <template #prefix>
        <span class="cmt-label">图表类型</span>
      </template>
      <el-option label="业务对象图" value="businessObject" />
      <el-option label="服务模块图" value="serviceModule" />
    </el-select>

    <!-- 颜色分组维度 -->
    <el-select
      :model-value="colorGroupBy"
      size="small"
      class="cmt-select"
      @update:model-value="handleUpdate('color-group-by', $event)"
    >
      <template #prefix>
        <span class="cmt-label">颜色分组</span>
      </template>
      <el-option label="按领域" value="domain" />
      <el-option label="按子领域" value="sub_domain" />
      <el-option label="按服务模块" value="service_module" />
    </el-select>

    <!-- 颜色方案 -->
    <el-select
      :model-value="colorScheme"
      size="small"
      class="cmt-select cmt-select--short"
      @update:model-value="handleUpdate('color-scheme', $event)"
    >
      <template #prefix>
        <span class="cmt-label">配色</span>
      </template>
      <el-option label="默认" value="default" />
      <el-option label="高对比" value="high-contrast" />
      <el-option label="柔和" value="soft" />
    </el-select>

    <!-- 备注图标 -->
    <el-tooltip content="显示备注图标" placement="bottom" :teleported="false">
      <el-button
        size="small"
        :type="showAnnotationIcon ? 'primary' : 'default'"
        :icon="ChatDotRound"
        @click="handleUpdate('show-annotation-icon', !showAnnotationIcon)"
      />
    </el-tooltip>

    <div class="cmt-spacer"></div>

    <!-- 全屏按钮 -->
    <el-tooltip content="在新页面打开（全屏）" placement="bottom" :teleported="false">
      <el-button size="small" :icon="FullScreen" @click="handleOpenFullscreen" />
    </el-tooltip>
  </div>
</template>

<script setup>
/**
 * ChartMiniToolbar - 高频配置工具栏
 *
 * 设计原则（v2.3 §5.0.2 ③ 状态分层）：
 *   - 本组件不持有 chartConfig 状态
 *   - 通过 v-model 与父组件 EmbeddedChartView 双向绑定
 *   - 仅作为 UI 层，触发 update 事件
 */
import { ChatDotRound, FullScreen } from '@element-plus/icons-vue'

const props = defineProps({
  chartType: { type: String, required: true },
  colorScheme: { type: String, required: true },
  colorGroupBy: { type: String, required: true },
  showAnnotationIcon: { type: Boolean, default: false }
})

const emit = defineEmits([
  'update:chart-type',
  'update:color-scheme',
  'update:color-group-by',
  'update:show-annotation-icon',
  'open-fullscreen'
])

function handleUpdate(field, value) {
  emit(`update:${field}`, value)
}

function handleOpenFullscreen() {
  emit('open-fullscreen')
}
</script>

<style lang="scss" scoped>
.chart-mini-toolbar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  padding: 8px 16px;
  background: var(--color-bg-container, #fff);
  border-bottom: 1px solid var(--color-border, #e4e7ed);
  flex-shrink: 0;
}

.cmt-select {
  width: 180px;
}

.cmt-select--short {
  width: 120px;
}

.cmt-label {
  font-size: 12px;
  color: var(--color-text-tertiary, #909399);
  white-space: nowrap;
  padding-right: 4px;
  border-right: 1px solid var(--color-border, #dcdfe6);
  margin-right: 4px;
}

.cmt-spacer {
  flex: 1;
}
</style>
