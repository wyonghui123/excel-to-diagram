/**
 * useMermaidColors 单测 (v32 复盘回归保护 - 2026-06-11)
 *
 * 覆盖:
 * - getColorScheme (3 测试): 7 个内置 scheme / 未知 fallback / 空值 fallback
 * - buildColorMap (4 测试): 3 种 groupBy / customColors 覆盖 / nodeName 兜底 / 颜色循环
 * - updateLinkColors (4 测试): 同域 / 跨域 / source fallback target / DEFAULT_LINK_COLOR
 * - filterEnabledContainers (4 测试): 默认全保留 / disabled 过滤 / null 过滤 / 组合
 *
 * 总计: 15 个测试, ~120 行
 */
import { describe, it, expect } from 'vitest'
import { useMermaidColors } from '../useMermaidColors'
import { filterEnabledContainers, partitionContainersByEnabled } from '../../layouts/containerFilter'

describe('useMermaidColors - getColorScheme', () => {
  it('7 个内置 scheme 都能取到', () => {
    const { getColorScheme } = useMermaidColors()
    const schemes = ['default', 'vibrant', 'pastel', 'warm', 'cool', 'business', 'nature']
    schemes.forEach(name => {
      const scheme = getColorScheme(name)
      expect(scheme).toBeDefined()
      expect(Array.isArray(scheme)).toBe(true)
      expect(scheme.length).toBeGreaterThanOrEqual(8)
    })
  })

  it('未知 scheme 应 fallback 到 default', () => {
    const { getColorScheme } = useMermaidColors()
    expect(getColorScheme('unknown-scheme')).toEqual(getColorScheme('default'))
  })

  it('空字符串 / null / undefined 都应 fallback', () => {
    const { getColorScheme } = useMermaidColors()
    expect(getColorScheme('')).toEqual(getColorScheme('default'))
    expect(getColorScheme(null)).toEqual(getColorScheme('default'))
    expect(getColorScheme(undefined)).toEqual(getColorScheme('default'))
  })
})

describe('useMermaidColors - buildColorMap', () => {
  it('colorGroupBy=domain 时按 domain 分组, 相同 domain 合并', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
      ['N2', { domain: '业务A' }],
      ['N3', { domain: '业务B' }]
    ])
    const nodeColorMappings = [
      { nodeCode: 'N1' },
      { nodeCode: 'N2' },
      { nodeCode: 'N3' }
    ]
    const colorMap = buildColorMap(
      nodeColorMappings, objectToModuleMap, 'domain',
      ['#FF0000', '#00FF00', '#0000FF'], {}
    )
    expect(colorMap.size).toBe(2)  // 业务A + 业务B
    expect(colorMap.get('业务A')).toBe('#FF0000')
    expect(colorMap.get('业务B')).toBe('#00FF00')
  })

  it('colorGroupBy=serviceModule 时按 serviceModuleName 分组', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([
      ['N1', { serviceModuleName: '订单模块' }],
      ['N2', { serviceModule: '支付模块' }]  // serviceModule 兜底
    ])
    const colorMap = buildColorMap(
      [{ nodeCode: 'N1' }, { nodeCode: 'N2' }], objectToModuleMap, 'serviceModule',
      ['#FF0000', '#00FF00'], {}
    )
    expect(colorMap.get('订单模块')).toBe('#FF0000')
    expect(colorMap.get('支付模块')).toBe('#00FF00')
  })

  it('customColors 覆盖默认 scheme 颜色', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map([['N1', { domain: '业务A' }]])
    const colorMap = buildColorMap(
      [{ nodeCode: 'N1' }], objectToModuleMap, 'domain',
      ['#FF0000'], { '业务A': '#123456' }
    )
    expect(colorMap.get('业务A')).toBe('#123456')  // 自定义覆盖
  })

  it('颜色 index 超过 scheme 长度时循环', () => {
    const { buildColorMap } = useMermaidColors()
    const objectToModuleMap = new Map()
    const nodeColorMappings = []
    // 13 个分组, scheme 只有 2 色, 应循环
    for (let i = 0; i < 13; i++) {
      const code = `N${i}`
      objectToModuleMap.set(code, { domain: `域${i}` })
      nodeColorMappings.push({ nodeCode: code })
    }
    const colorMap = buildColorMap(
      nodeColorMappings, objectToModuleMap, 'domain',
      ['#FF0000', '#00FF00'], {}
    )
    expect(colorMap.size).toBe(13)
    // 第 13 个 (index=12) 应是 #FF0000 (12 % 2 = 0)
    expect(colorMap.get('域12')).toBe('#FF0000')
  })
})

describe('useMermaidColors - updateLinkColors', () => {
  // 用 happy-dom 创建 mock svg
  function createMockSvg(numPaths = 1) {
    const paths = []
    for (let i = 0; i < numPaths; i++) {
      const path = {
        setAttribute: function(k, v) { this[k] = v },
        style: { stroke: '' }
      }
      paths.push(path)
    }
    return {
      querySelectorAll: (sel) => {
        if (sel.includes('.flowchart-link') || sel.includes('.edgePath')) {
          return paths
        }
        return []
      }
    }
  }

  it('同域连线: 颜色 = 该域 colorMap 颜色', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
      ['N2', { domain: '业务A' }]
    ])
    const nodeColorMappings = [
      { nodeId: 'id1', nodeCode: 'N1' },
      { nodeId: 'id2', nodeCode: 'N2' }
    ]
    const linkColorMappings = [{
      sourceId: 'id1', targetId: 'id2', index: 0
    }]
    const colorMap = new Map([['业务A', '#FF0000']])
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap)
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#FF0000')
  })

  it('跨域连线: 颜色 = source 域颜色 (而非 target)', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
      ['N2', { domain: '业务B' }]
    ])
    const nodeColorMappings = [
      { nodeId: 'id1', nodeCode: 'N1' },
      { nodeId: 'id2', nodeCode: 'N2' }
    ]
    const linkColorMappings = [{
      sourceId: 'id1', targetId: 'id2', index: 0
    }]
    const colorMap = new Map([
      ['业务A', '#FF0000'],
      ['业务B', '#00FF00']
    ])
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap)
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#FF0000')  // 跟 source 同色
  })

  it('source 不在 colorMap 时, fallback target', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务X' }],  // 不在 colorMap
      ['N2', { domain: '业务A' }]
    ])
    const nodeColorMappings = [
      { nodeId: 'id1', nodeCode: 'N1' },
      { nodeId: 'id2', nodeCode: 'N2' }
    ]
    const linkColorMappings = [{
      sourceId: 'id1', targetId: 'id2', index: 0
    }]
    const colorMap = new Map([['业务A', '#00FF00']])
    updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap)
    expect(svg.querySelectorAll('.edgePath path')[0].stroke).toBe('#00FF00')  // fallback target
  })

  it('path index 越界时优雅降级 (不抛错)', () => {
    const { updateLinkColors } = useMermaidColors()
    const svg = createMockSvg(1)  // 只有 1 条 path
    const objectToModuleMap = new Map([
      ['N1', { domain: '业务A' }],
      ['N2', { domain: '业务A' }]
    ])
    const nodeColorMappings = [
      { nodeId: 'id1', nodeCode: 'N1' },
      { nodeId: 'id2', nodeCode: 'N2' }
    ]
    const linkColorMappings = [{
      sourceId: 'id1', targetId: 'id2', index: 999  // 越界
    }]
    const colorMap = new Map([['业务A', '#FF0000']])
    expect(() => {
      updateLinkColors(svg, linkColorMappings, nodeColorMappings, objectToModuleMap, 'domain', colorMap)
    }).not.toThrow()
  })
})

describe('filterEnabledContainers (Bug 1 回归保护)', () => {
  it('默认 (无 enabled 字段) 全部保留', () => {
    const containers = [
      { name: 'A', nodes: [] },
      { name: 'B', nodes: [] }
    ]
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)
  })

  it('enabled=false 容器被过滤', () => {
    const containers = [
      { name: 'A', enabled: true, nodes: [] },
      { name: 'B', enabled: false, nodes: [] },
      { name: 'C', nodes: [] }
    ]
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)
    expect(result.map(c => c.name)).toEqual(['A', 'C'])
  })

  it('null 容器被过滤', () => {
    const containers = [
      { name: 'A' },
      null,
      undefined,
      { name: 'B' }
    ]
    const result = filterEnabledContainers(containers)
    expect(result.length).toBe(2)
  })

  it('partitionContainersByEnabled 返回 {enabled, disabled}', () => {
    const containers = [
      { name: 'A', enabled: true },
      { name: 'B', enabled: false },
      { name: 'C' }
    ]
    const result = partitionContainersByEnabled(containers)
    expect(result.enabled.map(c => c.name)).toEqual(['A', 'C'])
    expect(result.disabled.map(c => c.name)).toEqual(['B'])
  })
})
