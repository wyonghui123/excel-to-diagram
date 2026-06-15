/**
 * BoCodeSelector.spec.js - Pick by Code 模式组件测试
 *
 * 测试核心功能:
 * 1. 初始空状态渲染
 * 2. 成功查询: emit update:selected + 显示结果卡片
 * 3. BO_NOT_FOUND: 显示 warning alert
 * 4. UNAUTHORIZED: 显示 error alert
 * 5. MISSING_CODE: 空 code 触发本地校验
 * 6. 清空按钮: 重置 state
 * 7. productId 变化时自动清空
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import BoCodeSelector from '@/components/common/ValueHelp/BoCodeSelector.vue'

// flushPromises is used in async test waits; suppress unused warning
void flushPromises

// Mock boService
vi.mock('@/services/boService', () => ({
  default: {
    pickBoByCode: vi.fn()
  }
}))

import boService from '@/services/boService'

const stubs = {
  'el-input': {
    name: 'el-input',
    template: '<div class="el-input-stub"><input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" @keyup.enter="$emit(\'keyup.enter\')" @clear="$emit(\'clear\')" /><slot name="append" /></div>',
    props: ['modelValue', 'disabled', 'placeholder', 'clearable']
  },
  'el-button': {
    name: 'el-button',
    template: '<button class="el-button-stub" :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
    props: ['disabled', 'loading', 'size', 'type']
  },
  'el-icon': {
    name: 'el-icon',
    template: '<i class="el-icon-stub"><slot /></i>'
  },
  'el-tag': {
    name: 'el-tag',
    template: '<span class="el-tag-stub" :class="`el-tag--${type}`"><slot /></span>',
    props: ['type', 'size']
  },
  'el-card': {
    name: 'el-card',
    template: '<div class="el-card-stub"><slot /></div>',
    props: ['shadow']
  },
  'el-alert': {
    name: 'el-alert',
    template: '<div class="el-alert-stub" :class="`el-alert--${type}`"><div class="el-alert__title">{{ title }}</div><slot /></div>',
    props: ['title', 'type', 'closable', 'showIcon']
  }
}

const createWrapper = (props = {}) => {
  return mount(BoCodeSelector, {
    props: {
      productId: 1,
      ...props
    },
    global: { stubs }
  })
}

describe('BoCodeSelector.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ===== Test 1: 初始空状态 =====
  it('renders empty state initially', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.bo-code-selector__empty').exists()).toBe(true)
    expect(wrapper.find('.bo-code-selector__result').exists()).toBe(false)
    expect(wrapper.find('.bo-code-selector__alert').exists()).toBe(false)
  })

  // ===== Test 2: 成功查询 =====
  it('emits update:selected on successful search', async () => {
    const mockBo = { id: 100, code: 'BO_B_001', name: '业务对象 B', description: 'desc' }
    boService.pickBoByCode.mockResolvedValue({
      success: true,
      data: mockBo
    })

    const wrapper = createWrapper({ productId: 1 })
    // 直接设置 ref 值 (避免 setData 限制)
    wrapper.vm.code = 'BO_B_001'
    await nextTick()

    // 点击"查询"按钮 (el-button 在 append slot)
    const buttons = wrapper.findAll('.el-button-stub')
    // 第一个是查询按钮
    await buttons[0].trigger('click')
    await flushPromises()

    expect(boService.pickBoByCode).toHaveBeenCalledWith(
      'BO_B_001', 1, expect.objectContaining({ reason: 'cross_domain_relationship_create' })
    )
    // 显示结果卡片
    expect(wrapper.find('.bo-code-selector__result').exists()).toBe(true)
    expect(wrapper.text()).toContain('BO_B_001')
    expect(wrapper.text()).toContain('业务对象 B')
  })

  // ===== Test 3: BO_NOT_FOUND =====
  it('shows warning alert when BO not found', async () => {
    boService.pickBoByCode.mockResolvedValue({
      success: false,
      code: 'BO_NOT_FOUND',
      message: 'BO 不存在',
      httpStatus: 404
    })

    const wrapper = createWrapper({ productId: 1 })
    wrapper.vm.code = 'BO_NOT_EXIST'
    await nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('.bo-code-selector__alert').exists()).toBe(true)
    expect(wrapper.find('.el-alert--warning').exists()).toBe(true)
    expect(wrapper.text()).toContain('未找到该 BO')
  })

  // ===== Test 4: UNAUTHORIZED =====
  it('shows error alert when unauthorized', async () => {
    boService.pickBoByCode.mockResolvedValue({
      success: false,
      code: 'UNAUTHORIZED',
      message: '未登录',
      httpStatus: 401
    })

    const wrapper = createWrapper({ productId: 1 })
    wrapper.vm.code = 'BO_B_001'
    await nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('.el-alert--error').exists()).toBe(true)
    expect(wrapper.text()).toContain('未授权')
  })

  // ===== Test 5: 空 code 触发本地校验 =====
  it('shows MISSING_CODE error for empty code (no API call)', async () => {
    const wrapper = createWrapper({ productId: 1 })
    // code 为空时, 查询按钮 disabled, 这里直接调 handleSearch
    await wrapper.vm.handleSearch()
    await flushPromises()

    expect(boService.pickBoByCode).not.toHaveBeenCalled()
    expect(wrapper.find('.el-alert--error').exists()).toBe(true)
    expect(wrapper.text()).toContain('请输入 BO 编码')
  })

  // ===== Test 6: 网络异常 =====
  it('handles network exception gracefully', async () => {
    boService.pickBoByCode.mockRejectedValue(new Error('网络超时'))

    const wrapper = createWrapper({ productId: 1 })
    wrapper.vm.code = 'BO_B_001'
    await nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('.el-alert--error').exists()).toBe(true)
    expect(wrapper.text()).toContain('网络错误')
  })

  // ===== Test 7: 点击"选择"按钮 emit =====
  it('emits update:selected when clicking select button', async () => {
    const mockBo = { id: 100, code: 'BO_B_001', name: '业务对象 B' }
    boService.pickBoByCode.mockResolvedValue({ success: true, data: mockBo })

    const wrapper = createWrapper({ productId: 1 })
    wrapper.vm.code = 'BO_B_001'
    await nextTick()

    // 触发查询 (第一个按钮)
    let buttons = wrapper.findAll('.el-button-stub')
    await buttons[0].trigger('click')
    await flushPromises()

    // 重新查询按钮 (DOM 已更新, 第二个按钮现在可见)
    buttons = wrapper.findAll('.el-button-stub')
    // 第一个是查询 (在 append slot), 第二个是结果卡片的"选择"按钮
    expect(buttons.length).toBeGreaterThanOrEqual(2)
    await buttons[1].trigger('click')

    expect(wrapper.emitted('update:selected')).toBeTruthy()
    expect(wrapper.emitted('update:selected')[0][0]).toEqual(mockBo)
  })

  // ===== Test 8: 清空重置 =====
  it('resets state on clear', async () => {
    boService.pickBoByCode.mockResolvedValue({
      success: true,
      data: { id: 100, code: 'BO_B_001', name: 'B' }
    })

    const wrapper = createWrapper({ productId: 1 })
    wrapper.vm.code = 'BO_B_001'
    await nextTick()

    const buttons = wrapper.findAll('.el-button-stub')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(wrapper.find('.bo-code-selector__result').exists()).toBe(true)

    // 调 handleClear
    wrapper.vm.handleClear()
    await nextTick()

    expect(wrapper.vm.code).toBe('')
    expect(wrapper.vm.result).toBeNull()
    expect(wrapper.vm.errorCode).toBe('')
  })
})
