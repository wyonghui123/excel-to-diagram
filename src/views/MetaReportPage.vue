<template>
  <div class="meta-report-page">
    <header class="report-header">
      <div>
        <h2 class="report-title">{{ config?.title || '报表' }}</h2>
        <p v-if="config?.description" class="report-description">{{ config.description }}</p>
      </div>
    </header>

    <el-alert
      v-if="configError"
      type="error"
      :title="configError"
      :closable="false"
      show-icon
    />

    <FilterBar
      v-if="config"
      :model-value="filterValues"
      :fields="filterFields"
      @update:model-value="onFilterValuesChange"
      @search="fetchReport"
      @reset="resetAndFetch"
    />

    <el-alert
      v-if="errorMessage"
      class="report-error"
      type="error"
      :title="errorMessage"
      :closable="false"
      show-icon
    />

    <el-row v-if="config?.kpis?.length" :gutter="16" class="report-kpis">
      <el-col v-for="kpi in config.kpis" :key="kpi.field" :span="6">
        <el-card shadow="never" class="report-kpi-card">
          <div class="report-kpi-label">{{ kpi.label }}</div>
          <div class="report-kpi-value">{{ formatValue(reportData?.[kpi.field], kpi.format) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="config?.chart" shadow="never" class="report-chart-card">
      <ReportBarChart
        :items="chartItems"
        :title="config.chart.title"
        :category-field="config.chart.category_field"
        :value-field="config.chart.value_field"
      />
    </el-card>

    <el-card v-if="config?.table" shadow="never" class="report-table-card">
      <el-table
        v-loading="loading"
        :data="pagedRows"
        :row-key="rowKeyOf"
        stripe
        @row-click="handleRowClick"
      >
        <el-table-column
          v-for="column in tableColumns"
          :key="column.field || column.key"
          :prop="column.field || column.key"
          :label="column.label"
          :width="column.width"
          :align="column.align || 'left'"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            {{ formatValue(row[column.field || column.key], column.format) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="report-pagination">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="tableRows.length"
          layout="total, prev, pager, next"
          background
        />
      </div>
    </el-card>

    <el-drawer
      v-model="detailVisible"
      :title="config?.drilldown?.title || '明细'"
      size="60%"
    >
      <template v-if="detailData">
        <el-descriptions :column="3" border class="report-detail-desc">
          <el-descriptions-item label="截止日期">{{ detailData.as_of }}</el-descriptions-item>
          <el-descriptions-item label="在手数量">{{ formatValue(detailData.qty_on_hand, 'number') }}</el-descriptions-item>
          <el-descriptions-item label="对账">
            <el-tag :type="detailData.reconciled ? 'success' : 'danger'" size="small">
              {{ detailData.reconciled ? '已对平' : '不平' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-table :data="detailData.layers" stripe>
          <el-table-column prop="receipt_date" label="入库过账日" width="130" />
          <el-table-column prop="layer_qty" label="入库层数量" width="120" align="right">
            <template #default="{ row }">{{ formatValue(row.layer_qty, 'number') }}</template>
          </el-table-column>
          <el-table-column prop="remaining_qty" label="剩余数量" width="120" align="right">
            <template #default="{ row }">{{ formatValue(row.remaining_qty, 'number') }}</template>
          </el-table-column>
          <el-table-column prop="days_in_stock" label="库龄(天)" width="100" align="right" />
        </el-table>
      </template>
      <el-empty v-else description="暂无明细" />
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { apiV1 } from '@/utils/httpClient'
import metaService from '@/services/metaService'
import FilterBar from '@/components/common/FilterBar/FilterBar.vue'
import ReportBarChart from '@/components/common/MetaReportPage/ReportBarChart.vue'

const props = defineProps({
  objectType: { type: String, default: '' },
  pageConfig: { type: Object, default: null },
})

const config = ref(null)
const configError = ref('')
const loading = ref(false)
const errorMessage = ref('')
const reportData = ref(null)
const filterValues = reactive({})
const currentPage = ref(1)
const detailVisible = ref(false)
const detailData = ref(null)

const filterFields = computed(() => (config.value?.filters || []).map((item) => ({
  key: item.key,
  label: item.label,
  type: item.type || 'text',
  options: item.options || [],
  valueHelpConfig: item.type === 'value_help'
    ? { source: { type: 'bo', target_bo: item.target_type }, behavior: {}, presentation: {} }
    : null,
})))

const tableColumns = computed(() => config.value?.table?.columns || [])
const tableRows = computed(() => reportData.value?.[config.value?.table?.data_field || 'rows'] || [])
const pageSize = computed(() => Number(config.value?.table?.page_size) || 20)
const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return tableRows.value.slice(start, start + pageSize.value)
})
const chartItems = computed(() => reportData.value?.[config.value?.chart?.data_field || 'summary'] || [])

watch(pageSize, () => { currentPage.value = 1 })

function normalizeEndpoint(endpoint) {
  return String(endpoint || '').replace(/^\/api\/v1/, '')
}

// FilterBar 以新对象回传，reactive 对象不能直接 v-model 赋值，需原地合并
function onFilterValuesChange(values) {
  const next = values || {}
  for (const key of Object.keys(filterValues)) {
    if (!(key in next)) delete filterValues[key]
  }
  Object.assign(filterValues, next)
}

function formatDate(value) {
  if (!value) return ''
  if (value instanceof Date) {
    const y = value.getFullYear()
    const m = String(value.getMonth() + 1).padStart(2, '0')
    const d = String(value.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return String(value).slice(0, 10)
}

function filterValue(item, value) {
  if (value === '' || value === null || value === undefined) return undefined
  if (item.type === 'date' || item.type === 'datetime') return formatDate(value)
  return value
}

function buildParams() {
  const params = {}
  for (const item of config.value?.filters || []) {
    const value = filterValue(item, filterValues[item.key])
    if (value !== undefined) params[item.key] = value
  }
  return params
}

function formatValue(value, format) {
  if (value === null || value === undefined || value === '') return '—'
  if (format === 'number') {
    const num = Number(value)
    if (Number.isNaN(num)) return String(value)
    return num.toLocaleString('zh-CN', { maximumFractionDigits: 6 })
  }
  if (format === 'date') return formatDate(value)
  return String(value)
}

function errorText(result) {
  if (!result) return '请求失败'
  return result.code ? `${result.code}: ${result.message || ''}` : (result.message || '请求失败')
}

async function loadConfig() {
  if (!props.objectType) {
    configError.value = '报表页缺少 primary_object_type，无法加载配置'
    return
  }
  const result = await metaService.getViewConfig(props.objectType)
  if (!result?.success || !result.data?.report) {
    configError.value = `对象 ${props.objectType} 未声明 ui_view_config.report`
    return
  }
  config.value = props.pageConfig?.report
    ? { ...result.data.report, ...props.pageConfig.report }
    : result.data.report

  for (const item of config.value.filters || []) {
    filterValues[item.key] = item.default ?? ''
  }
}

async function fetchReport() {
  if (!config.value?.endpoint) return
  loading.value = true
  errorMessage.value = ''
  try {
    const result = await apiV1.get(normalizeEndpoint(config.value.endpoint), { params: buildParams() })
    if (!result?.success) {
      errorMessage.value = errorText(result)
      reportData.value = null
      return
    }
    reportData.value = result.data || {}
    currentPage.value = 1
  } catch (error) {
    errorMessage.value = error?.message || '请求失败'
    reportData.value = null
  } finally {
    loading.value = false
  }
}

function resetAndFetch() {
  for (const item of config.value?.filters || []) {
    filterValues[item.key] = item.default ?? ''
  }
  fetchReport()
}

function rowKeyOf(row) {
  return (config.value?.table?.row_key || []).map((key) => row[key] ?? '').join('|')
}

async function handleRowClick(row) {
  const drilldown = config.value?.drilldown
  if (!drilldown?.endpoint || detailLoading.value) return
  const requiredGroup = drilldown.only_when_group_by
  if (requiredGroup && filterValues.group_by !== requiredGroup) return

  detailLoading.value = true
  detailData.value = null
  detailVisible.value = true
  try {
    const params = {}
    for (const [target, source] of Object.entries(drilldown.param_map || {})) {
      const value = row[source] ?? filterValues[source]
      if (value !== undefined && value !== null && value !== '') {
        params[target] = value
      }
    }
    const result = await apiV1.get(normalizeEndpoint(drilldown.endpoint), { params })
    detailData.value = result?.success ? result.data : null
    if (!result?.success) errorMessage.value = errorText(result)
  } catch (error) {
    errorMessage.value = error?.message || '明细请求失败'
  } finally {
    detailLoading.value = false
  }
}

const detailLoading = ref(false)

onMounted(async () => {
  await loadConfig()
  if (config.value) await fetchReport()
})
</script>

<style scoped>
.meta-report-page {
  padding: 16px;
}
.report-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.report-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #1f1f1f;
}
.report-description {
  margin: 6px 0 0;
  font-size: 13px;
  color: #8c8c8c;
}
.report-error {
  margin-bottom: 12px;
}
.report-kpis {
  margin-bottom: 16px;
}
.report-kpi-card {
  border-radius: 8px;
}
.report-kpi-label {
  font-size: 13px;
  color: #8c8c8c;
  margin-bottom: 6px;
}
.report-kpi-value {
  font-size: 22px;
  font-weight: 600;
  color: #1f1f1f;
}
.report-chart-card,
.report-table-card {
  margin-bottom: 16px;
  border-radius: 8px;
}
.report-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.report-detail-desc {
  margin-bottom: 16px;
}
</style>
