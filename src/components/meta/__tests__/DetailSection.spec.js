/**
 * DetailSection.spec.js - ui-meta 详情区渲染测试（T13-8）
 *
 * 覆盖：1 列 vs 2 列渲染差异 / col_span 映射与越界夹取 /
 *       0 与 false 不被显示成 '-' / 未知枚举值显示原值 / visible_when 过滤 / tabs 分组。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'

vi.mock('@/services/metaEnumService', () => ({
  getEnum: vi.fn(),
  getEnumBatch: vi.fn()
}))

import { getEnum, getEnumBatch } from '@/services/metaEnumService'
import DetailSection from '@/components/meta/DetailSection.vue'
import { _resetEnumMetaCache } from '@/composables/useEnumMeta'

function makeUiMeta({ sections = [], fields = [], tabs = [] }) {
  return {
    schema_version: 'v1',
    object_type: 'task',
    label: '任务',
    detail: { sections, tabs },
    form: { fields }
  }
}

/** 按 label 找到详情项 */
function itemByLabel(wrapper, label) {
  return wrapper
    .findAll('.detail-section__item')
    .find(item => item.find('.detail-section__label').text() === label)
}

const baseMeta = makeUiMeta({
  sections: [
    {
      key: 'main',
      label: '主要信息',
      columns: 2,
      col_span_map: {},
      fields: ['name', 'status', 'count', 'flag']
    }
  ],
  fields: [
    { key: 'name', label: '名称', widget: 'text' },
    { key: 'status', label: '状态', widget: 'select', enum_type: 'task_status' },
    { key: 'count', label: '数量', widget: 'number' },
    { key: 'flag', label: '标记', widget: 'switch' }
  ]
})

describe('DetailSection', () => {
  beforeEach(() => {
    _resetEnumMetaCache()
    getEnum.mockReset()
    getEnum.mockResolvedValue([{ value: 'active', label: '启用', color: 'success' }])
    getEnumBatch.mockReset()
    getEnumBatch.mockResolvedValue({
      task_status: [{ value: 'active', label: '启用', color: 'success' }]
    })
  })

  it('2 列 => span 12；columns prop 覆盖为 1 列 => span 24', () => {
    const twoCol = mount(DetailSection, {
      props: { uiMeta: baseMeta, data: { name: '演示' } }
    })
    expect(twoCol.findAll('.el-col-12')).toHaveLength(4)

    const oneCol = mount(DetailSection, {
      props: { uiMeta: baseMeta, data: { name: '演示' }, columns: 1 }
    })
    expect(oneCol.findAll('.el-col-24')).toHaveLength(4)
  })

  it('字段 col_span 生效且越界夹到 1..24', () => {
    const meta = makeUiMeta({
      sections: [
        {
          key: 'main',
          label: '',
          columns: 2,
          col_span_map: { remark: 1 },
          fields: ['name', 'remark', 'count']
        }
      ],
      fields: [
        { key: 'name', label: '名称', widget: 'text', col_span: 2 },
        { key: 'remark', label: '备注', widget: 'text' },
        { key: 'count', label: '数量', widget: 'number', col_span: 9 }
      ]
    })
    const wrapper = mount(DetailSection, { props: { uiMeta: meta, data: {} } })

    expect(itemByLabel(wrapper, '名称').element.closest('.el-col').className).toContain('el-col-24')
    expect(itemByLabel(wrapper, '备注').element.closest('.el-col').className).toContain('el-col-12')
    expect(itemByLabel(wrapper, '数量').element.closest('.el-col').className).toContain('el-col-24')
  })

  it('0 / false 正常显示，空值显示 "-"', async () => {
    const wrapper = mount(DetailSection, {
      props: {
        uiMeta: baseMeta,
        data: { name: '', status: 'active', count: 0, flag: false }
      }
    })
    await flushPromises()

    expect(itemByLabel(wrapper, '数量').find('.detail-section__value').text()).toBe('0')
    expect(itemByLabel(wrapper, '标记').find('.detail-section__value').text()).toBe('false')
    expect(itemByLabel(wrapper, '名称').find('.detail-section__value').text()).toBe('-')
    expect(itemByLabel(wrapper, '状态').find('.el-tag').text()).toBe('启用')
  })

  it('未知枚举值显示原值', async () => {
    const wrapper = mount(DetailSection, {
      props: { uiMeta: baseMeta, data: { status: 'ghost' } }
    })
    await flushPromises()

    expect(wrapper.find('.enum-tag--unknown').text()).toBe('ghost')
  })

  it('visible_when 过滤字段，数据变化后重新出现', async () => {
    const meta = makeUiMeta({
      sections: [
        { key: 'main', label: '', columns: 2, fields: ['name', 'amount'] }
      ],
      fields: [
        { key: 'name', label: '名称', widget: 'text' },
        { key: 'amount', label: '金额', widget: 'number', visible_when: "kind === 'big'" }
      ]
    })
    const data = reactive({ kind: 'small', name: '甲', amount: 1 })
    const wrapper = mount(DetailSection, { props: { uiMeta: meta, data } })

    expect(wrapper.text()).not.toContain('金额')

    data.kind = 'big'
    await nextTick()

    expect(wrapper.text()).toContain('金额')
  })

  it('detail.tabs 按 section_keys 分组，无效 key 忽略', () => {
    const meta = makeUiMeta({
      sections: baseMeta.detail.sections,
      fields: baseMeta.form.fields,
      tabs: [
        { key: 't1', label: '基本信息', section_keys: ['main', 'ghost'] },
        { key: 't2', label: '无对应区段', section_keys: ['ghost'] }
      ]
    })
    const wrapper = mount(DetailSection, {
      props: { uiMeta: meta, data: { status: 'active' } }
    })

    const panes = wrapper.findAll('.el-tab-pane')
    expect(panes).toHaveLength(1)
    // tab 标签由 Element Plus 渲染在导航区，不在 pane 文本内；无效 key 的 t2 应被过滤
    const tabLabels = wrapper.findAll('.el-tabs__item')
    expect(tabLabels).toHaveLength(1)
    expect(tabLabels[0].text()).toBe('基本信息')
    expect(panes[0].findAll('.detail-section__item')).toHaveLength(4)
  })
})