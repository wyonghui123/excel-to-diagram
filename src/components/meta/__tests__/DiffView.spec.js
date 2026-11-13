/**
 * DiffView.spec.js - 工程 BOM 差异只读渲染测试（T13-10）
 *
 * 覆盖：自动加载并渲染 summary/三类行 / modify 仅展示变化字段 /
 *       接口 success=false 显示错误 / 歧义警告 / itemLabels 映射 /
 *       autoLoad=false 不请求 / 缺少结构 ID 不请求 / reload 重新拉取。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/engineeringChangeService', () => ({
  diffStructures: vi.fn()
}))

import { diffStructures } from '@/services/engineeringChangeService'
import DiffView from '@/components/meta/DiffView.vue'

function buildDiff() {
  return {
    source_structure_id: 3001,
    target_structure_id: 2001,
    source_revision: 'B',
    target_revision: 'A',
    as_of: '2026-11-13',
    summary: { add: 1, modify: 1, remove: 1 },
    ambiguous: [],
    rows: [
      {
        line_type: 'add',
        match_key: 'add-101',
        component_item_id: 101,
        substitute_group_code: null,
        operation_seq: 10,
        note: '',
        old: null,
        new: { qty_per: 2, fixed_qty: null, valid_to: '2027-01-01', optional_flag: false }
      },
      {
        line_type: 'modify',
        match_key: 'modify-102',
        component_item_id: 102,
        substitute_group_code: 'S1',
        operation_seq: 20,
        note: '',
        old: { qty_per: 1, fixed_qty: 5, valid_to: '2027-01-01', optional_flag: 0 },
        new: { qty_per: 3, fixed_qty: 5, valid_to: '2027-01-01', optional_flag: 0 }
      },
      {
        line_type: 'remove',
        match_key: 'remove-103',
        component_item_id: 103,
        substitute_group_code: null,
        operation_seq: 30,
        note: '',
        old: { qty_per: 4, fixed_qty: null, valid_to: null, optional_flag: null },
        new: null
      }
    ]
  }
}

function mountView(props = {}) {
  return mount(DiffView, {
    props: { sourceStructureId: 3001, targetStructureId: 2001, ...props }
  })
}

describe('DiffView', () => {
  beforeEach(() => {
    diffStructures.mockReset()
    diffStructures.mockResolvedValue({ success: true, data: buildDiff() })
  })

  it('自动加载并按 summary 与行类型渲染', async () => {
    const wrapper = mountView({ asOf: '2026-11-13' })
    await flushPromises()

    expect(diffStructures).toHaveBeenCalledTimes(1)
    expect(diffStructures).toHaveBeenCalledWith({
      source_structure_id: 3001,
      target_structure_id: 2001,
      as_of: '2026-11-13'
    })

    expect(wrapper.get('[data-test="diff-summary-add"]').text()).toContain('新增 1')
    expect(wrapper.get('[data-test="diff-summary-modify"]').text()).toContain('修改 1')
    expect(wrapper.get('[data-test="diff-summary-remove"]').text()).toContain('移除 1')
    expect(wrapper.get('[data-test="diff-as-of"]').text()).toContain('2026-11-13')

    expect(wrapper.findAll('.diff-row--add')).toHaveLength(1)
    expect(wrapper.findAll('.diff-row--modify')).toHaveLength(1)
    expect(wrapper.findAll('.diff-row--remove')).toHaveLength(1)

    const rows = wrapper.findAll('.el-table__body tr')
    expect(rows[0].text()).toContain('新增')
    expect(rows[1].text()).toContain('修改')
    expect(rows[2].text()).toContain('移除')
    expect(wrapper.find('[data-test="diff-error"]').exists()).toBe(false)
  })

  it('modify 行仅展示实际变化的字段（qty_per 变、valid_to 不变）', async () => {
    diffStructures.mockResolvedValue({
      success: true,
      data: {
        ...buildDiff(),
        summary: { add: 0, modify: 1, remove: 0 },
        rows: [buildDiff().rows[1]]
      }
    })

    const wrapper = mountView()
    await flushPromises()

    const fields = wrapper.findAll('[data-test="diff-field"]')
    expect(fields).toHaveLength(1)
    expect(fields[0].text()).toContain('单位用量')
    expect(fields[0].text()).toContain('1')
    expect(fields[0].text()).toContain('3')
    expect(fields[0].text()).not.toContain('有效期至')
    expect(fields[0].text()).not.toContain('固定用量')
  })

  it('add 行展示新值，remove 行展示旧值', async () => {
    diffStructures.mockResolvedValue({
      success: true,
      data: {
        ...buildDiff(),
        summary: { add: 1, modify: 0, remove: 1 },
        rows: [buildDiff().rows[0], buildDiff().rows[2]]
      }
    })

    const wrapper = mountView()
    await flushPromises()

    const [addRow, removeRow] = wrapper.findAll('.el-table__body tr')
    expect(addRow.text()).toContain('单位用量')
    expect(addRow.text()).toContain('2')
    expect(removeRow.text()).toContain('单位用量')
    expect(removeRow.text()).toContain('4')
  })

  it('接口 success=false 时展示错误且不渲染差异行', async () => {
    diffStructures.mockResolvedValue({ success: false, message: '来源结构非 active' })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="diff-error"]').text()).toContain('来源结构非 active')
    expect(wrapper.findAll('.diff-row')).toHaveLength(0)
    expect(wrapper.emitted('error')?.[0]).toEqual(['来源结构非 active'])
  })

  it('接口抛错时展示错误信息', async () => {
    diffStructures.mockRejectedValue(new Error('网络不可达'))

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('[data-test="diff-error"]').text()).toContain('网络不可达')
  })

  it('歧义行渲染警告', async () => {
    diffStructures.mockResolvedValue({
      success: true,
      data: {
        ...buildDiff(),
        summary: { add: 0, modify: 0, remove: 0 },
        rows: [],
        ambiguous: [
          { match_key: 'k-1', message: '同一匹配键在单侧出现多行，需人工确认' }
        ]
      }
    })

    const wrapper = mountView()
    await flushPromises()

    const alert = wrapper.get('[data-test="diff-ambiguous"]')
    expect(alert.text()).toContain('1 处匹配键歧义')
    expect(alert.text()).toContain('k-1')
    expect(wrapper.get('[data-test="diff-empty"]').text()).toContain('无差异')
  })

  it('itemLabels 把组件 ID 映射为显示名', async () => {
    const wrapper = mountView({ itemLabels: { 101: '螺栓 M8' } })
    await flushPromises()

    const addRow = wrapper.get('.diff-row--add')
    expect(addRow.text()).toContain('螺栓 M8')
    // 未映射的组件保留 ID
    expect(wrapper.get('.diff-row--modify').text()).toContain('102')
  })

  it('autoLoad=false 不请求，reload 后再拉取', async () => {
    const wrapper = mountView({ autoLoad: false })
    await flushPromises()

    expect(diffStructures).not.toHaveBeenCalled()

    await wrapper.vm.reload()
    await flushPromises()

    expect(diffStructures).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.diff-row')).toHaveLength(3)
  })

  it('缺少结构 ID 时不请求并清空', async () => {
    const wrapper = mountView({ targetStructureId: null })
    await flushPromises()

    expect(diffStructures).not.toHaveBeenCalled()
    expect(wrapper.findAll('.diff-row')).toHaveLength(0)
  })
})