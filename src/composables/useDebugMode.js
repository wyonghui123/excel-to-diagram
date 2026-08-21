import { ref, computed } from 'vue'

/**
 * useDebugMode - 调试模式门控 + 交互记录器
 *
 * 用法:
 *   ?mode=debug          → 开启调试模式（面板/日志/API）
 *   ?mode=debug&preset=scp → 调试模式 + 快捷启动
 *   无参数时              → 零污染（无面板/无日志/无全局 API）
 *
 * P0: mode 门控 — 所有调试代码通过 isDebug 条件执行
 * P1: 交互记录器 — 记录/回放/逐步执行用户操作
 */
export function useDebugMode() {
  const params = new URLSearchParams(window.location.search)
  const isDebug = params.get('mode') === 'debug'

  // ---- P0: 调试面板可见性 ----
  const debugPanelVisible = ref(false)

  // ---- P0: 条件日志 ----
  // [OBS 2026-08-09] 缓冲最近日志, 供 evaluate / probe 通过 __archPage.debug.getLogs() 取回,
  //   避免只能看浏览器 console (排查需读临时 log 文件). 仅 debug 模式缓存, 生产零污染.
  const logBuffer = ref([])
  const LOG_BUFFER_MAX = 300
  function serializeArgs(args) {
    return args.map(a => {
      if (a === undefined) return 'undefined'
      if (a === null) return 'null'
      if (typeof a === 'string') return a
      if (typeof a === 'object') {
        try { return JSON.stringify(a) } catch (e) { return String(a) }
      }
      return String(a)
    }).join(' ')
  }
  function pushLog(level, args) {
    if (!isDebug) return
    logBuffer.value.push({ level, time: Date.now(), text: serializeArgs(args) })
    if (logBuffer.value.length > LOG_BUFFER_MAX) {
      logBuffer.value.splice(0, logBuffer.value.length - LOG_BUFFER_MAX)
    }
  }
  const debugLog = (...args) => { if (isDebug) { console.log(...args); pushLog('log', args) } }
  const debugWarn = (...args) => { if (isDebug) { console.warn(...args); pushLog('warn', args) } }
  const debugError = (...args) => { if (isDebug) { console.error(...args); pushLog('error', args) } }

  // 取回最近日志 (倒序), limit 控制条数; 生产模式返回空数组
  function getLogs(limit = 80) {
    if (!isDebug) return []
    return logBuffer.value.slice(-limit).reverse()
  }

  // ---- P1: 交互记录器 ----
  const interactionHistory = ref([])
  const currentStepIndex = ref(-1)
  const isRecording = ref(false)

  /**
   * 记录一次交互
   * @param {string} type  - 交互类型: 'dblclick' | 'contextmenu' | 'menu-click' | 'nav' | 'custom'
   * @param {object} data  - 交互数据: { target, group, key, result, ... }
   */
  function recordInteraction(type, data = {}) {
    if (!isDebug) return
    const entry = {
      type,
      data: JSON.parse(JSON.stringify(data)),
      time: Date.now(),
      index: interactionHistory.value.length
    }
    interactionHistory.value.push(entry)
    currentStepIndex.value = interactionHistory.value.length - 1
    debugLog(`[REC] ${type}`, data)
    return entry
  }

  /**
   * 回放所有已记录的交互（逐个执行，间隔 delay ms）
   */
  async function replay(delay = 500) {
    if (!isDebug || interactionHistory.value.length === 0) return
    debugLog(`[REPLAY] 开始回放 ${interactionHistory.value.length} 步`)
    for (let i = 0; i < interactionHistory.value.length; i++) {
      currentStepIndex.value = i
      const step = interactionHistory.value[i]
      debugLog(`[REPLAY] 步骤 ${i}: ${step.type}`, step.data)
      // 触发自定义事件供外部监听执行
      window.dispatchEvent(new CustomEvent('debug:replay-step', {
        detail: { step, index: i }
      }))
      await new Promise(r => setTimeout(r, delay))
    }
    debugLog('[REPLAY] 完成')
  }

  /**
   * 前进到下一步
   */
  function stepForward() {
    if (!isDebug) return
    const next = Math.min(currentStepIndex.value + 1, interactionHistory.value.length - 1)
    if (next === currentStepIndex.value) return
    currentStepIndex.value = next
    const step = interactionHistory.value[next]
    debugLog(`[STEP] 前进到 ${next}: ${step.type}`, step.data)
    window.dispatchEvent(new CustomEvent('debug:replay-step', {
      detail: { step, index: next }
    }))
    return step
  }

  /**
   * 后退到上一步
   */
  function stepBackward() {
    if (!isDebug) return
    const prev = Math.max(currentStepIndex.value - 1, -1)
    currentStepIndex.value = prev
    debugLog(`[STEP] 后退到 ${prev}`)
    window.dispatchEvent(new CustomEvent('debug:replay-step', {
      detail: { step: null, index: prev }
    }))
    return prev
  }

  /**
   * 清空交互历史
   */
  function clearHistory() {
    interactionHistory.value = []
    currentStepIndex.value = -1
  }

  /**
   * 注册调试 API 到 window.__archPage（仅调试模式）
   */
  function registerDebugAPI(api) {
    if (!isDebug) return
    window.__archPage = window.__archPage || {}
    Object.assign(window.__archPage, api)
  }

  /**
   * 获取调试模式返回的模板块（供模板 v-if 使用）
   */
  const debugPanelState = computed(() => ({
    visible: debugPanelVisible.value,
    isDebug,
    historyCount: interactionHistory.value.length,
    currentStep: currentStepIndex.value
  }))

  return {
    // P0: mode 门控
    isDebug,
    debugPanelVisible,
    debugLog,
    debugWarn,
    debugError,
    registerDebugAPI,
    debugPanelState,
    getLogs,
    logBuffer,

    // P1: 交互记录器
    interactionHistory,
    currentStepIndex,
    isRecording,
    recordInteraction,
    replay,
    stepForward,
    stepBackward,
    clearHistory
  }
}