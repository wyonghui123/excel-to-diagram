import { describe, it, expect } from 'vitest'
import { buildHierarchyTree } from '../buildHierarchyTree.js'

const preview = {
  domainProducts: [
    { name: '营销云', code: 'MKT', modules: [
      { name: '营销中台', code: 'MKT-M', submodules: [
        { name: '会员中心', code: 'SM001', businessObjects: [
          { id: 101, code: 'BO001', name: '会员' },
          { id: 102, code: 'BO002', name: '会员等级' },
        ] },
      ] },
    ] },
    { name: '供应链云', code: 'SUP', modules: [
      { name: '供应链计划', code: 'SUP-P', submodules: [
        { name: '需求计划', code: 'DP', businessObjects: [
          { id: 103, code: 'DP01', name: '需求计划' },
        ] },
      ] },
    ] },
  ],
  relationships: [
    { id: 901, source_bo_id: 101, target_bo_id: 103, relation_code: 'PLA001-PLD00201' },
  ],
}

describe('buildHierarchyTree', () => {
  it('从 domainProducts 构建五层树', () => {
    const { tree, elementRefIndex } = buildHierarchyTree({ preview })
    expect(tree.layer).toBe('PRODUCT')
    expect(tree.children.map(c => c.code)).toEqual(['MKT', 'SUP'])
    const sm = tree.children[0].children[0].children[0] // 营销中台 → 会员中心
    expect(sm.layer).toBe('SERVICE_MODULE')
    expect(sm.code).toBe('SM001')
    expect(sm.children.map(bo => bo.code)).toEqual(['BO001', 'BO002'])
  })

  it('elementRefIndex 覆盖所有 BO/SM/子领域/领域', () => {
    const { elementRefIndex } = buildHierarchyTree({ preview })
    expect(elementRefIndex.has(101)).toBe(true)  // BO001
    expect(elementRefIndex.has(103)).toBe(true)  // DP01
  })

  it('links 端点引用原始 elementRef id', () => {
    const { links } = buildHierarchyTree({ preview })
    expect(links).toHaveLength(1)
    expect(links[0].source).toBe(101)
    expect(links[0].target).toBe(103)
  })
})
