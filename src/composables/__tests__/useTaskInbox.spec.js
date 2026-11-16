import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/taskService', () => ({
  fetchInbox: vi.fn(),
  fetchInboxCounts: vi.fn(),
  claimTask: vi.fn(),
  submitDecision: vi.fn(),
  fetchTaskActions: vi.fn(),
  BATCH_CONCURRENCY: 4,
  runWithConcurrency: async (items, limit, worker) => {
    const list = Array.isArray(items) ? items : []
    const size = list.length
    if (!size) return []
    const width = Number.isFinite(limit) && limit > 0 ? Math.max(1, Math.min(limit, size)) : 1
    const results = new Array(size)
    let cursor = 0
    const drain = async () => {
      while (cursor < size) {
        const index = cursor
        cursor += 1
        try {
          results[index] = { ok: true, value: await worker(list[index], index) }
        } catch (error) {
          results[index] = { ok: false, error }
        }
      }
    }
    await Promise.all(Array.from({ length: width }, () => drain()))
    return results
  },
  actionAllowedFromPayload: (res, decision) => {
    if (!res || res.success !== true || !res.data) return null
    if (!Array.isArray(res.data.actions)) return null
    return res.data.actions.some((item) => !!item && item.action === decision)
  },
  normalizeInboxResponse: (res) => res && res.success
    ? { entries: res.data.entries || [], counts: res.data.counts || {}, total: res.data.total || 0 }
    : { entries: [], counts: {}, total: 0 },
  formatTaskRow: (e) => ({ ...e, pause: null }),
  sortApprovalFirst: (rows) => {
    if (!Array.isArray(rows)) return []
    const rank = (row) => (row?.primary_bucket === 'approval' ? 0 : 1)
    return [...rows].sort((a, b) => rank(a) - rank(b))
  },
  summarizeBatchResults: (results = []) => {
    const succeeded = []
    const failed = []
    results.forEach((item) => {
      if (item.success) succeeded.push(item.task_id)
      else failed.push({ task_id: item.task_id, message: item.message || '', httpStatus: item.httpStatus })
    })
    return { succeeded, failed, retryableIds: failed.filter((f) => f.httpStatus === 502).map((f) => f.task_id) }
  },
  BUCKET_ORDER: ['alert', 'approval', 'todo', 'agent_handoff', 'claimable'],
  BUCKET_LABELS: { alert: '逾期告警', approval: '待我审核', todo: '我的待办', agent_handoff: 'Agent 移交', claimable: '可认领' }
}))

import { fetchInbox, fetchInboxCounts, claimTask, submitDecision, fetchTaskActions } from '@/services/taskService'
import { useTaskInbox } from '../useTaskInbox'

describe('useTaskInbox', () => {
  beforeEach(() => vi.clearAllMocks())

  it('load 填充行 + 角标', async () => {
    fetchInbox.mockResolvedValue({
      success: true,
      data: { entries: [{ task_id: 'T-1', buckets: ['todo'], primary_bucket: 'todo' }], counts: { todo: 1 }, total: 1 }
    })
    const box = useTaskInbox()
    await box.load()
    expect(box.rows.value).toHaveLength(1)
    expect(box.counts.value.todo).toBe(1)
    expect(box.loading.value).toBe(false)
  })

  it('badge(bucket) 取角标，缺省 0', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: { alert: 2 }, total: 0 } })
    const box = useTaskInbox()
    await box.load()
    expect(box.badge('alert')).toBe(2)
    expect(box.badge('claimable')).toBe(0)
  })

  it('setBucket 触发带 bucket 的重新加载', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    const box = useTaskInbox()
    await box.setBucket('approval')
    expect(box.activeBucket.value).toBe('approval')
    expect(fetchInbox).toHaveBeenLastCalledWith(expect.objectContaining({ bucket: 'approval' }))
  })

  it('setBucket("") 清空分区', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    const box = useTaskInbox()
    await box.setBucket('')
    expect(fetchInbox).toHaveBeenLastCalledWith(expect.objectContaining({ bucket: undefined }))
  })

  it('load 失败 → error 置位、rows 保持空、不抛', async () => {
    fetchInbox.mockRejectedValue(new Error('boom'))
    const box = useTaskInbox()
    await box.load()
    expect(box.error.value).toBeTruthy()
    expect(box.rows.value).toEqual([])
  })

  it('claim 成功后刷新并回传结果', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    claimTask.mockResolvedValue({ success: true, data: { status: 'claimed' } })
    const box = useTaskInbox()
    const res = await box.claim('T-1')
    expect(res.success).toBe(true)
    expect(claimTask).toHaveBeenCalledWith('T-1')
    expect(fetchInboxCounts).toHaveBeenCalled()
  })

  it('claim 失败回传 success=false，不抛', async () => {
    claimTask.mockRejectedValue(new Error('409'))
    const box = useTaskInbox()
    const res = await box.claim('T-1')
    expect(res.success).toBe(false)
  })

  it('load 后 approval 行置顶（稳定排序）', async () => {
    fetchInbox.mockResolvedValue({
      success: true,
      data: {
        entries: [
          { task_id: 'T-1', primary_bucket: 'todo' },
          { task_id: 'T-2', primary_bucket: 'approval' },
          { task_id: 'T-3', primary_bucket: 'alert' }
        ],
        counts: {}, total: 3
      }
    })
    const box = useTaskInbox()
    await box.load()
    expect(box.rows.value.map(r => r.task_id)).toEqual(['T-2', 'T-1', 'T-3'])
  })

  it('submitBatch 逐条提交，失败不中断并汇总成功/失败', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    submitDecision
      .mockResolvedValueOnce({ success: true })
      .mockResolvedValueOnce({ success: false, message: '单据未生效', httpStatus: 502 })
      .mockResolvedValueOnce({ success: true })
    const box = useTaskInbox()
    const summary = await box.submitBatch(['T-1', 'T-2', 'T-3'], { decision: 'approve', comment: 'ok' })
    expect(submitDecision).toHaveBeenNthCalledWith(1, 'T-1', { decision: 'approve', comment: 'ok', allowRework: false })
    expect(submitDecision).toHaveBeenNthCalledWith(2, 'T-2', { decision: 'approve', comment: 'ok', allowRework: false })
    expect(submitDecision).toHaveBeenNthCalledWith(3, 'T-3', { decision: 'approve', comment: 'ok', allowRework: false })
    expect(summary.succeeded).toEqual(['T-1', 'T-3'])
    expect(summary.failed).toHaveLength(1)
    expect(summary.retryableIds).toEqual(['T-2'])
  })

  it('submitBatch 单条抛错不中断后续', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    submitDecision
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ success: true })
    const box = useTaskInbox()
    const summary = await box.submitBatch(['T-1', 'T-2'], { decision: 'reject', comment: 'no' })
    expect(summary.succeeded).toEqual(['T-2'])
    expect(summary.failed[0].message).toBe('network')
  })

  it('precheckDecidable：缺该动作 → blocked（驳回），响应失败 → fail-open 保留', async () => {
    fetchTaskActions
      .mockResolvedValueOnce({ success: true, data: { actions: [{ action: 'approve' }] } })
      .mockResolvedValueOnce({ success: true, data: { actions: [] } })
      .mockResolvedValueOnce({ success: false, message: '403' })
    const box = useTaskInbox()
    const out = await box.precheckDecidable(['T-1', 'T-2', 'T-3'], 'reject')
    expect(out.blocked.map(item => item.task_id)).toEqual(['T-1', 'T-2'])
    expect(out.blocked[0].message).toBe('无权执行驳回或状态已变化')
    expect(out.decidable).toEqual(['T-3'])
  })

  it('precheckDecidable：空 actions 判为不可通过；动作齐全可决策', async () => {
    fetchTaskActions
      .mockResolvedValueOnce({ success: true, data: { actions: [] } })
      .mockResolvedValueOnce({ success: true, data: { actions: [{ action: 'approve' }, { action: 'reject' }] } })
    const box = useTaskInbox()
    const out = await box.precheckDecidable(['T-8', 'T-9'], 'approve')
    expect(out.decidable).toEqual(['T-9'])
    expect(out.blocked).toEqual([{ task_id: 'T-8', message: '无权执行通过或状态已变化' }])
  })
})