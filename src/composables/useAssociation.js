/**
 * useAssociation - 关联操作 Composable
 * 
 * 提供关联操作的核心功能：
 * - 查询关联列表
 * - 分配/取消分配单个关联
 * - 批量分配/取消分配
 * - 统计关联数量
 * 
 * 设计原则：
 * - 统一使用 $associations v2 API
 * - 返回 204 的操作不返回 response body
 * - 遵循 YON_EP_GUIDE 设计规范
 */

import { ref, computed } from 'vue'
import boService from '@/services/boService'

export function useAssociation(objectType, options = {}) {
  const {
    associationName = null,
    sourceId = null
  } = options

  const items = ref([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref(null)
  const count = ref(0)
  const countLoading = ref(false)

  const selectedItems = ref([])
  const assigning = ref(false)
  const unassigning = ref(false)
  const batchAssigning = ref(false)
  const batchUnassigning = ref(false)

  const hasItems = computed(() => items.value.length > 0)
  const hasSelectedItems = computed(() => selectedItems.value.length > 0)

  async function queryAssociations(params = {}) {
    if (!associationName) {
      error.value = 'associationName is required'
      return null
    }

    loading.value = true
    error.value = null

    try {
      const result = await boService.queryAssociationsV2(
        objectType,
        sourceId.value,
        associationName,
        params
      )

      if (result.success) {
        items.value = result.data?.items || []
        total.value = result.data?.total || 0
        return result.data
      } else {
        error.value = result.message
        return null
      }
    } catch (e) {
      error.value = e.message || '查询关联失败'
      return null
    } finally {
      loading.value = false
    }
  }

  async function loadPage(page = 1, pageSize = 50) {
    return queryAssociations({ page, page_size: pageSize })
  }

  async function refresh() {
    return loadPage(1)
  }

  async function countAssociations() {
    if (!associationName) {
      error.value = 'associationName is required'
      return 0
    }

    countLoading.value = true
    error.value = null

    try {
      const result = await boService.countAssociationsV2(
        objectType,
        sourceId.value,
        associationName
      )

      if (result.success) {
        count.value = result.data?.count || 0
        return count.value
      } else {
        error.value = result.message
        return 0
      }
    } catch (e) {
      error.value = e.message || '统计关联数量失败'
      return 0
    } finally {
      countLoading.value = false
    }
  }

  async function assign(targetId, metadata = {}) {
    if (!associationName) {
      error.value = 'associationName is required'
      return false
    }

    assigning.value = true
    error.value = null

    try {
      const result = await boService.assignAssociationV2(
        objectType,
        sourceId.value,
        associationName,
        { target_id: targetId, metadata }
      )

      if (result.success || result === true) {
        await refresh()
        await countAssociations()
        return true
      } else {
        error.value = result.message || '分配失败'
        return false
      }
    } catch (e) {
      error.value = e.message || '分配失败'
      return false
    } finally {
      assigning.value = false
    }
  }

  async function unassign(targetId) {
    if (!associationName) {
      error.value = 'associationName is required'
      return false
    }

    unassigning.value = true
    error.value = null

    try {
      const result = await boService.unassignAssociationV2(
        objectType,
        sourceId.value,
        associationName,
        { association_record_id: targetId }
      )

      if (result.success || result === true) {
        await refresh()
        await countAssociations()
        return true
      } else {
        error.value = result.message || '取消分配失败'
        return false
      }
    } catch (e) {
      error.value = e.message || '取消分配失败'
      return false
    } finally {
      unassigning.value = false
    }
  }

  async function batchAssign(targetIds, metadata = {}) {
    if (!associationName) {
      error.value = 'associationName is required'
      return null
    }

    if (!targetIds || targetIds.length === 0) {
      error.value = 'targetIds is required'
      return null
    }

    batchAssigning.value = true
    error.value = null

    try {
      const result = await boService.batchAssignAssociationsV2(
        objectType,
        sourceId.value,
        associationName,
        { target_ids: targetIds, metadata }
      )

      if (result.success) {
        await refresh()
        await countAssociations()
        return result.data
      } else {
        error.value = result.message
        return null
      }
    } catch (e) {
      error.value = e.message || '批量分配失败'
      return null
    } finally {
      batchAssigning.value = false
    }
  }

  async function batchUnassign(targetIds, options = {}) {
    if (!associationName) {
      error.value = 'associationName is required'
      return null
    }

    if (!targetIds || targetIds.length === 0) {
      error.value = 'targetIds is required'
      return null
    }

    batchUnassigning.value = true
    error.value = null

    try {
      const params = options.useAssociationRecordIds 
        ? { association_record_ids: targetIds }
        : { target_ids: targetIds }
      
      const result = await boService.batchUnassignAssociationsV2(
        objectType,
        sourceId.value,
        associationName,
        params
      )

      if (result.success) {
        await refresh()
        await countAssociations()
        return result.data
      } else {
        error.value = result.message
        return null
      }
    } catch (e) {
      error.value = e.message || '批量取消分配失败'
      return null
    } finally {
      batchUnassigning.value = false
    }
  }

  function setSourceId(id) {
    sourceId.value = id
  }

  function setAssociationName(name) {
    associationName = name
  }

  function clearSelection() {
    selectedItems.value = []
  }

  function toggleSelection(item) {
    const index = selectedItems.value.findIndex(s => s.id === item.id)
    if (index >= 0) {
      selectedItems.value.splice(index, 1)
    } else {
      selectedItems.value.push(item)
    }
  }

  function selectAll() {
    selectedItems.value = [...items.value]
  }

  async function unassignSelected() {
    if (!hasSelectedItems.value) return false
    const ids = selectedItems.value.map(s => s.id)
    const result = await batchUnassign(ids, { useAssociationRecordIds: true })
    if (result) {
      clearSelection()
    }
    return !!result
  }

  return {
    items,
    total,
    loading,
    error,
    count,
    countLoading,
    selectedItems,
    assigning,
    unassigning,
    batchAssigning,
    batchUnassigning,
    hasItems,
    hasSelectedItems,
    queryAssociations,
    loadPage,
    refresh,
    countAssociations,
    assign,
    unassign,
    batchAssign,
    batchUnassign,
    setSourceId,
    setAssociationName,
    clearSelection,
    toggleSelection,
    selectAll,
    unassignSelected
  }
}

export default useAssociation
