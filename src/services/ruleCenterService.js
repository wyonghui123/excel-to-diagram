/**
 * 规则中心 API 客户端（FR-014 / FR-015）
 *
 * 全部为只读端点，统一返回 { success, data }。
 */
import { apiV2 } from '@/utils/httpClient'

/** 规则中心视图元数据（页签 / 列 / 详情分区唯一数据源）。 */
export function getRuleCenterViewConfig() {
  return apiV2.get('/rules/view-config')
}

let _viewConfigCache = null

/**
 * 视图元数据的进程内缓存（多页面共用页签/文案映射，避免重复请求）。
 * 规则中心页面仍用 getRuleCenterViewConfig() 以便手动刷新。
 */
export function getRuleCenterViewConfigCached() {
  if (!_viewConfigCache) {
    _viewConfigCache = getRuleCenterViewConfig().catch((err) => {
      _viewConfigCache = null
      throw err
    })
  }
  return _viewConfigCache
}

/** 规则目录（多来源聚合）。 */
export function listRules(params = {}) {
  return apiV2.get('/rules', { params })
}

/** 规则详情。 */
export function getRule(ruleKey) {
  return apiV2.get(`/rules/${encodeURIComponent(ruleKey)}`)
}

/** 单据推导链（IF-007）。 */
export function getRuleTrace(objectType, recordId, params = {}) {
  return apiV2.get(`/bo/${objectType}/${recordId}/rule-trace`, { params })
}

/** 单场景解释（IF-003）。 */
export function explainRule(objectType, payload) {
  return apiV2.post(`/bo/${objectType}/rules/explain`, payload)
}

/** 规则试算（IF-008，只读）：config_mode=baseline|draft|both。 */
export function simulateRule(payload) {
  return apiV2.post('/rules/simulate', payload)
}

/** 保存配置草稿（target=control_parameter_value|line_type_assignment）。 */
export function saveRuleConfigDraft(payload) {
  return apiV2.post('/rules/config/draft', payload)
}

/** 校验并发布草稿。 */
export function publishRuleConfig(payload) {
  return apiV2.post('/rules/config/publish', payload)
}

/** 按上一发布版本回滚。 */
export function rollbackRuleConfig(payload) {
  return apiV2.post('/rules/config/rollback', payload)
}

/** 配置发布 / 回滚历史（audit_logs）。 */
export function getRuleConfigHistory(params = {}) {
  return apiV2.get('/rules/config/history', { params })
}