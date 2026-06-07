/**
 * API 工具函数（精简版）
 *
 * 废弃的 apiGet/apiPost/apiPut/apiDelete/apiPatch/apiGetV2/apiPostV2/apiPutV2/apiDeleteV2 已移除。
 * 请使用 httpClient 命名空间:
 *   import { apiV1, apiV2 } from '@/utils/httpClient'
 *   apiV1.get('/users')
 *   apiV2.post('/action/login', { username, password })
 */

import { setOnUnauthorized as httpClientSetOnUnauthorized } from '@/utils/httpClient'

export const API_BASE = '/api/v1'
export const API_BASE_V2 = '/api/v2'

export function setOnUnauthorized(callback) {
  // 同步到 httpClient
  httpClientSetOnUnauthorized(callback)
}

export function getHeaders(authStore) {
  return {
    'Content-Type': 'application/json',
    ...authStore.getAuthHeaders()
  }
}
