/**
 * associationService - BO 关联管理服务
 *
 * FR-UI-013: 收敛 BO 关联相关的 API 调用和业务逻辑。
 * FR-GAP-018: 添加 LRU 缓存层，替代 boAssociationService 的缓存能力。
 *
 * 三层职责:
 *   1. 纯函数 — 结果兼容、参数归一化、缓存键
 *   2. 纯函数 — 状态映射（assign/unassign/batch_xxx）
 *   3. API    — 直接通过 httpClient 调 v1/v2 BO association API（带 LRU 缓存）
 *
 * 缓存策略:
 *   - 读操作缓存: queryAssociations, queryV2, countV2
 *   - 写操作失效: associate, dissociate, assignV2, unassignV2, batchAssignV2, batchUnassignV2
 *   - 缓存键格式: objectType:assoc:{v1|v2}:associationName:id:params (兼容 boAssociationService)
 *   - 写操作同时清除 objectType:query: 前缀 (兼容 boCrudService list cache)
 *
 * @module services/associationService
 */

import { apiV1, apiV2 } from '@/utils/httpClient'
import { LRUCache } from '@/utils/lruCache'

// ============================================================================
// 0. 模块级 LRU 缓存实例
// ============================================================================

const _cache = new LRUCache(100)
const _cacheTimeout = 5 * 60 * 1000 // 5 分钟

/**
 * 稳定序列化（与 boBaseService._stableStringify 兼容）
 */
function _stableStringify(obj) {
  if (obj === null || obj === undefined) return ''
  if (typeof obj !== 'object') return String(obj)
  const sorted = {}
  Object.keys(obj).sort().forEach(key => {
    sorted[key] = _stableStringify(obj[key])
  })
  return JSON.stringify(sorted)
}

/**
 * 构建缓存键（兼容 boAssociationService 格式）
 *
 * boAssociationService 格式: objectType:assoc:associationName:id:stableStringify(params)
 * boAssociationService V2 格式: objectType:assocV2:associationName:id:JSON.stringify(params)
 *
 * @param {string} objectType
 * @param {string} prefix - 'assoc' | 'assocV2' | 'assocCount'
 * @param {string} associationName
 * @param {string|number} id
 * @param {Object} params
 * @returns {string}
 */
function _buildCacheKey(objectType, prefix, associationName, id, params = {}) {
  return `${objectType}:${prefix}:${associationName}:${id}:${_stableStringify(params)}`
}

/**
 * 使关联缓存失效（写操作调用）
 *
 * 清除范围:
 *   1. objectType:assoc:{associationName}:{id}:* (关联查询缓存)
 *   2. objectType:assocV2:{associationName}:{id}:* (V2 关联查询缓存)
 *   3. objectType:assocCount:{associationName}:{id}:* (计数缓存)
 *   4. objectType:query:* (列表查询缓存，兼容 boCrudService)
 */
function _invalidateCache(objectType, id, associationName = null) {
  if (associationName) {
    _cache.deleteByPrefix(`${objectType}:assoc:${associationName}:${id}:`)
    _cache.deleteByPrefix(`${objectType}:assocV2:${associationName}:${id}:`)
    _cache.deleteByPrefix(`${objectType}:assocCount:${associationName}:${id}:`)
  } else {
    _cache.deleteByPrefix(`${objectType}:assoc:`)
    _cache.deleteByPrefix(`${objectType}:assocV2:`)
    _cache.deleteByPrefix(`${objectType}:assocCount:`)
  }
  // 兼容 boCrudService 的 list cache 前缀
  _cache.deleteByPrefix(`${objectType}:query:`)
}

/**
 * 清除指定 objectType 的所有缓存
 * @param {string} objectType
 */
export function clearCache(objectType) {
  if (objectType) {
    _cache.deleteByPrefix(`${objectType}:`)
  } else {
    _cache.clear()
  }
}

// ============================================================================
// 1. 纯函数 — 结果兼容 / 参数归一化
// ============================================================================

/**
 * 判断调用是否成功
 *
 * 兼容以下返回类型:
 *   - { success: true, ... }
 *   - true（204 No Content 场景）
 *   - undefined / null → false
 *
 * @param {*} result
 * @returns {boolean}
 */
export function isSuccess(result) {
  if (result === true) return true
  if (result && typeof result === 'object' && result.success === true) return true
  return false
}

/**
 * 从结果中提取 items 数组
 *
 * 兼容以下返回结构:
 *   - { data: { items: [...] } }
 *   - { items: [...] }
 *   - [...]（直接数组）
 *
 * @param {*} result
 * @returns {Array}
 */
export function extractItems(result) {
  if (!result) return []
  if (Array.isArray(result)) return result
  if (result.data?.items) return result.data.items
  if (result.items) return result.items
  return []
}

/**
 * 归一化关联参数
 *
 * 1. 过滤 null/undefined/''
 * 2. 转 String 防止 URLSearchParams 抛错
 *
 * @param {Object} params
 * @returns {Object}
 */
export function normalizeAssocParams(params = {}) {
  const out = {}
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    out[k] = String(v)
  }
  return out
}

/**
 * 构建关联缓存 key
 *
 * @param {string} objectType
 * @param {string|number} id
 * @param {string} associationName
 * @param {Object} params
 * @returns {string}
 */
export function buildAssocCacheKey(objectType, id, associationName, params = {}) {
  return `${objectType}:${id}:${associationName}:${JSON.stringify(normalizeAssocParams(params))}`
}

/**
 * 构建查询字符串
 *
 * @param {Object} params
 * @returns {string}
 */
function buildQuery(params = {}) {
  const normalized = normalizeAssocParams(params)
  const qs = new URLSearchParams(normalized).toString()
  return qs ? `?${qs}` : ''
}

// ============================================================================
// 2. 纯函数 — 状态映射
// ============================================================================

const ACTION_API_MAP = {
  assign: 'associate',
  unassign: 'unassignV2',
  batch_assign: 'batchAssignV2',
  batch_unassign: 'batchUnassignV2',
  query: 'queryV1',
  query_v2: 'queryV2',
  count_v2: 'countV2'
}

/**
 * action 名 → boService 方法名
 * @param {string} action
 * @returns {string|null}
 */
export function mapActionToApiMethod(action) {
  return ACTION_API_MAP[action] || null
}

// ============================================================================
// 3. API 函数 — 直接调 v1/v2 BO association API
// ============================================================================

/**
 * v1 关联分配（POST + body + 缓存失效）
 *
 * @deprecated 推荐使用 addByTargetId() — 语义化命名
 */
export async function associate(objectType, id, associationName, targetId, targetType = null) {
  const body = { target_id: targetId }
  if (targetType) body.target_type = targetType
  const result = await apiV2.post(`/bo/${objectType}/${id}/associations/${associationName}`, body)
  if (result.success) {
    _invalidateCache(objectType, id, associationName)
  }
  return result
}

/**
 * v1 关联取消（DELETE + query string + 缓存失效）
 *
 * @deprecated 推荐使用 removeByTargetId()
 */
export async function dissociate(objectType, id, associationName, targetId, targetType = null) {
  const params = new URLSearchParams({ target_id: String(targetId) })
  if (targetType) params.append('target_type', targetType)
  const result = await apiV2.delete(`/bo/${objectType}/${id}/associations/${associationName}?${params}`)
  if (result.success) {
    _invalidateCache(objectType, id, associationName)
  }
  return result
}

/**
 * v1 关联查询（带缓存）
 *
 * @deprecated 推荐使用 queryV2()
 */
export async function queryAssociations(objectType, id, associationName, params = {}) {
  const cacheKey = _buildCacheKey(objectType, 'assoc', associationName, id, params)
  const cached = _cache.get(cacheKey)
  if (cached) return cached

  const result = await apiV2.get(`/bo/${objectType}/${id}/associations/${associationName}${buildQuery(params)}`)
  if (result.success) {
    _cache.set(cacheKey, result, _cacheTimeout)
  }
  return result
}

/**
 * v2 关联查询（$associations + 缓存）
 */
export async function queryV2(objectType, id, associationName, params = {}) {
  const cacheKey = _buildCacheKey(objectType, 'assocV2', associationName, id, params)
  const cached = _cache.get(cacheKey)
  if (cached) return cached

  const result = await apiV2.get(`/bo/${objectType}/${id}/$associations/${associationName}${buildQuery(params)}`)
  if (result.success) {
    _cache.set(cacheKey, result, _cacheTimeout)
  }
  return result
}

/**
 * v2 关联计数（带缓存）
 */
export async function countV2(objectType, id, associationName) {
  const cacheKey = _buildCacheKey(objectType, 'assocCount', associationName, id)
  const cached = _cache.get(cacheKey)
  if (cached) return cached

  const result = await apiV2.get(`/bo/${objectType}/${id}/$associations/${associationName}/count`)
  if (result.success) {
    _cache.set(cacheKey, result, _cacheTimeout)
  }
  return result
}

/**
 * v2 关联分配（POST /assign + 缓存失效）
 *
 * 兼容 204 No Content 响应（返回 true）
 */
export async function assignV2(objectType, id, associationName, data = {}) {
  const res = await apiV2.post(`/bo/${objectType}/${id}/$associations/${associationName}/assign`, data)
  const result = (res && typeof res === 'object' && res.status === 204) ? true : res
  if (result === true || (result && result.success)) {
    _invalidateCache(objectType, id, associationName)
  }
  return result
}

/**
 * v2 关联取消（POST /unassign + 缓存失效）
 *
 * 兼容 204 No Content 响应（返回 true）
 */
export async function unassignV2(objectType, id, associationName, data = {}) {
  const res = await apiV2.post(`/bo/${objectType}/${id}/$associations/${associationName}/unassign`, data)
  const result = (res && typeof res === 'object' && res.status === 204) ? true : res
  if (result === true || (result && result.success)) {
    _invalidateCache(objectType, id, associationName)
  }
  return result
}

/**
 * v2 批量分配（+ 缓存失效）
 *
 * @param {string} objectType
 * @param {string|number} id
 * @param {string} associationName
 * @param {Array<number>} targetIds - 目标 ID 列表
 * @param {Object} [options={}]
 * @param {string} [options.targetType] - 目标类型
 * @param {Object} [options.metadata] - 附加元数据
 */
export async function batchAssignV2(objectType, id, associationName, targetIds, options = {}) {
  const body = { target_ids: targetIds }
  if (options.targetType) body.target_type = options.targetType
  if (options.metadata) body.metadata = options.metadata
  const result = await apiV2.post(`/bo/${objectType}/${id}/$associations/${associationName}/batch_assign`, body)
  if (result.success) {
    _invalidateCache(objectType, id, associationName)
  }
  return result
}

/**
 * v2 批量取消（+ 缓存失效）
 *
 * @param {string} objectType
 * @param {string|number} id
 * @param {string} associationName
 * @param {Array<number>} [targetIds=[]] - 目标 ID 列表
 * @param {Object} [options={}]
 * @param {string} [options.targetType] - 目标类型
 * @param {Array<number>} [options.associationRecordIds] - 关联记录 ID 列表
 */
export async function batchUnassignV2(objectType, id, associationName, targetIds = [], options = {}) {
  const body = {}
  if (targetIds?.length) body.target_ids = targetIds
  if (options.targetType) body.target_type = options.targetType
  if (options.associationRecordIds) body.association_record_ids = options.associationRecordIds
  const result = await apiV2.post(`/bo/${objectType}/${id}/$associations/${associationName}/batch_unassign`, body)
  if (result.success) {
    _invalidateCache(objectType, id, associationName)
  }
  return result
}

/**
 * 跨源批量查询
 */
export function batchQuery(objectType, associationName, data = {}) {
  return apiV2.post(`/bo/${objectType}/$associations/${associationName}/batch-query`, data)
}

/**
 * 检索时带关联展开（+ 缓存失效）
 */
export async function retrieveWithAssociations(objectType, id, options = {}) {
  const { associations = [], depth = 1 } = options
  const params = new URLSearchParams()
  if (associations.length > 0) params.append('associations', associations.join(','))
  params.append('depth', String(depth))
  const result = await apiV2.get(`/bo/${objectType}/${id}/retrieve?${params.toString()}`)
  if (result.success) {
    _invalidateCache(objectType, id)
  }
  return result
}

// ============================================================================
// 4. 语义化 API（新增 — 替代 v1/v2 混乱命名）
// ============================================================================

/**
 * 通过目标 ID 分配关联（语义化命名 — 替代 associate()）
 *
 * @param {string} objectType
 * @param {string|number} id
 * @param {string} associationName
 * @param {string|number} targetId
 * @param {string} [targetType=null]
 */
export function addByTargetId(objectType, id, associationName, targetId, targetType = null) {
  return associate(objectType, id, associationName, targetId, targetType)
}

/**
 * 通过关联记录 ID 取消关联（语义化命名 — 替代 unassignV2()）
 *
 * 注意：参数是 association_record_id 而非 target_id
 *
 * @param {string} objectType
 * @param {string|number} id
 * @param {string} associationName
 * @param {string|number} recordId
 */
export function removeByRecordId(objectType, id, associationName, recordId) {
  return unassignV2(objectType, id, associationName, { association_record_id: recordId })
}

// ============================================================================
// 5. 默认导出
// ============================================================================

export default {
  // 缓存管理
  clearCache,
  // 纯函数
  isSuccess,
  extractItems,
  normalizeAssocParams,
  buildAssocCacheKey,
  mapActionToApiMethod,
  // API
  associate,
  dissociate,
  queryAssociations,
  queryV2,
  countV2,
  assignV2,
  unassignV2,
  batchAssignV2,
  batchUnassignV2,
  batchQuery,
  retrieveWithAssociations,
  // 语义化
  addByTargetId,
  removeByRecordId
}
