/**
 * useHierarchyList.spec.js - 钻取状态管理测试
 *
 * 测试核心功能：
 * 1. 初始状态
 * 2. drillIn 钻入操作
 * 3. drillOut/goTo 回退操作
 * 4. reset 重置操作
 * 5. path 路径管理
 * 6. currentType 当前类型管理
 * 7. childType 子类型计算
 * 8. 版本切换自动重置
 *
 * 注意：useHierarchyList 通过 `inject('metaObject')` 获取 metaObject，
 * 在 vitest 环境中没有 Vue setup context，inject 会 fallback 到 undefined。
 * 因此测试通过 options 显式传入 `metaObject` ref。
 * 当 metaObject.value 为 null 时，composable 会使用内置 DEFAULT_HIERARCHY_CONFIG。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useHierarchyList } from '../useHierarchyList'

// 默认 mock：null → 使用内置 DEFAULT_HIERARCHY_CONFIG
const createMockMeta = () => ref(null)

// 可选：完整的 metaObject mock（hierarchies[0].levels 与 DEFAULT 一致）
const createFullMeta = () => ref({
  hierarchies: [{
    levels: [
      { object_type: 'domain', children_field: 'sub_domains' },
      { object_type: 'sub_domain', children_field: 'service_modules' },
      { object_type: 'service_module', children_field: 'business_objects' },
      { object_type: 'business_object', children_field: null }
    ],
    root_type: 'domain',
    root_filter: 'version_id',
    path_separator: '›'
  }]
})

describe('useHierarchyList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should initialize with empty path', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.path.value).toEqual([])
    })

    it('should initialize with default objectType', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.currentType.value).toBe('domain')
    })

    it('should initialize with null parentId', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.parentId.value).toBeNull()
    })

    it('should initialize with isDrilling false', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.isDrilling.value).toBe(false)
    })

    it('should use custom objectType', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta(), objectType: 'service_module' })
      expect(hierarchy.currentType.value).toBe('service_module')
    })

    it('should use custom separator', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta(), pathSeparator: '>' })
      expect(hierarchy.separator.value).toBe('>')
    })

    it('should use default separator as unicode arrow', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.separator.value).toBe('›')
    })
  })

  describe('drillIn', () => {
    it('should add node to path', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.path.value).toHaveLength(1)
      expect(hierarchy.path.value[0]).toEqual({
        type: 'sub_domain',
        id: 5,
        name: '总账'
      })
    })

    it('should update currentType', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.currentType.value).toBe('sub_domain')
    })

    it('should update parentId', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.parentId.value).toBe(5)
    })

    it('should append to existing path', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      expect(hierarchy.path.value).toHaveLength(2)
      expect(hierarchy.path.value[0].name).toBe('总账')
      expect(hierarchy.path.value[1].name).toBe('凭证管理')
    })

    it('should call onPathChange callback', () => {
      const onPathChange = vi.fn()
      const hierarchy = useHierarchyList({ metaObject: createMockMeta(), onPathChange })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(onPathChange).toHaveBeenCalledWith(hierarchy.path.value)
    })
  })

  describe('drillOut', () => {
    it('should remove nodes after target index', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      hierarchy.drillOut(0)
      expect(hierarchy.path.value).toHaveLength(1)
      expect(hierarchy.path.value[0].name).toBe('总账')
    })

    it('should update currentType after drillOut', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      hierarchy.drillOut(0)
      expect(hierarchy.currentType.value).toBe('sub_domain')
    })

    it('should not change path for invalid index', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillOut(5)
      expect(hierarchy.path.value).toHaveLength(1)
    })

    it('should not change path for negative index', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillOut(-1)
      expect(hierarchy.path.value).toHaveLength(1)
    })
  })

  describe('goTo', () => {
    it('should be alias for drillOut', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      hierarchy.goTo(0)
      expect(hierarchy.path.value).toHaveLength(1)
      expect(hierarchy.path.value[0].name).toBe('总账')
    })
  })

  describe('reset', () => {
    it('should clear path', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      hierarchy.reset()
      expect(hierarchy.path.value).toEqual([])
    })

    it('should reset currentType to root', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.reset()
      expect(hierarchy.currentType.value).toBe('domain')
    })

    it('should reset parentId to null', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.reset()
      expect(hierarchy.parentId.value).toBeNull()
    })

    it('should call onPathChange callback', () => {
      const onPathChange = vi.fn()
      const hierarchy = useHierarchyList({ metaObject: createMockMeta(), onPathChange })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.reset()
      expect(onPathChange).toHaveBeenCalledWith([])
    })
  })

  describe('computed properties', () => {
    describe('hasChildren', () => {
      it('should return true for domain', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        expect(hierarchy.hasChildren.value).toBe(true)
      })

      it('should return true for sub_domain', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        hierarchy.drillIn('sub_domain', 5, '总账')
        expect(hierarchy.hasChildren.value).toBe(true)
      })

      it('should return false for business_object', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        hierarchy.drillIn('sub_domain', 5, '总账')
        hierarchy.drillIn('service_module', 10, '凭证管理')
        hierarchy.drillIn('business_object', 15, '凭证')
        expect(hierarchy.hasChildren.value).toBe(false)
      })
    })

    describe('childType', () => {
      it('should return sub_domain for domain', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        expect(hierarchy.childType.value).toBe('sub_domain')
      })

      it('should return service_module for sub_domain', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        hierarchy.drillIn('sub_domain', 5, '总账')
        expect(hierarchy.childType.value).toBe('service_module')
      })

      it('should return business_object for service_module', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        hierarchy.drillIn('sub_domain', 5, '总账')
        hierarchy.drillIn('service_module', 10, '凭证管理')
        expect(hierarchy.childType.value).toBe('business_object')
      })

      it('should return null for business_object', () => {
        const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
        hierarchy.drillIn('sub_domain', 5, '总账')
        hierarchy.drillIn('service_module', 10, '凭证管理')
        hierarchy.drillIn('business_object', 15, '凭证')
        expect(hierarchy.childType.value).toBeNull()
      })
    })
  })

  describe('getPathString', () => {
    it('should return empty string for empty path', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.getPathString()).toBe('')
    })

    it('should return single node name', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.getPathString()).toBe('总账')
    })

    it('should join nodes with separator', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      expect(hierarchy.getPathString()).toBe('总账 › 凭证管理')
    })

    it('should use custom separator', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      hierarchy.drillIn('service_module', 10, '凭证管理')
      expect(hierarchy.getPathString(' > ')).toBe('总账 > 凭证管理')
    })
  })

  describe('isDrilling', () => {
    it('should be false initially', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      expect(hierarchy.isDrilling.value).toBe(false)
    })

    it('should be false after drillIn completes', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.isDrilling.value).toBe(false)
    })
  })

  describe('version switch', () => {
    it('should reset path when versionId changes', async () => {
      const versionId = ref(1)
      const hierarchy = useHierarchyList({ metaObject: createMockMeta(), versionId })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.path.value).toHaveLength(1)
      versionId.value = 2
      await nextTick()
      expect(hierarchy.path.value).toEqual([])
    })

    it('should reset currentType when versionId changes', async () => {
      const versionId = ref(1)
      const hierarchy = useHierarchyList({ metaObject: createMockMeta(), versionId })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.currentType.value).toBe('sub_domain')
      versionId.value = 2
      await nextTick()
      expect(hierarchy.currentType.value).toBe('domain')
    })

    it('should not auto-reset when versionId is null', () => {
      const hierarchy = useHierarchyList({ metaObject: createMockMeta() })
      hierarchy.drillIn('sub_domain', 5, '总账')
      expect(hierarchy.path.value).toHaveLength(1)
    })
  })

  describe('with full metaObject', () => {
    it('should compute childType from provided meta hierarchies', () => {
      const hierarchy = useHierarchyList({ metaObject: createFullMeta() })
      expect(hierarchy.childType.value).toBe('sub_domain')
    })

    it('should indicate hasChildren based on provided meta hierarchies', () => {
      const hierarchy = useHierarchyList({ metaObject: createFullMeta() })
      expect(hierarchy.hasChildren.value).toBe(true)
    })
  })
})
