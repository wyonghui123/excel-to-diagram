/**
 * jobService - 统一异步作业管理 API 封装（spec IF-007 ~ IF-012）
 *
 * 职责:
 *   · 作业定义：列表 / 更新运营参数；
 *   · 触发器：查询 / 新建 / 更新 / 删除（`trigger_type` 不可变，换类型请删后重建）；
 *   · 执行记录：列表（服务端过滤）/ 详情 / 手动运行 / 重试 / 取消；
 *   · 调度器状态：只读快照。
 *
 * 边界:
 *   · 本模块只做请求转发，不推导状态与可用性 —— 一律消费后端
 *     `capabilities` / `meta.filters`（spec §2.1 单一事实）；
 *   · 作业码与 id 均走路径参数，必须 encodeURIComponent。
 *
 * @module services/jobService
 */

import { apiV2 } from '@/utils/httpClient'

// ============================================================================
// 作业定义
// ============================================================================

/**
 * 拉取作业列表（含 `capabilities` 与触发器/最近运行概览）。
 * @param {object} [params] 预留：分页/过滤
 * @returns {Promise<{success:boolean,data?:{items:Array,total:number},message?:string}>}
 */
export async function fetchJobs(params) {
  return apiV2.get('/jobs', { params })
}

/**
 * 更新作业运营参数（白名单：name/description/default_params/timeout_seconds/
 * max_attempts/backoff_seconds/status）。
 * @param {string} code
 * @param {object} payload
 */
export async function patchJob(code, payload) {
  return apiV2.patch(`/jobs/${encodeURIComponent(code)}`, payload)
}

// ============================================================================
// 触发器
// ============================================================================

/**
 * 拉取某作业的触发器列表（含 `next_runs` 预览）。
 * @param {string} code
 */
export async function fetchTriggers(code) {
  return apiV2.get(`/jobs/${encodeURIComponent(code)}/triggers`)
}

/**
 * 新建触发器。
 * @param {string} code
 * @param {{trigger_type:string, cron_expr?:string, interval_seconds?:number,
 *          run_at?:number, params_override?:object, enabled?:boolean}} payload
 */
export async function createTrigger(code, payload) {
  return apiV2.post(`/jobs/${encodeURIComponent(code)}/triggers`, payload)
}

/**
 * 更新触发器（cron_expr/interval_seconds/params_override/enabled/next_run_at）。
 * @param {number} triggerId
 * @param {object} payload
 */
export async function updateTrigger(triggerId, payload) {
  return apiV2.patch(`/jobs/triggers/${encodeURIComponent(triggerId)}`, payload)
}

/**
 * 删除触发器（物理删除；历史 run 仍可查）。
 * @param {number} triggerId
 */
export async function deleteTrigger(triggerId) {
  return apiV2.delete(`/jobs/triggers/${encodeURIComponent(triggerId)}`)
}

// ============================================================================
// 执行记录
// ============================================================================

/**
 * 执行记录列表。
 * @param {{job_code?:string, status?:string, source?:string, trigger_type?:string,
 *          from?:number|string, to?:number|string, page?:number,
 *          page_size?:number}} [params]
 * @returns {Promise<{success:boolean,data?:{
 *   items:Array,total:number,page:number,page_size:number,has_more:boolean,
 *   meta?:{filters?:{statuses:Array<string>,sources:Array<string>,
 *                   job_codes:Array<{code:string,name:string}>}}}}>}
 */
export async function fetchRuns(params) {
  return apiV2.get('/jobs/runs', { params })
}

/**
 * 执行记录详情（含 `params` / `timeline` / `capabilities`）。
 * @param {number|string} runId
 */
export async function fetchRun(runId) {
  return apiV2.get(`/jobs/runs/${encodeURIComponent(runId)}`)
}

/**
 * 手动运行一次（可选 `scheduled_for`，容差 ±60s）。
 * @param {string} code
 * @param {{params?:object, scheduled_for?:number}} [payload]
 */
export async function runNow(code, payload) {
  return apiV2.post(`/jobs/${encodeURIComponent(code)}/run-now`, payload || {})
}

/**
 * 重试终态 run（新建 run，保留 `attempt` 递增）。
 * @param {number|string} runId
 */
export async function retryRun(runId) {
  return apiV2.post(`/jobs/runs/${encodeURIComponent(runId)}/retry`, {})
}

/**
 * 取消 run（终态返回 409，由调用方按错误码处理）。
 * @param {number|string} runId
 */
export async function cancelRun(runId) {
  return apiV2.post(`/jobs/runs/${encodeURIComponent(runId)}/cancel`, {})
}

// ============================================================================
// 调度器
// ============================================================================

/**
 * 调度器只读状态快照（未注入时后端回落只读视图）。
 * @returns {Promise<{success:boolean,data?:{
 *   enabled:boolean, dry_run:boolean, running:boolean,
 *   backlog:{pending:number, due_triggers:number}}}>}
 */
export async function fetchDispatcherStatus() {
  return apiV2.get('/jobs/dispatcher/status')
}

export default {
  fetchJobs,
  patchJob,
  fetchTriggers,
  createTrigger,
  updateTrigger,
  deleteTrigger,
  fetchRuns,
  fetchRun,
  runNow,
  retryRun,
  cancelRun,
  fetchDispatcherStatus
}