import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/taskService', () => ({
  fetchInbox: vi.fn(),
  fetchInboxCounts: vi.fn(),
  claimTask: vi.fn(),
  submitDecision: vi.fn(),
  normalizeInboxResponse: (res) => res && res.success
    ? { entries: res.data.entries || [], counts: res.data.counts || {}, total: res.data.total || 0 }
    : { entries: [], counts: {}, total: 0 },
  formatTaskRow: (e) => ({
    ...e,
    bucketLabel: e.primary_bucket,
    pause: e.status === 'claimed' ? { code: 'awaiting_human', label: '等待人工办理', tone: 'info' } : null,
    isOverdue: !!e.alert, overdueLabel: e.alert ? 'SLA 90%' : ''
  }),
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

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    ElMessageBox: { confirm: vi.fn(() => Promise.resolve()) }
  }
})

import { fetchInbox, submitDecision } from '@/services/taskService'
import TaskInboxPanel from '../TaskInboxPanel.vue'

const ENTRY = {
  task_id: 'T-1', title: '录入采购申请', type: 'story', status: 'claimed',
  executor_type: 'human', buckets: ['todo'], primary_bucket: 'todo', alert: null,
  due_at: '2026-10-05T10:00:00', assignee: 'u-a'
}

const APPROVAL_ENTRY = {
  task_id: 'T-2', title: '审批采购单', type: 'approval', status: 'pending',
  executor_type: 'human', buckets: ['approval'], primary_bucket: 'approval', alert: null,
  due_at: '2026-10-05T10:00:00', assignee: 'u-b'
}

describe('TaskInboxPanel', () => {
  beforeEach(() => vi.clearAllMocks())

  it('挂载即加载并渲染行', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [ENTRY], counts: { todo: 1 }, total: 1 } })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    expect(w.text()).toContain('录入采购申请')
  })

  it('渲染分区 Tab 与角标', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: { todo: 3, claimable: 1 }, total: 0 } })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    const tabs = w.findAll('[data-test^="bucket-tab-"]')
    expect(tabs.length).toBe(5)
    expect(w.find('[data-test="bucket-tab-todo"]').text()).toContain('3')
  })

  it('点击分区 Tab 触发带 bucket 的重新查询', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    await w.find('[data-test="bucket-tab-approval"]').trigger('click')
    await flushPromises()
    expect(fetchInbox).toHaveBeenLastCalledWith(expect.objectContaining({ bucket: 'approval' }))
  })

  it('点击行 emit open-detail(taskId)', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [ENTRY], counts: {}, total: 1 } })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    await w.find('[data-test="inbox-row"]').trigger('click')
    expect(w.emitted('open-detail')[0]).toEqual(['T-1'])
  })

  it('空列表显示空态', async () => {
    fetchInbox.mockResolvedValue({ success: true, data: { entries: [], counts: {}, total: 0 } })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    expect(w.find('[data-test="empty"]').exists()).toBe(true)
  })

  it('加载失败显示错误态', async () => {
    fetchInbox.mockRejectedValue(new Error('network'))
    const w = mount(TaskInboxPanel)
    await flushPromises()
    expect(w.find('[data-test="error"]').exists()).toBe(true)
  })

  it('审批行置顶并展示批量栏；非审批行无勾选框', async () => {
    fetchInbox.mockResolvedValue({
      success: true,
      data: {
        entries: [ENTRY, { ...APPROVAL_ENTRY }],
        counts: { todo: 1, approval: 1 }, total: 2
      }
    })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    const rows = w.findAll('[data-test="inbox-row"]')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('审批采购单')
    expect(w.find('[data-test="batch-bar"]').exists()).toBe(true)
    expect(w.find('[data-test="row-check-T-2"]').exists()).toBe(true)
    expect(w.find('[data-test="row-check-T-1"]').exists()).toBe(false)
  })

  it('批量通过逐条提交并显示成功/失败汇总', async () => {
    fetchInbox.mockResolvedValue({
      success: true,
      data: { entries: [{ ...APPROVAL_ENTRY }], counts: { approval: 1 }, total: 1 }
    })
    submitDecision.mockResolvedValue({ success: true })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    await w.find('[data-test="row-check-T-2"] input').setValue(true)
    await w.find('[data-test="batch-approve"]').trigger('click')
    await flushPromises()
    expect(submitDecision).toHaveBeenCalledWith('T-2', { decision: 'approve', comment: '', allowRework: false })
    expect(w.find('[data-test="batch-result"]').text()).toContain('成功 1 / 失败 0')
  })

  it('批量驳回未填意见时不提交并提示', async () => {
    fetchInbox.mockResolvedValue({
      success: true,
      data: { entries: [{ ...APPROVAL_ENTRY }], counts: { approval: 1 }, total: 1 }
    })
    const w = mount(TaskInboxPanel)
    await flushPromises()
    await w.find('[data-test="row-check-T-2"] input').setValue(true)
    await w.find('[data-test="batch-reject"]').trigger('click')
    await flushPromises()
    expect(submitDecision).not.toHaveBeenCalled()
    expect(w.find('[data-test="batch-result"]').text()).toContain('驳回需填写审批意见')
  })
})