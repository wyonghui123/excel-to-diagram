/**
 * StateTransitionButtons 工单开工入口测试（G13）
 *
 * 守：work_order + start_work_order 走 POST /api/v1/work-orders/<id>/start，
 *     其它状态迁移仍走通用 BO 更新。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { post: vi.fn() },
  apiV2: { get: vi.fn(), put: vi.fn() },
}))

vi.mock('@/composables/useCrudMessage', () => ({
  useCrudMessage: () => ({
    stateChanged: vi.fn(),
    stateChangeFailed: vi.fn(),
  }),
}))

vi.mock('@/components/common/AppButton/AppButton.vue', () => ({
  default: {
    name: 'AppButton',
    template: '<button @click="$emit(\'click\')"><slot /></button>',
  },
}))

import { apiV1, apiV2 } from '@/utils/httpClient'
import StateTransitionButtons from '@/components/bo/StateTransitionButtons.vue'

const START = {
  id: 'start_work_order',
  label: '开始',
  stateField: 'status',
  toState: 'In Progress',
  available: true,
}

const ACCEPT = {
  id: 'accept_work_order',
  label: '受理',
  stateField: 'status',
  toState: 'Accepted',
  available: true,
}

const mountButtons = (objectType) => mount(StateTransitionButtons, {
  props: { objectType, objectId: 21, autoLoad: false },
  global: { stubs: { 'el-dialog': true } },
})

beforeEach(() => {
  vi.clearAllMocks()
  apiV1.post.mockResolvedValue({ success: true, data: { id: 21 } })
  apiV2.put.mockResolvedValue({ success: true, data: { id: 21 } })
  apiV2.get.mockResolvedValue({ success: true, data: [] })
})

describe('StateTransitionButtons 工单开工入口', () => {
  it('work_order 开始时调用执行入口而非通用更新', async () => {
    const wrapper = mountButtons('work_order')

    await wrapper.vm.executeTransition(START)

    expect(apiV1.post).toHaveBeenCalledWith('/work-orders/21/start')
    expect(apiV2.put).not.toHaveBeenCalled()
  })

  it('work_order 其它迁移仍走通用更新', async () => {
    const wrapper = mountButtons('work_order')

    await wrapper.vm.executeTransition(ACCEPT)

    expect(apiV2.put).toHaveBeenCalledWith(
      '/bo/work_order/21',
      { status: 'Accepted' }
    )
    expect(apiV1.post).not.toHaveBeenCalled()
  })

  it('普通对象的状态迁移不受影响', async () => {
    const wrapper = mountButtons('project')

    await wrapper.vm.executeTransition({ ...START, id: 'start' })

    expect(apiV2.put).toHaveBeenCalledWith('/bo/project/21', { status: 'In Progress' })
    expect(apiV1.post).not.toHaveBeenCalled()
  })
})
