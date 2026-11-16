/**
 * integrationService - 集成模块前端 API（M5 运行面三视图）
 *
 * 配置面：连接 connection
 * 运行面：投递实例 delivery（in / out messages）
 * 交付面：导入批次 import batch（staging 三段式）
 */
import { apiV2 } from '@/utils/httpClient'

const BASE = '/integrations'

const enc = (value) => encodeURIComponent(String(value))

// --- 配置面：连接 ---
export const fetchConnections = (params = {}) => apiV2.get(`${BASE}/connections`, { params })
export const createConnection = (payload) => apiV2.post(`${BASE}/connections`, payload)
export const updateConnection = (code, payload) =>
  apiV2.put(`${BASE}/connections/${enc(code)}`, payload)
export const deleteConnection = (code) => apiV2.delete(`${BASE}/connections/${enc(code)}`)
export const testConnection = (code) =>
  apiV2.post(`${BASE}/connections/${enc(code)}/test`, {})

// --- 取值域：下拉选项统一来自后端 YAML 元数据（前端不再复制常量数组）---
export const fetchIntegrationOptions = () => apiV2.get(`${BASE}/options`)

// --- 运行面：投递实例 ---
export const fetchDeliveries = (params = {}) => apiV2.get(`${BASE}/deliveries`, { params })
// 顶部指标：状态分布 / 可重试 / 重试耗尽 / 平均耗时（后端聚合，状态标题来自 YAML）
export const fetchDeliveryStats = () => apiV2.get(`${BASE}/deliveries/stats`)
export const retryDelivery = (id) => apiV2.post(`${BASE}/deliveries/${enc(id)}/retry`, {})

// --- 交付面：导入批次 ---
export const fetchImportBatches = (params = {}) => apiV2.get(`${BASE}/imports`, { params })
export const fetchImportBatch = (batchNo) => apiV2.get(`${BASE}/imports/${enc(batchNo)}`)
export const fetchImportRows = (batchNo, params = {}) =>
  apiV2.get(`${BASE}/imports/${enc(batchNo)}/rows`, { params })
// 批次详情返回的报告地址带 /api/v2 前缀，下载时裁掉再由 apiV2 统一拼接
const API_V2_PREFIX = '/api/v2'

export const fetchImportErrorReport = (batchNo, reportUrl) => {
  const path = reportUrl && reportUrl.startsWith(API_V2_PREFIX)
    ? reportUrl.slice(API_V2_PREFIX.length)
    : `${BASE}/imports/${enc(batchNo)}/error-report`
  return apiV2.download(path)
}