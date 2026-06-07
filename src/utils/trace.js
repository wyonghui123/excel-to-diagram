/**
 * 结构化 trace 日志工具
 *
 * 用于 OSS/RSS 事件链路调试，输出格式统一的控制台日志。
 * DEV 模式下通过 console.debug 输出，生产环境构建时可被 tree-shake。
 *
 * 用法：
 *   import { createTrace } from '@/utils/trace'
 *   const trace = createTrace('ObjectScopeSection')
 *   trace.log('handleBoCheck', { boIds: [...] })
 *   // → [ObjectScopeSection] handleBoCheck { boIds: [...] }
 */

let _seq = 0

const ENABLED = import.meta.env.DEV

/**
 * 创建组件级别的 trace 日志器
 * @param {string} componentName - 组件名，用于日志前缀
 * @returns {{ log, warn, error }}
 */
export function createTrace(componentName) {
  const prefix = `[${componentName}]`

  return {
    /**
     * 调试日志（DEV only）
     * @param {string} eventName - 事件名
     * @param {object} [payload] - 附加数据
     */
    log(eventName, payload) {
      if (!ENABLED) return
      const seq = (_seq++).toString(36)
      console.debug(
        `%c${prefix}%c ${eventName} %c#${seq}`,
        'color:#4fc3f7;font-weight:bold',
        'color:#e0e0e0',
        'color:#666',
        payload ?? ''
      )
    },

    /**
     * 警告日志（始终输出）
     * @param {string} eventName
     * @param {object} [payload]
     */
    warn(eventName, payload) {
      console.warn(`${prefix} ${eventName}`, payload ?? '')
    },

    /**
     * 错误日志（始终输出）
     * @param {string} eventName
     * @param {object} [payload]
     */
    error(eventName, payload) {
      console.error(`${prefix} ${eventName}`, payload ?? '')
    }
  }
}
