import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

const mocks = vi.hoisted(() => ({
  listChanges: vi.fn()
}))

vi.mock('@/services/engineeringChangeService', () => ({
  listChanges: mocks.listChanges,
  default: { listChanges: mocks.listChanges }
}))

import EngineeringChangeListPage from '../EngineeringChangeListPage.vue'

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
      path: '/master-data/engineering-change/diff',
      name: 'engineering-change-diff',
      component: { template: '<div />' }
    },
    {
      path: '/master-data/engineering-change/:id',
      name: 'engineering-change-detail',
      component: { template: '<div />' }
    }
  ]
})

const ITEMS = [
  {
    id: 11,
    change_no: 'EC-202611-0001',
    title: '工程 BOM 改版',
    status: 'draft',
    item_id: 101,
    project_id: 7,
    effective_date: '2026-11-20',
    line_count: 3,
    created_at: '2026-11-03 10:00:00'
  },
  {
    id: 12,
    change_no: 'EC-202611-0002',
    title: '新增替代料',
    status: 'in_review',
    item_id: 102,
    project_id: null,
    effective_date: '2026-11-25',
    line_count: 1,
    created_at: '2026-11-03 11:00:00'
  }
]

function mountPage() {
  return mount(EngineeringChangeListPage, { global: { plugins: [router] } })
}

describe('EngineeringChangeListPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('渲染列表列与状态标签', async () => {
    mocks.listChanges.mockResolvedValue({
      success: true,
      data: { items: ITEMS, total: 2, page: 1, page_size: 20 }
    })

    const w = mountPage()
    await flushPromises()

    expect(mocks.listChanges).toHaveBeenCalledTimes(1)
    expect(mocks.listChanges).toHaveBeenCalledWith({ page: 1, page_size: 20 })

    expect(w.findAll('[data-test="ec-row-no"]').length).toBe(2)
    expect(w.text()).toContain('EC-202611-0001')
    expect(w.text()).toContain('工程 BOM 改版')
    expect(w.text()).toContain('草稿')
    expect(w.text()).toContain('评审中')
    expect(w.text()).toContain('2026-11-20')
    expect(w.text()).toContain('101')
    expect(w.text()).toContain('7')
  })

  it('状态筛选带上 status 并重置到第一页', async () => {
    mocks.listChanges.mockResolvedValue({
      success: true,
      data: { items: [ITEMS[0]], total: 1, page: 1, page_size: 20 }
    })

    const w = mountPage()
    await flushPromises()

    const selects = w.findAllComponents({ name: 'ElSelect' })
    expect(selects.length).toBeGreaterThan(0)
    selects[0].vm.$emit('update:modelValue', 'draft')
    await w.find('[data-test="ec-search"]').trigger('click')
    await flushPromises()

    expect(mocks.listChanges).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 20,
      status: 'draft'
    })
  })

  it('点击行进入详情路由', async () => {
    mocks.listChanges.mockResolvedValue({
      success: true,
      data: { items: ITEMS, total: 2, page: 1, page_size: 20 }
    })

    const w = mountPage()
    await flushPromises()

    const table = w.findAllComponents({ name: 'ElTable' })[0]
    table.vm.$emit('row-click', ITEMS[0])
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('engineering-change-detail')
    expect(router.currentRoute.value.params.id).toBe('11')
  })

  it('新建入口跳转差异预览', async () => {
    mocks.listChanges.mockResolvedValue({ success: true, data: { items: [], total: 0 } })

    const w = mountPage()
    await flushPromises()

    await w.find('[data-test="ec-create"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('engineering-change-diff')
  })

  it('接口失败时展示错误并清空列表', async () => {
    mocks.listChanges.mockResolvedValue({ success: false, message: '无权限查看工程变更单' })

    const w = mountPage()
    await flushPromises()

    expect(w.find('[data-test="ec-list-error"]').exists()).toBe(true)
    expect(w.text()).toContain('无权限查看工程变更单')
    expect(w.findAll('[data-test="ec-row-no"]').length).toBe(0)
  })
})
