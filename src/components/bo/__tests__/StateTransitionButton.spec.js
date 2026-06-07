/**
 * StateTransitionButton.spec.js - 状态转换按钮组件测试
 *
 * 测试核心功能：
 * 1. availableTransitions 计算属性 - 按 from_states 过滤
 * 2. handleTransition - requireConfirm 时弹出确认对话框
 * 3. executeTransition - 调用 boService
 * 4. 成功/失败时的消息和事件
 * 5. disabled/loading 状态
 * 6. 空规则列表时的渲染
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import StateTransitionButton from '@/components/bo/StateTransitionButton.vue'

vi.mock('@/services/boService', () => ({
  default: {
    executeAction: vi.fn(),
    update: vi.fn(),
  }
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@element-plus/icons-vue', () => ({
  ArrowDown: { name: 'ArrowDown', render: () => null },
}))

import boService from '@/services/boService'
import { ElMessage } from 'element-plus'

const createWrapper = (props = {}) => {
  return mount(StateTransitionButton, {
    props: {
      objectType: 'order',
      objectId: 1,
      currentState: 'draft',
      ...props,
    },
    global: {
      stubs: {
        'el-button': {
          template: '<button :disabled="disabled" :class="{ loading }" @click="$emit(\'click\')"><slot /></button>',
          props: ['disabled', 'loading', 'type', 'size'],
        },
        'el-dropdown': {
          template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>',
          props: ['trigger', 'disabled'],
          emits: ['command'],
        },
        'el-dropdown-menu': { template: '<div class="el-dropdown-menu"><slot /></div>' },
        'el-dropdown-item': {
          template: '<div class="el-dropdown-item" @click="$emit(\'command\')"><slot /></div>',
          props: ['command', 'disabled', 'divided'],
          emits: ['command'],
        },
        'el-dialog': {
          template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
          props: ['modelValue', 'title', 'width'],
        },
        'el-icon': { template: '<i class="el-icon"><slot /></i>' },
      },
    },
  })
}

describe('StateTransitionButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('availableTransitions', () => {
    it('returns empty when no rules', () => {
      const wrapper = createWrapper({ rules: [] })
      expect(wrapper.vm.availableTransitions).toEqual([])
    })

    it('filters by state_transition type', () => {
      const wrapper = createWrapper({
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', to_state: 'approved' },
          { id: 'r2', type: 'validation', name: 'validate' },
        ],
      })
      expect(wrapper.vm.availableTransitions).toHaveLength(1)
      expect(wrapper.vm.availableTransitions[0].name).toBe('approve')
    })

    it('filters by from_states matching currentState', () => {
      const wrapper = createWrapper({
        currentState: 'draft',
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', from_states: ['draft'], to_state: 'approved' },
          { id: 'r2', type: 'state_transition', name: 'close', from_states: ['approved'], to_state: 'closed' },
        ],
      })
      expect(wrapper.vm.availableTransitions).toHaveLength(1)
      expect(wrapper.vm.availableTransitions[0].name).toBe('approve')
    })

    it('includes rules without from_states', () => {
      const wrapper = createWrapper({
        currentState: 'draft',
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', from_states: ['draft'], to_state: 'approved' },
          { id: 'r2', type: 'state_transition', name: 'cancel', to_state: 'cancelled' },
        ],
      })
      expect(wrapper.vm.availableTransitions).toHaveLength(2)
    })

    it('maps rule properties to transition object', () => {
      const wrapper = createWrapper({
        rules: [
          {
            id: 'r1',
            type: 'state_transition',
            name: 'approve',
            label: '审批通过',
            to_state: 'approved',
            icon: 'check',
            require_confirm: false,
            confirm_message: '确认审批？',
            action: 'approve_action',
          },
        ],
      })
      const transition = wrapper.vm.availableTransitions[0]
      expect(transition.id).toBe('r1')
      expect(transition.name).toBe('approve')
      expect(transition.label).toBe('审批通过')
      expect(transition.toState).toBe('approved')
      expect(transition.icon).toBe('check')
      expect(transition.requireConfirm).toBe(false)
      expect(transition.confirmMessage).toBe('确认审批？')
      expect(transition.action).toBe('approve_action')
    })

    it('defaults requireConfirm to true', () => {
      const wrapper = createWrapper({
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', to_state: 'approved' },
        ],
      })
      expect(wrapper.vm.availableTransitions[0].requireConfirm).toBe(true)
    })
  })

  describe('handleTransition', () => {
    it('shows confirm dialog when requireConfirm is true', async () => {
      const wrapper = createWrapper({
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', to_state: 'approved' },
        ],
      })

      const transition = wrapper.vm.availableTransitions[0]
      wrapper.vm.handleTransition(transition)

      expect(wrapper.vm.confirmDialogVisible).toBe(true)
      expect(wrapper.vm.pendingTransition).toEqual(transition)
    })

    it('executes directly when requireConfirm is false', async () => {
      boService.update.mockResolvedValue({ success: true })

      const wrapper = createWrapper({
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', to_state: 'approved', require_confirm: false },
        ],
      })

      const transition = wrapper.vm.availableTransitions[0]
      await wrapper.vm.handleTransition(transition)

      expect(boService.update).toHaveBeenCalled()
    })

    it('skips disabled transition', async () => {
      const wrapper = createWrapper({
        rules: [
          { id: 'r1', type: 'state_transition', name: 'approve', to_state: 'approved', disabled: true },
        ],
      })

      const transition = wrapper.vm.availableTransitions[0]
      wrapper.vm.handleTransition(transition)

      expect(wrapper.vm.confirmDialogVisible).toBe(false)
      expect(boService.update).not.toHaveBeenCalled()
    })
  })

  describe('executeTransition', () => {
    it('calls executeAction when action is defined', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        action: 'approve_action',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)

      expect(boService.executeAction).toHaveBeenCalledWith(
        'order', 1, 'approve_action',
        { status: 'approved' }
      )
    })

    it('calls update when no action defined', async () => {
      boService.update.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)

      expect(boService.update).toHaveBeenCalledWith(
        'order', 1,
        { status: 'approved' }
      )
    })

    it('emits success on successful transition', async () => {
      boService.update.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)

      expect(wrapper.emitted('success')).toBeTruthy()
      expect(wrapper.emitted('transition')).toBeTruthy()
      expect(ElMessage.success).toHaveBeenCalledWith('审批 成功')
    })

    it('emits error on failed transition', async () => {
      boService.update.mockResolvedValue({ success: false, message: 'Cannot transition' })

      const wrapper = createWrapper()
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)

      expect(wrapper.emitted('error')).toBeTruthy()
      expect(ElMessage.error).toHaveBeenCalledWith('Cannot transition')
    })

    it('handles exception', async () => {
      boService.update.mockRejectedValue(new Error('Network error'))

      const wrapper = createWrapper()
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)

      expect(wrapper.emitted('error')).toBeTruthy()
      expect(ElMessage.error).toHaveBeenCalled()
    })

    it('resets loading state after execution', async () => {
      boService.update.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)
      expect(wrapper.vm.loading).toBe(false)
    })

    it('uses custom stateField', async () => {
      boService.update.mockResolvedValue({ success: true })

      const wrapper = createWrapper({ stateField: 'state' })
      const transition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        action: 'approve_action',
        requireConfirm: false,
      }

      await wrapper.vm.executeTransition(transition)

      expect(boService.executeAction).toHaveBeenCalledWith(
        'order', 1, 'approve_action',
        { state: 'approved' }
      )
    })
  })

  describe('confirmTransition', () => {
    it('executes pending transition', async () => {
      boService.update.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      wrapper.vm.pendingTransition = {
        name: 'approve',
        label: '审批',
        toState: 'approved',
        requireConfirm: true,
      }

      await wrapper.vm.confirmTransition()

      expect(boService.update).toHaveBeenCalled()
      expect(wrapper.vm.confirmDialogVisible).toBe(false)
    })

    it('does nothing when no pending transition', async () => {
      const wrapper = createWrapper()
      wrapper.vm.pendingTransition = null

      await wrapper.vm.confirmTransition()

      expect(boService.update).not.toHaveBeenCalled()
    })
  })

  describe('confirmTitle and confirmMessage', () => {
    it('uses transition label as confirm title', () => {
      const wrapper = createWrapper()
      wrapper.vm.pendingTransition = { label: '审批通过', confirmMessage: '确认审批？' }

      expect(wrapper.vm.confirmTitle).toBe('审批通过')
      expect(wrapper.vm.confirmMessage).toBe('确认审批？')
    })

    it('uses defaults when no pending transition', () => {
      const wrapper = createWrapper()
      wrapper.vm.pendingTransition = null

      expect(wrapper.vm.confirmTitle).toBe('确认操作')
      expect(wrapper.vm.confirmMessage).toBe('确定要执行此操作吗？')
    })
  })
})
