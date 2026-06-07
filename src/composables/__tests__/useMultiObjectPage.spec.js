import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, computed, reactive } from 'vue'

const mockScopeSource = reactive({
  source: { id: 'multi-object-scope' },
  setBusinessObjectIds: vi.fn(),
  setRelationCodes: vi.fn(),
  setRelationIds: vi.fn(),
  clear: vi.fn()
})

const mockContextSource = reactive({
  source: { id: 'version-context' },
  setContext: vi.fn(),
  clear: vi.fn()
})

const mockFilterFlowCombinedFilters = ref({ version_id: 1 })

vi.mock('../useVersionContext', () => ({
  useVersionContext: vi.fn(() => ({
    selectedVersionId: ref(1),
    selectedVersion: ref({ id: 1, name: 'V1.0', product_name: '产品A' }),
    selectedProductId: ref(1),
    versions: ref([{ id: 1, name: 'V1.0', product_name: '产品A' }]),
    hasContext: ref(true),
    selectVersion: vi.fn(),
    clearContext: vi.fn()
  }))
}))

vi.mock('../useFilterFlow', () => ({
  useFilterFlow: vi.fn(() => ({
    combinedFilters: mockFilterFlowCombinedFilters,
    registerSource: vi.fn(),
    unregisterSource: vi.fn(),
    refresh: vi.fn()
  }))
}))

vi.mock('../filterSources/useContextFilterSource', () => ({
  useContextFilterSource: vi.fn(() => mockContextSource)
}))

vi.mock('../filterSources/useScopeFilterSource', () => ({
  useScopeFilterSource: vi.fn(() => mockScopeSource)
}))

const mockHierarchyLabels = {
  domain: '领域',
  sub_domain: '子领域',
  service_module: '服务模块',
  business_object: '业务对象',
  relationship: '关系'
}
const mockHierarchyIcons = {
  domain: 'Folder',
  sub_domain: 'FolderOpened',
  service_module: 'Widgets',
  business_object: 'Description',
  relationship: 'Connection'
}

// Mock levels 数据（供 hierarchyService 纯函数使用）
const mockLevels = [
  { object_type: 'product', label: '产品', children_field: 'versions', kind: 'entity' },
  { object_type: 'version', label: '版本', children_field: 'domains', kind: 'entity' },
  { object_type: 'domain', label: '领域', children_field: 'sub_domains', kind: 'entity' },
  { object_type: 'sub_domain', label: '子领域', children_field: 'service_modules', kind: 'entity' },
  { object_type: 'service_module', label: '服务模块', children_field: 'business_objects', kind: 'entity' },
  { object_type: 'business_object', label: '业务对象', kind: 'entity' },
  { object_type: 'relationship', label: '关系', kind: 'association', source_entity: 'business_object', target_entity: 'business_object' }
]

const mockGetParentType = vi.fn()
const mockGetLevelIndex = vi.fn()
const mockIsEntity = vi.fn()
const mockIsAssociation = vi.fn()
const mockGetFilterMappings = vi.fn()
const mockFindLevel = vi.fn()

vi.mock('../useHierarchyTypes', () => ({
  useHierarchyTypes: vi.fn(() => ({
    getLabel: vi.fn(type => mockHierarchyLabels[type] || type),
    getIcon: vi.fn(type => mockHierarchyIcons[type] || null),
    getParentType: mockGetParentType,
    getChildType: vi.fn(),
    getLevelIndex: mockGetLevelIndex,
    hasChildren: vi.fn(),
    isEntity: mockIsEntity,
    isAssociation: mockIsAssociation,
    getFilterMappings: mockGetFilterMappings,
    findLevel: mockFindLevel,
    levels: { value: mockLevels }
  })),
  isHierarchyType: vi.fn(() => true)
}))

// Mock hierarchyService — FR-UI-010 后 useMultiObjectPage 直接调用 hierarchyService 纯函数
vi.mock('@/services/hierarchyService', () => {
  const mockLabels = { domain: '领域', sub_domain: '子领域', service_module: '服务模块', business_object: '业务对象', relationship: '关系' }
  const mockIcons = { domain: 'Folder', sub_domain: 'FolderOpened', service_module: 'Widgets', business_object: 'Description', relationship: 'Connection' }
  const findLvl = (levels, type) => levels.find(l => (l.object_type || l.object) === type)
  const idxOf = (levels, type) => levels.findIndex(l => (l.object_type || l.object) === type)

  return {
    getLabel: vi.fn((levels, type) => findLvl(levels, type)?.label || mockLabels[type] || type),
    getIcon: vi.fn((levels, type) => findLvl(levels, type)?.icon || mockIcons[type] || 'Document'),
    getParentType: vi.fn((levels, type) => { const i = idxOf(levels, type); return i > 0 ? levels[i - 1]?.object_type : null }),
    getChildType: vi.fn(),
    getLevelIndex: vi.fn((levels, type) => idxOf(levels, type)),
    getFKField: vi.fn((levels, type) => { const p = idxOf(levels, type) > 0 ? levels[idxOf(levels, type) - 1]?.object_type : null; return p ? `${p}_id` : null }),
    isHierarchyType: vi.fn((levels, type) => idxOf(levels, type) >= 2),
    hasChildren: vi.fn((levels, type) => !!findLvl(levels, type)?.children_field),
    findLevel: vi.fn((levels, objectType) => findLvl(levels, objectType)),
    getKind: vi.fn((levels, objectType) => findLvl(levels, objectType)?.kind || null),
    isEntity: vi.fn((levels, objectType) => findLvl(levels, objectType)?.kind === 'entity'),
    isAssociation: vi.fn((levels, objectType) => findLvl(levels, objectType)?.kind === 'association'),
    getFilterMappings: vi.fn((levels, objectType) => findLvl(levels, objectType)?.filter_mappings || []),
    getTypesBetween: vi.fn(),
    buildHierarchyFilterParams: vi.fn(({ levels: lvls, scopeIds, objectType }) => {
      const filters = {}
      const typeScope = scopeIds[objectType]
      if (!typeScope) return filters
      if (typeScope.selected.length > 0) filters.id__in = typeScope.selected.join(',')
      else if (typeScope.effective.length > 0) filters.id__in = typeScope.effective.join(',')
      const pIdx = idxOf(lvls, objectType)
      const parentType = pIdx > 0 ? lvls[pIdx - 1]?.object_type : null
      if (parentType && scopeIds[parentType]) {
        const ps = scopeIds[parentType]
        const pids = ps.selected.length > 0 ? ps.selected : ps.effective.length > 0 ? ps.effective : []
        if (pids.length > 0) { const fk = `${parentType}_id`; filters[`${fk}__in`] = pids.join(',') }
      }
      return filters
    }),
    buildRelationshipFilterParams: vi.fn((extra) => {
      const f = {}
      if (extra.relationCodes.length > 0) f.relation_code__in = extra.relationCodes.join(',')
      if (extra.categoryTypes.length > 0) f.category_types__in = extra.categoryTypes.join(',')
      if (extra.filterRelationCodes.length > 0) {
        const ex = f.relation_code__in ? f.relation_code__in.split(',') : []
        const cb = ex.length > 0 ? ex.filter(r => extra.filterRelationCodes.includes(r)) : extra.filterRelationCodes
        if (cb.length > 0) f.relation_code__in = cb.join(',')
        else delete f.relation_code__in
      }
      return f
    }),
    buildAssociationFilterParams: vi.fn(({ levels: lvls, scopeIds, relationExtra }) => {
      const f = {}
      const mappings = findLvl(lvls, 'relationship')?.filter_mappings || []
      if (relationExtra.relationIds?.length > 0) { f.id__in = relationExtra.relationIds.join(',') }
      else if (mappings.length === 0) {
        // 匹配真实实现：无 filter_mappings 时回退到 buildRelationshipFilterParams
        const rf = {}
        if (relationExtra.relationCodes.length > 0) rf.relation_code__in = relationExtra.relationCodes.join(',')
        if (relationExtra.categoryTypes.length > 0) rf.category_types__in = relationExtra.categoryTypes.join(',')
        if (relationExtra.filterRelationCodes.length > 0) {
          const ex = rf.relation_code__in ? rf.relation_code__in.split(',') : []
          const cb = ex.length > 0 ? ex.filter(r => relationExtra.filterRelationCodes.includes(r)) : relationExtra.filterRelationCodes
          if (cb.length > 0) rf.relation_code__in = cb.join(',')
          else delete rf.relation_code__in
        }
        return rf
      } else {
        const sorted = [...mappings].sort((a, b) => (a.priority || 99) - (b.priority || 99))
        for (const m of sorted) {
          if (m.trigger === 'selected' || m.trigger === 'effective') {
            let key = m.filter_field === 'relation_code' ? 'relationCodes' : m.filter_field === 'category_types' ? 'categoryTypes' : null
            if (key && relationExtra[key]?.length > 0) f[`${m.filter_field}__in`] = relationExtra[key].join(',')
          }
        }
      }
      const sm = mappings.find(m => m.filter_field === 'source_bo_id')
      const tm = mappings.find(m => m.filter_field === 'target_bo_id')
      if (sm?.trigger === 'entity_scope') {
        const se = findLvl(lvls, 'relationship')?.source_entity
        if (se && scopeIds[se]) { const s = scopeIds[se]; const ids = s.selected.length > 0 ? s.selected : s.effective; if (ids.length > 0) f.source_bo_id__in = ids.join(',') }
      }
      if (tm?.trigger === 'entity_scope') {
        const te = findLvl(lvls, 'relationship')?.target_entity
        if (te && scopeIds[te]) { const s = scopeIds[te]; const ids = s.selected.length > 0 ? s.selected : s.effective; if (ids.length > 0) f.target_bo_id__in = ids.join(',') }
      }
      return f
    }),
    fetchHierarchyConfig: vi.fn(),
    getFallbackConfig: vi.fn(),
    getHierarchyTree: vi.fn(),
    getChildCount: vi.fn(),
    getObjectPath: vi.fn(),
    getDescendantIds: vi.fn(),
    collectIdsByTypeWithDescendants: vi.fn(),
    collectAncestorIds: vi.fn(),
    getHierarchyDepth: vi.fn()
  }
})

import { useMultiObjectPage } from '../useMultiObjectPage'

const DEFAULT_OBJECT_TYPES = ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']

function createComposable(objectTypes = DEFAULT_OBJECT_TYPES, config = {}) {
  return useMultiObjectPage(objectTypes, config)
}

describe('useMultiObjectPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockFilterFlowCombinedFilters.value = { version_id: 1 }
    mockGetParentType.mockImplementation(type => {
      const map = { domain: 'version', sub_domain: 'domain', service_module: 'sub_domain', business_object: 'service_module' }
      return map[type] || null
    })
    mockGetLevelIndex.mockImplementation(type => {
      const indexMap = { product: 0, version: 1, domain: 2, sub_domain: 3, service_module: 4, business_object: 5 }
      return indexMap[type] ?? -1
    })
    mockIsEntity.mockImplementation(type => type !== 'relationship')
    mockIsAssociation.mockImplementation(type => type === 'relationship')
    mockGetFilterMappings.mockReturnValue([])
    mockFindLevel.mockReturnValue(undefined)
  })

  describe('初始状态 & Tabs 自动生成', () => {
    it('应该接受 objectTypes 数组作为输入', () => {
      const page = createComposable()
      expect(page.tabs).toBeDefined()
      expect(page.tabs.value).toHaveLength(5)
    })

    it('应该自动生成 5 个 Tab', () => {
      const page = createComposable()
      const tabNames = page.tabs.value.map(t => t.name)
      expect(tabNames).toEqual(['domain', 'sub_domain', 'service_module', 'business_object', 'relationship'])
    })

    it('每个 Tab 应该包含 name、label、icon', () => {
      const page = createComposable()
      for (const tab of page.tabs.value) {
        expect(tab).toHaveProperty('name')
        expect(tab).toHaveProperty('label')
        expect(tab).toHaveProperty('icon')
      }
    })

    it('应该使用 config.defaultTab 作为默认激活 Tab', () => {
      const page = createComposable(DEFAULT_OBJECT_TYPES, { defaultTab: 'domain' })
      expect(page.activeTab.value).toBe('domain')
    })

    it('没有 config.defaultTab 时应使用第一个 objectType', () => {
      const page = createComposable()
      expect(page.activeTab.value).toBe('domain')
    })

    it('scopeIds 应该初始化为空', () => {
      const page = createComposable()
      expect(page.scopeIds.domain.selected).toEqual([])
      expect(page.scopeIds.domain.effective).toEqual([])
      expect(page.scopeIds.sub_domain.selected).toEqual([])
      expect(page.scopeIds.sub_domain.effective).toEqual([])
      expect(page.scopeIds.service_module.selected).toEqual([])
      expect(page.scopeIds.service_module.effective).toEqual([])
      expect(page.scopeIds.business_object.selected).toEqual([])
      expect(page.scopeIds.business_object.effective).toEqual([])
      expect(page.scopeIds.globalFilters).toEqual({})
      expect(page.scopeIds.relationExtra.relationCodes).toEqual([])
      expect(page.scopeIds.relationExtra.categoryTypes).toEqual([])
      expect(page.scopeIds.relationExtra.filterRelationCodes).toEqual([])
    })

    it('hasScopeSelection 初始应为 false', () => {
      const page = createComposable()
      expect(page.hasScopeSelection.value).toBe(false)
    })
  })

  describe('combinedFilters - 基础行为', () => {
    it('应该从 filterFlow.combinedFilters 中获取基础过滤', () => {
      const page = createComposable()
      expect(page.combinedFilters.value).toHaveProperty('version_id', 1)
    })

    it('没有 scope 选择时应只包含基础过滤', () => {
      const page = createComposable()
      const filters = page.combinedFilters.value
      expect(Object.keys(filters)).toContain('version_id')
    })
  })

  describe('combinedFilters - 全局过滤 (annotation_category)', () => {
    it('应该对所有 Tab 添加 annotation_category__in 过滤', () => {
      const page = createComposable()
      page.scopeIds.globalFilters = { annotation_category: ['bug', 'todo'] }

      page.activeTab.value = 'domain'
      expect(page.combinedFilters.value.annotation_category__in).toBe('bug,todo')

      page.activeTab.value = 'business_object'
      expect(page.combinedFilters.value.annotation_category__in).toBe('bug,todo')

      page.activeTab.value = 'relationship'
      expect(page.combinedFilters.value.annotation_category__in).toBe('bug,todo')
    })

    it('globalFilters 为空时不应添加该过滤', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'
      expect(page.combinedFilters.value).not.toHaveProperty('annotation_category__in')
    })
  })

  describe('combinedFilters - 关系 Tab 过滤', () => {
    it('应该添加 relation_code__in 过滤', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON', 'CALLS']

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON,CALLS')
    })

    it('应该添加 category_types__in 过滤', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.categoryTypes = ['cross_domain', 'same_module']

      expect(page.combinedFilters.value.category_types__in).toBe('cross_domain,same_module')
    })

    it('filterRelationCodes 与 relation_code__in 做 intersection merge', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON', 'CALLS', 'DATA_FLOW']
      page.scopeIds.relationExtra.filterRelationCodes = ['DEPENDS_ON', 'DATA_FLOW']

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON,DATA_FLOW')
    })

    it('filterRelationCodes 没有 relationCodes 时应直接用 filterRelationCodes', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = []
      page.scopeIds.relationExtra.filterRelationCodes = ['DEPENDS_ON']

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON')
    })

    it('filterRelationCodes 为空时不应影响 relation_code__in', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON', 'CALLS']
      page.scopeIds.relationExtra.filterRelationCodes = []

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON,CALLS')
    })

    it('filterRelationCodes 有交集为空 -> 不设置 relation_code__in', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['CALLS']
      page.scopeIds.relationExtra.filterRelationCodes = ['DEPENDS_ON']

      expect(page.combinedFilters.value.relation_code__in).toBeUndefined()
    })

    it('关系 Tab 不应有层级过滤', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.domain.effective = [1, 2]

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
      expect(page.combinedFilters.value).not.toHaveProperty('service_module_id__in')
    })

    it('同时有全局过滤 + 关系过滤 + category 过滤', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.globalFilters = { annotation_category: ['bug'] }
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON', 'CALLS']
      page.scopeIds.relationExtra.categoryTypes = ['cross_domain']

      const filters = page.combinedFilters.value
      expect(filters.annotation_category__in).toBe('bug')
      expect(filters.relation_code__in).toBe('DEPENDS_ON,CALLS')
      expect(filters.category_types__in).toBe('cross_domain')
      expect(filters).toHaveProperty('version_id', 1)
    })

    it('relation_codes 为空时不应添加 relation_code__in', () => {
      const page = createComposable()
      page.activeTab.value = 'relationship'

      expect(page.combinedFilters.value).not.toHaveProperty('relation_code__in')
    })
  })

  describe('combinedFilters - 层级对象 Tab 过滤 (元数据驱动)', () => {
    it('domain Tab: effective → id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'
      page.scopeIds.domain.effective = [1, 2, 3]

      expect(page.combinedFilters.value.id__in).toBe('1,2,3')
    })

    it('domain Tab: selected → id__in (优先于 effective)', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'
      page.scopeIds.domain.selected = [4, 5]
      page.scopeIds.domain.effective = [1, 2, 3]

      expect(page.combinedFilters.value.id__in).toBe('4,5')
    })

    it('domain Tab: 无选择时不应有 id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })

    it('sub_domain Tab: effective → id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'sub_domain'
      page.scopeIds.sub_domain.effective = [10, 20]

      expect(page.combinedFilters.value.id__in).toBe('10,20')
    })

    it('sub_domain Tab: 无选择时不应有 id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'sub_domain'

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })

    it('service_module Tab: selected → id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'service_module'
      page.scopeIds.service_module.selected = [5, 6]

      expect(page.combinedFilters.value.id__in).toBe('5,6')
    })

    it('service_module Tab: 无选择时不应有 id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'service_module'

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })

    it('business_object Tab: selected (boIds) → id__in（selected 优先，不管 parent 状态）', () => {
      const page = createComposable()
      page.activeTab.value = 'business_object'
      page.scopeIds.business_object.selected = [10, 20]
      page.scopeIds.service_module.selected = [5, 6]

      expect(page.combinedFilters.value.id__in).toBe('10,20')
      expect(page.combinedFilters.value).not.toHaveProperty('service_module_id__in')
    })

    it('business_object Tab: 无 selected 时 parent selected → FK__in', () => {
      const page = createComposable()
      page.activeTab.value = 'business_object'
      page.scopeIds.service_module.selected = [5, 6]

      expect(page.combinedFilters.value.service_module_id__in).toBe('5,6')
    })

    it('business_object Tab: 无选择时不应有 id__in 或 service_module_id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'business_object'

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
      expect(page.combinedFilters.value).not.toHaveProperty('service_module_id__in')
    })

    it('层级 Tab 同时有全局过滤 + 层级过滤', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'
      page.scopeIds.globalFilters = { annotation_category: ['bug'] }
      page.scopeIds.domain.effective = [1, 2]

      const filters = page.combinedFilters.value
      expect(filters.annotation_category__in).toBe('bug')
      expect(filters.id__in).toBe('1,2')
      expect(filters).toHaveProperty('version_id', 1)
    })
  })

  describe('combinedFilters - association filter (entity_scope)', () => {
    it('object scope selected → source_bo_id__in + target_bo_id__in', () => {
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origMappings = relLevel.filter_mappings
      const origSource = relLevel.source_entity
      const origTarget = relLevel.target_entity
      relLevel.filter_mappings = [
        { filter_field: 'relation_code', priority: 1, trigger: 'selected' },
        { filter_field: 'category_types', priority: 2, trigger: 'effective' },
        { filter_field: 'source_bo_id', priority: 3, trigger: 'entity_scope' },
        { filter_field: 'target_bo_id', priority: 3, trigger: 'entity_scope' }
      ]
      relLevel.source_entity = 'business_object'
      relLevel.target_entity = 'business_object'

      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.business_object.selected = [10, 20]

      expect(page.combinedFilters.value.source_bo_id__in).toBe('10,20')
      expect(page.combinedFilters.value.target_bo_id__in).toBe('10,20')

      relLevel.filter_mappings = origMappings
      relLevel.source_entity = origSource
      relLevel.target_entity = origTarget
    })

    it('relation_code selected 与 entity_scope 同时生效', () => {
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origMappings = relLevel.filter_mappings
      const origSource = relLevel.source_entity
      const origTarget = relLevel.target_entity
      relLevel.filter_mappings = [
        { filter_field: 'relation_code', priority: 1, trigger: 'selected' },
        { filter_field: 'category_types', priority: 2, trigger: 'effective' },
        { filter_field: 'source_bo_id', priority: 3, trigger: 'entity_scope' },
        { filter_field: 'target_bo_id', priority: 3, trigger: 'entity_scope' }
      ]
      relLevel.source_entity = 'business_object'
      relLevel.target_entity = 'business_object'

      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON']
      page.scopeIds.business_object.selected = [10, 20]

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON')
      expect(page.combinedFilters.value.source_bo_id__in).toBe('10,20')
      expect(page.combinedFilters.value.target_bo_id__in).toBe('10,20')

      relLevel.filter_mappings = origMappings
      relLevel.source_entity = origSource
      relLevel.target_entity = origTarget
    })

    it('business_object effective 回退到 source_bo_id__in', () => {
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origMappings = relLevel.filter_mappings
      const origSource = relLevel.source_entity
      const origTarget = relLevel.target_entity
      relLevel.filter_mappings = [
        { filter_field: 'source_bo_id', priority: 3, trigger: 'entity_scope' },
        { filter_field: 'target_bo_id', priority: 3, trigger: 'entity_scope' }
      ]
      relLevel.source_entity = 'business_object'
      relLevel.target_entity = 'business_object'

      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.business_object.selected = []
      page.scopeIds.business_object.effective = [1, 2]

      expect(page.combinedFilters.value.source_bo_id__in).toBe('1,2')
      expect(page.combinedFilters.value.target_bo_id__in).toBe('1,2')

      relLevel.filter_mappings = origMappings
      relLevel.source_entity = origSource
      relLevel.target_entity = origTarget
    })

    it('无 filter_mappings 时回退到 _buildRelationshipFilters', () => {
      // mockLevels relationship 已无 filter_mappings，hierarchyService.getFilterMappings 返回 []
      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON']

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON')
      expect(page.combinedFilters.value).not.toHaveProperty('source_bo_id__in')
    })
  })

  describe('scopeIds - 边界情况', () => {
    it('domain.effective 为空不应有 id__in（即使有 service_module 选择）', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'
      page.scopeIds.service_module.selected = [5]

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })

    it('仅 service_module.selected 对 domain Tab 不生效', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'
      page.scopeIds.service_module.selected = [5]

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
      expect(page.combinedFilters.value).not.toHaveProperty('service_module_id__in')
    })
  })

  describe('handleScopeChange', () => {
    it('应该同步 scopeIds 和 scopeSource', () => {
      const page = createComposable()
      const scope = {
        boIds: [1, 2],
        relationCodes: ['R1'],
        categoryTypes: ['cross_domain'],
        selectedDomainIds: [10],
        selectedSubDomainIds: [20],
        selectedServiceModuleIds: [30],
        effectiveDomainIds: [1, 2, 10],
        effectiveSubDomainIds: [20],
        annotationCategories: ['bug'],
        filterRelationCodes: ['R2']
      }

      page.handleScopeChange(scope)

      expect(page.scopeIds.business_object.selected).toEqual([1, 2])
      expect(page.scopeIds.relationExtra.relationCodes).toEqual(['R1'])
      expect(page.scopeIds.domain.selected).toEqual([10])
      expect(page.scopeIds.domain.effective).toEqual([1, 2, 10])
      expect(page.scopeIds.globalFilters.annotation_category).toEqual(['bug'])
      expect(page.scopeIds.relationExtra.filterRelationCodes).toEqual(['R2'])
    })

    it('scope 字段缺失时应使用空数组默认值', () => {
      const page = createComposable()
      page.scopeIds.business_object.selected = [1, 2]
      page.scopeIds.relationExtra.relationCodes = ['R1']

      page.handleScopeChange({})

      expect(page.scopeIds.business_object.selected).toEqual([])
      expect(page.scopeIds.relationExtra.relationCodes).toEqual([])
      expect(page.scopeIds.domain.effective).toEqual([])
    })

    it('应该调用 scopeSource.setBusinessObjectIds', () => {
      const page = createComposable()
      page.handleScopeChange({ boIds: [1, 2] })

      expect(mockScopeSource.setBusinessObjectIds).toHaveBeenCalledWith([1, 2])
    })

    it('应该调用 scopeSource.setRelationCodes', () => {
      const page = createComposable()
      page.handleScopeChange({ relationCodes: ['R1'] })

      expect(mockScopeSource.setRelationCodes).toHaveBeenCalledWith(['R1'])
    })
  })

  describe('clearScope', () => {
    it('应该重置所有 scopeIds 字段', () => {
      const page = createComposable()
      page.scopeIds.business_object.selected = [1, 2]
      page.scopeIds.relationExtra.relationCodes = ['R1']
      page.scopeIds.domain.effective = [10]
      page.scopeIds.globalFilters = { annotation_category: ['bug'] }

      page.clearScope()

      expect(page.scopeIds.business_object.selected).toEqual([])
      expect(page.scopeIds.relationExtra.relationCodes).toEqual([])
      expect(page.scopeIds.domain.effective).toEqual([])
      expect(page.scopeIds.globalFilters).toEqual({})
    })

    it('应该调用 scopeSource.clear()', () => {
      const page = createComposable()
      page.clearScope()
      expect(mockScopeSource.clear).toHaveBeenCalled()
    })
  })

  describe('handleToolbarChange', () => {
    it('应该选择版本并清空 scope', () => {
      const page = createComposable()
      page.scopeIds.business_object.selected = [1, 2]

      page.handleToolbarChange({ versionId: 1 })

      expect(page.scopeIds.business_object.selected).toEqual([])
    })

    it('应该重置 activeTab 为 defaultTab', () => {
      const page = createComposable(DEFAULT_OBJECT_TYPES, { defaultTab: 'relationship' })
      page.activeTab.value = 'domain'

      page.handleToolbarChange({ versionId: 1 })

      expect(page.activeTab.value).toBe('relationship')
    })

    it('versionId 为 null 时应该取消选择版本', () => {
      const page = createComposable()
      page.handleToolbarChange({ versionId: null })

      expect(page.scopeIds.business_object.selected).toEqual([])
    })
  })

  describe('activeTab 切换', () => {
    it('切换 Tab 时 combinedFilters 应该更新', () => {
      const page = createComposable()
      page.scopeIds.domain.effective = [1, 2]
      page.scopeIds.service_module.selected = [5]
      page.activeTab.value = 'domain'

      expect(page.combinedFilters.value.id__in).toBe('1,2')
      expect(page.combinedFilters.value).not.toHaveProperty('service_module_id__in')

      page.activeTab.value = 'business_object'

      expect(page.combinedFilters.value.service_module_id__in).toBe('5')
    })

    it('切换 Tab 时全局过滤应该保持', () => {
      const page = createComposable()
      page.scopeIds.globalFilters = { annotation_category: ['bug'] }

      page.activeTab.value = 'domain'
      expect(page.combinedFilters.value.annotation_category__in).toBe('bug')

      page.activeTab.value = 'relationship'
      expect(page.combinedFilters.value.annotation_category__in).toBe('bug')
    })
  })

  describe('hasScopeSelection', () => {
    it('有 business_object.selected 时应该为 true', () => {
      const page = createComposable()
      page.scopeIds.business_object.selected = [1]
      expect(page.hasScopeSelection.value).toBe(true)
    })

    it('有 domain.effective 时应该为 true', () => {
      const page = createComposable()
      page.scopeIds.domain.effective = [1]
      expect(page.hasScopeSelection.value).toBe(true)
    })

    it('有 relationCodes 时应该为 true', () => {
      const page = createComposable()
      page.scopeIds.relationExtra.relationCodes = ['R1']
      expect(page.hasScopeSelection.value).toBe(true)
    })

    it('全部为空时应该为 false', () => {
      const page = createComposable()
      expect(page.hasScopeSelection.value).toBe(false)
    })
  })

  describe('元数据驱动 - 通用性', () => {
    it('只传入层级类型也能正常工作', () => {
      const page = createComposable(['domain', 'sub_domain'])
      expect(page.tabs.value).toHaveLength(2)
      expect(page.tabs.value[0].name).toBe('domain')
      expect(page.tabs.value[1].name).toBe('sub_domain')
    })

    it('只传入 relationship 也能正常工作', () => {
      const page = createComposable(['relationship'])
      expect(page.tabs.value).toHaveLength(1)
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['R1']
      expect(page.combinedFilters.value.relation_code__in).toBe('R1')
    })

    it('config.customFilterBuilders 支持自定义对象类型', () => {
      const customBuilder = vi.fn((filters, ids) => {
        if (ids.custom_type?.selected.length > 0) {
          filters.custom_field__in = ids.custom_type.selected.join(',')
        }
        return filters
      })
      const page = createComposable(['custom_type'], {
        customFilterBuilders: { custom_type: customBuilder }
      })
      page.scopeIds.custom_type = { selected: ['a', 'b'], effective: [] }
      page.activeTab.value = 'custom_type'

      const filters = page.combinedFilters.value
      expect(customBuilder).toHaveBeenCalled()
      expect(filters.custom_field__in).toBe('a,b')
    })

    it('customFilterBuilders 优先于 isEntity/isAssociation', () => {
      const customBuilder = vi.fn((filters, ids) => {
        if (ids.business_object?.selected.length > 0) {
          filters.override__in = ids.business_object.selected.join(',')
        }
        return filters
      })
      const page = createComposable(['business_object'], {
        customFilterBuilders: { business_object: customBuilder }
      })
      page.scopeIds.business_object.selected = [10, 20]
      page.activeTab.value = 'business_object'

      expect(page.combinedFilters.value.override__in).toBe('10,20')
      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })
  })

  describe('tabFilters — precompute 所有 Tab', () => {
    it('应该 precompute 所有 objectType 的过滤 delta', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [1, 2]
      page.scopeIds.service_module.selected = [5, 6]

      const tf = page.tabFilters.value
      expect(tf).toHaveProperty('domain')
      expect(tf).toHaveProperty('sub_domain')
      expect(tf).toHaveProperty('service_module')
      expect(tf).toHaveProperty('business_object')
      expect(tf).toHaveProperty('relationship')

      expect(tf.domain.id__in).toBe('1,2')
      expect(tf.service_module.id__in).toBe('5,6')
    })

    it('非 activeTab 的过滤 delta 应已预计算', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [1, 2]
      page.activeTab.value = 'service_module'

      expect(page.tabFilters.value.domain.id__in).toBe('1,2')
      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })

    it('scopeIds 变更后 tabFilters 应自动更新', () => {
      const page = createComposable()
      page.scopeIds.business_object.selected = [10]
      expect(page.tabFilters.value.business_object.id__in).toBe('10')

      page.scopeIds.business_object.selected = [20, 30]
      expect(page.tabFilters.value.business_object.id__in).toBe('20,30')
    })

    it('customFilterBuilders 在 tabFilters precompute 中也生效', () => {
      const customBuilder = vi.fn((filters, ids) => {
        if (ids.custom_type?.selected.length > 0) {
          filters.custom_field__in = ids.custom_type.selected.join(',')
        }
        return filters
      })
      const page = createComposable(['custom_type', 'domain'], {
        customFilterBuilders: { custom_type: customBuilder }
      })
      page.scopeIds.custom_type = { selected: ['a'], effective: [] }
      page.activeTab.value = 'domain'

      expect(page.tabFilters.value.custom_type.custom_field__in).toBe('a')
    })
  })

  describe('scopeFilterKeys — 动态推导', () => {
    it('应包含所有固定键', () => {
      const page = createComposable()
      const keys = page.scopeFilterKeys.value
      expect(keys).toContain('id__in')
      expect(keys).toContain('annotation_category__in')
      expect(keys).toContain('relation_code__in')
      expect(keys).toContain('category_types__in')
      expect(keys).toContain('source_bo_ids')
      expect(keys).toContain('target_bo_ids')
    })

    it('应包含从 parent type 推导的 FK 键', () => {
      const page = createComposable()
      const keys = page.scopeFilterKeys.value
      expect(keys).toContain('version_id__in')
      expect(keys).toContain('domain_id__in')
      expect(keys).toContain('sub_domain_id__in')
      expect(keys).toContain('service_module_id__in')
    })

    it('filter_mappings trigger=parent → 添加 filter_field__in', () => {
      const sdLevel = mockLevels.find(l => l.object_type === 'sub_domain')
      const origMappings = sdLevel.filter_mappings
      sdLevel.filter_mappings = [
        { filter_field: 'domain_id', priority: 3, trigger: 'parent' }
      ]

      const page = createComposable()
      expect(page.scopeFilterKeys.value).toContain('domain_id__in')

      sdLevel.filter_mappings = origMappings
    })

    it('filter_mappings trigger=entity_scope → 添加 filter_field__in', () => {
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origMappings = relLevel.filter_mappings
      relLevel.filter_mappings = [
        { filter_field: 'source_bo_id', priority: 3, trigger: 'entity_scope' },
        { filter_field: 'target_bo_id', priority: 3, trigger: 'entity_scope' }
      ]

      const page = createComposable()
      expect(page.scopeFilterKeys.value).toContain('source_bo_id__in')
      expect(page.scopeFilterKeys.value).toContain('target_bo_id__in')

      relLevel.filter_mappings = origMappings
    })

    it('scopeFilterKeys 应去重', () => {
      const sdLevel = mockLevels.find(l => l.object_type === 'sub_domain')
      const origMappings = sdLevel.filter_mappings
      sdLevel.filter_mappings = [
        { filter_field: 'domain_id', priority: 3, trigger: 'parent' }
      ]

      const page = createComposable()
      const keys = page.scopeFilterKeys.value
      const domainIdCount = keys.filter(k => k === 'domain_id__in').length
      expect(domainIdCount).toBe(1)

      sdLevel.filter_mappings = origMappings
    })
  })

  describe('combinedFilters — scopeFilterKeys cleanup', () => {
    it('应从 base 中清除 scope 相关过滤键后重建', () => {
      mockFilterFlowCombinedFilters.value = {
        version_id: 1,
        id__in: '100,200',
        domain_id__in: '5,6'
      }

      const page = createComposable()
      page.scopeIds.domain.selected = [1, 2]
      page.activeTab.value = 'domain'

      expect(page.combinedFilters.value.id__in).toBe('1,2')
      expect(page.combinedFilters.value).not.toHaveProperty('domain_id__in')
      expect(page.combinedFilters.value).toHaveProperty('version_id', 1)
    })

    it('清除后 scopeFilterKeys 中的键不应残留', () => {
      mockFilterFlowCombinedFilters.value = {
        version_id: 1,
        relation_code__in: 'STALE',
        category_types__in: 'STALE',
        source_bo_ids: 'STALE'
      }

      const page = createComposable()
      page.activeTab.value = 'relationship'

      expect(page.combinedFilters.value).not.toHaveProperty('relation_code__in')
      expect(page.combinedFilters.value).not.toHaveProperty('category_types__in')
      expect(page.combinedFilters.value).not.toHaveProperty('source_bo_ids')
    })
  })

  describe('combinedFilters — FK 回退全层级', () => {
    it('sub_domain Tab: 无选择时 parent domain selected → domain_id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'sub_domain'
      page.scopeIds.domain.selected = [10, 20]

      expect(page.combinedFilters.value.domain_id__in).toBe('10,20')
      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
    })

    it('sub_domain Tab: 无选择时 parent domain effective → domain_id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'sub_domain'
      page.scopeIds.domain.effective = [1, 2]

      expect(page.combinedFilters.value.domain_id__in).toBe('1,2')
    })

    it('service_module Tab: parent sub_domain selected → sub_domain_id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'service_module'
      page.scopeIds.sub_domain.selected = [5, 6]

      expect(page.combinedFilters.value.sub_domain_id__in).toBe('5,6')
    })

    it('service_module Tab: parent sub_domain effective → sub_domain_id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'service_module'
      page.scopeIds.sub_domain.effective = [3, 4]

      expect(page.combinedFilters.value.sub_domain_id__in).toBe('3,4')
    })

    it('BO Tab: parent service_module effective → service_module_id__in', () => {
      const page = createComposable()
      page.activeTab.value = 'business_object'
      page.scopeIds.service_module.effective = [7, 8]

      expect(page.combinedFilters.value.service_module_id__in).toBe('7,8')
    })

    it('domain Tab: 无父级 FK 回退（domain parent=version 不在 scopeIds 中）', () => {
      const page = createComposable()
      page.activeTab.value = 'domain'

      expect(page.combinedFilters.value).not.toHaveProperty('id__in')
      expect(page.combinedFilters.value).not.toHaveProperty('version_id__in')
    })
  })

  describe('_computeTypeFilters — 路由', () => {
    it('非层级非关联未知类型返回空 filters', () => {
      const page = createComposable(['unknown_type'])
      page.activeTab.value = 'unknown_type'

      const filters = page.combinedFilters.value
      expect(filters).toHaveProperty('version_id', 1)
    })

    it('isEntity=true 的类型走 _buildHierarchyFilters', () => {
      // mockLevels 中 domain 已有 kind: 'entity'，hierarchyService.isEntity 自动返回 true

      const page = createComposable()
      page.activeTab.value = 'domain'
      page.scopeIds.domain.selected = [1, 2]

      expect(page.combinedFilters.value.id__in).toBe('1,2')
    })

    it('isAssociation=true 类型有 filter_mappings 时走 _buildAssociationFilters', () => {
      // 在 mockLevels 中给 relationship 添加 filter_mappings
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origMappings = relLevel.filter_mappings
      const origSource = relLevel.source_entity
      const origTarget = relLevel.target_entity
      relLevel.filter_mappings = [
        { filter_field: 'source_bo_id', priority: 3, trigger: 'entity_scope' },
        { filter_field: 'target_bo_id', priority: 3, trigger: 'entity_scope' }
      ]
      relLevel.source_entity = 'business_object'
      relLevel.target_entity = 'business_object'

      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.business_object.selected = [10]

      expect(page.combinedFilters.value.source_bo_id__in).toBe('10')
      expect(page.combinedFilters.value.target_bo_id__in).toBe('10')

      // 恢复
      relLevel.filter_mappings = origMappings
      relLevel.source_entity = origSource
      relLevel.target_entity = origTarget
    })

    it('type=relationship 但 isEntity/isAssociation 均未提供时应走回退', () => {
      // 临时修改 relationship 的 kind 为 null，使其既不是 entity 也不是 association
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origKind = relLevel.kind
      relLevel.kind = null

      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON']

      expect(page.combinedFilters.value.relation_code__in).toBe('DEPENDS_ON')

      // 恢复
      relLevel.kind = origKind
    })

    it('type=relationship 不匹配任何路由时应走 _buildRelationshipFilters', () => {
      // 临时修改 relationship 的 kind 和移除层级索引
      const relLevel = mockLevels.find(l => l.object_type === 'relationship')
      const origKind = relLevel.kind
      relLevel.kind = null

      const page = createComposable()
      page.activeTab.value = 'relationship'
      page.scopeIds.relationExtra.relationCodes = ['CALLS']

      expect(page.combinedFilters.value.relation_code__in).toBe('CALLS')

      // 恢复
      relLevel.kind = origKind
    })
  })

  describe('handleScopeChange — BO 回退逻辑', () => {
    it('selectedBusinessObjectIds 优先于 boIds', () => {
      const page = createComposable()
      page.handleScopeChange({
        boIds: [1, 2],
        selectedBusinessObjectIds: [3, 4]
      })

      expect(page.scopeIds.business_object.selected).toEqual([3, 4])
    })

    it('无 selectedBusinessObjectIds 时使用 boIds', () => {
      const page = createComposable()
      page.handleScopeChange({ boIds: [5, 6] })

      expect(page.scopeIds.business_object.selected).toEqual([5, 6])
    })

    it('两者都无时 business_object.selected 为空', () => {
      const page = createComposable()
      page.scopeIds.business_object.selected = [99]
      page.handleScopeChange({})

      expect(page.scopeIds.business_object.selected).toEqual([])
    })
  })

  describe('activeTab 为空', () => {
    it('activeTab 为 null 时 combinedFilters 应只返回 base + global', () => {
      const page = createComposable()
      page.activeTab.value = null
      page.scopeIds.globalFilters = { annotation_category: ['bug'] }

      const f = page.combinedFilters.value
      expect(f.version_id).toBe(1)
      expect(f.annotation_category__in).toBe('bug')
      expect(f).not.toHaveProperty('id__in')
    })
  })

  describe('globalFilters — 非数组处理', () => {
    it('globalFilters 值为非数组时不应添加 __in 过滤', () => {
      const page = createComposable()
      page.scopeIds.globalFilters = { some_string: 'hello' }
      page.activeTab.value = 'domain'

      expect(page.combinedFilters.value).not.toHaveProperty('some_string__in')
    })

    it('globalFilters 值为空数组时不应添加 __in 过滤', () => {
      const page = createComposable()
      page.scopeIds.globalFilters = { empty_val: [] }
      page.activeTab.value = 'domain'

      expect(page.combinedFilters.value).not.toHaveProperty('empty_val__in')
    })
  })

  describe('Action 状态管理', () => {
    it('handleGlobalAction("import") 应设置 importDialogVisible = true', () => {
      const page = createComposable()
      expect(page.importDialogVisible.value).toBe(false)
      page.handleGlobalAction('import')
      expect(page.importDialogVisible.value).toBe(true)
    })

    it('handleGlobalAction("export") 应设置 exportDialogVisible = true', () => {
      const page = createComposable()
      expect(page.exportDialogVisible.value).toBe(false)
      page.handleGlobalAction('export')
      expect(page.exportDialogVisible.value).toBe(true)
    })

    it('handleGlobalAction("refresh") 应递增 refreshTrigger', () => {
      const page = createComposable()
      expect(page.refreshTrigger.value).toBe(0)
      page.handleGlobalAction('refresh')
      expect(page.refreshTrigger.value).toBe(1)
    })

    it('handleGlobalAction("chart") 应返回 chartData', () => {
      const page = createComposable()
      const result = page.handleGlobalAction('chart')
      expect(result).toBeDefined()
      expect(result.versionId).toBe(1)
      expect(result.hierarchyFilter).toBeDefined()
    })

    it('canImport 在有 version 选择时返回 true', () => {
      const page = createComposable()
      expect(page.canImport.value).toBe(true)
    })

    it('canExport 在有 version 选择时返回 true', () => {
      const page = createComposable()
      expect(page.canExport.value).toBe(true)
    })

    it('canShowChart 在无 scope 选择时返回 false', () => {
      const page = createComposable()
      expect(page.canShowChart.value).toBe(false)
    })

    it('canShowChart 在有 scope 选择时返回 true', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [1]
      expect(page.canShowChart.value).toBe(true)
    })

    it('canRefresh 在有 version 选择时返回 true', () => {
      const page = createComposable()
      expect(page.canRefresh.value).toBe(true)
    })

    it('actions 配置 chart.enabled=false 时 canShowChart 返回 false', () => {
      const page = createComposable(DEFAULT_OBJECT_TYPES, { actions: { chart: { enabled: false } } })
      expect(page.canShowChart.value).toBe(false)
    })

    it('actions 配置 import.enabled=false 时 canImport 返回 false', () => {
      const page = createComposable(DEFAULT_OBJECT_TYPES, { actions: { import: { enabled: false } } })
      expect(page.canImport.value).toBe(false)
    })

    it('handleImportSuccess 应关闭导入弹窗并触发刷新', () => {
      const page = createComposable()
      page.importDialogVisible.value = true
      page.handleImportSuccess()
      expect(page.importDialogVisible.value).toBe(false)
      expect(page.refreshTrigger.value).toBe(1)
    })

    it('handleExportSuccess 应关闭导出弹窗', () => {
      const page = createComposable()
      page.exportDialogVisible.value = true
      page.handleExportSuccess()
      expect(page.exportDialogVisible.value).toBe(false)
    })

    it('importContext 应包含 version_id 和 product_id', () => {
      const page = createComposable()
      const ctx = page.importContext.value
      expect(ctx).toHaveProperty('version_id')
      expect(ctx).toHaveProperty('product_id')
    })

    it('handleShowChart chartData 应包含 scope 层级数据', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [10, 20]
      page.scopeIds.sub_domain.selected = [30]
      const chartData = page.handleShowChart()
      expect(chartData.selectedDomainIds).toEqual([10, 20])
      expect(chartData.selectedSubDomainIds).toEqual([30])
    })
  })

  describe('baseFilters', () => {
    it('应包含 version_id', () => {
      const page = createComposable()
      expect(page.baseFilters.value).toHaveProperty('version_id', 1)
    })

    it('应包含 product_id', () => {
      const page = createComposable()
      expect(page.baseFilters.value).toHaveProperty('product_id', 1)
    })
  })

  describe('exportFilters — 多类型导出', () => {
    it('应包含 baseFilters', () => {
      const page = createComposable()
      const f = page.exportFilters.value
      expect(f.version_id).toBe(1)
      expect(f.product_id).toBe(1)
    })

    it('scope 全空时应只含 baseFilters', () => {
      const page = createComposable()
      const f = page.exportFilters.value
      expect(f.version_id).toBe(1)
      const keys = Object.keys(f).filter(k => k !== 'version_id' && k !== 'product_id')
      expect(keys.length).toBe(0)
    })

    it('切换 activeTab 不应改变 exportFilters', () => {
      const page = createComposable()
      page.scopeIds.globalFilters = { annotation_category: ['bug'] }

      page.activeTab.value = 'domain'
      const f1 = page.exportFilters.value

      page.activeTab.value = 'relationship'
      const f2 = page.exportFilters.value

      expect(f1).toEqual(f2)
    })

    it('应包含 globalFilters', () => {
      const page = createComposable()
      page.scopeIds.globalFilters = { annotation_category: ['bug', 'feature'] }

      page.activeTab.value = 'domain'
      expect(page.exportFilters.value.annotation_category).toEqual(['bug', 'feature'])
    })

    it('应包含所有层级类型的 {type}_id', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [1, 2]
      page.scopeIds.sub_domain.selected = [10, 20]
      page.scopeIds.relationExtra.relationCodes = ['DEPENDS_ON']

      const f = page.exportFilters.value

      expect(f.domain_id).toEqual([1, 2])
      expect(f.sub_domain_id).toEqual([10, 20])
      expect(f.relation_codes).toEqual(['DEPENDS_ON'])
    })

    it('不应包含任何类型的 id__in', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [1, 2]
      page.scopeIds.sub_domain.selected = [10, 20]
      page.scopeIds.service_module.selected = [5, 6]

      const f = page.exportFilters.value
      expect(f).not.toHaveProperty('id__in')
    })

    it('应为每个选中层级类型发送 {type}_id 数组', () => {
      const page = createComposable()
      page.scopeIds.domain.selected = [3, 4]
      page.scopeIds.sub_domain.selected = [10, 20]
      page.scopeIds.service_module.selected = [30, 40]

      const f = page.exportFilters.value

      expect(f.domain_id).toEqual([3, 4])
      expect(f.sub_domain_id).toEqual([10, 20])
      expect(f.service_module_id).toEqual([30, 40])
    })
  })

  describe('exportContext', () => {
    it('应包含 objectType', () => {
      const page = createComposable()
      page.activeTab.value = 'sub_domain'
      expect(page.exportContext.value.objectType).toBe('sub_domain')
    })

    it('应包含 filters', () => {
      const page = createComposable()
      expect(page.exportContext.value.filters).toBeDefined()
    })

    it('objectTypes 应过滤掉 relationship', () => {
      const page = createComposable()
      const types = page.exportContext.value.objectTypes
      expect(types).not.toContain('relationship')
      expect(types).toContain('domain')
      expect(types).toContain('sub_domain')
    })
  })

  describe('objectTypeLabels', () => {
    it('应为所有 objectType 提供标签', () => {
      const page = createComposable()
      const labels = page.objectTypeLabels.value
      expect(labels.domain).toBe('领域')
      expect(labels.sub_domain).toBe('子领域')
      expect(labels.service_module).toBe('服务模块')
      expect(labels.business_object).toBe('业务对象')
      expect(labels.relationship).toBe('关系')
    })

    it('未知类型应回退到原字符串', () => {
      const page = createComposable(['unknown_type'])
      expect(page.objectTypeLabels.value.unknown_type).toBe('unknown_type')
    })
  })
})
