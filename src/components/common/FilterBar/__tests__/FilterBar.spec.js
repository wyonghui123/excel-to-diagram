/**
 * FilterBar.spec.js - 筛选栏组件测试
 *
 * 测试核心功能：
 * 1. 文本输入渲染和更新
 * 2. 下拉选择渲染和更新
 * 3. 日期范围处理
 * 4. 多选下拉框
 * 5. 重置功能
 * 6. 搜索按钮
 * 7. modelValue 更新
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import FilterBar from '@/components/common/FilterBar/FilterBar.vue'

vi.mock('@/components/common', () => ({
  DateTimePicker: {
    name: 'DateTimePicker',
    template: '<input class="date-time-picker" :value="modelValue" @input="$emit(\'update:model-value\', $event.target.value)" />',
    props: ['modelValue', 'placeholder', 'showTime', 'showSeconds', 'size', 'clearable'],
    emits: ['update:model-value'],
  },
}))

vi.mock('@/components/common/ValueHelpField.vue', () => ({
  default: {
    name: 'ValueHelpField',
    template: '<input class="value-help-field" :value="modelValue" @input="$emit(\'update:model-value\', $event.target.value)" />',
    props: ['modelValue', 'valueHelpConfig', 'placeholder', 'formValues'],
    emits: ['update:model-value'],
  },
}))

const createWrapper = (props = {}) => {
  return mount(FilterBar, {
    props: {
      fields: [],
      modelValue: {},
      ...props,
    },
    attachTo: document.body,
  })
}

describe('FilterBar', () => {
  describe('text input', () => {
    it('renders text input field', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称', type: 'text' }],
      })
      expect(wrapper.find('.filter-bar__input').exists()).toBe(true)
      expect(wrapper.find('.filter-bar__label').text()).toBe('名称')
    })

    it('emits update:modelValue on input', async () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: {},
      })
      const input = wrapper.find('.filter-bar__input')
      await input.setValue('test')

      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0][0]).toEqual({ name: 'test' })
    })

    it('shows clear button when value is present', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: { name: 'test' },
      })
      expect(wrapper.find('.filter-bar__clear').exists()).toBe(true)
    })

    it('clears value on clear button click', async () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: { name: 'test' },
      })
      await wrapper.find('.filter-bar__clear').trigger('click')
      expect(wrapper.emitted('update:modelValue')[0][0].name).toBe('')
    })

    it('uses custom placeholder', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称', placeholder: '请输入名称' }],
      })
      expect(wrapper.find('.filter-bar__input').attributes('placeholder')).toBe('请输入名称')
    })

    it('emits search on Enter key', async () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
      })
      await wrapper.find('.filter-bar__input').trigger('keyup.enter')
      expect(wrapper.emitted('search')).toBeTruthy()
    })
  })

  describe('select input', () => {
    it('renders select field', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'status',
          label: '状态',
          type: 'select',
          options: [
            { value: 'active', label: '激活' },
            { value: 'inactive', label: '未激活' },
          ],
        }],
      })
      expect(wrapper.find('.filter-bar__select').exists()).toBe(true)
      const options = wrapper.findAll('option')
      expect(options.length).toBe(2)
    })

    it('emits update:modelValue on change', async () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'status',
          label: '状态',
          type: 'select',
          options: [{ value: 'active', label: '激活' }],
        }],
      })
      await wrapper.find('.filter-bar__select').setValue('active')
      expect(wrapper.emitted('update:modelValue')[0][0]).toEqual({ status: 'active' })
    })

    it('shows placeholder option', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'status',
          label: '状态',
          type: 'select',
          placeholder: '请选择',
          options: [{ value: 'active', label: '激活' }],
        }],
      })
      const options = wrapper.findAll('option')
      expect(options[0].text()).toBe('请选择')
    })
  })

  describe('number input', () => {
    it('renders number input field', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'amount', label: '金额', type: 'number' }],
      })
      const input = wrapper.find('.filter-bar__input')
      expect(input.exists()).toBe(true)
      expect(input.attributes('type')).toBe('number')
    })
  })

  describe('user input', () => {
    it('renders user text input field', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'creator', label: '创建人', type: 'user' }],
      })
      expect(wrapper.find('.filter-bar__input').exists()).toBe(true)
    })
  })

  describe('multi-select', () => {
    it('renders multi-select field', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [
            { value: 'a', label: '标签A' },
            { value: 'b', label: '标签B' },
          ],
        }],
      })
      expect(wrapper.find('.filter-bar__multi-select').exists()).toBe(true)
    })

    it('shows placeholder when no selection', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [{ value: 'a', label: '标签A' }],
        }],
        modelValue: {},
      })
      expect(wrapper.vm.getMultiSelectLabel(wrapper.props('fields')[0])).toBe('请选择标签')
    })

    it('shows selected labels', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [
            { value: 'a', label: '标签A' },
            { value: 'b', label: '标签B' },
          ],
        }],
        modelValue: { tags: ['a', 'b'] },
      })
      expect(wrapper.vm.getMultiSelectLabel(wrapper.props('fields')[0])).toBe('标签A, 标签B')
    })

    it('shows count when more than 2 selected', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [
            { value: 'a', label: '标签A' },
            { value: 'b', label: '标签B' },
            { value: 'c', label: '标签C' },
          ],
        }],
        modelValue: { tags: ['a', 'b', 'c'] },
      })
      expect(wrapper.vm.getMultiSelectLabel(wrapper.props('fields')[0])).toBe('已选 3 项')
    })

    it('toggles option selection', async () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [{ value: 'a', label: '标签A' }],
        }],
        modelValue: { tags: [] },
      })
      wrapper.vm.toggleOption('tags', 'a')
      expect(wrapper.emitted('update:modelValue')[0][0].tags).toEqual(['a'])
    })

    it('deselects already selected option', async () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [{ value: 'a', label: '标签A' }],
        }],
        modelValue: { tags: ['a'] },
      })
      wrapper.vm.toggleOption('tags', 'a')
      expect(wrapper.emitted('update:modelValue')[0][0].tags).toEqual([])
    })

    it('selects all options', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [
            { value: 'a', label: '标签A' },
            { value: 'b', label: '标签B' },
          ],
        }],
        modelValue: {},
      })
      wrapper.vm.selectAllOptions(wrapper.props('fields')[0])
      expect(wrapper.emitted('update:modelValue')[0][0].tags).toEqual(['a', 'b'])
    })

    it('clears all options', () => {
      const wrapper = createWrapper({
        fields: [{
          key: 'tags',
          label: '标签',
          type: 'multi-select',
          options: [{ value: 'a', label: '标签A' }],
        }],
        modelValue: { tags: ['a'] },
      })
      wrapper.vm.clearAllOptions(wrapper.props('fields')[0])
      expect(wrapper.emitted('update:modelValue')[0][0].tags).toEqual([])
    })

    it('checks if option is selected', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'tags', label: '标签', type: 'multi-select', options: [] }],
        modelValue: { tags: ['a', 'b'] },
      })
      expect(wrapper.vm.isOptionSelected('tags', 'a')).toBe(true)
      expect(wrapper.vm.isOptionSelected('tags', 'c')).toBe(false)
    })
  })

  describe('date range', () => {
    it('handles updateDateRange for start', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'date', label: '日期', type: 'date-range' }],
        modelValue: { date: [] },
      })
      wrapper.vm.updateDateRange('date', 'start', '2024-01-01')
      expect(wrapper.emitted('update:modelValue')[0][0].date[0]).toBe('2024-01-01')
    })

    it('handles updateDateRange for end', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'date', label: '日期', type: 'date-range' }],
        modelValue: { date: ['2024-01-01', ''] },
      })
      wrapper.vm.updateDateRange('date', 'end', '2024-12-31')
      expect(wrapper.emitted('update:modelValue')[0][0].date).toEqual(['2024-01-01', '2024-12-31'])
    })

    it('clears date range', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'date', label: '日期', type: 'date-range' }],
        modelValue: { date: ['2024-01-01', '2024-12-31'] },
      })
      wrapper.vm.clearDateRange('date')
      expect(wrapper.emitted('update:modelValue')[0][0].date).toEqual([])
    })

    it('detects date range value', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'date', label: '日期', type: 'date-range' }],
        modelValue: { date: ['2024-01-01', ''] },
      })
      expect(wrapper.vm.hasDateRangeValue('date')).toBeTruthy()
    })

    it('detects empty date range', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'date', label: '日期', type: 'date-range' }],
        modelValue: { date: ['', ''] },
      })
      expect(wrapper.vm.hasDateRangeValue('date')).toBeFalsy()
    })

    it('getDateValue returns start or end', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'date', label: '日期', type: 'date-range' }],
        modelValue: { date: ['2024-01-01', '2024-12-31'] },
      })
      expect(wrapper.vm.getDateValue('date', 'start')).toBe('2024-01-01')
      expect(wrapper.vm.getDateValue('date', 'end')).toBe('2024-12-31')
    })
  })

  describe('reset', () => {
    it('emits update:modelValue with empty object and reset event', async () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: { name: 'test' },
        showReset: true,
      })
      await wrapper.find('.filter-bar__btn--reset').trigger('click')
      expect(wrapper.emitted('update:modelValue')[0][0]).toEqual({})
      expect(wrapper.emitted('reset')).toBeTruthy()
    })

    it('hides reset button when showReset is false', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        showReset: false,
      })
      expect(wrapper.find('.filter-bar__btn--reset').exists()).toBe(false)
    })
  })

  describe('search', () => {
    it('emits search on search button click', async () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
      })
      await wrapper.find('.filter-bar__btn--search').trigger('click')
      expect(wrapper.emitted('search')).toBeTruthy()
    })
  })

  describe('getModelValue', () => {
    it('returns empty string for undefined', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: {},
      })
      expect(wrapper.vm.getModelValue('name')).toBe('')
    })

    it('returns empty string for null', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: { name: null },
      })
      expect(wrapper.vm.getModelValue('name')).toBe('')
    })

    it('returns value when present', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'name', label: '名称' }],
        modelValue: { name: 'test' },
      })
      expect(wrapper.vm.getModelValue('name')).toBe('test')
    })
  })

  describe('hasEmptyOption', () => {
    it('returns true when options contain empty value', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'status', label: '状态', type: 'select', options: [{ value: '', label: '全部' }] }],
      })
      expect(wrapper.vm.hasEmptyOption(wrapper.props('fields')[0])).toBe(true)
    })

    it('returns false when no empty option', () => {
      const wrapper = createWrapper({
        fields: [{ key: 'status', label: '状态', type: 'select', options: [{ value: 'active', label: '激活' }] }],
      })
      expect(wrapper.vm.hasEmptyOption(wrapper.props('fields')[0])).toBe(false)
    })
  })
})
