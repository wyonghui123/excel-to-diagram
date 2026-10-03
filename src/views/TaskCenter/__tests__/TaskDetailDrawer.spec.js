import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/taskService', async (orig) => {
  const actual = await orig()
  return {
    ...actual,
    fetchTaskDetail: vi.fn(),
    fetchTaskEvents: vi.fn(),
    claimTask: vi.fn()
  }
})

import { fetchTaskDetail, fetchTaskEvents } from '@/services/taskService'
import TaskDetailDrawer from '../TaskDetailDrawer.vue'

const TASK = {
  id: 'T-1', title: '录入采购申请', type: 'story', status: 'ready',
  executor_type: 'human', executor_assignee: '', executor_candidates: ['u-a'],
  assign_policy: 'claim', due_at: '2026-10-05T10:00:00', created_by: 'u-owner',
  doc_ref: 'PO-1', workflow_run_id: 'R-1'
}

const EVENTS = [
  { id: 'e1', event_type: 'created', to_status: 'pending', actor: 'u-owner', actor_kind: 'human', occurred_at: '2026-10-04T09:00:00', reason: null },
  { id: 'e2', event_type: 'status_changed', from_status: 'pending', to_status: 'ready', actor: 'system', actor_kind: 'system', occurred_at: '2026-10-04T09:05:00', reason: '派工' }
]

// AppModal 内部 <Teleport to="body">；测试桩掉 Teleport 让内容留在 wrapper 内可断言。
function mountDrawer(props) {
  return mount(TaskDetailDrawer, {
    props,
    global: { stubs: { Teleport: true } }
  })
}

describe('TaskDetailDrawer', () => {
  beforeEach(() => vi.clearAllMocks())

  it('visible 时加载详情与活动流并渲染', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: EVENTS })
    const w = mountDrawer({ visible: true, taskId: 'T-1' })
    await flushPromises()
    expect(w.text()).toContain('录入采购申请')
    expect(w.findAll('[data-test="event-item"]').length).toBe(2)
  })

  it('渲染暂停徽标（human+ready → 等待人工办理）', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1' })
    await flushPromises()
    expect(w.find('[data-test="pause-badge"]').text()).toContain('等待人工办理')
  })

  it('候选池命中 → 认领按钮可用', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-a' })
    await flushPromises()
    const btn = w.find('[data-test="claim-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('disabled')).toBeUndefined()
  })

  it('非候选 → 不渲染认领按钮', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-x' })
    await flushPromises()
    expect(w.find('[data-test="claim-btn"]').exists()).toBe(false)
  })

  it('活动流渲染事件类型与状态迁移', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: EVENTS })
    const w = mountDrawer({ visible: true, taskId: 'T-1' })
    await flushPromises()
    expect(w.text()).toContain('pending → ready')
  })

  it('详情不可见（404）→ 错误态', async () => {
    fetchTaskDetail.mockResolvedValue({ success: false, message: '任务不存在或无权查看' })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1' })
    await flushPromises()
    expect(w.find('[data-test="error"]').exists()).toBe(true)
  })
})