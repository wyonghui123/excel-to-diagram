/**
 * sourcingService - 供应来源规则试算与配置校验
 *
 * 对齐后端 meta/api/sourcing_api.py（只调用，不改动）:
 *   GET  /api/v1/sourcing/resolve                    供应来源求值（五步口径）
 *   POST /api/v1/sourcing/rules/<rule_id>/validate    规则配置完整性校验
 *
 * 错误契约（由 httpClient 透传到 businessCode / details）:
 *   400 SOURCING_INVALID_PARAM      details.hint
 *   404 SOURCING_RULE_NOT_FOUND
 *   422 SOURCING_NO_ASSIGNMENT / SOURCING_ALL_LINES_INELIGIBLE / SOURCING_MODE_CONFLICT
 *       details.hint / details.supply_mode / details.explain
 *
 * @module services/sourcingService
 */

import { apiV1 } from '@/utils/httpClient'

/**
 * 供应来源求值。
 * @param {{item_id:number,dest_org_id:number,usage:string,date?:string,dest_location_id?:number}} params
 * @returns {Promise<{success:boolean,data?:object,message?:string,businessCode?:string,details?:object}>}
 */
export async function resolveSourcing(params) {
  return apiV1.get('/sourcing/resolve', { params })
}

/**
 * 校验规则配置（errors 非空属正常业务结果，不是 500）。
 * @param {number|string} ruleId
 * @returns {Promise<{success:boolean,data?:object,message?:string,businessCode?:string}>}
 */
export async function validateSourcingRule(ruleId) {
  return apiV1.post(`/sourcing/rules/${encodeURIComponent(ruleId)}/validate`, {})
}

export default {
  resolveSourcing,
  validateSourcingRule
}
