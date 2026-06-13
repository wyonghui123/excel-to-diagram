/**
 * httpClient - 统一 HTTP 客户端
 *
 * FR-UI-001: 替代散落的 fetch() 调用，提供:
 * - 统一 credentials: 'include' (Cookie 认证)
 * - 统一错误码 (ErrorCode 枚举)
 * - 统一响应格式 { success, data, message, code, httpStatus, traceId }
 * - 401 自动拦截 (onUnauthorized 回调)
 * - 请求/响应拦截器
 * - 慢请求日志 (>1s)
 * - AbortSignal / timeout 支持
 *
 * 命名空间导出:
 *   import { apiV1, apiV2 } from '@/utils/httpClient'
 *   apiV1.get('/users')
 *   apiV2.post('/action/login', { username, password })
 */

import { API_BASE, API_BASE_V2, getHeaders } from '@/utils/api'
import { useAuthStore } from '@/stores/authStore'
import { logger } from '@/utils/logger'

// ---------------------------------------------------------------------------
// ErrorCode 枚举 —— HTTP 传输层错误（注意：与业务错误不同源）
// ---------------------------------------------------------------------------
// ⚠️ 本枚举仅用于 httpClient 内部构造 transport 错误响应（NETWORK/TIMEOUT/4xx/5xx）。
// 业务错误（如 token_expired、action_failed 等）请用 '@/composables/errorCodes' 的
// ErrorCodes（auto-generated from meta/core/error_codes.py），其值风格为 lowercase snake_case。
// 本枚举与 ErrorCodes 故意保持值风格不同（UPPER_SNAKE vs lowercase）以体现分层。
// ---------------------------------------------------------------------------
export const ErrorCode = Object.freeze({
  ERR_NETWORK:          'NETWORK_ERROR',
  ERR_TIMEOUT:          'TIMEOUT',
  ERR_ABORT:            'ABORTED',
  ERR_400_BAD_REQUEST:  'BAD_REQUEST',
  ERR_401_UNAUTHORIZED: 'UNAUTHORIZED',
  ERR_403_FORBIDDEN:    'FORBIDDEN',
  ERR_404_NOT_FOUND:    'NOT_FOUND',
  ERR_409_CONFLICT:     'CONFLICT',
  ERR_422_VALIDATION:   'VALIDATION_ERROR',
  ERR_429_RATE_LIMITED: 'RATE_LIMITED',
  ERR_500_SERVER:       'SERVER_ERROR',
  ERR_502_BAD_GATEWAY:  'BAD_GATEWAY',
  ERR_503_UNAVAILABLE:  'SERVICE_UNAVAILABLE',
  ERR_504_TIMEOUT:      'GATEWAY_TIMEOUT',
  ERR_PARSE:            'PARSE_ERROR',
  ERR_UNKNOWN:          'UNKNOWN_ERROR',
})

const HTTP_STATUS_TO_ERROR_CODE = {
  400: ErrorCode.ERR_400_BAD_REQUEST,
  401: ErrorCode.ERR_401_UNAUTHORIZED,
  403: ErrorCode.ERR_403_FORBIDDEN,
  404: ErrorCode.ERR_404_NOT_FOUND,
  409: ErrorCode.ERR_409_CONFLICT,
  422: ErrorCode.ERR_422_VALIDATION,
  429: ErrorCode.ERR_429_RATE_LIMITED,
  500: ErrorCode.ERR_500_SERVER,
  502: ErrorCode.ERR_502_BAD_GATEWAY,
  503: ErrorCode.ERR_503_UNAVAILABLE,
  504: ErrorCode.ERR_504_TIMEOUT,
}

// ---------------------------------------------------------------------------
// 拦截器 & 回调
// ---------------------------------------------------------------------------
const requestInterceptors = []
const responseInterceptors = []
let onUnauthorizedCallback = null

/**
 * 注册请求拦截器
 * @param {(url: string, options: object) => void} fn
 */
export function registerRequestInterceptor(fn) {
  requestInterceptors.push(fn)
}

/**
 * 注册响应拦截器
 * @param {(result: object) => void} fn
 */
export function registerResponseInterceptor(fn) {
  responseInterceptors.push(fn)
}

/**
 * 设置 401 未授权回调 (与 api.js 的 setOnUnauthorized 对齐)
 * @param {() => void} callback
 */
export function setOnUnauthorized(callback) {
  onUnauthorizedCallback = callback
}

// ---------------------------------------------------------------------------
// traceId 生成 (FR-013)
// 使用 crypto.randomUUID() (Chrome 92+, Edge 92+, Firefox 95+, Safari 15.4+)
// Fallback: crypto.getRandomValues() (更广泛的浏览器支持)
// 旧实现使用 Math.random() 是非加密安全,traceId 可被猜测
// ---------------------------------------------------------------------------
function generateTraceId() {
  // 优先: 原生 randomUUID
  if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
    return window.crypto.randomUUID()
  }
  // Fallback: 32 字符 hex (与旧版兼容长度)
  if (typeof window !== 'undefined' && window.crypto?.getRandomValues) {
    const arr = new Uint8Array(16)
    window.crypto.getRandomValues(arr)
    return Array.from(arr, b => b.toString(16).padStart(2, '0')).join('')
  }
  // 终极 fallback: 旧实现 (仅在 crypto 不可用时)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

// ---------------------------------------------------------------------------
// In-flight 请求去重 (FR-017)
// 相同 GET 请求并发时复用同一个 Promise，避免重复网络请求
// ---------------------------------------------------------------------------
const inflightCache = new Map()

/**
 * 把 options.params 序列化为 query string 并拼到 URL 上
 *
 * [FIX-2026-06-08] 修复 loadConditionRules 不传 role_id 的全局 bug
 *   - 之前 URL 直接 = `${baseUrl}${path}`, 完全忽略 options.params
 *   - 现在: 把 params 拼成 query string, 跳过 null/undefined, 用 URLSearchParams 做正确编码
 *   - 影响: 13+ 个 API 接口 (permissionService, filterVariant, annotation 等)
 *
 * 行为:
 *   - 无 params / 空对象 → 返回 baseUrl + path (不加 `?`)
 *   - 有值参数 → 拼成 ?k1=v1&k2=v2 (URL 编码)
 *   - null / undefined 值 → 跳过
 *   - 数组 / 对象 → 转为 JSON 字符串 (避免歧义)
 *
 * @param {string} baseUrl - 如 '/api/v1'
 * @param {string} path - 如 '/permission-rules'
 * @param {object|undefined} params - 如 { role_id: 1803, page: 1 }
 * @returns {string} - 完整 URL, 如 '/api/v1/permission-rules?role_id=1803'
 */
function buildUrlWithParams(baseUrl, path, params) {
  if (!params || typeof params !== 'object' || Object.keys(params).length === 0) {
    return `${baseUrl}${path}`
  }
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue
    if (Array.isArray(v)) {
      // [FIX-2026-06-08] 数组: 展开为同名多次参数
      //   filter_product_id: [18, 19] → ?filter_product_id=18&filter_product_id=19
      //   后端 Flask request.args.getlist() 解析, 用于 SQL IN
      //   之前 JSON.stringify() 错误, getlist() 拿到 ['"[18,19]"'] 无法 IN 匹配
      for (const item of v) {
        if (item === undefined || item === null || item === '') continue
        qs.append(k, String(item))
      }
    } else if (typeof v === 'object') {
      // 普通对象 → JSON 字符串
      qs.append(k, JSON.stringify(v))
    } else {
      qs.append(k, String(v))
    }
  }
  const qsStr = qs.toString()
  return qsStr ? `${baseUrl}${path}?${qsStr}` : `${baseUrl}${path}`
}

/**
 * 生成去重缓存 key
 * GET /api/v1/users → "GET:/api/v1/users:"
 * POST 不参与去重
 */
function getCacheKey(method, url, body) {
  const bodyStr = body ? JSON.stringify(body) : ''
  return `${method}:${url}:${bodyStr}`
}

// ---------------------------------------------------------------------------
// 核心请求函数
// ---------------------------------------------------------------------------
const SLOW_REQUEST_THRESHOLD_MS = 1000

/**
 * 统一请求入口
 * @param {string} method - HTTP 方法
 * @param {string} baseUrl - API 基础路径 (API_BASE 或 API_BASE_V2)
 * @param {string} path - 请求路径 (如 '/users')
 * @param {object} [options]
 * @param {object} [options.body] - 请求体 (POST/PUT/PATCH，支持 FormData)
 * @param {object} [options.headers] - 额外请求头
 * @param {number} [options.timeout] - 请求超时 (ms)
 * @param {AbortSignal} [options.signal] - 取消信号
 * @param {'json'|'blob'} [options.responseType='json'] - 响应类型 (blob 用于文件下载)
 * @param {object} [options.authStore] - 认证 store 实例 (可选，默认自动获取)
 * @param {boolean} [options.dedupe] - GET 请求去重 (默认 true，设 false 跳过)
 * @returns {Promise<{success: boolean, data: any, message: string, code?: string, httpStatus?: number, traceId: string}>}
 */
async function request(method, baseUrl, path, options = {}) {
  const traceId = generateTraceId()
  const startTime = Date.now()
  // [FIX-2026-06-08] 将 options.params 序列化为 query string 拼到 URL 上
  //   原因: 之前直接用 `${baseUrl}${path}` 构造 URL, 导致所有 { params: {...} } 参数被丢弃,
  //   loadConditionRules({ role_id: 1803 }) 实际请求变成 GET /permission-rules (无 query),
  //   后端走 get_all_rules() 分支返回全部 39 条规则, 任意角色都看到同样的 10+ 条 domain 规则.
  const url = buildUrlWithParams(baseUrl, path, options.params)

  // [FR-017] In-flight 去重: GET 请求默认去重
  const shouldDedupe = method === 'GET'
    && options.dedupe !== false
    && !options.signal
    && options.responseType !== 'blob'

  if (shouldDedupe) {
    // 注意: cache key 必须用含 query 的完整 URL,
    // 否则 GET /users?page=1 和 GET /users?page=2 会被错误去重成同一次请求.
    const cacheKey = getCacheKey(method, url, options.body)
    const existing = inflightCache.get(cacheKey)
    if (existing) {
      logger.debug(`[httpClient] Deduped request: ${method} ${url} (traceId=${traceId})`)
      return existing
    }
    // 创建 Promise 并缓存，确保自身和后续并发请求拿到同一个引用
    const promise = _doRequest(method, url, options, traceId, startTime)
    inflightCache.set(cacheKey, promise)
    try {
      const result = await promise
      return result
    } finally {
      inflightCache.delete(cacheKey)
    }
  }

  return _doRequest(method, url, options, traceId, startTime)
}

/**
 * 实际执行请求 (从 request() 抽出，供去重逻辑复用)
 */
async function _doRequest(method, url, options, traceId, startTime) {

  // 获取 authStore (优先使用传入的，否则自动获取)
  const authStore = options.authStore || useAuthStore()

  // 构建 headers
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  const headers = {
    ...getHeaders(authStore),
    ...options.headers,
  }
  // FormData: 移除 Content-Type，让浏览器自动设置 multipart/form-data boundary
  if (isFormData) {
    delete headers['Content-Type']
  }

  // 构建 fetch options
  const fetchOptions = {
    method,
    headers,
    credentials: 'include',
  }

  // body (POST/PUT/PATCH)
  if (options.body !== undefined) {
    fetchOptions.body = isFormData ? options.body : JSON.stringify(options.body)
  }

  // AbortSignal
  if (options.signal) {
    fetchOptions.signal = options.signal
  }

  // timeout: 通过 AbortController 实现
  let timeoutId = null
  let controller = null
  if (options.timeout && !options.signal) {
    controller = new AbortController()
    fetchOptions.signal = controller.signal
    timeoutId = setTimeout(() => controller.abort(), options.timeout)
  }

  // 执行请求拦截器
  for (const interceptor of requestInterceptors) {
    try { interceptor(url, fetchOptions) } catch (_) { /* ignore */ }
  }

  let resp
  try {
    resp = await fetch(url, fetchOptions)
  } catch (e) {
    // 区分 abort / timeout / network error
    const isAbort = e instanceof DOMException && e.name === 'AbortError'
    const isTimeout = isAbort && timeoutId !== null

    const result = {
      success: false,
      data: null,
      message: isTimeout ? '请求超时' : (isAbort ? '请求已取消' : '网络错误'),
      code: isTimeout ? ErrorCode.ERR_TIMEOUT : (isAbort ? ErrorCode.ERR_ABORT : ErrorCode.ERR_NETWORK),
      traceId,
    }

    for (const interceptor of responseInterceptors) {
      try { interceptor(result) } catch (_) { /* ignore */ }
    }

    return result
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }

  // 慢请求日志
  const elapsed = Date.now() - startTime
  if (elapsed > SLOW_REQUEST_THRESHOLD_MS) {
    // [FR-001] 替换 console.warn → logger.warn
    logger.warn(`[httpClient] Slow request: ${method} ${url} took ${elapsed}ms (traceId=${traceId})`)
  }

  // 401 处理
  if (resp.status === 401) {
    if (onUnauthorizedCallback) {
      onUnauthorizedCallback()
    }
    const result = {
      success: false,
      data: null,
      message: '未授权，请重新登录',
      code: ErrorCode.ERR_401_UNAUTHORIZED,
      httpStatus: 401,
      traceId,
    }
    for (const interceptor of responseInterceptors) {
      try { interceptor(result) } catch (_) { /* ignore */ }
    }
    return result
  }

  // 解析响应
  const responseType = options.responseType || 'json'

  // Blob 响应 (文件下载)
  if (responseType === 'blob') {
    if (!resp.ok) {
      // 尝试解析 JSON 错误信息
      let errorMsg = `请求失败: ${resp.status}`
      try {
        const errBody = await resp.json()
        errorMsg = errBody.message || errorMsg
      } catch (_) { /* ignore */ }
      const errorCode = HTTP_STATUS_TO_ERROR_CODE[resp.status] || ErrorCode.ERR_UNKNOWN
      const result = {
        success: false,
        data: null,
        message: errorMsg,
        code: errorCode,
        httpStatus: resp.status,
        traceId,
      }
      for (const interceptor of responseInterceptors) {
        try { interceptor(result) } catch (_) { /* ignore */ }
      }
      return result
    }
    const blob = await resp.blob()
    const result = {
      success: true,
      data: blob,
      message: '',
      traceId,
    }
    for (const interceptor of responseInterceptors) {
      try { interceptor(result) } catch (_) { /* ignore */ }
    }
    return result
  }

  // JSON 响应 (默认)
  let body
  try {
    body = await resp.json()
  } catch (_) {
    const result = {
      success: false,
      data: null,
      message: `响应解析失败 (status=${resp.status})`,
      code: ErrorCode.ERR_PARSE,
      httpStatus: resp.status,
      traceId,
    }
    for (const interceptor of responseInterceptors) {
      try { interceptor(result) } catch (_) { /* ignore */ }
    }
    return result
  }

  // 非 2xx
  if (!resp.ok) {
    const errorCode = HTTP_STATUS_TO_ERROR_CODE[resp.status] || ErrorCode.ERR_UNKNOWN
    const result = {
      success: false,
      data: body.data || body.errors || null,
      message: body.message || `请求失败: ${resp.status}`,
      code: errorCode,
      httpStatus: resp.status,
      traceId,
    }
    // 兼容旧 _handleResponse: errors 保持在顶层（useBOApi/useMetaList 依赖 result.errors）
    if (body.errors) {
      result.errors = body.errors
    }
    // 兼容旧 _handleResponse: error_code 保持在顶层（boCrudService deepInsert 依赖）
    if (body.error_code) {
      result.error_code = body.error_code
    }
    for (const interceptor of responseInterceptors) {
      try { interceptor(result) } catch (_) { /* ignore */ }
    }
    return result
  }

  // 成功
  // [FIX 2026-06-12] 即使是 2xx 也要保留 errors / message, 让 batch-delete (207 Multi-Status)
  // 之类"部分失败"响应能在前端 useMetaList.handleBatchDelete 看到具体错误。
  // 之前 bug: 207 走成功分支, result.errors / body.message 都没保留,
  // 前端 result.errors 为 undefined, 走兜底'删除失败'四个字, 用户看不到具体原因。
  const result = {
    success: body.success !== undefined ? body.success : true,
    data: body.data !== undefined ? body.data : body,
    message: body.message || '',
    traceId,
  }
  if (body.errors) {
    result.errors = body.errors
  }
  if (body.error_code) {
    result.error_code = body.error_code
  }

  for (const interceptor of responseInterceptors) {
    try { interceptor(result) } catch (_) { /* ignore */ }
  }

  return result
}

// ---------------------------------------------------------------------------
// 命名空间导出: apiV1 / apiV2
// ---------------------------------------------------------------------------
function createNamespace(baseUrl) {
  return {
    get(path, options) {
      return request('GET', baseUrl, path, options)
    },
    post(path, body, options) {
      return request('POST', baseUrl, path, { ...options, body })
    },
    put(path, body, options) {
      return request('PUT', baseUrl, path, { ...options, body })
    },
    delete(path, options) {
      return request('DELETE', baseUrl, path, options)
    },
    patch(path, body, options) {
      return request('PATCH', baseUrl, path, { ...options, body })
    },
    /**
     * 下载文件 (GET + responseType:'blob')
     * @param {string} path - 请求路径
     * @param {object} [options] - 同 request options
     * @returns {Promise<{success: boolean, data: Blob|null, message: string, traceId: string}>}
     */
    download(path, options) {
      return request('GET', baseUrl, path, { ...options, responseType: 'blob' })
    },
  }
}

export const apiV1 = createNamespace(API_BASE)
export const apiV2 = createNamespace(API_BASE_V2)

// ---------------------------------------------------------------------------
// In-flight 缓存管理 (FR-017)
// ---------------------------------------------------------------------------

/**
 * 清空 in-flight 去重缓存 (用于测试或路由切换时清理)
 */
export function clearInflightCache() {
  inflightCache.clear()
}

/**
 * 获取当前 in-flight 请求数量 (用于监控/调试)
 */
export function getInflightCount() {
  return inflightCache.size
}

// ---------------------------------------------------------------------------
// 文件下载工具
// ---------------------------------------------------------------------------

/**
 * 触发浏览器下载 Blob 文件
 * @param {Blob} blob - 文件 Blob
 * @param {string} filename - 下载文件名
 */
export function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }, 100)
}

export default { apiV1, apiV2 }
