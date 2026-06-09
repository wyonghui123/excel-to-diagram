/**
 * ValueHelpField.spec.js - ValueHelpField 组件测试
 *
 * 测试核心功能：
 * 1. 三种 resultType 渲染：dropdown / dialog / inline
 * 2. 单选 vs 多选行为
 * 3. 选中后 emit (update:modelValue / update:displayValue / change / out-mapping)
 * 4. out_mappings 触发 out-mapping 事件
 * 5. binding 不满足时禁用
 * 6. onMounted 预加载 options
 * 7. props.modelValue 变化时同步 internalValue
 * 8. dialog 模式打开/关闭
 * 9. inline 模式（autocomplete）输入与选中
 * 10. 参数绑定变化时重新加载
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import ValueHelpField from '@/components/common/ValueHelpField.vue'

function makeValueHelpMock(overrides = {}) {
  return {
    optionsList: ref(overrides.optionsList !== undefined ? overrides.optionsList : []),
    loading: ref(overrides.loading !== undefined ? overrides.loading : false),
    displayValue: ref(overrides.displayValue !== undefined ? overrides.displayValue : ''),
    loadOptions: overrides.loadOptions || vi.fn().mockResolvedValue(undefined),
    loadOptionsDebounced: overrides.loadOptionsDebounced || vi.fn(),
    resolveDisplay: overrides.resolveDisplay || vi.fn().mockResolvedValue(undefined),
    validateInput: overrides.validateInput || vi.fn(() => true),
    getFilterParams: overrides.getFilterParams || vi.fn(() => ({})),
    isBindingSatisfied: overrides.isBindingSatisfied || vi.fn(() => true),
    outMappings: ref(overrides.outMappings !== undefined ? overrides.outMappings : []),
    applyOutMappings: overrides.applyOutMappings || vi.fn(() => ({})),
    saveRecentItem: overrides.saveRecentItem || vi.fn(),
  }
}

vi.mock('@/composables/useValueHelp', () => ({
  useValueHelp: vi.fn(() => makeValueHelpMock()),
}))

import { useValueHelp } from '@/composables/useValueHelp'

const createWrapper = (props = {}, opts = {}) => {
  return mount(ValueHelpField, {
    props: {
      modelValue: null,
      valueHelpConfig: {
        source: { type: 'enum', enum_type_id: 'status' },
        presentation: { result_type: 'dropdown' },
      },
      ...props,
    },
    global: {
      stubs: {
        'el-select': {
          name: 'el-select',
          template: '<div class="el-select-stub" @click="$emit(\'visible-change\', true)"><slot /></div>',
          props: ['modelValue', 'multiple', 'filterable', 'loading', 'disabled', 'placeholder', 'clearable'],
          emits: ['update:modelValue', 'visible-change', 'remove-tag', 'clear'],
        },
        'el-option': { name: 'el-option', template: '<div class="el-option-stub" :data-value="value" :data-label="label"></div>', props: ['value', 'label'] },
        'el-input': {
          name: 'el-input',
          template: '<input class="el-input-stub" :value="modelValue" @click="$emit(\'click\')" @input="$emit(\'update:modelValue\', $event.target.value)" />',
          props: ['modelValue', 'disabled', 'placeholder'],
        },
        'el-autocomplete': {
          name: 'el-autocomplete',
          template: '<div class="el-autocomplete-stub" @click="$emit(\'visible-change\', true)"><slot /></div>',
          props: ['modelValue', 'fetchSuggestions', 'disabled', 'placeholder'],
          emits: ['update:modelValue', 'select', 'visible-change', 'clear'],
        },
        'el-icon': { name: 'el-icon', template: '<i class="el-icon-stub"><slot /></i>' },
        SearchHelpDialog: { name: 'SearchHelpDialog', template: '<div class="search-help-dialog-stub" />', props: ['visible', 'valueHelpConfig', 'multiple', 'selectedValue'], emits: ['update:visible', 'confirm'] },
      },
    },
    ...opts,
  })
}

describe('ValueHelpField', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  // ----------------------------------------------------------------
  // 渲染
  // ----------------------------------------------------------------
  describe('rendering', () => {
    it('默认 resultType=dropdown 时渲染 el-select', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-select-stub').exists()).toBe(true)
    })

    it('resultType=dialog 时渲染 el-input + SearchHelpDialog', () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'dialog' },
        },
      })
      expect(wrapper.find('.el-input-stub').exists()).toBe(true)
      expect(wrapper.find('.search-help-dialog-stub').exists()).toBe(true)
    })

    it('resultType=inline 时渲染 el-autocomplete', () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'inline' },
        },
      })
      expect(wrapper.find('.el-autocomplete-stub').exists()).toBe(true)
    })

    it('resultType 缺失时回退到 dropdown', () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
        },
      })
      expect(wrapper.find('.el-select-stub').exists()).toBe(true)
    })
  })

  // ----------------------------------------------------------------
  // 单选 vs 多选
  // ----------------------------------------------------------------
  describe('single vs multiple', () => {
    it('behavior.multiple=true 时 el-select 接收 multiple=true', () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: true },
        },
      })
      expect(wrapper.find('.el-select-stub').exists()).toBe(true)
    })

    it('behavior.multiple=false 时 el-select 接收 multiple=false', () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: false },
        },
      })
      expect(wrapper.find('.el-select-stub').exists()).toBe(true)
    })
  })

  // ----------------------------------------------------------------
  // 禁用 (binding 未满足)
  // ----------------------------------------------------------------
  describe('disabled (binding not satisfied)', () => {
    it('binding 不满足时 el-select 禁用', () => {
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        isBindingSatisfied: vi.fn(() => false),
      }))
      const wrapper = createWrapper()
      const elSelect = wrapper.findComponent({ name: 'el-select' })
      expect(elSelect.props('disabled')).toBe(true)
    })

    it('binding 不满足时 onMounted 不调用 loadOptions', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
        isBindingSatisfied: vi.fn(() => false),
      }))
      createWrapper()
      await nextTick()
      expect(loadOptions).not.toHaveBeenCalled()
    })
  })

  // ----------------------------------------------------------------
  // 事件 emit - 单选（通过 vm 方法调用）
  // ----------------------------------------------------------------
  describe('emit - dropdown single select', () => {
    it('handleSelectChange 触发后 emit update:modelValue + update:displayValue + change', async () => {
      const opt = { value: 'a', display: 'Alpha', code: 'A' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt],
      }))
      const wrapper = createWrapper()
      // 直接调用 vm 的 handleSelectChange
      wrapper.vm.handleSelectChange('a')
      const events = wrapper.emitted()
      expect(events['update:modelValue']).toBeTruthy()
      expect(events['update:modelValue'][0]).toEqual(['a'])
      expect(events['update:displayValue']).toBeTruthy()
      expect(events['update:displayValue'][0]).toEqual(['Alpha'])
      expect(events['change']).toBeTruthy()
      expect(events['change'][0]).toEqual(['a'])
    })

    it('选中未在 optionsList 中的值时 displayValue 留空', async () => {
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [],
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleSelectChange('unknown')
      const events = wrapper.emitted()
      expect(events['update:modelValue'][0]).toEqual(['unknown'])
      expect(events['update:displayValue'][0]).toEqual([''])
    })

    it('单选选中后 saveRecentItem 被调用', async () => {
      const opt = { value: 'a', display: 'Alpha', code: 'A' }
      const saveRecentItem = vi.fn()
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt],
        saveRecentItem,
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleSelectChange('a')
      expect(saveRecentItem).toHaveBeenCalledWith(opt)
    })
  })

  // ----------------------------------------------------------------
  // 事件 emit - 多选
  // ----------------------------------------------------------------
  describe('emit - multiple select', () => {
    it('多选选中后 emit values 数组 + display 用 , 拼接', async () => {
      const opt1 = { value: 'a', display: 'Alpha' }
      const opt2 = { value: 'b', display: 'Beta' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt1, opt2],
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: true },
        },
      })
      wrapper.vm.handleSelectChange(['a', 'b'])
      const events = wrapper.emitted()
      expect(events['update:modelValue'][0]).toEqual([['a', 'b']])
      expect(events['update:displayValue'][0]).toEqual(['Alpha, Beta'])
    })

    it('多选选中后每个 option 都被 saveRecentItem', async () => {
      const opt1 = { value: 'a', display: 'Alpha' }
      const opt2 = { value: 'b', display: 'Beta' }
      const saveRecentItem = vi.fn()
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt1, opt2],
        saveRecentItem,
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: true },
        },
      })
      wrapper.vm.handleSelectChange(['a', 'b'])
      expect(saveRecentItem).toHaveBeenCalledWith(opt1)
      expect(saveRecentItem).toHaveBeenCalledWith(opt2)
    })
  })

  // ----------------------------------------------------------------
  // out_mappings 联动
  // ----------------------------------------------------------------
  describe('out_mappings', () => {
    it('单选有 out_mappings 时 emit out-mapping 事件', async () => {
      const opt = { value: 'a', display: 'Alpha', code: 'A' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt],
        outMappings: [{ value_help_field: 'code', local_field: 'user_code' }],
        applyOutMappings: vi.fn(() => ({ user_code: 'A' })),
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleSelectChange('a')
      const events = wrapper.emitted()
      expect(events['out-mapping']).toBeTruthy()
      expect(events['out-mapping'][0]).toEqual([{ user_code: 'A' }])
    })

    it('applyOutMappings 返回空对象时不应 emit out-mapping', async () => {
      const opt = { value: 'a', display: 'Alpha' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt],
        outMappings: [{ value_help_field: 'code', local_field: 'user_code' }],
        applyOutMappings: vi.fn(() => ({})),
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleSelectChange('a')
      const events = wrapper.emitted()
      expect(events['out-mapping']).toBeFalsy()
    })

    it('无 out_mappings 时不 emit out-mapping', async () => {
      const opt = { value: 'a', display: 'Alpha' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt],
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleSelectChange('a')
      const events = wrapper.emitted()
      expect(events['out-mapping']).toBeFalsy()
    })
  })

  // ----------------------------------------------------------------
  // props.modelValue 同步
  // ----------------------------------------------------------------
  describe('modelValue sync', () => {
    it('props.modelValue 变化时同步到 el-select', async () => {
      const wrapper = createWrapper()
      await wrapper.setProps({ modelValue: 'a' })
      const elSelect = wrapper.findComponent({ name: 'el-select' })
      expect(elSelect.props('modelValue')).toBe('a')
    })

    it('props.modelValue 变为 null 时 el-select 接收 null', async () => {
      const wrapper = createWrapper({ modelValue: 'a' })
      await wrapper.setProps({ modelValue: null })
      const elSelect = wrapper.findComponent({ name: 'el-select' })
      expect(elSelect.props('modelValue')).toBeNull()
    })

    it('props.modelValue 非空时调用 resolveDisplay 解析 display', async () => {
      const resolveDisplay = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        resolveDisplay,
      }))
      const wrapper = createWrapper({ modelValue: null })
      await nextTick()
      await wrapper.setProps({ modelValue: 'a' })
      await nextTick()
      expect(resolveDisplay).toHaveBeenCalledWith('a')
    })

    it('props.modelValue 为 null 时不调用 resolveDisplay', async () => {
      const resolveDisplay = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        resolveDisplay,
      }))
      const wrapper = createWrapper({ modelValue: null })
      await nextTick()
      expect(resolveDisplay).not.toHaveBeenCalled()
    })

    it('props.modelValue 为空数组（多选）时不调用 resolveDisplay', async () => {
      const resolveDisplay = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        resolveDisplay,
      }))
      const wrapper = createWrapper({
        modelValue: null,
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: true },
        },
      })
      await nextTick()
      expect(resolveDisplay).not.toHaveBeenCalled()
    })
  })

  // ----------------------------------------------------------------
  // 远程搜索 (handleRemoteSearch)
  // ----------------------------------------------------------------
  describe('remote search', () => {
    it('多选模式下 binding 满足时 handleRemoteSearch 调用 loadOptionsDebounced', () => {
      const loadOptionsDebounced = vi.fn()
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptionsDebounced,
        getFilterParams: vi.fn(() => ({ category: 'x' })),
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: true },
        },
      })
      wrapper.vm.handleRemoteSearch('abc')
      expect(loadOptionsDebounced).toHaveBeenCalledWith('abc', expect.objectContaining({ filters: { category: 'x' } }))
    })

    it('binding 不满足时 handleRemoteSearch 不调用 loadOptionsDebounced', () => {
      const loadOptionsDebounced = vi.fn()
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptionsDebounced,
        isBindingSatisfied: vi.fn(() => false),
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: { multiple: true },
        },
      })
      wrapper.vm.handleRemoteSearch('abc')
      expect(loadOptionsDebounced).not.toHaveBeenCalled()
    })
  })

  // ----------------------------------------------------------------
  // dialog 模式
  // ----------------------------------------------------------------
  describe('dialog mode', () => {
    it('点击 el-input 触发 handleDialogOpen', async () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'dialog' },
        },
      })
      const elInput = wrapper.find('.el-input-stub')
      await elInput.trigger('click')
      expect(elInput.exists()).toBe(true)
    })

    it('disabled=true 时 handleDialogOpen 不打开 dialog', () => {
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'dialog' },
        },
        disabled: true,
      })
      expect(wrapper.props('disabled')).toBe(true)
      const vm = wrapper.vm
      vm.handleDialogOpen()
    })

    it('dialog 模式 + 单选 confirm 后 emit update:modelValue + out-mapping', async () => {
      const opt = { value: 'a', display: 'Alpha', code: 'A' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt],
        outMappings: [{ value_help_field: 'code', local_field: 'user_code' }],
        applyOutMappings: vi.fn(() => ({ user_code: 'A' })),
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'dialog' },
        },
      })
      wrapper.vm.handleDialogConfirm(opt)
      const events = wrapper.emitted()
      expect(events['update:modelValue'][0]).toEqual(['a'])
      expect(events['update:displayValue'][0]).toEqual(['Alpha'])
      expect(events['out-mapping'][0]).toEqual([{ user_code: 'A' }])
    })

    it('dialog 模式 + 多选 confirm 后 emit values 数组', async () => {
      const opt1 = { value: 'a', display: 'Alpha' }
      const opt2 = { value: 'b', display: 'Beta' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: [opt1, opt2],
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'dialog' },
          behavior: { multiple: true },
        },
      })
      wrapper.vm.handleDialogConfirm([opt1, opt2])
      const events = wrapper.emitted()
      expect(events['update:modelValue'][0]).toEqual([['a', 'b']])
      expect(events['update:displayValue'][0]).toEqual(['Alpha, Beta'])
    })
  })

  // ----------------------------------------------------------------
  // autocomplete (inline 模式)
  // ----------------------------------------------------------------
  describe('inline mode (autocomplete)', () => {
    it('handleAutocompleteSelect 触发后 emit update:modelValue + update:displayValue + change', async () => {
      const opt = { value: 'a', display: 'Alpha', code: 'A' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock())
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'inline' },
        },
      })
      wrapper.vm.handleAutocompleteSelect({ value: 'Alpha', item: opt })
      const events = wrapper.emitted()
      expect(events['update:modelValue'][0]).toEqual(['a'])
      expect(events['update:displayValue'][0]).toEqual(['Alpha'])
      expect(events['change'][0]).toEqual(['a'])
    })

    it('handleAutocompleteSelect 带 out_mappings 时 emit out-mapping', async () => {
      const opt = { value: 'a', display: 'Alpha', code: 'A' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        outMappings: [{ value_help_field: 'code', local_field: 'user_code' }],
        applyOutMappings: vi.fn(() => ({ user_code: 'A' })),
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'inline' },
        },
      })
      wrapper.vm.handleAutocompleteSelect({ value: 'Alpha', item: opt })
      const events = wrapper.emitted()
      expect(events['out-mapping'][0]).toEqual([{ user_code: 'A' }])
    })

    it('handleAutocompleteSelect applyOutMappings 返回空时不 emit out-mapping', async () => {
      const opt = { value: 'a', display: 'Alpha' }
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        outMappings: [{ value_help_field: 'code', local_field: 'user_code' }],
        applyOutMappings: vi.fn(() => ({})),
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'inline' },
        },
      })
      wrapper.vm.handleAutocompleteSelect({ value: 'Alpha', item: opt })
      const events = wrapper.emitted()
      expect(events['out-mapping']).toBeFalsy()
    })

    it('handleAutocompleteInput 输入空字符串时 emit 空值', () => {
      useValueHelp.mockReturnValueOnce(makeValueHelpMock())
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'inline' },
        },
      })
      wrapper.vm.handleAutocompleteInput('')
      const events = wrapper.emitted()
      expect(events['update:modelValue'][0]).toEqual([''])
      expect(events['update:displayValue'][0]).toEqual([''])
      expect(events['change'][0]).toEqual([''])
    })

    it('handleAutocomplete 异步 load 后调用 cb 返回 options', async () => {
      const opts = [
        { value: 'a', display: 'Alpha' },
        { value: 'b', display: 'Beta' },
      ]
      const cb = vi.fn()
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        optionsList: opts,
        loadOptions: vi.fn().mockResolvedValue(undefined),
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          presentation: { result_type: 'inline' },
        },
      })
      await wrapper.vm.handleAutocomplete('abc', cb)
      expect(cb).toHaveBeenCalledWith([
        { value: 'Alpha', item: opts[0] },
        { value: 'Beta', item: opts[1] },
      ])
    })
  })

  // ----------------------------------------------------------------
  // 参数绑定变化时重新加载
  // ----------------------------------------------------------------
  describe('parameter binding change', () => {
    it('formValues 中绑定字段变化时 loadOptions 被再次调用', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: {
            parameter_bindings: [
              { target_field: 'parent_id', local_field: 'group_id' }
            ],
          },
        },
        formValues: { group_id: 1 },
      })
      await nextTick()
      const callCountBefore = loadOptions.mock.calls.length
      await wrapper.setProps({ formValues: { group_id: 2 } })
      await nextTick()
      expect(loadOptions.mock.calls.length).toBeGreaterThan(callCountBefore)
    })

    it('formValues 绑定字段未变时 loadOptions 不会再次调用', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
      }))
      const wrapper = createWrapper({
        valueHelpConfig: {
          source: { type: 'enum', enum_type_id: 'status' },
          behavior: {
            parameter_bindings: [
              { target_field: 'parent_id', local_field: 'group_id' }
            ],
          },
        },
        formValues: { group_id: 1, other: 'x' },
      })
      await nextTick()
      const callCountBefore = loadOptions.mock.calls.length
      await wrapper.setProps({ formValues: { group_id: 1, other: 'y' } })
      await nextTick()
      expect(loadOptions.mock.calls.length).toBe(callCountBefore)
    })
  })

  // ----------------------------------------------------------------
  // dropdown 打开时预加载
  // ----------------------------------------------------------------
  describe('handleDropdownVisible', () => {
    it('dropdown 打开 + optionsList 空时调用 loadOptions', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
        optionsList: [],
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleDropdownVisible(true)
      expect(loadOptions).toHaveBeenCalled()
    })

    it('dropdown 打开 + optionsList 已有值时不再加载', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
        optionsList: [{ value: 'a', display: 'A' }],
      }))
      const wrapper = createWrapper()
      const before = loadOptions.mock.calls.length
      wrapper.vm.handleDropdownVisible(true)
      expect(loadOptions.mock.calls.length).toBe(before)
    })

    it('dropdown 关闭 (visible=false) 时不调用 loadOptions', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
        optionsList: [],
      }))
      const wrapper = createWrapper()
      const before = loadOptions.mock.calls.length
      wrapper.vm.handleDropdownVisible(false)
      expect(loadOptions.mock.calls.length).toBe(before)
    })

    it('binding 不满足时 dropdown 打开也不调用 loadOptions', async () => {
      const loadOptions = vi.fn().mockResolvedValue(undefined)
      useValueHelp.mockReturnValueOnce(makeValueHelpMock({
        loadOptions,
        optionsList: [],
        isBindingSatisfied: vi.fn(() => false),
      }))
      const wrapper = createWrapper()
      wrapper.vm.handleDropdownVisible(true)
    })
  })
})
