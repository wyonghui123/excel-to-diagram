/**
 * useScopeFilterSource - 范围过滤源 Composable
 *
 * 用于创建基于范围（如关系范围）的过滤源
 * 特点:
 * 1. 从 YAML hierarchies.hierarchy_scopes 读取配置
 * 2. 支持业务对象范围选择
 * 3. 关系范围分类为计算字段
 *
 * @example
 * const scopeSource = useScopeFilterSource({
 *   id: 'relation-scope',
 *   metaObject: metaObjectRef
 * })
 *
 * filterFlow.registerSource(scopeSource.source)
 * scopeSource.selectedBoIds.value = [1, 2, 3]
 */
import { ref, computed, unref } from 'vue'
import { createFilterSource } from '../useFilterFlow.js'

export function useScopeFilterSource(options = {}) {
  const {
    id = 'scope',
    label = 'Scope',
    metaObject = null,
    dependsOn = [],
    icon = 'link',
    description = ''
  } = options

  const selectedBoIds = ref([])
  const selectedRelationCodes = ref([])
  const selectedRelationIds = ref([])
  const selectedCategoryTypes = ref([])
  const loading = ref(false)

  const scopeConfig = computed(() => {
    const meta = unref(metaObject)
    return meta?.hierarchy_scopes || []
  })

  const computedCategoryTypes = computed(() => {
    if (selectedCategoryTypes.value.length > 0) {
      return selectedCategoryTypes.value
    }

    if (selectedBoIds.value.length === 0) return []

    return []
  })

  const value = computed(() => {
    const filters = {}
    const boIds = selectedBoIds.value
    const relCodes = selectedRelationCodes.value
    const relIds = selectedRelationIds.value
    const catTypes = computedCategoryTypes.value

    if (boIds && boIds.length > 0) {
      filters.source_bo_ids = [...boIds]
      filters.target_bo_ids = [...boIds]
    }

    // [FIX v3.18 2026-06-10] 字段名统一为 `id__in`（与 buildRelationshipFilterParams 对齐）：
    //   原实现用 `id: [1,2,3]`，但后端 _build_in_filter 只识别 `id__in`（逗号字符串）。
    //   导致同一个过滤意图用 `id` 数组 + `id__in` 字符串双重下发，
    //   URL 出现 `id=1&id=2&id=3&id__in=1,2,3`，后端只识别 `id__in`，但语义混乱。
    //   改用 `id__in` 后，filterFlow 合并时进 scopeFilterKeys 的删除列表，
    //   再由 buildRelationshipFilterParams 重新加回 (统一逗号字符串格式)。
    if (relIds && relIds.length > 0) {
      filters.id__in = [...relIds]
    } else if (relCodes && relCodes.length > 0) {
      filters.relation_codes = [...relCodes]
    }

    if (catTypes && catTypes.length > 0) {
      filters.category_types = [...catTypes]
    }

    return filters
  })

  const meta = computed(() => ({
    fields: [
      {
        key: 'source_bo_ids',
        label: 'Source Business Objects',
        type: 'array',
        operator: 'in'
      },
      {
        key: 'target_bo_ids',
        label: 'Target Business Objects',
        type: 'array',
        operator: 'in'
      },
      {
        key: 'relation_codes',
        label: 'Relation Types',
        type: 'array',
        operator: 'in'
      },
      {
        key: 'relation_ids',
        label: 'Relation IDs',
        type: 'array',
        operator: 'in'
      },
      {
        key: 'category_types',
        label: 'Scope Categories',
        type: 'array',
        operator: 'in'
      }
    ],
    icon,
    description: description || `${label} scope filter`
  }))

  const ready = computed(() => true)

  function setBusinessObjectIds(ids) {
    // [FIX] 只在值真正变化时才更新，避免触发不必要的 watcher
    const current = selectedBoIds.value
    if (ids === current) return
    if (Array.isArray(ids) && Array.isArray(current) &&
        ids.length === current.length &&
        ids.every((id, i) => id === current[i])) return
    selectedBoIds.value = ids
  }

  function setRelationCodes(codes) {
    // [FIX] 只在值真正变化时才更新
    const current = selectedRelationCodes.value
    if (codes === current) return
    if (Array.isArray(codes) && Array.isArray(current) &&
        codes.length === current.length &&
        codes.every((c, i) => c === current[i])) return
    selectedRelationCodes.value = codes
  }

  function setRelationIds(ids) {
    // [FIX] 只在值真正变化时才更新
    const current = selectedRelationIds.value
    if (ids === current) return
    if (Array.isArray(ids) && Array.isArray(current) &&
        ids.length === current.length &&
        ids.every((id, i) => id === current[i])) return
    selectedRelationIds.value = ids
  }

  function setCategoryTypes(types) {
    selectedCategoryTypes.value = types
  }

  function clear() {
    selectedBoIds.value = []
    selectedRelationCodes.value = []
    selectedRelationIds.value = []
    selectedCategoryTypes.value = []
  }

  function clearBusinessObjects() {
    selectedBoIds.value = []
  }

  function clearRelationCodes() {
    selectedRelationCodes.value = []
    selectedRelationIds.value = []
  }

  function clearCategoryTypes() {
    selectedCategoryTypes.value = []
  }

  async function onDependencyChange(dependencyValues) {
    const allIds = []
    for (const [depId, depValue] of dependencyValues) {
      if (depValue.bo_ids) {
        allIds.push(...depValue.bo_ids)
      } else if (depValue.node_ids) {
        allIds.push(...depValue.node_ids)
      }
    }
    if (allIds.length > 0) {
      selectedBoIds.value = allIds
    }
  }

  const source = createFilterSource({
    id,
    type: 'scope',
    label,
    value,
    dependsOn,
    onDependencyChange,
    loading,
    ready,
    meta,
    clear
  })

  return {
    source,
    value,
    scopeConfig,
    selectedBoIds,
    selectedRelationCodes,
    selectedRelationIds,
    selectedCategoryTypes,
    computedCategoryTypes,
    loading,
    ready,
    meta,
    setBusinessObjectIds,
    setRelationCodes,
    setRelationIds,
    setCategoryTypes,
    clear,
    clearBusinessObjects,
    clearRelationCodes,
    clearCategoryTypes
  }
}
