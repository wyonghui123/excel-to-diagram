/**
 * schedulerService - 调度器状态与手动触发服务（只读状态 + run-now）
 *
 * 职责:
 *   - fetchSchedulerStatus: 拉取进程内调度器状态（运维/平台两组作业 + 暂停态）
 *   - runSchedulerJob:      手动触发指定作业码（立即执行一次）
 *
 * 纪律（对齐后端 meta/api/scheduler_api.py）:
 *   - 两个端点为无条件注册的只读/触发接口，无需登录鉴权以外的额外参数
 *   - 未接线时 status 返回 503（success=false），由调用方按错误分支处理
 *   - code 走路径参数，必须先 encodeURIComponent（code 可能含特殊字符）
 *
 * @module services/schedulerService
 */

import { apiV2 } from '@/utils/httpClient'

// ============================================================================
// API — v2 schedulers 端点
// ============================================================================

/**
 * 拉取调度器状态。
 * @returns {Promise<{success:boolean,data?:{paused:boolean,maintenance:Object|null,platform:Object|null},message?:string}>}
 */
export async function fetchSchedulerStatus() {
  return apiV2.get('/schedulers/status')
}

/**
 * 立即执行指定作业。
 * @param {string} code 作业码
 * @returns {Promise<{success:boolean,message?:string}>}
 */
export async function runSchedulerJob(code) {
  return apiV2.post(`/schedulers/${encodeURIComponent(code)}/run-now`, {})
}

export default {
  fetchSchedulerStatus,
  runSchedulerJob
}
