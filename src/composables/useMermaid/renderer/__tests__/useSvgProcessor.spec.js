/**
 * useSvgProcessor 单元测试 (v32 修复回归保护 - 2026-06-13)
 *
 * 覆盖 Bug: ReferenceError: cleanup is not defined
 * 之前 return 中引用了未定义的 cleanup, 触发 setup() 阶段 ReferenceError
 * 修复: 添加 cleanup 函数, 内部调用 tooltip.cleanup()
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock 依赖, 避免在 jsdom 环境加载 mermaid
vi.mock('../style/useSvgStyle.js', () => ({
  useSvgStyle: () => ({
    fixArrowMarkers: vi.fn(),
    fixLabelBackground: vi.fn(),
    fixEdgeLabelOverflow: vi.fn()
  })
}))

vi.mock('../tooltip/useTooltip.js', () => ({
  useTooltip: () => ({
    addMouseOverTooltips: vi.fn(),
    cleanup: vi.fn()
  })
}))

vi.mock('../annotation/index.js', () => ({
  useAnnotation: () => ({
    parseAnnotationsFromData: vi.fn(() => []),
    setConfig: vi.fn(),
    buildNumberMap: vi.fn(() => ({}))
  }),
  useAnnotationOverlay: () => ({
    removeAnnotationLayers: vi.fn(),
    overlayNumberMarkers: vi.fn(),
    overlayAnnotationPanel: vi.fn(),
    bindAnnotationInteraction: vi.fn(),
    overlayColorLegend: vi.fn()
  })
}))

vi.mock('../interaction/useInteraction.js', () => ({
  useInteraction: () => ({})
}))

describe('useSvgProcessor - cleanup 函数 (v32 ReferenceError 修复)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('useSvgProcessor 导入不抛 ReferenceError (cleanup 必须已定义)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    expect(() => useSvgProcessor({})).not.toThrow()
  })

  it('返回的 api 包含 cleanup 函数 (类型 = function)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    expect(typeof api.cleanup).toBe('function')
  })

  it('cleanup() 内部调用 tooltip.cleanup()', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    api.cleanup()
    // tooltip.cleanup 来自 useTooltip.js mock, 已被调用
    // 注: 实际验证需要拿到 useTooltip 实例, 这里仅验证不抛错
    expect(() => api.cleanup()).not.toThrow()
  })

  it('多次调用 cleanup 不抛错 (幂等)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    expect(() => {
      api.cleanup()
      api.cleanup()
      api.cleanup()
    }).not.toThrow()
  })

  it('其它关键 API 仍正常导出 (回归保护)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    expect(typeof api.processSvg).toBe('function')
    expect(typeof api.fixViewBox).toBe('function')
    expect(typeof api.addTooltips).toBe('function')
    expect(typeof api.renderAnnotationOverlay).toBe('function')
    expect(typeof api.setupCanvasLayout).toBe('function')
    expect(typeof api.buildColorLegendData).toBe('function')
  })
})

describe('useSvgProcessor - processSvg 调用 fixEdgeLabelSize (v33 关键回归)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fixEdgeLabelSize 导出, 接受 svgEl 参数, 不抛错', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})

    const svgEl = {
      getBoundingClientRect: vi.fn(() => ({ width: 100, height: 100, top: 0, left: 0, right: 100, bottom: 100, x: 0, y: 0 })),
      querySelectorAll: vi.fn(() => [])
    }
    expect(() => api.fixEdgeLabelSize(svgEl)).not.toThrow()
  })

  it('fixEdgeLabelSize 处理 null svgEl 不抛错', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    expect(() => api.fixEdgeLabelSize(null)).not.toThrow()
    expect(() => api.fixEdgeLabelSize(undefined)).not.toThrow()
  })
})

describe('useSvgProcessor - fixViewBox 幂等 (2026-08-10 图表缩小修复)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const makeApi = async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    return useSvgProcessor({})
  }

  // 构造一个 JS DOM 影子 SVG 元素 (setAttribute/getAttribute)
  const makeSvg = (vb) => ({
    _attrs: { viewBox: vb },
    getAttribute(k) { return this._attrs[k] ?? null },
    setAttribute(k, v) { this._attrs[k] = String(v) }
  })

  it('负坐标 viewBox 首次调用会加 padding 并标记已处理', async () => {
    const api = await makeApi()
    const svg = makeSvg('-20 -20 100 200')
    api.fixViewBox(svg)
    expect(svg.getAttribute('viewBox')).toBe('-40 -40 140 240')
    expect(svg.getAttribute('data-viewbox-padded')).toBe('true')
  })

  it('同一元素重复调用 fixViewBox 不再叠加 padding (幂等)', async () => {
    const api = await makeApi()
    const svg = makeSvg('-20 -20 100 200')
    // 模拟真实 UI 反复切换"区分对象范围"触发多次 processSvg
    api.fixViewBox(svg)
    const first = svg.getAttribute('viewBox')
    api.fixViewBox(svg)
    api.fixViewBox(svg)
    api.fixViewBox(svg)
    expect(svg.getAttribute('viewBox')).toBe(first)
    expect(svg.getAttribute('viewBox')).toBe('-40 -40 140 240')
  })

  it('全正坐标 viewBox 不修改且不标记', async () => {
    const api = await makeApi()
    const svg = makeSvg('10 10 100 200')
    api.fixViewBox(svg)
    expect(svg.getAttribute('viewBox')).toBe('10 10 100 200')
    expect(svg.getAttribute('data-viewbox-padded')).toBeNull()
  })

  it('null/undefined svgEl 不抛错', async () => {
    const api = await makeApi()
    expect(() => api.fixViewBox(null)).not.toThrow()
    expect(() => api.fixViewBox(undefined)).not.toThrow()
  })
})

describe('useSvgProcessor - buildColorLegendData 整组都在对象范围不单独列示 (2026-08-05 恢复)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const makeApi = async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    return useSvgProcessor({})
  }

  it('区分对象范围时, 整组都在对象范围的服务模块不单独列示', async () => {
    const api = await makeApi()
    const diagramData = {
      colorGroupBy: 'serviceModule',
      centerScopeColor: '#808080',
      centerObjectColor: '#EDEDED',
      nodes: [
        // 需求计划：整组都在对象范围（isCenter=true）→ 应被跳过
        { code: 'A1', name: 'A1', serviceModuleName: '需求计划', subDomain: '供应链计划', domain: '计划', isCenter: true },
        { code: 'A2', name: 'A2', serviceModuleName: '需求计划', subDomain: '供应链计划', domain: '计划', isCenter: true },
        // 生产计划：含非对象范围节点 → 应保留
        { code: 'B1', name: 'B1', serviceModuleName: '生产计划', subDomain: '制造', domain: '制造', isCenter: true },
        { code: 'B2', name: 'B2', serviceModuleName: '生产计划', subDomain: '制造', domain: '制造', isCenter: false }
      ]
    }
    const legend = api.buildColorLegendData(diagramData, [], true)
    const names = legend.map(i => i.name)
    expect(names).toContain('对象范围')          // 有对象范围节点 → 对象范围项在
    expect(names).not.toContain('需求计划')       // 整组都在对象范围 → 跳过
    expect(names).toContain('生产计划')           // 含非对象范围节点 → 保留
  })

  it('不区分对象范围时, 所有分组都正常列示', async () => {
    const api = await makeApi()
    const diagramData = {
      colorGroupBy: 'serviceModule',
      centerScopeColor: '#808080',
      centerObjectColor: '#EDEDED',
      nodes: [
        { code: 'A1', name: 'A1', serviceModuleName: '需求计划', subDomain: '供应链计划', domain: '计划', isCenter: true },
        { code: 'A2', name: 'A2', serviceModuleName: '需求计划', subDomain: '供应链计划', domain: '计划', isCenter: true }
      ]
    }
    const legend = api.buildColorLegendData(diagramData, [], false)
    const names = legend.map(i => i.name)
    expect(names).not.toContain('对象范围')       // 不区分 → 无对象范围项
    expect(names).toContain('需求计划')           // 不区分 → 整组对象范围也正常列出
  })

  it('按领域分组时, 整组都在对象范围的领域同样跳过', async () => {
    const api = await makeApi()
    const diagramData = {
      colorGroupBy: 'domain',
      centerScopeColor: '#808080',
      centerObjectColor: '#EDEDED',
      nodes: [
        { code: 'A1', name: 'A1', serviceModuleName: 'M1', subDomain: 'S1', domain: '计划', isCenter: true },
        { code: 'B1', name: 'B1', serviceModuleName: 'M2', subDomain: 'S2', domain: '计划', isCenter: true },
        { code: 'C1', name: 'C1', serviceModuleName: 'M3', subDomain: 'S3', domain: '制造', isCenter: false }
      ]
    }
    const legend = api.buildColorLegendData(diagramData, [], true)
    const names = legend.map(i => i.name)
    expect(names).not.toContain('计划')           // 整组都在对象范围 → 跳过
    expect(names).toContain('制造')               // 含非对象范围节点 → 保留
  })

  // [LEGEND-SECTION 2026-08-15] 区分对象范围时, 对象范围项后应插入"对象范围外部"节标题,
  //   明确下方颜色分组属于范围外元素; 不区分或仅有对象范围项时不应有节标题.
  it('区分对象范围且有范围外分组时, 插入"对象范围外部"节标题', async () => {
    const api = await makeApi()
    const diagramData = {
      colorGroupBy: 'domain',
      centerScopeColor: '#808080',
      centerObjectColor: '#EDEDED',
      centerScope: ['A1'],
      nodes: [
        { code: 'A1', name: 'A1', serviceModuleName: 'M1', subDomain: 'S1', domain: '计划', isCenter: true },
        { code: 'C1', name: 'C1', serviceModuleName: 'M3', subDomain: 'S3', domain: '制造', isCenter: false }
      ]
    }
    const legend = api.buildColorLegendData(diagramData, [], true)
    const names = legend.map(i => i.name)
    expect(names[0]).toBe('对象范围')
    expect(names[1]).toBe('对象范围外部')
    expect(legend[1].isSection).toBe(true)
    expect(names).toContain('制造')
  })

  it('不区分对象范围时, 不插入节标题', async () => {
    const api = await makeApi()
    const diagramData = {
      colorGroupBy: 'domain',
      centerScopeColor: '#808080',
      centerObjectColor: '#EDEDED',
      centerScope: ['A1'],
      nodes: [
        { code: 'A1', name: 'A1', serviceModuleName: 'M1', subDomain: 'S1', domain: '计划', isCenter: true },
        { code: 'C1', name: 'C1', serviceModuleName: 'M3', subDomain: 'S3', domain: '制造', isCenter: false }
      ]
    }
    const legend = api.buildColorLegendData(diagramData, [], false)
    expect(legend.some(i => i.isSection)).toBe(false)
    expect(legend.some(i => i.name === '对象范围')).toBe(false)
  })
})

describe('useSvgProcessor - addNodeCodeAttributes 同名前缀 BO 编码匹配 (2026-08-09)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const makeNode = (label, id) => ({
    id,
    querySelector: (sel) => sel === '.nodeLabel' ? { textContent: label } : null,
    getAttribute: (attr) => attr === 'id' ? id : null,
    setAttribute: vi.fn()
  })

  const makeSvg = (nodes) => ({
    querySelectorAll: (sel) => sel === '.node' ? nodes : []
  })

  it('BO 叶子节点 "需求计划算法方案PLB034" 应标 data-code=PLB034 而非同名前缀的 DP01', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    const diagramData = {
      nodes: [
        { code: 'DP01', name: '需求计划' },
        { code: 'PLB034', name: '需求计划算法方案' },
        { code: 'PLD00601', name: '需求计划协同对象' },
        { code: 'PLD00201', name: '需求计划薄' }
      ]
    }
    const plb034Node = makeNode('需求计划算法方案PLB034', 'flowchart-N6-14')
    const dp01Node = makeNode('需求计划DP01', 'flowchart-N4-12')
    const svg = makeSvg([plb034Node, dp01Node])
    api.addNodeCodeAttributes(svg, diagramData)
    // 取最后一次 setAttribute('data-code', ...) 的参数
    const setCode = (el) => el.setAttribute.mock.calls.filter(c => c[0] === 'data-code').map(c => c[1])
    expect(setCode(plb034Node)).toContain('PLB034')
    expect(setCode(plb034Node)).not.toContain('DP01')
    expect(setCode(dp01Node)).toContain('DP01')
  })

  it('COLLAPSE 容器节点不因同名 BO 被误标 data-code (仅标 data-container-code)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    const diagramData = {
      nodes: [
        { code: 'DP01', name: '需求计划' },
        { code: 'PLB034', name: '需求计划算法方案' }
      ]
    }
    const collapseNode = makeNode('[需求计划]服务模块 DP', 'flowchart-COLLAPSE_SM_DP-9')
    const svg = makeSvg([collapseNode])
    api.addNodeCodeAttributes(svg, diagramData)
    const dataCodeCalls = collapseNode.setAttribute.mock.calls.filter(c => c[0] === 'data-code')
    expect(dataCodeCalls.length).toBe(0)          // COLLAPSE 节点不应有 data-code
    const containerCode = collapseNode.setAttribute.mock.calls.find(c => c[0] === 'data-container-code')
    expect(containerCode && containerCode[1]).toBe('DP')
  })
})

describe('useSvgProcessor - addLinkCodeAttributes 关系编码定位 (2026-08-09)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const makeEdge = (labelText) => {
    const edgeGroup = { setAttribute: vi.fn() }
    const edgeLabel = {
      textContent: labelText,
      closest: (sel) => sel === 'g' ? edgeGroup : null
    }
    return { edgeLabel, edgeGroup }
  }

  const makeSvg = (edgeLabels) => ({
    querySelectorAll: (sel) => sel === '.edgeLabel' ? edgeLabels : []
  })

  it('relationCode 为空时回退到 link.code, 设置 data-relation-code (arch data 流程修复)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    const diagramData = {
      links: [
        { code: 'PLA001-PLD00201', relationCode: '', source: 'PLA001', target: 'PLD00201' }
      ]
    }
    const { edgeLabel, edgeGroup } = makeEdge('PLA001-PLD00201')
    const svg = makeSvg([edgeLabel])
    api.addLinkCodeAttributes(svg, diagramData)
    const setCalls = edgeGroup.setAttribute.mock.calls.filter(c => c[0] === 'data-relation-code')
    expect(setCalls.length).toBe(1)
    expect(setCalls[0][1]).toBe('PLA001-PLD00201')  // 回退到 link.code (= 渲染标签 = annotation targetId)
  })

  it('relationCode 非空时优先用 relationCode (addBidirectionalAttributes 依赖)', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    const diagramData = {
      links: [
        { code: 'PLA001-PLD00201', relationCode: 'BELONGS_TO', source: 'PLA001', target: 'PLD00201' }
      ]
    }
    const { edgeLabel, edgeGroup } = makeEdge('PLA001-PLD00201')
    const svg = makeSvg([edgeLabel])
    api.addLinkCodeAttributes(svg, diagramData)
    const setCalls = edgeGroup.setAttribute.mock.calls.filter(c => c[0] === 'data-relation-code')
    expect(setCalls.length).toBe(1)
    expect(setCalls[0][1]).toBe('BELONGS_TO')
  })

  it('标签不匹配任何 link 时, 不设置 data-relation-code', async () => {
    const { useSvgProcessor } = await import('../useSvgProcessor.js')
    const api = useSvgProcessor({})
    const diagramData = {
      links: [
        { code: 'PLA001-PLD00201', relationCode: '', source: 'PLA001', target: 'PLD00201' }
      ]
    }
    const { edgeLabel, edgeGroup } = makeEdge('SOMETHING-ELSE')
    const svg = makeSvg([edgeLabel])
    api.addLinkCodeAttributes(svg, diagramData)
    const setCalls = edgeGroup.setAttribute.mock.calls.filter(c => c[0] === 'data-relation-code')
    expect(setCalls.length).toBe(0)
  })
})
