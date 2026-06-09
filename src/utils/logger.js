/**
 * logger - 统一日志工具
 *
 * 设计目标 (FR-002):
 * - 统一日志格式: 级别 + 标签 + 消息
 * - 开发环境 (DEV): 所有级别输出到 console
 * - 生产环境 (PROD): 仅 error/warn 输出到 console + sendBeacon 上报
 * - 支持 traceId 关联（httpClient 设置 window.__currentTraceId）
 * - 零依赖
 *
 * 替代散落的 console.* 调用,便于:
 * - 生产构建剥离（FR-001）
 * - 统一错误上报（M4 FR-003）
 * - 日志分级
 */

const isDev = import.meta.env?.DEV ?? false
const isProd = import.meta.env?.PROD ?? false

/**
 * 异步上报到后端 (fire-and-forget, 不阻塞调用方)
 * @param {'debug'|'info'|'warn'|'error'} level
 * @param {string} message
 * @param {object} [extra]
 */
function sendTelemetry(level, message, extra) {
  if (!isProd) return
  if (typeof navigator === 'undefined' || !navigator.sendBeacon) return

  try {
    const payload = JSON.stringify({
      level,
      message,
      extra: extra || null,
      traceId: (typeof window !== 'undefined' && window.__currentTraceId) || null,
      url: typeof location !== 'undefined' ? location.href : null,
      userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : null,
      ts: Date.now(),
    })
    // sendBeacon 上限 64KB
    if (payload.length < 65536) {
      navigator.sendBeacon('/api/v1/telemetry/error', payload)
    }
  } catch (_) {
    // 上报失败静默,不传播到调用方
  }
}

function format(level, args) {
  return [`[${level.toUpperCase()}]`, ...args]
}

export const logger = {
  /**
   * DEBUG: 仅开发环境输出,生产环境完全剥离
   */
  debug: (...args) => {
    if (isDev) {
      // eslint-disable-next-line no-console
      console.debug(...format('DEBUG', args))
    }
  },

  /**
   * INFO: 仅开发环境输出
   */
  info: (...args) => {
    if (isDev) {
      // eslint-disable-next-line no-console
      console.info(...format('INFO', args))
    }
  },

  /**
   * WARN: 所有环境输出,但不上报
   */
  warn: (...args) => {
    // eslint-disable-next-line no-console
    console.warn(...format('WARN', args))
  },

  /**
   * ERROR: 所有环境输出 + 生产环境上报
   * @param {...any} args - 第一个参数可作为消息,其余作为 extra
   */
  error: (...args) => {
    // eslint-disable-next-line no-console
    console.error(...format('ERROR', args))

    // 提取 message + extra
    const message = args
      .map(a => {
        if (a instanceof Error) return a.message
        if (typeof a === 'string') return a
        try {
          return JSON.stringify(a)
        } catch (_) {
          return String(a)
        }
      })
      .join(' ')

    const firstError = args.find(a => a instanceof Error)
    const extra = firstError
      ? { stack: firstError.stack, name: firstError.name }
      : null

    sendTelemetry('error', message, extra)
  },

  /**
   * 内部使用: 设置当前请求的 traceId (httpClient 调用)
   * 用于在错误上报时关联
   */
  setTraceId(traceId) {
    if (typeof window !== 'undefined') {
      window.__currentTraceId = traceId
    }
  },

  /**
   * 内部使用: 清除当前 traceId
   */
  clearTraceId() {
    if (typeof window !== 'undefined') {
      delete window.__currentTraceId
    }
  },
}

/**
 * 创建带命名空间的 logger
 * 兼容 v3 之前的 createLogger(namespace) API
 *
 * @param {string} namespace - 命名空间, e.g. 'metaService', 'httpClient'
 * @returns {Object} 包含 debug/info/warn/error 方法的 logger
 */
export function createLogger(namespace) {
  const prefix = namespace ? `[${namespace}]` : ''
  return {
    debug: (...args) => logger.debug(prefix, ...args),
    info: (...args) => logger.info(prefix, ...args),
    warn: (...args) => logger.warn(prefix, ...args),
    error: (...args) => logger.error(prefix, ...args),
  }
}

export default logger
