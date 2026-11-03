import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

const mocks = vi.hoisted(() => ({
  diffStructures: vi.fn(),
  createChange: vi.fn(),
  queryStructures: vi.fn()
}))

vi.mock('@/services/engineeringChangeService', () => ({
  diffStructures: mocks.diffStructures,
  createChange: mocks.createChange,
  default: { diffStructures: mocks.diffStructures, createChange: mocks.createChange }
}))

vi.mock('@/services/boService', () => ({
  default: { query: mocks.queryStructures },
  query: mocks.queryStructures
}))

import EngineeringChangeDiffPage from '../EngineeringChangeDiffPage.vue'

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

const STRUCTURES = {
  success: true,
  data: {
    items: [
      { id: 1, item_id: 10, usage: 'engineering', revision: 'A', status: 'active' },
      { id: 2, item_id: 10, usage: 'production', revision: 'B', status: 'active' }
    ]
  }
}

const DIFF_RESULT = {
  success: true,
  data: {
    source_structure_id: 1,
    target_structure_id: 2,
    source_revision: 'A',
    target_revision: 'B',
    as_of: '2026-11-03',
    ambiguous: [],
    summary: { add: 1, modify: 1, remove: 0 },
    rows: [
      {
        line_type: 'add',
        match_key: '201||',
        component_item_id: 201,
        substitute_group_code: null,
        operation_seq: null,
        target_structure_id: 2,
        source_structure_id: 1,
        source_structure_line_id: 11,
        structure_line_id: null,
        old_qty_per: null,
        new_qty_per: 2,
        old_valid_to: null,
        new_valid_to: null
      },
      {
        line_type: 'modify',
        match_key: '202||',
        component_item_id: 202,
        substitute_group_code: null,
        operation_seq: null,
        target_structure_id: 2,
        source_structure_id: 1,
        source_structure_line_id: 12,
        structure_line_id: 22,
        old_qty_per: 1,
        new_qty_per: 3,
        old_valid_to: null,
        new_valid_to: null
      }
    ]
  }
}

function mountPage() {
  return mount(EngineeringChangeDiffPage, { global: { plugins: [router] } })
}

describe('EngineeringChangeDiffPage', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    mocks.queryStructures.mockImplementation(params =>
      Promise.resolve({
        success: true,
        data: {
          items: STRUCTURES.data.items.filter(item => item.usage === params.usage)
        }
      })
    )
    mocks.diffStructures.mockResolvedValue(DIFF_RESULT)
  })

  it('加载工程/生产结构选项', async () => {
    const w = mountPage()
    await flushPromises()

    expect(mocks.queryStructures).toHaveBeenCalledWith(
      'item_structure',
      expect.objectContaining({ usage: 'engineering', status: 'active' })
    )
    expect(mocks.queryStructures).toHaveBeenCalledWith(
      'item_structure',
      expect.objectContaining({ usage: 'production', status: 'active' })
    )
    expect(w.text()).toContain('工程结构')
    expect(w.text()).toContain('生产结构')
  }, 20000)

  it('生成差异预览：只读表格与统计', async () => {
    // Element Plus 全量挂载较慢，显式放宽单测超时
    const w = mountPage()
    await flushPromises()

    const selects = w.findAllComponents({ name: 'ElSelect' })
    selects[0].vm.$emit('update:modelValue', 1)
    selects[1].vm.$emit('update:modelValue', 2)
    w.findAllComponents({ name: 'ElDatePicker' })[0].vm.$emit('update:modelValue', '2026-11-03')
    await w.find('[data-test="ec-diff-run"]').trigger('click')
    await flushPromises()

    expect(mocks.diffStructures).toHaveBeenCalledWith({
      source_structure_id: 1,
      target_structure_id: 2,
      as_of: '2026-11-03'
    })
    expect(w.find('[data-test="ec-diff-summary"]').exists()).toBe(true)
    expect(w.text()).toContain('新增 1')
    expect(w.text()).toContain('修改 1')
    expect(w.text()).toContain('201')
    expect(w.text()).toContain('202')
  }, 20000)

  it('勾选差异行后创建请求体包含正确 lines 并跳转详情', async () => {
    mocks.createChange.mockResolvedValue({ success: true, data: { id: 99 } })

    const w = mountPage()
    await flushPromises()

    const selects = w.findAllComponents({ name: 'ElSelect' })
    selects[0].vm.$emit('update:modelValue', 1)
    selects[1].vm.$emit('update:modelValue', 2)
    await w.find('[data-test="ec-diff-run"]').trigger('click')
    await flushPromises()

    // 首个 ElCheckbox 为「全选差异行」
    w.findAllComponents({ name: 'ElCheckbox' })[0].vm.$emit('change', true)
    await flushPromises()
    expect(w.text()).toContain('已勾选 2 行')

    await w.find('[data-test="ec-diff-title"]').setValue('工程 BOM 改版')
    await w.find('[data-test="ec-diff-reason"]').setValue('更新用量')
    // 第 2 个日期选择器为生效日
    w.findAllComponents({ name: 'ElDatePicker' })[1].vm.$emit('update:modelValue', '2026-12-01')
    await flushPromises()

    await w.find('[data-test="ec-diff-create"]').trigger('click')
    await flushPromises()

    expect(mocks.createChange).toHaveBeenCalledTimes(1)
    const payload = mocks.createChange.mock.calls[0][0]
    expect(payload.change_type).toBe('revise')
    expect(payload.title).toBe('工程 BOM 改版')
    expect(payload.reason).toBe('更新用量')
    expect(payload.effective_date).toBe('2026-12-01')
    expect(payload.lines).toHaveLength(2)
    expect(payload.lines[0]).toMatchObject({
      line_type: 'add',
      component_item_id: 201,
      target_structure_id: 2,
      source_structure_id: 1,
      source_structure_line_id: 11,
      structure_line_id: null,
      match_key: '201||'
    })
    expect(payload.lines[1]).toMatchObject({
      line_type: 'modify',
      component_item_id: 202,
      structure_line_id: 22,
      source_structure_line_id: 12
    })

    expect(router.currentRoute.value.name).toBe('engineering-change-detail')
    expect(router.currentRoute.value.params.id).toBe('99')
  }, 20000)

  it('未勾选差异行时阻止创建', async () => {
    const w = mountPage()
    await flushPromises()

    const selects = w.findAllComponents({ name: 'ElSelect' })
    selects[0].vm.$emit('update:modelValue', 1)
    selects[1].vm.$emit('update:modelValue', 2)
    await w.find('[data-test="ec-diff-run"]').trigger('click')
    await flushPromises()

    await w.find('[data-test="ec-diff-title"]').setValue('工程 BOM 改版')
    await w.find('[data-test="ec-diff-create"]').trigger('click')
    await flushPromises()

    expect(mocks.createChange).not.toHaveBeenCalled()
    expect(w.find('[data-test="ec-diff-create-error"]').exists()).toBe(true)
  }, 20000)
})
