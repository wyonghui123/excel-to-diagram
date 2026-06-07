/**
 * useFilterFlow - 通用过滤流管理器
 *
 * 支持多个过滤源(FilterSource)的级联依赖和聚合:
 * 1. 过滤源注册/注销
 * 2. 级联依赖处理(Source A -> Source B -> Source C)
 * 3. 过滤条件聚合
 * 4. 自动/手动刷新控制
 *
 * @example
 * const filterFlow = useFilterFlow({
 *   aggregator: { strategy: 'merge' },
 *   autoRefreshDependencies: true,
 *   refreshMode: 'debounced'
 * })
 *
 * // 注册过滤源
 * filterFlow.registerSource(versionSource)
 * filterFlow.registerSource(treeSource)
 *
 * // 获取聚合后的过滤条件
 * console.log(filterFlow.combinedFilters.value)
 */
import { computed, ref, watch, unref, nextTick, isRef } from 'vue'

function deepUnwrap(obj) {
  if (obj === null || obj === undefined) return obj
  if (isRef(obj)) return deepUnwrap(obj.value)
  if (Array.isArray(obj)) {
    return obj.map(item => deepUnwrap(item))
  }
  if (typeof obj === 'object') {
    const result = {}
    for (const [key, val] of Object.entries(obj)) {
      result[key] = deepUnwrap(val)
    }
    return result
  }
  return obj
}

export function useFilterFlow(config = {}) {
  const {
    aggregator = { strategy: 'merge' },
    target = null,
    autoRefreshDependencies = true,
    refreshMode = 'immediate',
    refreshDebounce = 300
  } = config

  const registeredSources = ref(new Map())
  const registeredTarget = ref(target)

  let debounceTimer = null

  function buildDependencyGraph(sources) {
    const dependents = new Map()
    const dependencies = new Map()

    for (const [id] of sources) {
      dependents.set(id, [])
      dependencies.set(id, [])
    }

    for (const [id, source] of sources) {
      if (source.dependsOn && source.dependsOn.length > 0) {
        dependencies.set(id, [...source.dependsOn])

        for (const depId of source.dependsOn) {
          const depList = dependents.get(depId) || []
          depList.push(id)
          dependents.set(depId, depList)
        }
      }
    }

    const { order, hasCycle, cyclePath } = topologicalSort(sources, dependencies)

    return {
      dependents,
      dependencies,
      executionOrder: order,
      hasCycle,
      cyclePath
    }
  }

  function topologicalSort(sources, dependencies) {
    const visited = new Set()
    const visiting = new Set()
    const order = []
    let cyclePath = undefined

    function visit(id, path) {
      if (visited.has(id)) return true
      if (visiting.has(id)) {
        cyclePath = [...path, id]
        return false
      }

      visiting.add(id)

      const deps = dependencies.get(id) || []
      for (const depId of deps) {
        if (!visit(depId, [...path, id])) {
          return false
        }
      }

      visiting.delete(id)
      visited.add(id)
      order.push(id)
      return true
    }

    for (const [id] of sources) {
      if (!visited.has(id)) {
        if (!visit(id, [])) {
          return { order: [], hasCycle: true, cyclePath }
        }
      }
    }

    return { order, hasCycle: false }
  }

  const dependencyGraph = computed(() => {
    return buildDependencyGraph(registeredSources.value)
  })

  function getSourcesToRefresh(sourceId, graph) {
    const result = []
    const visited = new Set()

    function collect(id) {
      if (visited.has(id)) return
      visited.add(id)

      const deps = graph.dependents.get(id) || []
      for (const depId of deps) {
        collect(depId)
      }

      if (id !== sourceId) {
        result.push(id)
      }
    }

    collect(sourceId)
    return result
  }

  async function refreshSourceAndDependents(sourceId) {
    const graph = dependencyGraph.value

    if (graph.hasCycle) {
      console.error('[useFilterFlow] Circular dependency detected:', graph.cyclePath)
      return
    }

    const toRefresh = getSourcesToRefresh(sourceId, graph)

    for (const id of toRefresh) {
      const source = registeredSources.value.get(id)
      if (source) {
        const depValues = new Map()
        if (source.dependsOn) {
          for (const depId of source.dependsOn) {
            const depSource = registeredSources.value.get(depId)
            if (depSource) {
              depValues.set(depId, unref(depSource.value))
            }
          }
        }

        if (source.onDependencyChange) {
          try {
            await source.onDependencyChange(depValues)
          } catch (e) {
            console.error(`[useFilterFlow] Error in onDependencyChange for ${id}:`, e)
          }
        }

        if (source.refresh) {
          try {
            await source.refresh()
          } catch (e) {
            console.error(`[useFilterFlow] Error refreshing ${id}:`, e)
          }
        }
      }
    }
  }

  function registerSource(source) {
    if (!source || !source.id) {
      console.error('[useFilterFlow] Invalid source: missing id')
      return
    }

    registeredSources.value.set(source.id, source)

    const graph = dependencyGraph.value
    if (graph.hasCycle) {
      console.warn(`[useFilterFlow] Circular dependency detected after registering ${source.id}:`, graph.cyclePath)
    }

    if (autoRefreshDependencies) {
      setupSourceWatcher(source)
    }
  }

  function unregisterSource(sourceId) {
    registeredSources.value.delete(sourceId)
  }

  function getSource(sourceId) {
    return registeredSources.value.get(sourceId)
  }

  const sourceWatchers = new Map()

  function setupSourceWatcher(source) {
    if (sourceWatchers.has(source.id)) {
      sourceWatchers.get(source.id)()
    }

    const stopWatch = watch(
      () => unref(source.value),
      () => {
        if (refreshMode === 'immediate') {
          refreshSourceAndDependents(source.id)
        } else if (refreshMode === 'debounced') {
          if (debounceTimer) {
            clearTimeout(debounceTimer)
          }
          debounceTimer = setTimeout(() => {
            refreshSourceAndDependents(source.id)
          }, refreshDebounce)
        }
      },
      { deep: true }
    )

    sourceWatchers.set(source.id, stopWatch)
  }

  function intersectFilters(sourceValues) {
    const result = {}

    const allKeys = new Set()
    for (const val of sourceValues) {
      Object.keys(val).forEach(k => allKeys.add(k))
    }

    for (const key of allKeys) {
      const valuesForKey = sourceValues
        .filter(v => v[key] !== undefined)
        .map(v => v[key])

      if (valuesForKey.length === 0) continue

      const firstVal = valuesForKey[0]

      if (Array.isArray(firstVal)) {
        const intersection = valuesForKey.reduce(
          (acc, val) => acc.filter(item => val.includes(item)),
          firstVal
        )
        if (intersection.length > 0) {
          result[key] = intersection
        }
      } else {
        const allEqual = valuesForKey.every(v => v === firstVal)
        if (allEqual) {
          result[key] = firstVal
        }
      }
    }

    return result
  }

  const combinedFilters = computed(() => {
    const sourceValues = Array.from(registeredSources.value.values())
      .filter(s => {
        if (s.ready !== undefined) {
          return unref(s.ready)
        }
        return true
      })
      .map(s => deepUnwrap(unref(s.value)))
      .filter(v => v && Object.keys(v).length > 0)

    if (sourceValues.length === 0) return {}

    switch (aggregator.strategy) {
      case 'merge':
        return sourceValues.reduce((acc, val) => ({ ...acc, ...val }), {})

      case 'intersect':
        return intersectFilters(sourceValues)

      case 'custom':
        if (aggregator.customMerge) {
          return aggregator.customMerge(sourceValues)
        }
        return sourceValues.reduce((acc, val) => ({ ...acc, ...val }), {})

      default:
        return sourceValues.reduce((acc, val) => ({ ...acc, ...val }), {})
    }
  })

  function registerTarget(t) {
    registeredTarget.value = t
  }

  function applyFilters() {
    const t = registeredTarget.value
    if (t && t.applyFilters) {
      t.applyFilters(combinedFilters.value)
    }
  }

  function refresh() {
    const t = registeredTarget.value
    if (t && t.refresh) {
      t.refresh()
    }
  }

  watch(combinedFilters, () => {
    nextTick(() => {
      applyFilters()
    })
  }, { deep: true })

  async function refreshAll() {
    const order = dependencyGraph.value.executionOrder

    for (const id of order) {
      const source = registeredSources.value.get(id)
      if (source && source.refresh) {
        try {
          await source.refresh()
        } catch (e) {
          console.error(`[useFilterFlow] Error refreshing ${id}:`, e)
        }
      }
    }
  }

  function clearAll() {
    for (const [id, source] of registeredSources.value) {
      if (source.clear) {
        source.clear()
      }
    }
  }

  return {
    registerSource,
    unregisterSource,
    getSource,
    sources: computed(() => Array.from(registeredSources.value.values())),

    registerTarget,
    target: registeredTarget,

    dependencyGraph,

    combinedFilters,

    refreshSourceAndDependents,
    applyFilters,
    refresh,
    refreshAll,
    clearAll
  }
}

export function createFilterSource(options) {
  const {
    id,
    type = 'filter',
    label = id,
    value,
    dependsOn = [],
    onDependencyChange,
    refresh,
    loading,
    ready,
    meta
  } = options

  return {
    id,
    type,
    label,
    value,
    dependsOn,
    onDependencyChange,
    refresh,
    loading,
    ready,
    meta
  }
}
