/**
 * BoSelectorDualMode.spec.js - 双模式 ValueHelp 顶层组件测试
 *
 * 测试核心功能:
 * 1. 未选时显示触发按钮
 * 2. 已选时显示 BO 信息卡
 * 3. 打开弹窗: 显示两个 Tab (List / By Code)
 * 4. 通过 By Code 模式选中后自动关闭弹窗 + emit
 * 5. 通过 List 模式选中后自动关闭弹窗 + emit
 * 6. modelValue 变化时同步 selectedBo
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import BoSelectorDualMode from '@/components/common/ValueHelp/BoSelectorDualMode.vue'

// Mock 子组件
const BoListSelectorStub = {
  name: 'BoListSelector',
  template: '<div class="bo-list-selector-stub" />',
  props: ['productId', 'modelValue', 'allowCrossDomain', 'disabled'],
  emits: ['update:selected', 'cross-domain-toggled']
}

const BoCodeSelectorStub = {
  name: 'BoCodeSelector',
  template: '<div class="bo-code-selector-stub" />',
  props: ['productId', 'disabled'],
  emits: ['update:selected', 'error']
}

const createWrapper = (props = {}) => {
  return mount(BoSelectorDualMode, {
    props: {
      productId: 1,
      ...props
    },
    global: {
      stubs: {
        BoListSelector: BoListSelectorStub,
        BoCodeSelector: BoCodeSelectorStub,
        'el-button': {
          name: 'el-button',
          template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>',
          props: ['disabled', 'type', 'plain', 'text', 'size']
        },
        'el-icon': {
          name: 'el-icon',
          template: '<i class="el-icon-stub"><slot /></i>'
        },
        'el-tag': {
          name: 'el-tag',
          template: '<span class="el-tag-stub"><slot /></span>',
          props: ['type', 'size']
        },
        'el-card': {
          name: 'el-card',
          template: '<div class="el-card-stub"><slot /></div>',
          props: ['shadow']
        },
        'el-dialog': {
          name: 'el-dialog',
          template: '<div v-if="modelValue" class="el-dialog-stub"><slot /></div>',
          props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
          emits: ['update:modelValue']
        },
        'el-tabs': {
          name: 'el-tabs',
          template: '<div class="el-tabs-stub"><slot /></div>',
          props: ['modelValue']
        },
        'el-tab-pane': {
          name: 'el-tab-pane',
          template: '<div class="el-tab-pane-stub"><slot /></div>',
          props: ['label', 'name']
        }
      }
    }
  })
}

describe('BoSelectorDualMode.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ===== Test 1: 未选时显示触发按钮 =====
  it('renders trigger button when no BO selected', () => {
    const wrapper = createWrapper()
    const buttons = wrapper.findAll('.el-button-stub')
    expect(buttons.length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('选择 BO')
  })

  // ===== Test 2: 已选时显示 BO 信息卡 =====
  it('renders selected BO card when modelValue is set', () => {
    const bo = { id: 100, code: 'BO_A_001', name: '业务对象 A' }
    const wrapper = createWrapper({ modelValue: bo })
    expect(wrapper.find('.bo-selector-dual-mode__selected').exists()).toBe(true)
    expect(wrapper.text()).toContain('BO_A_001')
    expect(wrapper.text()).toContain('业务对象 A')
  })

  // ===== Test 3: 打开弹窗 =====
  it('opens dialog with two tabs (List / By Code)', async () => {
    const wrapper = createWrapper()

    // 初始弹窗不显示
    expect(wrapper.find('.el-dialog-stub').exists()).toBe(false)

    // 调 openDialog
    wrapper.vm.openDialog()
    await nextTick()

    // 弹窗显示
    expect(wrapper.vm.dialogVisible).toBe(true)

    // 两个 Tab
    const tabPanes = wrapper.findAll('.el-tab-pane-stub')
    expect(tabPanes.length).toBe(2)

    // 子组件都被渲染
    expect(wrapper.findComponent(BoListSelectorStub).exists()).toBe(true)
    expect(wrapper.findComponent(BoCodeSelectorStub).exists()).toBe(true)
  })

  // ===== Test 4: 通过 By Code 模式选中 emit =====
  it('emits update:modelValue when Code mode selects', async () => {
    const wrapper = createWrapper()
    wrapper.vm.openDialog()
    await nextTick()

    // 模拟 Code 模式 emit
    const bo = { id: 200, code: 'BO_B_002', name: '业务对象 B' }
    const codeSelector = wrapper.findComponent(BoCodeSelectorStub)
    codeSelector.vm.$emit('update:selected', bo)
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(bo)
    expect(wrapper.emitted('change')).toBeTruthy()
    // 选中后自动关闭
    expect(wrapper.vm.dialogVisible).toBe(false)
  })

  // ===== Test 5: 通过 List 模式选中 emit =====
  it('emits update:modelValue when List mode selects', async () => {
    const wrapper = createWrapper()
    wrapper.vm.openDialog()
    await nextTick()

    const bo = { id: 300, code: 'BO_C_003', name: '业务对象 C' }
    const listSelector = wrapper.findComponent(BoListSelectorStub)
    listSelector.vm.$emit('update:selected', bo)
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0][0]).toEqual(bo)
    expect(wrapper.vm.dialogVisible).toBe(false)
  })

  // ===== Test 6: 跨域 toggle 转发 =====
  it('forwards cross-domain-toggled event from List mode', async () => {
    const wrapper = createWrapper()
    wrapper.vm.openDialog()
    await nextTick()

    const listSelector = wrapper.findComponent(BoListSelectorStub)
    listSelector.vm.$emit('cross-domain-toggled', true)
    await nextTick()

    expect(wrapper.emitted('cross-domain-toggled')).toBeTruthy()
    expect(wrapper.emitted('cross-domain-toggled')[0][0]).toBe(true)
  })

  // ===== Test 7: Code 模式错误转发 =====
  it('forwards code-error event from Code mode', async () => {
    const wrapper = createWrapper()
    wrapper.vm.openDialog()
    await nextTick()

    const codeSelector = wrapper.findComponent(BoCodeSelectorStub)
    codeSelector.vm.$emit('error', 'BO_NOT_FOUND')
    await nextTick()

    expect(wrapper.emitted('code-error')).toBeTruthy()
    expect(wrapper.emitted('code-error')[0][0]).toBe('BO_NOT_FOUND')
  })

  // ===== Test 8: modelValue 同步 =====
  it('syncs selectedBo when modelValue changes', async () => {
    const wrapper = createWrapper()
    expect(wrapper.vm.selectedBo).toBeNull()

    const bo = { id: 100, code: 'BO_A_001', name: 'A' }
    await wrapper.setProps({ modelValue: bo })
    expect(wrapper.vm.selectedBo).toEqual(bo)
  })
})
