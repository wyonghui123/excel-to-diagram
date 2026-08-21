/**
 * useSvgStyle 单元测试 (v33 修复回归保护 - 2026-06-13)
 *
 * 覆盖 fixEdgeLabelOverflow:
 * - 测宽: 读 labelBkg.getBoundingClientRect().width
 * - 改 foreignObject width 属性
 * - 调整 foreignObject x 属性 (保持中心点)
 * - 同步调整 rect 背景框
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useSvgStyle } from '../useSvgStyle.js'

/**
 * 构造一个 mermaid 输出的 edgeLabel 模拟结构
 * g.edgeLabel > foreignObject(width=W, x=-W/2) > div.labelBkg
 */
function buildMermaidEdgeLabel(text, foreignObjectWidth = 80) {
  const svgNs = 'http://www.w3.org/2000/svg'
  const xhtmlNs = 'http://www.w3.org/1999/xhtml'

  const g = document.createElementNS(svgNs, 'g')
  g.setAttribute('class', 'edgeLabel')

  // inner g.label 包裹 (mermaid 结构)
  const gLabel = document.createElementNS(svgNs, 'g')
  gLabel.setAttribute('class', 'label')
  g.appendChild(gLabel)

  // rect 背景框 (mermaid 输出)
  const rect = document.createElementNS(svgNs, 'rect')
  rect.setAttribute('class', 'background')
  rect.setAttribute('x', -foreignObjectWidth / 2)
  rect.setAttribute('y', -10)
  rect.setAttribute('width', foreignObjectWidth)
  rect.setAttribute('height', 20)
  gLabel.appendChild(rect)

  // foreignObject
  const foreignObject = document.createElementNS(svgNs, 'foreignObject')
  foreignObject.setAttribute('x', -foreignObjectWidth / 2)
  foreignObject.setAttribute('y', -10)
  foreignObject.setAttribute('width', foreignObjectWidth)
  foreignObject.setAttribute('height', 20)
  gLabel.appendChild(foreignObject)

  // div.labelBkg
  const labelBkg = document.createElementNS(xhtmlNs, 'div')
  labelBkg.setAttribute('class', 'labelBkg')
  labelBkg.style.display = 'table-cell'
  labelBkg.style.whiteSpace = 'nowrap'
  labelBkg.style.maxWidth = '200px'

  // span.edgeLabel
  const span = document.createElementNS(xhtmlNs, 'span')
  span.setAttribute('class', 'edgeLabel')
  // 模拟文字内容
  const p = document.createElementNS(xhtmlNs, 'p')
  p.textContent = text
  span.appendChild(p)
  labelBkg.appendChild(span)
  foreignObject.appendChild(labelBkg)

  // mock getBoundingClientRect: 假设 labelBkg 实际宽度 = 文字宽度 + 20
  // 这样 fixEdgeLabelOverflow 测到 80+20=100, 会扩到 100
  const measuredWidth = text.length * 12 + 20
  labelBkg.getBoundingClientRect = () => ({
    width: measuredWidth,
    height: 20,
    top: 0,
    left: 0,
    right: measuredWidth,
    bottom: 20,
    x: 0,
    y: 0
  })

  return { g, foreignObject, labelBkg, rect, gLabel }
}

describe('useSvgStyle - fixEdgeLabelOverflow (v33 修复回归)', () => {
  let svgStyle
  let svg

  beforeEach(() => {
    svgStyle = useSvgStyle()
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  })

  it('不存在 edgeLabel 时不抛错', () => {
    expect(() => svgStyle.fixEdgeLabelOverflow(svg)).not.toThrow()
  })

  it('null svg 不抛错', () => {
    expect(() => svgStyle.fixEdgeLabelOverflow(null)).not.toThrow()
  })

  it('edge label 文字宽度 > foreignObject width 时自动扩宽 (v33 关键修复)', () => {
    // 模拟 Mermaid 给出 width=80 的 foreignObject
    // 但实际文字 "测试 ABC 测试 ABC" 需要 100px
    const { g, foreignObject, rect, labelBkg } = buildMermaidEdgeLabel('测试 ABC 测试 ABC', 80)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.fixEdgeLabelOverflow(svg)

    // 关键断言 v33: foreignObject width 必须扩到至少 100 + 4 = 104
    const newWidth = parseFloat(foreignObject.getAttribute('width'))
    expect(newWidth).toBeGreaterThan(80)
    expect(newWidth).toBeGreaterThanOrEqual(100 + 4 - 1) // +SAFETY - 1 容差

    // 关键断言 v33: foreignObject x 同步调整, 保持中心点
    // 原 x = -40, 新 width = 104, 中心点 x 应 = -52 (即 -104/2)
    // 也就是 x 应该向左偏 (widthDiff / 2) = (104-80)/2 = 12
    const newX = parseFloat(foreignObject.getAttribute('x'))
    expect(newX).toBeLessThan(-40)
    expect(Math.abs(newX - (-newWidth / 2))).toBeLessThan(0.5) // 中心点对齐

    // 关键断言 v33: rect 背景框同步调整
    const newRectWidth = parseFloat(rect.getAttribute('width'))
    expect(newRectWidth).toBe(newWidth)
    const newRectX = parseFloat(rect.getAttribute('x'))
    expect(newRectX).toBe(newX)

    document.body.removeChild(svg)
  })

  it('labelBkg 已设 padding 后能正确测宽', () => {
    const { g, foreignObject } = buildMermaidEdgeLabel('短', 80)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.fixEdgeLabelOverflow(svg)

    // 即使文字很短, padding 4px 8px 后内容宽度至少 36
    // 但 measured width (在 mock 里) = 文字宽度 + 20, "短" 测到 32
    // foreignObject width 至少 32+4=36
    const newWidth = parseFloat(foreignObject.getAttribute('width'))
    expect(newWidth).toBeGreaterThanOrEqual(36 - 1)

    document.body.removeChild(svg)
  })

  it('CSS: 设置了 max-width: none 覆盖 mermaid 内联', () => {
    const { g, foreignObject, labelBkg } = buildMermaidEdgeLabel('test', 80)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.fixEdgeLabelOverflow(svg)

    expect(labelBkg.style.getPropertyValue('max-width')).toBe('none')
    expect(labelBkg.style.getPropertyValue('white-space')).toBe('nowrap')
    expect(labelBkg.style.getPropertyValue('overflow')).toBe('visible')
    expect(labelBkg.style.getPropertyValue('padding')).toBe('4px 8px')
    expect(foreignObject.style.getPropertyValue('overflow')).toBe('visible')

    document.body.removeChild(svg)
  })

  it('不修改 nodeLabel / cluster-label (回归保护)', () => {
    const svgNs = 'http://www.w3.org/2000/svg'
    const gNode = document.createElementNS(svgNs, 'g')
    gNode.setAttribute('class', 'node')
    const nodeLabel = document.createElementNS(svgNs, 'foreignObject')
    nodeLabel.setAttribute('x', '0')
    nodeLabel.setAttribute('y', '0')
    nodeLabel.setAttribute('width', '100')
    nodeLabel.setAttribute('height', '30')
    const div = document.createElement('div')
    div.setAttribute('class', 'nodeLabel')
    div.textContent = '节点'
    nodeLabel.appendChild(div)
    gNode.appendChild(nodeLabel)
    svg.appendChild(gNode)
    document.body.appendChild(svg)

    const originalWidth = nodeLabel.getAttribute('width')
    const originalX = nodeLabel.getAttribute('x')

    svgStyle.fixEdgeLabelOverflow(svg)

    // nodeLabel 的 width/x 不应被修改
    expect(nodeLabel.getAttribute('width')).toBe(originalWidth)
    expect(nodeLabel.getAttribute('x')).toBe(originalX)

    document.body.removeChild(svg)
  })
})

// [FIX 2026-08-05] syncArrowMarkers: 箭头 marker 颜色跟随 path stroke (增量变色后箭头色同步)
describe('useSvgStyle - syncArrowMarkers (箭头色跟随线色)', () => {
  let svgStyle
  let svg

  const buildEdgePath = (id, stroke) => {
    const svgNs = 'http://www.w3.org/2000/svg'
    const g = document.createElementNS(svgNs, 'g')
    g.setAttribute('class', 'edgePath')
    const path = document.createElementNS(svgNs, 'path')
    path.setAttribute('class', 'flowchart-link')
    path.setAttribute('stroke', stroke)
    g.appendChild(path)
    return { g, path }
  }

  beforeEach(() => {
    svgStyle = useSvgStyle()
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  })

  it('箭头 marker fill 与 path stroke 一致', () => {
    const { g, path } = buildEdgePath('e1', '#1890ff')
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.syncArrowMarkers(svg, 'businessObject')

    const defs = svg.querySelector('defs')
    expect(defs).toBeTruthy()
    // marker-end 指向 arrowhead-1890ff
    expect(path.getAttribute('marker-end')).toContain('arrowhead-1890ff')
    // marker polygon fill = 线色
    const poly = defs.querySelector('#arrowhead-1890ff polygon')
    expect(poly.getAttribute('fill')).toBe('#1890ff')
    document.body.removeChild(svg)
  })

  it('改线色后再 sync, 箭头 marker 更新为新色 (增量变色后箭头色同步)', () => {
    const { g, path } = buildEdgePath('e1', '#1890ff')
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.syncArrowMarkers(svg, 'businessObject')
    expect(path.getAttribute('marker-end')).toContain('arrowhead-1890ff')

    // 模拟 updateLinkColors 改线色为红色
    path.setAttribute('stroke', '#f5222d')
    path.style.stroke = '#f5222d'
    svgStyle.syncArrowMarkers(svg, 'businessObject')

    // marker-end 指向新色 marker
    expect(path.getAttribute('marker-end')).toContain('arrowhead-f5222d')
    const defs = svg.querySelector('defs')
    const poly = defs.querySelector('#arrowhead-f5222d polygon')
    expect(poly.getAttribute('fill')).toBe('#f5222d')
    document.body.removeChild(svg)
  })

  it('单向边不残留 marker-start', () => {
    const { g, path } = buildEdgePath('e1', '#1890ff')
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.syncArrowMarkers(svg, 'businessObject')
    expect(path.getAttribute('marker-start')).toBeNull()
    document.body.removeChild(svg)
  })
})

// [OPT 2026-08-06] 多行容器标题最小高度修复 (解决换行后被节点/边框遮挡)
describe('useSvgStyle - fixForeignObjectWidth (多行容器标题高度)', () => {
  let svgStyle
  let svg

  const buildSubgraphFO = (text, height = 24) => {
    const svgNs = 'http://www.w3.org/2000/svg'
    const xhtmlNs = 'http://www.w3.org/1999/xhtml'

    const g = document.createElementNS(svgNs, 'g')
    g.setAttribute('class', 'subgraph')
    const fo = document.createElementNS(svgNs, 'foreignObject')
    fo.setAttribute('x', '0')
    fo.setAttribute('y', '0')
    fo.setAttribute('width', '200')
    fo.setAttribute('height', String(height))
    const div = document.createElementNS(xhtmlNs, 'div')
    div.textContent = text
    fo.appendChild(div)
    g.appendChild(fo)
    return { g, fo, div }
  }

  beforeEach(() => {
    svgStyle = useSvgStyle()
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  })

  it('多行标题时高度扩展到容纳所有行', () => {
    const { g, fo } = buildSubgraphFO('需求计划 DP\n（供应链云/供应链计划）', 24)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.validateContainerTitles(svg)

    // [FIX 2026-08-06] 行高对齐 Mermaid 实际 24px/行: 2 行 * 24 + 4 padding = 52
    //   原旧算法用 24*1.3=31.2px/行 → 2 行得 70px, 会过度下探压到容器内容.
    const newHeight = parseFloat(fo.getAttribute('height'))
    expect(newHeight).toBeGreaterThan(24)
    expect(newHeight).toBeGreaterThanOrEqual(2 * 24 + 4 - 1)
    expect(newHeight).toBeLessThan(70)  // 不再过度拉升到 70 (旧行为)
    document.body.removeChild(svg)
  })

  it('多行容器标题压缩行高+内边距, 避免父名称第二行被子内容遮挡', () => {
    const { g, fo, div } = buildSubgraphFO('供应链计划\n（供应链云）', 24)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.validateContainerTitles(svg)

    // [FIX 2026-08-06] mermaid 按单行布局 subgraph 标签, 内容从标签下方即开始排列,
    //   两行标签若用 1.3 行高, 父名称第二行会下探到内容区被遮挡. 压缩为 1.1 + 上下 2px 内边距,
    //   让文字足迹收敛进 mermaid 预留的单行空间.
    expect(div.style.lineHeight).toBe('1.1')
    expect(div.style.padding).toBe('2px 8px')
    expect(div.style.whiteSpace).toBe('pre-line')
    document.body.removeChild(svg)
  })

  it('单行标题不改变高度 (回归保护)', () => {
    const { g, fo } = buildSubgraphFO('采购管理', 24)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.validateContainerTitles(svg)

    expect(fo.getAttribute('height')).toBe('24')
    document.body.removeChild(svg)
  })

  it('多行标题未超出当前高度时不重复扩展', () => {
    const { g, fo } = buildSubgraphFO('需求计划 DP\n（供应链云/供应链计划）', 200)
    svg.appendChild(g)
    document.body.appendChild(svg)

    svgStyle.validateContainerTitles(svg)

    // 当前高度已足够, 不应被缩小
    expect(fo.getAttribute('height')).toBe('200')
    document.body.removeChild(svg)
  })
})
