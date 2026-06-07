import { describe, it, expect } from 'vitest'
import {
  treeNodesToScope,
  scopeToNodeKeys,
  nodeKeysToRelationCodes,
  relationCodesToNodeKeys
} from '@/composables/useScopeTreeState'

const OBJECT_TREE_DATA = [
  {
    id: 'd_1',
    originalId: 1,
    name: '供应链云',
    type: 'domain',
    children: [
      {
        id: 's_11',
        originalId: 11,
        name: '采购供应',
        type: 'sub_domain',
        children: [
          {
            id: 'sm_111',
            originalId: 111,
            name: '库存管理模块',
            type: 'service_module',
            children: []
          },
          {
            id: 'sm_112',
            originalId: 112,
            name: '采购管理模块',
            type: 'service_module',
            children: []
          }
        ]
      },
      {
        id: 's_12',
        originalId: 12,
        name: '销售服务',
        type: 'sub_domain',
        children: [
          {
            id: 'sm_121',
            originalId: 121,
            name: '销售管理模块',
            type: 'service_module',
            children: []
          }
        ]
      }
    ]
  },
  {
    id: 'd_2',
    originalId: 2,
    name: '财务云',
    type: 'domain',
    children: [
      {
        id: 's_21',
        originalId: 21,
        name: '财务管理',
        type: 'sub_domain',
        children: [
          {
            id: 'sm_211',
            originalId: 211,
            name: '财务核算模块',
            type: 'service_module',
            children: []
          }
        ]
      }
    ]
  }
]

const RELATION_TREE_DATA = [
  {
    id: 'internal',
    name: '范围内',
    children: [
      {
        id: 'internal-cross-domain',
        name: '跨领域',
        children: [
          {
            id: 'internal-cross-domain-module-111-211',
            name: '库存-财务核算',
            level: 'module',
            relationCodes: ['RS001', 'RS002']
          }
        ]
      },
      {
        id: 'internal-same-module',
        name: '同服务模块',
        children: [
          {
            id: 'internal-same-module-module-111-111',
            name: '库存-库存',
            level: 'module',
            relationCodes: ['RS003']
          }
        ]
      }
    ]
  },
  {
    id: 'cross-boundary',
    name: '范围内与外部',
    children: [
      {
        id: 'cross-boundary-cross-domain',
        name: '跨领域',
        children: [
          {
            id: 'cross-boundary-cross-domain-module-111-312',
            name: '库存-应收',
            level: 'module',
            relationCodes: ['RS004']
          }
        ]
      }
    ]
  }
]

describe('treeNodesToScope', () => {
  it('空 nodes 返回空 scope', () => {
    const result = treeNodesToScope([])
    expect(result).toEqual({ boIds: [], domainIds: [], subDomainIds: [], serviceModuleIds: [] })
  })

  it('单个 domain node 正确提取 domainId（原始 data 对象）', () => {
    const nodes = [{ id: 'd_1', originalId: 1, type: 'domain' }]
    const result = treeNodesToScope(nodes)
    expect(result.domainIds).toEqual([1])
    expect(result.subDomainIds).toEqual([])
    expect(result.serviceModuleIds).toEqual([])
  })

  it('多个不同类型 node 正确分类（原始 data 对象）', () => {
    const nodes = [
      { id: 'd_1', originalId: 1, type: 'domain' },
      { id: 's_11', originalId: 11, type: 'sub_domain' },
      { id: 'sm_111', originalId: 111, type: 'service_module' },
      { id: 's_12', originalId: 12, type: 'sub_domain' }
    ]
    const result = treeNodesToScope(nodes)
    expect(result.domainIds).toEqual([1])
    expect(result.subDomainIds).toEqual([11, 12])
    expect(result.serviceModuleIds).toEqual([111])
  })

  it('单个 domain node 正确提取 domainId（Element Plus Node 对象）', () => {
    const nodes = [{ id: 'd_1', data: { id: 'd_1', originalId: 1 }, type: 'domain' }]
    const result = treeNodesToScope(nodes)
    expect(result.domainIds).toEqual([1])
    expect(result.subDomainIds).toEqual([])
    expect(result.serviceModuleIds).toEqual([])
  })

  it('多个不同类型 node 正确分类（Element Plus Node 对象）', () => {
    const nodes = [
      { id: 'd_1', data: { id: 'd_1', originalId: 1 }, type: 'domain' },
      { id: 's_11', data: { id: 's_11', originalId: 11 }, type: 'sub_domain' },
      { id: 'sm_111', data: { id: 'sm_111', originalId: 111 }, type: 'service_module' },
      { id: 's_12', data: { id: 's_12', originalId: 12 }, type: 'sub_domain' }
    ]
    const result = treeNodesToScope(nodes)
    expect(result.domainIds).toEqual([1])
    expect(result.subDomainIds).toEqual([11, 12])
    expect(result.serviceModuleIds).toEqual([111])
  })

  it('node 缺少 originalId 时回退使用 id', () => {
    const nodes = [{ id: 'd_1', type: 'domain' }]
    const result = treeNodesToScope(nodes)
    expect(result.domainIds).toEqual(['d_1'])
  })

  it('不识别 type 的 node 被忽略', () => {
    const nodes = [{ id: 'x_1', type: 'unknown' }]
    const result = treeNodesToScope(nodes)
    expect(result).toEqual({ boIds: [], domainIds: [], subDomainIds: [], serviceModuleIds: [] })
  })
})

describe('scopeToNodeKeys', () => {
  it('空 scopeIds 返回空数组', () => {
    const result = scopeToNodeKeys(OBJECT_TREE_DATA, null)
    expect(result).toEqual([])
  })

  it('空 treeData 返回空数组', () => {
    const result = scopeToNodeKeys([], { domain: { selected: [1] } })
    expect(result).toEqual([])
  })

  it('selected 非空时优先使用 selected', () => {
    const scopeIds = {
      domain: { selected: [1], effective: [1, 2] }
    }
    const result = scopeToNodeKeys(OBJECT_TREE_DATA, scopeIds)
    expect(result).toContain('d_1')
    expect(result).not.toContain('d_2')
  })

  it('selected 为空时回退使用 effective', () => {
    const scopeIds = {
      sub_domain: { selected: [], effective: [11] }
    }
    const result = scopeToNodeKeys(OBJECT_TREE_DATA, scopeIds)
    expect(result).toContain('s_11')
    expect(result).not.toContain('s_12')
  })

  it('多类型同时设置返回全部匹配 node key', () => {
    const scopeIds = {
      domain: { selected: [1], effective: [] },
      sub_domain: { selected: [], effective: [21] },
      service_module: { selected: [121], effective: [] }
    }
    const result = scopeToNodeKeys(OBJECT_TREE_DATA, scopeIds)
    expect(result).toContain('d_1')
    expect(result).toContain('s_21')
    expect(result).toContain('sm_121')
    expect(result).not.toContain('d_2')
    expect(result).not.toContain('sm_111')
  })

  it('不存在的 type scope 不影响结果', () => {
    const scopeIds = {
      unknown_type: { selected: [999], effective: [] },
      domain: { selected: [2], effective: [] }
    }
    const result = scopeToNodeKeys(OBJECT_TREE_DATA, scopeIds)
    expect(result).toContain('d_2')
    expect(result).not.toContain('d_1')
  })

  it('scopeIds 中类型范围为 null/undefined 不报错', () => {
    const scopeIds = {
      domain: null,
      sub_domain: undefined,
      service_module: { selected: [111], effective: [] }
    }
    const result = scopeToNodeKeys(OBJECT_TREE_DATA, scopeIds)
    expect(result).toContain('sm_111')
  })
})

describe('nodeKeysToRelationCodes', () => {
  it('空 nodeKeys 返回空数组', () => {
    const result = nodeKeysToRelationCodes([], RELATION_TREE_DATA)
    expect(result).toEqual([])
  })

  it('空 treeData 返回空数组', () => {
    const result = nodeKeysToRelationCodes(['internal-same-module-module-111-111'], [])
    expect(result).toEqual([])
  })

  it('单个 module node 返回对应 relationCodes', () => {
    const result = nodeKeysToRelationCodes(
      ['internal-same-module-module-111-111'],
      RELATION_TREE_DATA
    )
    expect(result).toEqual(['RS003'])
  })

  it('多个 module node 返回合并去重的 relationCodes', () => {
    const result = nodeKeysToRelationCodes(
      ['internal-cross-domain-module-111-211', 'internal-same-module-module-111-111'],
      RELATION_TREE_DATA
    )
    expect(result.sort()).toEqual(['RS001', 'RS002', 'RS003'].sort())
  })

  it('不匹配的 nodeKey 返回空数组', () => {
    const result = nodeKeysToRelationCodes(['nonexistent'], RELATION_TREE_DATA)
    expect(result).toEqual([])
  })
})

describe('relationCodesToNodeKeys', () => {
  it('空 relationCodes 返回空数组', () => {
    const result = relationCodesToNodeKeys([], RELATION_TREE_DATA)
    expect(result).toEqual([])
  })

  it('空 treeData 返回空数组', () => {
    const result = relationCodesToNodeKeys(['RS001'], [])
    expect(result).toEqual([])
  })

  it('单个 relationCode 匹配到对应 module node', () => {
    const result = relationCodesToNodeKeys(['RS003'], RELATION_TREE_DATA)
    expect(result).toEqual(['internal-same-module-module-111-111'])
  })

  it('多个 relationCode 全部匹配才返回 node key', () => {
    const result = relationCodesToNodeKeys(['RS001', 'RS002'], RELATION_TREE_DATA)
    expect(result).toContain('internal-cross-domain-module-111-211')
  })

  it('部分匹配的 relationCode 不返回 node key', () => {
    const result = relationCodesToNodeKeys(['RS001'], RELATION_TREE_DATA)
    expect(result).not.toContain('internal-cross-domain-module-111-211')
  })

  it('多个 codes 匹配多个 nodes', () => {
    const result = relationCodesToNodeKeys(['RS003', 'RS004'], RELATION_TREE_DATA)
    expect(result.sort()).toEqual(
      ['internal-same-module-module-111-111', 'cross-boundary-cross-domain-module-111-312'].sort()
    )
  })

  it('不存在的 relationCode 不影响已匹配的 node', () => {
    const result = relationCodesToNodeKeys(['RS003', 'NONEXIST'], RELATION_TREE_DATA)
    expect(result).toContain('internal-same-module-module-111-111')
  })

  // OSS scope-change 不带 relationCodes 时，handleScopeChange 设置为 null
  // relationCodesToNodeKeys(null, treeData) 应返回 [] 而非报错
  it('null relationCodes 返回空数组（OSS 变更清空 RSS 勾选）', () => {
    const result = relationCodesToNodeKeys(null, RELATION_TREE_DATA)
    expect(result).toEqual([])
  })
})
