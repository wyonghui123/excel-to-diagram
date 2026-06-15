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
