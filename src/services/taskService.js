/**
 * taskService - task.v1 任务服务（收件箱 / 详情 / 活动流 / 认领 / 监控）
 *
 * 三层职责:
 *   1. 纯函数 — 分区常量、暂停态派生、行视图模型
 *   2. 纯函数 — 响应归一
 *   3. API    — 经 httpClient 调 /api/v1 task.v1 端点
 *
 * 纪律（对齐后端）:
 *   - 分区口径与 meta/core/task_inbox.py BUCKETS 顺序一致（primary_bucket 优先级）
 *   - 暂停态**派生**不落列（A2 无 waiting 态）：human / webhook / approval / blocked
 *   - 认领 actor 由服务端裁决，前端不传身份
 *
 * @module services/taskService
 */

import { apiV1, apiV2 } from '@/utils/httpClient'
import { statusLabel, statusTone } from '@/constants/taskStatus'

// ============================================================================
// 1. 常量 — 分区（顺序即优先级，与 A8 BUCKETS 对齐）
// ============================================================================

export const BUCKET_ORDER = ['alert', 'approval', 'todo', 'agent_handoff', 'claimable']

export const BUCKET_LABELS = {
  alert: '逾期告警',
  approval: '待我审核',
  todo: '我的待办',
  agent_handoff: 'Agent 移交',
  claimable: '可认领'
}

// ============================================================================
// 2. 纯函数 — 暂停态派生（§9.4 三个真实暂停点，不发明状态）
// ============================================================================

const ACTIVE_STATUSES = ['ready', 'claimed', 'in_progress', 'blocked']
const PAUSED_TERMINAL = ['done', 'failed', 'cancelled', 'skipped', 'dead']

const PAUSE_DEFS = {
  awaiting_human: { code: 'awaiting_human', label: '等待人工办理', tone: 'info' },
  awaiting_async: { code: 'awaiting_async', label: '等待外部回调', tone: 'info' },
  needs_review: { code: 'needs_review', label: '等待审核', tone: 'warning' },
  blocked: { code: 'blocked', label: '受阻', tone: 'danger' }
}

/**
 * 从任务字段**派生**暂停/停等信号（纯函数，可单测）。
 * @param {{executor_type?:string,type?:string,status?:string}} task
 * @returns {{code:string,label:string,tone:string}|null}
 */
export function derivePause(task) {
  if (!task) return null
  const status = task.status
  if (PAUSED_TERMINAL.includes(status)) return null
  if (status === 'blocked') return PAUSE_DEFS.blocked
  if (task.type === 'approval' && status === 'waiting_approval') return PAUSE_DEFS.needs_review
  if (!ACTIVE_STATUSES.includes(status)) return null
  if (task.executor_type === 'human') return PAUSE_DEFS.awaiting_human
  if (task.executor_type === 'webhook') return PAUSE_DEFS.awaiting_async
  return null
}

// ============================================================================
// 3. 纯函数 — 行视图模型 / 响应归一
// ============================================================================

/**
 * 收件箱 entry → 视图模型（补分区标签 / 暂停徽标 / 逾期标记）。
 * @param {Object} entry
 * @returns {Object}
 */
export function formatTaskRow(entry) {
  if (!entry) return null
  const primary = entry.primary_bucket
  const alert = entry.alert
  return {
    ...entry,
    bucketLabel: BUCKET_LABELS[primary] || primary || '',
    pause: derivePause(entry),
    isOverdue: !!alert,
    overdueLabel: alert ? `SLA ${alert.pct_used != null ? `${alert.pct_used}%` : alert.rung_name || ''}`.trim() : ''
  }
}

/**
 * 归一收件箱响应 → {entries, counts, total}（失败/空一律兜底空结构，不抛）。
 * @param {{success?:boolean,data?:Object}} res
 */
export function normalizeInboxResponse(res) {
  const empty = { entries: [], counts: {}, total: 0 }
  if (!res || res.success !== true || !res.data) return empty
  const d = res.data
  return {
    entries: Array.isArray(d.entries) ? d.entries : [],
    counts: d.counts && typeof d.counts === 'object' ? d.counts : {},
    total: typeof d.total === 'number' ? d.total : (Array.isArray(d.entries) ? d.entries.length : 0)
  }
}

// ============================================================================
// 3.5 纯函数 — 收件箱批量审批 / approval 置顶（D-AP-12）
// ============================================================================

/**
 * approval 分区置顶（稳定排序：approval 行在前，其余保持原顺序）。
 * @param {Array} rows
 * @returns {Array}
 */
export function sortApprovalFirst(rows) {
  if (!Array.isArray(rows)) return []
  return rows
    .map((row, index) => ({ row, index }))
    .sort((a, b) => {
      const rank = item => (item.row?.primary_bucket === 'approval' ? 0 : 1)
      return rank(a) - rank(b) || a.index - b.index
    })
    .map(item => item.row)
}

/**
 * 汇总逐条决策结果：成功 N / 失败 M；httpStatus=502（单据未生效）可重试。
 * @param {Array<{task_id:string,success:boolean,message?:string,httpStatus?:number}>} results
 * @returns {{succeeded:string[], failed:Array<{task_id:string,message:string,httpStatus?:number}>, retryableIds:string[]}}
 */
export function summarizeBatchResults(results) {
  const succeeded = []
  const failed = []
  ;(results || []).forEach(item => {
    if (!item) return
    if (item.success) succeeded.push(item.task_id)
    else failed.push({ task_id: item.task_id, message: item.message || '', httpStatus: item.httpStatus })
  })
  return {
    succeeded,
    failed,
    retryableIds: failed.filter(item => item.httpStatus === 502).map(item => item.task_id)
  }
}

// ============================================================================
// 3.5.1 批量护栏 — 上限 / 并发池 / 动作预判（§9.13.4.3）
// ============================================================================

/** 单次批量上限（选中 > 50 条时提示分批，UI 层使用） */
export const BATCH_MAX_SIZE = 50

/** 批量并发上限（简单 Promise 池，避免瞬时打爆服务端） */
export const BATCH_CONCURRENCY = 4

/**
 * 简单 Promise 池：结果数组与输入同序，worker 抛错不中断其他项。
 * 每项返回 `{ok:true, value}` 或 `{ok:false, error}`。
 * @param {Array} items
 * @param {number} limit 并发上限（非法值回落 1；实际并发 = min(limit, items.length)）
 * @param {(item:any, index:number)=>Promise<any>} worker
 * @returns {Promise<Array<{ok:boolean, value?:any, error?:any}>>}
 */
export function runWithConcurrency(items, limit, worker) {
  const list = Array.isArray(items) ? items : []
  const size = list.length
  if (!size) return Promise.resolve([])
  const width = Number.isFinite(limit) && limit > 0
    ? Math.max(1, Math.min(Math.floor(limit), size))
    : 1
  const results = new Array(size)
  let cursor = 0
  async function drain() {
    while (cursor < size) {
      const index = cursor
      cursor += 1
      try {
        results[index] = { ok: true, value: await worker(list[index], index) }
      } catch (error) {
        results[index] = { ok: false, error }
      }
    }
  }
  return Promise.all(Array.from({ length: width }, () => drain())).then(() => results)
}

/**
 * 动作预判：`GET /tasks/{id}/actions` 的 actions 是否含该决策动作。
 * 三态：true（含）/ false（响应成功但缺该动作）/ null（响应失败或结构异常，无法判定）。
 * 无法判定时由服务端兜底，不做前端拦截（fail-open）。
 * @param {{success?:boolean,data?:Object}|null} res
 * @param {'approve'|'reject'} decision
 * @returns {boolean|null}
 */
export function actionAllowedFromPayload(res, decision) {
  if (!res || res.success !== true || !res.data) return null
  const actions = res.data.actions
  if (!Array.isArray(actions)) return null
  return actions.some(item => !!item && item.action === decision)
}

function _qs(params) {
  const sp = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.append(k, String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
}

// ============================================================================
// 3.6 纯函数 — M4 通用能力（参与进度 / 改派准入 / SLA 倒计时 / 委托表单）
// ============================================================================

const TERMINAL_STATUSES = ['done', 'failed', 'cancelled', 'skipped', 'dead']
export const DELEGATION_SCOPES = ['any', 'app', 'type', 'doc_ref_type']

/** 参与进度响应归一（失败/空兜底，不抛）。 */
export function normalizeParticipations(res) {
  const empty = { participants: [], counts: {}, remaining: [], completionMode: 'any' }
  if (!res || res.success !== true || !res.data) return empty
  const d = res.data
  return {
    participants: Array.isArray(d.participants) ? d.participants : [],
    counts: d.counts && typeof d.counts === 'object' ? d.counts : {},
    remaining: Array.isArray(d.remaining) ? d.remaining : [],
    completionMode: d.completion_mode || 'any'
  }
}

/** 改派动作可见性（服务端仍裁决；前端只做「无权限不渲染」）。 */
export function canReassignTask(task, actor, { isAdmin = false } = {}) {
  if (!task || !actor) return false
  if (TERMINAL_STATUSES.includes(task.status)) return false
  if (isAdmin) return true
  if (task.executor_assignee === actor) return true
  const c = task.executor_candidates
  const list = Array.isArray(c)
    ? c
    : (c && typeof c === 'object' ? [...(c.users || []), ...(c.agents || []), ...(c.groups || [])] : [])
  return list.includes(actor)
}

/**
 * SLA 倒计时（纯函数）：due_at − now。
 * @returns {{overdue:boolean, ms:number, label:string}|null}
 */
export function formatSlaRemaining(dueAt, now = Date.now()) {
  if (!dueAt) return null
  const due = new Date(dueAt).getTime()
  const base = now instanceof Date ? now.getTime() : Number(now)
  if (!Number.isFinite(due) || !Number.isFinite(base)) return null
  const diff = due - base
  const overdue = diff < 0
  const abs = Math.abs(diff)
  const totalMinutes = Math.floor(abs / 60000)
  const days = Math.floor(totalMinutes / 1440)
  const hours = Math.floor((totalMinutes % 1440) / 60)
  const minutes = totalMinutes % 60
  let span
  if (days > 0) span = `${days}d ${hours}h`
  else if (hours > 0) span = `${hours}h ${minutes}m`
  else span = `${minutes}m`
  return { overdue, ms: diff, label: overdue ? `已超时 ${span}` : `剩余 ${span}` }
}

/** 委托表单校验（与后端 create_delegation 口径一致，前端先拦）。 */
export function validateDelegationForm(form = {}) {
  const delegate = String(form.delegate || '').trim()
  if (!delegate) return { valid: false, message: '受托人不能为空' }
  const delegator = String(form.delegator || '').trim()
  if (delegator && delegator === delegate) return { valid: false, message: '不能委托给自己' }
  const scopeType = form.scope_type || 'any'
  if (!DELEGATION_SCOPES.includes(scopeType)) {
    return { valid: false, message: `不支持的委托范围：${scopeType}` }
  }
  if (scopeType !== 'any' && !String(form.scope_value || '').trim()) {
    return { valid: false, message: '选择范围后必须填写范围值' }
  }
  const from = form.effective_from ? new Date(form.effective_from).getTime() : null
  const to = form.effective_to ? new Date(form.effective_to).getTime() : null
  if (Number.isFinite(from) && Number.isFinite(to) && to < from) {
    return { valid: false, message: '结束时间不能早于开始时间' }
  }
  return { valid: true, message: '' }
}

// ============================================================================
// 3.7 纯函数 — 单据侧只读审批投影（§9.13.4.1）
// ============================================================================

/**
 * 实例流转三步态（纯函数，可单测）：步骤列表 + done/active/pending。
 * 数据源：任务详情 `inputs.policy_snapshot.steps` + 基础列 `stage_no` / `status`。
 * 已完成步的处理人不伪造：仅当事件 payload.step_no / payload.stage_no 命中该步
 * 且 actor 非空时归属，多条取 occurred_at 最新（同刻取最后）。
 *
 * @param {Object|null} task 审批任务（需含 inputs.policy_snapshot）
 * @param {Array} events 任务活动流（升序）
 * @returns {{hitPolicy:boolean,missReason:string,currentStage:number,steps:Array}}
 */
export function buildApprovalFlow(task, events = []) {
  const inputs = task?.inputs && typeof task.inputs === 'object' ? task.inputs : {}
  const snapshot = inputs.policy_snapshot && typeof inputs.policy_snapshot === 'object'
    ? inputs.policy_snapshot
    : {}
  const rawSteps = Array.isArray(snapshot.steps) ? snapshot.steps : []
  const currentStage = Number(task?.stage_no) || 1
  const allDone = task?.status === 'done'
  const list = Array.isArray(events) ? events : []

  const steps = rawSteps
    .filter(step => step && typeof step === 'object')
    // 缺省 step_no 时先按位置补序号再排序，避免补号与既有序号撞车（仅用于展示/三态，不写回数据）
    .map((step, index) => {
      const stepNo = _stepNo(step) || index + 1
      // 三态以 stage_no 为准（同 stage = 并行审批人）；旧快照无 stage_no 时回落 step_no（逐步串行）
      return { step, stepNo, stageNo: _stepNo(step, 'stage_no') || stepNo }
    })
    .sort((a, b) => (a.stageNo - b.stageNo) || (a.stepNo - b.stepNo))
    .map(({ step, stepNo, stageNo }) => {
      let state = 'pending'
      if (allDone) state = 'done'
      else if (stageNo < currentStage) state = 'done'
      else if (stageNo === currentStage) state = 'active'

      let hit = null
      if (state === 'done') {
        for (const ev of list) {
          if (!ev || !ev.actor) continue
          const payload = ev.payload && typeof ev.payload === 'object' ? ev.payload : null
          if (!payload) continue
          const byStep = Number(payload.step_no) === stepNo
          const byStage = Number(payload.stage_no) === stageNo
          if (!byStep && !byStage) continue
          if (!hit || String(ev.occurred_at || '') >= String(hit.occurred_at || '')) hit = ev
        }
      }

      return {
        step_no: stepNo,
        stage_no: stageNo,
        approverLabel: step.approver_ref || step.approver_type || '',
        approveMode: step.approve_mode,
        slaHours: step.sla_hours ?? null,
        state,
        actor: hit ? hit.actor : '',
        occurredAt: hit ? (hit.occurred_at || '') : ''
      }
    })

  return {
    hitPolicy: snapshot.hit_policy !== false,
    missReason: snapshot.hit_policy === false ? '未命中策略，回落默认链' : '',
    currentStage,
    steps
  }
}

/** 步骤号归一：非法值回落 0（仅用于排序/比较，不伪造展示值） */
function _stepNo(step, key = 'step_no') {
  const n = Number(step?.[key])
  return Number.isFinite(n) && n > 0 ? n : 0
}

/**
 * 单据详情页只读审批投影（纯函数，可单测）。
 * 数据源：`GET /tasks?doc_ref_*` 的最新一条 + 活动流（升序）。
 * 不读单据 `approval_status`（投影列只展示），状态文案走 `taskStatus.js` 单一真源。
 *
 * @param {Object|null} task 最新审批任务
 * @param {Array} events 任务活动流（`list_task_events` 升序）
 * @returns {{id:string,statusLabel:string,tone:string,assignee:string,
 *            stage:number,stageTotal:number,policyName:string,
 *            events:Array,legacyRef:boolean}|null}
 */
export function buildApprovalProjection(task, events = []) {
  if (!task) return null
  const inputs = task.inputs && typeof task.inputs === 'object' ? task.inputs : {}
  const snapshot = inputs.policy_snapshot && typeof inputs.policy_snapshot === 'object'
    ? inputs.policy_snapshot
    : {}
  const steps = Array.isArray(snapshot.steps) ? snapshot.steps : []
  const stages = new Set(
    steps.map(step => (Number(step?.stage_no) > 0 ? Number(step.stage_no) : 1))
  )
  const recent = (Array.isArray(events) ? events : []).slice(-3).reverse()
  return {
    id: task.id,
    statusLabel: statusLabel(task),
    tone: statusTone(task),
    assignee: task.assignee || '',
    stage: Number(task.stage_no) > 0 ? Number(task.stage_no) : 1,
    stageTotal: stages.size || 1,
    policyName: snapshot.policy_name || '',
    events: recent,
    legacyRef: !task.doc_ref_type || !task.doc_ref_id,
    flow: buildApprovalFlow(task, events)
  }
}

// ============================================================================
// 4. API — v1 task.v1 端点
// ============================================================================

/** 统一收件箱（entries + counts） */
export async function fetchInbox({ bucket, appId, limit } = {}) {
  return apiV1.get(`/task-inbox${_qs({ bucket, app_id: appId, limit })}`)
}

/** 分区角标（全量口径） */
export async function fetchInboxCounts({ appId } = {}) {
  return apiV1.get(`/task-inbox/counts${_qs({ app_id: appId })}`)
}

/** 任务详情（行级可见性 fail-closed） */
export async function fetchTaskDetail(taskId) {
  return apiV1.get(`/tasks/${encodeURIComponent(taskId)}`)
}

/** 任务可用动作（状态 × 权限；只读，动作用于批量预判） */
export async function fetchTaskActions(taskId) {
  return apiV1.get(`/tasks/${encodeURIComponent(taskId)}/actions`)
}

/** 任务活动流 */
export async function fetchTaskEvents(taskId, limit = 200) {
  return apiV1.get(`/tasks/${encodeURIComponent(taskId)}/events${_qs({ limit })}`)
}

/** 认领（actor 由服务端裁决） */
export async function claimTask(taskId) {
  return apiV1.post(`/tasks/${encodeURIComponent(taskId)}/claim`, {})
}

/**
 * 提交审批决策（决策-生效协议入口；四眼/权限由服务端裁决）。
 * @param {string} taskId
 * @param {{decision:'approve'|'reject', comment?:string, allowRework?:boolean}} payload
 *   - decision 必须来自任务快照 executor_config.decision_actions 的动作入参
 *   - allow_rework=true 时驳回后退回「进行中」（可重新提交）
 * @returns {Promise<{success:boolean,data?:Object,message?:string,httpStatus?:number}>}
 *   409 = 入口/守卫不满足（未产生副作用）；502 = 单据未生效，可重试
 */
export async function submitDecision(taskId, { decision, comment = '', allowRework = false } = {}) {
  return apiV1.post(`/tasks/${encodeURIComponent(taskId)}/decision`, {
    decision,
    comment,
    allow_rework: !!allowRework
  })
}

/** 参与人进度（任务可见者；M4-2/M4-5） */
export async function fetchParticipations(taskId) {
  return apiV1.get(`/tasks/${encodeURIComponent(taskId)}/participations`)
}

/** 改派执行人（M4-1；reason 必填留痕，服务端裁决准入与四眼） */
export async function reassignTask(taskId, { toUser, reason } = {}) {
  return apiV1.post(`/tasks/${encodeURIComponent(taskId)}/assign`, {
    to_user: toUser,
    reason
  })
}

/** 加签 / 会签（M4-2；participant 缺省 = 自己） */
export async function participateTask(taskId, { participant, comment = '', requireAll = false } = {}) {
  const body = { comment, require_all: !!requireAll }
  if (participant) body.participant = participant
  return apiV1.post(`/tasks/${encodeURIComponent(taskId)}/participate`, body)
}

/** 我的委托配置（M4-3；服务端非 admin 强制 delegator=当前用户） */
export async function fetchDelegations({ includeInactive = false, delegator } = {}) {
  return apiV1.get(`/task-delegations${_qs({
    include_inactive: includeInactive ? 'true' : undefined,
    delegator
  })}`)
}

/** 新建委托（M4-3） */
export async function createDelegation(payload = {}) {
  return apiV1.post('/task-delegations', payload)
}

/** 撤销委托（M4-3；DELETE → status=revoked，保留审计行） */
export async function revokeDelegation(id) {
  return apiV1.delete(`/task-delegations/${id}`)
}

/** 任务列表（管理员全量；非管理员需同时传 docRefType + docRefId，按行级可见性收敛） */
export async function fetchTasks({ status, type, appId, executorType,
                                   docRefType, docRefId, page, pageSize } = {}) {
  return apiV1.get(`/tasks${_qs({
    status, type, app_id: appId, executor_type: executorType,
    doc_ref_type: docRefType, doc_ref_id: docRefId, page, page_size: pageSize
  })}`)
}

/** 编排调度聚合（只读）：定义 + 触发规则 + 最近运行（任务管理页「调度」tab 数据源） */
export async function fetchWorkflowSchedules() {
  return apiV2.get('/workflows/schedules')
}

export default {
  BUCKET_ORDER, BUCKET_LABELS, DELEGATION_SCOPES,
  BATCH_MAX_SIZE, BATCH_CONCURRENCY,
  derivePause, formatTaskRow, normalizeInboxResponse,
  sortApprovalFirst, summarizeBatchResults,
  runWithConcurrency, actionAllowedFromPayload,
  normalizeParticipations, canReassignTask, formatSlaRemaining, validateDelegationForm,
  buildApprovalProjection, buildApprovalFlow,
  fetchInbox, fetchInboxCounts, fetchTaskDetail, fetchTaskActions, fetchTaskEvents,
  claimTask, submitDecision,
  fetchParticipations, reassignTask, participateTask,
  fetchDelegations, createDelegation, revokeDelegation,
  fetchTasks, fetchWorkflowSchedules
}