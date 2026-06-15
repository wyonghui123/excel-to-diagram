/**
 * AppDatePicker.spec.js — YonDesign AppDatePicker 组件测试
 *
 * 测试策略:
 * - Stub el-date-picker（不依赖 Element Plus 真实实现）
 * - 验证 props 透传、v-model 双向绑定、事件转发、日期格式化
 * - 覆盖 20 个场景,约 62 个用例
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AppDatePicker from '../AppDatePicker.vue'

// ─── el-date-picker stub ─────────────────────────────────────────
const ElDatePickerStub = {
  name: 'ElDatePicker',
  template: `
    <div class="el-date-picker-stub"
      :data-model-value="JSON.stringify(modelValue)"
      :data-type="type"
      :data-placeholder="placeholder"
      :data-disabled="disabled"
      :data-clearable="clearable"
      :data-format="format"
      :data-value-format="valueFormat"
      :data-readonly="readonly"
      :data-size="size"
      :data-empty-text="emptyText"
      :data-teleported="teleported"
      :data-popper-class="popperClass"
    >
      <button class="trigger-focus" @click="$emit('focus')" />
      <button class="trigger-blur" @click="$emit('blur')" />
      <button class="trigger-change" @click="$emit('change', '2026-06-13')" />
      <button class="trigger-update" @click="$emit('update:model-value', '2026-06-13')" />
    </div>
  `,
  props: [
    'modelValue', 'type', 'placeholder', 'disabled', 'clearable',
    'format', 'valueFormat', 'readonly', 'size', 'emptyText',
    'teleported', 'popperClass',
  ],
  emits: ['update:model-value', 'focus', 'blur', 'change'],
}

// ─── helper ──────────────────────────────────────────────────────
function createWrapper(props = {}, options = {}) {
  return mount(AppDatePicker, {
    props,
    slots: options.slots,
    global: {
      stubs: {
        'el-date-picker': ElDatePickerStub,
        ...options.stubs,
      },
    },
    ...options,
  })
}

// ─── 测试套件 ────────────────────────────────────────────────────
describe('AppDatePicker', () => {
  // ── 1. 默认渲染 ──────────────────────────────────────────────
  describe('1-默认渲染', () => {
    it('应渲染 el-date-picker stub', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').exists()).toBe(true)
    })

    it('默认 type 为 "date"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-type')).toBe('date')
    })

    it('默认 placeholder 为 "请选择日期"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-placeholder')).toBe('请选择日期')
    })

    it('默认 disabled 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-disabled')).toBe('false')
    })

    it('默认 clearable 为 true', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-clearable')).toBe('true')
    })

    it('默认 format 为 "YYYY-MM-DD"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-format')).toBe('YYYY-MM-DD')
    })

    it('默认 valueFormat 为 "YYYY-MM-DD"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-value-format')).toBe('YYYY-MM-DD')
    })

    it('默认 readonly 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-readonly')).toBe('false')
    })

    it('默认 size 为 "default"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-size')).toBe('default')
    })

    it('默认 emptyText 为 "暂无数据"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-empty-text')).toBe('暂无数据')
    })

    it('teleported 固定为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-teleported')).toBe('false')
    })

    it('popper-class 固定为 "app-datepicker-popper"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').attributes('data-popper-class')).toBe('app-datepicker-popper')
    })
  })

  // ── 2. v-model 双向绑定 ──────────────────────────────────────
  describe('2-v-model 双向绑定', () => {
    it('应透传 modelValue 到 el-date-picker', async () => {
      const wrapper = createWrapper({ modelValue: '2026-06-13' })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify('2026-06-13'))
    })

    it('el-date-picker 触发 update:model-value 时应 emit update:modelValue', async () => {
      const wrapper = createWrapper({ modelValue: null })
      await wrapper.find('.trigger-update').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual(['2026-06-13'])
    })

    it('应支持数组 modelValue（daterange 模式）', async () => {
      const wrapper = createWrapper({
        modelValue: ['2026-06-01', '2026-06-30'],
        type: 'daterange',
      })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(['2026-06-01', '2026-06-30']))
    })

    it('应支持 Date 对象 modelValue', async () => {
      const date = new Date('2026-06-13')
      const wrapper = createWrapper({ modelValue: date })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(date.toISOString()))
    })

    it('应支持数字时间戳 modelValue', async () => {
      const timestamp = 1718236800000
      const wrapper = createWrapper({ modelValue: timestamp })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(timestamp))
    })

    it('应支持 null modelValue', async () => {
      const wrapper = createWrapper({ modelValue: null })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(null))
    })
  })

  // ── 3. type 透传 ─────────────────────────────────────────────
  describe('3-type 透传', () => {
    it('应透传 type="datetime"', () => {
      const wrapper = createWrapper({ type: 'datetime' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-type')).toBe('datetime')
    })

    it('应透传 type="daterange"', () => {
      const wrapper = createWrapper({ type: 'daterange' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-type')).toBe('daterange')
    })

    it('应透传 type="month"', () => {
      const wrapper = createWrapper({ type: 'month' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-type')).toBe('month')
    })

    it('应透传 type="year"', () => {
      const wrapper = createWrapper({ type: 'year' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-type')).toBe('year')
    })
  })

  // ── 4. placeholder ──────────────────────────────────────────
  describe('4-placeholder', () => {
    it('应透传自定义 placeholder', () => {
      const wrapper = createWrapper({ placeholder: '选择开始日期' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-placeholder')).toBe('选择开始日期')
    })
  })

  // ── 5. disabled ─────────────────────────────────────────────
  describe('5-disabled', () => {
    it('应透传 disabled=true', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-disabled')).toBe('true')
    })

    it('应透传 disabled=false', () => {
      const wrapper = createWrapper({ disabled: false })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-disabled')).toBe('false')
    })
  })

  // ── 6. clearable ────────────────────────────────────────────
  describe('6-clearable', () => {
    it('应透传 clearable=true', () => {
      const wrapper = createWrapper({ clearable: true })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-clearable')).toBe('true')
    })

    it('应透传 clearable=false', () => {
      const wrapper = createWrapper({ clearable: false })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-clearable')).toBe('false')
    })
  })

  // ── 7. format / valueFormat ─────────────────────────────────
  describe('7-format / valueFormat', () => {
    it('应透传自定义 format', () => {
      const wrapper = createWrapper({ format: 'YYYY/MM/DD' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-format')).toBe('YYYY/MM/DD')
    })

    it('应透传自定义 valueFormat', () => {
      const wrapper = createWrapper({ valueFormat: 'YYYY-MM-DD HH:mm:ss' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-value-format')).toBe('YYYY-MM-DD HH:mm:ss')
    })

    it('应同时透传 format 和 valueFormat', () => {
      const wrapper = createWrapper({
        format: 'MM/DD/YYYY',
        valueFormat: 'YYYY-MM-DD',
      })
      const el = wrapper.find('.el-date-picker-stub')
      expect(el.attributes('data-format')).toBe('MM/DD/YYYY')
      expect(el.attributes('data-value-format')).toBe('YYYY-MM-DD')
    })
  })

  // ── 8. readonly ─────────────────────────────────────────────
  describe('8-readonly', () => {
    it('应透传 readonly=true', () => {
      const wrapper = createWrapper({ readonly: true })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-readonly')).toBe('true')
    })

    it('应透传 readonly=false', () => {
      const wrapper = createWrapper({ readonly: false })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-readonly')).toBe('false')
    })
  })

  // ── 9. size 映射 ────────────────────────────────────────────
  describe('9-size 映射', () => {
    it('small → small', () => {
      const wrapper = createWrapper({ size: 'small' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-size')).toBe('small')
    })

    it('default → default', () => {
      const wrapper = createWrapper({ size: 'default' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-size')).toBe('default')
    })

    it('large → large', () => {
      const wrapper = createWrapper({ size: 'large' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-size')).toBe('large')
    })

    it('无效 size 降级为 default', () => {
      const wrapper = createWrapper({ size: 'medium' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-size')).toBe('default')
    })
  })

  // ── 10. emptyText ───────────────────────────────────────────
  describe('10-emptyText', () => {
    it('应透传自定义 emptyText', () => {
      const wrapper = createWrapper({ emptyText: '无日期' })
      expect(wrapper.find('.el-date-picker-stub').attributes('data-empty-text')).toBe('无日期')
    })
  })

  // ── 11. focus / blur 事件 ───────────────────────────────────
  describe('11-focus/blur 事件', () => {
    it('el-date-picker focus 时应 emit focus', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.trigger-focus').trigger('click')
      expect(wrapper.emitted('focus')).toBeTruthy()
    })

    it('el-date-picker blur 时应 emit blur', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.trigger-blur').trigger('click')
      expect(wrapper.emitted('blur')).toBeTruthy()
    })
  })

  // ── 12. change 事件 ─────────────────────────────────────────
  describe('12-change 事件', () => {
    it('el-date-picker change 时应 emit change', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.trigger-change').trigger('click')
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('change')[0]).toEqual(['2026-06-13'])
    })
  })

  // ── 13. handleChange 逻辑 ───────────────────────────────────
  describe('13-handleChange 逻辑', () => {
    it('handleChange 应 emit update:modelValue', async () => {
      const wrapper = createWrapper({ modelValue: null })
      const elDatePicker = wrapper.findComponent(ElDatePickerStub)
      await elDatePicker.vm.$emit('update:model-value', '2026-06-13')
      await nextTick()
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual(['2026-06-13'])
    })
  })

  // ── 14. 范围选择类型 ────────────────────────────────────────
  describe('14-范围选择类型', () => {
    it('daterange 模式应支持数组 modelValue', () => {
      const wrapper = createWrapper({
        type: 'daterange',
        modelValue: ['2026-06-01', '2026-06-30'],
      })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(['2026-06-01', '2026-06-30']))
    })

    it('datetimerange 模式应支持数组 modelValue', () => {
      const wrapper = createWrapper({
        type: 'datetimerange',
        modelValue: ['2026-06-01 10:00:00', '2026-06-30 18:00:00'],
      })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(['2026-06-01 10:00:00', '2026-06-30 18:00:00']))
    })
  })

  // ── 15. 不同日期格式 ────────────────────────────────────────
  describe('15-不同日期格式', () => {
    it('应支持 YYYY-MM-DD HH:mm:ss 格式', () => {
      const wrapper = createWrapper({
        type: 'datetime',
        format: 'YYYY-MM-DD HH:mm:ss',
        valueFormat: 'YYYY-MM-DD HH:mm:ss',
      })
      const el = wrapper.find('.el-date-picker-stub')
      expect(el.attributes('data-format')).toBe('YYYY-MM-DD HH:mm:ss')
      expect(el.attributes('data-value-format')).toBe('YYYY-MM-DD HH:mm:ss')
    })

    it('应支持 YYYY/MM/DD 格式', () => {
      const wrapper = createWrapper({
        format: 'YYYY/MM/DD',
        valueFormat: 'YYYY/MM/DD',
      })
      const el = wrapper.find('.el-date-picker-stub')
      expect(el.attributes('data-format')).toBe('YYYY/MM/DD')
      expect(el.attributes('data-value-format')).toBe('YYYY/MM/DD')
    })

    it('应支持 MM/DD/YYYY 格式', () => {
      const wrapper = createWrapper({
        format: 'MM/DD/YYYY',
        valueFormat: 'MM/DD/YYYY',
      })
      const el = wrapper.find('.el-date-picker-stub')
      expect(el.attributes('data-format')).toBe('MM/DD/YYYY')
      expect(el.attributes('data-value-format')).toBe('MM/DD/YYYY')
    })
  })

  // ── 16. props 默认值完整性 ──────────────────────────────────
  describe('16-props 默认值完整性', () => {
    it('modelValue 默认为 null', () => {
      const wrapper = createWrapper()
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(null))
    })
  })

  // ── 17. 组合 props ──────────────────────────────────────────
  describe('17-组合 props', () => {
    it('应同时透传多个自定义 props', () => {
      const wrapper = createWrapper({
        type: 'datetime',
        placeholder: '选择日期时间',
        disabled: true,
        clearable: false,
        format: 'YYYY-MM-DD HH:mm',
        valueFormat: 'YYYY-MM-DD HH:mm:ss',
        readonly: true,
        size: 'large',
        emptyText: '无数据',
      })
      const el = wrapper.find('.el-date-picker-stub')
      expect(el.attributes('data-type')).toBe('datetime')
      expect(el.attributes('data-placeholder')).toBe('选择日期时间')
      expect(el.attributes('data-disabled')).toBe('true')
      expect(el.attributes('data-clearable')).toBe('false')
      expect(el.attributes('data-format')).toBe('YYYY-MM-DD HH:mm')
      expect(el.attributes('data-value-format')).toBe('YYYY-MM-DD HH:mm:ss')
      expect(el.attributes('data-readonly')).toBe('true')
      expect(el.attributes('data-size')).toBe('large')
      expect(el.attributes('data-empty-text')).toBe('无数据')
    })
  })

  // ── 18. 值类型兼容性 ────────────────────────────────────────
  describe('18-值类型兼容性', () => {
    it('应支持空字符串 modelValue', () => {
      const wrapper = createWrapper({ modelValue: '' })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify(''))
    })

    it('应支持空数组 modelValue', () => {
      const wrapper = createWrapper({ modelValue: [], type: 'daterange' })
      const attr = wrapper.find('.el-date-picker-stub').attributes('data-model-value')
      expect(attr).toBe(JSON.stringify([]))
    })
  })

  // ── 19. 事件完整性 ──────────────────────────────────────────
  describe('19-事件完整性', () => {
    it('应支持所有 4 个事件: update:modelValue, change, focus, blur', async () => {
      const wrapper = createWrapper({ modelValue: null })
      
      // focus
      await wrapper.find('.trigger-focus').trigger('click')
      expect(wrapper.emitted('focus')).toBeTruthy()
      
      // blur
      await wrapper.find('.trigger-blur').trigger('click')
      expect(wrapper.emitted('blur')).toBeTruthy()
      
      // change
      await wrapper.find('.trigger-change').trigger('click')
      expect(wrapper.emitted('change')).toBeTruthy()
      
      // update:modelValue
      await wrapper.find('.trigger-update').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    })
  })

  // ── 20. 边界情况 ────────────────────────────────────────────
  describe('20-边界情况', () => {
    it('modelValue 为 undefined 时应正常渲染', () => {
      const wrapper = createWrapper({ modelValue: undefined })
      expect(wrapper.find('.el-date-picker-stub').exists()).toBe(true)
    })

    it('所有 props 都为默认值时应正常渲染', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-date-picker-stub').exists()).toBe(true)
    })
  })
})
