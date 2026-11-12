import { apiV2 } from '@/utils/httpClient'

/** 规则清单（可按源 / 目标 BO 过滤） */
export async function listRules(params = {}) {
  const resp = await apiV2.get('/doc-flow/rules', { params })
  return resp.data
}

/** 上游实例 + 已生成 + 未结量（分页） */
export async function listSources(ruleId, params = {}) {
  const resp = await apiV2.get('/doc-flow/sources', {
    params: { rule_id: ruleId, ...params },
  })
  return resp.data
}

/** 按上游行批量生成本次下游数量 */
export async function deriveDocuments(payload) {
  const resp = await apiV2.post('/doc-flow/derive', payload)
  return resp.data
}

/** 边追溯（源侧或目标侧二选一） */
export async function listEdges(params = {}) {
  const resp = await apiV2.get('/doc-flow/edges', { params })
  return resp.data
}

/** 头→行展开后的上下游追溯（id 可传单据头或行，单次返回 upstream/downstream） */
export async function traceDocuments(params = {}) {
  const resp = await apiV2.get('/doc-flow/trace', { params })
  return resp.data
}