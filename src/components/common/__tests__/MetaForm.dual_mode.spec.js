/**
 * MetaForm.dual_mode.spec.js - 元数据驱动的 dual_mode 行为测试
 *
 * 测试核心功能:
 * 1. dual_mode: true → 渲染 BoSelectorDualMode
 * 2. dual_mode: false 或缺省 → 渲染 ValueHelpField (原行为)
 * 3. cross-domain-toggled 事件正确转发
 *
 * 背景: V1.2.0 跨域关系改造
 * 任何 FK 字段在 YAML 中加 dual_mode: true 即可启用双模式 ValueHelp,
 * 无需为单个对象类型写自定义表单.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import MetaForm from '@/components/common/MetaForm.vue'

// Mock 子组件, 检查哪个被渲染
const BoSelectorDualModeStub = {
  name: 'BoSelectorDualMode',
  template: '<div class="bo-selector-dual-mode-stub" :data-product-id="productId" :data-required="required" :data-label="label" :data-disabled="disabled" />',
  props: ['modelValue', 'productId', 'label', 'required', 'allowCrossDomain', 'disabled'],
  emits: ['update:modelValue', 'cross-domain-toggled', 'code-error']
}

const ValueHelpFieldStub = {
  name: 'ValueHelpField',
  template: '<div class="value-help-field-stub" />',
  props: ['modelValue', 'valueHelpConfig', 'disabled', 'placeholder', 'formValues'],
  emits: ['update:modelValue', 'update:displayValue', 'change']
}

const createWrapper = (props = {}, opts = {}) => {
  return mount(MetaForm, {
    props,
    global: {
      stubs: {
        BoSelectorDualMode: BoSelectorDualModeStub,
        ValueHelpField: ValueHelpFieldStub,
        AppSelect: { name: 'AppSelect', template: '<div class="app-select-stub" />' }
      }
    },
    ...opts
  })
}

describe('MetaForm.vue - dual_mode 元数据驱动', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ===== Test 1: dual_mode: true → 渲染 BoSelectorDualMode =====
  it('renders BoSelectorDualMode when value_help.dual_mode is true', () => {
    const fields = [
      {
        key: 'source_bo_id',
        label: '源业务对象',
        type: 'value_help',
        required: true,
        valueHelp: {
          source: { type: 'bo', target_bo: 'business_object' },
          presentation: { result_type: 'dropdown' },
          dual_mode: true  // [V1.2.0] 元数据驱动开关
        }
      }
    ]
    const wrapper = createWrapper({ fields })

    expect(wrapper.find('.bo-selector-dual-mode-stub').exists()).toBe(true)
    expect(wrapper.find('.value-help-field-stub').exists()).toBe(false)
  })

  // ===== Test 2: 缺省/dual_mode: false → 渲染 ValueHelpField =====
  it('renders ValueHelpField when dual_mode is false or missing', () => {
    const fields = [
      {
        key: 'source_bo_id',
        label: '源业务对象',
        type: 'value_help',
        required: true,
        valueHelp: {
          source: { type: 'bo', target_bo: 'business_object' },
          presentation: { result_type: 'dropdown' }
          // dual_mode 缺省
        }
      }
    ]
    const wrapper = createWrapper({ fields })

    expect(wrapper.find('.value-help-field-stub').exists()).toBe(true)
    expect(wrapper.find('.bo-selector-dual-mode-stub').exists()).toBe(false)
  })

  // ===== Test 3: ui.dual_mode 路径也支持 (ui.relation 派生 value_help 的场景) =====
  it('recognizes dual_mode when nested inside valueHelp', () => {
    const fields = [
      {
        key: 'source_bo_id',
        label: '源业务对象',
        type: 'value_help',
        valueHelp: {
          source: { type: 'bo', target_bo: 'business_object' },
          // DetailPage 把 ui.dual_mode 合并进 valueHelp 后的最终形态
          dual_mode: true
        }
      }
    ]
    const wrapper = createWrapper({ fields })

    expect(wrapper.find('.bo-selector-dual-mode-stub').exists()).toBe(true)
  })

  // ===== Test 4: cross-domain-toggled 事件转发 =====
  it('forwards cross-domain-toggled event from BoSelectorDualMode', async () => {
    const fields = [
      {
        key: 'source_bo_id',
        label: '源业务对象',
        type: 'value_help',
        valueHelp: { source: {}, dual_mode: true }
      }
    ]
    const wrapper = createWrapper({ fields })

    const dualModeStub = wrapper.findComponent(BoSelectorDualModeStub)
    dualModeStub.vm.$emit('cross-domain-toggled', true)
    await nextTick()

    expect(wrapper.emitted('cross-domain-toggled')).toBeTruthy()
    const payload = wrapper.emitted('cross-domain-toggled')[0][0]
    expect(payload.fieldKey).toBe('source_bo_id')
    expect(payload.enabled).toBe(true)
    expect(payload.ts).toBeDefined()
  })

  // ===== Test 5: code-error 事件转发 =====
  it('forwards code-error event from BoSelectorDualMode', async () => {
    const fields = [
      {
        key: 'target_bo_id',
        label: '目标业务对象',
        type: 'value_help',
        valueHelp: { source: {}, dual_mode: true }
      }
    ]
    const wrapper = createWrapper({ fields })

    const dualModeStub = wrapper.findComponent(BoSelectorDualModeStub)
    dualModeStub.vm.$emit('code-error', 'BO_NOT_FOUND')
    await nextTick()

    expect(wrapper.emitted('code-error')).toBeTruthy()
    const payload = wrapper.emitted('code-error')[0][0]
    expect(payload.fieldKey).toBe('target_bo_id')
    expect(payload.code).toBe('BO_NOT_FOUND')
  })
})
