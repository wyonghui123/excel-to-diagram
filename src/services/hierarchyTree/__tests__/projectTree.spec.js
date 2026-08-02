import { describe, it, expect } from 'vitest'
import { buildHierarchyTree } from '../buildHierarchyTree.js'
import { projectTree, GLOBAL_TERMINALS } from '../projectTree.js'

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
  ],
  relationships: [
    { id: 901, source_bo_id: 101, target_bo_id: 102, relation_code: 'R1' },
  ],
}

describe('projectTree', () => {
  it('serviceModule 末端粒度: BO 折叠进 SM, link 重映射, 自环丢弃', () => {
    const { tree, elementRefIndex, links } = buildHierarchyTree({ preview })
    const { nodes, containers, links: outLinks } = projectTree(
      { tree, elementRefIndex, links },
      { terminalResolver: GLOBAL_TERMINALS.serviceModule }
    )
    expect(nodes).toHaveLength(1)                    // 仅 SM001
    expect(nodes[0].id).toBe('SM001')                // 显示节点 id = code
    expect(nodes[0].aggregated.count).toBe(2)        // 折叠 2 个 BO
    // 容器为嵌套树: 领域(children) → 子领域(nodeIds=SM code)
    expect(containers).toHaveLength(1)               // 领域容器
    expect(containers[0].layer).toBe('DOMAIN')
    expect(containers[0].children).toHaveLength(1)   // 子领域容器
    expect(containers[0].children[0].layer).toBe('SUB_DOMAIN')
    expect(containers[0].children[0].nodeIds).toEqual(['SM001']) // 容器内节点 = code
    expect(outLinks).toHaveLength(0)                 // 两端同 SM → 丢弃
  })

  it('businessObject 末端粒度: BO 为节点, SM/子领域为容器', () => {
    const { tree, elementRefIndex, links } = buildHierarchyTree({ preview })
    const { nodes, containers, links: outLinks } = projectTree(
      { tree, elementRefIndex, links },
      { terminalResolver: GLOBAL_TERMINALS.businessObject }
    )
    expect(nodes.map(n => n.code)).toEqual(['BO001', 'BO002'])
    // 容器为嵌套树: 领域(children) → 子领域(children) → 服务模块(nodeIds=BO code)
    expect(containers).toHaveLength(1)
    expect(containers[0].layer).toBe('DOMAIN')
    const sd = containers[0].children[0]
    expect(sd.layer).toBe('SUB_DOMAIN')
    const sm = sd.children[0]
    expect(sm.layer).toBe('SERVICE_MODULE')
    expect(sm.nodeIds).toEqual(['BO001', 'BO002'])
    expect(outLinks).toHaveLength(1)                 // BO001 → BO002
    expect(outLinks[0].source).toBe('BO001')         // 显示节点 id = code
    expect(outLinks[0].target).toBe('BO002')
  })

  it('混合粒度: 不同领域不同末端层', () => {
    const preview2 = {
      domainProducts: [
        { name: '营销云', code: 'MKT', modules: [
          { name: '营销中台', code: 'MKT-M', submodules: [
            { name: '会员中心', code: 'SM001', businessObjects: [
              { id: 101, code: 'BO001', name: '会员' },
            ] },
          ] },
        ] },
        { name: '财务云', code: 'FIN', modules: [
          { name: '核算', code: 'FIN-H', submodules: [
            { name: '总账', code: 'GL', businessObjects: [
              { id: 201, code: 'GL01', name: '总账凭证' },
            ] },
          ] },
        ] },
      ],
      relationships: [{ id: 1, source_bo_id: 101, target_bo_id: 201, relation_code: 'X' }],
    }
    const mixed = (node) => {
      if (node.layer === 'DOMAIN' && node.code === 'MKT') return 'BUSINESS_OBJECT'
      return 'SERVICE_MODULE'
    }
    const { tree, elementRefIndex, links } = buildHierarchyTree({ preview: preview2 })
    const { nodes, links: outLinks } = projectTree(
      { tree, elementRefIndex, links }, { terminalResolver: mixed }
    )
    expect(nodes.map(n => n.code)).toEqual(['BO001', 'GL'])   // MKT→BO, FIN→SM
    expect(outLinks).toHaveLength(1)                          // BO001 → GL
  })
})
