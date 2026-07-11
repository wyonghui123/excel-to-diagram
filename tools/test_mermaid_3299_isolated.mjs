// [V760-fix] mermaid 11.13.0 隔离测试 — 用 jsdom 提供真实 DOM
// DOMPurify 需要 window/document, jsdom 提供完整环境
import { JSDOM } from 'jsdom'
import mermaid from 'mermaid'
import { writeFileSync } from 'fs'

const out = []
const log = (s) => { out.push(s); console.log(s) }

process.on('uncaughtException', (err) => {
  log(`[uncaughtException] name=${err.name}`)
  log(`[uncaughtException] msg=${err.message?.slice(0, 500)}`)
  log(`[uncaughtException] stack (40 lines):`)
  log((err.stack || '').split('\n').slice(0, 40).join('\n'))
  writeFileSync('tools/test_mermaid_3299_isolated.result.json', JSON.stringify(out, null, 2))
  process.exit(2)
})

// 创建 jsdom 环境
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
  url: 'http://localhost:3006/',
  pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
// navigator is read-only on newer Node, skip it
// DOMPurify 会从 window 上取
if (!dom.window.DOMPurify) {
  // jsdom 没有 DOMPurify, 注入 mock
  dom.window.DOMPurify = {
    sanitize: (str) => str,
    isValidAttribute: () => true,
    addHook: () => {},
    removeAllHooks: () => {},
  }
}

mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'loose',
  flowchart: { htmlLabels: true, maxEdges: 10000, defaultRenderer: 'elk' },
  maxTextSize: 99999999,
  maxEdges: 10000,
})

// 构造用户实际场景
const N = 1610
const E = 3299
const lines = ['flowchart LR', '  subgraph 财务云']
for (let i = 0; i < N; i++) {
  const name = `业务对象${i}_财务_报表_项目${i}_子项${i % 50}_类型${i % 20}`
  const code = `BO${String(i).padStart(5, '0')}`
  lines.push(`    n${i}["${name}<br/>${code}"]`)
}
lines.push('  end')
for (let i = 0; i < E; i++) {
  const src = i % N
  const dst = (i * 7 + 3) % N
  if (src === dst) continue
  const relType = ['调用','引用','依赖','关联','组合','聚合','继承','实现','触发','消费','生产','归属'][i % 12]
  const annContent = `备注_${i}: 业务规则_${i % 100}_执行条件_${i % 50}`
  lines.push(`  n${src} -->|"${relType}<br/>${annContent}"| n${dst}`)
}
const code = lines.join('\n')

log(`code length = ${code.length} bytes`)
log(`nodes = ${N}, edges = ${E}`)

// 1) parse
log('\n--- parse() ---')
try {
  const t0 = Date.now()
  const r = await mermaid.parse(code, { suppressErrors: false })
  log(`OK in ${Date.now() - t0}ms, hasDiagram=${!!r}`)
} catch (err) {
  log(`FAIL: name=${err.name}`)
  log(`msg=${err.message?.slice(0, 500)}`)
  log(`hash: ${JSON.stringify(err.hash || {}).slice(0, 500)}`)
  log(`stack (40 lines):`)
  log((err.stack || '').split('\n').slice(0, 40).join('\n'))
  writeFileSync('tools/test_mermaid_3299_isolated.result.json', JSON.stringify(out, null, 2))
  process.exit(1)
}

writeFileSync('tools/test_mermaid_3299_isolated.result.json', JSON.stringify(out, null, 2))
log('\n[done] parse succeeded, result written')
