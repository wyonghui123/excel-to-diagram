import { describe, it, expect } from 'vitest'
import { colorize } from '../colorize.js'

const nodes = [
  { id: 'SM_DP', layer: 'SERVICE_MODULE', code: 'DP', name: '需求计划', domain: '供应链云', subDomain: '供应链计划' },
  { id: 'SM_GL', layer: 'SERVICE_MODULE', code: 'GL', name: '总账', domain: '财务云', subDomain: '核算' },
]

describe('colorize', () => {
  it('按 subDomain 分组着色', () => {
    const { nodes: out } = colorize(nodes, [], { colorGroupBy: 'subDomain', colorScheme: 'default' })
    expect(out[0].color).toBeTruthy()
    expect(out[0].color).toMatch(/^#/)
  })

  it('中心模块 colorGroupBy=subDomain 时仍用分组色（非灰）', () => {
    const { nodes: out } = colorize(nodes, [], {
      colorGroupBy: 'subDomain', colorScheme: 'default',
      centerServiceModuleCodes: ['DP'], centerScopeHighlight: true,
    })
    expect(out[0].color).not.toBe('#808080')
    expect(out[0].isCenter).toBe(true)
  })

  it('返回与图表同源的 groupColorMap（键与分组维度对齐）', () => {
    const { groupColorMap } = colorize(nodes, [], {
      colorGroupBy: 'subDomain', colorScheme: 'default',
    })
    // subDomain 分组 → 键为 subDomain 名
    expect(groupColorMap['供应链计划']).toBeTruthy()
    expect(groupColorMap['核算']).toBeTruthy()
    // groupColorMap 与节点实际颜色一致（同源）
    const { nodes: out } = colorize(nodes, [], { colorGroupBy: 'subDomain', colorScheme: 'default' })
    expect(out[0].color).toBe(groupColorMap['供应链计划'])
    expect(out[1].color).toBe(groupColorMap['核算'])
  })

  it('domain 分组时 groupColorMap 键为 domain 名', () => {
    const { groupColorMap } = colorize(nodes, [], {
      colorGroupBy: 'domain', colorScheme: 'default',
    })
    expect(groupColorMap['供应链云']).toBeTruthy()
    expect(groupColorMap['财务云']).toBeTruthy()
    const { nodes: out } = colorize(nodes, [], { colorGroupBy: 'domain', colorScheme: 'default' })
    expect(out[0].color).toBe(groupColorMap['供应链云'])
    expect(out[1].color).toBe(groupColorMap['财务云'])
  })
})
