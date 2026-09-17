/**
 * Test: mermaid 11.13.0 转义语法验证 (Node.js, 无需 jsdom)
 * 核心问题: 找到 innerHTML 安全的转义方案
 */
import mermaid from 'mermaid'
import { JSDOM } from 'jsdom'
import createDOMPurify from 'dompurify'

// mermaid 11.x 需要 DOM 环境
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', { runScripts: 'dangerously' })
global.document = dom.window.document
global.window = dom.window
// DOMPurify: mermaid 内部访问 window.DOMPurify 或 global.DOMPurify
const DOMPurifyInstance = createDOMPurify(dom.window)
dom.window.DOMPurify = DOMPurifyInstance
global.DOMPurify = DOMPurifyInstance
try { global.navigator = dom.window.navigator } catch(e) {}

mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' })

let counter = 0

async function testRender(name, code) {
  try {
    const id = `test-${++counter}-${Date.now()}`
    const { svg } = await mermaid.render(id, code)
    console.log(`[PASS] ${name} (svg ${svg.length} chars)`)
    return true
  } catch (err) {
    const msg = (err?.message || String(err)).substring(0, 80).replace(/\n/g, ' ')
    console.log(`[FAIL] ${name}: ${msg}`)
    return false
  }
}

async function main() {
  console.log('=== mermaid 11.13.0 转义语法验证 ===\n')
  
  let p = 0, f = 0
  const check = (r) => { r ? p++ : f++ }
  
  console.log('--- Baseline ---')
  check(await testRender('纯中文', 'flowchart LR\n  A["财务云"]'))
  check(await testRender('#quot;', 'flowchart LR\n  A["test#quot;name"]'))
  check(await testRender('#91; #93;', 'flowchart LR\n  A["test#91;1#93;"]'))
  
  console.log('\n--- #XX; 数字转义 (mermaid 语法) ---')
  check(await testRender('#60; <', 'flowchart LR\n  A["test#60;name"]'))
  check(await testRender('#62; >', 'flowchart LR\n  A["test#62;name"]'))
  check(await testRender('#38; &', 'flowchart LR\n  A["test#38;name"]'))
  
  console.log('\n--- #name; 命名转义 (mermaid 语法) ---')
  check(await testRender('#lt; <', 'flowchart LR\n  A["test#lt;name"]'))
  check(await testRender('#gt; >', 'flowchart LR\n  A["test#gt;name"]'))
  check(await testRender('#amp; &', 'flowchart LR\n  A["test#amp;name"]'))
  
  console.log('\n--- HTML 实体 (mermaid.render 直接传字符串) ---')
  check(await testRender('&lt; <', 'flowchart LR\n  A["test&lt;name"]'))
  check(await testRender('&gt; >', 'flowchart LR\n  A["test&gt;name"]'))
  check(await testRender('&amp; &', 'flowchart LR\n  A["test&amp;name"]'))
  
  console.log('\n--- <br/> 换行 ---')
  check(await testRender('<br/> 换行', 'flowchart LR\n  A["hello<br/>world"]'))
  check(await testRender('\\n 换行', 'flowchart LR\n  A["hello\\nworld"]'))
  
  console.log('\n--- 混合场景 ---')
  check(await testRender('BOSS<系统> #lt;', 'flowchart LR\n  A["BOSS#lt;系统#gt;"]'))
  check(await testRender('A&B #38;', 'flowchart LR\n  A["A#38;B"]'))
  check(await testRender('含"引号 #quot;', 'flowchart LR\n  A["含#quot;引号"]'))
  
  console.log('\n--- subgraph label ---')
  check(await testRender('subgraph #lt;', 'flowchart LR\n  subgraph S1["test#lt;name"]\n    A\n  end'))
  check(await testRender('subgraph #quot;', 'flowchart LR\n  subgraph S1["test#quot;name"]\n    A\n  end'))
  
  console.log('\n--- arrow label ---')
  check(await testRender('-->|"label"| #60;', 'flowchart LR\n  A -->|"test#60;name"| B'))
  check(await testRender('-->|"label"| #quot;', 'flowchart LR\n  A -->|"test#quot;name"| B'))
  check(await testRender('<-- text --> #60;', 'flowchart LR\n  A <-- test#60;name --> B'))
  
  console.log(`\n=== 结果: ${p}/${p + f} PASS, ${f} FAIL ===`)
}

main().catch(console.error)
