/**
 * useTreeFilterSource - 树形过滤源 Composable
 *
 * 用于创建基于树形结构（如层级树）的过滤源
 * 支持:
 * 1. 节点选择/勾选
 * 2. 级联依赖（依赖其他过滤源的值）
 * 3. 数据刷新
 *
 * @example
 * const treeSource = useTreeFilterSource({
 *   id: 'bo-tree',
 *   type: 'hierarchy',
 *   config: configRef,
 *   fetchData: async (params) => { ... }
 * })
 *
 * filterFlow.registerSource(treeSource.source)
 */
import { ref, computed, unref } from 'vue'
import { createFilterSource } from '../useFilterFlow.js'

export function useTreeFilterSource(options = {}) {
  const {
    id = 'tree',
    type = 'hierarchy',
    label = 'Tree',
    config = null,
    dependsOn = [],
    fetchData = null,
    initialData = [],
    icon = 'folder',
    description = '',
    filterFieldBuilder = null
  } = options

  const selectedNodes = ref([])
  const checkedNodeIds = ref([])
  const treeData = ref(initialData)
  const loading = ref(false)
  const expandedKeys = ref([])

  const ready = computed(() => treeData.value.length > 0)

  function buildDefaultFilter(checkedIds, configValue) {
    if (!checkedIds || checkedIds.length === 0) return {}

    if (filterFieldBuilder) {
      return filterFieldBuilder(checkedIds, configValue)
    }

    if (type === 'hierarchy') {
      const cfg = configValue || unref(config)
      const filterField = cfg?.filter_field || 'parent_id'

      if (checkedIds.length === 1) {
        return { [filterField]: checkedIds[0] }
      } else {
        return { [`${filterField}__in`]: checkedIds }
      }
    }

    return { node_ids: checkedIds }
  }

  const value = computed(() => {
    return buildDefaultFilter(checkedNodeIds.value, unref(config))
  })

  const meta = computed(() => {
    const cfg = unref(config) || {}
    return {
      fields: cfg.filterFields || [
        {
          key: 'node_ids',
          label: label,
          type: 'array',
          operator: 'in'
        }
      ],
      icon,
      description: description || `${label} tree filter`
    }
  })

  async function refresh(params = {}) {
    if (!fetchData) return

    loading.value = true
    try {
      const result = await fetchData({
        ...params,
        checkedIds: checkedNodeIds.value
      })
      treeData.value = result || []
    } catch (e) {
      console.error(`[useTreeFilterSource] Error refreshing ${id}:`, e)
    } finally {
      loading.value = false
    }
  }

  async function onDependencyChange(dependencyValues) {
    if (!fetchData) return

    const params = {}
    for (const [depId, depValue] of dependencyValues) {
      Object.assign(params, depValue)
    }

    await refresh(params)
  }

  function handleNodeSelect(node) {
    selectedNodes.value = [node]
  }

  function handleNodeCheck(ids) {
    checkedNodeIds.value = ids
  }

  function handleExpand(keys) {
    expandedKeys.value = keys
  }

  function clear() {
    selectedNodes.value = []
    checkedNodeIds.value = []
  }

  function selectAll() {
    const allIds = collectAllIds(treeData.value)
    checkedNodeIds.value = allIds
  }

  function collectAllIds(nodes, ids = []) {
    for (const node of nodes) {
      if (node.id !== undefined) {
        ids.push(node.id)
      }
      if (node.children && node.children.length > 0) {
        collectAllIds(node.children, ids)
      }
    }
    return ids
  }

  const source = createFilterSource({
    id,
    type: 'tree',
    label,
    value,
    dependsOn,
    onDependencyChange,
    refresh,
    loading,
    ready,
    meta,
    clear
  })

  return {
    source,
    value,
    selectedNodes,
    checkedNodeIds,
    treeData,
    loading,
    ready,
    expandedKeys,
    meta,
    handleNodeSelect,
    handleNodeCheck,
    handleExpand,
    selectAll,
    clear,
    refresh
  }
}
