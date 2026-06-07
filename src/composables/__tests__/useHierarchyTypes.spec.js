/**
 * useHierarchyTypes.spec.js - Hierarchy Types Metadata Management Tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useHierarchyTypes } from '../useHierarchyTypes'

describe('useHierarchyTypes', () => {
  describe('default config', () => {
    it('should return default levels', () => {
      const { levels } = useHierarchyTypes()
      expect(levels.value).toBeDefined()
      expect(Array.isArray(levels.value)).toBe(true)
      expect(levels.value.length).toBe(6)
    })

    it('should have correct default root type', () => {
      const { rootType } = useHierarchyTypes()
      expect(rootType.value).toBe('product')
    })

    it('should have correct default anchor type', () => {
      const { anchorType } = useHierarchyTypes()
      expect(anchorType.value).toBe('domain')
    })

    it('should have correct anchor types list', () => {
      const { anchorTypes } = useHierarchyTypes()
      expect(anchorTypes.value).toEqual(['domain'])
    })

    it('should have correct selectable types', () => {
      const { selectableTypes } = useHierarchyTypes()
      // selectableTypes = is_anchor || !children_field
      // domain 是 anchor，business_object 没有 children_field
      expect(selectableTypes.value).toContain('domain')
      expect(selectableTypes.value).toContain('business_object')
    })
  })

  describe('getLabel', () => {
    it('should return correct label for domain', () => {
      const { getLabel } = useHierarchyTypes()
      // FR-UI-010: getLabel 委托给 hierarchyService，从 levels 中查找 label 字段
      expect(getLabel('domain')).toBe('领域')
    })

    it('should return correct label for sub_domain', () => {
      const { getLabel } = useHierarchyTypes()
      expect(getLabel('sub_domain')).toBe('子领域')
    })

    it('should return type as fallback for unknown type', () => {
      const { getLabel } = useHierarchyTypes()
      expect(getLabel('unknown_type')).toBe('unknown_type')
    })
  })

  describe('getIcon', () => {
    it('should return correct icon for domain', () => {
      const { getIcon } = useHierarchyTypes()
      expect(getIcon('domain')).toBeDefined()
    })

    it('should return Document as fallback for unknown type', () => {
      const { getIcon } = useHierarchyTypes()
      expect(getIcon('unknown')).toBe('Document')
    })
  })

  describe('getChildType', () => {
    it('should return sub_domain for domain', () => {
      const { getChildType } = useHierarchyTypes()
      expect(getChildType('domain')).toBe('sub_domain')
    })

    it('should return null for leaf type', () => {
      const { getChildType } = useHierarchyTypes()
      expect(getChildType('business_object')).toBeNull()
    })

    it('should return null for unknown type', () => {
      const { getChildType } = useHierarchyTypes()
      expect(getChildType('unknown')).toBeNull()
    })
  })

  describe('getLevelIndex', () => {
    it('should return correct index for domain', () => {
      const { getLevelIndex } = useHierarchyTypes()
      expect(getLevelIndex('domain')).toBeDefined()
      expect(typeof getLevelIndex('domain')).toBe('number')
    })

    it('should return -1 for unknown type', () => {
      const { getLevelIndex } = useHierarchyTypes()
      expect(getLevelIndex('unknown')).toBe(-1)
    })
  })

  describe('hasChildren', () => {
    it('should return true for domain', () => {
      const { hasChildren } = useHierarchyTypes()
      expect(hasChildren('domain')).toBe(true)
    })

    it('should return false for leaf type', () => {
      const { hasChildren } = useHierarchyTypes()
      expect(hasChildren('business_object')).toBe(false)
    })
  })

  describe('childFieldMap', () => {
    it('should map domain to sub_domains', () => {
      const { childFieldMap } = useHierarchyTypes()
      expect(childFieldMap.value['domain']).toBeDefined()
    })

    it('should map business_object to null', () => {
      const { childFieldMap } = useHierarchyTypes()
      // business_object 没有 children_field，map 中不存在该键
      expect(childFieldMap.value['business_object'] ?? null).toBeNull()
    })
  })

  describe('typeIndexMap', () => {
    it('should map types to indices', () => {
      const { typeIndexMap } = useHierarchyTypes()
      expect(typeIndexMap.value['product']).toBe(0)
      expect(typeIndexMap.value['domain']).toBeDefined()
    })
  })
})
