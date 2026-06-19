/**
 * useMessageTrace - trace_id 提取与格式化
 *
 * 解决问题：业务错误需要给用户一个"可追踪"的标识，方便联系运维
 * 业界标准：RFC 7807 Problem Details + X-Trace-Id 响应头
 *
 * 性能优化：WeakMap 缓存避免重复提取（批量场景）
 *
 * @see docs/specs/spec-message-unification-2026-06-18-v1.1.md
 */

const _traceIdCache = new WeakMap()

/**
 * 从 error 对象中提取 trace_id
 * 支持 RFC 7807 响应头 X-Trace-Id 或 error.trace_id 字段
 */
export function extractTraceId(error) {
  if (!error || typeof error !== 'object') return null
  if (_traceIdCache.has(error)) return _traceIdCache.get(error)

  let traceId = null
  try {
    const headers = error?.response?.headers
    if (headers) {
      traceId = headers['x-trace-id'] || headers['X-Trace-Id']
    }
    if (!traceId && typeof headers?.get === 'function') {
      traceId = headers.get('x-trace-id')
    }
    if (!traceId) traceId = error.trace_id || error.traceId
    if (!traceId) traceId = error.data?.trace_id
  } catch (e) {
    traceId = null
  }

  _traceIdCache.set(error, traceId)
  return traceId
}

/**
 * 格式化错误消息，自动附加 trace_id
 * @param {string} message 原始消息
 * @param {Error|object} error 可选错误对象
 * @param {boolean} [forceTraceId=true] 是否强制附加
 */
export function formatErrorMessage(message, error, forceTraceId = true) {
  if (!error) return message
  const traceId = extractTraceId(error)
  if (traceId && forceTraceId) {
    return `${message}（错误编号: ${traceId}）`
  }
  return message
}
