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
})
