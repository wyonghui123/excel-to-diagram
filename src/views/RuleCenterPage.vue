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
                :placeholder="messages.scenario_placeholder"
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
                :placeholder="messages.config_mode_placeholder"
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
                {{ messages.simulate_run }}
              </el-button>
              <el-button @click="resetSimulate">{{ messages.simulate_reset }}</el-button>
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
              <h4 class="result-title">{{ messages.candidates }}</h4>
              <el-table :data="simulateCandidates" size="small" border>
                <el-table-column
                  v-for="column in candidateColumns"
                  :key="column"
                  :label="candidateLabel(column)"
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

        <div v-else-if="tab.kind === 'rule_trace'" class="trace-pane">
          <el-form :model="traceForm" label-width="120px" class="simulate-form">
            <el-form-item
              v-for="field in traceFields"
              :key="field"
              :label="labelOfColumn(field)"
            >
              <el-select
                v-if="field === 'object_type'"
                v-model="traceForm.object_type"
                filterable
                allow-create
                default-first-option
                :placeholder="messages.object_type_placeholder"
              >
                <el-option
                  v-for="option in objectTypeOptions"
                  :key="option.id"
                  :label="option.label"
                  :value="option.id"
                />
              </el-select>
              <el-select
                v-else-if="field === 'scenarios'"
                v-model="traceForm.scenarios"
                multiple
                collapse-tags
                :placeholder="messages.scenarios_placeholder"
              >
                <el-option
                  v-for="option in scenarioOptions"
                  :key="option"
                  :label="option"
                  :value="option"
                />
              </el-select>
              <el-input
                v-else
                v-model="traceForm[field]"
                :placeholder="simulatePlaceholder(field)"
                clearable
              />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="runTrace">{{ messages.trace_run }}</el-button>
              <el-button @click="resetTrace">{{ messages.trace_reset }}</el-button>
            </el-form-item>
          </el-form>

          <RuleTracePanel
            v-if="traceRequest"
            ref="tracePanelRef"
            :key="traceRunSeq"
            :object-type="traceRequest.object_type"
            :record-id="traceRequest.record_id"
            :scenarios="traceRequest.scenarios"
            :codes="traceRequest.codes"
            :dims="traceRequest.dims"
            :decisions="traceDecisions"
            :labels="columnLabels"
          />
        </div>

        <div v-else-if="tab.kind" class="placeholder">
          <el-empty :description="`${tab.label} · ${messages.not_ready}`" />
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
            <el-button type="primary" @click="reload">{{ messages.query }}</el-button>
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

            <el-table-column :label="messages.action_column" width="180" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openDetail(row)">{{ messages.detail }}</el-button>
                <el-button
                  v-if="(tab.actions || []).includes('copy_key')"
                  link
                  type="primary"
                  @click="copyKey(row)"
                >
                  {{ messages.copy_key }}
                </el-button>
                <el-button
                  v-if="(tab.actions || []).includes('simulate')"
                  link
                  type="primary"
                  @click="useSimulate(row)"
                >
                  {{ messages.simulate_run }}
                </el-button>
                <el-button
                  v-else-if="hasP2Action(tab)"
                  link
                  type="info"
                  disabled
                >
                  {{ messages.p2_pending }}
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
            <el-table-column prop="value" :label="messages.history_value" min-width="200" />
          </el-table>

          <pre v-else-if="section.widget === 'source_snippet'" class="code-block">{{ snippetOf(detailRow) }}</pre>

          <div v-else-if="section.widget === 'audit_log'" class="audit-log">
            <div class="audit-toolbar">
              <el-button size="small" :loading="historyLoading" @click="loadHistory(section)">
                {{ messages.refresh }}
              </el-button>
              <el-button
                v-if="canPublish"
                size="small"
                type="primary"
                :loading="publishing"
                @click="onPublish"
              >
                {{ messages.publish_draft }}
              </el-button>
              <el-button
                v-if="canRollback"
                size="small"
                type="warning"
                :loading="rollingBack"
                @click="onRollback"
              >
                {{ messages.rollback_previous }}
              </el-button>
            </div>

            <el-table v-loading="historyLoading" :data="pagedHistory" size="small" border>
              <el-table-column :label="messages.history_time" width="170">
                <template #default="{ row }">{{ row.created_at || '—' }}</template>
              </el-table-column>
              <el-table-column :label="messages.history_action" width="100">
                <template #default="{ row }">
                  <el-tag size="small" :type="actionTagType(row.action)">
                    {{ actionLabel(row.action) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column :label="messages.history_operator" width="120">
                <template #default="{ row }">{{ row.operator || '—' }}</template>
              </el-table-column>
              <el-table-column :label="messages.history_before" min-width="160">
                <template #default="{ row }">
                  <span class="cell-text">{{ formatCell(row.before) }}</span>
                </template>
              </el-table-column>
              <el-table-column :label="messages.history_after" min-width="160">
                <template #default="{ row }">
                  <span class="cell-text">{{ formatCell(row.after) }}</span>
                </template>
              </el-table-column>
            </el-table>

            <el-empty
              v-if="!historyLoading && !historyRows.length"
              :description="section.label + ' · ' + messages.history_empty"
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
import RuleTracePanel from '@/components/common/RuleTrace/RuleTracePanel.vue'
import { apiV1 } from '@/utils/httpClient'
import { getRule, getRuleCenterViewConfig, getRuleConfigHistory, listRules, publishRuleConfig, rollbackRuleConfig, simulateRule } from '@/services/ruleCenterService'

const FALLBACK_CONFIG = {
  title: '',
  tabs: [],
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

const traceForm = reactive({})
const traceRequest = ref(null)
const traceRunSeq = ref(0)
const tracePanelRef = ref(null)
const objectTypeOptions = ref([])

const historyRows = ref([])
const historyLoading = ref(false)
const historyPage = ref(1)
const historyPageSize = ref(10)
const publishing = ref(false)
const rollingBack = ref(false)

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
const traceMeta = computed(() => config.value.trace || {})
const messages = computed(() => traceMeta.value.messages || {})
const factorKeys = computed(() => traceMeta.value.factor_keys || [])
const simulateHints = computed(() => simulateMeta.value.hints || {})
const traceFields = computed(() => traceMeta.value.tab?.fields || [])
const traceDecisions = computed(() => traceMeta.value.decisions || {})
const configModeOptions = computed(() => simulateMeta.value.config_modes || [])

const simulateCandidates = computed(() => simulateResult.value?.candidates || [])

const candidateColumns = computed(() => {
  const rows = simulateCandidates.value
  if (!rows.length) return []
  // 列顺序与中文名同源：视图元数据 simulate.candidate_columns（spec §13 F-13-07）
  const declared = Object.keys(simulateMeta.value.candidate_columns || {})
  const keys = new Set()
  rows.forEach(row => Object.keys(row).forEach(key => keys.add(key)))
  const ordered = declared.filter(key => keys.has(key))
  keys.forEach(key => {
    if (!ordered.includes(key)) ordered.push(key)
  })
  return ordered
})

const simulateSummary = computed(() => {
  const result = simulateResult.value
  if (!result) return []
  const labels = simulateMeta.value.summary || {}
  return [
    ['scenario', result.scenario],
    ['config_mode', result.config_mode],
    ['decision', result.decision],
    ['source', result.source],
    ['rule_id', result.rule_id],
    ['reason', result.reason],
    ['elapsed_ms', result.elapsed_ms],
    ['cached', result.cached ? labels.cached_hit : labels.cached_miss],
  ].map(([key, value]) => ({ label: labels[key] || key, value: formatCell(value) }))
})

const simulateBlocks = computed(() => {
  const result = simulateResult.value
  if (!result) return []
  return Object.entries(simulateMeta.value.blocks || {})
    .filter(([key]) => result[key] !== undefined && result[key] !== null)
    .map(([key, label]) => ({ key, label, text: JSON.stringify(result[key], null, 2) }))
})

const pagedHistory = computed(() => {
  const start = (historyPage.value - 1) * historyPageSize.value
  return historyRows.value.slice(start, start + historyPageSize.value)
})

const configTarget = computed(() => detailRow.value?.links?.edit?.target || '')

const canWriteConfig = computed(() => auth.hasPermission('rule_center:write'))

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
      message.warning(response.message || messages.value.fallback_warning)
    }
  } catch {
    message.warning(messages.value.fallback_warning)
  }
  const defaultTab = (config.value.tabs || []).find(tab => tab.default)
  activeTab.value = defaultTab?.id || visibleTabs.value[0]?.id || ''
  resetFilters()
  resetSimulate()
  resetTrace()
  loadObjectTypes()
  await reload()
})

function simulatePlaceholder(field) {
  return simulateHints.value[field] || labelOfColumn(field)
}

function resetSimulate() {
  Object.keys(simulateForm).forEach(key => delete simulateForm[key])
  simulateForm.scenario = scenarioOptions.value[0] || ''
  simulateForm.config_mode = configModeOptions.value[0] || ''
  simulateResult.value = null
}

async function loadObjectTypes() {
  try {
    const response = await apiV1.get('/meta/objects')
    if (response.success) {
      objectTypeOptions.value = (response.data || []).map(item => ({
        id: item.id || item.name,
        label: item.name || item.id,
      }))
    }
  } catch {
    // 下拉不可用时仍允许手填 object_type
  }
}

function resetTrace() {
  Object.keys(traceForm).forEach(key => delete traceForm[key])
  traceRequest.value = null
}

function runTrace() {
  const objectType = String(traceForm.object_type || '').trim()
  const recordRaw = String(traceForm.record_id || '').trim()
  const recordId = Number(recordRaw)
  if (!objectType || !recordRaw || !Number.isFinite(recordId) || recordId <= 0) {
    message.warning(messages.value.missing_target)
    return
  }
  const codes = String(traceForm.codes || '')
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
  const dims = {}
  for (const field of factorKeys.value) {
    const value = traceForm[field]
    if (value !== '' && value !== null && value !== undefined) {
      dims[field] = /^\d+$/.test(String(value).trim()) ? Number(value) : value
    }
  }
  traceRequest.value = {
    object_type: objectType,
    record_id: recordId,
    scenarios: [...(traceForm.scenarios || [])],
    codes,
    dims,
  }
  traceRunSeq.value += 1
}

function buildSimulatePayload() {
  const payload = { config_mode: simulateForm.config_mode || configModeOptions.value[0] }
  if (simulateForm.scenario) payload.scenario = simulateForm.scenario

  const codes = String(simulateForm.codes || '')
    .split(',')
    .map(item => item.trim())
    .filter(Boolean)
  if (codes.length) payload.codes = codes

  if (simulateForm.object_type) payload.object_type = String(simulateForm.object_type).trim()
  if (simulateForm.record_id) payload.record_id = simulateForm.record_id

  const factors = {}
  for (const field of factorKeys.value) {
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
      message.error(response.message || messages.value.simulate_failed)
    }
  } catch {
    simulateResult.value = null
    message.error(messages.value.simulate_failed)
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
    const code = String(row.rule_key || '').split(':').slice(1).join(':')
    if (code) simulateForm.codes = code
  }
  if (row?.source && scenarioOptions.value.includes(row.source)) {
    simulateForm.scenario = row.source
  }
  if (row?.source === 'line_type') {
    for (const field of factorKeys.value) {
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
    if (!response.success) message.error(response.message || messages.value.history_load_failed)
  } catch {
    historyRows.value = []
    message.error(messages.value.history_load_failed)
  } finally {
    historyLoading.value = false
  }
}

function actionLabel(action) {
  return (messages.value.action_labels || {})[action] || action || '—'
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
      message.success(msgText('publish_success', { count: response.data?.superseded ?? 0 }))
      await refreshAfterConfigChange()
    } else {
      message.error(response.message || messages.value.publish_failed)
    }
  } catch {
    message.error(messages.value.publish_failed)
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
      message.success(msgText('rollback_success', { count: response.data?.restored ?? 0 }))
      await refreshAfterConfigChange()
    } else {
      message.error(response.message || messages.value.rollback_failed)
    }
  } catch {
    message.error(messages.value.rollback_failed)
  } finally {
    rollingBack.value = false
  }
}

function labelOfColumn(key) {
  return columnLabels.value[key] || key
}

function candidateLabel(key) {
  return (simulateMeta.value.candidate_columns || {})[key] || labelOfColumn(key)
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
    filters[key] = key === 'status' ? (optionsOf('status')[0] || '') : ''
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
    if (!response.success) message.error(response.message || messages.value.catalog_failed)
  } catch {
    rows.value = []
    message.error(messages.value.catalog_failed)
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
    const serialized = JSON.stringify(value)
    return serialized.length > 120 ? `${serialized.slice(0, 120)}…` : serialized
  }
  return String(value)
}

function msgText(key, params = {}) {
  let value = messages.value[key] || ''
  for (const [name, param] of Object.entries(params)) {
    value = value.replace(`{${name}}`, String(param))
  }
  return value
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
    message.success(messages.value.copied_key)
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