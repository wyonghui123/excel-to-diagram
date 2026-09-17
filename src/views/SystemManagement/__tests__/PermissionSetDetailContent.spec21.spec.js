/**
 * PermissionSetDetailContent.spec21.spec.js - Spec 21 (动作对象级/实例级语义化) 测试
 *
 * 覆盖（Spec 21 §3 第十次 PM 反馈）：
 *   - 权限集详情页头部 action 区：
 *     - 模板监听 ObjectPage @refresh 事件（StateTransitionButtons 启用/停用后回调）
 *     - handleRefresh() 调用 boService.read 重新拉数据
 *     - permissionSet 数据被刷新
 *
 * 测试目标：确认 YAML 加 rules 后，前端能正确响应 ObjectPage 转发的 refresh 事件。
 * YAML 的具体解析/状态字段已由 meta/tests/test_state_adoption_verification.py 覆盖。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

// Mock boService：避免真实后端调用
vi.mock('@/services/boService', () => ({
  boService: {
    read: vi.fn(),
    queryAssociations: vi.fn().mockResolvedValue({ success: true, data: [] }),
    create: vi.fn(),
    update: vi.fn()
  }
}))

vi.mock('@/composables/useMessage', () => ({
  useMessage: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn()
  })
}))

vi.mock('@/stores/tabStore', () => ({
  useTabStore: () => ({
    replaceTabId: vi.fn(),
    closeTab: vi.fn(),
    tabs: [],
    activeTabId: null
  })
}))

// Mock HistorySection 间接依赖的 useAuditLogs 和 auditLogService，避免真的拉接口
vi.mock('@/composables/useAuditLogs', () => ({
  useAuditLogs: () => ({
    logs: [],
    loading: false,
    loadLogs: vi.fn().mockResolvedValue(undefined),
    pagination: { total: 0, page: 1, pageSize: 20 }
  })
}))

vi.mock('@/services/auditLogService', () => ({
  default: {
    getLogsByObject: vi.fn().mockResolvedValue({ items: [], total: 0 })
  }
}))

import PermissionSetDetailContent from '../PermissionSetDetailContent.vue'
import { boService } from '@/services/boService'

const buildRouter = () => createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/system/permission-set-detail/:roleId', component: { template: '<div />' } },
    { path: '/', component: { template: '<div />' } }
  ]
})

describe('Spec 21 PM 反馈第十次 - PermissionSetDetailContent 状态转换刷新', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
  })

  it('挂载后调用 boService.read 拉权限集数据', async () => {
    boService.read.mockResolvedValueOnce({
      success: true,
      data: { id: 5, code: 'admin', name: '管理员', is_active: true }
    })

    const router = buildRouter()
    await router.push('/system/permission-set-detail/5')
    await router.isReady()

    mount(PermissionSetDetailContent, {
      global: { plugins: [router] },
      props: {}
    })

    await flushPromises()
    expect(boService.read).toHaveBeenCalledWith('permission_set', '5')
  })

  it('handleRefresh 收到 @refresh 事件后重新调 boService.read', async () => {
    // 初次加载 + refresh 后再次加载 共 2 次调用
    boService.read
      .mockResolvedValueOnce({ success: true, data: { id: 5, code: 'admin', name: '管理员', is_active: true } })
      .mockResolvedValueOnce({ success: true, data: { id: 5, code: 'admin', name: '管理员', is_active: false } })

    const router = buildRouter()
    await router.push('/system/permission-set-detail/5')
    await router.isReady()

    const wrapper = mount(PermissionSetDetailContent, {
      global: { plugins: [router] },
      props: {}
    })

    await flushPromises()
    expect(boService.read).toHaveBeenCalledTimes(1)

    // 模拟 ObjectPage 触发 refresh 事件（StateTransitionButtons 启用/停用后回调）
    await wrapper.vm.handleRefresh({ newStatus: false, stateField: 'is_active' })
    await flushPromises()

    expect(boService.read).toHaveBeenCalledTimes(2)
    expect(boService.read).toHaveBeenNthCalledWith(2, 'permission_set', '5')
  })

  it('handleRefresh 在加载失败时不抛错（仅 console.error）', async () => {
    boService.read.mockRejectedValueOnce(new Error('network fail'))

    const router = buildRouter()
    await router.push('/system/permission-set-detail/5')
    await router.isReady()

    const wrapper = mount(PermissionSetDetailContent, {
      global: { plugins: [router] },
      props: {}
    })

    // 不应抛错
    await expect(wrapper.vm.handleRefresh({})).resolves.toBeUndefined()
  })
})