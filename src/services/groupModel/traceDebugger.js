/**
 * 分组处理追踪模块
 * 
 * 设计原则：
 * 1. 每个处理环节生成追踪记录
 * 2. 形成完整的调用链
 * 3. 支持从最终结果反推问题
 */

let traceEnabled = false
let currentTraceId = 0
const traces = new Map()

/**
 * 启用/禁用追踪
 */
export function enableTrace(enabled = true) {
  traceEnabled = enabled
  if (enabled) {
    console.log('[Trace] Enabled. Call getTraceReport() to see full trace.')
  }
}

/**
 * 开始一个新的追踪会话
 */
export function startTrace(operation, input) {
  if (!traceEnabled) return null
  
  currentTraceId++
  const traceId = `trace_${currentTraceId}`
  
  traces.set(traceId, {
    id: traceId,
    operation,
    startTime: Date.now(),
    steps: [],
    input: summarizeInput(input)
  })
  
  return traceId
}

/**
 * 记录处理步骤
 */
export function traceStep(traceId, stepName, data) {
  if (!traceEnabled || !traceId) return
  
  const trace = traces.get(traceId)
  if (!trace) return
  
  trace.steps.push({
    step: stepName,
    time: Date.now() - trace.startTime,
    data: summarizeData(data)
  })
}

/**
 * 结束追踪
 */
export function endTrace(traceId, output) {
  if (!traceEnabled || !traceId) return
  
  const trace = traces.get(traceId)
  if (!trace) return
  
  trace.endTime = Date.now()
  trace.duration = trace.endTime - trace.startTime
  trace.output = summarizeOutput(output)
  
  // 打印简要信息
  console.log(`[Trace] ${trace.operation} completed in ${trace.duration}ms with ${trace.steps.length} steps`)
}

/**
 * 获取追踪报告
 */
export function getTraceReport(traceId = null) {
  if (traceId) {
    return traces.get(traceId)
  }
  
  return Array.from(traces.values())
}

/**
 * 清除追踪记录
 */
export function clearTraces() {
  traces.clear()
  currentTraceId = 0
}

/**
 * 从结果反推问题
 * 检查某个元素在各个阶段的状态
 */
export function traceElement(elementId) {
  const report = []
  
  traces.forEach(trace => {
    const found = trace.steps.find(step => {
      if (step.data?.elementId === elementId) return true
      if (step.data?.elements?.includes(elementId)) return true
      if (step.data?.groups?.some(g => g.id === elementId || g.title === elementId)) return true
      return false
    })
    
    if (found) {
      report.push({
        traceId: trace.id,
        operation: trace.operation,
        step: found.step,
        data: found.data
      })
    }
  })
  
  console.log(`[Trace] Element "${elementId}" found in ${report.length} steps:`)
  report.forEach(r => {
    console.log(`  - ${r.operation}/${r.step}: ${JSON.stringify(r.data)}`)
  })
  
  return report
}

/**
 * 数据摘要（避免打印过多信息）
 */
function summarizeInput(input) {
  if (!input) return null
  if (Array.isArray(input)) {
    return `${input.length} items: ${input.slice(0, 3).map(i => i?.title || i?.id || i).join(', ')}...`
  }
  return typeof input === 'object' ? Object.keys(input) : input
}

function summarizeData(data) {
  if (!data) return null
  if (Array.isArray(data)) {
    return data.slice(0, 5).map(d => d?.title || d?.id || d)
  }
  if (typeof data === 'object') {
    const keys = Object.keys(data)
    if (keys.length > 5) {
      return { ...Object.fromEntries(keys.slice(0, 5).map(k => [k, data[k]])), _truncated: true }
    }
    return data
  }
  return data
}

function summarizeOutput(output) {
  return summarizeInput(output)
}

/**
 * 装饰器：自动追踪函数调用
 */
export function withTrace(operation, fn) {
  return function(...args) {
    const traceId = startTrace(operation, args[0])
    
    try {
      traceStep(traceId, 'input', args[0])
      const result = fn.apply(this, args)
      traceStep(traceId, 'output', result)
      endTrace(traceId, result)
      return result
    } catch (error) {
      traceStep(traceId, 'error', error.message)
      endTrace(traceId, null)
      throw error
    }
  }
}
