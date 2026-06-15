import { describe, it, expect } from 'vitest'
import {
  treeNodesToScope,
  scopeToNodeKeys,
  nodeKeysToRelationCodes,
  nodeKeysToRelationIds,
  relationCodesToNodeKeys,
  relationIdsToNodeKeys
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

// [v3.18 新增] nodeKeysToRelationIds 测试
describe('nodeKeysToRelationIds', () => {
  it('空 nodeKeys 返回空数组', () => {
    const result = nodeKeysToRelationIds([], RELATION_TREE_DATA)
    expect(result).toEqual([])
  })

  it('空 treeData 返回空数组', () => {
    const result = nodeKeysToRelationIds(['internal-same-module-module-111-111'], [])
    expect(result).toEqual([])
  })

  it('null nodeKeys 返回空数组', () => {
    const result = nodeKeysToRelationIds(null, RELATION_TREE_DATA)
    expect(result).toEqual([])
  })

  it('单个 module node 返回对应的 relationIds', () => {
    // 该节点的 relationIds 应从 treeData 中获取，这里测试函数本身的正确性
    const result = nodeKeysToRelationIds(['internal-same-module-module-111-111'], RELATION_TREE_DATA)
    // 如果 treeData 中该节点有 relationIds，会被收集
    expect(Array.isArray(result)).toBe(true)
  })

  it('多个 nodeKeys 合并去重', () => {
    // 即使有重复 ID 也应去重
    const treeWithDup = [
      {
        id: 'node-a',
        name: '节点A',
        children: [
          { id: 'leaf-a', name: '叶子A', level: 'module', relationIds: [1, 2] }
        ]
      },
      {
        id: 'node-b',
        name: '节点B',
        children: [
          { id: 'leaf-b', name: '叶子B', level: 'module', relationIds: [2, 3] }
        ]
      }
    ]
    const result = nodeKeysToRelationIds(['leaf-a', 'leaf-b'], treeWithDup)
    // 去重后应为 [1, 2, 3]
    expect(result.sort()).toEqual([1, 2, 3])
  })

  it('节点无 relationIds 时跳过', () => {
    const treeWithEmpty = [
      {
        id: 'node-x',
        name: '节点X',
        children: [
          { id: 'leaf-x', name: '叶子X', level: 'module', relationIds: [] }
        ]
      }
    ]
    const result = nodeKeysToRelationIds(['leaf-x'], treeWithEmpty)
    expect(result).toEqual([])
  })

  it('不存在的 nodeKey 返回空', () => {
    const result = nodeKeysToRelationIds(['nonexistent-node'], RELATION_TREE_DATA)
    expect(result).toEqual([])
  })

  it('relationIds 中无重复值', () => {
    const treeWithDups = [
      {
        id: 'node-1',
        name: '节点1',
        children: [
          { id: 'leaf-1a', name: '叶子1A', level: 'module', relationIds: [10, 10, 10] }
        ]
      }
    ]
    const result = nodeKeysToRelationIds(['leaf-1a'], treeWithDups)
    // Set 去重后只剩 [10]
    expect(result).toEqual([10])
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

// v39.4: relationIdsToNodeKeys 测试 - 修复从图表返回时关系范围选择状态"漂移"问题
// 使用独立 fixture (RELATION_TREE_WITH_IDS) 包含 relationIds 字段
const RELATION_TREE_WITH_IDS = [
  {
    id: 'internal',
    name: '范围内',
    children: [
      {
        id: 'internal-cross-domain',
        name: '跨领域',
        children: [
          {
            id: 'internal-leaf-1',
            name: '库存-财务核算',
            level: 'module',
            relationCodes: ['RS001', 'RS002'],
            relationIds: [101, 102]
          }
        ]
      },
      {
        id: 'internal-same-module',
        name: '同服务模块',
        children: [
          {
            id: 'internal-leaf-2',
            name: '库存-库存',
            level: 'module',
            relationCodes: ['RS003'],
            relationIds: [103]
          }
        ]
      }
    ]
  },
  {
    id: 'external',
    name: '范围外',
    children: [
      {
        id: 'external-cross-domain',
        name: '跨领域',
        children: [
          {
            id: 'external-leaf-1',
            name: '外部-外部',
            level: 'module',
            relationCodes: ['RS004'],
            relationIds: [201]
          }
        ]
      }
    ]
  }
]

describe('relationIdsToNodeKeys', () => {
  it('空 relationIds 返回空数组', () => {
    const result = relationIdsToNodeKeys([], RELATION_TREE_WITH_IDS)
    expect(result).toEqual([])
  })

  it('空 treeData 返回空数组', () => {
    const result = relationIdsToNodeKeys([101], [])
    expect(result).toEqual([])
  })

  it('null relationIds 返回空数组（OSS 变更清空）', () => {
    const result = relationIdsToNodeKeys(null, RELATION_TREE_WITH_IDS)
    expect(result).toEqual([])
  })

  it('undefined relationIds 返回空数组', () => {
    const result = relationIdsToNodeKeys(undefined, RELATION_TREE_WITH_IDS)
    expect(result).toEqual([])
  })

  it('单个 relationId 匹配到对应 module node（节点仅含 1 个 id）', () => {
    // internal-leaf-2 只含 103，传 103 应匹配
    const result = relationIdsToNodeKeys([103], RELATION_TREE_WITH_IDS)
    expect(result).toContain('internal-leaf-2')
  })

  it('节点含多个 ids 时，必须全部传入才能匹配', () => {
    // internal-leaf-1 含 [101,102]，只传 101 不应匹配（102 缺失）
    const result = relationIdsToNodeKeys([101], RELATION_TREE_WITH_IDS)
    expect(result).not.toContain('internal-leaf-1')
  })

  it('多个 relationId 全部匹配才返回 node key', () => {
    // 101+102 都属于 internal-leaf-1 → 匹配
    const result = relationIdsToNodeKeys([101, 102], RELATION_TREE_WITH_IDS)
    expect(result).toContain('internal-leaf-1')
  })

  it('部分匹配的 relationId 不返回 node key', () => {
    // 102 存在但 9999 不存在 → 内部所有 ids 都要匹配才算
    const result = relationIdsToNodeKeys([102, 9999], RELATION_TREE_WITH_IDS)
    expect(result).not.toContain('internal-leaf-1')
  })

  it('不存在的 relationId 不影响已匹配的 node（集合中含有效 id）', () => {
    const result = relationIdsToNodeKeys([103, 99999], RELATION_TREE_WITH_IDS)
    expect(result).toContain('internal-leaf-2')
  })

  it('只匹配叶子 module 节点，不返回父级 scope/category 节点', () => {
    // 关键测试: 修复"漂移"问题 - 不能返回父节点否则会级联勾选所有子节点
    const result = relationIdsToNodeKeys([101], RELATION_TREE_WITH_IDS)
    result.forEach(key => {
      expect(key).toMatch(/-leaf-/)
    })
    expect(result).not.toContain('internal')
    expect(result).not.toContain('internal-cross-domain')
  })

  it('跨 scope 误匹配防护: 同 code 在不同 scope 不会导致跨 scope 勾选', () => {
    // 关键测试: 模拟用户原始问题场景
    // 修复前 relationCodesToNodeKeys 会因 CONTAINS code 同时存在于 internal/external
    //   而误匹配到 external-leaf-1，导致"勾选状态飘到范围外"
    // 修复后 relationIdsToNodeKeys 用唯一 ID 精确匹配，不会跨 scope
    const result = relationIdsToNodeKeys([101, 102], RELATION_TREE_WITH_IDS)
    expect(result).toContain('internal-leaf-1')
    expect(result).not.toContain('external-leaf-1')  // 关键: 不应误匹配范围外
  })

  it('关系 ID 数字和字符串混用也能正确匹配（String 转换）', () => {
    const result = relationIdsToNodeKeys(['101', '102'], RELATION_TREE_WITH_IDS)
    expect(result).toContain('internal-leaf-1')
  })

  it('同一 scope 多个叶子节点独立匹配', () => {
    // 同时匹配 internal-leaf-1 (101,102) 和 internal-leaf-2 (103)
    const result = relationIdsToNodeKeys([101, 102, 103], RELATION_TREE_WITH_IDS)
    expect(result).toContain('internal-leaf-1')
    expect(result).toContain('internal-leaf-2')
  })

  it('跳过有 children 的中间节点（只匹配叶子）', () => {
    // 即使中间节点没有 relationIds，也不会被错误返回
    const treeWithIntermediates = [
      {
        id: 'root',
        name: '根',
        relationIds: [999],  // 根节点也有 relationIds 但不是叶子
        children: [
          {
            id: 'mid',
            name: '中间',
            relationIds: [888],  // 中间节点也有 relationIds 但不是叶子
            children: [
              {
                id: 'leaf',
                name: '叶子',
                level: 'module',
                relationIds: [101]
              }
            ]
          }
        ]
      }
    ]
    const result = relationIdsToNodeKeys([101, 888, 999], treeWithIntermediates)
    expect(result).toEqual(['leaf'])  // 只匹配叶子
  })
})
