<template>
  <PageShell
    title="执行记录"
    :show-back-button="false"
  >
    <template #title-bar-actions>
      <AppButton variant="secondary" size="sm" :loading="loading" @click="manualRefresh">刷新</AppButton>
    </template>

    <FilterBar
      v-model="filters"
      :fields="filterFields"
      @search="applyFilters"
      @reset="resetFilters"
    />

    <AppAlert v-if="loadError" type="error">{{ loadError }}</AppAlert>

    <MetaTable
      :columns="columns"
      :data="items"
      :loading="loading"
      :search-placeholder="null"
      :show-header="false"
      :pagination="pagination"
      :id-key="'run_id'"
      :row-key="'run_id'"
      empty-type="search"
      empty-title="暂无执行记录"
      empty-description="调整筛选条件后重试"
      @row-click="openDetail"
      @page-change="onPageChange"
      @page-size-change="onPageSizeChange"
    >
      <template #cell-job="{ row }">
        <div class="job-cell">
          <span class="job-cell__name">{{ row.job_name || '-' }}</span>
          <span class="job-cell__code">{{ row.job_code || '-' }}</span>
        </div>
      </template>

      <template #cell-status="{ row }">
        <span class="run-badge" :class="`run-badge--${statusTone(row.status)}`">{{ statusLabel(row.status) }}</span>
      </template>

      <template #cell-progress="{ row }">
        <div class="run-progress">
          <div class="run-progress__track">
            <div
              class="run-progress__bar"
              :class="{ 'run-progress__bar--indeterminate': rowPercent(row) === null }"
              :style="rowPercent(row) === null ? {} : { width: rowPercent(row) + '%' }"
            ></div>
          </div>
          <span class="run-progress__text">{{ rowProgressText(row) }}</span>
        </div>
      </template>

      <template #cell-attempt="{ row }">
        <span class="muted">{{ row.attempt ?? 0 }}/{{ row.max_attempts ?? '-' }}</span>
      </template>

      <template #cell-source="{ row }">
        <span>{{ sourceLabel(row.source) }}</span>
      </template>

      <template #cell-duration="{ row }">
        <span class="muted">{{ formatDuration(row.duration_ms) }}</span>
      </template>

      <template #cell-created_at="{ row }">
        <span class="muted">{{ formatTime(row.created_at) }}</span>
      </template>

      <template #cell-actions="{ row }">
        <div class="row-actions">
          <AppButton
            v-if="row.capabilities && row.capabilities.can_cancel"
            variant="text"
            size="xs"
            :loading="actionLoading && actionRunId === row.run_id"
            @click.stop="onCancel(row)"
          >取消</AppButton>
          <AppButton
            v-if="row.capabilities && row.capabilities.can_retry"
            variant="text"
            size="xs"
            :loading="actionLoading && actionRunId === row.run_id"
            @click.stop="onRetry(row)"
          >重试</AppButton>
          <AppButton variant="text" size="xs" @click.stop="openDetail(row)">详情</AppButton>
        </div>
      </template>
    </MetaTable>

    <Drawer
      v-model="drawerVisible"
      title="执行详情"
      width="720px"
      @close="onDrawerClosed"
    >
      <div v-if="detailLoading && !detail" class="drawer-loading">加载中...</div>

      <template v-else-if="detail">
        <section class="drawer-section">
          <div class="section-head">
            <h4 class="drawer-section__title">基础信息</h4>
            <span class="run-badge" :class="`run-badge--${statusTone(detail.status)}`">{{ statusLabel(detail.status) }}</span>
          </div>
          <div class="kv-grid">
            <div class="kv-item">
              <span class="kv-item__label">作业</span>
              <span class="kv-item__value">{{ detail.job_name || '-' }}（{{ detail.job_code || '-' }}）</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">执行 ID</span>
              <span class="kv-item__value">#{{ detail.run_id }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">来源</span>
              <span class="kv-item__value">{{ sourceLabel(detail.source) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">尝试次数</span>
              <span class="kv-item__value">{{ detail.attempt ?? 0 }}/{{ detail.max_attempts ?? '-' }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">创建时间</span>
              <span class="kv-item__value">{{ formatTime(detail.created_at) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">开始时间</span>
              <span class="kv-item__value">{{ formatTime(detail.started_at) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">结束时间</span>
              <span class="kv-item__value">{{ formatTime(detail.finished_at) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">耗时</span>
              <span class="kv-item__value">{{ formatDuration(detail.duration_ms) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">计划执行</span>
              <span class="kv-item__value">{{ formatTime(detail.scheduled_for) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">下次重试</span>
              <span class="kv-item__value">{{ formatTime(detail.next_retry_at) }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">执行器实例</span>
              <span class="kv-item__value">{{ detail.worker_id || '-' }}</span>
            </div>
            <div class="kv-item">
              <span class="kv-item__label">触发器</span>
              <span class="kv-item__value">{{ detail.trigger_id ? `#${detail.trigger_id}` : '-' }}</span>
            </div>
          </div>
          <div v-if="detail.links && detail.links.job" class="drawer-link">
            <router-link :to="detail.links.job" @click="onDrawerClosed">查看作业定义</router-link>
          </div>
        </section>

        <section class="drawer-section">
          <div class="section-head">
            <h4 class="drawer-section__title">进度</h4>
            <span class="muted">{{ detailPercent === null ? '未上报进度' : detailPercent + '%' }}</span>
          </div>
          <div class="run-progress run-progress--drawer">
            <div class="run-progress__track">
              <div
                class="run-progress__bar"
                :class="{ 'run-progress__bar--indeterminate': detailPercent === null }"
                :style="detailPercent === null ? {} : { width: detailPercent + '%' }"
              ></div>
            </div>
          </div>
          <div v-if="detail.progress" class="progress-meta">
            <span v-if="detail.progress.stage">阶段：{{ detail.progress.stage }}</span>
            <span v-if="detail.progress.message">说明：{{ detail.progress.message }}</span>
            <span v-if="detail.progress.current !== undefined && detail.progress.total !== undefined">
              进度：{{ detail.progress.current }}/{{ detail.progress.total }}
            </span>
          </div>
        </section>

        <section class="drawer-section">
          <div class="section-head">
            <h4 class="drawer-section__title">参数</h4>
            <AppButton variant="text" size="xs" @click="copyText(paramsText, '参数已复制')">复制 JSON</AppButton>
          </div>
          <pre class="json-block">{{ paramsText }}</pre>
        </section>

        <section class="drawer-section">
          <div class="section-head">
            <h4 class="drawer-section__title">结果</h4>
            <div class="section-actions">
              <AppButton variant="text" size="xs" @click="copyText(resultText, '结果已复制')">复制</AppButton>
              <AppButton variant="text" size="xs" @click="downloadResult">下载</AppButton>
            </div>
          </div>
          <div v-if="resultCounts.length > 0" class="count-grid">
            <div v-for="item in resultCounts" :key="item.key" class="count-item">
              <span class="count-item__label">{{ item.label }}</span>
              <span class="count-item__value">{{ item.value }}</span>
            </div>
          </div>
          <pre v-if="resultCounts.length === 0" class="json-block">{{ resultText }}</pre>

          <template v-if="resultErrors.length > 0">
            <table class="errors-table">
              <thead>
                <tr>
                  <th>对象类型</th>
                  <th>行号</th>
                  <th>字段</th>
                  <th>错误信息</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(err, index) in shownErrors" :key="index">
                  <td>{{ err.object_type || '-' }}</td>
                  <td>{{ err.row ?? '-' }}</td>
                  <td>{{ err.field || '-' }}</td>
                  <td>{{ err.message || '-' }}</td>
                </tr>
              </tbody>
            </table>
            <div v-if="resultErrors.length > shownErrors.length" class="muted">
              另有 {{ resultErrors.length - shownErrors.length }} 条错误，请下载完整结果查看。
            </div>
            <div v-if="detail.result && detail.result.errors_truncated" class="muted">
              错误明细已截断，完整明细请下载结果文件。
            </div>
          </template>
        </section>

        <section v-if="detail.error" class="drawer-section">
          <div class="section-head">
            <h4 class="drawer-section__title">错误</h4>
            <AppButton variant="text" size="xs" @click="copyText(detail.error, '错误信息已复制')">复制</AppButton>
          </div>
          <div class="error-summary">{{ errorSummary }}</div>
          <details v-if="errorHasStack" class="error-stack">
            <summary>展开堆栈</summary>
            <pre class="json-block">{{ detail.error }}</pre>
          </details>
        </section>

        <section class="drawer-section">
          <h4 class="drawer-section__title">时间线</h4>
          <ul class="timeline">
            <li v-for="(entry, index) in detail.timeline || []" :key="index">
              <span class="timeline__time">{{ formatTime(entry.at) }}</span>
              <span class="timeline__status">{{ statusLabel(entry.status) }}</span>
            </li>
          </ul>
        </section>
      </template>

      <template #footer>
        <div class="drawer-footer">
          <AppButton
            v-if="detail && detail.capabilities && detail.capabilities.can_cancel"
            variant="danger"
            size="sm"
            :loading="actionLoading"
            @click="onCancel(detail)"
          >取消执行</AppButton>
          <AppButton
            v-if="detail && detail.capabilities && detail.capabilities.can_retry"
            variant="primary"
            size="sm"
            :loading="actionLoading"
            @click="onRetry(detail)"
          >重试</AppButton>
          <AppButton variant="secondary" size="sm" @click="closeDrawer">关闭</AppButton>
        </div>
      </template>
    </Drawer>
  </PageShell>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PageShell, FilterBar, MetaTable, Drawer, AppButton, AppAlert } from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import { fetchRuns, fetchRun, retryRun, cancelRun } from '@/services/jobService'
import { statusLabel, statusTone, sourceLabel } from '@/utils/jobRunStatus'
import { toEpochSeconds } from '@/utils/jobParams'

const POLL_INTERVAL_MS = 3000
const ERROR_PREVIEW_LIMIT = 50
const QUERY_KEYS = ['job_code', 'status', 'source', 'from', 'to', 'page', 'page_size', 'run']

const route = useRoute()
const router = useRouter()
const { success, error } = useMessage()

const filters = ref({ job_code: '', status: '', source: '', range: [] })
const filtersMeta = ref({ statuses: [], sources: [], job_codes: [] })
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const loadError = ref('')

const drawerVisible = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const currentRunId = ref(null)
const actionLoading = ref(false)
const actionRunId = ref(null)

let pollTimer = null

const columns = [
  { key: 'run_id', label: 'ID', width: '84px' },
  { key: 'job', label: '作业', slot: true, width: '220px' },
  { key: 'status', label: '状态', slot: true, width: '96px' },
  { key: 'progress', label: '进度', slot: true, width: '150px' },
  { key: 'attempt', label: '尝试', slot: true, width: '70px' },
  { key: 'source', label: '来源', slot: true, width: '90px' },
  { key: 'duration', label: '耗时', slot: true, width: '90px' },
  { key: 'created_at', label: '创建时间', slot: true, width: '170px' },
  { key: 'actions', label: '操作', slot: true, width: '150px' }
]

const filterFields = computed(() => [
  {
    key: 'job_code',
    label: '作业',
    type: 'select',
    placeholder: '全部作业',
    options: (filtersMeta.value.job_codes || []).map(job => ({
      value: job.code,
      label: job.name ? `${job.name}（${job.code}）` : job.code
    }))
  },
  {
    key: 'status',
    label: '状态',
    type: 'select',
    placeholder: '全部状态',
    options: (filtersMeta.value.statuses || []).map(value => ({ value, label: statusLabel(value) }))
  },
  {
    key: 'source',
    label: '来源',
    type: 'select',
    placeholder: '全部来源',
    options: (filtersMeta.value.sources || []).map(value => ({ value, label: sourceLabel(value) }))
  },
  {
    key: 'range',
    label: '时间范围',
    type: 'datetime-range',
    placeholder: ['开始时间', '结束时间']
  }
])

const pagination = computed(() => ({
  current: page.value,
  pageSize: pageSize.value,
  total: total.value,
  pageSizeOptions: [20, 50, 100]
}))

const detailPercent = computed(() => percentOf(detail.value && detail.value.progress))

const paramsText = computed(() => toJsonText(detail.value && detail.value.params))

const resultText = computed(() => toJsonText(detail.value && detail.value.result))

const resultCounts = computed(() => {
  const result = detail.value && detail.value.result
  if (!result || typeof result !== 'object') return []
  const keys = [
    { key: 'created', label: '成功新增' },
    { key: 'updated', label: '成功更新' },
    { key: 'failed', label: '失败' },
    { key: 'skipped', label: '跳过' }
  ]
  // import_cascade 的结果按对象类型分组（result.results），此处汇总总数
  const nested = result.results
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const sums = { created: 0, updated: 0, failed: 0, skipped: 0 }
    let hasSheet = false
    Object.values(nested).forEach((sheet) => {
      if (!sheet || typeof sheet !== 'object') return
      hasSheet = true
      Object.keys(sums).forEach((key) => {
        sums[key] += Number(sheet[key] || 0)
      })
    })
    if (hasSheet) return keys.map((item) => ({ ...item, value: sums[item.key] }))
  }
  return keys
    .filter(item => result[item.key] !== undefined && result[item.key] !== null)
    .map(item => ({ ...item, value: result[item.key] }))
})

const resultErrors = computed(() => {
  const result = detail.value && detail.value.result
  return result && Array.isArray(result.errors) ? result.errors : []
})

const shownErrors = computed(() => resultErrors.value.slice(0, ERROR_PREVIEW_LIMIT))

const errorSummary = computed(() => {
  const text = (detail.value && detail.value.error) || ''
  return String(text).split('\n')[0]
})

const errorHasStack = computed(() => {
  const text = (detail.value && detail.value.error) || ''
  return String(text).includes('\n')
})

function percentOf(progress) {
  if (!progress || typeof progress !== 'object') return null
  if (typeof progress.percent === 'number' && Number.isFinite(progress.percent)) {
    return Math.max(0, Math.min(100, Math.round(progress.percent)))
  }
  const current = Number(progress.current)
  const size = Number(progress.total)
  if (Number.isFinite(current) && Number.isFinite(size) && size > 0) {
    return Math.max(0, Math.min(100, Math.round((current / size) * 100)))
  }
  return null
}

function rowPercent(row) {
  return percentOf(row.progress)
}

function rowProgressText(row) {
  const percent = rowPercent(row)
  if (percent !== null) return `${percent}%`
  const stage = row.progress && row.progress.stage
  return stage || '未上报'
}

function pad(value) {
  return String(value).padStart(2, '0')
}

function formatTime(value) {
  if (value === null || value === undefined || value === '') return '-'
  let ms = null
  if (typeof value === 'number') {
    ms = value < 1e12 ? value * 1000 : value
  } else {
    const parsed = Date.parse(String(value))
    if (!Number.isNaN(parsed)) ms = parsed
  }
  if (ms === null) return String(value)
  const date = new Date(ms)
  if (Number.isNaN(date.getTime())) return String(value)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} `
    + `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function formatDuration(value) {
  if (value === null || value === undefined || value === '') return '-'
  const ms = Number(value)
  if (!Number.isFinite(ms) || ms < 0) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.round((ms % 60000) / 1000)
  return `${minutes}m${seconds}s`
}

function toJsonText(value) {
  if (value === null || value === undefined) return '-'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function buildRequestParams() {
  const params = { page: page.value, page_size: pageSize.value }
  if (filters.value.job_code) params.job_code = filters.value.job_code
  if (filters.value.status) params.status = filters.value.status
  if (filters.value.source) params.source = filters.value.source
  const range = Array.isArray(filters.value.range) ? filters.value.range : []
  const from = toEpochSeconds(range[0])
  const to = toEpochSeconds(range[1])
  if (from !== null) params.from = from
  if (to !== null) params.to = to
  return params
}

async function loadRuns(options = {}) {
  const silent = options.silent === true
  if (!silent) loading.value = true
  const res = await fetchRuns(buildRequestParams())
  if (!silent) loading.value = false
  if (!res.success) {
    loadError.value = res.message || '执行记录加载失败'
    if (!silent) error(loadError.value)
    return
  }
  loadError.value = ''
  const data = res.data || {}
  items.value = data.items || []
  total.value = data.total || 0
  if (data.page) page.value = data.page
  if (data.page_size) pageSize.value = data.page_size
  if (data.meta && data.meta.filters) filtersMeta.value = data.meta.filters
  ensurePolling()
}

async function loadDetail(runId, options = {}) {
  const silent = options.silent === true
  if (!silent) detailLoading.value = true
  const res = await fetchRun(runId)
  if (!silent) detailLoading.value = false
  if (!res.success) {
    if (!silent) error(res.message || '执行详情加载失败')
    return
  }
  detail.value = res.data || null
  ensurePolling()
}

function hasActiveWork() {
  if (items.value.some(item => !(item.capabilities && item.capabilities.is_terminal))) return true
  if (drawerVisible.value && detail.value) {
    return !(detail.value.capabilities && detail.value.capabilities.is_terminal)
  }
  return false
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

function ensurePolling() {
  if (!hasActiveWork()) {
    stopPolling()
    return
  }
  if (pollTimer) return
  pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS)
}

async function tick() {
  pollTimer = null
  if (document.hidden) return
  if (!hasActiveWork()) return
  await loadRuns({ silent: true })
  if (drawerVisible.value && currentRunId.value) {
    await loadDetail(currentRunId.value, { silent: true })
  }
  ensurePolling()
}

function onVisibilityChange() {
  if (document.hidden) {
    stopPolling()
    return
  }
  if (hasActiveWork()) {
    stopPolling()
    tick()
  }
}

function applyFilters() {
  page.value = 1
  loadRuns()
  syncQuery()
}

function resetFilters() {
  filters.value = { job_code: '', status: '', source: '', range: [] }
  page.value = 1
  loadRuns()
  syncQuery()
}

function onPageChange(value) {
  page.value = value
  loadRuns()
  syncQuery()
}

function onPageSizeChange(value) {
  pageSize.value = value
  page.value = 1
  loadRuns()
  syncQuery()
}

function manualRefresh() {
  loadRuns()
  if (drawerVisible.value && currentRunId.value) loadDetail(currentRunId.value)
}

function openDetail(row) {
  if (!row || row.run_id === undefined || row.run_id === null) return
  openDetailById(row.run_id)
}

async function openDetailById(runId) {
  const id = Number(runId)
  if (!Number.isFinite(id)) return
  currentRunId.value = id
  detail.value = null
  drawerVisible.value = true
  await loadDetail(id)
  syncQuery()
}

function closeDrawer() {
  drawerVisible.value = false
  onDrawerClosed()
}

function onDrawerClosed() {
  currentRunId.value = null
  detail.value = null
  syncQuery()
  ensurePolling()
}

function readableError(res) {
  if (res && res.httpStatus === 409) return res.message || '当前状态不允许该操作（409）'
  return (res && res.message) || '操作失败'
}

async function runAction(runId, action, doneText) {
  if (runId === undefined || runId === null) return
  actionLoading.value = true
  actionRunId.value = runId
  const res = await action(runId)
  actionLoading.value = false
  actionRunId.value = null
  if (!res.success) {
    error(readableError(res))
    return
  }
  success(doneText)
  await loadRuns({ silent: true })
  if (drawerVisible.value && currentRunId.value === runId) {
    await loadDetail(runId, { silent: true })
  }
  ensurePolling()
}

function onCancel(target) {
  runAction(target && target.run_id, cancelRun, '已提交取消')
}

function onRetry(target) {
  runAction(target && target.run_id, retryRun, '已提交重试')
}

async function copyText(text, doneText) {
  if (!text || text === '-') return
  try {
    await navigator.clipboard.writeText(text)
    success(doneText)
  } catch {
    error('复制失败，请手动选择内容')
  }
}

function downloadResult() {
  const runId = detail.value && detail.value.run_id
  const payload = detail.value ? detail.value.result : null
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `task-run-${runId || 'result'}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

function queryEqual(left, right) {
  const leftKeys = Object.keys(left).sort()
  const rightKeys = Object.keys(right).sort()
  if (leftKeys.length !== rightKeys.length) return false
  return leftKeys.every((key, index) => key === rightKeys[index]
    && String(left[key]) === String(right[key]))
}

function syncQuery() {
  const next = { ...route.query }
  QUERY_KEYS.forEach(key => { delete next[key] })
  if (filters.value.job_code) next.job_code = filters.value.job_code
  if (filters.value.status) next.status = filters.value.status
  if (filters.value.source) next.source = filters.value.source
  const range = Array.isArray(filters.value.range) ? filters.value.range : []
  const from = toEpochSeconds(range[0])
  const to = toEpochSeconds(range[1])
  if (from !== null) next.from = String(from)
  if (to !== null) next.to = String(to)
  if (page.value > 1) next.page = String(page.value)
  if (pageSize.value !== 20) next.page_size = String(pageSize.value)
  if (drawerVisible.value && currentRunId.value) next.run = String(currentRunId.value)

  if (queryEqual(next, route.query)) return
  router.replace({ path: route.path, query: next })
}

function epochToIso(value) {
  if (value === undefined || value === null || value === '') return ''
  const ts = Number(value)
  if (!Number.isFinite(ts)) return ''
  const date = new Date(ts * 1000)
  return Number.isNaN(date.getTime()) ? '' : date.toISOString()
}

function filtersFromQuery() {
  const query = route.query
  const read = (key) => (typeof query[key] === 'string' ? query[key] : '')
  return {
    job_code: read('job_code'),
    status: read('status'),
    source: read('source'),
    range: [epochToIso(query.from), epochToIso(query.to)]
  }
}

function pageFromQuery() {
  const value = Number(route.query.page)
  return Number.isFinite(value) && value > 0 ? value : 1
}

function pageSizeFromQuery() {
  const value = Number(route.query.page_size)
  return Number.isFinite(value) && value > 0 ? value : 20
}

watch(() => route.query.run, (value) => {
  const id = Number(value)
  if (value && Number.isFinite(id)) {
    if (!drawerVisible.value || id !== currentRunId.value) openDetailById(id)
    return
  }
  if (drawerVisible.value) closeDrawer()
  if (currentRunId.value !== null) {
    currentRunId.value = null
    detail.value = null
    ensurePolling()
  }
})

onMounted(async () => {
  filters.value = filtersFromQuery()
  page.value = pageFromQuery()
  pageSize.value = pageSizeFromQuery()
  document.addEventListener('visibilitychange', onVisibilityChange)
  await loadRuns()
  const deepLinkRun = Number(route.query.run)
  if (route.query.run && Number.isFinite(deepLinkRun)) await openDetailById(deepLinkRun)
})

onBeforeUnmount(() => {
  stopPolling()
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.job-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.job-cell__name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
}

.job-cell__code {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.muted {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.run-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: var(--font-size-xs);
  white-space: nowrap;
}

.run-badge--success {
  color: var(--color-success);
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
}

.run-badge--danger {
  color: var(--color-error);
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
}

.run-badge--warning {
  color: var(--color-warning);
  background: var(--color-warning-bg);
  border-color: var(--color-warning-border);
}

.run-badge--info {
  color: var(--color-info);
  background: var(--color-info-bg);
  border-color: var(--color-info-border);
}

.run-badge--primary {
  color: var(--color-primary);
  background: var(--color-primary-bg);
  border-color: var(--color-primary);
}

.run-badge--default {
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border-color: var(--color-border);
}

.run-progress {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.run-progress__track {
  width: 64px;
  height: 6px;
  background: var(--color-bg-tertiary);
  border-radius: 999px;
  overflow: hidden;
  flex-shrink: 0;
}

.run-progress--drawer .run-progress__track {
  width: 100%;
}

.run-progress__bar {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.run-progress__bar--indeterminate {
  width: 100%;
  opacity: 0.35;
}

.run-progress__text {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.row-actions {
  display: flex;
  gap: var(--spacing-xs);
  align-items: center;
}

.drawer-loading {
  padding: var(--spacing-lg);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-sm);
}

.drawer-section {
  margin-bottom: var(--spacing-lg);
}

.drawer-section__title {
  margin: 0 0 var(--spacing-sm);
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.section-head .drawer-section__title {
  margin: 0;
}

.section-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--spacing-sm) var(--spacing-md);
}

.kv-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.kv-item__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.kv-item__value {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  word-break: break-all;
}

.drawer-link {
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-sm);
}

.progress-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
  margin-top: var(--spacing-sm);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.json-block {
  margin: 0;
  padding: var(--spacing-sm);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: var(--font-size-xs);
  line-height: 1.5;
  color: var(--color-text-primary);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow: auto;
}

.count-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-sm);
}

.count-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--spacing-sm);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
}

.count-item__label {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.count-item__value {
  font-size: var(--font-size-md);
  font-weight: 600;
  color: var(--color-text-primary);
}

.errors-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--font-size-xs);
  margin-top: var(--spacing-sm);
}

.errors-table th,
.errors-table td {
  border-bottom: 1px solid var(--color-border);
  padding: var(--spacing-xs) var(--spacing-sm);
  text-align: left;
  vertical-align: top;
}

.errors-table th {
  color: var(--color-text-tertiary);
  font-weight: 500;
}

.error-summary {
  font-size: var(--font-size-sm);
  color: var(--color-error);
  word-break: break-all;
}

.error-stack {
  margin-top: var(--spacing-sm);
}

.error-stack summary {
  cursor: pointer;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.timeline li {
  display: flex;
  gap: var(--spacing-md);
  padding: var(--spacing-xs) 0;
  border-bottom: 1px dashed var(--color-border);
  font-size: var(--font-size-sm);
}

.timeline li:last-child {
  border-bottom: none;
}

.timeline__time {
  min-width: 150px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.timeline__status {
  color: var(--color-text-primary);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}
</style>