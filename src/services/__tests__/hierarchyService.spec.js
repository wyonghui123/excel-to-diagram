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
