/**
 * useAuditLogs - 审计日志 Composable
 *
 * 委托给 auditLogService（FR-UI-012）
 * 移除了 queryAssociations(..., 'audit_logs', ...) 反模式
 *
 * @example
 * // 拉角色自身日志 (向后兼容)
 * const { logs, total, loading, loadLogs, setFilters, setPage } = useAuditLogs('role', roleId)
 *
 * @example
 * // [FIX 2026-06-12] 拉角色 + 子对象日志 (角色详情"操作日志" tab)
 * const { logs, total, loading, loadLogs, setFilters, setPage } = useAuditLogs('role', roleId, {
 *   parentObjectType: 'role',  // 父对象 = 角色自身
 *   parentObjectId: roleId,
 * })
 */

import { ref, computed, unref, onMounted, shallowRef } from 'vue'
import * as auditLogService from '@/services/auditLogService'

export function useAuditLogs(objectType, objectId, options = {}) {
  const { pageSize = 20, autoLoad = true, parentObjectType, parentObjectId } = options

  // [M2 PR-2.1] 审计日志数据是 API 整体返回后整体替换，无 push/splice 原地修改 → shallowRef
  //   性能: 1000+ 条日志 reactive 创建 1000+ Proxy → shallowRef 0 Proxy
  //   触发: 仅整体替换时触发 watcher，避免无谓的细粒度更新
  const logs = shallowRef([])
  const total = ref(0)
  const loading = ref(false)
  const currentPage = ref(1)
  // [M2 PR-2.1] filters 同样只做整体替换 (setFilters/clearFilters 都是 new object) → shallowRef
  const filters = shallowRef({})

  const resolvedObjectType = computed(() => unref(objectType))
  const resolvedObjectId = computed(() => unref(objectId))
  // [FIX 2026-06-12] parentObjectType/parentObjectId 也支持响应式 ref
  const resolvedParentObjectType = computed(() => unref(parentObjectType))
  const resolvedParentObjectId = computed(() => unref(parentObjectId))

  async function loadLogs(params = {}) {
    const type = resolvedObjectType.value
    const id = resolvedObjectId.value

    if (!type || !id) return { success: false, message: 'objectType and objectId are required' }

    loading.value = true

    const result = await auditLogService.getLogsByObject(type, id, {
      page: params.page || currentPage.value,
      pageSize: params.pageSize || pageSize,
      filters: { ...filters.value, ...(params.filters || {}) },
      parentObjectType: resolvedParentObjectType.value,
      parentObjectId: resolvedParentObjectId.value,
    })

    if (result.success) {
      logs.value = result.data?.items || []
      total.value = result.data?.total || 0
    }

    loading.value = false
    return result
  }

  function setFilters(newFilters) {
    filters.value = { ...newFilters }
    currentPage.value = 1
    return loadLogs()
  }

  function setPage(page) {
    currentPage.value = page
    return loadLogs({ page })
  }

  function clearFilters() {
    filters.value = {}
    currentPage.value = 1
    return loadLogs()
  }

  // [DECORATIVE] FR-LOG-013: 加载相关事件（同 transaction_id / parent_action_id）
  function loadRelatedEvents(log, options = {}) {
    return auditLogService.getRelatedEvents(log, options)
  }

  // [DECORATIVE] FR-LOG-013: 加载同 transaction_id 的所有事件
  function loadByTransactionId(transactionId) {
    return auditLogService.getByTransactionId(transactionId)
  }

  if (autoLoad && unref(objectType) && unref(objectId)) {
    onMounted(() => loadLogs())
  }

  return {
    logs,
    total,
    loading,
    currentPage,
    filters,
    loadLogs,
    setFilters,
    setPage,
    clearFilters,
    // [DECORATIVE] FR-LOG-013: v2 增强 API
    loadRelatedEvents,
    loadByTransactionId,
  }
}

export default { useAuditLogs }
