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
        <span v-if="pause" data-test="pause-badge" class="tdd-chip" :class="`tdd-chip--${pause.tone}`">
          {{ pause.label }}
        </span>
      </div>

      <dl class="tdd-fields">
        <div><dt>认领人</dt><dd>{{ task.executor_assignee || '—' }}</dd></div>
        <div><dt>到期</dt><dd>{{ task.due_at || '—' }}</dd></div>
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

      <div v-if="isApproval" data-test="decision-panel" class="tdd-decision">
        <h4 class="tdd-section">审批</h4>

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
import { fetchTaskDetail, fetchTaskEvents, claimTask, derivePause, submitDecision } from '@/services/taskService'
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

/** 审批权限口径与后端一致：admin 短路，否则 {bo}:approve */
const hasApprovePermission = computed(() => {
  if (!docRefType.value) return false
  return authStore.isAdmin || authStore.hasPermission(`${docRefType.value}:approve`)
})

const canDecide = computed(() => {
  const t = task.value
  if (!t || !isApproval.value || t.status !== 'waiting_approval') return false
  return !!(decisionActions.value?.approve || decisionActions.value?.reject) && hasApprovePermission.value
})

const decideHint = computed(() => {
  const t = task.value
  if (!t || !isApproval.value) return ''
  if (!decisionActions.value) return '任务未冻结审批动作配置，无法在此提交决策'
  if (t.status !== 'waiting_approval') return `当前状态「${statusLabel(t)}」不可审批`
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

watch(() => [props.visible, props.taskId], () => {
  decideMsg.value = ''
  decideFailed.value = false
  comment.value = ''
  allowRework.value = false
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
</style>