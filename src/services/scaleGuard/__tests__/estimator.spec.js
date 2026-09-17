import { describe, it, expect } from 'vitest'
import { estimateVisible, estimateExpand, codeOf } from '../estimator'

const groups = [
  {
    id: 'd1', groupType: 'domain', collapsed: false,
    directNodes: [],
    children: [
      { id: 'sd1', groupType: 'subDomain', collapsed: true,
        directNodes: ['A01', 'A02'], children: [], containers: [] },
      { id: 'sd2', groupType: 'subDomain', collapsed: false,
        directNodes: ['B01'],
        children: [
          { id: 'sm1', groupType: 'serviceModule', collapsed: false,
            directNodes: ['B02', 'B03'], children: [], containers: [] }
        ], containers: [] }
    ],
    containers: []
  }
]
const links = [
  { sourceCode: 'B01', targetCode: 'B02' }, // 双端可见
  { sourceCode: 'B01', targetCode: 'A01' }, // A01 被折叠 → 不可见
  { sourceCode: 'A01', targetCode: 'A02' }, // 双端被折叠 → 不可见
  { sourceCode: 'X00', targetCode: 'B02' }  // 不在树 → 不可见
]

describe('scaleGuard estimator', () => {
  it('codeOf: 兼容字符串与对象', () => {
    expect(codeOf('A01')).toBe('A01')
    expect(codeOf({ code: 'B01' })).toBe('B01')
    expect(codeOf({ id: 'C01' })).toBe('C01')
    expect(codeOf(null)).toBe('')
  })

  it('estimateVisible: 折叠分组计1聚合节点, 展开分组计direct叶子, 关系双端可见才计', () => {
    const v = estimateVisible(groups, links)
    // nodes: sd1(折叠=1) + B01 + B02 + B03 = 4 (d1/sd2/sm1 展开容器不计)
    expect(v.nodes).toBe(4)
    // relations: 仅 B01-B02 双端可见 = 1
    expect(v.relations).toBe(1)
  })

  it('estimateExpand: 展开指定折叠分组后可见数增加', () => {
    const v = estimateExpand(groups, links, 'sd1', 99) // 99=全展开
    // sd1 从折叠(1)变展开: +A01 +A02 → nodes 4→5
    expect(v.nodes).toBe(5)
    // 新增可见: B01-A01, A01-A02 → relations 1→3
    expect(v.relations).toBe(3)
  })

  it('estimateExpand 层级感知: 展开到服务模块层只露出 SM 聚合节点, 不展开 BO', () => {
    const groups2 = [
      { id: 'sdX', groupType: 'subDomain', collapsed: true, directNodes: [],
        children: [
          { id: 'smX1', groupType: 'serviceModule', collapsed: true, directNodes: ['X01'], children: [], containers: [] },
          { id: 'smX2', groupType: 'serviceModule', collapsed: true, directNodes: ['X02', 'X03'], children: [], containers: [] }
        ], containers: [] }
    ]
    const linksX = [{ sourceCode: 'X01', targetCode: 'X02' }]
    // 展开前: sdX 折叠 → 1 聚合节点
    expect(estimateVisible(groups2, linksX).nodes).toBe(1)
    // 展开到 SM 层 (level=2): sdX 展开, smX1/smX2(level2>=2) 折叠 → nodes=2, BO 不可见 → relations=0
    const v2 = estimateVisible(groups2, linksX, { expandGroupId: 'sdX', expandGroupLevel: 2 })
    expect(v2.nodes).toBe(2)
    expect(v2.relations).toBe(0)
    // 全展开 (level=99): X01/X02/X03 可见 → nodes=3, relations=1
    const v99 = estimateVisible(groups2, linksX, { expandGroupId: 'sdX', expandGroupLevel: 99 })
    expect(v99.nodes).toBe(3)
    expect(v99.relations).toBe(1)
  })

  it('links 兼容 source/target 字段', () => {
    const altLinks = [
      { source: 'B01', target: 'B02' },
      { source: 'B01', target: 'A01' }
    ]
    const v = estimateVisible(groups, altLinks)
    expect(v.relations).toBe(1)
  })
})
