import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn(), post: vi.fn() }
}))

import { apiV1 } from '@/utils/httpClient'
import {
  BUCKET_ORDER, BUCKET_LABELS, derivePause, formatTaskRow,
  normalizeInboxResponse, fetchInbox, fetchInboxCounts, fetchTaskDetail,
  fetchTaskEvents, claimTask, fetchTasks
} from '../taskService'

describe('BUCKET 常量', () => {
  it('顺序与 A8 core BUCKETS 一致（优先级）', () => {
    expect(BUCKET_ORDER).toEqual(['alert', 'approval', 'todo', 'agent_handoff', 'claimable'])
  })
  it('每个分区有中文标签', () => {
    BUCKET_ORDER.forEach(b => expect(BUCKET_LABELS[b]).toBeTruthy())
  })
})

describe('derivePause 暂停态派生（不发明状态）', () => {
  it('human + 活跃 → awaiting_human', () => {
    expect(derivePause({ executor_type: 'human', type: 'story', status: 'claimed' }).code)
      .toBe('awaiting_human')
  })
  it('webhook + 活跃 → awaiting_async', () => {
    expect(derivePause({ executor_type: 'webhook', type: 'story', status: 'in_progress' }).code)
      .toBe('awaiting_async')
  })
  it('approval + waiting_approval → needs_review', () => {
    expect(derivePause({ executor_type: 'human', type: 'approval', status: 'waiting_approval' }).code)
      .toBe('needs_review')
  })
  it('blocked → blocked（受阻）', () => {
    expect(derivePause({ executor_type: 'system', type: 'automation', status: 'blocked' }).code)
      .toBe('blocked')
  })
  it('终态 → null', () => {
    expect(derivePause({ executor_type: 'human', type: 'story', status: 'done' })).toBeNull()
    expect(derivePause({ executor_type: 'system', type: 'automation', status: 'failed' })).toBeNull()
  })
  it('system 活跃但无停等 → null', () => {
    expect(derivePause({ executor_type: 'system', type: 'automation', status: 'in_progress' })).toBeNull()
  })
})

describe('normalizeInboxResponse', () => {
  it('成功响应归一 + 缺省兜底', () => {
    const out = normalizeInboxResponse({ success: true, data: { entries: [{ task_id: 'T-1' }], counts: { todo: 1 }, total: 1 } })
    expect(out.entries).toHaveLength(1)
    expect(out.counts.todo).toBe(1)
    expect(out.total).toBe(1)
  })
  it('失败响应 → 空结构，不抛', () => {
    const out = normalizeInboxResponse({ success: false, message: 'x' })
    expect(out.entries).toEqual([])
    expect(out.total).toBe(0)
  })
  it('null → 空结构', () => {
    expect(normalizeInboxResponse(null).entries).toEqual([])
  })
})

describe('formatTaskRow', () => {
  it('补齐 primary_bucket 标签与暂停徽标', () => {
    const row = formatTaskRow({
      task_id: 'T-1', title: '录入', type: 'story', status: 'claimed',
      executor_type: 'human', buckets: ['todo'], primary_bucket: 'todo', alert: null
    })
    expect(row.bucketLabel).toBe(BUCKET_LABELS.todo)
    expect(row.pause.code).toBe('awaiting_human')
  })
  it('alert 存在 → 逾期标记', () => {
    const row = formatTaskRow({
      task_id: 'T-2', title: 'x', type: 'story', status: 'ready',
      executor_type: 'human', buckets: ['alert', 'todo'], primary_bucket: 'alert',
      alert: { rung: 2, rung_name: 'warn', pct_used: 90 }
    })
    expect(row.isOverdue).toBe(true)
    expect(row.overdueLabel).toContain('90')
  })
})

describe('API 封装', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetchInbox 带 bucket/app_id/limit 查询', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    await fetchInbox({ bucket: 'todo', appId: 'app-a', limit: 20 })
    expect(apiV1.get).toHaveBeenCalledWith('/task-inbox?bucket=todo&app_id=app-a&limit=20')
  })

  it('fetchInboxCounts 打 /task-inbox/counts', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: { todo: 0 } })
    await fetchInboxCounts()
    expect(apiV1.get).toHaveBeenCalledWith('/task-inbox/counts')
  })

  it('fetchTaskDetail / fetchTaskEvents 打对应路径', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: {} })
    await fetchTaskDetail('T-1')
    await fetchTaskEvents('T-1', 50)
    expect(apiV1.get).toHaveBeenCalledWith('/tasks/T-1')
    expect(apiV1.get).toHaveBeenCalledWith('/tasks/T-1/events?limit=50')
  })

  it('claimTask 用 POST', async () => {
    apiV1.post.mockResolvedValue({ success: true, data: { status: 'claimed' } })
    await claimTask('T-1')
    expect(apiV1.post).toHaveBeenCalledWith('/tasks/T-1/claim', {})
  })

  it('fetchTasks 拼过滤与分页', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: { items: [], total: 0 } })
    await fetchTasks({ status: 'failed', page: 2, pageSize: 20 })
    expect(apiV1.get).toHaveBeenCalledWith('/tasks?status=failed&page=2&page_size=20')
  })
})