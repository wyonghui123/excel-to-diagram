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

    <!-- [FIX 2026-07-30 v2] chart-config slot: 注入 ChartMiniToolbar 到 GlobalToolbar
         （图表类型/颜色分组/配色/备注/全屏）。
         chartConfig 提升到本组件持有，让 GlobalToolbar 和 EmbeddedChartView 共享同一配置。
         架构：通用模块（GlobalToolbar/MultiObjectManagementPage）零侵入，业务扩展只在 RelationshipManagement -->
    <template #chart-config>
      <ChartMiniToolbar
        v-if="viewMode === 'chart'"
        :chart-type="chartConfig.chartType"
        :color-scheme="chartConfig.colorScheme"
        :color-group-by="chartConfig.colorGroupBy"
        :center-scope-highlight="chartConfig.centerScopeHighlight"
        :annotation-category-filter="chartConfig.annotationCategoryFilter"
        :version-id="embeddedContext.versionId ?? null"
        @update:chart-type="(v) => (chartConfig.chartType = v)"
        @update:color-scheme="(v) => (chartConfig.colorScheme = v)"
        @update:color-group-by="(v) => (chartConfig.colorGroupBy = v)"
        @update:center-scope-highlight="(v) => (chartConfig.centerScopeHighlight = v)"
        @update:annotation-category-filter="(v) => (chartConfig.annotationCategoryFilter = v)"
        @open-layout-settings="layoutDrawerVisible = true"
      />
    </template>

    <!-- [Phase 2 v2.3 §5.0.2 ⑤] detailContent slot: 注入嵌入式图表视图 -->
    <!-- [PHASE 6 COMPARE] 总是注入，由父组件 viewMode 控制显示 -->
    <template #detailContent="{ context }">
      <ArchDataChartSwitcher
        :context="context"
        :chart-config="chartConfig"
        :layout-drawer-visible="layoutDrawerVisible"
        @update:layout-drawer-visible="(v) => (layoutDrawerVisible = v)"
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
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import ArchDataChartSwitcher from '@/views/SystemManagement/components/ArchDataChart/ArchDataChartSwitcher.vue'
import ChartMiniToolbar from '@/views/systemmanagement/components/archdatachart/ChartMiniToolbar.vue'
import { createDefaultChartConfig } from '@/views/SystemManagement/components/ArchDataChart/chartConfigDefaults.js'

defineOptions({ name: 'RelationshipManagement' })

// [FIX v1.2.18 2026-06-20] annotation 不应作为顶层对象类型 (它是辅助关联数据, category=auxiliary)
// 之前错误地加入 objectTypes, 现在移除
// annotation 通过其他对象的"备注"关联面板管理, 不通过顶层导入
const objectTypes = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
const pageOptions = { defaultTab: 'relationship' }
const pageRef = ref(null)
// [B6 2026-08-03] chartSwitcherRef 已移除: reload 统一走 window.__archPage.reload (slot ref 不可靠).

// [FIX 2026-07-30 v2] chartConfig 提升到本组件持有，
// 让 GlobalToolbar（chart-config slot）和 ArchDataChartSwitcher/EmbeddedChartView 共享同一份配置
// [FIX 2026-08-01] 对齐 EmbeddedChartView 7/31 22:31 大重构版的 layoutControl 结构
//   (含 layoutType/preserveOrder 字段, 默认 enabled=true 跟随 useDiagramData 自动分组)
// [T1 2026-08-02] 默认值统一走 chartConfigDefaults.js 工厂, 与 EmbeddedChartView/ArchDataChartSwitcher 共用
const chartConfig = reactive(createDefaultChartConfig())

// [FIX 2026-07-31] 布局设置抽屉可见性：ChartMiniToolbar 的"布局设置"按钮触发
const layoutDrawerVisible = ref(false)


// [FIX 2026-07-30 v2] viewMode 通过 MultiObjectManagementPage.expose({ viewMode }) 暴露。
// 用 computed 包装，让模板中可以直接用 viewMode 而无需 pageRef.value.viewMode。
const viewMode = computed(() => pageRef.value?.viewMode || 'list')

// embeddedChartContext 包含 versionId/scopeIds/chartData 等（来自 MOMP.expose）
const embeddedContext = computed(() => pageRef.value?.embeddedChartContext || {})

function getCategoryTagType(categoryType) {
  return ''
}

function handleToolbarAction(action) {
  // 兼容旧式 action string 和新式 { type, viewMode } 对象
  const actionType = typeof action === 'string' ? action : action?.type
  if (actionType === 'refresh') {
    // [FIX 2026-08-03] refresh 触发图表 reload (强制 mermaid.run() 全量重绘)
    //   原: 只调 pageRef.refresh() (刷新元数据列表), 图表 reload 链路断裂.
    //   现: 调 window.__archPage.reload() → MermaidComponent.forceRerender()
    //   (清空 lastRenderedCode 让 code-diff 不命中 → mermaid.run() 重绘 SVG, 避免显示 text).
    //   [B6 2026-08-03] reload 唯一入口: window.__archPage.reload (EmbeddedChartView 内赋值).
    //     slot ref 链路 (ArchDataChartSwitcher.defineExpose.reload) 已移除, 不再使用.
    //   不调 pageRef.refresh(): MOMP.refresh 异步触发 generateDiagram 会覆盖 reload 重绘.
    if (typeof window !== 'undefined' && window.__archPage?.reload) {
      window.__archPage.reload()
    }
  }
  // 'view-mode-change' 由 MultiObjectManagementPage 内部处理，无需在此响应
}

// [A8 2026-07-30] 嵌入式图表节点点击: 简单提示，后续可扩展为打开详情抽屉
function handleChartNodeClick(payload) {
  const name = payload?.node?.name || payload?.name || payload?.id || '节点'
  ElMessage?.info?.(`点击节点: ${name}`) || console.info('[A8] chart node click:', name)
}

// [O1 2026-08-02] 渲染状态反馈: render-complete/render-error 之前无人消费,
//   用户侧对"图表是否渲染完成/失败"无感知。现在:
//   - 成功: 仅首次/版本切换时提示 (避免每次过滤变化都刷 toast)
//   - 失败: 始终提示
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
