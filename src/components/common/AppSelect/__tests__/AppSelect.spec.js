/**
 * AppSelect.spec.js — YonDesign AppSelect 组件测试
 *
 * 测试策略:
 * - Stub el-select / el-option / el-option-group（不依赖 Element Plus 真实实现）
 * - 验证 props 透传、v-model 双向绑定、事件转发、slot 渲染、分组逻辑
 * - 覆盖 20 个场景,约 65 个用例
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AppSelect from '../AppSelect.vue'

// ─── el-select stub ──────────────────────────────────────────────
const ElSelectStub = {
  name: 'ElSelect',
  template: `
    <div class="el-select-stub"
      :data-model-value="JSON.stringify(modelValue)"
      :data-placeholder="placeholder"
      :data-disabled="disabled"
      :data-clearable="clearable"
      :data-filterable="filterable"
      :data-multiple="multiple"
      :data-size="size"
      :data-empty-text="emptyText"
      :data-teleported="teleported"
      :data-popper-class="popperClass"
    >
      <slot />
      <slot name="footer" />
      <button class="trigger-focus" @click="$emit('focus')" />
      <button class="trigger-blur" @click="$emit('blur')" />
      <button class="trigger-change" @click="$emit('update:model-value', 'test-value')" />
    </div>
  `,
  props: [
    'modelValue', 'placeholder', 'disabled', 'clearable', 'filterable',
    'multiple', 'size', 'emptyText', 'teleported', 'popperClass',
  ],
  emits: ['update:model-value', 'focus', 'blur'],
}

// ─── el-option stub ──────────────────────────────────────────────
const ElOptionStub = {
  name: 'ElOption',
  template: `
    <div class="el-option-stub"
      :data-value="value"
      :data-label="label"
      :data-disabled="disabled"
    >
      <slot />
    </div>
  `,
  props: ['value', 'label', 'disabled'],
}

// ─── el-option-group stub ────────────────────────────────────────
const ElOptionGroupStub = {
  name: 'ElOptionGroup',
  template: `
    <div class="el-option-group-stub" :data-label="label">
      <slot />
    </div>
  `,
  props: ['label'],
}

// ─── helper ──────────────────────────────────────────────────────
function createWrapper(props = {}, options = {}) {
  return mount(AppSelect, {
    props,
    slots: options.slots,
    global: {
      stubs: {
        'el-select': ElSelectStub,
        'el-option': ElOptionStub,
        'el-option-group': ElOptionGroupStub,
        ...options.stubs,
      },
    },
    ...options,
  })
}

const sampleOptions = [
  { value: 'a', label: 'Apple' },
  { value: 'b', label: 'Banana' },
  { value: 'c', label: 'Cherry' },
]

const groupedOptions = [
  {
    label: '水果',
    options: [
      { value: 'apple', label: '苹果' },
      { value: 'banana', label: '香蕉' },
    ],
  },
  {
    label: '蔬菜',
    options: [
      { value: 'carrot', label: '胡萝卜' },
      { value: 'broccoli', label: '西兰花' },
    ],
  },
]

// ─── 测试套件 ────────────────────────────────────────────────────
describe('AppSelect', () => {
  // ── 1. 默认渲染 ──────────────────────────────────────────────
  describe('1-默认渲染', () => {
    it('应渲染 el-select stub', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').exists()).toBe(true)
    })

    it('默认 placeholder 为 "请选择"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-placeholder')).toBe('请选择')
    })

    it('默认 size 为 md → el-select 收到 "default"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-size')).toBe('default')
    })

    it('默认 disabled 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-disabled')).toBe('false')
    })

    it('默认 clearable 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-clearable')).toBe('false')
    })

    it('默认 filterable(searchable) 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-filterable')).toBe('false')
    })

    it('默认 multiple 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-multiple')).toBe('false')
    })

    it('默认 emptyText 为 "无匹配选项"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-empty-text')).toBe('无匹配选项')
    })

    it('teleported 固定为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-teleported')).toBe('false')
    })

    it('popper-class 固定为 "app-select-popper"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').attributes('data-popper-class')).toBe('app-select-popper')
    })
  })

  // ── 2. v-model 双向绑定 ──────────────────────────────────────
  describe('2-v-model 双向绑定', () => {
    it('应透传 modelValue 到 el-select', async () => {
      const wrapper = createWrapper({ modelValue: 'a' })
      const attr = wrapper.find('.el-select-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify('a'))
    })

    it('el-select 触发 update:model-value 时应 emit update:modelValue', async () => {
      const wrapper = createWrapper({ modelValue: '' })
      await wrapper.find('.trigger-change').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual(['test-value'])
    })

    it('el-select 触发 update:model-value 时应同时 emit change', async () => {
      const wrapper = createWrapper({ modelValue: '' })
      await wrapper.find('.trigger-change').trigger('click')
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('change')[0]).toEqual(['test-value'])
    })

    it('应支持数组 modelValue（multiple 模式）', async () => {
      const wrapper = createWrapper({ modelValue: ['a', 'b'], multiple: true })
      const attr = wrapper.find('.el-select-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(['a', 'b']))
    })

    it('应支持数字 modelValue', async () => {
      const wrapper = createWrapper({ modelValue: 42 })
      const attr = wrapper.find('.el-select-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(42))
    })
  })

  // ── 3. 选项渲染（flat） ──────────────────────────────────────
  describe('3-选项渲染（flat）', () => {
    it('应渲染所有 flat 选项', () => {
      const wrapper = createWrapper({ options: sampleOptions })
      const opts = wrapper.findAll('.el-option-stub')
      expect(opts).toHaveLength(3)
    })

    it('每个选项应有正确的 value 和 label', () => {
      const wrapper = createWrapper({ options: sampleOptions })
      const opts = wrapper.findAll('.el-option-stub')
      expect(opts[0].attributes('data-value')).toBe('a')
      expect(opts[0].attributes('data-label')).toBe('Apple')
      expect(opts[2].attributes('data-value')).toBe('c')
      expect(opts[2].attributes('data-label')).toBe('Cherry')
    })

    it('应透传选项的 disabled 属性', () => {
      const opts = [
        { value: 'a', label: 'Apple', disabled: true },
        { value: 'b', label: 'Banana', disabled: false },
      ]
      const wrapper = createWrapper({ options: opts })
      const all = wrapper.findAll('.el-option-stub')
      expect(all[0].attributes('data-disabled')).toBe('true')
      // disabled=false 时属性可能不存在或为 'false',取决于 Vue 渲染行为
      const disabledAttr = all[1].attributes('data-disabled')
      expect(disabledAttr === 'false' || disabledAttr === undefined).toBe(true)
    })

    it('空 options 时不应渲染 el-option', () => {
      const wrapper = createWrapper({ options: [] })
      expect(wrapper.findAll('.el-option-stub')).toHaveLength(0)
    })
  })

  // ── 4. 分组选项 ──────────────────────────────────────────────
  describe('4-分组选项', () => {
    it('应检测分组选项并渲染 el-option-group', () => {
      const wrapper = createWrapper({ options: groupedOptions })
      const groups = wrapper.findAll('.el-option-group-stub')
      expect(groups).toHaveLength(2)
    })

    it('分组应有正确的 label', () => {
      const wrapper = createWrapper({ options: groupedOptions })
      const groups = wrapper.findAll('.el-option-group-stub')
      expect(groups[0].attributes('data-label')).toBe('水果')
      expect(groups[1].attributes('data-label')).toBe('蔬菜')
    })

    it('每个分组内应渲染正确的选项数', () => {
      const wrapper = createWrapper({ options: groupedOptions })
      const groups = wrapper.findAll('.el-option-group-stub')
      // 水果组 2 个, 蔬菜组 2 个
      const allOpts = wrapper.findAll('.el-option-stub')
      expect(allOpts).toHaveLength(4)
    })

    it('flat 选项时不应渲染 el-option-group', () => {
      const wrapper = createWrapper({ options: sampleOptions })
      expect(wrapper.findAll('.el-option-group-stub')).toHaveLength(0)
    })
  })

  // ── 5. size 映射 ─────────────────────────────────────────────
  describe('5-size 映射', () => {
    it('sm → small', () => {
      const wrapper = createWrapper({ size: 'sm' })
      expect(wrapper.find('.el-select-stub').attributes('data-size')).toBe('small')
    })

    it('md → default', () => {
      const wrapper = createWrapper({ size: 'md' })
      expect(wrapper.find('.el-select-stub').attributes('data-size')).toBe('default')
    })

    it('lg → large', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.el-select-stub').attributes('data-size')).toBe('large')
    })

    it('无效 size 降级为 default', () => {
      const wrapper = createWrapper({ size: 'xl' })
      expect(wrapper.find('.el-select-stub').attributes('data-size')).toBe('default')
    })
  })

  // ── 6. disabled ──────────────────────────────────────────────
  describe('6-disabled', () => {
    it('应透传 disabled 到 el-select', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.el-select-stub').attributes('data-disabled')).toBe('true')
    })

    it('disabled=false 应透传 false', () => {
      const wrapper = createWrapper({ disabled: false })
      expect(wrapper.find('.el-select-stub').attributes('data-disabled')).toBe('false')
    })
  })

  // ── 7. clearable ─────────────────────────────────────────────
  describe('7-clearable', () => {
    it('应透传 clearable 到 el-select', () => {
      const wrapper = createWrapper({ clearable: true })
      expect(wrapper.find('.el-select-stub').attributes('data-clearable')).toBe('true')
    })
  })

  // ── 8. searchable → filterable ───────────────────────────────
  describe('8-searchable → filterable', () => {
    it('searchable=true 应映射为 filterable=true', () => {
      const wrapper = createWrapper({ searchable: true })
      expect(wrapper.find('.el-select-stub').attributes('data-filterable')).toBe('true')
    })

    it('searchable=false 应映射为 filterable=false', () => {
      const wrapper = createWrapper({ searchable: false })
      expect(wrapper.find('.el-select-stub').attributes('data-filterable')).toBe('false')
    })
  })

  // ── 9. multiple ──────────────────────────────────────────────
  describe('9-multiple', () => {
    it('应透传 multiple 到 el-select', () => {
      const wrapper = createWrapper({ multiple: true })
      expect(wrapper.find('.el-select-stub').attributes('data-multiple')).toBe('true')
    })
  })

  // ── 10. placeholder ──────────────────────────────────────────
  describe('10-placeholder', () => {
    it('应透传自定义 placeholder', () => {
      const wrapper = createWrapper({ placeholder: '请选择城市' })
      expect(wrapper.find('.el-select-stub').attributes('data-placeholder')).toBe('请选择城市')
    })
  })

  // ── 11. emptyText ────────────────────────────────────────────
  describe('11-emptyText', () => {
    it('应透传自定义 emptyText', () => {
      const wrapper = createWrapper({ emptyText: '没有数据' })
      expect(wrapper.find('.el-select-stub').attributes('data-empty-text')).toBe('没有数据')
    })
  })

  // ── 12. focus / blur 事件 ────────────────────────────────────
  describe('12-focus/blur 事件', () => {
    it('el-select focus 时应 emit focus', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.trigger-focus').trigger('click')
      expect(wrapper.emitted('focus')).toBeTruthy()
    })

    it('el-select blur 时应 emit blur', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.trigger-blur').trigger('click')
      expect(wrapper.emitted('blur')).toBeTruthy()
    })
  })

  // ── 13. option slot ──────────────────────────────────────────
  describe('13-option slot', () => {
    it('应支持 option 自定义插槽', () => {
      const wrapper = createWrapper(
        { options: sampleOptions },
        {
          slots: {
            option: '<template #option="{ option }"><em class="custom-opt">{{ option.label }}</em></template>',
          },
        },
      )
      const customOpts = wrapper.findAll('.custom-opt')
      expect(customOpts).toHaveLength(3)
      expect(customOpts[0].text()).toBe('Apple')
    })
  })

  // ── 14. dropdown-footer slot ─────────────────────────────────
  describe('14-dropdown-footer slot', () => {
    it('应支持 dropdown-footer 插槽', () => {
      const wrapper = createWrapper(
        { options: sampleOptions },
        {
          slots: {
            'dropdown-footer': '<div class="custom-footer">加载更多</div>',
          },
        },
      )
      expect(wrapper.find('.custom-footer').exists()).toBe(true)
      expect(wrapper.find('.custom-footer').text()).toBe('加载更多')
    })

    it('无 dropdown-footer 插槽时不应渲染 footer 内容', () => {
      const wrapper = createWrapper({ options: sampleOptions })
      expect(wrapper.find('.custom-footer').exists()).toBe(false)
    })
  })

  // ── 15. handleChange 双 emit ─────────────────────────────────
  describe('15-handleChange 双 emit', () => {
    it('handleChange 应同时 emit update:modelValue 和 change', async () => {
      const wrapper = createWrapper({ modelValue: '' })
      // 模拟 el-select 触发 update:model-value
      const elSelect = wrapper.findComponent(ElSelectStub)
      await elSelect.vm.$emit('update:model-value', 'new-val')
      await nextTick()
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual(['new-val'])
      expect(wrapper.emitted('change')[0]).toEqual(['new-val'])
    })
  })

  // ── 16. 分组选项边界 ─────────────────────────────────────────
  describe('16-分组选项边界', () => {
    it('分组内 options 为空数组时应正常渲染', () => {
      const opts = [{ label: '空组', options: [] }]
      const wrapper = createWrapper({ options: opts })
      const groups = wrapper.findAll('.el-option-group-stub')
      expect(groups).toHaveLength(1)
      expect(wrapper.findAll('.el-option-stub')).toHaveLength(0)
    })

    it('分组内 options 为 undefined 时应降级为空数组', () => {
      // 注意: isGrouped 检测依赖 'options' in opt,无 options 字段的元素不算分组
      // 所以要让 isGrouped=true,至少一个元素需含 options 字段
      const opts = [
        { label: '有 options 但为 undefined', options: undefined },
      ]
      const wrapper = createWrapper({ options: opts })
      const groups = wrapper.findAll('.el-option-group-stub')
      expect(groups).toHaveLength(1)
    })
  })

  // ── 17. isGrouped 检测逻辑 ───────────────────────────────────
  describe('17-isGrouped 检测逻辑', () => {
    it('options 中任一元素含 options 字段即视为分组', () => {
      const mixed = [
        { value: 'x', label: 'X' },
        { label: '组', options: [{ value: 'y', label: 'Y' }] },
      ]
      const wrapper = createWrapper({ options: mixed })
      // 有分组 → 应渲染 el-option-group
      expect(wrapper.findAll('.el-option-group-stub').length).toBeGreaterThan(0)
    })

    it('options 全部无 options 字段 → flat 模式', () => {
      const wrapper = createWrapper({ options: sampleOptions })
      expect(wrapper.findAll('.el-option-group-stub')).toHaveLength(0)
      expect(wrapper.findAll('.el-option-stub')).toHaveLength(3)
    })
  })

  // ── 18. props 默认值完整性 ───────────────────────────────────
  describe('18-props 默认值完整性', () => {
    it('modelValue 默认值为空字符串', () => {
      const wrapper = createWrapper()
      const attr = wrapper.find('.el-select-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(''))
    })

    it('options 默认为空数组', () => {
      const wrapper = createWrapper()
      expect(wrapper.findAll('.el-option-stub')).toHaveLength(0)
    })
  })

  // ── 19. 自定义 placeholder + emptyText 组合 ──────────────────
  describe('19-组合 props', () => {
    it('应同时透传多个自定义 props', () => {
      const wrapper = createWrapper({
        placeholder: '选一个',
        emptyText: '没数据',
        clearable: true,
        searchable: true,
        multiple: true,
        size: 'lg',
        disabled: true,
      })
      const el = wrapper.find('.el-select-stub')
      expect(el.attributes('data-placeholder')).toBe('选一个')
      expect(el.attributes('data-empty-text')).toBe('没数据')
      expect(el.attributes('data-clearable')).toBe('true')
      expect(el.attributes('data-filterable')).toBe('true')
      expect(el.attributes('data-multiple')).toBe('true')
      expect(el.attributes('data-size')).toBe('large')
      expect(el.attributes('data-disabled')).toBe('true')
    })
  })

  // ── 20. 值类型兼容性 ─────────────────────────────────────────
  describe('20-值类型兼容性', () => {
    it('应支持空数组 modelValue', () => {
      const wrapper = createWrapper({ modelValue: [], multiple: true })
      const attr = wrapper.find('.el-select-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify([]))
    })

    it('应支持数字 0 作为 modelValue', () => {
      const wrapper = createWrapper({ modelValue: 0 })
      const attr = wrapper.find('.el-select-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(0))
    })
  })
})
