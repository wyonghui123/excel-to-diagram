/**
 * useScopeFilterSource.spec.js - 范围过滤源测试
 *
 * 测试核心功能：
 * 1. 初始状态和配置
 * 2. 过滤值生成（业务对象范围、关系类型、计算字段）
 * 3. setBusinessObjectIds / setRelationCodes / setCategoryTypes
 * 4. clear 方法（全部和单独）
 * 5. onDependencyChange 处理
 * 6. computedCategoryTypes 计算字段
 * 7. meta 元数据
 * 8. FilterSource 接口实现
 */

import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useScopeFilterSource } from '@/composables/filterSources/useScopeFilterSource'

const MOCK_META_OBJECT = {
  hierarchy_scopes: [
    { id: 'cross_domain', name: '跨领域', type: 'cross_domain' },
    { id: 'same_domain_cross_subdomain', name: '同领域跨子领域', type: 'same_domain_cross_subdomain' },
    { id: 'same_subdomain_cross_module', name: '同子领域跨模块', type: 'same_subdomain_cross_module' },
    { id: 'same_module', name: '同服务模块', type: 'same_module' }
  ]
}

describe('useScopeFilterSource', () => {
  describe('initial state', () => {
    it('should initialize with default values', () => {
      const source = useScopeFilterSource()
      
      expect(source.source.id).toBe('scope')
      expect(source.source.type).toBe('scope')
      expect(source.selectedBoIds.value).toEqual([])
      expect(source.selectedRelationCodes.value).toEqual([])
      expect(source.selectedCategoryTypes.value).toEqual([])
      expect(source.loading.value).toBe(false)
    })

    it('should use custom id when provided', () => {
      const source = useScopeFilterSource({ id: 'relation-scope' })
      expect(source.source.id).toBe('relation-scope')
    })

    it('should use custom label when provided', () => {
      const source = useScopeFilterSource({ label: 'Relation Scope' })
      expect(source.source.label).toBe('Relation Scope')
    })

    it('should expose all required methods and properties', () => {
      const source = useScopeFilterSource()
      
      expect(source.setBusinessObjectIds).toBeDefined()
      expect(typeof source.setBusinessObjectIds).toBe('function')
      
      expect(source.setRelationCodes).toBeDefined()
      expect(typeof source.setRelationCodes).toBe('function')
      
      expect(source.setCategoryTypes).toBeDefined()
      expect(typeof source.setCategoryTypes).toBe('function')
      
      expect(source.clear).toBeDefined()
      expect(typeof source.clear).toBe('function')
      
      expect(source.clearBusinessObjects).toBeDefined()
      expect(source.clearRelationCodes).toBeDefined()
      expect(source.clearCategoryTypes).toBeDefined()
      
      expect(source.scopeConfig).toBeDefined()
      expect(source.computedCategoryTypes).toBeDefined()
    })
  })

  describe('filter value generation', () => {
    it('should return empty object when nothing selected', () => {
      const source = useScopeFilterSource()
      expect(source.value.value).toEqual({})
    })

    it('should generate source_bo_ids and target_bo_ids when BOs selected', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1, 2, 3])
      
      const val = source.value.value
      expect(val.source_bo_ids).toEqual([1, 2, 3])
      expect(val.target_bo_ids).toEqual([1, 2, 3])
    })

    it('should generate relation_codes when types selected', () => {
      const source = useScopeFilterSource()
      source.setRelationCodes(['DEPENDS_ON', 'CALLS'])
      
      expect(source.value.value.relation_codes).toEqual(['DEPENDS_ON', 'CALLS'])
    })

    it('should generate category_types when categories selected', () => {
      const source = useScopeFilterSource()
      source.setCategoryTypes(['cross_domain'])
      
      expect(source.value.value.category_types).toEqual(['cross_domain'])
    })

    it('should combine all filter values', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([10, 20])
      source.setRelationCodes(['DEPENDS_ON'])
      source.setCategoryTypes(['same_module'])

      const val = source.value.value
      expect(val.source_bo_ids).toEqual([10, 20])
      expect(val.target_bo_ids).toEqual([10, 20])
      expect(val.relation_codes).toEqual(['DEPENDS_ON'])
      expect(val.category_types).toEqual(['same_module'])
    })

    it('should not include empty arrays in value', () => {
      const source = useScopeFilterSource()
      expect(Object.keys(source.value.value)).toHaveLength(0)
    })

    // [v3.18 新增] id__in 字段生成测试
    it('should generate id__in when relationIds are set', () => {
      const source = useScopeFilterSource()
      source.setRelationIds([5, 10, 15])
      // 字段名必须是 id__in（与 buildRelationshipFilterParams 对齐），不是 id 或 relation_ids
      expect(source.value.value.id__in).toEqual([5, 10, 15])
      // relation_codes 不应出现（relationIds 有值时应被忽略）
      expect(source.value.value.relation_codes).toBeUndefined()
    })

    it('should prefer relationIds over relationCodes', () => {
      // 模拟"范围内"节点勾选：同时设置 codes 和 ids
      const source = useScopeFilterSource()
      source.setRelationCodes(['GENERATES', 'DEPENDS_ON'])
      source.setRelationIds([101, 102])
      // relationIds 有值时，value 应输出 id__in，不输出 relation_codes
      expect(source.value.value.id__in).toEqual([101, 102])
      expect(source.value.value.relation_codes).toBeUndefined()
    })

    it('should fall back to relation_codes when relationIds is empty', () => {
      const source = useScopeFilterSource()
      source.setRelationIds([])
      source.setRelationCodes(['CALLS'])
      expect(source.value.value.id__in).toBeUndefined()
      expect(source.value.value.relation_codes).toEqual(['CALLS'])
    })

    it('should handle single relationId', () => {
      const source = useScopeFilterSource()
      source.setRelationIds([42])
      expect(source.value.value.id__in).toEqual([42])
    })
  })

  describe('setBusinessObjectIds method', () => {
    it('should update selectedBoIds', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([100, 200])
      expect(source.selectedBoIds.value).toEqual([100, 200])
    })

    it('should replace previous values', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1, 2])
      source.setBusinessObjectIds([3, 4])
      expect(source.selectedBoIds.value).toEqual([3, 4])
    })

    it('should accept empty array', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1, 2])
      source.setBusinessObjectIds([])
      expect(source.selectedBoIds.value).toEqual([])
    })
  })

  describe('setRelationCodes method', () => {
    it('should update selectedRelationCodes', () => {
      const source = useScopeFilterSource()
      source.setRelationCodes(['A', 'B'])
      expect(source.selectedRelationCodes.value).toEqual(['A', 'B'])
    })

    it('should replace previous values', () => {
      const source = useScopeFilterSource()
      source.setRelationCodes(['X'])
      source.setRelationCodes(['Y'])
      expect(source.selectedRelationCodes.value).toEqual(['Y'])
    })
  })

  // [v3.18 新增] setRelationIds 测试
  describe('setRelationIds method', () => {
    it('should update selectedRelationIds', () => {
      const source = useScopeFilterSource()
      source.setRelationIds([100, 200, 300])
      expect(source.selectedRelationIds.value).toEqual([100, 200, 300])
    })

    it('should replace previous values', () => {
      const source = useScopeFilterSource()
      source.setRelationIds([1, 2])
      source.setRelationIds([3, 4])
      expect(source.selectedRelationIds.value).toEqual([3, 4])
    })

    it('should accept empty array', () => {
      const source = useScopeFilterSource()
      source.setRelationIds([1, 2])
      source.setRelationIds([])
      expect(source.selectedRelationIds.value).toEqual([])
    })
  })

  describe('setCategoryTypes method', () => {
    it('should update selectedCategoryTypes', () => {
      const source = useScopeFilterSource()
      source.setCategoryTypes(['type1', 'type2'])
      expect(source.selectedCategoryTypes.value).toEqual(['type1', 'type2'])
    })
  })

  describe('clear methods', () => {
    it('clear should reset all selections', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1, 2])
      source.setRelationCodes(['A'])
      source.setCategoryTypes(['cat1'])
      
      source.clear()
      
      expect(source.selectedBoIds.value).toEqual([])
      expect(source.selectedRelationCodes.value).toEqual([])
      expect(source.selectedCategoryTypes.value).toEqual([])
      expect(source.value.value).toEqual({})
    })

    it('clearBusinessObjects should only reset BO selection', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1, 2])
      source.setRelationCodes(['A'])
      
      source.clearBusinessObjects()
      
      expect(source.selectedBoIds.value).toEqual([])
      expect(source.selectedRelationCodes.value).toEqual(['A'])
    })

    it('clearRelationCodes should only reset relation codes', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1])
      source.setRelationCodes(['A', 'B'])
      
      source.clearRelationCodes()
      
      expect(source.selectedBoIds.value).toEqual([1])
      expect(source.selectedRelationCodes.value).toEqual([])
    })

    it('clearCategoryTypes should only reset category types', () => {
      const source = useScopeFilterSource()
      source.setCategoryTypes(['type1'])
      
      source.clearCategoryTypes()
      
      expect(source.selectedCategoryTypes.value).toEqual([])
    })
  })

  describe('ready state', () => {
    it('should always be true', () => {
      const source = useScopeFilterSource()
      expect(source.ready.value).toBe(true)
    })

    it('should remain true after operations', () => {
      const source = useScopeFilterSource()
      source.setBusinessObjectIds([1])
      expect(source.ready.value).toBe(true)
      
      source.clear()
      expect(source.ready.value).toBe(true)
    })
  })

  describe('scopeConfig - meta object integration', () => {
    it('should return empty array when metaObject is null', () => {
      const source = useScopeFilterSource({
        metaObject: ref(null)
      })
      expect(source.scopeConfig.value).toEqual([])
    })

    it('should return empty array when metaObject has no hierarchies', () => {
      const source = useScopeFilterSource({
        metaObject: ref({})
      })
      expect(source.scopeConfig.value).toEqual([])
    })

    it('should read hierarchy_scopes from metaObject', () => {
      const source = useScopeFilterSource({
        metaObject: ref(MOCK_META_OBJECT)
      })
      
      expect(source.scopeConfig.value).toHaveLength(4)
      expect(source.scopeConfig.value[0].id).toBe('cross_domain')
    })
  })

  describe('computedCategoryTypes', () => {
    it('should return empty array when no BOs selected', () => {
      const source = useScopeFilterSource()
      expect(source.computedCategoryTypes.value).toEqual([])
    })

    it('should return selectedCategoryTypes if manually set', () => {
      const source = useScopeFilterSource()
      source.setCategoryTypes(['custom_type'])
      
      expect(source.computedCategoryTypes.value).toEqual(['custom_type'])
    })

    it('should reflect changes to selectedCategoryTypes', () => {
      const source = useScopeFilterSource()
      
      expect(source.computedCategoryTypes.value).toEqual([])
      
      source.setCategoryTypes(['type_a'])
      expect(source.computedCategoryTypes.value).toEqual(['type_a'])
      
      source.setCategoryTypes(['type_b'])
      expect(source.computedCategoryTypes.value).toEqual(['type_b'])
    })
  })

  describe('onDependencyChange handling', () => {
    it('should extract bo_ids from dependency values', async () => {
      const source = useScopeFilterSource({
        dependsOn: ['bo-tree']
      })
      
      const depMap = new Map([
        ['bo-tree', { bo_ids: [10, 20, 30] }]
      ])
      
      await source.source.onDependencyChange(depMap)
      
      expect(source.selectedBoIds.value).toEqual([10, 20, 30])
    })

    it('should extract node_ids as fallback', async () => {
      const source = useScopeFilterSource({
        dependsOn: ['bo-tree']
      })
      
      const depMap = new Map([
        ['bo-tree', { node_ids: [5, 6] }]
      ])
      
      await source.source.onDependencyChange(depMap)
      
      expect(source.selectedBoIds.value).toEqual([5, 6])
    })

    it('should handle dependency with no bo_ids or node_ids', async () => {
      const source = useScopeFilterSource({
        dependsOn: ['version']
      })
      
      const depMap = new Map([
        ['version', { version_id: 1 }]
      ])
      
      await source.source.onDependencyChange(depMap)
      
      expect(source.selectedBoIds.value).toEqual([])
    })

    it('should handle multiple dependencies', async () => {
      const source = useScopeFilterSource({
        dependsOn: ['tree1', 'tree2']
      })
      
      const depMap = new Map([
        ['tree1', { bo_ids: [1, 2] }],
        ['tree2', { bo_ids: [3, 4] }]
      ])
      
      await source.source.onDependencyChange(depMap)
      
      expect(source.selectedBoIds.value).toContain(1)
      expect(source.selectedBoIds.value).toContain(4)
    })
  })

  describe('meta metadata', () => {
    it('should have correct icon', () => {
      const source = useScopeFilterSource()
      expect(source.meta.value.icon).toBe('link')
    })

    it('should have all five field definitions', () => {
      const source = useScopeFilterSource()
      const fields = source.meta.value.fields

      // 源码包含 5 个字段：source_bo_ids, target_bo_ids, relation_codes, relation_ids, category_types
      expect(fields).toHaveLength(5)

      const keys = fields.map(f => f.key)
      expect(keys).toContain('source_bo_ids')
      expect(keys).toContain('target_bo_ids')
      expect(keys).toContain('relation_codes')
      expect(keys).toContain('relation_ids')
      expect(keys).toContain('category_types')
    })

    it('all fields should have array type and in operator', () => {
      const source = useScopeFilterSource()
      
      for (const field of source.meta.value.fields) {
        expect(field.type).toBe('array')
        expect(field.operator).toBe('in')
      }
    })

    it('should include description', () => {
      const source = useScopeFilterSource({ label: 'Rel Scope' })
      expect(source.meta.value.description).toContain('Rel Scope')
    })
  })

  describe('FilterSource interface compliance', () => {
    it('should have all required FilterSource properties', () => {
      const source = useScopeFilterSource({ id: 'rel-scope' })
      const fs = source.source
      
      expect(fs.id).toBe('rel-scope')
      expect(fs.type).toBe('scope')
      expect(fs.label).toBeDefined()
      expect(fs.value).toBeDefined()
      expect(fs.dependsOn).toBeDefined()
      expect(Array.isArray(fs.dependsOn)).toBe(true)
      expect(fs.loading).toBeDefined()
      expect(fs.ready).toBeDefined()
      expect(fs.meta).toBeDefined()
    })

    it('should support dependsOn configuration', () => {
      const source = useScopeFilterSource({
        dependsOn: ['bo-tree', 'version-context']
      })
      
      expect(source.source.dependsOn).toEqual(['bo-tree', 'version-context'])
    })

    it('should be usable in useFilterFlow', async () => {
      const { useFilterFlow } = await import('@/composables/useFilterFlow')
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const scopeSource = useScopeFilterSource({
        id: 'relation-scope',
        metaObject: ref(MOCK_META_OBJECT)
      })
      scopeSource.setBusinessObjectIds([1, 2, 3])
      scopeSource.setRelationCodes(['DEPENDS_ON'])
      
      flow.registerSource(scopeSource.source)
      
      const filters = flow.combinedFilters.value
      expect(filters.source_bo_ids).toEqual([1, 2, 3])
      expect(filters.target_bo_ids).toEqual([1, 2, 3])
      expect(filters.relation_codes).toEqual(['DEPENDS_ON'])
    })
  })

  describe('integration with other sources', () => {
    it('should work with context source in same flow', async () => {
      const { useFilterFlow } = await import('@/composables/useFilterFlow')
      const { useContextFilterSource } = await import('@/composables/filterSources/useContextFilterSource')
      
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const ctxSource = useContextFilterSource({
        id: 'version',
        contextField: 'version_id'
      })
      ctxSource.setContext(5)
      
      const scopeSource = useScopeFilterSource({
        id: 'scope',
        dependsOn: ['version']
      })
      scopeSource.setBusinessObjectIds([10, 20])
      scopeSource.setRelationCodes(['CALLS'])
      
      flow.registerSource(ctxSource.source)
      flow.registerSource(scopeSource.source)
      
      const filters = flow.combinedFilters.value
      expect(filters.version_id).toBe(5)
      expect(filters.source_bo_ids).toEqual([10, 20])
      expect(filters.target_bo_ids).toEqual([10, 20])
      expect(filters.relation_codes).toEqual(['CALLS'])
    })
  })
})
