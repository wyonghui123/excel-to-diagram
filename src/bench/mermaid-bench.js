// mermaid scale calibration bench — 合成基准: 节点数 -> mermaid.render() 耗时/内存/DOM
// [TEMP] 校准探针用, 校准完删除. 不进任何业务代码路径.
import mermaid from 'mermaid'
import * as elk from '@mermaid-js/layout-elk'

// 注册 ELK (与应用 useElkLoader 一致)
mermaid.registerLayoutLoaders([...elk.default])
mermaid.initialize({
  startOnLoad: false,
  securityLevel: 'loose',
  maxEdges: 200000,
  flowchart: { useMaxWidth: false, nodeSpacing: 80, rankSpacing: 100 }
})

// 简单种子随机数 (可复现)
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// 生成层级式 flowchart: clusters 个子图, 每个含若干节点, 指定条边 (默认 ~1.2n)
function genCode(n, clusters, rnd, edgeCount) {
  const lines = ['flowchart TB']
  const per = Math.ceil(n / clusters)
  const cname = (c) => `CL${c}`
  for (let c = 0; c < clusters; c++) {
    lines.push(`subgraph ${cname(c)}["${'集群' + (c + 1)}"]`)
    const start = c * per
    const end = Math.min(start + per, n)
    for (let i = start; i < end; i++) {
      lines.push(`  N${i}["业务对象${i}_模块${(i % 7) + 1}"]`)
    }
    lines.push('end')
  }
  // 有向边 (种子随机, 少部分跨集群)
  const edges = edgeCount || Math.round(n * 1.2)
  for (let e = 0; e < edges; e++) {
    const a = Math.floor(rnd() * n)
    const b = Math.floor(rnd() * n)
    if (a !== b) lines.push(`N${a} --> N${b}`)
  }
  return lines.join('\n')
}

const out = document.getElementById('out')
const log = document.getElementById('log')

async function renderOnce(code, engine) {
  out.innerHTML = ''
  const base = { startOnLoad: false, securityLevel: 'loose', maxEdges: 200000,
                 flowchart: { useMaxWidth: false, nodeSpacing: 80, rankSpacing: 100 } }
  let cfg = base
  if (engine === 'elk') {
    cfg = {
      ...base,
      layout: 'elk',
      elk: {
        'elk.direction': 'DOWN',
        'elk.spacing.nodeNode': 100,
        'elk.layered.spacing.nodeNodeBetweenLayers': 150,
        'elk.padding': '[top=60,left=80,right=80,bottom=40]',
        'elk.hierarchyHandling': 'INCLUDE_CHILDREN',
        'elk.algorithm': 'layered',
        'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
        'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
        'elk.contentAlignment': 'CENTER',
        'elk.alignment': 'CENTER',
        'elk.spacing.componentComponent': 250,
        'elk.layered.spacing.componentComponent': 250,
        'elk.layered.cycleBreaking.strategy': 'GREEDY_MODEL_ORDER',
        'elk.layered.layering.strategy': 'NETWORK_SIMPLEX'
      }
    }
  }
  mermaid.initialize(cfg)
  const beforeHeap = performance.memory ? performance.memory.usedJSHeapSize : null
  const t0 = performance.now()
  let svg
  let err = null
  try {
    ;({ svg } = await mermaid.render('bench_' + engine + '_' + Date.now(), code))
  } catch (e) {
    err = String(e && e.message ? e.message : e)
  }
  const renderMs = performance.now() - t0
  const afterHeap = performance.memory ? performance.memory.usedJSHeapSize : null
  if (err) {
    out.innerHTML = ''
    return { error: err.slice(0, 200), renderMs: Math.round(renderMs) }
  }
  out.innerHTML = svg
  const svgEl = out.querySelector('svg')
  const nodeCount = out.querySelectorAll('g.node').length
  const edgeCount = out.querySelectorAll('g.edgePath, g.edge').length
  let dims = null
  if (svgEl) {
    const vb = svgEl.viewBox.baseVal
    dims = { w: Math.round(vb.width), h: Math.round(vb.height) }
  }
  return {
    renderMs: Math.round(renderMs),
    domNodes: nodeCount,
    domEdges: edgeCount,
    dims,
    heapDeltaMB: beforeHeap && afterHeap ? Math.round((afterHeap - beforeHeap) / 1048576) : null
  }
}

async function runBench(n, engine, repeats = 2, edgeCount = null) {
  const rnd = mulberry32(20260818)
  const code = genCode(n, Math.min(8, Math.max(2, Math.round(n / 40))), rnd, edgeCount)
  const edgeCountReal = (code.match(/-->/g) || []).length
  let okList = []
  let lastErr = null
  for (let i = 0; i < repeats; i++) {
    const r = await renderOnce(code, engine)
    if (r.error) {
      lastErr = r.error
    } else {
      okList.push(r)
    }
    await new Promise(res => setTimeout(res, 150))
  }
  if (okList.length === 0) {
    return { nodes: n, engine, edges: edgeCountReal, error: lastErr || 'render failed' }
  }
  let best = okList[0]
  let total = 0
  for (const r of okList) {
    total += r.renderMs
    if (r.renderMs < best.renderMs) best = r
  }
  best.avgMs = Math.round(total / okList.length)
  best.repeatsOk = okList.length
  best.nodes = n
  best.engine = engine
  best.edges = edgeCountReal
  if (lastErr) best.lastErr = lastErr
  return best
}

window.runBench = runBench
log.textContent = 'bench ready (window.runBench(n, engine, repeats))'
