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

  // [P0-B 2026-08-03] useTooltip highlight 状态暴露
  //   之前 useTooltip 的 selectedElements 是闭包私有, 外部 (chart_e2e / 调试) 无法观测.
  //   annotationOverlay 走 DOM class (.annotation-highlighted) 可 querySelectorAll, 但 useTooltip
  //   走 inline style 不留 class → 双高亮系统状态不对齐, 排查困难.
  //   现在 useTooltip 在每次 highlight/clear 时调 setHighlightState, 这里持有最新快照,
  //   window.__archPage.mermaid.highlight 一键读取, 与 annotationOverlay 的 DOM 查询互补.
  let _highlightState = { hasHighlight: false, path: null, label: null, sourceNode: null, targetNode: null }
  const setHighlightState = (state) => {
    _highlightState = state
      ? { ...state }
      : { hasHighlight: false, path: null, label: null, sourceNode: null, targetNode: null }
  }
  const getHighlightState = () => ({ ..._highlightState })

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

  /**
   * 统一读取面 — 一次调用返回图表当前渲染的结构化快照
   * [E2E v2 2026-08-02] 断言从"多次 DOM 探测"收敛为"快照比对":
   *   render       渲染元数据 (nodeCount/edgeCount/containerCount/durationMs/error/layoutEngine)
   *   nodes        节点 code + 标签 + fill + 高亮态 (A/B/D 断言数据源)
   *   links        SVG 连线 stroke + stepMeta.linkColorMappings (B 断言数据源)
   *   containers   集群层级: totalClusters/nestedClusters/maxDepth/leafClusters (A 嵌套断言)
   *   legend       图例名称 + 色块颜色 (B 图例完整性断言)
   *   annotations  备注面板 items (C 备注断言数据源)
   * Python 端 chart_diag.get_snapshot() 一行读取, 不再逐个 evaluate.
   */
  const snapshot = () => {
    const doc = typeof document === 'undefined' ? null : document
    const nodeEls = doc ? Array.from(doc.querySelectorAll('svg g.node[data-code]')) : []
    const nodes = nodeEls.map(n => {
      const rect = n.querySelector('rect')
      return {
        code: n.getAttribute('data-code'),
        label: (n.textContent || '').trim(),
        fill: rect ? (rect.getAttribute('fill') || rect.style.fill || '') : '',
        highlighted: n.classList.contains('annotation-highlighted')
      }
    })
    const clusterEls = doc ? Array.from(doc.querySelectorAll('svg g.cluster')) : []
    // [FIX 2026-08-02] mermaid 11 ELK 渲染嵌套 subgraph 时 DOM 是平铺的
    //   (g.cluster 之间无 DOM 包含关系, 节点也全部挂在顶层 g.nodes),
    //   嵌套通过 rect bbox 包含体现: 内层 cluster 画在外层 cluster 的 rect 内.
    //   因此 nestedClusters/maxDepth/leafClusters 必须基于 bbox 包含计算, 而非 DOM contains.
    //   [FIX v2] 坐标必须用 getBoundingClientRect() 屏幕坐标:
    //     getBBox() 返回元素本地坐标系 (不含祖先 transform), 而节点在 g.nodes 下带 translate,
    //     cluster 与 node 的 getBBox 坐标系不可比 → 节点归属判断失效.
    const rectOf = (el) => {
      const r = el && el.querySelector('rect')
      if (!r) return null
      const b = r.getBoundingClientRect()
      return { x: b.left, y: b.top, w: b.width, h: b.height }
    }
    const clusterRects = clusterEls
      .map(c => ({ el: c, id: c.getAttribute('id') || '', ...rectOf(c) }))
      .filter(r => r.w > 0)
    const bboxContains = (a, b) => {
      if (a === b) return false
      if (a.w * a.h <= b.w * b.h) return false // 面积严格更大才可能是父 (防环)
      const bx = b.x + b.w / 2
      const by = b.y + b.h / 2
      return bx >= a.x && bx <= a.x + a.w && by >= a.y && by <= a.y + a.h
    }
    const depthOf = (r) => {
      const parent = clusterRects.find(o => bboxContains(o, r))
      return parent ? depthOf(parent) + 1 : 1
    }
    const nodePos = nodeEls.map(n => {
      const r = n.querySelector('rect')
      const b = r ? r.getBoundingClientRect() : null
      return { code: n.getAttribute('data-code'), x: b ? b.left + b.width / 2 : 0, y: b ? b.top + b.height / 2 : 0 }
    })
    const nodeInCluster = (rect, p) =>
      p.x >= rect.x && p.x <= rect.x + rect.w && p.y >= rect.y && p.y <= rect.y + rect.h
    // 叶子 cluster = 没有 bbox 子 cluster (不包含任何更小的 cluster); nodeCodes = bbox 内节点
    const leafClusters = clusterRects
      .filter(r => !clusterRects.some(o => bboxContains(r, o)))
      .map(r => ({
        id: r.id,
        title: (r.el.querySelector('.cluster-label, text')?.textContent || '').trim(),
        nodeCodes: nodePos.filter(p => nodeInCluster(r, p)).map(p => p.code)
      }))
    const legend = (() => {
      const panel = doc && doc.querySelector('.color-legend-panel')
      if (!panel) return []
      const list = panel.children[1] || panel
      return Array.from(list.querySelectorAll('div')).map(item => {
        const rect = item.querySelector('svg rect')
        return {
          name: (item.querySelector('span:last-child')?.textContent || '').trim(),
          color: rect ? (rect.getAttribute('fill') || '') : ''
        }
      }).filter(i => i.name)
    })()
    const annotationEls = doc
      ? Array.from(doc.querySelectorAll('.annotation-dock-panel .annotation-item'))
      : []
    const annotations = annotationEls.map(i => {
      const cls = i.className || ''
      const m = cls.match(/annotation-(node|relation|container|item)/)
      return {
        targetId: i.getAttribute('data-target-id'),
        targetType: m ? m[1] : 'unknown',
        text: (i.textContent || '').trim().substring(0, 60),
        selected: i.classList.contains('annotation-item-selected')
      }
    })
    return {
      render: lastRender.value,
      nodes,
      links: {
        svgStrokes: doc
          ? Array.from(doc.querySelectorAll('path.flowchart-link')).map(p => ({
              id: p.getAttribute('id') || '',
              stroke: (p.getAttribute('stroke') || p.style.stroke || '').trim().toLowerCase()
            }))
          : [],
        colorMappings: Array.isArray(stepMeta.linkColorMappings)
          ? stepMeta.linkColorMappings.flat()
          : [],
      },
      containers: {
        totalClusters: clusterRects.length,
        nestedClusters: clusterRects.filter(r => clusterRects.some(o => bboxContains(o, r))).length,
        maxDepth: clusterRects.length ? Math.max(...clusterRects.map(r => depthOf(r))) : 0,
        leafClusters
      },
      legend,
      annotations
    }
  }

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
    setHighlightState,
    getHighlightState,
    dump,
    snapshot
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
    // [FIX 2026-08-02] L5 增量跳过信号 (spec 4.4) — MermaidComponent 每次命中 code-diff
    //   跳过时递增 renderSkippedCount / 记录已渲染 code, chart_e2e A8 断言读取.
    renderSkippedCount: 0,
    lastRenderedCode: null,
    hooks: diag.hooks,
    // [P0-B 2026-08-03] useTooltip 闭包 highlight 状态镜像 (与 DOM .annotation-highlighted 互补)
    //   chart_e2e D 段断言 + chart_diag dump 一键读取, 排查"双高亮系统不对齐"类问题.
    get highlight() { return diag.getHighlightState() },
    dump: diag.dump,
    snapshot: diag.snapshot
  }
}