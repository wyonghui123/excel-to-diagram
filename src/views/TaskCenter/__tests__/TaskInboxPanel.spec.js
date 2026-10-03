import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/taskService', () => ({
  fetchInbox: vi.fn(),
  fetchInboxCounts: vi.fn(),
  claimTask: vi.fn(),
  normalizeInboxResponse: (res) => res && res.success
    ? { entries: res.data.entries || [], counts: res.data.counts || {}, total: res.data.total || 0 }
    : { entries: [], counts: {}, total: 0 },
  formatTaskRow: (e) => ({
    ...e,
    bucketLabel: e.primary_bucket,
    pause: e.status === 'claimed' ? { code: 'awaiting_human', label: '等待人工办理', tone: 'info' } : null,
    isOverdue: !!e.alert, overdueLabel: e.alert ? 'SLA 90%' : ''
  }),
  BUCKET_ORDER: ['alert', 'approval', 'todo', 'agent_handoff', 'claimable'],
  BUCKET_LABELS: { alert: '逾期告警', approval: '待我审核', todo: '我的待办', agent_handoff: 'Agent 移交', claimable: '可认领' }
}))

import { fetchInbox } from '@/services/taskService'
import TaskInboxPanel from '../TaskInboxPanel.vue'

const ENTRY = {
  task_id: 'T-1', title: '录入采购申请', type: 'story', status: 'claimed',
  executor_type: 'human', buckets: ['todo'], primary_bucket: 'todo', alert: null,
  due_at: '2026-10-05T10:00:00', assignee: 'u-a'
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
})