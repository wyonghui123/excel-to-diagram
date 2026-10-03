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
  fetchInbox, fetchInboxCounts, claimTask,
  normalizeInboxResponse, formatTaskRow,
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
      rows.value = norm.entries.map(formatTaskRow)
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

  return {
    rows, counts, total, activeBucket, loading, error, buckets,
    badge, load, refreshCounts, setBucket, claim
  }
}

export default useTaskInbox