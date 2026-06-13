/**
 * Base Service - 前端服务基类
 *
 * 提供统一的缓存、认证、响应处理逻辑
 * boService 和 metaService 继承此基类
 */

import { API_BASE, API_BASE_V2, getHeaders } from '@/utils/api'
import { apiV1, apiV2 } from '@/utils/httpClient'
import { useAuthStore } from '@/stores/authStore'
import { LRUCache } from '@/utils/lruCache'

export class BaseService {
  constructor(cacheMaxSize = 100, cacheTimeout = 5 * 60 * 1000) {
    this.cache = new LRUCache(cacheMaxSize)
    this.cacheTimeout = cacheTimeout
    this.API_BASE = API_BASE
    this.API_BASE_V2 = API_BASE_V2
  }

  _getAuthStore() {
    return useAuthStore()
  }

  _getHeaders() {
    return getHeaders(this._getAuthStore())
  }

  _getCacheKey(...parts) {
    return parts.join(':')
  }

  _getCached(key) {
    return this.cache.get(key)
  }

  _setCache(key, data) {
    this.cache.set(key, data, this.cacheTimeout)
  }

  _clearCache(objectType) {
    this.cache.deleteByPrefix(`${objectType}:`)
  }

  /**
   * 通过 httpClient 发送请求 (推荐，新代码使用)
   * @param {string} method - HTTP 方法
   * @param {string} path - 请求路径 (不含 /api/v1 或 /api/v2 前缀)
   * @param {object} [options] - 选项
   * @param {object} [options.body] - 请求体
   * @param {number} [options.version=2] - API 版本 (1 或 2)
   * @returns {Promise<{success: boolean, data: any, message: string, code?: string, httpStatus?: number, traceId: string}>}
   */
  async _request(method, path, options = {}) {
    const { version = 2, ...rest } = options
    const client = version === 1 ? apiV1 : apiV2
    const methodLower = method.toLowerCase()

    if (methodLower === 'get' || methodLower === 'delete') {
      return client[methodLower](path, rest)
    }
    // post, put, patch
    return client[methodLower](path, rest.body, rest)
  }

  /**
   * 处理 fetch Response 对象 (旧接口，保持向后兼容)
   * @deprecated 新代码请使用 _request() 直接获取结构化结果
   */
  async _handleResponse(response) {
    if (!response) {
      return { success: false, message: '网络请求失败' }
    }

    const data = await response.json()

    if (response.status === 401) {
      this._getAuthStore().logout()
      return { success: false, message: '未授权，请重新登录', code: 401 }
    }

    if (!response.ok) {
      return {
        success: false,
        message: data.message || `请求失败: ${response.status}`,
        code: response.status,
        errors: data.errors || []
      }
    }

    return data
  }
}
