<template>
  <div ref="rootRef" class="rule-trace-panel" v-loading="loading">
    <div class="rtp-toolbar">
      <el-button
        type="primary"
        size="small"
        :loading="loading"
        :disabled="!canRun"
        @click="run"
      >
        {{ rerunLabel }}
      </el-button>
      <el-button v-if="result" size="small" @click="copySnapshot">{{ copyLabel }}</el-button>
      <span v-if="result?.trace_id" class="rtp-trace-id">{{ result.trace_id }}</span>
    </div>

    <el-alert
      v-if="!canRun && !errorMessage"
      :title="missingHint"
      type="info"
      :closable="false"
      show-icon
    />
    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
    />

    <template v-if="result">
      <el-descriptions class="rtp-factors" :column="factorColumns" border size="small">
        <el-descriptions-item v-for="item in factorItems" :key="item.key" :label="item.label">
          {{ item.value }}
          <el-tag
            v-if="item.source"
            size="small"
            type="info"
            effect="plain"
            class="rtp-factor-source"
          >
            {{ item.source }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="result.truncated"
        :title="truncatedHint"
        type="warning"
        :closable="false"
        show-icon
      />

      <div v-if="scenarioSteps.length" class="rtp-rules">
        <div class="rtp-rules__head">
          <strong class="rtp-rules__title">{{ rulesAllLabel }}</strong>
          <el-tag
            v-for="tag in scenarioTags"
            :key="'scenario-' + tag.value"
            size="small"
            :type="ruleFilter === tag.value ? 'primary' : 'info'"
            :effect="ruleFilter === tag.value ? 'dark' : 'plain'"
            class="rtp-filter-tag"
            @click="ruleFilter = tag.value"
          >
            {{ tag.label }}
          </el-tag>
          <span class="rtp-rules__gap" />
          <el-tag
            v-for="tag in scopeTags"
            :key="'scope-' + tag.value"
            size="small"
            :type="scopeFilter === tag.value ? 'primary' : 'info'"
            :effect="scopeFilter === tag.value ? 'dark' : 'plain'"
            class="rtp-filter-tag"
            @click="scopeFilter = tag.value"
          >
            {{ tag.label }}
          </el-tag>
        </div>

        <el-empty
          v-if="!ruleRows.length"
          :image-size="40"
          :description="rulesEmptyHint"
        />
        <el-table v-else :data="ruleRows" size="small" border class="rtp-table">
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="rtp-rule-expand">
                <el-table
                  v-if="row.conditions.length"
                  :data="row.conditions"
                  size="small"
                  border
                >
                  <el-table-column
                    v-for="column in conditionColumns"
                    :key="column.key"
                    :label="column.label"
                    :min-width="column.minWidth"
                  >
                    <template #default="{ row: condition }">
                      <el-tag
                        v-if="column.key === 'passed'"
                        size="small"
                        :type="condition.passed ? 'success' : 'danger'"
                        effect="light"
                      >
                        {{ passedLabel(condition.passed) }}
                      </el-tag>
                      <span v-else class="cell-text">{{ formatCell(condition[column.key]) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
                <p v-else class="rtp-rule-expand__empty">{{ conditionsEmptyHint }}</p>
                <p class="rtp-rule-expand__output">
                  <span class="rtp-rule-expand__label">{{ outputColumnLabel }}</span>
                  {{ row.output || outputEmptyHint }}
                </p>
              </div>
            </template>
          </el-table-column>
          <el-table-column
            v-for="column in ruleColumns"
            :key="column.key"
            :label="column.label"
            :min-width="column.minWidth"
          >
            <template #default="{ row }">
              <el-tag
                v-if="column.key === 'scenario'"
                size="small"
                type="info"
                effect="plain"
              >
                {{ row.scenarioLabel }}
              </el-tag>
              <el-tag
                v-else-if="column.key === 'scope'"
                size="small"
                :type="scopeMeta(row.scope).type"
                effect="light"
              >
                {{ scopeMeta(row.scope).label }}
              </el-tag>
              <el-tag
                v-else-if="column.key === 'status'"
                size="small"
                :type="decisionMeta(row.status).type"
                effect="light"
              >
                {{ decisionMeta(row.status).label }}
              </el-tag>
              <span v-else class="cell-text">{{ formatCell(row[column.key]) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-empty
        v-if="!scenarioSteps.length"
        :image-size="60"
        :description="emptyResultHint"
      />

      <section
        v-for="step in scenarioSteps"
        :key="step.scenario"
        :class="['rtp-step', { 'is-failed': step.ok === false }]"
      >
        <header class="rtp-step__head">
          <strong class="rtp-step__scenario">{{ scenarioLabelOf(step.scenario) }}</strong>
          <span v-if="step.seq != null" class="rtp-step__seq">#{{ step.seq }}</span>
          <el-tag v-if="step.stage" size="small" type="info" effect="plain">
            {{ stageLabelOf(step.stage) }}
          </el-tag>
          <el-tag size="small" :type="decisionMeta(step).type" effect="light">
            {{ decisionMeta(step).label }}
          </el-tag>
          <el-tag v-if="step.source" size="small" type="info" effect="plain">
            {{ step.source }}
          </el-tag>
          <span v-if="step.rule_id" class="rtp-step__rule">{{ step.rule_id }}</span>
          <span v-if="step.elapsed_ms != null" class="rtp-step__elapsed">
            {{ elapsedText(step.elapsed_ms) }}
          </span>
        </header>

        <p v-if="step.reason && step.ok !== false" class="rtp-step__reason">{{ step.reason }}</p>
        <el-alert
          v-if="step.ok === false"
          :title="step.reason || traceFailedHint"
          type="error"
          :closable="false"
          show-icon
        />
        <p v-else-if="stepHint(step)" class="rtp-step__hint">
          {{ stepHint(step) }}
        </p>

        <template v-if="step.detail">
          <el-table
            v-if="chainRows(step).length"
            :data="chainRows(step)"
            size="small"
            border
            class="rtp-table"
          >
            <el-table-column
              v-for="column in chainColumns"
              :key="column.key"
              :label="column.label"
              :min-width="column.minWidth"
            >
              <template #default="{ row }">
                <span class="cell-text">{{ formatCell(row[column.key]) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <el-table
            v-else-if="rulesRows(step).length"
            :data="rulesRows(step)"
            size="small"
            border
            class="rtp-table"
          >
            <el-table-column
              v-for="column in rulesColumnsFor(step)"
              :key="column.key"
              :label="column.label"
              :min-width="column.minWidth"
            >
              <template #default="{ row }">
                <el-tag
                  v-if="column.key === 'status'"
                  size="small"
                  :type="decisionMeta(row.status).type"
                  effect="light"
                >
                  {{ decisionMeta(row.status).label }}
                </el-tag>
                <span v-else class="cell-text">{{ formatCell(row[column.key]) }}</span>
              </template>
            </el-table-column>
          </el-table>

          <el-descriptions v-else-if="detailScalars(step).length" :column="2" border size="small">
            <el-descriptions-item
              v-for="item in detailScalars(step)"
              :key="item.key"
              :label="item.key"
            >
              {{ item.value }}
            </el-descriptions-item>
          </el-descriptions>
        </template>

        <el-collapse v-if="stepFactorPairs(step).length" class="rtp-step__factors">
          <el-collapse-item :title="factorDetailLabel" :name="step.scenario">
            <dl class="rtp-factor-list">
              <template v-for="pair in stepFactorPairs(step)" :key="pair.key">
                <dt>{{ pair.label }}</dt>
                <dd>{{ pair.value }}</dd>
              </template>
            </dl>
          </el-collapse-item>
        </el-collapse>
      </section>
    </template>

    <el-empty
      v-else-if="!loading && !errorMessage"
      :image-size="60"
      :description="idleHint"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useMessage } from '@/composables/useMessage'
import { getRuleCenterViewConfigCached, getRuleTrace } from '@/services/ruleCenterService'

const FACTOR_KEYS = ['org_id', 'document_type_id', 'line_type_id', 'item_group_id']

// 元数据缺失时的兜底文案；正常路径以视图配置 trace.messages 为准
const FALLBACK_MESSAGES = {
  rerun: '重新推导',
  copy_snapshot: '复制因子快照',
  copied: '因子快照已复制',
  copy_failed: '复制失败，请手动复制',
  clipboard_unsupported: '当前环境不支持剪贴板',
  missing_target: '请先选择单据对象并填写记录 ID',
  codes_required: '需指定控制参数编码（codes）后重跑',
  all_missing: '全部控制参数均未取到值',
  empty_result: '未返回推导场景',
  idle: '尚未推导',
  failed: '推导失败',
  factor_detail: '因子明细',
  value_missing: '未提供',
  forbidden: '无权查看单据推导（缺少 rule_center:rule_center_trace）',
  not_found: '单据不存在或超出数据范围',
  rules_all: '规则全集',
  rules_empty: '本次推导没有可展示的规则',
  scope_all: '全部',
  conditions_empty: '无可核对条件',
  condition_passed: '通过',
  condition_failed: '未通过',
  output_empty: '无输出',
  truncated: '规则节点过多，已截断展示'
}

// 规则全集归属 → tag 颜色（文案走视图元数据 trace.scopes）
const SCOPE_TAG_TYPES = {
  evaluated: 'success',
  not_triggered: 'info',
  downstream: 'warning'
}

const props = defineProps({
  objectType: { type: String, default: '' },
  recordId: { type: [String, Number], default: null },
  scenarios: { type: Array, default: () => [] },
  codes: { type: Array, default: () => [] },
  dims: { type: Object, default: () => ({}) },
  // 决策文案映射（trace.decisions）；缺省时组件自行从视图元数据补齐
  decisions: { type: Object, default: () => ({}) },
  // 因子/列的中文标签（页面已有映射时传入）
  labels: { type: Object, default: () => ({}) },
  autoLoad: { type: Boolean, default: true },
  maxCodes: { type: Number, default: 20 }
})

const emit = defineEmits(['loaded'])

const message = useMessage()
const rootRef = ref(null)
const loading = ref(false)
const result = ref(null)
const errorMessage = ref('')
const fetchedTrace = ref({})
const configLoaded = ref(false)
// 规则全集表筛选：场景 / 归属（all 表示不过滤）
const ruleFilter = ref('all')
const scopeFilter = ref('all')

let observer = null
let started = false

const messages = computed(() => ({
  ...FALLBACK_MESSAGES,
  ...(fetchedTrace.value.messages || {})
}))

const rerunLabel = computed(() => messages.value.rerun)
const copyLabel = computed(() => messages.value.copy_snapshot)
const missingHint = computed(() => messages.value.missing_target)
const emptyResultHint = computed(() => messages.value.empty_result)
const idleHint = computed(() => messages.value.idle)
const traceFailedHint = computed(() => messages.value.failed)
const factorDetailLabel = computed(() => messages.value.factor_detail)
const truncatedHint = computed(() => messages.value.truncated)
const rulesAllLabel = computed(() => messages.value.rules_all)
const rulesEmptyHint = computed(() => messages.value.rules_empty)
const conditionsEmptyHint = computed(() => messages.value.conditions_empty)
const passedLabel = (passed) => (
  passed ? messages.value.condition_passed : messages.value.condition_failed
)
const outputEmptyHint = computed(() => messages.value.output_empty)

const canRun = computed(() => {
  if (!props.objectType) return false
  const raw = props.recordId == null ? '' : String(props.recordId).trim()
  if (!raw) return false
  const num = Number(raw)
  return Number.isFinite(num) && num > 0
})

const factorColumns = computed(() => (factorItems.value.length > 4 ? 3 : 2))

const decisionMap = computed(() => ({
  ...(fetchedTrace.value.decisions || {}),
  ...(props.decisions || {})
}))

const kindMap = computed(() => fetchedTrace.value.kinds || {})
const factorSourceLabels = computed(() => fetchedTrace.value.factor_sources || {})
const factorSources = computed(() => result.value?.factor_sources || {})

const scenarioSteps = computed(() => {
  const data = result.value
  if (!data) return []
  if (Array.isArray(data.scenarios)) return data.scenarios
  if (Array.isArray(data.steps)) return data.steps
  return []
})

const factorItems = computed(() => {
  const factors = result.value?.factors || {}
  const keys = []
  for (const key of FACTOR_KEYS) keys.push(key)
  for (const key of Object.keys(factors)) {
    if (!keys.includes(key)) keys.push(key)
  }
  return keys.map((key) => ({
    key,
    label: props.labels?.[key] || key,
    value: valueText(factors[key]),
    source: factorSourceLabels.value[factorSources.value[key]] || ''
  }))
})

const chainColumns = [
  { key: 'code', label: 'code', minWidth: 160 },
  { key: 'value', label: 'value', minWidth: 100 },
  { key: 'source', label: 'source', minWidth: 140 },
  { key: 'specificity', label: 'specificity_rank', minWidth: 120 },
  { key: 'candidates', label: '候选数', minWidth: 80 }
]

const scopeMap = computed(() => fetchedTrace.value.scopes || {})

function scenarioLabelOf(scenario) {
  const labels = fetchedTrace.value.scenario_labels || {}
  return labels[scenario] || scenario || '-'
}

function stageLabelOf(stage) {
  const labels = fetchedTrace.value.stages || {}
  return labels[stage] || stage || ''
}

function scopeMeta(scope) {
  const raw = scopeMap.value?.[scope]
  if (typeof raw === 'string') {
    return { label: raw, type: SCOPE_TAG_TYPES[scope] || 'info' }
  }
  if (raw && typeof raw === 'object') return raw
  return { label: scope || '-', type: SCOPE_TAG_TYPES[scope] || 'info' }
}

// 规则全集表：聚合各场景 detail.rules；无规则明细的场景按节点本身出一行
function ruleOutput(step, rule) {
  if (rule) {
    if (rule.target_bo) return String(rule.target_bo)
    if (rule.target_field) {
      return rule.value == null
        ? String(rule.target_field)
        : `${rule.target_field}=${formatCell(rule.value)}`
    }
  }
  const output = step?.output
  if (output && typeof output === 'object' && Object.keys(output).length) {
    return Object.entries(output)
      .map(([key, value]) => `${key}=${formatCell(value)}`)
      .join(', ')
  }
  return ''
}

function buildRuleRow(step, rule, index) {
  const scenario = step?.scenario || ''
  const status = rule ? rule.status : step?.decision
  // 归属三类（spec §11.4）：下游声明 / 条件未命中 / 本次已评估
  let scope = 'evaluated'
  if (scenario === 'doc_flow') scope = 'downstream'
  else if (status === 'not_matched') scope = 'not_triggered'
  return {
    key: `${step?.node_id || scenario}-${index}`,
    scenario,
    scenarioLabel: scenarioLabelOf(scenario),
    rule_id: rule?.rule_id || step?.rule_id || scenario,
    scope,
    status,
    output: ruleOutput(step, rule),
    conditions: Array.isArray(step?.match?.conditions) ? step.match.conditions : []
  }
}

const allRuleRows = computed(() => {
  const rows = []
  for (const step of scenarioSteps.value) {
    const rules = rulesRows(step)
    const list = rules.length ? rules : [null]
    for (const rule of list) {
      rows.push(buildRuleRow(step, rule, rows.length))
    }
  }
  return rows
})

const ruleRows = computed(() => allRuleRows.value.filter((row) => (
  (ruleFilter.value === 'all' || row.scenario === ruleFilter.value)
  && (scopeFilter.value === 'all' || row.scope === scopeFilter.value)
)))

const scenarioTags = computed(() => {
  const ids = []
  for (const step of scenarioSteps.value) {
    const id = step?.scenario
    if (id && !ids.includes(id)) ids.push(id)
  }
  return [
    { value: 'all', label: messages.value.scope_all },
    ...ids.map((id) => ({ value: id, label: scenarioLabelOf(id) }))
  ]
})

const scopeTags = computed(() => {
  const present = new Set(allRuleRows.value.map((row) => row.scope))
  const ids = Object.keys(scopeMap.value).filter((id) => present.has(id))
  return [
    { value: 'all', label: messages.value.scope_all },
    ...ids.map((id) => ({ value: id, label: scopeMeta(id).label }))
  ]
})

const ruleColumns = computed(() => {
  const map = fetchedTrace.value.rules_columns || {}
  return [
    { key: 'scenario', label: map.scenario || 'scenario', minWidth: 96 },
    { key: 'rule_id', label: map.rule_id || 'rule_id', minWidth: 180 },
    { key: 'scope', label: map.scope || 'scope', minWidth: 80 },
    { key: 'status', label: map.status || 'status', minWidth: 96 },
    { key: 'output', label: map.output || 'output', minWidth: 160 }
  ]
})

const conditionColumns = computed(() => {
  const map = fetchedTrace.value.conditions_columns || {}
  return [
    { key: 'field', label: map.field || 'field', minWidth: 120 },
    { key: 'op', label: map.op || 'op', minWidth: 80 },
    { key: 'expected', label: map.expected || 'expected', minWidth: 120 },
    { key: 'actual', label: map.actual || 'actual', minWidth: 120 },
    { key: 'passed', label: map.passed || 'passed', minWidth: 64 }
  ]
})

const outputColumnLabel = computed(() => (
  (fetchedTrace.value.rules_columns || {}).output || 'output'
))

// default 场景列出"参与评估的规则清单"，doc_flow 列出"下游单据规则"
const defaultRuleColumns = [
  { key: 'rule_id', label: 'rule_id', minWidth: 180 },
  { key: 'target_field', label: 'target_field', minWidth: 140 },
  { key: 'value', label: 'value', minWidth: 100 },
  { key: 'status', label: 'status', minWidth: 110 },
  { key: 'skip_reason', label: 'skip_reason', minWidth: 140 }
]

const docFlowRuleColumns = [
  { key: 'rule_id', label: 'rule_id', minWidth: 180 },
  { key: 'target_bo', label: 'target_bo', minWidth: 140 },
  { key: 'pool', label: 'pool', minWidth: 100 },
  { key: 'status', label: 'status', minWidth: 90 }
]

function rulesColumnsFor(step) {
  return step?.scenario === 'default' ? defaultRuleColumns : docFlowRuleColumns
}

function valueText(value) {
  if (value == null || value === '') return messages.value.value_missing
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatCell(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function decisionMeta(stepOrValue) {
  const isStep = Boolean(stepOrValue) && typeof stepOrValue === 'object'
  const decision = isStep ? stepOrValue.decision : stepOrValue
  const kind = isStep ? stepOrValue.kind : null
  const meta = decisionMap.value?.[decision] || kindMap.value?.[kind || '']
  if (meta && typeof meta === 'object') return meta
  if (typeof meta === 'string') return { label: meta, type: 'info' }
  return { label: decision || kind || '-', type: 'info' }
}

// 区分"需要补输入"与"确实取不到值"两种跳过
function stepHint(step) {
  if (!step || step.ok === false) return ''
  if (step.reason === 'no_codes_requested') return messages.value.codes_required
  if (step.reason === 'all_codes_missing') return messages.value.all_missing
  return ''
}

function elapsedText(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return ''
  return `${num.toFixed(2)} ms`
}

function chainRows(step) {
  const chain = step?.detail?.chain
  return Array.isArray(chain) ? chain : []
}

function rulesRows(step) {
  const rules = step?.detail?.rules
  return Array.isArray(rules) ? rules : []
}

function detailScalars(step) {
  const detail = step?.detail
  if (!detail || typeof detail !== 'object') return []
  return Object.entries(detail)
    .filter(([, value]) => value == null || typeof value !== 'object')
    .map(([key, value]) => ({ key, value: valueText(value) }))
}

function stepFactorPairs(step) {
  const factors = step?.factors
  if (!factors || typeof factors !== 'object') return []
  return Object.entries(factors).map(([key, value]) => ({
    key,
    label: props.labels?.[key] || key,
    value: valueText(value)
  }))
}

function normalizeCodes() {
  const seen = new Set()
  const list = []
  for (const raw of props.codes || []) {
    const code = String(raw == null ? '' : raw).trim()
    if (!code || seen.has(code)) continue
    seen.add(code)
    list.push(code)
    if (list.length >= props.maxCodes) break
  }
  return list
}

function buildParams() {
  const params = {}
  if (props.scenarios.length) params.scenarios = props.scenarios.join(',')
  const codes = normalizeCodes()
  if (codes.length) params.codes = codes.join(',')
  for (const key of FACTOR_KEYS) {
    const raw = props.dims?.[key]
    if (raw == null || raw === '') continue
    params[key] = raw
  }
  return params
}

async function ensureTraceConfig() {
  if (configLoaded.value) return
  try {
    const resp = await getRuleCenterViewConfigCached()
    if (resp?.success) {
      fetchedTrace.value = resp.data?.trace || {}
    }
  } catch (err) {
    // 文案/映射缺失只影响展示，不阻断推导
    console.warn('[RuleTracePanel] load view config failed:', err)
  } finally {
    configLoaded.value = true
  }
}

function errorText(resp) {
  if (resp?.code === 'FORBIDDEN') return messages.value.forbidden
  if (resp?.code === 'NOT_FOUND') return messages.value.not_found
  return resp?.message || messages.value.failed
}

async function run() {
  if (!canRun.value || loading.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    const [resp] = await Promise.all([
      getRuleTrace(props.objectType, props.recordId, buildParams()),
      ensureTraceConfig()
    ])
    if (resp?.success) {
      result.value = resp.data
      // 重跑后场景集合可能变化，筛选回到全部，避免命中空表
      ruleFilter.value = 'all'
      scopeFilter.value = 'all'
      emit('loaded', resp.data)
    } else {
      errorMessage.value = errorText(resp)
      message.error(errorMessage.value)
    }
  } catch (err) {
    errorMessage.value = err?.message || traceFailedHint
    message.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

function start() {
  if (started) return
  started = true
  if (observer) {
    observer.disconnect()
    observer = null
  }
  run()
}

function copySnapshot() {
  if (!result.value) return
  const payload = {
    trace_id: result.value.trace_id,
    object_type: result.value.object_type,
    record_id: result.value.record_id,
    factors: result.value.factors,
    factor_sources: result.value.factor_sources || {},
    scenarios: scenarioSteps.value.map((step) => ({
      scenario: step.scenario,
      decision: step.decision,
      kind: step.kind,
      rule_id: step.rule_id,
      source: step.source,
      reason: step.reason
    }))
  }
  const text = JSON.stringify(payload, null, 2)
  if (navigator?.clipboard?.writeText) {
    navigator.clipboard.writeText(text)
      .then(() => message.success(messages.value.copied))
      .catch(() => message.warning(messages.value.copy_failed))
  } else {
    message.warning(messages.value.clipboard_unsupported)
  }
}

onMounted(() => {
  if (!props.autoLoad || !canRun.value) return
  if (typeof IntersectionObserver === 'undefined') {
    start()
    return
  }
  observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) start()
  })
  if (rootRef.value) observer.observe(rootRef.value)
})

onBeforeUnmount(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }
})

defineExpose({ run, reload: run, getResult: () => result.value })
</script>

<style scoped>
.rule-trace-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rtp-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rtp-trace-id {
  margin-left: auto;
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rtp-factors {
  margin-top: 4px;
}

.rtp-factor-source {
  margin-left: 6px;
}

.rtp-rules {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rtp-rules__head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.rtp-rules__title {
  font-size: 13px;
  margin-right: 4px;
}

.rtp-rules__gap {
  width: 8px;
}

.rtp-filter-tag {
  cursor: pointer;
}

.rtp-step__seq {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rtp-rule-expand {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 8px;
}

.rtp-rule-expand__empty {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rtp-rule-expand__output {
  margin: 0;
  font-size: 12px;
}

.rtp-rule-expand__label {
  color: var(--el-text-color-secondary);
  margin-right: 6px;
}

.rtp-step {
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rtp-step.is-failed {
  border-color: var(--el-color-danger);
}

.rtp-step__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rtp-step__scenario {
  font-size: 13px;
}

.rtp-step__rule {
  font-family: monospace;
  font-size: 12px;
  color: var(--el-text-color-regular);
  overflow-wrap: anywhere;
}

.rtp-step__elapsed {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rtp-step__reason {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.rtp-step__hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-color-warning);
}

.rtp-table {
  width: 100%;
}

.rtp-factor-list {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 12px;
  margin: 0;
  font-size: 12px;
}

.rtp-factor-list dt {
  color: var(--el-text-color-secondary);
}

.rtp-factor-list dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.cell-text {
  overflow-wrap: anywhere;
}
</style>