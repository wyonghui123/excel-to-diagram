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
})
