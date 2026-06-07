/**
 * useTreeFilterSource.spec.js - 树形过滤源测试
 *
 * 测试核心功能：
 * 1. 初始状态和配置
 * 2. 过滤值生成（hierarchy 和 scope 类型）
 * 3. 节点选择/勾选处理
 * 4. 树数据管理
 * 5. ready 状态
 * 6. 自定义 filterFieldBuilder
 * 7. FilterSource 接口实现
 */

import { describe, it, expect, vi } from 'vitest'
import { ref, computed } from 'vue'
import { useTreeFilterSource } from '@/composables/filterSources/useTreeFilterSource'

const MOCK_TREE_DATA = [
  {
    id: 1,
    name: 'Root',
    type: 'domain',
    children: [
      { id: 2, name: 'Child 1', type: 'sub_domain', children: [] },
      { id: 3, name: 'Child 2', type: 'sub_domain', children: [] }
    ]
  }
]

function createMockFetchData(data = MOCK_TREE_DATA) {
  return vi.fn(async () => data)
}

describe('useTreeFilterSource', () => {
  describe('initial state', () => {
    it('should initialize with default values', () => {
      const source = useTreeFilterSource()
      
      expect(source.source.id).toBe('tree')
      expect(source.source.type).toBe('tree')
      expect(source.selectedNodes.value).toEqual([])
      expect(source.checkedNodeIds.value).toEqual([])
      expect(source.treeData.value).toEqual([])
      expect(source.loading.value).toBe(false)
    })

    it('should use custom id when provided', () => {
      const source = useTreeFilterSource({ id: 'bo-tree' })
      expect(source.source.id).toBe('bo-tree')
    })

    it('should use hierarchy type by default', () => {
      const source = useTreeFilterSource({ type: 'hierarchy' })
      expect(source.source.type).toBe('tree')
    })

    it('should accept initial data', () => {
      const source = useTreeFilterSource({
        initialData: [{ id: 1, name: 'Test' }]
      })
      
      expect(source.treeData.value).toHaveLength(1)
    })

    it('should expose all required methods and properties', () => {
      const source = useTreeFilterSource()
      
      expect(source.handleNodeSelect).toBeDefined()
      expect(typeof source.handleNodeSelect).toBe('function')
      
      expect(source.handleNodeCheck).toBeDefined()
      expect(typeof source.handleNodeCheck).toBe('function')
      
      expect(source.handleExpand).toBeDefined()
      expect(typeof source.handleExpand).toBe('function')
      
      expect(source.selectAll).toBeDefined()
      expect(typeof source.selectAll).toBe('function')
      
      expect(source.clear).toBeDefined()
      expect(typeof source.clear).toBe('function')
      
      expect(source.refresh).toBeDefined()
      expect(typeof source.refresh).toBe('function')
    })
  })

  describe('filter value generation - hierarchy type', () => {
    it('should return empty object when no nodes checked', () => {
      const source = useTreeFilterSource({
        type: 'hierarchy',
        config: ref({ filter_field: 'parent_id' })
      })
      
      expect(source.value.value).toEqual({})
    })

    it('should generate parent_id filter for single selection (hierarchy)', () => {
      const source = useTreeFilterSource({
        type: 'hierarchy',
        config: ref({ filter_field: 'parent_id' })
      })
      
      source.handleNodeCheck([5])
      
      expect(source.value.value.parent_id).toBe(5)
    })

    it('should generate parent_id__in filter for multiple selections (hierarchy)', () => {
      const source = useTreeFilterSource({
        type: 'hierarchy',
        config: ref({ filter_field: 'parent_id' })
      })

      source.handleNodeCheck([1, 2, 3])

      // 源码：多选用 `${filterField}__in` 后缀（不是 plural 'parent_ids'）
      expect(source.value.value.parent_id__in).toEqual([1, 2, 3])
    })

    it('should use default filter_field when not in config', () => {
      const source = useTreeFilterSource({
        type: 'hierarchy'
      })
      
      source.handleNodeCheck([10])
      expect(source.value.value.parent_id).toBe(10)
    })
  })

  describe('filter value generation - scope type', () => {
    it('should generate node_ids filter for scope type', () => {
      const source = useTreeFilterSource({
        type: 'scope',
        config: ref({})
      })
      
      source.handleNodeCheck([100, 200])
      
      expect(source.value.value.node_ids).toEqual([100, 200])
    })

    it('should handle single node check for scope type', () => {
      const source = useTreeFilterSource({
        type: 'scope'
      })
      
      source.handleNodeCheck([42])
      expect(source.value.value.node_ids).toEqual([42])
    })
  })

  describe('custom filterFieldBuilder', () => {
    it('should use custom builder when provided', () => {
      const customBuilder = (ids, config) => ({
        custom_field: ids,
        extra: 'data'
      })
      
      const configRef = ref({ test: true })
      const source = useTreeFilterSource({
        filterFieldBuilder: customBuilder,
        config: configRef
      })
      
      source.handleNodeCheck([1, 2])
      
      expect(source.value.value.custom_field).toEqual([1, 2])
      expect(source.value.value.extra).toBe('data')
    })
  })

  describe('node selection handling', () => {
    it('handleNodeSelect should update selectedNodes', () => {
      const source = useTreeFilterSource()
      const node = { id: 1, name: 'Node 1' }
      
      source.handleNodeSelect(node)
      
      expect(source.selectedNodes.value).toEqual([node])
    })

    it('handleNodeSelect should replace previous selection', () => {
      const source = useTreeFilterSource()
      
      source.handleNodeSelect({ id: 1, name: 'First' })
      source.handleNodeSelect({ id: 2, name: 'Second' })
      
      expect(source.selectedNodes.value).toHaveLength(1)
      expect(source.selectedNodes.value[0].id).toBe(2)
    })

    it('handleNodeCheck should update checkedNodeIds', () => {
      const source = useTreeFilterSource()
      
      source.handleNodeCheck([10, 20, 30])
      
      expect(source.checkedNodeIds.value).toEqual([10, 20, 30])
    })

    it('handleNodeCheck should replace previous checks', () => {
      const source = useTreeFilterSource()
      
      source.handleNodeCheck([1, 2])
      source.handleNodeCheck([3, 4])
      
      expect(source.checkedNodeIds.value).toEqual([3, 4])
    })
  })

  describe('expand/collapse handling', () => {
    it('handleExpand should update expandedKeys', () => {
      const source = useTreeFilterSource()
      
      source.handleExpand(['node-1', 'node-2'])
      
      expect(source.expandedKeys.value).toEqual(['node-1', 'node-2'])
    })
  })

  describe('selectAll method', () => {
    it('should select all node IDs from tree data', () => {
      const source = useTreeFilterSource({
        initialData: [
          { id: 1, children: [{ id: 2 }, { id: 3 }] },
          { id: 4, children: [] }
        ]
      })
      
      source.selectAll()
      
      expect(source.checkedNodeIds.value).toContain(1)
      expect(source.checkedNodeIds.value).toContain(2)
      expect(source.checkedNodeIds.value).toContain(3)
      expect(source.checkedNodeIds.value).toContain(4)
      expect(source.checkedNodeIds.value).toHaveLength(4)
    })

    it('should work with empty tree data', () => {
      const source = useTreeFilterSource()
      
      source.selectAll()
      
      expect(source.checkedNodeIds.value).toEqual([])
    })
  })

  describe('clear method', () => {
    it('should reset selectedNodes', () => {
      const source = useTreeFilterSource()
      source.handleNodeSelect({ id: 1 })
      
      source.clear()
      
      expect(source.selectedNodes.value).toEqual([])
    })

    it('should reset checkedNodeIds', () => {
      const source = useTreeFilterSource()
      source.handleNodeCheck([1, 2, 3])
      
      source.clear()
      
      expect(source.checkedNodeIds.value).toEqual([])
    })

    it('should clear filter value', () => {
      const source = useTreeFilterSource({ type: 'hierarchy' })
      source.handleNodeCheck([5])
      expect(source.value.value.parent_id).toBe(5)
      
      source.clear()
      
      expect(source.value.value).toEqual({})
    })
  })

  describe('ready state', () => {
    it('should be false when tree data is empty', () => {
      const source = useTreeFilterSource()
      expect(source.ready.value).toBe(false)
    })

    it('should be true when tree data has items', () => {
      const source = useTreeFilterSource({
        initialData: [{ id: 1 }]
      })
      expect(source.ready.value).toBe(true)
    })

    it('should toggle as tree data changes', async () => {
      const fetchData = createMockFetchData([{ id: 1 }])
      const source = useTreeFilterSource({ fetchData })
      
      expect(source.ready.value).toBe(false)
      
      await source.refresh()
      
      expect(source.ready.value).toBe(true)
    })
  })

  describe('refresh method', () => {
    it('should call fetchData with params', async () => {
      const fetchData = createMockFetchData(MOCK_TREE_DATA)
      const source = useTreeFilterSource({ fetchData })
      
      await source.refresh({ version_id: 1 })
      
      expect(fetchData).toHaveBeenCalled()
      const callArgs = fetchData.mock.calls[0][0]
      expect(callArgs.version_id).toBe(1)
    })

    it('should update treeData after refresh', async () => {
      const newData = [{ id: 99, name: 'New Data' }]
      const fetchData = createMockFetchData(newData)
      const source = useTreeFilterSource({ fetchData })
      
      await source.refresh()
      
      expect(source.treeData.value).toEqual(newData)
    })

    it('should set loading state during refresh', async () => {
      let resolvePromise
      const fetchData = vi.fn(() => new Promise(resolve => {
        resolvePromise = resolve
      }))
      const source = useTreeFilterSource({ fetchData })
      
      const refreshPromise = source.refresh()
      
      expect(source.loading.value).toBe(true)
      
      resolvePromise(MOCK_TREE_DATA)
      await refreshPromise
      
      expect(source.loading.value).toBe(false)
    })

    it('should handle fetch errors gracefully', async () => {
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const fetchData = vi.fn(() => Promise.reject(new Error('Network error')))
      const source = useTreeFilterSource({ fetchData })
      
      await expect(source.refresh()).resolves.not.toThrow()
      
      errorSpy.mockRestore()
    })
  })

  describe('meta metadata', () => {
    it('should have default icon folder', () => {
      const source = useTreeFilterSource()
      expect(source.meta.value.icon).toBe('folder')
    })

    it('should use custom icon from options', () => {
      const source = useTreeFilterSource({ icon: 'custom-icon' })
      expect(source.meta.value.icon).toBe('custom-icon')
    })

    it('should include description', () => {
      const source = useTreeFilterSource({ label: 'My Tree' })
      expect(source.meta.value.description).toContain('My Tree')
    })

    it('should have fields from config or defaults', () => {
      const source = useTreeFilterSource({
        config: ref({
          filterFields: [{ key: 'node_ids', label: 'Nodes' }]
        })
      })
      
      expect(source.meta.value.fields[0].key).toBe('node_ids')
    })
  })

  describe('FilterSource interface compliance', () => {
    it('should have all required FilterSource properties', () => {
      const source = useTreeFilterSource({ id: 'my-tree' })
      const fs = source.source
      
      expect(fs.id).toBe('my-tree')
      expect(fs.type).toBe('tree')
      expect(fs.label).toBeDefined()
      expect(fs.value).toBeDefined()
      expect(fs.dependsOn).toBeDefined()
      expect(Array.isArray(fs.dependsOn)).toBe(true)
      expect(fs.loading).toBeDefined()
      expect(fs.ready).toBeDefined()
      expect(fs.meta).toBeDefined()
    })

    it('should support dependsOn configuration', () => {
      const source = useTreeFilterSource({
        dependsOn: ['version-context']
      })
      
      expect(source.source.dependsOn).toEqual(['version-context'])
    })

    it('should support onDependencyChange callback', async () => {
      const fetchData = vi.fn(async () => [{ id: 1 }])
      const source = useTreeFilterSource({
        dependsOn: ['version'],
        fetchData
      })
      
      const depMap = new Map([['version', { version_id: 1 }]])
      await source.source.onDependencyChange(depMap)
      
      expect(fetchData).toHaveBeenCalled()
    })

    it('should be usable in useFilterFlow', async () => {
      const { useFilterFlow } = await import('@/composables/useFilterFlow')
      const flow = useFilterFlow({ autoRefreshDependencies: false })
      
      const treeSource = useTreeFilterSource({
        id: 'domain-tree',
        type: 'hierarchy',
        config: ref({ filter_field: 'domain_id' }),
        initialData: [{ id: 1 }]
      })
      treeSource.handleNodeCheck([5])
      
      flow.registerSource(treeSource.source)
      
      expect(flow.combinedFilters.value.domain_id).toBe(5)
    })
  })
})
