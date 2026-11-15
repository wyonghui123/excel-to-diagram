/**
 * useTaskInbox - 统一收件箱状态机（工作台「我的待办」复用）
 *
 * 职责: 加载收件箱（entries + 全量 counts）、分区切换、角标读取、认领后刷新。
 * 纪律: 错误不抛（UI 由 error 展示）；分区过滤交由服务端（bucket 参数）。
 *
 * @module composables/useTaskInbox
 */

import { ref, computed } from 'vue'
import {
  fetchInbox, fetchInboxCounts, claimTask, submitDecision,
  normalizeInboxResponse, formatTaskRow,
  sortApprovalFirst, summarizeBatchResults,
  BUCKET_ORDER, BUCKET_LABELS
} from '@/services/taskService'

export function useTaskInbox({ appId = null, limit = 50 } = {}) {
  const rows = ref([])
  const counts = ref({})
  const total = ref(0)
  const activeBucket = ref('')
  const loading = ref(false)
  const error = ref('')

  const buckets = computed(() => BUCKET_ORDER.map(key => ({
    key, label: BUCKET_LABELS[key], count: counts.value[key] || 0
  })))

  function badge(bucket) {
    return counts.value[bucket] || 0
  }

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const res = await fetchInbox({
        bucket: activeBucket.value || undefined,
        appId: appId || undefined,
        limit
      })
      const norm = normalizeInboxResponse(res)
      rows.value = sortApprovalFirst(norm.entries.map(formatTaskRow))
      counts.value = norm.counts
      total.value = norm.total
    } catch (e) {
      error.value = e?.message || String(e)
      rows.value = []
    } finally {
      loading.value = false
    }
  }

  async function refreshCounts() {
    try {
      const res = await fetchInboxCounts({ appId: appId || undefined })
      if (res && res.success && res.data) counts.value = res.data
    } catch (e) {
      /* 角标失败静默：不阻塞列表 */
    }
  }

  async function setBucket(bucket) {
    activeBucket.value = bucket || ''
    await load()
  }

  async function claim(taskId) {
    try {
      const res = await claimTask(taskId)
      refreshCounts()
      return res && res.success
        ? { success: true, data: res.data }
        : { success: false, message: res?.message || '认领失败' }
    } catch (e) {
      return { success: false, message: e?.message || String(e) }
    }
  }

  /**
   * 批量审批（D-AP-12：逐条调用现有端点，不新增批量 API）。
   * 单条失败不中断；返回成功/失败汇总与 502 可重试项。
   * @param {string[]} taskIds
   * @param {{decision:'approve'|'reject', comment?:string, allowRework?:boolean}} payload
   */
  async function submitBatch(taskIds, { decision, comment = '', allowRework = false } = {}) {
    const ids = (Array.isArray(taskIds) ? taskIds : []).filter(Boolean)
    const results = []
    for (const taskId of ids) {
      try {
        const res = await submitDecision(taskId, { decision, comment, allowRework })
        results.push({
          task_id: taskId,
          success: res?.success === true,
          message: res?.message || '',
          httpStatus: res?.httpStatus
        })
      } catch (e) {
        results.push({ task_id: taskId, success: false, message: e?.message || String(e) })
      }
    }
    const summary = summarizeBatchResults(results)
    if (summary.succeeded.length) await load()
    else await refreshCounts()
    return summary
  }

  return {
    rows, counts, total, activeBucket, loading, error, buckets,
    badge, load, refreshCounts, setBucket, claim, submitBatch
  }
}

export default useTaskInbox