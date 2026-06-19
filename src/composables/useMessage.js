import { ref, readonly } from 'vue'
import { extractTraceId, formatErrorMessage } from './useMessageTrace'

const messages = ref([])
let messageId = 0

function showMessage(m, type = 'success', duration = 3000) {
  const id = ++messageId
  messages.value = [...messages.value, { id, message: m, type, duration }]
  if (duration > 0) setTimeout(() => removeMessage(id), duration)
  return id
}

function removeMessage(id) {
  const i = messages.value.findIndex(x => x.id === id)
  if (i > -1) messages.value = messages.value.filter(x => x.id !== id)
}

function clearAll() { messages.value = [] }
function success(m, d) { return showMessage(m, 'success', d) }
function warning(m, d) { return showMessage(m, 'warning', d) }
function info(m, d) { return showMessage(m, 'info', d) }

function error(message, errorOrDuration, maybeDuration) {
  let errorObj = null, duration = 3000
  if (errorOrDuration instanceof Error || (errorOrDuration && typeof errorOrDuration === 'object' && !Number.isFinite(errorOrDuration))) {
    errorObj = errorOrDuration
    duration = maybeDuration ?? 3000
  } else if (Number.isFinite(errorOrDuration)) {
    duration = errorOrDuration
  }
  return showMessage(formatErrorMessage(message, errorObj), 'error', duration)
}

function detail(title, subtitle, type = 'info', duration = 4500) {
  try {
    if (window?.$notification?.primary) {
      const t = type === 'success' || type === 'error' || type === 'warning' ? type : 'info'
      return window.$notification[t]({ title, message: subtitle, duration })
    }
  } catch (e) { /* STAB-2 优雅降级 */ }
  return showMessage(subtitle ? `${title}\n${subtitle}` : title, type, duration)
}

async function confirm({ title = '确认', content = '' } = {}) {
  return new Promise(resolve => {
    try { resolve(window.confirm(content || title)) } catch (e) { resolve(false) }
  })
}

export function useMessage() {
  return {
    messages: readonly(messages),
    show: showMessage, success, error, warning, info, detail, confirm,
    remove: removeMessage, clearAll,
    extractTraceId, formatErrorMessage,
    // 业务消息 API (P2 业务术语优化)
    saved: (e = '数据') => success(`${e}已保存`),
    created: (e = '数据') => success(`${e}已创建`),
    deleted: (e = '数据') => success(`${e}已删除`),
    stateChanged: (action, e = '数据') => success(`${e}已${action}`),
    // 系统级 (P1)
    networkError: () => error('网络连接失败，请检查网络后重试'),
    sessionExpired: () => error('会话已过期，请重新登录'),
  }
}
