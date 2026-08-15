/**
 * containerStats.spec.js - 容器统计纯函数 (业务对象数量 + 内部关系数量)
 * 回归保护: 2026-08-14 新增容器悬停 tooltip 的统计口径
 *   - BO 数量 = 容器子树内"当前展示"的 BO
 *   - 内部关系 = source 与 target 均在容器子树内的关系
 */
import { describe, it, expect } from 'vitest'
import { computeContainerStats } from '../containerStats.js'

// 容器树: 供应链云(SCM) > 采购供应(MM) > 库存(INV)/采购请求(PR) 服务模块
const containers = [
  {
    code: 'SCM', layer: 'DOMAIN', name: '供应链云',
    children: [
      {
        code: 'MM', layer: 'SUB_DOMAIN', name: '采购供应',
        children: [
          { code: 'INV', layer: 'SERVICE_MODULE', name: '库存', nodeIds: ['INV01', 'INV02', 'INV99'] },
          { code: 'PR', layer: 'SERVICE_MODULE', name: '采购请求', nodeIds: ['PR01', 'PR02'] },
        ],
      },
    ],
  },
]

const baseData = (nodes, links) => ({
  containers,
  nodes,
  links,
})

describe('computeContainerStats', () => {
  const nodes = [
    { code: 'INV01' }, { code: 'INV02' }, { code: 'PR01' }, { code: 'PR02' },
  ]
  const links = [
    { sourceCode: 'INV01', targetCode: 'INV02' },   // INV 内部 + MM/SCM 内部
    { sourceCode: 'INV01', targetCode: 'PR01' },    // MM/SCM 内部, 跨服务模块
    { sourceCode: 'INV01', targetCode: 'EXT99' },   // 外部 BO (不在图内) → 不计
  ]

  it('按容器子树统计 BO 数量 (含嵌套聚合)', () => {
    const stats = computeContainerStats(baseData(nodes, links))
    expect(stats.get('INV').boCount).toBe(2)   // INV99 未展示不计
    expect(stats.get('PR').boCount).toBe(2)
    expect(stats.get('MM').boCount).toBe(4)
    expect(stats.get('SCM').boCount).toBe(4)
  })

  it('内部关系 = 两端均在容器子树内; 跨服务模块计入上级, 计入自身服务模块不计', () => {
    const stats = computeContainerStats(baseData(nodes, links))
    expect(stats.get('INV').relCount).toBe(1)   // INV01→INV02
    expect(stats.get('PR').relCount).toBe(0)
    expect(stats.get('MM').relCount).toBe(2)    // INV01→INV02 + INV01→PR01
    expect(stats.get('SCM').relCount).toBe(2)
  })

  it('外部 BO (不在图内) 的关系不计入内部关系', () => {
    const stats = computeContainerStats(baseData(nodes, links))
    // INV01→EXT99: EXT99 不在 INV 子树, 不构成 INV 内部关系
    expect(stats.get('INV').relCount).toBe(1)
  })

  it('BO 数量基于当前展示 (nodeIds 含未展示 BO 不计)', () => {
    const partial = baseData(
      nodes.filter(n => n.code !== 'PR02'),
      links,
    )
    const stats = computeContainerStats(partial)
    expect(stats.get('PR').boCount).toBe(1)     // PR02 未展示
    expect(stats.get('MM').boCount).toBe(3)
  })

  it('无 containers 时兜底 layoutGroups (directNodes)', () => {
    const stats = computeContainerStats(
      { nodes, links, layoutControlConfig: null },
      [
        { code: 'SCM', children: [
          { code: 'MM', children: [
            { code: 'INV', directNodes: ['INV01', 'INV02'] },
            { code: 'PR', directNodes: ['PR01', 'PR02'] },
          ] },
        ] },
      ],
    )
    expect(stats.get('INV').boCount).toBe(2)
    expect(stats.get('INV').relCount).toBe(1)
    expect(stats.get('MM').relCount).toBe(2)
  })

  it('空/无数据返回空 Map', () => {
    expect(computeContainerStats(null).size).toBe(0)
    expect(computeContainerStats({ nodes: [], links: [] }).size).toBe(0)
  })
})
