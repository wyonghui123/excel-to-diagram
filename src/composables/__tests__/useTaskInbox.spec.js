import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/taskService', () => ({
  fetchInbox: vi.fn(),
  fetchInboxCounts: vi.fn(),
  claimTask: vi.fn(),
  normalizeInboxResponse: (res) => res && res.success
    ? { entries: res.data.entries || [], counts: res.data.counts || {}, total: res.data.total || 0 }
    : { entries: [], counts: {}, total: 0 },
  formatTaskRow: (e) => ({ ...e, pause: null }),
  BUCKET_ORDER: ['alert', 'approval', 'todo', 'agent_handoff', 'claimable'],
  BUCKET_LABELS: { alert: '逾期告警', approval: '待我审核', todo: '我的待办', agent_handoff: 'Agent 移交', claimable: '可认领' }
}))

import { fetchInbox, fetchInboxCounts, claimTask } from '@/services/taskService'
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
})