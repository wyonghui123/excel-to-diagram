/**
 * useDiagnostics — 模块级可观测性基础设施
 * =================================================================
 *
 * [目的] 解决排查图表 bug 时, 反复需要:
 *   1. 在代码里加 console.log → 提交 → 让 AI 重新触发 → 看 console
 *   2. 不知道渲染耗时多少 (性能问题无处下手)
 *   3. 不知道上一次渲染用的 mermaid code / 报错 (复现困难)
 *   4. 不知道状态如何从 render() 流到 onRenderComplete (回调链黑箱)
 *
 * [设计] 单一全局 store + 模块调用点埋点, E2E / 自动化测试通过
 *   `window.__archPage.mermaid` 一键读取:
 *     {
 *       lastRender: {
 *         startTime: 1722548400000,
 *         endTime:   1722548400500,
 *         durationMs: 500,
 *         mermaidCode: 'flowchart LR\n  A --> B',
 *         layoutEngine: 'elk',
 *         nodeCount: 41,
 *         edgeCount: 38,
 *         containerCount: 28,
 *         error: null,
 *       },
 *       errors: [...],  // 最近 N 个错误, 含 stack
 *       warnings: [...],
 *       hooks: { onRenderStart, onRenderEnd, onError }  // 业务可挂回调
 *     }
 *
 * [调用点埋点] 用 performance.now() 高精度计时, 各步骤单独计时:
 *   - mermaid.run() 入口 / 出口
 *   - useSvgProcessor.processSvg() 入口 / 出口
 *   - useInteraction.bindAnnotationInteraction()
 *
 * [与 chart_diag.py 集成] Python 端通过 evaluate('window.__archPage.mermaid.lastRender')
 * 一行拿到渲染结果, 不需要解析 console.
 *
 * [性能开销] < 0.1ms / render, 仅 ref/object 赋值.
 */

import { ref, reactive } from 'vue'

// 错误/警告 ring buffer 大小 (避免无限增长)
const BUFFER_SIZE = 50

const createDiagnostics = () => {
  /**
   * lastRender: 最近一次完整渲染的元数据
   * - null 表示从未渲染
   * - { durationMs: 500, error: '...' } 渲染报错也记录
   */
  const lastRender = ref(null)

  /**
   * 步骤级 timing 字典 (key = 步骤名, value = 累计 ms)
   * 例如 { syntax_gen: 12, mermaid_run: 480, svg_process: 8 }
   */
  const stepTimings = reactive({})

  /**
   * 步骤级 metadata 字典 (key = 步骤名, value = 任意 JSON)
   * 用于 "渲染时不知道要不要打印的统计信息" (e.g. addLinkCodeAttributes 标了多少 edgeLabel)
   * 不像 errors/warnings 有 ring buffer, 每次 beginRender 会清空.
   */
  const stepMeta = reactive({})

  /**
   * 当前正在进行的渲染 (如果有), 用于排查 "卡住不渲染" 类问题
   * { startedAt: 1722548400000, step: 'mermaid_run' }
   */
  const currentRender = ref(null)

  /**
   * 错误/警告 ring buffer
   */
  const errors = []
  const warnings = []

  /**
   * 业务可挂的回调 (e.g. chart_diag 用它来 track 渲染时间)
   */
  const hooks = {
    onRenderStart: null,
    onRenderEnd: null,
    onError: null
  }

  /**
   * 重置 stepTimings, 用于新一轮渲染
   */
  const resetStep = (name) => {
    stepTimings[name] = 0
  }
  /**
   * 累计某步骤耗时
   */
  const addStep = (name, ms) => {
    stepTimings[name] = (stepTimings[name] || 0) + ms
  }
  /**
   * 计时 + 累计 + 返回耗时 (典型用法: const t = time('mermaid_run'); ... await ...; endStep('mermaid_run', t))
   */
  const time = (name) => {
    const start = performance.now()
    return start
  }
  const endStep = (name, start) => {
    const ms = performance.now() - start
    stepTimings[name] = (stepTimings[name] || 0) + ms
    return ms
  }

  /**
   * 记录一次完整渲染的开始 (chart_diag 可通过 hook 知道)
   */
  const beginRender = (meta = {}) => {
    currentRender.value = {
      startedAt: performance.now(),
      meta,
      step: 'begin'
    }
    // 重置步骤计时 + 步骤元数据 (新一次渲染)
    Object.keys(stepTimings).forEach(k => delete stepTimings[k])
    Object.keys(stepMeta).forEach(k => delete stepMeta[k])
    if (hooks.onRenderStart) {
      try { hooks.onRenderStart(currentRender.value) } catch (e) { /* swallow */ }
    }
  }

  /**
   * 记录一次完整渲染的结束
   * @param {Object} info - { mermaidCode, layoutEngine, nodeCount, edgeCount, containerCount, error }
   */
  const endRender = (info = {}) => {
    const start = currentRender.value?.startedAt
    const durationMs = start ? Math.round(performance.now() - start) : null
    lastRender.value = {
      startTime: start ? Date.now() - durationMs : Date.now(),
      endTime: Date.now(),
      durationMs,
      stepTimings: { ...stepTimings },
      ...info
    }
    currentRender.value = null
    if (hooks.onRenderEnd) {
      try { hooks.onRenderEnd(lastRender.value) } catch (e) { /* swallow */ }
    }
  }

  /**
   * 记录错误 (附带 stack)
   */
  const recordError = (err, context = '') => {
    const entry = {
      time: Date.now(),
      context,
      message: err?.message || String(err),
      stack: err?.stack || null
    }
    errors.unshift(entry)
    if (errors.length > BUFFER_SIZE) errors.pop()
    if (hooks.onError) {
      try { hooks.onError(entry) } catch (e) { /* swallow */ }
    }
  }

  const recordWarning = (msg, context = '') => {
    warnings.unshift({ time: Date.now(), context, message: msg })
    if (warnings.length > BUFFER_SIZE) warnings.pop()
  }

  /**
   * 记录某步骤的元数据 (覆盖式 — 同一 key 后写覆盖前写)
   * 使用场景: 排查时想知道 "addLinkCodeAttributes 标了多少 edgeLabel",
   * 但又不想在 console 一直打印. 让 chart_diag.dump() 一键读取.
   * @param {string} key - 步骤名 (e.g. 'addLinkCodeAttributes')
   * @param {any} meta - 任意 JSON 数据
   */
  const recordStepMeta = (key, meta) => {
    // 多次记录合并到数组, 而不是覆盖 (addLinkCodeAttributes 调用了 3 次, 每次数据不同)
    if (stepMeta[key] === undefined) {
      stepMeta[key] = []
    } else if (!Array.isArray(stepMeta[key])) {
      stepMeta[key] = [stepMeta[key]]
    }
    stepMeta[key].push(meta)
  }

  /**
   * 一键导出 (用于 dump_state / chart_diag)
   */
  const dump = () => ({
    lastRender: lastRender.value,
    currentRender: currentRender.value,
    stepTimings: { ...stepTimings },
    stepMeta: JSON.parse(JSON.stringify(stepMeta)),
    errors: errors.slice(),
    warnings: warnings.slice()
  })

  return {
    // state
    lastRender,
    currentRender,
    stepTimings,
    stepMeta,
    errors,
    warnings,
    hooks,
    // actions
    resetStep,
    addStep,
    time,
    endStep,
    beginRender,
    endRender,
    recordError,
    recordWarning,
    recordStepMeta,
    dump
  }
}

// 单例: 整个 mermaid 模块共用一个 diagnostics store
// 避免每个 composable 实例化一份 (会浪费内存且不同步)
let _instance = null
export const useDiagnostics = () => {
  if (!_instance) _instance = createDiagnostics()
  return _instance
}

/**
 * 安装到 window.__archPage.mermaid — chart_diag / E2E 测试读取入口
 * 在 MermaidComponent onMounted 调用一次.
 */
export const installDiagnosticsToWindow = () => {
  if (typeof window === 'undefined') return
  const diag = useDiagnostics()
  window.__archPage = window.__archPage || {}
  window.__archPage.mermaid = {
    get lastRender() { return diag.lastRender.value },
    get currentRender() { return diag.currentRender.value },
    get stepTimings() { return { ...diag.stepTimings } },
    get stepMeta() { return JSON.parse(JSON.stringify(diag.stepMeta)) },
    get errors() { return diag.errors.slice() },
    get warnings() { return diag.warnings.slice() },
    hooks: diag.hooks,
    dump: diag.dump
  }
}