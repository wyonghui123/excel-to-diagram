import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const authState = vi.hoisted(() => ({ isAdmin: true, perms: [] }))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    get isAdmin() { return authState.isAdmin },
    hasPermission: (p) => authState.perms.includes(p)
  })
}))

vi.mock('@/services/taskService', async (orig) => {
  const actual = await orig()
  return {
    ...actual,
    fetchTaskDetail: vi.fn(),
    fetchTaskEvents: vi.fn(),
    claimTask: vi.fn(),
    submitDecision: vi.fn()
  }
})

import { fetchTaskDetail, fetchTaskEvents, submitDecision } from '@/services/taskService'
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

const APPROVAL_TASK = {
  id: 'T-2', title: '采购订单审批', type: 'approval', status: 'waiting_approval',
  executor_type: 'human', executor_assignee: '', executor_candidates: [],
  assign_policy: 'claim', created_by: 'u-owner', doc_ref: 'PO-9',
  doc_ref_type: 'purchase_order', doc_ref_id: 'PO-9',
  inputs: {
    policy_snapshot: {
      policy_code: 'po_high', policy_name: '采购高额审批', policy_version: 3, hit_policy: true,
      steps: [{ step_no: 1, approver_type: 'role', approver_ref: 'procurement_manager', approve_mode: 'any', sla_hours: 24 }],
      conditions_explain: [{ field: 'gross_amount', op: '>=', expected: 100000, actual: 128000, passed: true }]
    }
  },
  executor_config: {
    decision_actions: { approve: 'purchase_order.approve', reject: 'purchase_order.reject' }
  }
}

// AppModal 内部 <Teleport to="body">；测试桩掉 Teleport 让内容留在 wrapper 内可断言。
function mountDrawer(props) {
  return mount(TaskDetailDrawer, {
    props,
    global: { stubs: { Teleport: true } }
  })
}

describe('TaskDetailDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.isAdmin = true
    authState.perms = []
  })

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

  it('审批任务：状态中文化 + 审批链 + 命中依据 + 单据跳转', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="task-status"]').text()).toBe('待审批')
    expect(w.find('[data-test="approval-chain"]').text()).toContain('procurement_manager')
    expect(w.find('[data-test="condition-explain"]').text()).toContain('gross_amount')
    expect(w.find('[data-test="open-doc"]').exists()).toBe(true)
  })

  it('admin 短路权限 → 展示通过/驳回按钮', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="approve-btn"]').exists()).toBe(true)
    expect(w.find('[data-test="reject-btn"]').exists()).toBe(true)
  })

  it('非 admin 且有 {bo}:approve → 展示按钮', async () => {
    authState.isAdmin = false
    authState.perms = ['purchase_order:approve']
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="approve-btn"]').exists()).toBe(true)
  })

  it('无审批权限 → 不展示按钮且给出提示', async () => {
    authState.isAdmin = false
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="approve-btn"]').exists()).toBe(false)
    expect(w.find('[data-test="decision-hint"]').text()).toContain('purchase_order:approve')
  })

  it('驳回未填意见 → 不发请求并提示', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    await w.find('[data-test="reject-btn"]').trigger('click')
    await flushPromises()
    expect(submitDecision).not.toHaveBeenCalled()
    expect(w.find('[data-test="decision-msg"]').text()).toContain('驳回需填写审批意见')
  })

  it('驳回填意见 + 退回修改 → 提交 allow_rework 并 emit decided', async () => {
    submitDecision.mockResolvedValue({ success: true, data: { status: 'completed' } })
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    await w.find('[data-test="decision-comment"]').setValue('金额超限，退回修改')
    await w.find('[data-test="allow-rework"]').setValue(true)
    await w.find('[data-test="reject-btn"]').trigger('click')
    await flushPromises()
    expect(submitDecision).toHaveBeenCalledWith('T-2', {
      decision: 'reject',
      comment: '金额超限，退回修改',
      allowRework: true
    })
    expect(w.emitted('decided')).toBeTruthy()
  })
})