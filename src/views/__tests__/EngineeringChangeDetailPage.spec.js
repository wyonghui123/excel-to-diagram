import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

const mocks = vi.hoisted(() => ({
  getChange: vi.fn(),
  getImpact: vi.fn(),
  submitChange: vi.fn(),
  approveChange: vi.fn(),
  rejectChange: vi.fn(),
  cancelChange: vi.fn(),
  applyChange: vi.fn()
}))

vi.mock('@/services/engineeringChangeService', () => ({
  getChange: mocks.getChange,
  getImpact: mocks.getImpact,
  submitChange: mocks.submitChange,
  approveChange: mocks.approveChange,
  rejectChange: mocks.rejectChange,
  cancelChange: mocks.cancelChange,
  applyChange: mocks.applyChange,
  default: mocks
}))

import { useAuthStore } from '@/stores/authStore'
import EngineeringChangeDetailPage from '../EngineeringChangeDetailPage.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    {
      path: '/master-data/engineering-change',
      name: 'engineering-change',
      component: { template: '<div />' }
    },
    {
      path: '/master-data/engineering-change/:id',
      name: 'engineering-change-detail',
      component: { template: '<div />' }
    }
  ]
})

const BASE_CHANGE = {
  id: 21,
  change_no: 'EC-202611-0009',
  title: '工程 BOM 改版',
  change_type: 'revise',
  status: 'draft',
  effective_date: '2026-11-20',
  project_id: 7,
  item_id: 101,
  target_structure_id: 55,
  reason: '因工艺调整更新用量',
  created_at: '2026-11-03 10:00:00',
  created_by: 'admin',
  applied_at: null,
  applied_by: null,
  lines: [
    {
      id: 1,
      line_no: 1,
      line_type: 'add',
      component_item_id: 201,
      match_key: '201||',
      old_qty_per: null,
      new_qty_per: 2,
      target_structure_id: 55,
      source_structure_id: 66,
      note: ''
    },
    {
      id: 2,
      line_no: 2,
      line_type: 'modify',
      component_item_id: 202,
      match_key: '202||',
      old_qty_per: 1,
      new_qty_per: 3,
      target_structure_id: 55,
      source_structure_id: 66,
      note: ''
    },
    {
      id: 3,
      line_no: 3,
      line_type: 'remove',
      component_item_id: 203,
      match_key: '203||',
      old_qty_per: 1,
      new_qty_per: null,
      target_structure_id: 55,
      source_structure_id: null,
      note: ''
    }
  ]
}

const IMPACT = {
  change_id: 21,
  affected_component_item_ids: [201, 202, 203],
  parent_structures: [
    {
      structure_id: 71,
      item_id: 301,
      usage: 'production',
      revision: 'B',
      status: 'active',
      structure_line_id: 711,
      line_no: 2,
      component_item_id: 202,
      qty_per: 1
    }
  ],
  work_orders: [
    {
      work_order_id: 81,
      work_order_no: 'WO-202611-0001',
      status: 'Released',
      created_at: '2026-11-02 09:00:00',
      components: [{ component_item_id: 202, qty_required: 4 }]
    }
  ],
  read_only: true
}

function setPermissions(permissions) {
  const authStore = useAuthStore()
  authStore.$patch({ user: { user_id: 1, username: 'tester', permissions } })
  return authStore
}

async function mountPage(status = 'draft', permissions = null) {
  mocks.getChange.mockResolvedValue({
    success: true,
    data: { ...BASE_CHANGE, status }
  })
  mocks.getImpact.mockResolvedValue({ success: true, data: IMPACT })

  setPermissions(
    permissions || [
      'engineering_change:engineering_change_view',
      'engineering_change:engineering_change_create',
      'engineering_change:engineering_change_approve',
      'engineering_change:engineering_change_apply'
    ]
  )

  await router.push('/master-data/engineering-change/21')
  const w = mount(EngineeringChangeDetailPage, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('EngineeringChangeDetailPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('渲染头信息与明细色标', async () => {
    const w = await mountPage('draft')

    expect(w.text()).toContain('EC-202611-0009')
    expect(w.text()).toContain('因工艺调整更新用量')
    expect(w.text()).toContain('2026-11-20')
    expect(w.findAll('[data-test="ec-line-type"]').length).toBe(3)
    expect(w.text()).toContain('新增')
    expect(w.text()).toContain('修改')
    expect(w.text()).toContain('移除')
  })

  it('draft + create 权限：显示提交/取消，隐藏批准/驳回/应用', async () => {
    const w = await mountPage('draft')

    expect(w.find('[data-test="ec-action-submit"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-cancel"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-approve"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-reject"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-apply"]').exists()).toBe(false)
  })

  it('in_review + approve 权限：显示批准/驳回/取消，隐藏提交/应用', async () => {
    const w = await mountPage('in_review')

    expect(w.find('[data-test="ec-action-approve"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-reject"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-cancel"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-submit"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-apply"]').exists()).toBe(false)
  })

  it('approved + apply 权限：显示应用/取消，隐藏提交/批准/驳回', async () => {
    const w = await mountPage('approved')

    expect(w.find('[data-test="ec-action-apply"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-cancel"]').exists()).toBe(true)
    expect(w.find('[data-test="ec-action-submit"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-approve"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-reject"]').exists()).toBe(false)
  })

  it('无 approve 权限时 in_review 不显示批准/驳回', async () => {
    const w = await mountPage('in_review', [
      'engineering_change:engineering_change_view',
      'engineering_change:engineering_change_create'
    ])

    expect(w.find('[data-test="ec-action-approve"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-reject"]').exists()).toBe(false)
    expect(w.find('[data-test="ec-action-cancel"]').exists()).toBe(true)
  })

  it('影响预览为只读：展示父项结构与在途工单且不触发写接口', async () => {
    const w = await mountPage('draft')

    expect(mocks.getImpact).toHaveBeenCalledWith('21')
    expect(w.find('[data-test="ec-impact-readonly"]').exists()).toBe(true)
    expect(w.text()).toContain('受影响父项结构')
    expect(w.text()).toContain('在途工单')
    expect(w.text()).toContain('WO-202611-0001')
    expect(w.text()).toContain('301')

    expect(mocks.applyChange).not.toHaveBeenCalled()
    expect(mocks.submitChange).not.toHaveBeenCalled()
    expect(mocks.approveChange).not.toHaveBeenCalled()
    expect(mocks.cancelChange).not.toHaveBeenCalled()
    expect(mocks.rejectChange).not.toHaveBeenCalled()
  })
})
