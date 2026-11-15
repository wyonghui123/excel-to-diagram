import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
  apiV2: { get: vi.fn(), post: vi.fn() }
}))

import { apiV1, apiV2 } from '@/utils/httpClient'
import {
  BUCKET_ORDER, BUCKET_LABELS, derivePause, formatTaskRow,
  normalizeInboxResponse, fetchInbox, fetchInboxCounts, fetchTaskDetail,
  fetchTaskEvents, claimTask, submitDecision, fetchTasks, fetchWorkflowSchedules,
  sortApprovalFirst, summarizeBatchResults,
  normalizeParticipations, canReassignTask, formatSlaRemaining, validateDelegationForm,
  fetchParticipations, reassignTask, participateTask,
  fetchDelegations, createDelegation, revokeDelegation
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

describe('sortApprovalFirst（approval 分区置顶）', () => {
  it('approval 行在前，其余保持原顺序', () => {
    const rows = [
      { id: 1, primary_bucket: 'todo' },
      { id: 2, primary_bucket: 'approval' },
      { id: 3, primary_bucket: 'alert' },
      { id: 4, primary_bucket: 'approval' }
    ]
    expect(sortApprovalFirst(rows).map(r => r.id)).toEqual([2, 4, 1, 3])
  })
  it('非数组 → 空数组', () => {
    expect(sortApprovalFirst(null)).toEqual([])
  })
})

describe('summarizeBatchResults（成功 N / 失败 M + 502 可重试）', () => {
  it('汇总成功与失败，标注可重试项', () => {
    const out = summarizeBatchResults([
      { task_id: 'T-1', success: true },
      { task_id: 'T-2', success: false, message: '单据未生效', httpStatus: 502 },
      { task_id: 'T-3', success: false, message: '无权限', httpStatus: 403 }
    ])
    expect(out.succeeded).toEqual(['T-1'])
    expect(out.failed).toHaveLength(2)
    expect(out.failed[0]).toEqual({ task_id: 'T-2', message: '单据未生效', httpStatus: 502 })
    expect(out.retryableIds).toEqual(['T-2'])
  })
  it('空输入 → 空汇总', () => {
    expect(summarizeBatchResults([])).toEqual({ succeeded: [], failed: [], retryableIds: [] })
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

  it('submitDecision 按决策协议提交 approve', async () => {
    apiV1.post.mockResolvedValue({ success: true, data: { status: 'completed' } })
    await submitDecision('T-1', { decision: 'approve', comment: 'ok' })
    expect(apiV1.post).toHaveBeenCalledWith('/tasks/T-1/decision', {
      decision: 'approve', comment: 'ok', allow_rework: false
    })
  })

  it('submitDecision 驳回透传 allow_rework', async () => {
    apiV1.post.mockResolvedValue({ success: true })
    await submitDecision('T-2', { decision: 'reject', comment: '超限', allowRework: true })
    expect(apiV1.post).toHaveBeenCalledWith('/tasks/T-2/decision', {
      decision: 'reject', comment: '超限', allow_rework: true
    })
  })

  it('fetchTasks 拼过滤与分页', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: { items: [], total: 0 } })
    await fetchTasks({ status: 'failed', page: 2, pageSize: 20 })
    expect(apiV1.get).toHaveBeenCalledWith('/tasks?status=failed&page=2&page_size=20')
  })

  it('fetchWorkflowSchedules 走 apiV2 打 /workflows/schedules', async () => {
    apiV2.get.mockResolvedValue({ success: true, data: { items: [] } })
    await fetchWorkflowSchedules()
    expect(apiV2.get).toHaveBeenCalledWith('/workflows/schedules')
  })

  it('M4 通用能力端点路径正确', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: {} })
    apiV1.post.mockResolvedValue({ success: true, data: {} })
    apiV1.delete.mockResolvedValue({ success: true })
    await fetchParticipations('T-1')
    await reassignTask('T-1', { toUser: 'u-b', reason: '请假' })
    await participateTask('T-1', { participant: 'u-c', requireAll: true })
    await fetchDelegations({ includeInactive: true })
    await createDelegation({ delegate: 'u-b' })
    await revokeDelegation(7)
    expect(apiV1.get).toHaveBeenCalledWith('/tasks/T-1/participations')
    expect(apiV1.post).toHaveBeenCalledWith('/tasks/T-1/assign', { to_user: 'u-b', reason: '请假' })
    expect(apiV1.post).toHaveBeenCalledWith('/tasks/T-1/participate', { comment: '', require_all: true, participant: 'u-c' })
    expect(apiV1.get).toHaveBeenCalledWith('/task-delegations?include_inactive=true')
    expect(apiV1.post).toHaveBeenCalledWith('/task-delegations', { delegate: 'u-b' })
    expect(apiV1.delete).toHaveBeenCalledWith('/task-delegations/7')
  })
})

describe('M4 纯函数（参与进度 / 改派准入 / SLA / 委托校验）', () => {
  it('normalizeParticipations 对失败/空响应兜底', () => {
    expect(normalizeParticipations(null)).toEqual({
      participants: [], counts: {}, remaining: [], completionMode: 'any'
    })
    const ok = normalizeParticipations({
      success: true,
      data: { participants: [{ id: 1 }], counts: { approved: 1 }, completion_mode: 'all' }
    })
    expect(ok.participants).toHaveLength(1)
    expect(ok.completionMode).toBe('all')
  })

  it('canReassignTask：终态/陌生人不可，执行人/候选人/admin 可', () => {
    const base = { status: 'claimed', executor_assignee: 'u-a', executor_candidates: ['u-b'] }
    expect(canReassignTask(base, 'u-a')).toBe(true)
    expect(canReassignTask(base, 'u-b')).toBe(true)
    expect(canReassignTask(base, 'u-x')).toBe(false)
    expect(canReassignTask(base, 'u-x', { isAdmin: true })).toBe(true)
    expect(canReassignTask({ ...base, status: 'done' }, 'u-a')).toBe(false)
    expect(canReassignTask(null, 'u-a')).toBe(false)
  })

  it('formatSlaRemaining：剩余 / 已超时 / 非法输入', () => {
    const now = new Date('2026-11-15T10:00:00')
    expect(formatSlaRemaining('2026-11-15T13:30:00', now).label).toBe('剩余 3h 30m')
    expect(formatSlaRemaining('2026-11-15T08:00:00', now)).toMatchObject({
      overdue: true, label: '已超时 2h 0m'
    })
    expect(formatSlaRemaining('', now)).toBeNull()
    expect(formatSlaRemaining('bad-input', now)).toBeNull()
  })

  it('validateDelegationForm：受托人/范围/区间，与后端同口径', () => {
    expect(validateDelegationForm({}).message).toBe('受托人不能为空')
    expect(validateDelegationForm({ delegate: 'u-a', delegator: 'u-a' }).message).toBe('不能委托给自己')
    expect(validateDelegationForm({ delegate: 'u-b', scope_type: 'type' }).message)
      .toBe('选择范围后必须填写范围值')
    expect(validateDelegationForm({
      delegate: 'u-b', effective_from: '2026-12-05T10:00', effective_to: '2026-12-01T10:00'
    }).message).toBe('结束时间不能早于开始时间')
    expect(validateDelegationForm({
      delegate: 'u-b', scope_type: 'type', scope_value: 'approval',
      effective_from: '2026-12-01T10:00', effective_to: '2026-12-05T10:00'
    })).toEqual({ valid: true, message: '' })
  })
})