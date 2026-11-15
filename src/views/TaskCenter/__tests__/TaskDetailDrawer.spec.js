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
    submitDecision: vi.fn(),
    fetchParticipations: vi.fn(),
    reassignTask: vi.fn(),
    participateTask: vi.fn(),
    fetchDelegations: vi.fn(),
    createDelegation: vi.fn(),
    revokeDelegation: vi.fn()
  }
})

import {
  fetchTaskDetail, fetchTaskEvents, submitDecision,
  fetchParticipations, reassignTask, participateTask,
  fetchDelegations, createDelegation
} from '@/services/taskService'
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
    fetchParticipations.mockResolvedValue({
      success: true,
      data: { participants: [], counts: {}, remaining: [], completion_mode: 'any' }
    })
    fetchDelegations.mockResolvedValue({ success: true, data: { items: [], total: 0 } })
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

  // ── M4-5：参与进度 / 改派 / 加签 / 委托 / SLA ─────────────────────────

  it('会签未齐 → 展示参与进度与待表态人，不显示成功态', async () => {
    fetchParticipations.mockResolvedValue({
      success: true,
      data: {
        participants: [
          { id: 1, participant: 'u-a', role: 'approver', outcome: 'accepted' },
          { id: 2, participant: 'u-b', role: 'approver', outcome: 'pending' }
        ],
        counts: { accepted: 1, pending: 1 },
        remaining: ['u-b'],
        completion_mode: 'all'
      }
    })
    fetchTaskDetail.mockResolvedValue({ success: true, data: APPROVAL_TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.findAll('[data-test="participant-row"]').length).toBe(2)
    expect(w.find('[data-test="completion-mode"]').text()).toContain('会签')
    expect(w.find('[data-test="participation-remaining"]').text()).toContain('u-b')
  })

  it('SLA 已越线 → 倒计时显示已超时', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1' })
    await flushPromises()
    expect(w.find('[data-test="sla-countdown"]').text()).toContain('已超时')
  })

  it('无权限 → 不渲染改派/加签动作', async () => {
    authState.isAdmin = false
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-x' })
    await flushPromises()
    expect(w.find('[data-test="reassign-panel"]').exists()).toBe(false)
    expect(w.find('[data-test="participate-panel"]').exists()).toBe(false)
  })

  it('执行人可改派：缺原因拦截，补齐后提交并刷新', async () => {
    fetchTaskDetail.mockResolvedValue({
      success: true,
      data: { ...TASK, executor_assignee: 'u-a', status: 'claimed' }
    })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    reassignTask.mockResolvedValue({ success: true, data: {} })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-a' })
    await flushPromises()
    await w.find('[data-test="reassign-target"]').setValue('u-b')
    await w.find('[data-test="reassign-btn"]').trigger('click')
    await flushPromises()
    expect(reassignTask).not.toHaveBeenCalled()
    expect(w.find('[data-test="reassign-msg"]').text()).toContain('原因')
    await w.find('[data-test="reassign-reason"]').setValue('请假')
    await w.find('[data-test="reassign-btn"]').trigger('click')
    await flushPromises()
    expect(reassignTask).toHaveBeenCalledWith('T-1', { toUser: 'u-b', reason: '请假' })
    expect(w.emitted('claimed')).toBeTruthy()
  })

  it('加签勾选会签 → 提交 requireAll', async () => {
    fetchTaskDetail.mockResolvedValue({
      success: true,
      data: { ...TASK, executor_assignee: 'u-a', status: 'claimed' }
    })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    participateTask.mockResolvedValue({ success: true, data: { status: 'partially_approved' } })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-a' })
    await flushPromises()
    await w.find('[data-test="participant-input"]').setValue('u-c')
    await w.find('[data-test="require-all"]').setValue(true)
    await w.find('[data-test="participate-btn"]').trigger('click')
    await flushPromises()
    expect(participateTask).toHaveBeenCalledWith('T-1', { participant: 'u-c', requireAll: true })
    expect(w.find('[data-test="participate-msg"]').text()).toContain('会签未齐')
  })

  it('委托表单区间倒置 → 不发请求并提示', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-a' })
    await flushPromises()
    await w.find('[data-test="delegate-input"]').setValue('u-b')
    await w.find('[data-test="delegate-from"]').setValue('2026-12-05T10:00')
    await w.find('[data-test="delegate-to"]').setValue('2026-12-01T10:00')
    await w.find('[data-test="delegate-create-btn"]').trigger('click')
    await flushPromises()
    expect(createDelegation).not.toHaveBeenCalled()
    expect(w.find('[data-test="delegation-msg"]').text()).toContain('结束时间')
  })

  it('委托表单合法 → 创建后清空表单并刷新列表', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: TASK })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    createDelegation.mockResolvedValue({ success: true, data: { id: 1 } })
    fetchDelegations
      .mockResolvedValueOnce({ success: true, data: { items: [], total: 0 } })
      .mockResolvedValueOnce({
        success: true,
        data: { items: [{ id: 1, delegate: 'u-b', scope_type: 'any' }], total: 1 }
      })
    const w = mountDrawer({ visible: true, taskId: 'T-1', currentActor: 'u-a' })
    await flushPromises()
    await w.find('[data-test="delegate-input"]').setValue('u-b')
    await w.find('[data-test="delegate-create-btn"]').trigger('click')
    await flushPromises()
    expect(createDelegation).toHaveBeenCalledWith({
      delegate: 'u-b', scope_type: 'any', scope_value: null,
      effective_from: null, effective_to: null
    })
    expect(w.find('[data-test="delegation-msg"]').text()).toContain('已创建')
    expect(w.findAll('[data-test="delegation-row"]').length).toBe(1)
  })

  // ── M5-5：阶段进度 / 动作三态 / 取人依据 ─────────────────────────────

  const STAGED_APPROVAL = {
    ...APPROVAL_TASK,
    stage_no: 2,
    executor_candidates: ['u-a'],
    executor_config: {
      decision_actions: { approve: 'purchase_order.approve', reject: 'purchase_order.reject' },
      action_type: 'approve',
      assign_source: 'user_permission_sets',
      assign_explain: [
        { field: 'role_code', op: 'in', expected: ['APPROVER'], actual: ['u-a'], passed: true, step_no: 2 }
      ]
    },
    inputs: {
      policy_snapshot: {
        ...APPROVAL_TASK.inputs.policy_snapshot,
        steps: [
          { step_no: 1, stage_no: 1, approver_type: 'role', approver_ref: 'A', approve_mode: 'any' },
          { step_no: 2, stage_no: 2, approver_type: 'role', approver_ref: 'B', approve_mode: 'all' },
          { step_no: 3, stage_no: 3, approver_type: 'role', approver_ref: 'C', approve_mode: 'any' }
        ]
      }
    }
  }

  it('多阶段任务 → 展示阶段进度与取人依据', async () => {
    fetchTaskDetail.mockResolvedValue({ success: true, data: STAGED_APPROVAL })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="stage-progress"]').text()).toContain('阶段 2/3')
    expect(w.find('[data-test="action-type"]').text()).toContain('人工审批')
    const explain = w.find('[data-test="assign-explain"]').text()
    expect(explain).toContain('user_permission_sets')
    expect(explain).toContain('role_code')
    expect(explain).toContain('步骤 2')
  })

  it('空池原因 → 渲染中文说明', async () => {
    const task = {
      ...APPROVAL_TASK,
      executor_candidates: [],
      executor_config: {
        decision_actions: APPROVAL_TASK.executor_config.decision_actions,
        action_type: 'approve',
        assign_source: 'user_permission_sets',
        assign_reason: 'no_such_role'
      }
    }
    fetchTaskDetail.mockResolvedValue({ success: true, data: task })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="assign-reason"]').text()).toContain('权限角色不存在')
  })

  it('auto 阶段 → 徽标显示自动通过', async () => {
    const task = {
      ...APPROVAL_TASK,
      executor_config: { ...APPROVAL_TASK.executor_config, action_type: 'auto' }
    }
    fetchTaskDetail.mockResolvedValue({ success: true, data: task })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="action-type"]').text()).toContain('自动通过')
  })

  it('notify 阶段 → 只读知会，不渲染审批按钮', async () => {
    const task = {
      ...APPROVAL_TASK,
      executor_config: { ...APPROVAL_TASK.executor_config, action_type: 'notify' }
    }
    fetchTaskDetail.mockResolvedValue({ success: true, data: task })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="action-type"]').text()).toContain('知会')
    expect(w.find('[data-test="approve-btn"]').exists()).toBe(false)
    expect(w.find('[data-test="notify-hint"]').text()).toContain('只读')
  })

  it('notify 阶段 → 管理员也不渲染改派/加签面板', async () => {
    const task = {
      ...APPROVAL_TASK,
      executor_candidates: ['u-a'],
      executor_config: { ...APPROVAL_TASK.executor_config, action_type: 'notify' }
    }
    fetchTaskDetail.mockResolvedValue({ success: true, data: task })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({
      visible: true, taskId: 'T-2', currentActor: 'u-a'
    })
    await flushPromises()
    expect(w.find('[data-test="reassign-panel"]').exists()).toBe(false)
    expect(w.find('[data-test="participate-panel"]').exists()).toBe(false)
  })

  it('无策略快照 → 仍显示阶段动作徽标', async () => {
    const task = {
      ...APPROVAL_TASK,
      inputs: {},
      executor_config: { ...APPROVAL_TASK.executor_config, action_type: 'auto' }
    }
    fetchTaskDetail.mockResolvedValue({ success: true, data: task })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2' })
    await flushPromises()
    expect(w.find('[data-test="policy-snapshot"]').exists()).toBe(false)
    expect(w.find('[data-test="action-type"]').text()).toContain('自动通过')
  })

  it('仅知会名单用户 → 隐藏审批按钮（非候选池成员）', async () => {
    const task = {
      ...APPROVAL_TASK,
      executor_candidates: ['u-a'],
      executor_config: {
        ...APPROVAL_TASK.executor_config,
        action_type: 'approve',
        notify_candidates: ['u-b']
      }
    }
    fetchTaskDetail.mockResolvedValue({ success: true, data: task })
    fetchTaskEvents.mockResolvedValue({ success: true, data: [] })
    const w = mountDrawer({ visible: true, taskId: 'T-2', currentActor: 'u-b' })
    await flushPromises()
    expect(w.find('[data-test="approve-btn"]').exists()).toBe(false)
    expect(w.find('[data-test="notify-hint"]').exists()).toBe(true)
  })
})