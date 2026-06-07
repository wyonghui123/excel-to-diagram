/**
 * useFilterFlow.spec.js - 通用过滤流管理器测试
 *
 * 测试核心功能：
 * 1. 初始状态和配置
 * 2. 过滤源注册/注销/获取
 * 3. 过滤条件聚合（merge策略）
 * 4. 过滤条件聚合（intersect策略）
 * 5. 级联依赖处理
 * 6. 循环依赖检测
 * 7. 拓扑排序
 * 8. 目标注册和应用
 * 9. 刷新控制
 * 10. createFilterSource 工厂函数
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import { useFilterFlow, createFilterSource } from '@/composables/useFilterFlow'

function createMockSource(overrides = {}) {
  const value = ref(overrides.initialValue || {})
  return createFilterSource({
    id: overrides.id || 'test-source',
    type: overrides.type || 'filter',
    label: overrides.label || 'Test Source',
    value,
    dependsOn: overrides.dependsOn || [],
    onDependencyChange: overrides.onDependencyChange,
    refresh: overrides.refresh,
    loading: overrides.loading || ref(false),
    ready: overrides.ready !== undefined ? overrides.ready : computed(() => true),
    meta: overrides.meta,
    clear: overrides.clear,
    ...overrides
  })
}

describe('useFilterFlow', () => {
  describe('initial state', () => {
    it('should initialize with empty sources', () => {
      const flow = useFilterFlow()
      expect(flow.sources.value).toHaveLength(0)
      expect(flow.combinedFilters.value).toEqual({})
    })

    it('should accept custom aggregator config', () => {
      const flow = useFilterFlow({
        aggregator: { strategy: 'intersect' }
      })
      expect(flow.combinedFilters.value).toEqual({})
    })

    it('should accept target config', () => {
      const mockTarget = { applyFilters: vi.fn(), refresh: vi.fn() }
      const flow = useFilterFlow({ target: mockTarget })
      expect(flow.target.value).toEqual(mockTarget)
    })

    it('should expose all API methods', () => {
      const flow = useFilterFlow()
      
      expect(flow.registerSource).toBeDefined()
      expect(typeof flow.registerSource).toBe('function')
      
      expect(flow.unregisterSource).toBeDefined()
      expect(typeof flow.unregisterSource).toBe('function')
      
      expect(flow.getSource).toBeDefined()
      expect(typeof flow.getSource).toBe('function')
      
      expect(flow.registerTarget).toBeDefined()
      expect(typeof flow.registerTarget).toBe('function')
      
      expect(flow.refreshSourceAndDependents).toBeDefined()
      expect(typeof flow.refreshSourceAndDependents).toBe('function')
      
      expect(flow.applyFilters).toBeDefined()
      expect(typeof flow.applyFilters).toBe('function')
      
      expect(flow.refresh).toBeDefined()
      expect(typeof flow.refresh).toBe('function')
      
      expect(flow.refreshAll).toBeDefined()
      expect(typeof flow.refreshAll).toBe('function')
      
      expect(flow.clearAll).toBeDefined()
      expect(typeof flow.clearAll).toBe('function')
      
      expect(flow.dependencyGraph).toBeDefined()
      expect(flow.combinedFilters).toBeDefined()
      expect(flow.sources).toBeDefined()
    })
  })

  describe('source registration', () => {
    it('should register a source', () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      const source = createMockSource({ id: 'source-1' })
      
      flow.registerSource(source)
      
      expect(flow.sources.value).toHaveLength(1)
      expect(flow.getSource('source-1').id).toBe('source-1')
    })

    it('should register multiple sources', () => {
      const flow = useFilterFlow()
      
      flow.registerSource(createMockSource({ id: 's1' }))
      flow.registerSource(createMockSource({ id: 's2' }))
      flow.registerSource(createMockSource({ id: 's3' }))
      
      expect(flow.sources.value).toHaveLength(3)
    })

    it('should reject source without id', () => {
      const flow = useFilterFlow()
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      
      flow.registerSource({ type: 'filter' })
      
      expect(flow.sources.value).toHaveLength(0)
      expect(consoleSpy).toHaveBeenCalledWith(
        '[useFilterFlow] Invalid source: missing id'
      )
      
      consoleSpy.mockRestore()
    })

    it('should unregister a source', () => {
      const flow = useFilterFlow()
      const source = createMockSource({ id: 'source-1' })
      
      flow.registerSource(source)
      expect(flow.sources.value).toHaveLength(1)
      
      flow.unregisterSource('source-1')
      expect(flow.sources.value).toHaveLength(0)
      expect(flow.getSource('source-1')).toBeUndefined()
    })

    it('should handle unregistering non-existent source', () => {
      const flow = useFilterFlow()
      
      expect(() => flow.unregisterSource('non-existent')).not.toThrow()
    })
  })

  describe('filter aggregation - merge strategy', () => {
    it('should merge filter values from multiple sources', async () => {
      const flow = useFilterFlow({
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 'version',
        initialValue: { version_id: 1 }
      })
      const s2 = createMockSource({
        id: 'domain',
        initialValue: { domain_id: 5 },
        dependsOn: ['version']
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value).toEqual({
        version_id: 1,
        domain_id: 5
      })
    })

    it('should override same key with later source (merge)', async () => {
      const flow = useFilterFlow({
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 's1',
        initialValue: { status: 'active' }
      })
      const s2 = createMockSource({
        id: 's2',
        initialValue: { status: 'inactive' }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value.status).toBe('inactive')
    })

    it('should return empty object when no sources registered', () => {
      const flow = useFilterFlow()
      expect(flow.combinedFilters.value).toEqual({})
    })

    it('should skip sources with empty values', async () => {
      const flow = useFilterFlow({
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 'empty-source',
        initialValue: {}
      })
      const s2 = createMockSource({
        id: 'valid-source',
        initialValue: { key: 'value' }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value).toEqual({ key: 'value' })
    })

    it('should skip sources where ready is false', async () => {
      const flow = useFilterFlow({
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 'not-ready',
        initialValue: { should_be_ignored: true },
        ready: computed(() => false)
      })
      const s2 = createMockSource({
        id: 'ready',
        initialValue: { valid_key: true }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value).toEqual({ valid_key: true })
    })

    it('should include sources without ready property', async () => {
      const flow = useFilterFlow({
        autoRefreshDependencies: false
      })
      
      const sourceWithoutReady = {
        id: 'no-ready',
        type: 'filter',
        label: 'No Ready',
        value: ref({ data: 123 }),
        dependsOn: []
      }
      
      flow.registerSource(sourceWithoutReady)
      
      expect(flow.combinedFilters.value).toEqual({ data: 123 })
    })
  })

  describe('filter aggregation - intersect strategy', () => {
    it('should intersect array values', async () => {
      const flow = useFilterFlow({
        aggregator: { strategy: 'intersect' },
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 's1',
        initialValue: { ids: [1, 2, 3] }
      })
      const s2 = createMockSource({
        id: 's2',
        initialValue: { ids: [2, 3, 4] }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value.ids).toEqual([2, 3])
    })

    it('should intersect scalar values when all equal', async () => {
      const flow = useFilterFlow({
        aggregator: { strategy: 'intersect' },
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 's1',
        initialValue: { status: 'active' }
      })
      const s2 = createMockSource({
        id: 's2',
        initialValue: { status: 'active' }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value.status).toBe('active')
    })

    it('should exclude scalar values when not all equal', async () => {
      const flow = useFilterFlow({
        aggregator: { strategy: 'intersect' },
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 's1',
        initialValue: { status: 'active' }
      })
      const s2 = createMockSource({
        id: 's2',
        initialValue: { status: 'inactive' }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value.status).toBeUndefined()
    })

    it('should return empty intersection when arrays have no overlap', async () => {
      const flow = useFilterFlow({
        aggregator: { strategy: 'intersect' },
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({
        id: 's1',
        initialValue: { ids: [1, 2] }
      })
      const s2 = createMockSource({
        id: 's2',
        initialValue: { ids: [3, 4] }
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.combinedFilters.value.ids).toBeUndefined()
    })
  })

  describe('filter aggregation - custom strategy', () => {
    it('should use custom merge function when provided', async () => {
      const customMerge = vi.fn((values) => ({
        custom_result: values.length
      }))
      
      const flow = useFilterFlow({
        aggregator: { strategy: 'custom', customMerge },
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({ id: 's1', initialValue: { a: 1 } })
      const s2 = createMockSource({ id: 's2', initialValue: { b: 2 } })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      const result = flow.combinedFilters.value
      expect(result.custom_result).toBe(2)
    })

    it('should fallback to merge when custom function not provided', async () => {
      const flow = useFilterFlow({
        aggregator: { strategy: 'custom' },
        autoRefreshDependencies: false
      })
      
      const s1 = createMockSource({ id: 's1', initialValue: { x: 1 } })
      flow.registerSource(s1)
      
      expect(flow.combinedFilters.value.x).toBe(1)
    })
  })

  describe('dependency graph and topological sort', () => {
    it('should build correct dependency graph', () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const s1 = createMockSource({ id: 'a' })
      const s2 = createMockSource({ id: 'b', dependsOn: ['a'] })
      const s3 = createMockSource({ id: 'c', dependsOn: ['b'] })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      flow.registerSource(s3)
      
      const graph = flow.dependencyGraph.value
      
      expect(graph.hasCycle).toBe(false)
      expect(graph.dependencies.get('a')).toEqual([])
      expect(graph.dependencies.get('b')).toEqual(['a'])
      expect(graph.dependencies.get('c')).toEqual(['b'])
      
      expect(graph.dependents.get('a')).toEqual(['b'])
      expect(graph.dependents.get('b')).toEqual(['c'])
      expect(graph.dependents.get('c')).toEqual([])
    })

    it('should produce correct execution order via topological sort', () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const s1 = createMockSource({ id: 'root' })
      const s2 = createMockSource({ id: 'mid', dependsOn: ['root'] })
      const s3 = createMockSource({ id: 'leaf', dependsOn: ['mid'] })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      flow.registerSource(s3)
      
      const order = flow.dependencyGraph.value.executionOrder
      
      expect(order.indexOf('root')).toBeLessThan(order.indexOf('mid'))
      expect(order.indexOf('mid')).toBeLessThan(order.indexOf('leaf'))
    })

    it('should detect circular dependency', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const s1 = createMockSource({ id: 'a', dependsOn: ['b'] })
      const s2 = createMockSource({ id: 'b', dependsOn: ['a'] })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      expect(flow.dependencyGraph.value.hasCycle).toBe(true)
      expect(flow.dependencyGraph.value.cyclePath).toBeDefined()
      
      consoleSpy.mockRestore()
    })

    it('should detect self-loop as circular dependency', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const s1 = createMockSource({ id: 'self', dependsOn: ['self'] })
      flow.registerSource(s1)
      
      expect(flow.dependencyGraph.value.hasCycle).toBe(true)
      
      consoleSpy.mockRestore()
    })

    it('should handle complex diamond dependencies', () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const root = createMockSource({ id: 'root' })
      const b1 = createMockSource({ id: 'branch1', dependsOn: ['root'] })
      const b2 = createMockSource({ id: 'branch2', dependsOn: ['root'] })
      const leaf = createMockSource({ id: 'leaf', dependsOn: ['branch1', 'branch2'] })
      
      flow.registerSource(root)
      flow.registerSource(b1)
      flow.registerSource(b2)
      flow.registerSource(leaf)
      
      const graph = flow.dependencyGraph.value
      
      expect(graph.hasCycle).toBe(false)
      expect(graph.dependents.get('root').sort()).toEqual(['branch1', 'branch2'].sort())
      expect(graph.dependents.get('leaf')).toEqual([])
    })
  })

  describe('cascade refresh', () => {
    it('should call onDependencyChange for dependent sources', async () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const depChangeFn = vi.fn()
      const s1 = createMockSource({ id: 'parent', initialValue: { parent_val: 1 } })
      const s2 = createMockSource({
        id: 'child',
        dependsOn: ['parent'],
        onDependencyChange: depChangeFn
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      await flow.refreshSourceAndDependents('parent')
      
      expect(depChangeFn).toHaveBeenCalledTimes(1)
      const calledWithMap = depChangeFn.mock.calls[0][0]
      expect(calledWithMap).toBeInstanceOf(Map)
      expect(calledWithMap.get('parent')).toEqual({ parent_val: 1 })
    })

    it('should call refresh on dependent sources', async () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const refreshFn = vi.fn()
      const s1 = createMockSource({ id: 'parent' })
      const s2 = createMockSource({
        id: 'child',
        dependsOn: ['parent'],
        refresh: refreshFn
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      await flow.refreshSourceAndDependents('parent')
      
      expect(refreshFn).toHaveBeenCalledTimes(1)
    })

    it('should not refresh when circular dependency detected', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const refreshFn = vi.fn()
      const s1 = createMockSource({ id: 'a', dependsOn: ['b'], refresh: refreshFn })
      const s2 = createMockSource({ id: 'b', dependsOn: ['a'] })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      await flow.refreshSourceAndDependents('a')
      
      expect(refreshFn).not.toHaveBeenCalled()
      
      errorSpy.mockRestore()
      warnSpy.mockRestore()
    })

    it('should handle errors in onDependencyChange gracefully', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const failingFn = vi.fn(() => { throw new Error('test error') })
      const refreshFn = vi.fn()
      
      const s1 = createMockSource({ id: 'p' })
      const s2 = createMockSource({
        id: 'c',
        dependsOn: ['p'],
        onDependencyChange: failingFn,
        refresh: refreshFn
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      await expect(flow.refreshSourceAndDependents('p')).resolves.not.toThrow()
      expect(refreshFn).toHaveBeenCalled()
      
      errorSpy.mockRestore()
    })

    it('should cascade through multiple levels', async () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const callOrder = []
      
      const s1 = createMockSource({ id: 'l1' })
      const s2 = createMockSource({
        id: 'l2',
        dependsOn: ['l1'],
        refresh: () => callOrder.push('l2')
      })
      const s3 = createMockSource({
        id: 'l3',
        dependsOn: ['l2'],
        refresh: () => callOrder.push('l3')
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      flow.registerSource(s3)
      
      await flow.refreshSourceAndDependents('l1')
      
      expect(callOrder).toContain('l2')
      expect(callOrder).toContain('l3')
      expect(callOrder).toHaveLength(2)
    })
  })

  describe('target management', () => {
    it('should register target', () => {
      const flow = useFilterFlow()
      const target = { applyFilters: vi.fn(), refresh: vi.fn() }
      
      flow.registerTarget(target)
      
      expect(flow.target.value).toEqual(target)
    })

    it('should call applyFilters on target', () => {
      const target = { applyFilters: vi.fn(), refresh: vi.fn() }
      const flow = useFilterFlow({ target })
      
      flow.applyFilters()
      
      expect(target.applyFilters).toHaveBeenCalled()
    })

    it('should call refresh on target', () => {
      const target = { applyFilters: vi.fn(), refresh: vi.fn() }
      const flow = useFilterFlow({ target })
      
      flow.refresh()
      
      expect(target.refresh).toHaveBeenCalled()
    })

    it('should not throw when target has no applyFilters', () => {
      const flow = useFilterFlow({ target: {} })
      expect(() => flow.applyFilters()).not.toThrow()
    })

    it('should not throw when target is null', () => {
      const flow = useFilterFlow()
      expect(() => flow.applyFilters()).not.toThrow()
    })
  })

  describe('refreshAll', () => {
    it('should call refresh on all sources in order', async () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const callOrder = []
      
      const s1 = createMockSource({
        id: 'first',
        refresh: () => callOrder.push('first')
      })
      const s2 = createMockSource({
        id: 'second',
        dependsOn: ['first'],
        refresh: () => callOrder.push('second')
      })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      
      await flow.refreshAll()
      
      expect(callOrder).toEqual(['first', 'second'])
    })

    it('should skip sources without refresh method', async () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const s1 = createMockSource({ id: 'no-refresh' })
      flow.registerSource(s1)
      
      await expect(flow.refreshAll()).resolves.not.toThrow()
    })
  })

  describe('clearAll', () => {
    it('should call clear on all sources that have it', () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const clear1 = vi.fn()
      const clear2 = vi.fn()
      
      const s1 = createMockSource({ id: 's1' })
      s1.clear = clear1
      const s2 = createMockSource({ id: 's2' })
      s2.clear = clear2
      const s3 = createMockSource({ id: 's3' })
      
      flow.registerSource(s1)
      flow.registerSource(s2)
      flow.registerSource(s3)
      
      flow.clearAll()
      
      expect(clear1).toHaveBeenCalled()
      expect(clear2).toHaveBeenCalled()
    })
  })

  describe('dynamic updates', () => {
    it('should update combinedFilters when source value changes', async () => {
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const val = ref({ initial: true })
      const s1 = createMockSource({ id: 'dyn', value: val })
      
      flow.registerSource(s1)
      expect(flow.combinedFilters.value.initial).toBe(true)
      
      val.value = { updated: true }
      
      expect(flow.combinedFilters.value.updated).toBe(true)
    })
  })
})

describe('createFilterSource', () => {
  it('should create source with default values', () => {
    const source = createFilterSource({ id: 'test' })
    
    expect(source.id).toBe('test')
    expect(source.type).toBe('filter')
    expect(source.label).toBe('test')
    expect(source.dependsOn).toEqual([])
  })

  it('should create source with custom values', () => {
    const value = ref({ key: 'val' })
    const source = createFilterSource({
      id: 'custom',
      type: 'context',
      label: 'Custom Label',
      value,
      dependsOn: ['dep1'],
      loading: ref(true),
      ready: computed(() => false)
    })
    
    expect(source.id).toBe('custom')
    expect(source.type).toBe('context')
    expect(source.label).toBe('Custom Label')
    expect(source.dependsOn).toEqual(['dep1'])
  })

  it('should include optional properties when provided', () => {
    const onDepChange = vi.fn()
    const refresh = vi.fn()
    
    const source = createFilterSource({
      id: 'full',
      onDependencyChange: onDepChange,
      refresh
    })
    
    expect(typeof source.onDependencyChange).toBe('function')
    expect(typeof source.refresh).toBe('function')
  })
})
