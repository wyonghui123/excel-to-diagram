/**
 * 任务状态文案单一真源（D-AP-11）
 *
 * 枚举口径与后端 `meta/core/task_schema.py::TASK_STATUSES` 一一对齐（11 态）。
 * 说明：现有 /api/v2/meta/enums/task_status 指向 project_task BO，语义不同
 * （项目任务 ≠ task.v1 任务实例），不能复用；后端暂无任务状态 label 端点，
 * 因此本文件即唯一副本。所有页面展示任务状态必须经 statusLabel()/statusTone()，
 * 禁止再各自硬编码中文。
 *
 * @module constants/taskStatus
 */

export const TASK_STATUS_LABELS = {
  pending: '待就绪',
  ready: '待认领',
  claimed: '已认领',
  in_progress: '进行中',
  blocked: '受阻',
  waiting_approval: '待审批',
  done: '已完成',
  failed: '失败',
  cancelled: '已取消',
  skipped: '已跳过',
  dead: '已失效'
}

/** 审批类任务的终态语义差异（reject→failed、approve→done，见 decision_effect） */
const TYPE_OVERRIDES = {
  approval: {
    done: '已通过',
    failed: '已驳回',
    in_progress: '退回修改中'
  }
}

export const TASK_STATUS_TONES = {
  pending: 'muted',
  ready: 'info',
  claimed: 'info',
  in_progress: 'info',
  blocked: 'danger',
  waiting_approval: 'warning',
  done: 'success',
  failed: 'danger',
  cancelled: 'muted',
  skipped: 'muted',
  dead: 'muted'
}

function _statusOf(task) {
  return typeof task === 'string' ? task : (task?.status || '')
}

/**
 * 任务状态中文文案。
 * @param {{status?:string,type?:string}|string} task 任务对象或状态字符串
 * @returns {string}
 */
export function statusLabel(task) {
  const status = _statusOf(task)
  if (!status) return ''
  const type = typeof task === 'string' ? '' : task?.type
  const override = TYPE_OVERRIDES[type] || {}
  return override[status] || TASK_STATUS_LABELS[status] || status
}

/**
 * 任务状态视觉色调（success / info / warning / danger / muted）。
 * @param {{status?:string}|string} task 任务对象或状态字符串
 * @returns {string}
 */
export function statusTone(task) {
  return TASK_STATUS_TONES[_statusOf(task)] || 'muted'
}

export default { TASK_STATUS_LABELS, TASK_STATUS_TONES, statusLabel, statusTone }