import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getLabel,
  getIcon,
  getChildType,
  getParentType,
  getLevelIndex,
  getFKField,
  isHierarchyType,
  hasChildren,
  buildHierarchyFilterParams,
  buildRelationshipFilterParams,
  buildAssociationFilterParams,
  getDescendantIds,
  collectIdsByTypeWithDescendants,
  collectAncestorIds,
  fetchHierarchyConfig,
  getHierarchyTree,
  getChildCount
} from '@/services/hierarchyService'

// mock httpClient
vi.mock('@/utils/httpClient', () => ({
  apiV1: {
    get: vi.fn()
  },
  apiV2: {
    get: vi.fn()
  }
}))

import { apiV1, apiV2 } from '@/utils/httpClient'

// 共享测试数据
const levels = [
  { object_type: 'product', label: '产品', icon: 'inventory_2', kind: 'entity' },
  { object_type: 'version', label: '版本', icon: 'tag', kind: 'entity' },
  { object_type: 'domain', label: '领域', icon: 'business', kind: 'entity', children_field: 'sub_domain_ids' },
  { object_type: 'sub_domain', label: '子领域', icon: 'account_tree', kind: 'entity', children_field: 'service_module_ids' },
  { object_type: 'service_module', label: '服务模块', icon: 'widgets', kind: 'entity', children_field: 'business_object_ids' },
  { object_type: 'business_object', label: '业务对象', icon: 'description', kind: 'entity' }
]

describe('getLabel', () => {
  it('应返回匹配层级的 label', () => {
    expect(getLabel(levels, 'domain')).toBe('领域')
    expect(getLabel(levels, 'service_module')).toBe('服务模块')
  })

  it('应回退到 display_name', () => {
    const customLevels = [{ object_type: 'test', display_name: '测试' }]
    expect(getLabel(customLevels, 'test')).toBe('测试')
  })

  it('应回退到 NON_HIERARCHY_LABELS', () => {
    expect(getLabel([], 'relationship')).toBe('关联关系')
  })

  it('无匹配时回退到 type 本身', () => {
    expect(getLabel([], 'unknown_type')).toBe('unknown_type')
  })
})

describe('getIcon', () => {
  it('应返回匹配层级的 icon', () => {
    expect(getIcon(levels, 'domain')).toBe('business')
    expect(getIcon(levels, 'product')).toBe('inventory_2')
  })

  it('应回退到 NON_HIERARCHY_ICONS', () => {
    expect(getIcon([], 'relationship')).toBe('Connection')
  })

  it('无匹配时回退到 Document', () => {
    expect(getIcon([], 'unknown_type')).toBe('Document')
  })
})

describe('getChildType', () => {
  it('应返回下一层级类型', () => {
    expect(getChildType(levels, 'domain')).toBe('sub_domain')
    expect(getChildType(levels, 'sub_domain')).toBe('service_module')
  })

  it('最后一层应返回 null', () => {
    expect(getChildType(levels, 'business_object')).toBeNull()
  })

  it('未找到类型应返回 null', () => {
    expect(getChildType(levels, 'nonexistent')).toBeNull()
  })
})

describe('getParentType', () => {
  it('应返回上一层类型', () => {
    expect(getParentType(levels, 'sub_domain')).toBe('domain')
    expect(getParentType(levels, 'business_object')).toBe('service_module')
  })

  it('第一层应返回 null', () => {
    expect(getParentType(levels, 'product')).toBeNull()
  })

  it('未找到类型应返回 null', () => {
    expect(getParentType(levels, 'nonexistent')).toBeNull()
  })
})

describe('getLevelIndex', () => {
  it('应返回正确的索引', () => {
    expect(getLevelIndex(levels, 'product')).toBe(0)
    expect(getLevelIndex(levels, 'domain')).toBe(2)
    expect(getLevelIndex(levels, 'business_object')).toBe(5)
  })

  it('未找到应返回 -1', () => {
    expect(getLevelIndex(levels, 'nonexistent')).toBe(-1)
  })
})

describe('getFKField', () => {
  it('应根据父类型推导 FK 字段名', () => {
    expect(getFKField(levels, 'version')).toBe('product_id')
    expect(getFKField(levels, 'domain')).toBe('version_id')
    expect(getFKField(levels, 'service_module')).toBe('sub_domain_id')
  })

  it('顶层类型无父级应返回 null', () => {
    expect(getFKField(levels, 'product')).toBeNull()
  })
})

describe('isHierarchyType', () => {
  it('index >= 2 应为层级类型', () => {
    expect(isHierarchyType(levels, 'domain')).toBe(true)
    expect(isHierarchyType(levels, 'sub_domain')).toBe(true)
    expect(isHierarchyType(levels, 'business_object')).toBe(true)
  })

  it('index < 2 不属于层级类型', () => {
    expect(isHierarchyType(levels, 'product')).toBe(false)
    expect(isHierarchyType(levels, 'version')).toBe(false)
  })

  it('未找到类型 (index = -1) 不属于层级类型', () => {
    expect(isHierarchyType(levels, 'unknown')).toBe(false)
  })
})

describe('hasChildren', () => {
  it('有 children_field 的类型应返回 true', () => {
    expect(hasChildren(levels, 'domain')).toBe(true)
    expect(hasChildren(levels, 'sub_domain')).toBe(true)
    expect(hasChildren(levels, 'service_module')).toBe(true)
  })

  it('无 children_field 的类型应返回 false', () => {
    expect(hasChildren(levels, 'product')).toBe(false)
    expect(hasChildren(levels, 'business_object')).toBe(false)
  })

  it('未找到类型应返回 false', () => {
    expect(hasChildren(levels, 'unknown')).toBe(false)
  })
})

describe('buildHierarchyFilterParams', () => {
  it('应使用 selected 构建 id__in', () => {
    const result = buildHierarchyFilterParams({
      levels,
      scopeIds: { domain: { selected: [1, 2], effective: [] } },
      objectType: 'domain'
    })
    expect(result.id__in).toBe('1,2')
  })

  it('selected 为空时应回退到 effective', () => {
    const result = buildHierarchyFilterParams({
      levels,
      scopeIds: { domain: { selected: [], effective: [3, 4] } },
      objectType: 'domain'
    })
    expect(result.id__in).toBe('3,4')
  })

  it('应添加父级 FK 回退过滤', () => {
    const result = buildHierarchyFilterParams({
      levels,
      scopeIds: {
        sub_domain: { selected: [], effective: [] },
        domain: { selected: [10, 20], effective: [] }
      },
      objectType: 'sub_domain'
    })
    expect(result.domain_id__in).toBe('10,20')
  })

  it('scopeIds 中无对应类型应返回空对象', () => {
    const result = buildHierarchyFilterParams({
      levels,
      scopeIds: {},
      objectType: 'domain'
    })
    expect(result).toEqual({})
  })
})

describe('buildRelationshipFilterParams', () => {
  it('应构建 relation_code__in 和 category_types__in', () => {
    const result = buildRelationshipFilterParams({
      relationCodes: ['R1', 'R2'],
      categoryTypes: ['C1'],
      filterRelationCodes: []
    })
    expect(result.relation_code__in).toBe('R1,R2')
    expect(result.category_types__in).toBe('C1')
  })

  it('filterRelationCodes 应与现有 relationCodes 取交集', () => {
    const result = buildRelationshipFilterParams({
      relationCodes: ['R1', 'R2', 'R3'],
      categoryTypes: [],
      filterRelationCodes: ['R2', 'R3', 'R4']
    })
    expect(result.relation_code__in).toBe('R2,R3')
  })

  it('filterRelationCodes 无交集时应删除 relation_code__in', () => {
    const result = buildRelationshipFilterParams({
      relationCodes: ['R1'],
      categoryTypes: [],
      filterRelationCodes: ['R2']
    })
    expect(result.relation_code__in).toBeUndefined()
  })

  it('relationCodes 为空时 filterRelationCodes 应直接作为 relation_code__in', () => {
    const result = buildRelationshipFilterParams({
      relationCodes: [],
      categoryTypes: [],
      filterRelationCodes: ['R5']
    })
    expect(result.relation_code__in).toBe('R5')
  })

  // [v3.18 新增] relationIds 优先逻辑
  it('relationIds 存在时应生成 id__in 而非 relation_code__in', () => {
    const result = buildRelationshipFilterParams({
      relationIds: [101, 102, 103],
      relationCodes: ['R1', 'R2'],
      categoryTypes: [],
      filterRelationCodes: []
    })
    // relationIds 有值时，优先用精确 ID 过滤
    expect(result.id__in).toBe('101,102,103')
    // relation_code__in 不应出现（被 relationIds 覆盖）
    expect(result.relation_code__in).toBeUndefined()
  })

  it('relationIds 和 relationCodes 同时存在时 relationIds 优先', () => {
    // 模拟"范围内"节点被勾选：树同时返回 codes 和 ids
    const result = buildRelationshipFilterParams({
      relationIds: [5, 6, 7],
      relationCodes: ['GENERATES', 'DEPENDS_ON'],
      categoryTypes: ['cross_domain'],
      filterRelationCodes: []
    })
    expect(result.id__in).toBe('5,6,7')
    expect(result.relation_code__in).toBeUndefined()
    expect(result.category_types__in).toBe('cross_domain')
  })

  it('relationIds 为空时应回退到 relationCodes', () => {
    const result = buildRelationshipFilterParams({
      relationIds: [],
      relationCodes: ['CALLS'],
      categoryTypes: [],
      filterRelationCodes: []
    })
    expect(result.id__in).toBeUndefined()
    expect(result.relation_code__in).toBe('CALLS')
  })

  it('relationIds 为 null/undefined 时应回退到 relationCodes', () => {
    const resultNull = buildRelationshipFilterParams({
      relationIds: null,
      relationCodes: ['CALLS'],
      categoryTypes: [],
      filterRelationCodes: []
    })
    expect(resultNull.relation_code__in).toBe('CALLS')

    const resultUndef = buildRelationshipFilterParams({
      relationIds: undefined,
      relationCodes: ['CALLS'],
      categoryTypes: [],
      filterRelationCodes: []
    })
    expect(resultUndef.relation_code__in).toBe('CALLS')
  })

  it('relationIds 为单元素数组时应生成逗号分隔的 id__in', () => {
    const result = buildRelationshipFilterParams({
      relationIds: [42],
      relationCodes: [],
      categoryTypes: [],
      filterRelationCodes: []
    })
    expect(result.id__in).toBe('42')
    expect(result.relation_code__in).toBeUndefined()
  })

  it('relationIds 单独存在时应只生成 id__in', () => {
    const result = buildRelationshipFilterParams({
      relationIds: [10, 20],
      relationCodes: [],
      categoryTypes: [],
      filterRelationCodes: []
    })
    expect(result.id__in).toBe('10,20')
    expect(Object.keys(result)).toHaveLength(1)
  })
})

// [FIX 2026-06-15] buildAssociationFilterParams 新增 filterRelationCodes 行为
describe('buildAssociationFilterParams', () => {
  // 模拟 hierarchies.yaml 的 relationships.filter_mappings (hierarchy_scopes[relationships].filter_mappings)
  const levels = [
    {
      object_type: 'relationship',
      filter_mappings: [
        { target_object: 'relationship', filter_field: 'relation_code', priority: 1, trigger: 'selected' },
        { target_object: 'relationship', filter_field: 'category_types', priority: 2, trigger: 'effective' },
        { target_object: 'relationship', filter_field: 'source_bo_id', priority: 3, trigger: 'entity_scope' },
        { target_object: 'relationship', filter_field: 'target_bo_id', priority: 3, trigger: 'entity_scope' }
      ]
    }
  ]

  it('relationIds 存在时应优先用 id__in 精确过滤', () => {
    const result = buildAssociationFilterParams({
      levels,
      scopeIds: {},
      relationExtra: {
        relationIds: [1, 2, 3],
        relationCodes: ['GENERATES'],
        categoryTypes: ['cross_domain'],
        filterRelationCodes: ['UPDATES']
      }
    })
    expect(result.id__in).toBe('1,2,3')
    // id__in 精确过滤命中, 其它过滤都被覆盖
    expect(result.relation_type__in).toBeUndefined()
  })

  it('relationCodes 选中时应映射到 relation_code__in', () => {
    const result = buildAssociationFilterParams({
      levels,
      scopeIds: {},
      relationExtra: {
        relationIds: [],
        relationCodes: ['GENERATES', 'UPDATES'],
        categoryTypes: [],
        filterRelationCodes: []
      }
    })
    expect(result.relation_code__in).toBe('GENERATES,UPDATES')
  })

  // [FIX 2026-06-15] 之前 mappings.length > 0 分支完全忽略 filterRelationCodes
  // 现在 filterRelationCodes 应映射到 relation_type__in, 让过滤面板的"关系类型"能真正过滤列表
  it('filterRelationCodes 应映射到 relation_type__in (用户报的核心 bug)', () => {
    const result = buildAssociationFilterParams({
      levels,
      scopeIds: {},
      relationExtra: {
        relationIds: [],
        relationCodes: [],
        categoryTypes: [],
        filterRelationCodes: ['GENERATES', 'UPDATES']
      }
    })
    expect(result.relation_type__in).toBe('GENERATES,UPDATES')
  })

  it('filterRelationCodes 与现有 relation_code__in 取并集', () => {
    const result = buildAssociationFilterParams({
      levels,
      scopeIds: {},
      relationExtra: {
        relationIds: [],
        relationCodes: ['GENERATES'],
        categoryTypes: [],
        filterRelationCodes: ['UPDATES', 'TRIGGERS']
      }
    })
    // relation_code__in (旧字段, 来自关系范围树) 跟 relation_type__in (新字段, 来自过滤面板) 并存
    expect(result.relation_code__in).toBe('GENERATES')
    expect(result.relation_type__in).toBe('UPDATES,TRIGGERS')
  })

  it('filterRelationCodes 应去重 (与现有合并后)', () => {
    const result = buildAssociationFilterParams({
      levels,
      scopeIds: {},
      relationExtra: {
        relationIds: [],
        relationCodes: ['GENERATES'],
        categoryTypes: [],
        filterRelationCodes: ['GENERATES', 'UPDATES']
      }
    })
    // 注: 这里 relation_code__in 和 relation_type__in 是不同字段, 所以不重复
    expect(result.relation_code__in).toBe('GENERATES')
    expect(result.relation_type__in).toBe('GENERATES,UPDATES')
  })

  it('应支持 source_bo_id / target_bo_id entity_scope 过滤', () => {
    // 关系定义 source_entity=business_object, target_entity=business_object
    const levelsWithEntity = [
      {
        object_type: 'relationship',
        source_entity: 'business_object',
        target_entity: 'business_object',
        filter_mappings: levels[0].filter_mappings
      }
    ]
    const result = buildAssociationFilterParams({
      levels: levelsWithEntity,
      scopeIds: {
        business_object: { selected: [10, 20], effective: [] }
      },
      relationExtra: {
        relationIds: [],
        relationCodes: [],
        categoryTypes: [],
        filterRelationCodes: []
      }
    })
    // 关系定义 source_entity=business_object, source_bo_id__in
    // 同样 target_bo_id__in
    expect(result.source_bo_id__in).toBe('10,20')
  })

  it('无 filter_mappings 时回退到 buildRelationshipFilterParams', () => {
    // buildRelationshipFilterParams 中:
    //   - filterRelationCodes 与 relationCodes 取交集
    //   - ['GENERATES'] ∩ ['UPDATES'] = [], 交集为空 → 删除 relation_code__in
    //   - 但 category_types__in 仍保留
    const result = buildAssociationFilterParams({
      levels: [{ object_type: 'relationship' }],
      scopeIds: {},
      relationExtra: {
        relationIds: [],
        relationCodes: ['GENERATES'],
        categoryTypes: ['cross_domain'],
        filterRelationCodes: ['UPDATES']
      }
    })
    expect(result.relation_code__in).toBeUndefined() // 交集为空
    expect(result.category_types__in).toBe('cross_domain')
  })

  it('无 filter_mappings 且 filterRelationCodes 与 relationCodes 有交集时, 应取交集', () => {
    const result = buildAssociationFilterParams({
      levels: [{ object_type: 'relationship' }],
      scopeIds: {},
      relationExtra: {
        relationIds: [],
        relationCodes: ['GENERATES', 'UPDATES'],
        categoryTypes: [],
        filterRelationCodes: ['UPDATES', 'TRIGGERS']
      }
    })
    // ['GENERATES', 'UPDATES'] ∩ ['UPDATES', 'TRIGGERS'] = ['UPDATES']
    expect(result.relation_code__in).toBe('UPDATES')
  })
})

describe('getDescendantIds', () => {
  it('应收集所有后代 ID', () => {
    const tree = {
      id: 1,
      children: [
        { id: 2, children: [{ id: 4 }] },
        { id: 3 }
      ]
    }
    expect(getDescendantIds(tree)).toEqual([2, 4, 3])
  })

  it('无 children 时应返回空数组', () => {
    expect(getDescendantIds({ id: 1 })).toEqual([])
    expect(getDescendantIds({ id: 1, children: [] })).toEqual([])
  })
})

describe('collectIdsByTypeWithDescendants', () => {
  const nodes = [
    {
      id: 1, type: 'domain', objectId: 'D1',
      children: [
        { id: 2, type: 'sub_domain', objectId: 'SD1' },
        { id: 3, type: 'service_module', objectId: 'SM1' }
      ]
    },
    {
      id: 4, type: 'domain', objectId: 'D2',
      children: [
        { id: 5, type: 'sub_domain', objectId: 'SD2' }
      ]
    }
  ]

  it('应收集选中节点及其后代中匹配类型的 ID', () => {
    const checkedSet = new Set([1])
    const result = collectIdsByTypeWithDescendants(nodes, checkedSet, 'sub_domain')
    expect(result).toContain('SD1')
  })

  it('未选中节点不应收集其后代', () => {
    const checkedSet = new Set([4])
    const result = collectIdsByTypeWithDescendants(nodes, checkedSet, 'service_module')
    expect(result).toEqual([])
  })

  it('应去重结果', () => {
    const flatNodes = [
      { id: 1, type: 'domain', objectId: 'D1', children: [] },
      { id: 2, type: 'domain', objectId: 'D1', children: [] }
    ]
    const checkedSet = new Set([1, 2])
    const result = collectIdsByTypeWithDescendants(flatNodes, checkedSet, 'domain')
    expect(result).toEqual(['D1'])
  })
})

describe('collectAncestorIds', () => {
  const treeData = [
    {
      id: 1, type: 'domain', objectId: 'D1',
      children: [
        {
          id: 2, type: 'sub_domain', objectId: 'SD1',
          children: [
            { id: 3, type: 'service_module', objectId: 'SM1', children: [] }
          ]
        }
      ]
    }
  ]

  it('应收集选中节点的父类型 ID', () => {
    const result = collectAncestorIds(levels, 'service_module', [3], treeData)
    expect(result).toContain('SD1')
  })

  it('顶层类型无父级应返回空数组', () => {
    const result = collectAncestorIds(levels, 'product', [1], treeData)
    expect(result).toEqual([])
  })

  it('应去重结果', () => {
    const result = collectAncestorIds(levels, 'sub_domain', [2], treeData)
    expect(result).toEqual(['D1'])
  })
})

describe('fetchHierarchyConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 重置模块级缓存 — 通过 re-import 或直接调用 forceRefresh
  })

  it('应调用 apiV1.get 获取配置', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: { dimensions: ['product'] } })
    const result = await fetchHierarchyConfig(true)
    expect(apiV1.get).toHaveBeenCalledWith('/meta/hierarchies/config')
    expect(result.dimensions).toContain('product')
  })

  it('API 失败时应返回回退配置', async () => {
    apiV1.get.mockRejectedValue(new Error('network error'))
    const result = await fetchHierarchyConfig(true)
    expect(result.dimensions).toBeDefined()
    expect(result.hierarchy_levels).toBeDefined()
  })

  it('应使用缓存（不传 forceRefresh）', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: { dimensions: ['cached'] } })
    await fetchHierarchyConfig(true) // 首次加载并缓存
    const result = await fetchHierarchyConfig(false) // 应使用缓存
    expect(apiV1.get).toHaveBeenCalledTimes(1)
    expect(result.dimensions).toContain('cached')
  })
})

describe('getHierarchyTree', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('应调用 apiV2.get 获取层级树', async () => {
    apiV2.get.mockResolvedValue({ data: [] })
    await getHierarchyTree('domain', { version_id: 1, include_counts: true })
    expect(apiV2.get).toHaveBeenCalledWith(
      '/meta/hierarchy/tree?version_id=1&include_counts=true'
    )
  })

  it('无参数时路径不含查询字符串', async () => {
    apiV2.get.mockResolvedValue({ data: [] })
    await getHierarchyTree('domain')
    expect(apiV2.get).toHaveBeenCalledWith('/meta/hierarchy/tree')
  })
})

describe('getChildCount', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('应调用 apiV2.get 获取子对象数量', async () => {
    apiV2.get.mockResolvedValue({ count: 5 })
    await getChildCount('domain', 10, { child_type: 'sub_domain' })
    expect(apiV2.get).toHaveBeenCalledWith(
      '/bo/domain/10/child-count?child_type=sub_domain'
    )
  })

  it('无 child_type 时路径不含查询字符串', async () => {
    apiV2.get.mockResolvedValue({ count: 0 })
    await getChildCount('domain', 10)
    expect(apiV2.get).toHaveBeenCalledWith('/bo/domain/10/child-count')
  })
})
