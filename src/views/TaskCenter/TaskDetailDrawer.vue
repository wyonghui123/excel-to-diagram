<template>
  <AppModal :model-value="visible" :title="task?.title || '任务详情'" width="720px" @close="$emit('close')">
    <div v-if="loading" data-test="loading" class="tdd-state">加载中…</div>
    <div v-else-if="error" data-test="error" class="tdd-state tdd-error">{{ error }}</div>
    <div v-else-if="task" class="tdd-body">
      <div class="tdd-head">
        <span data-test="task-status" class="tdd-chip" :class="`tdd-chip--${statusTone(task)}`">
          {{ statusLabel(task) }}
        </span>
        <span class="tdd-chip tdd-chip--muted">{{ task.type }}</span>
        <span class="tdd-chip tdd-chip--muted">{{ task.executor_type }}</span>
        <!-- [M5-5] 阶段进度：stage_no + 快照去重阶段集合 -->
        <span v-if="stageProgress" data-test="stage-progress" class="tdd-chip tdd-chip--info">
          阶段 {{ stageProgress.current }}/{{ stageProgress.total }}
        </span>
        <span v-if="pause" data-test="pause-badge" class="tdd-chip" :class="`tdd-chip--${pause.tone}`">
          {{ pause.label }}
        </span>
      </div>

      <dl class="tdd-fields">
        <div><dt>认领人</dt><dd>{{ task.executor_assignee || '—' }}</dd></div>
        <div><dt>到期</dt><dd>
          {{ task.due_at || '—' }}
          <span v-if="sla" data-test="sla-countdown" class="tdd-countdown" :class="{ 'tdd-countdown--overdue': sla.overdue }">
            · {{ sla.label }}
          </span>
        </dd></div>
        <div><dt>创建人</dt><dd>{{ task.created_by || '—' }}</dd></div>
        <div>
          <dt>业务单据</dt>
          <dd>
            <template v-if="docRefType && docRefId">
              <span>{{ docRefType }} / {{ docRefId }}</span>
              <button type="button" data-test="open-doc" class="tdd-link" @click="openDoc">查看单据</button>
            </template>
            <template v-else>{{ task.doc_ref || '—' }}</template>
          </dd>
        </div>
      </dl>

      <div v-if="canClaim" class="tdd-actions">
        <AppButton data-test="claim-btn" :disabled="claiming" @click="onClaim">
          {{ claiming ? '认领中…' : '认领' }}
        </AppButton>
        <span v-if="claimMsg" class="tdd-claim-msg">{{ claimMsg }}</span>
      </div>

      <!-- M4-2、M4-5 参与人进度（通用能力，非审批任务同样展示） -->
      <div v-if="participation.participants.length" data-test="participants-panel" class="tdd-m4">
        <h4 class="tdd-section">
          参与人进度
          <span class="tdd-chip tdd-chip--muted" data-test="completion-mode">{{ completionModeLabel }}</span>
        </h4>
        <div class="tdd-counts" data-test="participation-counts">
          <span v-for="(n, key) in participation.counts" :key="key">{{ outcomeLabel(key) }} {{ n }}</span>
        </div>
        <ul class="tdd-participants">
          <li v-for="p in participation.participants" :key="p.id" data-test="participant-row" class="tdd-participant">
            {{ p.participant }} · {{ p.role }} · {{ outcomeLabel(p.outcome) }}
            <template v-if="p.on_behalf_of"> · 代 {{ p.on_behalf_of }}</template>
          </li>
        </ul>
        <div
          v-if="participation.completionMode === 'all' && participation.remaining.length"
          data-test="participation-remaining"
          class="tdd-decision-hint"
        >
          会签未齐，待 {{ participation.remaining.join('、') }} 表态
        </div>
      </div>

      <!-- M4-1、M4-5 改派（无权限不渲染） -->
      <div v-if="canReassign" data-test="reassign-panel" class="tdd-m4">
        <h4 class="tdd-section">改派</h4>
        <input v-model="reassignTarget" data-test="reassign-target" class="tdd-input" placeholder="目标执行人" />
        <input v-model="reassignReason" data-test="reassign-reason" class="tdd-input" placeholder="改派原因（必填）" />
        <div class="tdd-actions">
          <AppButton data-test="reassign-btn" :disabled="!!reassigning" @click="onReassign">
            {{ reassigning ? '提交中…' : '确认改派' }}
          </AppButton>
          <span v-if="reassignMsg" data-test="reassign-msg" class="tdd-claim-msg" :class="{ 'tdd-error': reassignFailed }">
            {{ reassignMsg }}
          </span>
        </div>
      </div>

      <!-- M4-2、M4-5 加签与会签（无权限不渲染） -->
      <div v-if="canParticipate" data-test="participate-panel" class="tdd-m4">
        <h4 class="tdd-section">加签</h4>
        <input v-model="participantInput" data-test="participant-input" class="tdd-input" placeholder="加签人（留空 = 加自己）" />
        <label class="tdd-check">
          <input v-model="requireAll" type="checkbox" data-test="require-all" />
          转会签（全部参与人通过才生效）
        </label>
        <div class="tdd-actions">
          <AppButton data-test="participate-btn" :disabled="!!participating" @click="onParticipate">
            {{ participating ? '提交中…' : '加签' }}
          </AppButton>
          <span v-if="participateMsg" data-test="participate-msg" class="tdd-claim-msg" :class="{ 'tdd-error': participateFailed }">
            {{ participateMsg }}
          </span>
        </div>
      </div>

      <!-- M4-3、M4-5 我的委托（用户级配置，随抽屉展开） -->
      <div v-if="currentActor" data-test="delegation-panel" class="tdd-m4">
        <h4 class="tdd-section">我的委托</h4>
        <ul v-if="delegations.length" class="tdd-participants">
          <li v-for="d in delegations" :key="d.id" data-test="delegation-row" class="tdd-participant">
            {{ d.delegate }} · {{ d.scope_type || 'any' }}<template v-if="d.scope_value">（{{ d.scope_value }}）</template>
            · {{ d.effective_from || '即时' }} → {{ d.effective_to || '长期' }}
            <button type="button" class="tdd-link" data-test="delegation-revoke" @click="onRevokeDelegation(d.id)">撤销</button>
          </li>
        </ul>
        <div v-else data-test="no-delegations" class="tdd-sub">暂无委托</div>
        <div class="tdd-form">
          <input v-model="delegationForm.delegate" data-test="delegate-input" class="tdd-input" placeholder="受托人" />
          <select v-model="delegationForm.scope_type" data-test="delegate-scope" class="tdd-input">
            <option value="any">全部任务</option>
            <option value="app">按应用</option>
            <option value="type">按任务类型</option>
            <option value="doc_ref_type">按单据类型</option>
          </select>
          <input
            v-if="delegationForm.scope_type !== 'any'"
            v-model="delegationForm.scope_value"
            data-test="delegate-scope-value"
            class="tdd-input"
            placeholder="范围值"
          />
          <input v-model="delegationForm.effective_from" data-test="delegate-from" class="tdd-input" type="datetime-local" />
          <input v-model="delegationForm.effective_to" data-test="delegate-to" class="tdd-input" type="datetime-local" />
          <div class="tdd-actions">
            <AppButton data-test="delegate-create-btn" :disabled="!!delegating" @click="onCreateDelegation">
              {{ delegating ? '提交中…' : '新增委托' }}
            </AppButton>
            <span v-if="delegationMsg" data-test="delegation-msg" class="tdd-claim-msg" :class="{ 'tdd-error': delegationFailed }">
              {{ delegationMsg }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="isApproval" data-test="decision-panel" class="tdd-decision">
        <h4 class="tdd-section">审批</h4>

        <!-- [M5-5] 阶段动作三态：approve 人工决策、auto 自动通过、notify 只读知会（无快照也显示） -->
        <div class="tdd-policy-head">
          <span data-test="action-type" class="tdd-chip" :class="`tdd-chip--${actionTypeTone}`">
            {{ actionTypeLabel }}
          </span>
        </div>

        <div v-if="policySnapshot" class="tdd-policy" data-test="policy-snapshot">
          <div class="tdd-policy-head">
            <span class="tdd-chip tdd-chip--info">
              {{ policySnapshot.policy_name || policySnapshot.policy_code || '审批策略' }}
            </span>
            <span v-if="policySnapshot.policy_version" class="tdd-chip tdd-chip--muted">
              v{{ policySnapshot.policy_version }}
            </span>
            <span v-if="policySnapshot.hit_policy === false" class="tdd-chip tdd-chip--warning">未命中策略</span>
          </div>

          <!-- [M5-5] 取人依据与空池原因（executor_config 由取人器写入） -->
          <div
            v-if="assignExplain.length || assignReasonLabel || assignSource"
            data-test="assign-explain"
            class="tdd-conditions"
          >
            <div class="tdd-sub">
              取人依据<template v-if="assignSource"> · {{ assignSource }}</template>
            </div>
            <div
              v-for="(a, i) in assignExplain"
              :key="i"
              class="tdd-cond"
              :class="{ 'tdd-cond--fail': a.passed === false }"
            >
              {{ a.field }} {{ a.op }} {{ a.expected }}（实际 {{ a.actual }}）
              <span v-if="a.step_no" class="tdd-chain-meta">· 步骤 {{ a.step_no }}</span>
            </div>
            <div v-if="assignReasonLabel" data-test="assign-reason" class="tdd-cond tdd-cond--fail">
              空池原因：{{ assignReasonLabel }}
            </div>
          </div>

          <ol v-if="approvalSteps.length" data-test="approval-chain" class="tdd-chain">
            <li v-for="s in approvalSteps" :key="s.step_no" class="tdd-chain-step">
              <span class="tdd-chain-no">{{ s.step_no }}</span>
              <span class="tdd-chain-body">
                <span>{{ stepApprover(s) }}</span>
                <span class="tdd-chain-meta">
                  {{ approveModeLabel(s.approve_mode) }}<template v-if="s.sla_hours"> · {{ s.sla_hours }}h</template>
                </span>
              </span>
            </li>
          </ol>

          <div v-if="conditionExplains.length" data-test="condition-explain" class="tdd-conditions">
            <div class="tdd-sub">命中依据</div>
            <div
              v-for="(c, i) in conditionExplains"
              :key="i"
              class="tdd-cond"
              :class="{ 'tdd-cond--fail': c.passed === false }"
            >
              {{ c.field }} {{ c.op }} {{ c.expected }}（实际 {{ c.actual }}）
            </div>
          </div>
        </div>

        <div v-if="canDecide" class="tdd-decide-form">
          <textarea
            v-model="comment"
            data-test="decision-comment"
            class="tdd-textarea"
            rows="2"
            placeholder="审批意见（驳回必填）"
          />
          <label class="tdd-check">
            <input v-model="allowRework" type="checkbox" data-test="allow-rework" />
            驳回后退回修改（允许重新提交）
          </label>
          <div class="tdd-actions">
            <AppButton v-if="decisionActions?.approve" data-test="approve-btn" :disabled="!!deciding" @click="onDecide('approve')">
              {{ deciding === 'approve' ? '提交中…' : '通过' }}
            </AppButton>
            <AppButton v-if="decisionActions?.reject" data-test="reject-btn" :disabled="!!deciding" @click="onDecide('reject')">
              {{ deciding === 'reject' ? '提交中…' : '驳回' }}
            </AppButton>
          </div>
        </div>
        <div v-else-if="isNotifyOnly" class="tdd-decision-hint" data-test="notify-hint">
          知会（只读）：本阶段无需决策，不计入会签
        </div>
        <div v-else-if="decideHint" class="tdd-decision-hint" data-test="decision-hint">{{ decideHint }}</div>
        <div v-if="decideMsg" data-test="decision-msg" class="tdd-claim-msg" :class="{ 'tdd-error': decideFailed }">
          {{ decideMsg }}
        </div>
      </div>

      <h4 class="tdd-section">活动流</h4>
      <ul v-if="events.length" class="tdd-timeline">
        <li v-for="ev in events" :key="ev.id" data-test="event-item" class="tdd-event">
          <span class="tdd-event-time">{{ ev.occurred_at }}</span>
          <span class="tdd-event-body">
            <span class="tdd-event-type">{{ ev.event_type }}</span>
            <span v-if="ev.from_status || ev.to_status" class="tdd-event-move">
              {{ ev.from_status || '—' }} → {{ ev.to_status || '—' }}
            </span>
            <span class="tdd-event-actor">{{ ev.actor || 'system' }}（{{ ev.actor_kind || 'system' }}）</span>
            <span v-if="ev.reason" class="tdd-event-reason">{{ ev.reason }}</span>
          </span>
        </li>
      </ul>
      <div v-else data-test="no-events" class="tdd-state">暂无活动记录</div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { AppModal, AppButton } from '@/components/common'
import { fetchTaskDetail, fetchTaskEvents, claimTask, derivePause, submitDecision,
  fetchParticipations, reassignTask, participateTask,
  fetchDelegations, createDelegation, revokeDelegation,
  normalizeParticipations, canReassignTask, formatSlaRemaining, validateDelegationForm } from '@/services/taskService'
import { statusLabel, statusTone } from '@/constants/taskStatus'
import { useAuthStore } from '@/stores/authStore'
import { resolveDetailPath } from '@/router/detailPathResolver'

const emit = defineEmits(['close', 'claimed', 'decided'])
defineOptions({ name: 'TaskDetailDrawer' })

const props = defineProps({
  visible: { type: Boolean, default: false },
  taskId: { type: String, default: '' },
  currentActor: { type: String, default: '' }
})

const authStore = useAuthStore()

const task = ref(null)
const events = ref([])
const loading = ref(false)
const error = ref('')
const claiming = ref(false)
const claimMsg = ref('')

const comment = ref('')
const allowRework = ref(false)
const deciding = ref('')
const decideMsg = ref('')
const decideFailed = ref(false)

const pause = computed(() => derivePause(task.value))

const isApproval = computed(() => task.value?.type === 'approval')

// ── M4 通用能力：参与进度 / 改派 / 加签 / 委托 / SLA 倒计时 ──────────────
const participation = ref(normalizeParticipations(null))
const sla = computed(() => formatSlaRemaining(task.value?.due_at))

const OUTCOME_LABELS = {
  pending: '待处理', accepted: '已接受', rejected: '已拒绝',
  skipped: '已跳过', transferred: '已转交'
}
function outcomeLabel(key) { return OUTCOME_LABELS[key] || key }
const completionModeLabel = computed(() => (
  participation.value.completionMode === 'all' ? '会签（全部通过）' : '或签（任一通过）'
))

const TERMINAL_STATUSES = ['done', 'failed', 'cancelled', 'skipped', 'dead']
const canReassign = computed(() => {
  if (isNotifyOnly.value) return false
  return canReassignTask(task.value, props.currentActor, { isAdmin: authStore.isAdmin })
})
const canParticipate = computed(() => {
  const t = task.value
  if (!t || !props.currentActor || TERMINAL_STATUSES.includes(t.status)) return false
  if (isNotifyOnly.value) return false
  return authStore.isAdmin || t.executor_assignee === props.currentActor ||
    candidates.value.includes(props.currentActor)
})

const reassignTarget = ref('')
const reassignReason = ref('')
const reassigning = ref(false)
const reassignMsg = ref('')
const reassignFailed = ref(false)

const participantInput = ref('')
const requireAll = ref(false)
const participating = ref(false)
const participateMsg = ref('')
const participateFailed = ref(false)

const delegations = ref([])
const delegating = ref(false)
const delegationMsg = ref('')
const delegationFailed = ref(false)
const delegationForm = ref({
  delegate: '', scope_type: 'any', scope_value: '', effective_from: '', effective_to: ''
})

/** 审批快照（D-AP-09：审批链 / 命中依据唯一数据源，已随任务冻结） */
const policySnapshot = computed(() => {
  const s = task.value?.inputs?.policy_snapshot
  return s && typeof s === 'object' ? s : null
})

const approvalSteps = computed(() => {
  const steps = policySnapshot.value?.steps
  return Array.isArray(steps) ? steps : []
})

const conditionExplains = computed(() => {
  const items = policySnapshot.value?.conditions_explain
  return Array.isArray(items) ? items : []
})

/** 合法动作唯一来源：任务快照 executor_config.decision_actions（前端不自造动作 id） */
const decisionActions = computed(() => {
  const actions = task.value?.executor_config?.decision_actions
  return actions && typeof actions === 'object' ? actions : null
})

const docRefType = computed(() => task.value?.doc_ref_type || '')
const docRefId = computed(() => task.value?.doc_ref_id || '')

// ── [M5-5] 阶段进度 / 动作三态 / 取人依据 ─────────────────────────────────
/** 任务当前阶段（tasks.stage_no；缺失按单阶段处理） */
const stageNo = computed(() => {
  const n = Number(task.value?.stage_no)
  return Number.isFinite(n) && n > 0 ? n : null
})

/** 快照内出现过的阶段号（升序去重）；无步骤时退化为当前阶段 */
const stageNumbers = computed(() => {
  const seen = new Set()
  for (const s of approvalSteps.value) {
    const n = Number(s.stage_no)
    if (Number.isFinite(n) && n > 0) seen.add(n)
  }
  if (!seen.size && stageNo.value) seen.add(stageNo.value)
  return [...seen].sort((a, b) => a - b)
})

const stageProgress = computed(() => {
  if (!stageNo.value) return null
  // 非审批任务仅单阶段且无快照时不占版面
  if (!policySnapshot.value && stageNo.value <= 1) return null
  const total = Math.max(stageNumbers.value.length, stageNo.value)
  return { current: stageNo.value, total }
})

const ACTION_TYPE_LABELS = {
  approve: '人工审批', auto: '自动通过', notify: '知会（只读）'
}
const ACTION_TYPE_TONES = { approve: 'info', auto: 'success', notify: 'warning' }
const actionType = computed(() => {
  const value = task.value?.executor_config?.action_type
  return typeof value === 'string' && ACTION_TYPE_LABELS[value] ? value : 'approve'
})
const actionTypeLabel = computed(() => ACTION_TYPE_LABELS[actionType.value] || actionType.value)
const actionTypeTone = computed(() => ACTION_TYPE_TONES[actionType.value] || 'muted')

const notifyCandidates = computed(() => {
  const raw = task.value?.executor_config?.notify_candidates
  return Array.isArray(raw) ? raw.map(String) : []
})

/** 只读知会：阶段动作为 notify，或当前用户仅在知会名单（不在候选池） */
const isNotifyOnly = computed(() => {
  if (actionType.value === 'notify') return true
  const actor = props.currentActor
  if (!actor) return false
  return notifyCandidates.value.includes(actor) && !candidates.value.includes(actor)
})

const assignExplain = computed(() => {
  const raw = task.value?.executor_config?.assign_explain
  return Array.isArray(raw) ? raw : []
})
const assignSource = computed(() => {
  const raw = task.value?.executor_config?.assign_source
  return typeof raw === 'string' ? raw : ''
})
const ASSIGN_REASON_LABELS = {
  no_member: '目标范围内没有匹配成员',
  no_such_role: '权限角色不存在或未绑定成员',
  missing_manager: '发起人缺少上级（管理链断点）',
  level_exhausted: '管理链已到顶层，仍无满足条件的人',
  unsupported_approver_type: '暂不支持的取人类型',
  no_data_source: '缺少数据源，无法取人'
}
const assignReasonLabel = computed(() => {
  const raw = task.value?.executor_config?.assign_reason
  if (typeof raw !== 'string' || !raw) return ''
  return ASSIGN_REASON_LABELS[raw] || raw
})

/** 审批权限口径与后端一致：admin 短路，否则 {bo}:approve */
const hasApprovePermission = computed(() => {
  if (!docRefType.value) return false
  return authStore.isAdmin || authStore.hasPermission(`${docRefType.value}:approve`)
})

const canDecide = computed(() => {
  const t = task.value
  if (!t || !isApproval.value || t.status !== 'waiting_approval') return false
  if (isNotifyOnly.value) return false
  return !!(decisionActions.value?.approve || decisionActions.value?.reject) && hasApprovePermission.value
})

const decideHint = computed(() => {
  const t = task.value
  if (!t || !isApproval.value) return ''
  if (!decisionActions.value) return '任务未冻结审批动作配置，无法在此提交决策'
  if (t.status !== 'waiting_approval') return `当前状态「${statusLabel(t)}」不可审批`
  if (isNotifyOnly.value) return '本阶段为知会（只读），无需决策'
  if (!docRefType.value) return '单据类型缺失（历史任务），无法判定审批权限'
  if (!hasApprovePermission.value) return `缺少审批权限（${docRefType.value}:approve）`
  return ''
})

function stepApprover(step) {
  const type = step.approver_type || 'role'
  return step.approver_ref ? `${type}：${step.approver_ref}` : type
}

const APPROVE_MODE_LABELS = { any: '任一通过', all: '全部通过', first: '先到先得' }

function approveModeLabel(mode) {
  return APPROVE_MODE_LABELS[mode] || mode || '任一通过'
}

const candidates = computed(() => {
  const c = task.value?.executor_candidates
  if (Array.isArray(c)) return c
  if (c && typeof c === 'object') return [...(c.users || []), ...(c.agents || []), ...(c.groups || [])]
  return []
})

const canClaim = computed(() => {
  const t = task.value
  if (!t || !props.currentActor) return false
  return t.status === 'ready' && t.assign_policy === 'claim' &&
    (candidates.value.includes(props.currentActor))
})

async function load() {
  if (!props.visible || !props.taskId) return
  loading.value = true
  error.value = ''
  claimMsg.value = ''
  try {
    const [detail, evts] = await Promise.all([
      fetchTaskDetail(props.taskId),
      fetchTaskEvents(props.taskId)
    ])
    if (!detail || detail.success !== true || !detail.data) {
      error.value = detail?.message || '任务不存在或无权查看'
      task.value = null
      events.value = []
      participation.value = normalizeParticipations(null)
    } else {
      task.value = detail.data
      events.value = (evts && evts.success && Array.isArray(evts.data)) ? evts.data : []
    }
  } catch (e) {
    error.value = e?.message || String(e)
    task.value = null
  } finally {
    loading.value = false
  }
  await Promise.all([refreshParticipation(), refreshDelegations()])
}

/** 参与人进度（失败静默：不影响抽屉主信息） */
async function refreshParticipation() {
  if (!props.taskId) {
    participation.value = normalizeParticipations(null)
    return
  }
  try {
    participation.value = normalizeParticipations(await fetchParticipations(props.taskId))
  } catch (e) {
    participation.value = normalizeParticipations(null)
  }
}

/** 我的委托（未登录/失败静默） */
async function refreshDelegations() {
  if (!props.currentActor) {
    delegations.value = []
    return
  }
  try {
    const res = await fetchDelegations({ includeInactive: false })
    delegations.value = (res && res.success === true && res.data && Array.isArray(res.data.items))
      ? res.data.items : []
  } catch (e) {
    delegations.value = []
  }
}

/** 跳转业务单据详情（懒加载 router，避免组件测试依赖路由安装） */
async function openDoc() {
  if (!docRefType.value || !docRefId.value) return
  const { default: router } = await import('@/router')
  router.push(resolveDetailPath(docRefType.value, docRefId.value))
}

async function onClaim() {
  claiming.value = true
  claimMsg.value = ''
  try {
    const res = await claimTask(props.taskId)
    if (res && res.success) {
      claimMsg.value = '认领成功'
      await load()
      emit('claimed')
    } else {
      claimMsg.value = res?.message || '认领失败'
    }
  } catch (e) {
    claimMsg.value = e?.message || String(e)
  } finally {
    claiming.value = false
  }
}

async function onDecide(decision) {
  if (decision === 'reject' && !comment.value.trim()) {
    decideMsg.value = '驳回需填写审批意见'
    decideFailed.value = true
    return
  }
  deciding.value = decision
  decideMsg.value = ''
  decideFailed.value = false
  try {
    const res = await submitDecision(props.taskId, {
      decision,
      comment: comment.value.trim(),
      allowRework: decision === 'reject' ? allowRework.value : false
    })
    if (res && res.success === true) {
      decideMsg.value = decision === 'approve' ? '已通过' : '已驳回'
      comment.value = ''
      allowRework.value = false
      await load()
      emit('decided', res.data)
    } else {
      decideFailed.value = true
      if (res?.httpStatus === 502) {
        decideMsg.value = `单据未生效，可重试：${res.message || ''}`
      } else if (res?.httpStatus === 409) {
        decideMsg.value = `不可提交：${res.message || ''}`
      } else {
        decideMsg.value = res?.message || '提交失败'
      }
    }
  } catch (e) {
    decideFailed.value = true
    decideMsg.value = e?.message || String(e)
  } finally {
    deciding.value = ''
  }
}

async function onReassign() {
  const toUser = reassignTarget.value.trim()
  const reason = reassignReason.value.trim()
  if (!toUser || !reason) {
    reassignFailed.value = true
    reassignMsg.value = '目标执行人与改派原因均必填'
    return
  }
  reassigning.value = true
  reassignMsg.value = ''
  reassignFailed.value = false
  try {
    const res = await reassignTask(props.taskId, { toUser, reason })
    if (res && res.success === true) {
      reassignMsg.value = `已改派给 ${toUser}`
      reassignTarget.value = ''
      reassignReason.value = ''
      await load()
      emit('claimed')
    } else {
      reassignFailed.value = true
      reassignMsg.value = res?.message || '改派失败'
    }
  } catch (e) {
    reassignFailed.value = true
    reassignMsg.value = e?.message || String(e)
  } finally {
    reassigning.value = false
  }
}

async function onParticipate() {
  participating.value = true
  participateMsg.value = ''
  participateFailed.value = false
  try {
    const res = await participateTask(props.taskId, {
      participant: participantInput.value.trim() || undefined,
      requireAll: requireAll.value
    })
    if (res && res.success === true) {
      participateMsg.value = res.data?.status === 'partially_approved'
        ? '已加签，会签未齐'
        : '已加签'
      participantInput.value = ''
      await refreshParticipation()
    } else {
      participateFailed.value = true
      participateMsg.value = res?.message || '加签失败'
    }
  } catch (e) {
    participateFailed.value = true
    participateMsg.value = e?.message || String(e)
  } finally {
    participating.value = false
  }
}

async function onCreateDelegation() {
  const check = validateDelegationForm(delegationForm.value)
  if (!check.valid) {
    delegationFailed.value = true
    delegationMsg.value = check.message
    return
  }
  delegating.value = true
  delegationMsg.value = ''
  delegationFailed.value = false
  const form = delegationForm.value
  try {
    const res = await createDelegation({
      delegate: form.delegate.trim(),
      scope_type: form.scope_type,
      scope_value: form.scope_type === 'any' ? null : String(form.scope_value || '').trim(),
      effective_from: form.effective_from || null,
      effective_to: form.effective_to || null
    })
    if (res && res.success === true) {
      delegationMsg.value = '委托已创建'
      delegationForm.value = {
        delegate: '', scope_type: 'any', scope_value: '', effective_from: '', effective_to: ''
      }
      await refreshDelegations()
    } else {
      delegationFailed.value = true
      delegationMsg.value = res?.message || '委托创建失败'
    }
  } catch (e) {
    delegationFailed.value = true
    delegationMsg.value = e?.message || String(e)
  } finally {
    delegating.value = false
  }
}

async function onRevokeDelegation(id) {
  delegationMsg.value = ''
  delegationFailed.value = false
  try {
    const res = await revokeDelegation(id)
    if (res && res.success === true) {
      delegationMsg.value = '已撤销'
      await refreshDelegations()
    } else {
      delegationFailed.value = true
      delegationMsg.value = res?.message || '撤销失败'
    }
  } catch (e) {
    delegationFailed.value = true
    delegationMsg.value = e?.message || String(e)
  }
}

watch(() => [props.visible, props.taskId], () => {
  decideMsg.value = ''
  decideFailed.value = false
  comment.value = ''
  allowRework.value = false
  reassignMsg.value = ''
  reassignFailed.value = false
  reassignTarget.value = ''
  reassignReason.value = ''
  participateMsg.value = ''
  participateFailed.value = false
  participantInput.value = ''
  requireAll.value = false
  delegationMsg.value = ''
  delegationFailed.value = false
  load()
}, { immediate: true })
</script>

<style scoped>
.tdd-head { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.tdd-chip { font-size: 12px; padding: 2px 8px; border-radius: 4px; }
.tdd-chip--info { background: rgba(64, 158, 255, 0.12); color: #409eff; }
.tdd-chip--warning { background: rgba(230, 162, 60, 0.12); color: #e6a23c; }
.tdd-chip--danger { background: rgba(245, 108, 108, 0.12); color: #f56c6c; }
.tdd-chip--success { background: rgba(103, 194, 58, 0.12); color: #67c23a; }
.tdd-chip--muted { background: var(--color-bg-layout); color: var(--color-text-secondary); }
.tdd-fields { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px 16px; margin: 0 0 16px; }
.tdd-fields dt { font-size: 12px; color: var(--color-text-secondary); }
.tdd-fields dd { margin: 2px 0 0; }
.tdd-link { margin-left: 8px; padding: 0; border: none; background: none; color: var(--color-primary); cursor: pointer; font-size: 13px; }
.tdd-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.tdd-claim-msg { font-size: 13px; color: var(--color-primary); }
.tdd-section { margin: 8px 0; }
.tdd-decision { border-top: 1px solid var(--color-border); padding-top: 8px; margin-bottom: 16px; }
.tdd-policy-head { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.tdd-chain { list-style: none; margin: 0 0 8px; padding: 0; }
.tdd-chain-step { display: flex; gap: 8px; padding: 4px 0; font-size: 13px; }
.tdd-chain-no { width: 18px; height: 18px; border-radius: 50%; background: var(--color-bg-layout); color: var(--color-text-secondary); font-size: 12px; text-align: center; line-height: 18px; flex: none; }
.tdd-chain-body { display: flex; gap: 8px; flex-wrap: wrap; }
.tdd-chain-meta { color: var(--color-text-secondary); }
.tdd-sub { font-size: 12px; color: var(--color-text-secondary); margin: 4px 0; }
.tdd-cond { font-size: 12px; padding: 2px 0; color: var(--color-text-secondary); }
.tdd-cond--fail { color: #e6a23c; }
.tdd-textarea { width: 100%; box-sizing: border-box; margin-bottom: 8px; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; font: inherit; resize: vertical; }
.tdd-check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--color-text-secondary); margin-bottom: 8px; }
.tdd-decision-hint { font-size: 13px; color: var(--color-text-secondary); padding: 4px 0 8px; }
.tdd-timeline { list-style: none; margin: 0; padding: 0; border-left: 2px solid var(--color-border); }
.tdd-event { display: flex; gap: 12px; padding: 6px 12px; }
.tdd-event-time { color: var(--color-text-secondary); font-size: 12px; white-space: nowrap; }
.tdd-event-body { display: flex; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.tdd-event-type { font-weight: 500; }
.tdd-event-move { color: var(--color-primary); }
.tdd-state { padding: 24px; text-align: center; color: var(--color-text-secondary); }
.tdd-error { color: #f56c6c; }
.tdd-m4 { border-top: 1px solid var(--color-border); padding-top: 8px; margin-bottom: 16px; }
.tdd-input { width: 100%; box-sizing: border-box; margin-bottom: 8px; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; font: inherit; }
.tdd-form { margin-top: 8px; }
.tdd-counts { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: var(--color-text-secondary); margin-bottom: 6px; }
.tdd-participants { list-style: none; margin: 0; padding: 0; }
.tdd-participant { font-size: 13px; padding: 3px 0; }
.tdd-countdown { font-size: 12px; color: var(--color-text-secondary); }
.tdd-countdown--overdue { color: #f56c6c; }
</style>