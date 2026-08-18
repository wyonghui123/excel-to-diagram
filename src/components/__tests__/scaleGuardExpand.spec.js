import { describe, it, expect } from 'vitest'
import { estimateExpand } from '@/services/scaleGuard/estimator'
import { classify } from '@/services/scaleGuard/guard'

const cfg = { softRels: 300, softNodes: 250, hardRels: 600, hardNodes: 400 }
const groups = [
  { id: 'sd1', groupType: 'subDomain', collapsed: true, directNodes: ['A01', 'A02'], children: [], containers: [] },
  { id: 'sd2', groupType: 'subDomain', collapsed: false, directNodes: ['B01'], children: [], containers: [] }
]
const links = [
  { sourceCode: 'A01', targetCode: 'A02' },
  { sourceCode: 'A01', targetCode: 'B01' },
  { sourceCode: 'B01', targetCode: 'X99' }
]

describe('scaleGuard expand', () => {
  it('estimateExpand 展开折叠分组(全展开)后 nodes/relations 增加', () => {
    // 预展开: sd1 折叠(1聚合) + B01 = 2; 展开 sd1(99)后: A01+A02+B01 = 3
    const cur = estimateExpand(groups, links, 'sd1', 99)
    expect(cur.nodes).toBe(3)
    expect(cur.relations).toBe(2) // A01-A02, A01-B01
  })
  it('estimateExpand 目标已展开时结果与现状一致', () => {
    // sd2 已展开(subDomain), 展开到子领域层(level=1): 无更深分组 → sd1(1) + B01(1) = 2
    const v = estimateExpand(groups, links, 'sd2', 1)
    expect(v.nodes).toBe(2)
    expect(v.relations).toBe(0) // A01 在 sd1 折叠内不可见 → 仅 B01 可见
  })
  it('classify 用展开后预估数判定', () => {
    expect(classify({ nodes: 300, relations: 400 }, cfg)).toBe('soft')
    expect(classify({ nodes: 300, relations: 650 }, cfg)).toBe('hard')
  })
})
