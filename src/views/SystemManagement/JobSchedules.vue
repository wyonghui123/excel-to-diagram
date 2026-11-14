<template>
  <PageShell title="作业调度" :show-back-button="false">
    <template #title-bar-actions>
      <AppButton variant="secondary" size="sm" :loading="loading" @click="loadAll">刷新</AppButton>
    </template>

    <div class="schedules">
      <AppAlert v-if="loadError" type="error">{{ loadError }}</AppAlert>

      <AppAlert :type="dispatcherTone" class="dispatcher">
        <div class="dispatcher__row">
          <span class="dispatcher__title">调度器</span>
          <span class="dispatcher__chip" :class="{ 'dispatcher__chip--on': status.enabled }">
            {{ status.enabled ? '已启用' : '未启用' }}
          </span>
          <span class="dispatcher__chip" :class="{ 'dispatcher__chip--on': status.running }">
            {{ status.running ? '运行中' : '未运行' }}
          </span>
          <span v-if="status.dry_run" class="dispatcher__chip">试运行</span>
          <span class="dispatcher__meta">待调度触发器 {{ status.backlog.due_triggers ?? 0 }}</span>
          <span class="dispatcher__meta">排队任务 {{ status.backlog.pending ?? 0 }}</span>
          <span v-if="status.tick_interval" class="dispatcher__meta">轮询间隔 {{ status.tick_interval }} 秒</span>
          <span v-if="status.last_tick_at" class="dispatcher__meta">最近轮询 {{ formatTime(status.last_tick_at) }}</span>
        </div>
      </AppAlert>

      <MetaTable
        :columns="jobColumns"
        :data="jobs"
        :loading="loading"
        :search-placeholder="null"
        :show-header="false"
        :show-pagination="false"
        :id-key="'code'"
        :row-key="'code'"
        empty-type="folder"
        empty-title="暂无作业定义"
        empty-description="作业由后端注册表注入，请确认服务启动日志"
      >
        <template #cell-job="{ row }">
          <div class="job-cell">
            <span class="job-cell__name">{{ row.name || '-' }}</span>
            <span class="job-cell__code">{{ row.code }} · {{ row.handler }}</span>
          </div>
        </template>

        <template #cell-status="{ row }">
          <span class="job-badge" :class="`job-badge--${jobStatusTone(row)}`">{{ jobStatusLabel(row) }}</span>
        </template>

        <template #cell-available="{ row }">
          <span class="job-badge" :class="`job-badge--${row.available ? 'success' : 'danger'}`">
            {{ row.available ? '可用' : '执行器缺失' }}
          </span>
        </template>

        <template #cell-last_run="{ row }">
          <span v-if="row.last_run" class="muted">
            {{ statusLabel(row.last_run.status) }} · {{ formatTime(row.last_run.created_at) }}
          </span>
          <span v-else class="muted">暂无执行</span>
        </template>

        <template #cell-next_run="{ row }">
          <span v-if="row.next_run && row.next_run.next_run_at" class="muted">
            {{ triggerTypeLabel(row.next_run.trigger_type) }} · {{ formatTime(row.next_run.next_run_at) }}
          </span>
          <span v-else class="muted">暂无计划</span>
        </template>

        <template #cell-actions="{ row }">
          <div class="row-actions">
            <AppButton
              variant="text"
              size="xs"
              :disabled="!canRun(row)"
              @click="openRun(row)"
            >立即运行</AppButton>
            <AppButton variant="text" size="xs" @click="openEdit(row)">设置</AppButton>
            <AppButton variant="text" size="xs" @click="openTriggers(row)">
              触发器<template v-if="row.trigger_count">（{{ row.trigger_count }}）</template>
            </AppButton>
            <router-link class="row-link" :to="`/system/task-runs?job_code=${row.code}`">执行记录</router-link>
          </div>
        </template>
      </MetaTable>
    </div>

    <!-- 作业设置 -->
    <Drawer v-model="editVisible" title="作业设置" width="620px">
      <div v-if="activeJob" class="form-block">
        <div class="job-head">
          <div>
            <div class="job-head__name">{{ activeJob.name || activeJob.code }}</div>
            <div class="job-head__code">{{ activeJob.code }} · {{ activeJob.handler }} · {{ activeJob.executor_type }}</div>
          </div>
          <span class="job-badge" :class="`job-badge--${jobStatusTone(activeJob)}`">{{ jobStatusLabel(activeJob) }}</span>
        </div>
        <MetaForm v-model="basicForm" :fields="basicFields" label-position="top" />
        <div v-if="hasDefaultParams" class="readonly-block">
          <div class="readonly-block__title">默认参数（只读）</div>
          <div class="readonly-block__hint">密钥类字段已脱敏；默认参数由作业注册决定，本页不修改。</div>
          <pre class="json-block">{{ defaultParamsText }}</pre>
        </div>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <AppButton variant="secondary" size="sm" @click="editVisible = false">取消</AppButton>
          <AppButton variant="primary" size="sm" :loading="saving" @click="saveJob">保存</AppButton>
        </div>
      </template>
    </Drawer>

    <!-- 立即运行 -->
    <Drawer v-model="runVisible" title="立即运行" width="560px">
      <div v-if="activeJob" class="form-block">
        <div class="job-head">
          <div>
            <div class="job-head__name">{{ activeJob.name || activeJob.code }}</div>
            <div class="job-head__code">{{ activeJob.code }}</div>
          </div>
        </div>
        <AppAlert v-if="!canRun(activeJob)" type="warning">
          作业当前不可运行（已暂停或执行器未注册）。
        </AppAlert>
        <MetaForm
          v-if="paramFields.length > 0"
          v-model="runForm"
          :fields="paramFields"
          label-position="top"
        />
        <div v-else class="muted">该作业无参数，可直接运行。</div>
      </div>
      <template #footer>
        <div class="drawer-footer">
          <AppButton variant="secondary" size="sm" @click="runVisible = false">取消</AppButton>
          <AppButton
            variant="primary"
            size="sm"
            :loading="running"
            :disabled="activeJob ? !canRun(activeJob) : true"
            @click="submitRun"
          >运行</AppButton>
        </div>
      </template>
    </Drawer>

    <!-- 触发器管理 -->
    <Drawer v-model="triggerVisible" title="触发器管理" width="900px">
      <div v-if="activeJob" class="form-block">
        <div class="job-head">
          <div>
            <div class="job-head__name">{{ activeJob.name || activeJob.code }}</div>
            <div class="job-head__code">{{ activeJob.code }}</div>
          </div>
        </div>

        <div class="sub-block">
          <div class="sub-block__title">
            {{ editingTriggerId ? `编辑触发器 #${editingTriggerId}` : '新建触发器' }}
          </div>
          <MetaForm v-model="triggerForm" :fields="triggerFields" label-position="top">
            <template #field-run_at>
              <DateTimePicker
                :model-value="triggerForm.run_at"
                show-time
                @update:model-value="onRunAtChange"
              />
            </template>
          </MetaForm>
          <div class="sub-block__actions">
            <AppButton variant="primary" size="sm" :loading="creatingTrigger" @click="submitTrigger">
              {{ editingTriggerId ? '保存' : '创建' }}
            </AppButton>
            <AppButton
              v-if="editingTriggerId"
              variant="secondary"
              size="sm"
              @click="cancelTriggerEdit"
            >取消编辑</AppButton>
          </div>
          <div class="muted sub-block__hint">下次运行时间由后端调度器同源推算，保存后展示，页面不做本地预演。</div>
        </div>

        <div class="sub-block">
          <div class="sub-block__title">现有触发器</div>
          <MetaTable
            :columns="triggerColumns"
            :data="triggers"
            :loading="triggerLoading"
            :search-placeholder="null"
            :show-header="false"
            :show-pagination="false"
            :id-key="'trigger_id'"
            :row-key="'trigger_id'"
            empty-type="folder"
            empty-title="暂无触发器"
            empty-description="按需创建定时、周期或一次性触发器"
          >
            <template #cell-trigger_type="{ row }">
              <span>{{ triggerTypeLabel(row.trigger_type) }}</span>
            </template>
            <template #cell-schedule="{ row }">
              <div class="mono">{{ triggerScheduleText(row) }}</div>
              <div v-if="row.next_runs_preview && row.next_runs_preview.length > 1" class="trigger-preview">
                未来 {{ formatShortTime(row.next_runs_preview[0]) }} · {{ formatShortTime(row.next_runs_preview[1]) }}
                <template v-if="row.next_runs_preview.length > 2">
                  · {{ formatShortTime(row.next_runs_preview[2]) }} 等 {{ row.next_runs_preview.length }} 次
                </template>
              </div>
            </template>
            <template #cell-next_run_at="{ row }">
              <span class="muted">{{ formatTime(row.next_run_at) }}</span>
            </template>
            <template #cell-last_run="{ row }">
              <template v-if="row.last_run">
                <span class="job-badge" :class="`job-badge--${lastRunTone(row.last_run)}`">
                  {{ statusLabel(row.last_run.status) }}
                </span>
                <div class="trigger-preview">{{ formatTime(row.last_run.created_at) }}</div>
              </template>
              <span v-else class="muted">暂无执行</span>
            </template>
            <template #cell-enabled="{ row }">
              <span class="job-badge" :class="`job-badge--${triggerStateTone(row)}`">
                {{ triggerStateLabel(row) }}
              </span>
            </template>
            <template #cell-actions="{ row }">
              <div class="row-actions">
                <AppButton variant="text" size="xs" @click="openTriggerEdit(row)">编辑</AppButton>
                <AppButton variant="text" size="xs" @click="toggleTrigger(row)">
                  {{ row.enabled ? '停用' : '启用' }}
                </AppButton>
                <AppButton variant="text" size="xs" @click="removeTrigger(row)">删除</AppButton>
              </div>
            </template>
          </MetaTable>
        </div>
      </div>
    </Drawer>
  </PageShell>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AppAlert,
  AppButton,
  DateTimePicker,
  Drawer,
  MetaForm,
  MetaTable,
  PageShell
} from '@/components/common'
import { useMessage } from '@/composables/useMessage'
import {
  createTrigger,
  deleteTrigger,
  fetchDispatcherStatus,
  fetchJobs,
  fetchTriggers,
  patchJob,
  runNow,
  updateTrigger
} from '@/services/jobService'
import { buildDefaults, schemaToFields, stripRedacted, toEpochSeconds } from '@/utils/jobParams'
import { statusLabel, statusTone, triggerTypeLabel } from '@/utils/jobRunStatus'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const loading = ref(false)
const loadError = ref('')
const saving = ref(false)
const running = ref(false)
const triggerLoading = ref(false)
const creatingTrigger = ref(false)

const jobs = ref([])
const triggers = ref([])
const activeJob = ref(null)

const status = reactive({
  enabled: false,
  dry_run: false,
  running: false,
  tick_interval: null,
  last_tick_at: null,
  backlog: { pending: 0, due_triggers: 0 }
})

const dispatcherTone = computed(() => (status.enabled && status.running ? 'success' : 'warning'))

const jobColumns = [
  { key: 'job', label: '作业', slot: true, width: '260px' },
  { key: 'status', label: '状态', slot: true, width: '90px' },
  { key: 'available', label: '执行器', slot: true, width: '110px' },
  { key: 'trigger_count', label: '触发器', width: '80px' },
  { key: 'last_run', label: '最近执行', slot: true, width: '190px' },
  { key: 'next_run', label: '下次运行', slot: true, width: '190px' },
  { key: 'actions', label: '操作', slot: true, width: '250px' }
]

const triggerColumns = [
  { key: 'trigger_id', label: 'ID', width: '60px' },
  { key: 'trigger_type', label: '类型', slot: true, width: '76px' },
  { key: 'schedule', label: '调度表达式', slot: true, width: '210px' },
  { key: 'next_run_at', label: '下次运行', slot: true, width: '140px' },
  { key: 'last_run', label: '上次执行', slot: true, width: '140px' },
  { key: 'enabled', label: '状态', slot: true, width: '120px' },
  { key: 'actions', label: '操作', slot: true, width: '170px' }
]

const JOB_STATUS_OPTIONS = [
  { label: '启用', value: 'active' },
  { label: '暂停', value: 'paused' }
]

const TRIGGER_TYPE_OPTIONS = [
  { label: '定时（cron）', value: 'cron' },
  { label: '周期（interval）', value: 'interval' },
  { label: '一次性（once）', value: 'once' }
]

// ── 作业设置 ──────────────────────────────────────────────────────────────

const editVisible = ref(false)
const basicForm = reactive({})

const basicFields = computed(() => [
  { key: 'name', label: '名称', type: 'text', required: true },
  { key: 'description', label: '说明', type: 'textarea' },
  { key: 'status', label: '状态', type: 'select', options: JOB_STATUS_OPTIONS },
  { key: 'timeout_seconds', label: '超时（秒）', type: 'number' },
  { key: 'max_attempts', label: '最大尝试次数', type: 'number' },
  { key: 'backoff_seconds', label: '重试退避（秒）', type: 'number' }
])

const hasDefaultParams = computed(() => {
  const params = activeJob.value && activeJob.value.default_params
  return Boolean(params && Object.keys(params).length > 0)
})

const defaultParamsText = computed(() => {
  const params = (activeJob.value && activeJob.value.default_params) || {}
  return JSON.stringify(params, null, 2)
})

function jobStatusLabel(job) {
  return job && job.status !== 'active' ? '已暂停' : '已启用'
}

function jobStatusTone(job) {
  return job && job.status !== 'active' ? 'warning' : 'success'
}

function canRun(job) {
  return Boolean(job && job.capabilities && job.capabilities.can_run)
}

function openEdit(job) {
  activeJob.value = job
  Object.keys(basicForm).forEach((key) => { delete basicForm[key] })
  Object.assign(basicForm, {
    name: job.name || '',
    description: job.description || '',
    status: job.status || 'active',
    timeout_seconds: job.timeout_seconds ?? null,
    max_attempts: job.max_attempts ?? null,
    backoff_seconds: job.backoff_seconds ?? null
  })
  editVisible.value = true
}

async function saveJob() {
  if (!activeJob.value) return
  const payload = {
    name: String(basicForm.name || '').trim(),
    description: basicForm.description || '',
    status: basicForm.status || 'active'
  }
  for (const key of ['timeout_seconds', 'max_attempts', 'backoff_seconds']) {
    const value = basicForm[key]
    if (value !== '' && value !== null && value !== undefined) payload[key] = Number(value)
  }
  saving.value = true
  const res = await patchJob(activeJob.value.code, payload)
  saving.value = false
  if (!res || !res.success) {
    message.error((res && res.message) || '作业设置保存失败')
    return
  }
  message.saved('作业设置')
  editVisible.value = false
  await loadAll()
}

// ── 立即运行 ──────────────────────────────────────────────────────────────

const runVisible = ref(false)
const runForm = reactive({})

const paramFields = computed(() => schemaToFields(activeJob.value && activeJob.value.params_schema))

function openRun(job) {
  if (!canRun(job)) return
  activeJob.value = job
  Object.keys(runForm).forEach((key) => { delete runForm[key] })
  const defaults = buildDefaults(job.params_schema, stripRedacted(job.default_params))
  Object.assign(runForm, defaults)
  runVisible.value = true
}

const RUN_ERRORS = {
  job_paused: '作业已暂停，无法运行',
  job_unavailable: '执行器未注册，无法运行',
  job_not_found: '作业不存在或已下线'
}

async function submitRun() {
  if (!activeJob.value) return
  const params = stripRedacted(runForm)
  const payload = Object.keys(params).length > 0 ? { params } : {}
  running.value = true
  const res = await runNow(activeJob.value.code, payload)
  running.value = false
  if (!res || !res.success) {
    message.error(RUN_ERRORS[res && res.code] || (res && res.message) || '提交执行失败')
    return
  }
  const runId = res.data && res.data.run_id
  message.success(runId ? `已提交执行 #${runId}` : '已提交执行')
  runVisible.value = false
  await loadAll()
  if (runId) router.push(`/system/task-runs?run=${runId}`)
}

// ── 触发器 ───────────────────────────────────────────────────────────────

const triggerVisible = ref(false)
const triggerForm = reactive({ trigger_type: 'cron' })
const editingTriggerId = ref(null)

const triggerFields = computed(() => {
  const fields = [{
    key: 'trigger_type',
    label: '触发类型',
    type: 'select',
    options: TRIGGER_TYPE_OPTIONS,
    disabled: Boolean(editingTriggerId.value)
  }]
  if (triggerForm.trigger_type === 'cron') {
    fields.push({
      key: 'cron_expr',
      label: 'cron 表达式',
      type: 'text',
      required: true,
      placeholder: '分 时 日 月 周，例如 0 2 * * *'
    })
  }
  if (triggerForm.trigger_type === 'interval') {
    fields.push({
      key: 'interval_seconds',
      label: '间隔（秒）',
      type: 'number',
      required: true,
      placeholder: '例如 3600'
    })
  }
  if (triggerForm.trigger_type === 'once') {
    fields.push({ key: 'run_at', label: '运行时间', slot: true, required: true })
  }
  return fields
})

const TRIGGER_ERRORS = {
  invalid_cron_expr: 'cron 表达式不合法',
  invalid_interval: '周期间隔必须为正整数秒',
  invalid_schedule: '调度参数不完整，请检查运行时间',
  run_at_in_past: '一次性运行时间必须晚于当前时间',
  invalid_params: '参数覆盖不合法'
}

function onRunAtChange(value) {
  triggerForm.run_at = value
}

function resetTriggerForm() {
  editingTriggerId.value = null
  Object.keys(triggerForm).forEach((key) => { delete triggerForm[key] })
  triggerForm.trigger_type = 'cron'
  triggerForm.cron_expr = ''
  triggerForm.interval_seconds = null
  triggerForm.run_at = null
}

function openTriggerEdit(trigger) {
  editingTriggerId.value = trigger.trigger_id
  Object.keys(triggerForm).forEach((key) => { delete triggerForm[key] })
  triggerForm.trigger_type = trigger.trigger_type
  triggerForm.cron_expr = trigger.cron_expr || ''
  triggerForm.interval_seconds = trigger.interval_seconds ?? null
  triggerForm.run_at = trigger.next_run_at
    ? new Date(trigger.next_run_at * 1000).toISOString()
    : null
}

function cancelTriggerEdit() {
  resetTriggerForm()
}

async function openTriggers(job) {
  activeJob.value = job
  resetTriggerForm()
  triggerVisible.value = true
  await loadTriggers()
}

async function loadTriggers() {
  if (!activeJob.value) return
  triggerLoading.value = true
  const res = await fetchTriggers(activeJob.value.code)
  triggerLoading.value = false
  if (!res || !res.success) {
    message.error((res && res.message) || '触发器加载失败')
    triggers.value = []
    return
  }
  const data = res.data || {}
  triggers.value = data.items || []
}

async function submitTrigger() {
  if (!activeJob.value) return
  const editing = editingTriggerId.value
  const payload = {}
  if (triggerForm.trigger_type === 'cron') {
    const expr = String(triggerForm.cron_expr || '').trim()
    if (!expr) {
      message.error('请填写 cron 表达式')
      return
    }
    payload.cron_expr = expr
  }
  if (triggerForm.trigger_type === 'interval') {
    const seconds = Number(triggerForm.interval_seconds)
    if (!Number.isFinite(seconds) || seconds <= 0) {
      message.error('请填写正整数间隔秒数')
      return
    }
    payload.interval_seconds = seconds
    // 编辑间隔时同步重置下次运行，避免继续沿用旧节奏
    if (editing) payload.next_run_at = Math.floor(Date.now() / 1000) + seconds
  }
  if (triggerForm.trigger_type === 'once') {
    const runAt = toEpochSeconds(triggerForm.run_at)
    if (runAt === null) {
      message.error('请选择运行时间')
      return
    }
    if (runAt <= Math.floor(Date.now() / 1000)) {
      message.error(TRIGGER_ERRORS.run_at_in_past)
      return
    }
    payload.next_run_at = runAt
    if (!editing) {
      delete payload.next_run_at
      payload.run_at = runAt
    }
  }
  creatingTrigger.value = true
  const res = editing
    ? await updateTrigger(editing, payload)
    : await createTrigger(activeJob.value.code, {
      trigger_type: triggerForm.trigger_type, enabled: true, ...payload
    })
  creatingTrigger.value = false
  if (!res || !res.success) {
    message.error(TRIGGER_ERRORS[res && res.code] || (res && res.message)
      || (editing ? '触发器更新失败' : '触发器创建失败'))
    return
  }
  if (editing) {
    message.saved('触发器')
  } else {
    message.created('触发器')
  }
  resetTriggerForm()
  await Promise.all([loadTriggers(), loadAll()])
}

async function toggleTrigger(trigger) {
  const res = await updateTrigger(trigger.trigger_id, { enabled: !trigger.enabled })
  if (!res || !res.success) {
    message.error((res && res.message) || '触发器状态更新失败')
    return
  }
  message.success(trigger.enabled ? '触发器已停用' : '触发器已启用')
  await Promise.all([loadTriggers(), loadAll()])
}

async function removeTrigger(trigger) {
  const ok = await message.confirm({
    title: '删除触发器',
    content: `确认删除触发器 #${trigger.trigger_id}？已产生的执行记录不受影响。`
  })
  if (!ok) return
  const res = await deleteTrigger(trigger.trigger_id)
  if (!res || !res.success) {
    message.error((res && res.message) || '触发器删除失败')
    return
  }
  message.deleted('触发器')
  await Promise.all([loadTriggers(), loadAll()])
}

function triggerScheduleText(trigger) {
  if (trigger.trigger_type === 'cron') return trigger.cron_expr || '-'
  if (trigger.trigger_type === 'interval') {
    return trigger.interval_seconds ? `每 ${trigger.interval_seconds} 秒` : '-'
  }
  return formatTime(trigger.next_run_at)
}

function triggerStateLabel(trigger) {
  const finishedOnce = trigger.trigger_type === 'once'
    && !trigger.enabled && !trigger.next_run_at
  if (finishedOnce) return '已完成（一次性）'
  return trigger.enabled ? '启用' : '停用'
}

function triggerStateTone(trigger) {
  const finishedOnce = trigger.trigger_type === 'once'
    && !trigger.enabled && !trigger.next_run_at
  if (finishedOnce) return 'info'
  return trigger.enabled ? 'success' : 'default'
}

function lastRunTone(run) {
  return statusTone(run && run.status)
}

function formatShortTime(value) {
  const full = formatTime(value)
  return full === '-' ? '-' : full.slice(5)
}

// ── 数据加载 ─────────────────────────────────────────────────────────────

async function loadAll() {
  loading.value = true
  const [jobsRes, statusRes] = await Promise.all([fetchJobs(), fetchDispatcherStatus()])
  loading.value = false

  if (!jobsRes || !jobsRes.success) {
    loadError.value = (jobsRes && jobsRes.message) || '作业列表加载失败'
  } else {
    loadError.value = ''
    const data = jobsRes.data || {}
    jobs.value = data.items || []
    if (activeJob.value) {
      const refreshed = jobs.value.find((item) => item.code === activeJob.value.code)
      if (refreshed) activeJob.value = refreshed
    }
  }

  const snapshot = (statusRes && statusRes.success && statusRes.data) || {}
  status.enabled = Boolean(snapshot.enabled)
  status.dry_run = Boolean(snapshot.dry_run)
  status.running = Boolean(snapshot.running)
  status.tick_interval = snapshot.tick_interval ?? null
  status.last_tick_at = snapshot.last_tick_at ?? null
  status.backlog = snapshot.backlog || { pending: 0, due_triggers: 0 }
}

function formatTime(value) {
  if (value === null || value === undefined || value === '') return '-'
  let stamp
  if (typeof value === 'number') {
    stamp = value > 1e12 ? value : value * 1000
  } else {
    const parsed = Date.parse(String(value))
    if (Number.isNaN(parsed)) return '-'
    stamp = parsed
  }
  const date = new Date(stamp)
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(async () => {
  await loadAll()
  const code = route.query.job
  if (code) {
    const target = jobs.value.find((item) => item.code === String(code))
    if (target) openEdit(target)
  }
})
</script>

<style scoped lang="scss">
.schedules {
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.dispatcher {
  flex-shrink: 0;
}

.dispatcher__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.dispatcher__title {
  font-weight: 600;
}

.dispatcher__chip {
  padding: 1px 8px;
  border-radius: var(--radius-full, 999px);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-light);
  font-size: var(--font-size-xs);
}

.dispatcher__chip--on {
  color: var(--color-success, #16a34a);
  border-color: var(--color-success-border, #b7ebc6);
  background: var(--color-success-bg, #f0fbf3);
}

.dispatcher__meta {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.job-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.job-cell__name {
  font-weight: 500;
  color: var(--color-text-primary);
}

.job-cell__code {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: var(--radius-full, 999px);
  font-size: var(--font-size-xs);
  border: 1px solid var(--color-border-light);
  background: var(--color-bg-secondary);
}

.job-badge--success {
  color: var(--color-success, #16a34a);
  border-color: var(--color-success-border, #b7ebc6);
  background: var(--color-success-bg, #f0fbf3);
}

.job-badge--warning {
  color: var(--color-warning, #d97706);
  border-color: var(--color-warning-border, #fde7b0);
  background: var(--color-warning-bg, #fffaeb);
}

.job-badge--danger {
  color: var(--color-danger, #dc2626);
  border-color: var(--color-danger-border, #f7c6c6);
  background: var(--color-danger-bg, #fef2f2);
}

.job-badge--info {
  color: var(--color-primary, #2563eb);
  border-color: var(--color-primary-border, #bfdbfe);
  background: var(--color-primary-bg, #eff6ff);
}

.job-badge--primary {
  color: var(--color-primary, #2563eb);
  border-color: var(--color-primary-border, #bfdbfe);
  background: var(--color-primary-bg, #eff6ff);
}

.trigger-preview {
  margin-top: 2px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.row-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.row-link {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  text-decoration: none;
}

.row-link:hover {
  text-decoration: underline;
}

.muted {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}

.mono {
  font-family: var(--font-family-mono, monospace);
  font-size: var(--font-size-xs);
}

.form-block {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.job-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-sm);
  padding-bottom: var(--spacing-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.job-head__name {
  font-weight: 600;
}

.job-head__code {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.readonly-block__title {
  font-weight: 600;
  margin-bottom: var(--spacing-xs);
}

.readonly-block__hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  margin-bottom: var(--spacing-xs);
}

.json-block {
  margin: 0;
  padding: var(--spacing-sm);
  border-radius: var(--radius-md, 8px);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-light);
  font-family: var(--font-family-mono, monospace);
  font-size: var(--font-size-xs);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow: auto;
}

.sub-block {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--color-border-light);
}

.sub-block__title {
  font-weight: 600;
}

.sub-block__actions {
  display: flex;
  justify-content: flex-end;
}

.sub-block__hint {
  margin-top: calc(var(--spacing-xs) * -1);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}
</style>