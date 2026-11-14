/**
 * jobRunStatus - 作业状态文案与色调（spec §12.2.2，纯函数）
 *
 * 边界:
 *   · 只做展示映射，不判断业务可用性 — 能否取消/重试由后端
 *     `capabilities` 下发（spec IF-002），页面禁止自行推导；
 *   · 枚举全集与后端 `RUN_STATUSES` / `TRIGGER_TYPES` / `RUN_SOURCES` 一致。
 */

//: run 状态文案（与后端 RUN_STATUSES 对齐）。
const RUN_STATUS_LABELS = {
  pending: '排队中',
  claimed: '已领取',
  running: '运行中',
  retrying: '重试中',
  succeeded: '成功',
  failed: '失败',
  cancelled: '已取消',
  skipped: '已跳过',
  dead: '已终结'
}

//: run 状态色调（MetaTable / 标签通用 tone）。
const RUN_STATUS_TONES = {
  pending: 'info',
  claimed: 'info',
  running: 'primary',
  retrying: 'warning',
  succeeded: 'success',
  failed: 'danger',
  cancelled: 'info',
  skipped: 'warning',
  dead: 'danger'
}

//: 触发方式文案（与后端 TRIGGER_TYPES 对齐）。
const TRIGGER_TYPE_LABELS = {
  cron: '定时',
  interval: '周期',
  once: '一次性'
}

//: run 来源文案（与后端 RUN_SOURCES 对齐）。
const RUN_SOURCE_LABELS = {
  manual: '手动',
  import: '导入',
  cron: '定时',
  interval: '周期',
  once: '一次性',
  scheduled: '计划'
}

/**
 * 状态文案。
 * @param {string} status
 * @returns {string}
 */
export function statusLabel(status) {
  return RUN_STATUS_LABELS[status] || status || ''
}

/**
 * 状态色调。
 * @param {string} status
 * @returns {string}
 */
export function statusTone(status) {
  return RUN_STATUS_TONES[status] || 'default'
}

/**
 * 触发方式文案。
 * @param {string} type
 * @returns {string}
 */
export function triggerTypeLabel(type) {
  return TRIGGER_TYPE_LABELS[type] || type || ''
}

/**
 * run 来源文案。
 * @param {string} source
 * @returns {string}
 */
export function sourceLabel(source) {
  return RUN_SOURCE_LABELS[source] || source || ''
}