<template>
  <MultiObjectManagementPage
    ref="pageRef"
    :object-types="objectTypes"
    :options="pageOptions"
    @toolbar-action="handleToolbarAction"
  >
    <template #tabsExtra="{ context }">
      <div v-if="context.filters.length" class="rm-tabs-extra">
        <el-tag
          v-for="filter in context.filters"
          :key="filter.key"
          type="info"
          size="small"
          closable
          class="rm-filter-tag"
          @close="context.clearFilter(filter.key)"
        >
          {{ filter.label }} {{ filter.count }}
        </el-tag>
        <el-button type="primary" link size="small" @click="context.clear">清空</el-button>
      </div>
    </template>

    <!-- [对齐 ArchDataManagement 2026-08-21] chart-config slot: 注入 ChartMiniToolbar 到 GlobalToolbar
         （图表类型/备注/布局方向/高级）。chartConfig 提升到本组件持有，
         让 GlobalToolbar 和 ArchDataChartSwitcher/EmbeddedChartView 共享同一配置。 -->
    <template #chart-config>
      <ChartMiniToolbar
        v-if="viewMode === 'chart'"
        :chart-type="chartConfig.chartType"
        :annotation-category-filter="chartConfig.annotationCategoryFilter"
        :overall-direction="chartConfig.layoutControl?.overallDirection ?? 'TB'"
        :engine="chartConfig.layoutEngine"
        :hide-link-label-tails="configStore.hideLinkLabelTails"
        :version-id="embeddedContext.versionId ?? null"
        @update:chart-type="(v) => (chartConfig.chartType = v)"
        @update:annotation-category-filter="(v) => (chartConfig.annotationCategoryFilter = v)"
        @update:overall-direction="(v) => (chartConfig.layoutControl.overallDirection = v)"
        @update:engine="(v) => { chartConfig.layoutEngine = v; chartConfig.layoutControl.engine = v }"
        @update:hide-link-label-tails="(v) => configStore.updateHideLinkLabelTails(v)"
      />
    </template>

    <!-- [对齐 ArchDataManagement 2026-08-21] detailContent slot: 注入嵌入式图表视图
         （viewMode 切换由 MultiObjectManagementPage 控制，本 slot 始终注入） -->
    <template #detailContent="{ context }">
      <ArchDataChartSwitcher
        :context="context"
        :chart-config="chartConfig"
        @node-click="handleChartNodeClick"
        @render-complete="handleChartRenderComplete"
        @render-error="handleChartRenderError"
      />
    </template>

    <template #cell-source_bo_name="{ row }">
      <div class="bo-cell">
        <span class="bo-name">{{ row.source_bo_name }}</span>
        <span class="bo-code">({{ row.source_code }})</span>
      </div>
    </template>

    <template #cell-target_bo_name="{ row }">
      <div class="bo-cell">
        <span class="bo-name">{{ row.target_bo_name }}</span>
        <span class="bo-code">({{ row.target_code }})</span>
      </div>
    </template>

    <template #cell-category_label="{ row }">
      <el-tag
        :type="getCategoryTagType(row.category_type)"
        size="small"
      >
        {{ row.category_label }}
      </el-tag>
    </template>
  </MultiObjectManagementPage>
</template>

<script setup>
import { ref, reactive, computed, provide } from 'vue'
import { ElMessage } from 'element-plus'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import ArchDataChartSwitcher from '@/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue'
import ChartMiniToolbar from '@/views/SystemManagement/components/ArchDataChart/ChartMiniToolbar.vue'
import { createDefaultChartConfig } from '@/views/SystemManagement/components/ArchDataChart/chartConfigDefaults.js'
import { useDiagramConfigStore } from '@/stores/diagramConfigStore'

defineOptions({ name: 'ArchDataManagement' })

// [FIX v1.2.18 2026-06-20] annotation 不应作为顶层对象类型 (它是辅助关联数据, category=auxiliary)
// 之前错误地加入 objectTypes, 现在移除
// annotation 通过其他对象的"备注"关联面板管理, 不通过顶层导入
const objectTypes = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
// [DEFAULT-TAB 2026-08-21] 进入页面默认 Tab = 业务对象 (对齐主仓 ArchDataManagement; 之前为 relationship)
const pageOptions = { defaultTab: 'business_object' }
const pageRef = ref(null)

// [对齐 ArchDataManagement] chartConfig 提升到本组件持有，
// 让 GlobalToolbar（chart-config slot）和 ArchDataChartSwitcher/EmbeddedChartView 共享同一份配置
const chartConfig = reactive(createDefaultChartConfig())
// [TAIL 2026-08-12] 拖尾线开关直接读写 store.hideLinkLabelTails
const configStore = useDiagramConfigStore()

// viewMode 通过 MultiObjectManagementPage.expose({ viewMode }) 暴露
const viewMode = computed(() => pageRef.value?.viewMode || 'list')

// embeddedChartContext 包含 versionId/scopeIds/chartData 等（来自 MOMP.expose）
const embeddedContext = computed(() => pageRef.value?.embeddedChartContext || {})

// [布局设置 sidebar 整合] 提供 chartConfig 给 RelationScopeTree (sidebar)
provide('chartConfig', chartConfig)

function getCategoryTagType(categoryType) {
  return ''
}

function handleToolbarAction(action) {
  const actionType = typeof action === 'string' ? action : action?.type
  if (actionType === 'refresh') {
    if (typeof window !== 'undefined' && window.__archPage?.reload) {
      window.__archPage.reload()
    }
  }
}

// [A8] 嵌入式图表节点点击: 简单提示，后续可扩展为打开详情抽屉
function handleChartNodeClick(payload) {
  const name = payload?.node?.name || payload?.name || payload?.id || '节点'
  ElMessage?.info?.(`点击节点: ${name}`) || console.info('[A8] chart node click:', name)
}

// [O1] 渲染状态反馈: render-complete render-error
let _lastRenderReportedKey = null
function handleChartRenderComplete(payload) {
  const versionKey = `v${embeddedContext.value.versionId ?? ''}`
  if (_lastRenderReportedKey === versionKey) return
  _lastRenderReportedKey = versionKey
  const nodeCount = payload?.nodeCount ?? 0
  const durationMs = payload?.durationMs
  ElMessage.success(`图表渲染完成 (${nodeCount} 节点${durationMs != null ? `, ${durationMs}ms` : ''})`)
}

function handleChartRenderError(payload) {
  const msg = payload?.error?.message || payload?.error || '未知错误'
  ElMessage.error(`图表渲染失败: ${msg}`)
}
</script>

<style lang="scss" scoped>
.bo-cell {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
}

.bo-name {
  color: var(--color-text-primary);
}

.bo-code {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

:deep(.el-table) {
  .bo-cell {
    .bo-name {
      font-weight: 500;
    }
  }
}

.rm-tabs-extra {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 16px;
}

.rm-filter-tag {
  border-radius: 4px;
}
</style>