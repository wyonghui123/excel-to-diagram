// FR-002 + FR-013 快速验证
// 验证: 1) logger 模块行为  2) crypto.randomUUID 唯一性 + 格式
// 注: traceId 实际行为通过 httpClient 的 generateTraceId 内部使用 crypto.randomUUID
//     (httpClient 在 Node 中需要 vite alias 解析,所以此处不直接导入)

// Mock window for Node (logger 内部用 typeof window 防御)
globalThis.window = globalThis.window || {}

// 抑制 logger 自身的 stderr 输出,避免 PowerShell 把 stderr 误判为错误
const origWarn = console.warn
const origError = console.error
console.warn = () => {}
console.error = () => {}

const { logger, createLogger } = await import('../logger.js')

// 恢复 console 用于 assert 输出
console.warn = origWarn
console.error = origError

let passed = 0
let failed = 0

function assert(cond, msg) {
  if (cond) {
    console.log('  [PASS]', msg)
    passed++
  } else {
    console.log('  [FAIL]', msg)
    failed++
  }
}

console.log('=== FR-002 logger 模块验证 ===')

// 1. 模块导出
assert(typeof logger === 'object', 'logger 是对象')
assert(typeof logger.debug === 'function', 'logger.debug 存在')
assert(typeof logger.info === 'function', 'logger.info 存在')
assert(typeof logger.warn === 'function', 'logger.warn 存在')
assert(typeof logger.error === 'function', 'logger.error 存在')
assert(typeof logger.setTraceId === 'function', 'logger.setTraceId 存在')
assert(typeof logger.clearTraceId === 'function', 'logger.clearTraceId 存在')
  assert(typeof createLogger === 'function', 'createLogger 工厂函数存在 (兼容 v3 API)')

// 2. setTraceId / clearTraceId
logger.setTraceId('test-trace-123')
assert(window.__currentTraceId === 'test-trace-123', 'setTraceId 后 window.__currentTraceId 被设置')
logger.clearTraceId()
assert(window.__currentTraceId === undefined, 'clearTraceId 后 window.__currentTraceId 被清除')

// 3. 各方法可调用（不应抛错）
try {
  logger.debug('test debug message', { foo: 'bar' })
  logger.info('test info message')
  logger.warn('test warn message')
  logger.error('test error message', new Error('simulated'))
  assert(true, 'logger 各方法调用无异常')
} catch (e) {
  assert(false, 'logger 调用异常: ' + e.message)
}

console.log('')
console.log('=== FR-013 traceId 升级验证 ===')

// 4. crypto.randomUUID() 可用性
if (globalThis.crypto?.randomUUID) {
  const id = globalThis.crypto.randomUUID()
  // UUID v4 格式: 8-4-4-4-12 含连字符
  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
  assert(uuidRe.test(id), `crypto.randomUUID() 返回标准 UUID v4: ${id}`)

  // 1000 次唯一性
  const ids = new Set()
  for (let i = 0; i < 1000; i++) {
    ids.add(globalThis.crypto.randomUUID())
  }
  assert(ids.size === 1000, '1000 次生成的 traceId 全部唯一')

  // 长度验证 (36 字符 = 32 hex + 4 连字符)
  assert(id.length === 36, `UUID 长度应为 36, 实际 ${id.length}`)

  // 连续两次不同
  const id2 = globalThis.crypto.randomUUID()
  assert(id !== id2, '连续两次生成的 traceId 不同')
} else {
  assert(false, 'globalThis.crypto.randomUUID 不可用 (旧 Node/浏览器)')
}

console.log('')
console.log(`=== Result: ${passed} passed, ${failed} failed ===`)
process.exit(failed > 0 ? 1 : 0)
