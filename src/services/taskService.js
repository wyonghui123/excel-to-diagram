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

import { apiV1 } from '@/utils/httpClient'

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

function _qs(params) {
  const sp = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') sp.append(k, String(v))
  })
  const s = sp.toString()
  return s ? `?${s}` : ''
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

/** 任务活动流 */
export async function fetchTaskEvents(taskId, limit = 200) {
  return apiV1.get(`/tasks/${encodeURIComponent(taskId)}/events${_qs({ limit })}`)
}

/** 认领（actor 由服务端裁决） */
export async function claimTask(taskId) {
  return apiV1.post(`/tasks/${encodeURIComponent(taskId)}/claim`, {})
}

/** 运维监控列表（限管理员） */
export async function fetchTasks({ status, type, appId, executorType, page, pageSize } = {}) {
  return apiV1.get(`/tasks${_qs({
    status, type, app_id: appId, executor_type: executorType, page, page_size: pageSize
  })}`)
}

export default {
  BUCKET_ORDER, BUCKET_LABELS, derivePause, formatTaskRow, normalizeInboxResponse,
  fetchInbox, fetchInboxCounts, fetchTaskDetail, fetchTaskEvents, claimTask, fetchTasks
}