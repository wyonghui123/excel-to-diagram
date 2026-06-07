/**
 * useContextFilterSource.spec.js - 上下文过滤源测试
 *
 * 测试核心功能：
 * 1. 初始状态和配置
 * 2. 过滤值生成
 * 3. setContext 方法
 * 4. clear 方法
 * 5. ready 状态
 * 6. meta 元数据
 * 7. FilterSource 接口实现
 */

import { describe, it, expect, vi } from 'vitest'
import { ref, computed } from 'vue'
import { useContextFilterSource } from '@/composables/filterSources/useContextFilterSource'

describe('useContextFilterSource', () => {
  describe('initial state', () => {
    it('should initialize with default id and contextField', () => {
      const source = useContextFilterSource()
      
      expect(source.source.id).toBe('context')
      expect(source.source.type).toBe('context')
      expect(source.source.dependsOn).toEqual([])
    })

    it('should use custom id when provided', () => {
      const source = useContextFilterSource({ id: 'version-context' })
      expect(source.source.id).toBe('version-context')
    })

    it('should use custom contextField when provided', () => {
      const source = useContextFilterSource({ contextField: 'product_id' })
      expect(source.contextValue.value).toBeNull()
      
      source.setContext(42)
      expect(source.value.value).toEqual({ product_id: 42 })
    })

    it('should expose all required properties', () => {
      const source = useContextFilterSource()
      
      expect(source.source).toBeDefined()
      expect(source.contextValue).toBeDefined()
      expect(source.loading).toBeDefined()
      expect(source.ready).toBeDefined()
      expect(source.meta).toBeDefined()
      expect(source.setContext).toBeDefined()
      expect(typeof source.setContext).toBe('function')
      expect(source.clear).toBeDefined()
      expect(typeof source.clear).toBe('function')
    })

    it('should have correct default label and icon', () => {
      const source = useContextFilterSource()
      
      expect(source.source.label).toBe('Context')
      expect(source.meta.value.icon).toBe('calendar')
    })

    it('should accept custom label and icon', () => {
      const source = useContextFilterSource({
        label: 'Version',
        icon: 'clock'
      })
      
      expect(source.source.label).toBe('Version')
      expect(source.meta.value.icon).toBe('clock')
    })
  })

  describe('filter value generation', () => {
    it('should return empty object when contextValue is null', () => {
      const source = useContextFilterSource({ contextField: 'version_id' })
      expect(source.value.value).toEqual({})
    })

    it('should return filter with context field when value is set', () => {
      const source = useContextFilterSource({ contextField: 'version_id' })
      source.setContext(5)
      
      expect(source.value.value).toEqual({ version_id: 5 })
    })

    it('should update value reactively', () => {
      const source = useContextFilterSource({ contextField: 'env_id' })
      
      source.setContext(1)
      expect(source.value.value.env_id).toBe(1)
      
      source.setContext(99)
      expect(source.value.value.env_id).toBe(99)
    })

    it('should support different context field types', () => {
      const stringSource = useContextFilterSource({ contextField: 'locale' })
      stringSource.setContext('zh-CN')
      expect(stringSource.value.value.locale).toBe('zh-CN')

      const boolSource = useContextFilterSource({ contextField: 'is_admin' })
      boolSource.setContext(true)
      expect(boolSource.value.value.is_admin).toBe(true)
    })
  })

  describe('setContext method', () => {
    it('should update contextValue', () => {
      const source = useContextFilterSource()
      source.setContext(123)
      expect(source.contextValue.value).toBe(123)
    })

    it('should update value computed property', () => {
      const source = useContextFilterSource({ contextField: 'test_id' })
      
      source.setContext(10)
      expect(source.value.value.test_id).toBe(10)
    })

    it('should handle null value', () => {
      const source = useContextFilterSource({ contextField: 'test_id' })
      
      source.setContext(10)
      expect(source.value.value.test_id).toBe(10)
      
      source.setContext(null)
      expect(source.value.value).toEqual({})
    })

    it('should handle undefined value', () => {
      const source = useContextFilterSource({ contextField: 'test_id' })
      
      source.setContext(undefined)
      expect(source.value.value).toEqual({})
    })

    it('should handle zero as valid value', () => {
      const source = useContextFilterSource({ contextField: 'offset' })
      
      source.setContext(0)
      expect(source.value.value.offset).toBe(0)
    })

    it('should handle empty string as valid value', () => {
      const source = useContextFilterSource({ contextField: 'search' })
      
      source.setContext('')
      expect(source.value.value.search).toBe('')
    })
  })

  describe('clear method', () => {
    it('should reset contextValue to null', () => {
      const source = useContextFilterSource()
      source.setContext(100)
      expect(source.contextValue.value).toBe(100)
      
      source.clear()
      expect(source.contextValue.value).toBeNull()
    })

    it('should clear the filter value', () => {
      const source = useContextFilterSource({ contextField: 'v_id' })
      source.setContext(5)
      expect(source.value.value.v_id).toBe(5)
      
      source.clear()
      expect(source.value.value).toEqual({})
    })
  })

  describe('ready state', () => {
    it('should be false when contextValue is null', () => {
      const source = useContextFilterSource()
      expect(source.ready.value).toBe(false)
    })

    it('should be true when contextValue is set', () => {
      const source = useContextFilterSource()
      source.setContext(1)
      expect(source.ready.value).toBe(true)
    })

    it('should toggle between false and true', () => {
      const source = useContextFilterSource()
      
      expect(source.ready.value).toBe(false)
      
      source.setContext(1)
      expect(source.ready.value).toBe(true)
      
      source.clear()
      expect(source.ready.value).toBe(false)
    })
  })

  describe('meta metadata', () => {
    it('should have fields array with one item', () => {
      const source = useContextFilterSource({ contextField: 'my_field' })
      
      const fields = source.meta.value.fields
      expect(fields).toHaveLength(1)
      expect(fields[0].key).toBe('my_field')
    })

    it('should have scalar type for context field', () => {
      const source = useContextFilterSource({ contextField: 'ver' })
      
      const field = source.meta.value.fields[0]
      expect(field.type).toBe('scalar')
      expect(field.operator).toBe('eq')
    })

    it('should include label from options', () => {
      const source = useContextFilterSource({
        label: 'Product Version',
        contextField: 'pv'
      })
      
      const field = source.meta.value.fields[0]
      expect(field.label).toBe('Product Version')
    })

    it('should generate description automatically', () => {
      const source = useContextFilterSource({ label: 'Env' })
      expect(source.meta.value.description).toContain('Env')
    })
  })

  describe('FilterSource interface compliance', () => {
    it('should have required FilterSource properties', () => {
      const source = useContextFilterSource({ id: 'test-ctx' })
      const fs = source.source
      
      expect(fs.id).toBe('test-ctx')
      expect(fs.type).toBe('context')
      expect(fs.label).toBeDefined()
      expect(fs.value).toBeDefined()
      expect(fs.dependsOn).toBeDefined()
      expect(Array.isArray(fs.dependsOn)).toBe(true)
      expect(fs.loading).toBeDefined()
      expect(fs.ready).toBeDefined()
      expect(fs.meta).toBeDefined()
    })

    it('should have empty dependsOn by default', () => {
      const source = useContextFilterSource()
      expect(source.source.dependsOn).toEqual([])
    })

    it('should be usable in useFilterFlow', async () => {
      const { useFilterFlow } = await import('@/composables/useFilterFlow')
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const ctxSource = useContextFilterSource({ 
        id: 'version',
        contextField: 'version_id'
      })
      ctxSource.setContext(7)
      
      flow.registerSource(ctxSource.source)
      
      expect(flow.combinedFilters.value.version_id).toBe(7)
    })
  })

  describe('loading state', () => {
    it('should initialize loading as false', () => {
      const source = useContextFilterSource()
      expect(source.loading.value).toBe(false)
    })

    it('should allow setting loading state externally if needed', () => {
      const source = useContextFilterSource()
      source.loading.value = true
      expect(source.loading.value).toBe(true)
    })
  })
})
