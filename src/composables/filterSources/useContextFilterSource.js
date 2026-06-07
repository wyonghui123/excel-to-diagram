/**
 * useContextFilterSource - 上下文过滤源 Composable
 *
 * 用于创建基于上下文（如版本）的过滤源
 * 实现 FilterSource 接口，可与 useFilterFlow 配合使用
 *
 * @example
 * const contextSource = useContextFilterSource({
 *   id: 'version-context',
 *   contextField: 'version_id'
 * })
 *
 * filterFlow.registerSource(contextSource.source)
 * contextSource.setContext(1)  // 设置版本 ID
 */
import { ref, computed } from 'vue'
import { createFilterSource } from '../useFilterFlow.js'

export function useContextFilterSource(options = {}) {
  const {
    id = 'context',
    contextField = 'version_id',
    label = 'Context',
    icon = 'calendar',
    description = ''
  } = options

  const contextValue = ref(null)

  const value = computed(() => {
    const ctx = contextValue.value
    if (ctx === null || ctx === undefined) return {}
    return { [contextField]: ctx }
  })

  const meta = computed(() => ({
    fields: [
      {
        key: contextField,
        label: label,
        type: 'scalar',
        operator: 'eq'
      }
    ],
    icon,
    description: description || `${label} context filter`
  }))

  const loading = ref(false)

  const ready = computed(() => !!contextValue.value)

  function setContext(value) {
    contextValue.value = value
  }

  function clear() {
    contextValue.value = null
  }

  const source = createFilterSource({
    id,
    type: 'context',
    label,
    value,
    dependsOn: [],
    loading,
    ready,
    meta,
    clear
  })

  return {
    source,
    value,
    contextValue,
    loading,
    ready,
    meta,
    setContext,
    clear
  }
}
