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

// --- 运行面：投递实例 ---
export const fetchDeliveries = (params = {}) => apiV2.get(`${BASE}/deliveries`, { params })
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