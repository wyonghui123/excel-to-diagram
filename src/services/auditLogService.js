/**
 * auditLogService - 审计日志服务
 *
 * FR-UI-012: 收敛审计日志相关的 API 调用和业务逻辑，消除：
 *   1. useAuditLogs.js 中 'audit_logs' 当 association 的反模式
 *   2. AuditLogManagement.vue 中直调 /audit/overview 的 apiGet
 *   3. AuditLog.vue / AuditLogDetail.vue 中散落的 100+ 行纯函数
 *
 * 三层职责:
 *   1. 纯函数 — 标签格式化、JSON 解析、批量聚合
 *   2. 纯函数 — URL filter 参数构建
 *   3. API    — 通过 httpClient 调 v1 audit API + v2 BO API
 *
 * @module services/auditLogService
 */

import { apiV1, apiV2 } from '@/utils/httpClient'
import { extractItems } from '@/services/associationService'

// ============================================================================
// 1. 纯函数 — 标签格式化
// ============================================================================

const ACTION_LABELS = {
  CREATE: '创建',
  UPDATE: '更新',
  DELETE: '删除',
  READ: '读取',
  LOGIN: '登录',
  LOGOUT: '登出',
  EXPORT: '导出',
  IMPORT: '导入',
  ASSIGN: '分配',
  UNASSIGN: '取消分配',
  EXECUTE: '执行',
  RESTORE: '恢复'
}

const LEVEL_LABELS = {
  DEBUG: '调试',
  INFO: '信息',
  WARNING: '警告',
  ERROR: '错误',
  CRITICAL: '严重'
}

const CATEGORY_LABELS = {
  business: '业务',
  security: '安全',
  system: '系统',
  data: '数据',
  permission: '权限',
  auth: '认证'
}

const COMMON_FIELD_NAMES = {
  id: 'ID',
  name: '名称',
  code: '编码',
  display_name: '显示名称',
  status: '状态',
  created_at: '创建时间',
  updated_at: '更新时间',
  created_by: '创建人',
  updated_by: '更新人',
  description: '描述'
}

/**
 * 格式化操作类型为中文标签
 * @param {string} action
 * @returns {string}
 */
export function formatLogAction(action) {
  if (!action) return ''
  return ACTION_LABELS[action] || action
}

/**
 * 格式化日志级别
 * @param {string} level
 * @returns {string}
 */
export function formatLogLevel(level) {
  if (!level) return ''
  return LEVEL_LABELS[level] || level
}

/**
 * 格式化日志分类
 * @param {string} category
 * @returns {string}
 */
export function formatLogCategory(category) {
  if (!category) return ''
  return CATEGORY_LABELS[category] || category
}

/**
 * 获取字段名（用于审计日志详情显示）
 * @param {string} fieldName
 * @returns {string}
 */
export function getFieldDisplayName(fieldName) {
  if (!fieldName) return ''
  return COMMON_FIELD_NAMES[fieldName] || fieldName
}

// ============================================================================
// 2. 纯函数 — 目标值解析
// ============================================================================

/**
 * 解析 target_value（可能是 JSON 字符串）
 *
 * 例: '{"id":1,"name":"test"}' → 'test（user）'
 * 例: '"plain string"' → 'plain string'
 *
 * @param {string|object} raw
 * @param {string} [objectType]
 * @returns {string}
 */
export function parseTargetDisplay(raw, objectType = '') {
  if (raw === null || raw === undefined) return ''

  if (typeof raw === 'object') {
    return raw.name || raw.display_name || raw.code || JSON.stringify(raw)
  }

  if (typeof raw !== 'string') return String(raw)

  // 尝试解析 JSON
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed === 'object' && parsed !== null) {
      const label = parsed.name || parsed.display_name || parsed.code || parsed.id
      return label ? `${label}（${objectType || parsed.type || ''}）`.replace(/（\s*）/g, '') : raw
    }
    return String(parsed)
  } catch (e) {
    return raw
  }
}

// ============================================================================
// 3. 纯函数 — 批量聚合 / 分组
// ============================================================================

/**
 * 批量关联按 transaction_id 折叠
 *
 * @param {Array} items
 * @returns {Array} 折叠后的项
 */
export function aggregateBatchAssociations(items) {
  if (!Array.isArray(items)) return []

  const groups = new Map()
  for (const item of items) {
    const txId = item.transaction_id || item.id
    if (!groups.has(txId)) {
      groups.set(txId, { ...item, children: [] })
    } else {
      groups.get(txId).children.push(item)
    }
  }
  return Array.from(groups.values())
}

/**
 * 按 transaction_id 分组
 *
 * @param {Array} logs
 * @returns {Map<string, Array>}
 */
export function groupByTransaction(logs) {
  if (!Array.isArray(logs)) return new Map()
  const map = new Map()
  for (const log of logs) {
    const txId = log.transaction_id || log.id
    if (!map.has(txId)) map.set(txId, [])
    map.get(txId).push(log)
  }
  return map
}

// ============================================================================
// 4. 纯函数 — URL filter 参数构建
// ============================================================================

/**
 * 构建审计日志查询参数
 *
 * @param {Object} filters
 * @param {string} [filters.action]
 * @param {string} [filters.level]
 * @param {string} [filters.category]
 * @param {string} [filters.user]
 * @param {string} [filters.startDate]
 * @param {string} [filters.endDate]
 * @returns {Object}
 */
export function buildLogFilter(filters = {}) {
  const out = {}
  if (filters.action) out.action = filters.action
  if (filters.level) out.level = filters.level
  if (filters.category) out.category = filters.category
  if (filters.user) out.user = filters.user
  if (filters.startDate) out.start_date = filters.startDate
  if (filters.endDate) out.end_date = filters.endDate
  if (filters.objectType) out.object_type = filters.objectType
  if (filters.objectId !== undefined && filters.objectId !== null) out.object_id = filters.objectId
  if (filters.transactionId) out.transaction_id = filters.transactionId
  return out
}

// ============================================================================
// 5. API 函数 — v1 审计后端
// ============================================================================

/**
 * 获取审计概览统计
 *
 * @param {Object} [options]
 * @param {number} [options.days=7]
 * @returns {Promise<{success: boolean, data?: Object, message?: string}>}
 */
export async function getOverview({ days = 7 } = {}) {
  return apiV1.get(`/audit/overview?days=${days}`)
}

/**
 * 获取失败日志（仅管理员）
 *
 * @returns {Promise<{success: boolean, data?: Array, message?: string}>}
 */
export async function getFailedLogs() {
  return apiV1.get('/audit/failed')
}

/**
 * 导出审计日志为 CSV
 *
 * @param {Object} [options]
 * @param {Object} [options.filters]
 * @returns {Promise<Blob>}
 */
export async function exportLogs({ filters = {} } = {}) {
  const params = new URLSearchParams(buildLogFilter(filters))
  return apiV1.get(`/audit/logs/export?${params.toString()}`)
}

// ============================================================================
// 6. API 函数 — v2 BO API（替代 useAuditLogs 的 'audit_logs' hack）
// ============================================================================

/**
 * 获取审计日志详情
 *
 * @param {number|string} id
 * @returns {Promise<{success: boolean, data?: Object, message?: string}>}
 */
export async function getLogById(id) {
  return apiV2.get(`/bo/audit_log/${id}`)
}

/**
 * 获取对象的审计日志列表
 *
 * 替代 useAuditLogs.js 中的 queryAssociations(type, id, 'audit_logs', ...) 反模式
 *
 * @param {string} objectType
 * @param {number|string} objectId
 * @param {Object} [options]
 * @param {number} [options.page=1]
 * @param {number} [options.pageSize=20]
 * @param {Object} [options.filters]
 * @returns {Promise<{success: boolean, data?: Object, message?: string}>}
 */
export async function getLogsByObject(objectType, objectId, { page = 1, pageSize = 20, filters = {} } = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    ...buildLogFilter({ ...filters, objectType, objectId })
  })
  return apiV2.get(`/bo/${objectType}/${objectId}/associations/audit_logs?${params.toString()}`)
}

/**
 * 获取关联事件（FR-LOG-013）
 *
 * @param {Object} log
 * @param {Object} [options]
 * @param {boolean} [options.includeChildren=true]
 * @param {boolean} [options.includeParent=true]
 * @returns {Promise<{success: boolean, parent?: Object, children?: Array, message?: string}>}
 */
export async function getRelatedEvents(log, { includeChildren = true, includeParent = true } = {}) {
  if (!log) return { success: false, message: 'log is required' }

  const result = { success: true, parent: null, children: [] }

  try {
    if (includeParent && log.parent_action_id) {
      const parentRes = await getLogById(log.parent_action_id)
      if (parentRes.success) result.parent = parentRes.data
    }

    if (includeChildren) {
      const childrenRes = await apiV2.get(`/bo/audit_log?parent_action_id=${log.id}&page_size=100`)
      if (childrenRes.success) {
        result.children = extractItems(childrenRes)
      }
    }
  } catch (e) {
    result.success = false
    result.message = e?.message || String(e)
  }
  return result
}

/**
 * 按 transaction_id 查询事件
 *
 * @param {string} transactionId
 * @returns {Promise<{success: boolean, events?: Array, total?: number, message?: string}>}
 */
export async function getByTransactionId(transactionId) {
  if (!transactionId) return { success: false, message: 'transactionId is required' }

  const res = await apiV2.get(`/bo/audit_log?transaction_id=${transactionId}&page_size=100`)
  if (res.success) {
    return {
      success: true,
      events: extractItems(res),
      total: res.data?.total || 0
    }
  }
  return res
}

// ============================================================================
// 7. 默认导出
// ============================================================================

export default {
  // 纯函数 - 标签
  formatLogAction,
  formatLogLevel,
  formatLogCategory,
  getFieldDisplayName,
  // 纯函数 - 解析
  parseTargetDisplay,
  // 纯函数 - 聚合
  aggregateBatchAssociations,
  groupByTransaction,
  // 纯函数 - 参数
  buildLogFilter,
  // 常量
  ACTION_LABELS,
  LEVEL_LABELS,
  CATEGORY_LABELS,
  COMMON_FIELD_NAMES,
  // API - v1
  getOverview,
  getFailedLogs,
  exportLogs,
  // API - v2
  getLogById,
  getLogsByObject,
  getRelatedEvents,
  getByTransactionId
}
