/**
 * MetaForm.spec.js - ui-meta 表单渲染测试（T13-8）
 *
 * 覆盖：span 推导与 col_span 优先级（含越界夹取）/ visible_when 动态显隐 /
 *       readonly 与 mode=view 禁用 / tabs 分组与无效 key 忽略 / required 校验。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick, reactive } from 'vue'

vi.mock('@/services/metaEnumService', () => ({
  getEnum: vi.fn(),
  getEnumBatch: vi.fn()
}))

import { getEnum, getEnumBatch } from '@/services/metaEnumService'
import MetaForm from '@/components/meta/MetaForm.vue'
import { _resetEnumMetaCache } from '@/composables/useEnumMeta'

function makeUiMeta({ sections = [], fields = [], tabs = [] }) {
  return {
    schema_version: 'v1',
    object_type: 'task',
    label: '任务',
    form: { sections, fields, tabs }
  }
}

/** 按字段 label 找到所在的 el-col */
function colByLabel(wrapper, label) {
  return wrapper
    .findAll('.el-col')
    .find(col => col.find('.el-form-item__label').text() === label)
}

const baseMeta = makeUiMeta({
  sections: [
    { key: 'basic', label: '基本信息', columns: 2, col_span_map: {}, fields: ['name', 'remark'] },
    { key: 'extra', label: '扩展', columns: 1, col_span_map: {}, fields: ['amount'] }
  ],
  fields: [
    { key: 'name', label: '名称', widget: 'text', required: true },
    { key: 'remark', label: '备注', widget: 'textarea' },
    { key: 'amount', label: '金额', widget: 'number' }
  ]
})

describe('MetaForm', () => {
  beforeEach(() => {
    _resetEnumMetaCache()
    getEnum.mockReset()
    getEnum.mockResolvedValue([])
    getEnumBatch.mockReset()
    getEnumBatch.mockResolvedValue({})
  })

  it('col_span 缺省按 section.columns 推导（2 列 => 12，1 列 => 24）', () => {
    const wrapper = mount(MetaForm, {
      props: { uiMeta: baseMeta, modelValue: { name: '', remark: '', amount: null } }
    })

    expect(colByLabel(wrapper, '名称').classes()).toContain('el-col-12')
    expect(colByLabel(wrapper, '备注').classes()).toContain('el-col-12')
    expect(colByLabel(wrapper, '金额').classes()).toContain('el-col-24')
    // 无 tabs 时平铺
    expect(wrapper.find('.el-tabs').exists()).toBe(false)
  })

  it('col_span 生效（含 col_span_map）且越界被夹到 6/12/18/24', () => {
    const meta = makeUiMeta({
      sections: [
        {
          key: 'layout',
          label: '布局',
          columns: 2,
          col_span_map: { remark: 3 },
          fields: ['name', 'remark', 'amount', 'note']
        }
      ],
      fields: [
        { key: 'name', label: '名称', widget: 'text', col_span: 1 },
        { key: 'remark', label: '备注', widget: 'text' },
        { key: 'amount', label: '金额', widget: 'number', col_span: 9 },
        { key: 'note', label: '说明', widget: 'text', col_span: 4 }
      ]
    })
    const wrapper = mount(MetaForm, {
      props: { uiMeta: meta, modelValue: {} }
    })

    expect(colByLabel(wrapper, '名称').classes()).toContain('el-col-6')
    expect(colByLabel(wrapper, '备注').classes()).toContain('el-col-18')
    expect(colByLabel(wrapper, '金额').classes()).toContain('el-col-24')
    expect(colByLabel(wrapper, '说明').classes()).toContain('el-col-24')
  })

  it('visible_when 为 false 的字段不渲染，数据变化后重新出现', async () => {
    const meta = makeUiMeta({
      sections: [
        { key: 'main', label: '', columns: 2, fields: ['name', 'remark'] }
      ],
      fields: [
        { key: 'name', label: '名称', widget: 'text' },
        { key: 'remark', label: '备注', widget: 'text', visible_when: "status === 'draft'" }
      ]
    })
    const model = reactive({ status: 'approved', name: '', remark: '' })
    const wrapper = mount(MetaForm, {
      props: { uiMeta: meta, modelValue: model }
    })

    expect(wrapper.findAll('.el-form-item')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('备注')

    model.status = 'draft'
    await nextTick()

    expect(wrapper.findAll('.el-form-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('备注')
  })

  it('readonly / mode=view 时控件禁用', () => {
    const readonlyWrapper = mount(MetaForm, {
      props: {
        uiMeta: baseMeta,
        modelValue: { name: '', remark: '', amount: null },
        readonly: true
      }
    })
    expect(readonlyWrapper.find('.el-input__inner').element.disabled).toBe(true)

    const viewWrapper = mount(MetaForm, {
      props: {
        uiMeta: baseMeta,
        modelValue: { name: '', remark: '', amount: null },
        mode: 'view'
      }
    })
    expect(viewWrapper.find('.el-input__inner').element.disabled).toBe(true)

    const editWrapper = mount(MetaForm, {
      props: { uiMeta: baseMeta, modelValue: { name: '', remark: '', amount: null } }
    })
    expect(editWrapper.find('.el-input__inner').element.disabled).toBe(false)
  })

  it('字段级 readonly 只禁用该字段', () => {
    const meta = makeUiMeta({
      sections: [
        { key: 'main', label: '', columns: 2, fields: ['name', 'remark'] }
      ],
      fields: [
        { key: 'name', label: '名称', widget: 'text', readonly: true },
        { key: 'remark', label: '备注', widget: 'text' }
      ]
    })
    const wrapper = mount(MetaForm, {
      props: { uiMeta: meta, modelValue: { name: '', remark: '' } }
    })
    const items = wrapper.findAll('.el-form-item')

    expect(items[0].find('.el-input__inner').element.disabled).toBe(true)
    expect(items[1].find('.el-input__inner').element.disabled).toBe(false)
  })

  it('tabs 按 section_keys 分组，无效 key 忽略', () => {
    const meta = makeUiMeta({
      sections: baseMeta.form.sections,
      fields: baseMeta.form.fields,
      tabs: [
        { key: 't1', label: '基本信息', section_keys: ['basic', 'ghost'] },
        { key: 't2', label: '扩展信息', section_keys: ['extra'] }
      ]
    })
    const wrapper = mount(MetaForm, {
      props: { uiMeta: meta, modelValue: { name: '', remark: '', amount: null } }
    })

    const tabs = wrapper.findAll('.el-tabs__item')
    expect(tabs.map(tab => tab.text())).toEqual(['基本信息', '扩展信息'])

    const panes = wrapper.findAll('.el-tab-pane')
    expect(panes).toHaveLength(2)
    expect(panes[0].findAll('.el-form-item')).toHaveLength(2)
    expect(panes[1].findAll('.el-form-item')).toHaveLength(1)
  })

  it('required 字段生成必填规则，并暴露返回 Promise 的 validate()', async () => {
    const wrapper = mount(MetaForm, {
      props: { uiMeta: baseMeta, modelValue: { name: '', remark: '', amount: null } }
    })
    await flushPromises()

    // el-form-item 由 field.required 推导出必填标记
    expect(wrapper.find('.el-form-item').classes()).toContain('is-required')

    const result = wrapper.vm.validate()
    expect(typeof result.then).toBe('function')
    await result.catch(() => {})
  })
})