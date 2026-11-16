/**
 * useTaskInbox - 统一收件箱状态机（工作台「我的待办」复用）
 *
 * 职责: 加载收件箱（entries + 全量 counts）、分区切换、角标读取、认领后刷新、批量审批。
 * 纪律: 错误不抛（UI 由 error 展示）；分区过滤交由服务端（bucket 参数）。
 *
 * 批量护栏（§9.13.4.3）:
 *   - 上限常量 BATCH_MAX_SIZE 由 UI 层拦截（本文件不重复判定）
 *   - 并发上限 BATCH_CONCURRENCY = 4（Promise 池，结果与入参同序）
 *   - 预判 fail-open：动作查询失败无法判定时交给服务端兜底，不前端拦掉
 *
 * @module composables/useTaskInbox
 */

import { ref, computed } from 'vue'
import {
  fetchInbox, fetchInboxCounts, claimTask, submitDecision, fetchTaskActions,
  normalizeInboxResponse, formatTaskRow,
  sortApprovalFirst, summarizeBatchResults,
  runWithConcurrency, BATCH_CONCURRENCY, actionAllowedFromPayload,
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
   * 并发 4（结果与入参同序），单条失败不中断；返回成功/失败汇总与 502 可重试项。
   * @param {string[]} taskIds
   * @param {{decision:'approve'|'reject', comment?:string, allowRework?:boolean}} payload
   */
  async function submitBatch(taskIds, { decision, comment = '', allowRework = false } = {}) {
    const ids = (Array.isArray(taskIds) ? taskIds : []).filter(Boolean)
    const settled = await runWithConcurrency(ids, BATCH_CONCURRENCY, taskId =>
      submitDecision(taskId, { decision, comment, allowRework })
    )
    const results = settled.map((item, index) => {
      if (!item.ok) {
        return {
          task_id: ids[index],
          success: false,
          message: item.error?.message || String(item.error)
        }
      }
      const res = item.value
      return {
        task_id: ids[index],
        success: res?.success === true,
        message: res?.message || '',
        httpStatus: res?.httpStatus
      }
    })
    const summary = summarizeBatchResults(results)
    if (summary.succeeded.length) await load()
    else await refreshCounts()
    return summary
  }

  /**
   * 批量前动作预判：GET /tasks/{id}/actions 判断该决策是否可用（fail-open）。
   * - `false`（响应成功但缺该动作）→ blocked（点击前排除，403 提前消失）
   * - `true` / `null`（无法判定）→ 保留在 decidable，交服务端兜底
   * @param {string[]} taskIds
   * @param {'approve'|'reject'} decision
   * @returns {Promise<{decidable:string[], blocked:Array<{task_id:string,message:string}>}>}
   */
  async function precheckDecidable(taskIds, decision) {
    const ids = (Array.isArray(taskIds) ? taskIds : []).filter(Boolean)
    const label = decision === 'reject' ? '驳回' : '通过'
    const settled = await runWithConcurrency(ids, BATCH_CONCURRENCY, taskId => fetchTaskActions(taskId))
    const decidable = []
    const blocked = []
    settled.forEach((item, index) => {
      const taskId = ids[index]
      const allowed = item.ok ? actionAllowedFromPayload(item.value, decision) : null
      if (allowed === false) {
        blocked.push({ task_id: taskId, message: `无权执行${label}或状态已变化` })
      } else {
        decidable.push(taskId)
      }
    })
    return { decidable, blocked }
  }

  return {
    rows, counts, total, activeBucket, loading, error, buckets,
    badge, load, refreshCounts, setBucket, claim, submitBatch, precheckDecidable
  }
}

export default useTaskInbox