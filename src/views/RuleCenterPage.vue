<template>
  <div class="rule-center-page">
    <div class="page-header">
      <h2>{{ config.title }}</h2>
      <p v-if="config.description" class="page-desc">{{ config.description }}</p>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in visibleTabs"
        :key="tab.id"
        :name="tab.id"
        :label="tab.label"
      >
        <div v-if="tab.kind === 'simulate'" class="simulate-pane">
          <el-form :model="simulateForm" label-width="120px" class="simulate-form">
            <el-form-item
              v-for="field in simulateFields"
              :key="field"
              :label="labelOfColumn(field)"
            >
              <el-select
                v-if="field === 'scenario'"
                v-model="simulateForm.scenario"
                placeholder="选择场景"
              >
                <el-option
                  v-for="option in scenarioOptions"
                  :key="option"
                  :label="option"
                  :value="option"
                />
              </el-select>
              <el-select
                v-else-if="field === 'config_mode'"
                v-model="simulateForm.config_mode"
                placeholder="配置口径"
              >
                <el-option
                  v-for="option in configModeOptions"
                  :key="option"
                  :label="option"
                  :value="option"
                />
              </el-select>
              <el-input
                v-else
                v-model="simulateForm[field]"
                :placeholder="simulatePlaceholder(field)"
                clearable
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="simulating" @click="runSimulate">
                试算
              </el-button>
              <el-button @click="resetSimulate">重置</el-button>
            </el-form-item>
          </el-form>

          <div v-if="simulateResult" class="simulate-result">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item
                v-for="item in simulateSummary"
                :key="item.label"
                :label="item.label"
              >
                {{ item.value }}
              </el-descriptions-item>
            </el-descriptions>

            <template v-if="simulateCandidates.length">
              <h4 class="result-title">候选集</h4>
              <el-table :data="simulateCandidates" size="small" border>
                <el-table-column
                  v-for="column in candidateColumns"
                  :key="column"
                  :label="column"
                  min-width="120"
                >
                  <template #default="{ row }">
                    <span class="cell-text">{{ formatCell(row[column]) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </template>

            <template v-for="block in simulateBlocks" :key="block.key">
              <h4 class="result-title">{{ block.label }}</h4>
              <pre class="code-block">{{ block.text }}</pre>
            </template>
          </div>
        </div>

        <div v-else-if="tab.kind" class="placeholder">
          <el-empty :description="`${tab.label} · 暂未接入`" />
        </div>

        <template v-else>
          <div class="filter-bar">
            <template v-for="filter in tab.filters || []" :key="filter">
              <el-input
                v-if="filter === 'keyword'"
                v-model="filters.keyword"
                class="filter-item keyword"
                :placeholder="labelOfFilter(filter)"
                clearable
                @keyup.enter="reload"
                @clear="reload"
              />
              <el-select
                v-else-if="optionsOf(filter).length"
                v-model="filters[filter]"
                class="filter-item"
                :placeholder="labelOfFilter(filter)"
                clearable
                @change="reload"
              >
                <el-option
                  v-for="option in optionsOf(filter)"
                  :key="option"
                  :label="option"
                  :value="option"
                />
              </el-select>
              <el-input
                v-else
                v-model="filters[filter]"
                class="filter-item"
                :placeholder="labelOfFilter(filter)"
                clearable
              />
            </template>
            <el-button type="primary" @click="reload">查询</el-button>
          </div>

          <el-table v-loading="loading" :data="pagedRows" border size="small">
            <el-table-column
              v-for="column in tab.columns || []"
              :key="column"
              :label="labelOfColumn(column)"
              min-width="140"
            >
              <template #default="{ row }">
                <span class="cell-text">{{ formatCell(pick(row, column)) }}</span>
              </template>
            </el-table-column>

            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openDetail(row)">详情</el-button>
                <el-button
                  v-if="(tab.actions || []).includes('copy_key')"
                  link
                  type="primary"
                  @click="copyKey(row)"
                >
                  复制键
                </el-button>
                <el-button
                  v-if="(tab.actions || []).includes('simulate')"
                  link
                  type="primary"
                  @click="useSimulate(row)"
                >
                  试算
                </el-button>
                <el-button
                  v-else-if="hasP2Action(tab)"
                  link
                  type="info"
                  disabled
                >
                  P2
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            class="pager"
            layout="total, sizes, prev, pager, next"
            :page-sizes="[20, 50, 100]"
            :total="filteredRows.length"
          />
        </template>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="drawerVisible" :title="detailRow?.name || detailRow?.rule_key" size="52%">
      <div v-if="detailRow" class="detail">
        <section
          v-for="section in detailSections"
          :key="section.id"
          class="detail-section"
        >
          <h4>{{ section.label }}</h4>

          <pre v-if="section.widget === 'code'" class="code-block">{{ codeOf(detailRow) }}</pre>

          <el-table
            v-else-if="section.widget === 'factor_matrix'"
            :data="factorRows"
            size="small"
            border
          >
            <el-table-column prop="key" :label="labelOfColumn('factors')" min-width="160" />
            <el-table-column prop="value" label="值" min-width="200" />
          </el-table>

          <pre v-else-if="section.widget === 'source_snippet'" class="code-block">{{ snippetOf(detailRow) }}</pre>

          <div v-else-if="section.widget === 'audit_log'" class="audit-log">
            <div class="audit-toolbar">
              <el-button size="small" :loading="historyLoading" @click="loadHistory(section)">
                刷新
              </el-button>
              <el-button
                v-if="canPublish"
                size="small"
                type="primary"
                :loading="publishing"
                @click="onPublish"
              >
                发布草稿
              </el-button>
              <el-button
                v-if="canRollback"
                size="small"
                type="warning"
                :loading="rollingBack"
                @click="onRollback"
              >
                回滚上一版本
              </el-button>
            </div>

            <el-table v-loading="historyLoading" :data="pagedHistory" size="small" border>
              <el-table-column label="时间" width="170">
                <template #default="{ row }">{{ row.created_at || '—' }}</template>
              </el-table-column>
              <el-table-column label="动作" width="100">
                <template #default="{ row }">
                  <el-tag size="small" :type="actionTagType(row.action)">
                    {{ actionLabel(row.action) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作人" width="120">
                <template #default="{ row }">{{ row.operator || '—' }}</template>
              </el-table-column>
              <el-table-column label="变更前" min-width="160">
                <template #default="{ row }">
                  <span class="cell-text">{{ formatCell(row.before) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="变更后" min-width="160">
                <template #default="{ row }">
                  <span class="cell-text">{{ formatCell(row.after) }}</span>
                </template>
              </el-table-column>
            </el-table>

            <el-empty
              v-if="!historyLoading && !historyRows.length"
              :description="section.label + ' · 暂无记录'"
              :image-size="60"
            />

            <el-pagination
              v-if="historyRows.length > historyPageSize"
              v-model:current-page="historyPage"
              v-model:page-size="historyPageSize"
              class="pager"
              layout="total, sizes, prev, pager, next"
              :page-sizes="[10, 20, 50]"
              :total="historyRows.length"
            />
          </div>

          <el-descriptions v-else :column="2" border size="small">
            <el-descriptions-item
              v-for="field in section.fields || []"
              :key="field"
              :label="labelOfColumn(field)"
            >
              {{ formatCell(pick(detailRow, field)) }}
            </el-descriptions-item>
          </el-descriptions>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage } from '@/composables/useMessage'
import { useAuthStore } from '@/stores/authStore'
import { getRule, getRuleCenterViewConfig, getRuleConfigHistory, listRules, publishRuleConfig, rollbackRuleConfig, simulateRule } from '@/services/ruleCenterService'

const FALLBACK_CONFIG = {
  title: '规则中心',
  tabs: [
    {
      id: 'all',
      label: '全部规则',
      sources: ['bo_yaml', 'doc_flow', 'approval', 'control_parameter', 'line_type'],
      columns: ['rule_key', 'name', 'rule_type', 'source', 'scope_bo', 'configurable', 'status'],
      filters: ['keyword', 'rule_type', 'source', 'configurable', 'status'],
      actions: ['detail', 'copy_key'],
    },
  ],
  column_labels: {},
  filter_labels: {},
  filter_options: {},
  detail: { sections: [] },
}

const auth = useAuthStore()
const message = useMessage()

const config = ref(FALLBACK_CONFIG)
const activeTab = ref('')
const loading = ref(false)
const rows = ref([])
const filters = reactive({})
const page = ref(1)
const pageSize = ref(50)
const drawerVisible = ref(false)
const detailRow = ref(null)

const simulateForm = reactive({})
const simulating = ref(false)
const simulateResult = ref(null)

const historyRows = ref([])
const historyLoading = ref(false)
const historyPage = ref(1)
const historyPageSize = ref(10)
const publishing = ref(false)
const rollingBack = ref(false)

const DIMENSION_FIELDS = ['org_id', 'document_type_id', 'line_type_id', 'item_group_id']
const SIMULATE_HINTS = {
  codes: '控制参数编码，逗号分隔，如 payment_term, credit_limit',
  object_type: '单据对象类型，如 sales_order',
  record_id: '单据主键 ID（需配合 object_type）',
  org_id: '组织 ID',
  document_type_id: '单据类型 ID',
  line_type_id: '行类型 ID',
  item_group_id: '物料组 ID',
}
const TARGET_BY_SOURCE = {
  control_parameter: 'control_parameter_value',
  line_type: 'line_type_assignment',
}
const ACTION_LABELS = { SAVE: '保存草稿', PUBLISH: '发布', ROLLBACK: '回滚' }
const BLOCK_LABELS = {
  final: '最终取值',
  baseline: 'baseline 结果',
  draft: 'draft 结果',
  diff: '差异',
}
const CANDIDATE_COLUMN_ORDER = [
  'code', 'value', 'value_id', 'line_type_id', 'document_type_id',
  'item_group_id', 'specificity_rank', 'status', 'hit', 'reason',
]

const columnLabels = computed(() => config.value.column_labels || {})
const filterLabels = computed(() => config.value.filter_labels || {})
const filterOptions = computed(() => config.value.filter_options || {})
const detailSections = computed(() => config.value.detail?.sections || [])

const visibleTabs = computed(() =>
  (config.value.tabs || []).filter(tab => !tab.require || auth.hasPermission(tab.require))
)

const currentTab = computed(() =>
  visibleTabs.value.find(tab => tab.id === activeTab.value) || visibleTabs.value[0] || null
)

const filteredRows = computed(() => {
  const tab = currentTab.value
  if (!tab) return []
  const skip = new Set(['keyword', 'rule_type', 'source', 'configurable', 'status'])
  const conditions = Object.entries(filters).filter(
    ([key, value]) => value !== '' && value !== null && value !== undefined && !skip.has(key)
  )
  if (!conditions.length) return rows.value
  return rows.value.filter(row =>
    conditions.every(([key, value]) => String(pick(row, key) ?? '').toLowerCase().includes(String(value).toLowerCase()))
  )
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

const factorRows = computed(() => {
  const factors = detailRow.value?.factors || {}
  return Object.entries(factors).map(([key, value]) => ({
    key,
    value: formatCell(value),
  }))
})

const simulateMeta = computed(() => config.value.simulate || {})
const simulateFields = computed(() => simulateMeta.value.fields || [])
const scenarioOptions = computed(() => config.value.trace?.scenarios || [])
const configModeOptions = computed(
  () => simulateMeta.value.config_modes || ['baseline', 'draft', 'both']
)

const simulateCandidates = computed(() => simulateResult.value?.candidates || [])

const candidateColumns = computed(() => {
  const rows = simulateCandidates.value
  if (!rows.length) return []
  const keys = new Set()
  rows.forEach(row => Object.keys(row).forEach(key => keys.add(key)))
  const ordered = CANDIDATE_COLUMN_ORDER.filter(key => keys.has(key))
  keys.forEach(key => {
    if (!ordered.includes(key)) ordered.push(key)
  })
  return ordered
})

const simulateSummary = computed(() => {
  const result = simulateResult.value
  if (!result) return []
  return [
    ['场景', result.scenario],
    ['配置口径', result.config_mode],
    ['决策', result.decision],
    ['来源', result.source],
    ['规则键', result.rule_id],
    ['原因', result.reason],
    ['耗时(ms)', result.elapsed_ms],
    ['缓存', result.cached ? '命中' : '未命中'],
  ].map(([label, value]) => ({ label, value: formatCell(value) }))
})

const simulateBlocks = computed(() => {
  const result = simulateResult.value
  if (!result) return []
  return Object.entries(BLOCK_LABELS)
    .filter(([key]) => result[key] !== undefined && result[key] !== null)
    .map(([key, label]) => ({ key, label, text: JSON.stringify(result[key], null, 2) }))
})

const pagedHistory = computed(() => {
  const start = (historyPage.value - 1) * historyPageSize.value
  return historyRows.value.slice(start, start + historyPageSize.value)
})

const configTarget = computed(() => TARGET_BY_SOURCE[detailRow.value?.source] || '')

const canWriteConfig = computed(() => auth.hasPermission('rule_center:rule_center_write'))

const canPublish = computed(() => {
  const latest = historyRows.value[0]
  return Boolean(
    canWriteConfig.value &&
    configTarget.value &&
    latest?.action === 'SAVE' &&
    latest?.extra?.draft_id
  )
})

const canRollback = computed(() =>
  Boolean(
    canWriteConfig.value &&
    configTarget.value &&
    historyRows.value.some(item => item.action === 'PUBLISH')
  )
)

onMounted(async () => {
  try {
    const response = await getRuleCenterViewConfig()
    if (response.success && response.data?.tabs?.length) {
      config.value = response.data
    } else {
      message.warning(response.message || '规则中心视图元数据不可用，已回落默认视图')
    }
  } catch {
    message.warning('规则中心视图元数据不可用，已回落默认视图')
  }
  const defaultTab = (config.value.tabs || []).find(tab => tab.default)
  activeTab.value = defaultTab?.id || visibleTabs.value[0]?.id || ''
  resetFilters()
  resetSimulate()
  await reload()
})

function simulatePlaceholder(field) {
  return SIMULATE_HINTS[field] || labelOfColumn(field)
}

function resetSimulate() {
  Object.keys(simulateForm).forEach(key => delete simulateForm[key])
  simulateForm.scenario = scenarioOptions.value[0] || 'default'
  simulateForm.config_mode = configModeOptions.value[0] || 'baseline'
  simulateResult.value = null
}

function buildSimulatePayload() {
  const payload = { config_mode: simulateForm.config_mode || 'baseline' }
  if (simulateForm.scenario) payload.scenario = simulateForm.scenario

  const codes = String(simulateForm.codes || '')
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
  if (codes.length) payload.codes = codes

  if (simulateForm.object_type) payload.object_type = String(simulateForm.object_type).trim()
  if (simulateForm.record_id) payload.record_id = simulateForm.record_id

  const factors = {}
  for (const field of DIMENSION_FIELDS) {
    const value = simulateForm[field]
    if (value !== '' && value !== null && value !== undefined) {
      factors[field] = /^\d+$/.test(String(value).trim()) ? Number(value) : value
    }
  }
  if (Object.keys(factors).length) payload.factors = factors
  return payload
}

async function runSimulate() {
  simulating.value = true
  try {
    const response = await simulateRule(buildSimulatePayload())
    if (response.success) {
      simulateResult.value = response.data
    } else {
      simulateResult.value = null
      message.error(response.message || '规则试算失败')
    }
  } catch {
    simulateResult.value = null
    message.error('规则试算失败')
  } finally {
    simulating.value = false
  }
}

function useSimulate(row) {
  const tab = (config.value.tabs || []).find(item => item.kind === 'simulate')
  if (!tab) return
  activeTab.value = tab.id
  resetSimulate()

  if (row?.source === 'control_parameter') {
    simulateForm.scenario = 'control_parameter'
    const code = String(row.rule_key || '').split(':').slice(1).join(':')
    if (code) simulateForm.codes = code
  } else if (row?.source === 'line_type') {
    simulateForm.scenario = 'line_type'
    for (const field of DIMENSION_FIELDS) {
      const value = pick(row, field)
      if (value !== undefined && value !== null) simulateForm[field] = value
    }
  }
}

function sectionParams(section, row) {
  const params = {}
  for (const [key, value] of Object.entries(section?.params || {})) {
    params[key] = typeof value === 'string'
      ? value.replace(/\{(\w+)\}/g, (_, name) => row?.[name] ?? '')
      : value
  }
  return params
}

function auditSection() {
  return detailSections.value.find(section => section.widget === 'audit_log') || null
}

async function loadHistory(section) {
  const row = detailRow.value
  const target = configTarget.value
  if (!row || !target) {
    historyRows.value = []
    return
  }

  const params = sectionParams(section || auditSection(), row)
  params.target = target
  params.rule_key = row.rule_key
  params.limit = 50

  historyLoading.value = true
  historyPage.value = 1
  try {
    const response = await getRuleConfigHistory(params)
    historyRows.value = response.success ? response.data?.items || [] : []
    if (!response.success) message.error(response.message || '读取变更记录失败')
  } catch {
    historyRows.value = []
    message.error('读取变更记录失败')
  } finally {
    historyLoading.value = false
  }
}

function actionLabel(action) {
  return ACTION_LABELS[action] || action || '—'
}

function actionTagType(action) {
  if (action === 'PUBLISH') return 'success'
  if (action === 'ROLLBACK') return 'warning'
  return 'info'
}

async function refreshAfterConfigChange() {
  await loadHistory()
  await reload()
  if (detailRow.value) openDetail(detailRow.value)
}

async function onPublish() {
  const latest = historyRows.value[0]
  const target = configTarget.value
  const draftId = latest?.extra?.draft_id
  if (!target || !draftId) return

  publishing.value = true
  try {
    const response = await publishRuleConfig({ target, draft_id: draftId })
    if (response.success) {
      message.success(`已发布（替换 ${response.data?.superseded ?? 0} 条生效配置）`)
      await refreshAfterConfigChange()
    } else {
      message.error(response.message || '发布配置失败')
    }
  } catch {
    message.error('发布配置失败')
  } finally {
    publishing.value = false
  }
}

async function onRollback() {
  const row = detailRow.value
  const target = configTarget.value
  if (!row || !target) return

  rollingBack.value = true
  try {
    const response = await rollbackRuleConfig({ target, payload: { rule_key: row.rule_key } })
    if (response.success) {
      message.success(`已回滚（恢复 ${response.data?.restored ?? 0} 条配置）`)
      await refreshAfterConfigChange()
    } else {
      message.error(response.message || '回滚配置失败')
    }
  } catch {
    message.error('回滚配置失败')
  } finally {
    rollingBack.value = false
  }
}

function labelOfColumn(key) {
  return columnLabels.value[key] || key
}

function labelOfFilter(key) {
  return filterLabels.value[key] || labelOfColumn(key)
}

function optionsOf(key) {
  const options = filterOptions.value[key]
  if (Array.isArray(options) && options.length) return options
  if (key === 'source') return (config.value.sources || []).map(item => item.id)
  return []
}

function resetFilters() {
  Object.keys(filters).forEach(key => delete filters[key])
  ;(currentTab.value?.filters || []).forEach(key => {
    filters[key] = key === 'status' ? 'active' : ''
  })
}

async function reload() {
  const tab = currentTab.value
  if (!tab || tab.kind) {
    rows.value = []
    return
  }
  loading.value = true
  page.value = 1
  try {
    const params = { limit: 500, offset: 0 }
    if (tab.sources?.length) params.sources = tab.sources.join(',')
    for (const key of ['keyword', 'rule_type', 'source', 'configurable', 'status']) {
      if (filters[key]) params[key] = filters[key]
    }
    const response = await listRules(params)
    rows.value = response.success ? response.data?.items || [] : []
    if (!response.success) message.error(response.message || '查询规则目录失败')
  } catch {
    rows.value = []
    message.error('查询规则目录失败')
  } finally {
    loading.value = false
  }
}

function onTabChange() {
  resetFilters()
  reload()
}

function pick(row, key) {
  if (!row) return undefined
  if (row[key] !== undefined) return row[key]
  const factors = row.factors || {}
  if (factors[key] !== undefined) return factors[key]
  const detail = row.detail || {}
  if (detail[key] !== undefined) return detail[key]
  if (detail.factors?.[key] !== undefined) return detail.factors[key]
  if (detail.declaration?.[key] !== undefined) return detail.declaration[key]
  return undefined
}

function formatCell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return text.length > 120 ? `${text.slice(0, 120)}…` : text
  }
  return String(value)
}

function codeOf(row) {
  const detail = row?.detail || {}
  const payload = detail.expression || detail.condition || detail.action || detail
  return typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2)
}

function snippetOf(row) {
  const detail = row?.detail || {}
  const payload = detail.source_snippet || detail.declaration || detail
  return typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2)
}

function hasP2Action(tab) {
  return (tab.actions || []).some(action =>
    ['edit', 'publish', 'rollback', 'simulate', 'view_source'].includes(action)
  )
}

async function openDetail(row) {
  detailRow.value = row
  drawerVisible.value = true
  historyRows.value = []
  try {
    const response = await getRule(row.rule_key)
    if (response.success && response.data) detailRow.value = response.data
  } catch {
    // 详情接口失败时保留列表行数据，不阻断抽屉
  }
  await loadHistory()
}

async function copyKey(row) {
  try {
    await navigator.clipboard.writeText(row.rule_key)
    message.success('已复制规则键')
  } catch {
    message.warning(row.rule_key)
  }
}
</script>

<style scoped>
.rule-center-page {
  padding: 16px 20px;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 18px;
}
.page-desc {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.filter-item {
  width: 180px;
}
.filter-item.keyword {
  width: 240px;
}
.cell-text {
  word-break: break-all;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.detail-section {
  margin-bottom: 20px;
}
.detail-section h4 {
  margin: 0 0 8px;
  font-size: 14px;
}
.code-block {
  margin: 0;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.placeholder {
  padding: 24px 0;
}
.simulate-form {
  max-width: 720px;
}
.simulate-result {
  margin-top: 16px;
}
.result-title {
  margin: 16px 0 8px;
  font-size: 14px;
}
.audit-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
</style>