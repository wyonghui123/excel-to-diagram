/**
 * useWorkspaceFilter.spec.js - 工作区过滤数据流管理测试
 *
 * 测试核心功能：
 * 1. 初始状态
 * 2. 版本上下文管理
 * 3. 层级钻取状态
 * 4. 过滤条件合并
 * 5. 父子类型映射
 * 6. 版本切换自动重置
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, computed } from 'vue'
import { useWorkspaceFilter } from '../useWorkspaceFilter'

vi.mock('../useVersionContext', () => ({
  useVersionContext: vi.fn(() => ({
    selectedVersionId: ref(1),
    selectedVersion: ref({ id: 1, name: 'V1.0', product_name: '产品A' }),
    contextFilters: computed(() => ({ version_id: 1 })),
    hasContext: ref(true),
    loadingVersions: ref(false),
    selectVersion: vi.fn(),
    resetContext: vi.fn(),
    setVersion: vi.fn()
  }))
}))

vi.mock('../useHierarchyList', () => ({
  useHierarchyList: vi.fn((options) => ({
    objectType: options?.objectType || 'domain',
    versionId: options?.versionId || ref(null),
    path: ref([]),
    currentType: ref(options?.objectType || 'domain'),
    parentId: ref(null),
    isDrilling: ref(false),
    separator: ref('›'),
    hasChildren: computed(() => false),
    drillIn: vi.fn(),
    goTo: vi.fn(),
    reset: vi.fn()
  }))
}))

describe('useWorkspaceFilter', () => {
  describe('initial state', () => {
    it('should initialize with default objectType', () => {
      const filter = useWorkspaceFilter()
      expect(filter.currentObjectType.value).toBe('domain')
    })

    it('should use custom objectType', () => {
      const filter = useWorkspaceFilter({ objectType: 'sub_domain' })
      expect(filter.currentObjectType.value).toBe('sub_domain')
    })

    it('should initialize with empty path', () => {
      const filter = useWorkspaceFilter()
      expect(filter.path.value).toEqual([])
    })

    it('should initialize with null parentId', () => {
      const filter = useWorkspaceFilter()
      expect(filter.parentId.value).toBeNull()
    })

    it('should have versionContext', () => {
      const filter = useWorkspaceFilter()
      expect(filter.versionContext).toBeDefined()
    })

    it('should have hierarchy', () => {
      const filter = useWorkspaceFilter()
      expect(filter.hierarchy).toBeDefined()
    })

    it('should initialize with empty combinedFilters when no context', () => {
      const filter = useWorkspaceFilter()
      expect(filter.combinedFilters.value).toBeDefined()
    })
  })

  describe('version context integration', () => {
    it('should expose selectedVersionId', () => {
      const filter = useWorkspaceFilter()
      expect(filter.selectedVersionId.value).toBe(1)
    })

    it('should expose selectedVersion', () => {
      const filter = useWorkspaceFilter()
      expect(filter.selectedVersion.value).toEqual({
        id: 1,
        name: 'V1.0',
        product_name: '产品A'
      })
    })

    it('should expose contextFilters', () => {
      const filter = useWorkspaceFilter()
      expect(filter.contextFilters.value).toEqual({ version_id: 1 })
    })

    it('should have hasContext true when version selected', () => {
      const filter = useWorkspaceFilter()
      expect(filter.hasContext.value).toBe(true)
    })

    it('should call versionContext.selectVersion on handleVersionChange', () => {
      const filter = useWorkspaceFilter()
      const context = { id: 2, name: 'V2.0', product_name: '产品B' }
      filter.handleVersionChange(context)
      expect(filter.versionContext.selectVersion).toHaveBeenCalledWith(context)
    })
  })

  describe('hierarchy integration', () => {
    it('should expose path', () => {
      const filter = useWorkspaceFilter()
      expect(filter.path.value).toEqual([])
    })

    it('should expose currentType', () => {
      const filter = useWorkspaceFilter()
      expect(filter.currentType.value).toBe('domain')
    })

    it('should expose parentId', () => {
      const filter = useWorkspaceFilter()
      expect(filter.parentId.value).toBeNull()
    })

    it('should expose separator', () => {
      const filter = useWorkspaceFilter()
      expect(filter.separator.value).toBe('›')
    })

    it('should call hierarchy.drillIn on handleNodeSelect', () => {
      const filter = useWorkspaceFilter()
      const node = { type: 'sub_domain', id: 5, name: '财务领域' }
      filter.handleNodeSelect(node)
      expect(filter.hierarchy.drillIn).toHaveBeenCalledWith('sub_domain', 5, '财务领域')
    })

    it('should call hierarchy.goTo on handleBreadcrumbNavigate', () => {
      const filter = useWorkspaceFilter()
      filter.handleBreadcrumbNavigate(1)
      expect(filter.hierarchy.goTo).toHaveBeenCalledWith(1)
    })

    it('should call hierarchy.reset on handleReset', () => {
      const filter = useWorkspaceFilter()
      filter.handleReset()
      expect(filter.hierarchy.reset).toHaveBeenCalled()
    })
  })

  describe('combined filters', () => {
    it('should include version_id in combinedFilters', () => {
      const filter = useWorkspaceFilter()
      expect(filter.combinedFilters.value.version_id).toBe(1)
    })

    it('should not include parent_id when parentId is null', () => {
      const filter = useWorkspaceFilter()
      const filters = filter.combinedFilters.value
      const parentFields = Object.keys(filters).filter(k => k.endsWith('_id') && k !== 'version_id')
      expect(parentFields).toHaveLength(0)
    })

    it('should have parentId as ref', () => {
      const filter = useWorkspaceFilter()
      expect(filter.parentId).toBeDefined()
      expect(filter.parentId.value).toBeNull()
    })
  })

  describe('filter field mapping', () => {
    it('should have parentFilterFieldMap', () => {
      const filter = useWorkspaceFilter()
      expect(filter.parentFilterFieldMap).toBeDefined()
    })

    it('should have currentParentFilterField as computed', () => {
      const filter = useWorkspaceFilter()
      expect(filter.currentParentFilterField).toBeDefined()
    })

    it('should provide getFiltersForType function', () => {
      const filter = useWorkspaceFilter()
      expect(filter.getFiltersForType).toBeDefined()
      expect(typeof filter.getFiltersForType).toBe('function')
    })

    it('should return filters with version_id in getFiltersForType', () => {
      const filter = useWorkspaceFilter()
      const filters = filter.getFiltersForType('sub_domain', 5)
      expect(filters).toHaveProperty('version_id', 1)
    })
  })

  describe('child object type', () => {
    it('should have childObjectType computed', () => {
      const filter = useWorkspaceFilter()
      expect(filter.childObjectType).toBeDefined()
    })

    it('should return null when no metaObject provided', () => {
      const filter = useWorkspaceFilter()
      expect(filter.childObjectType.value).toBeNull()
    })

    it('should have hasChildren computed', () => {
      const filter = useWorkspaceFilter()
      expect(filter.hasChildren).toBeDefined()
    })
  })

  describe('drillIntoChild', () => {
    it('should have drillIntoChild function', () => {
      const filter = useWorkspaceFilter()
      expect(filter.drillIntoChild).toBeDefined()
      expect(typeof filter.drillIntoChild).toBe('function')
    })

    it('should have childObjectType as computed', () => {
      const filter = useWorkspaceFilter()
      expect(filter.childObjectType).toBeDefined()
    })
  })

  describe('event handling', () => {
    it('should expose all event handler functions', () => {
      const filter = useWorkspaceFilter()

      expect(filter.handleVersionChange).toBeDefined()
      expect(typeof filter.handleVersionChange).toBe('function')

      expect(filter.handleNodeSelect).toBeDefined()
      expect(typeof filter.handleNodeSelect).toBe('function')

      expect(filter.handleBreadcrumbNavigate).toBeDefined()
      expect(typeof filter.handleBreadcrumbNavigate).toBe('function')

      expect(filter.handleReset).toBeDefined()
      expect(typeof filter.handleReset).toBe('function')
    })
  })

  describe('metadata-driven behavior', () => {
    it('should accept metaObject option', () => {
      const metaObjectRef = ref({
        hierarchies: [{
          levels: [
            { object_type: 'domain', children_field: 'sub_domains' },
            { object_type: 'sub_domain', children_field: 'service_modules' }
          ],
          root_filter: 'version_id'
        }]
      })

      const filter = useWorkspaceFilter({
        metaObject: metaObjectRef
      })

      expect(filter.parentFilterFieldMap.value).toBeDefined()
    })

    it('should derive filter fields from metaObject', () => {
      const metaObjectRef = ref({
        hierarchies: [{
          levels: [
            { object_type: 'domain', children_field: 'sub_domains' },
            { object_type: 'sub_domain', children_field: 'service_modules' }
          ],
          root_filter: 'version_id'
        }]
      })

      const filter = useWorkspaceFilter({
        metaObject: metaObjectRef
      })

      expect(filter.parentFilterFieldMap.value).toHaveProperty('domain')
      expect(filter.parentFilterFieldMap.value).toHaveProperty('sub_domain')
    })
  })
})
