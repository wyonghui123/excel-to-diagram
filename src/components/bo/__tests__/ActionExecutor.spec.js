/**
 * ActionExecutor.spec.js - 动作执行器组件测试
 *
 * 测试核心功能：
 * 1. groupedActions 计算属性 - 按 category 分组
 * 2. handleAction - 有 params 时弹出参数对话框
 * 3. executeWithParams - 表单验证后执行
 * 4. executeAction - 调用 boService.executeAction
 * 5. isActionDisabled - condition 表达式求值
 * 6. 成功/失败事件
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ActionExecutor from '@/components/bo/ActionExecutor.vue'

vi.mock('@/services/boService', () => ({
  default: {
    executeAction: vi.fn(),
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
  return mount(ActionExecutor, {
    props: {
      objectType: 'order',
      objectId: 1,
      ...props,
    },
    global: {
      stubs: {
        'el-button': {
          template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
          props: ['disabled', 'loading', 'type', 'size'],
        },
        'el-dropdown': {
          template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>',
          props: ['trigger', 'disabled'],
        },
        'el-dropdown-menu': { template: '<div class="el-dropdown-menu"><slot /></div>' },
        'el-dropdown-item': {
          template: '<div class="el-dropdown-item"><slot /></div>',
          props: ['command', 'disabled', 'divided'],
        },
        'el-dialog': {
          template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
          props: ['modelValue', 'title', 'width'],
        },
        'el-form': { template: '<form class="el-form"><slot /></form>' },
        'el-form-item': { template: '<div class="el-form-item"><slot /></div>' },
        'el-input': { template: '<input />', props: ['modelValue'] },
        'el-input-number': { template: '<input type="number" />', props: ['modelValue', 'min', 'max', 'step'] },
        'el-select': { template: '<select><slot /></select>', props: ['modelValue'] },
        'el-option': { template: '<option><slot /></option>' },
        'el-switch': { template: '<input type="checkbox" />', props: ['modelValue'] },
        'el-date-picker': { template: '<input type="date" />', props: ['modelValue'] },
        'el-result': { template: '<div class="el-result"><slot /></div>', props: ['icon', 'title', 'subTitle'] },
        'el-icon': { template: '<i class="el-icon"><slot /></i>' },
      },
    },
  })
}

describe('ActionExecutor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('groupedActions', () => {
    it('groups actions by category', () => {
      const wrapper = createWrapper({
        actions: [
          { id: 'a1', name: 'approve', category: 'workflow' },
          { id: 'a2', name: 'reject', category: 'workflow' },
          { id: 'a3', name: 'export', category: 'data' },
        ],
      })

      const groups = wrapper.vm.groupedActions
      expect(groups).toHaveLength(2)
      expect(groups[0].category).toBe('workflow')
      expect(groups[0].actions).toHaveLength(2)
      expect(groups[1].category).toBe('data')
      expect(groups[1].actions).toHaveLength(1)
    })

    it('groups actions without category', () => {
      const wrapper = createWrapper({
        actions: [
          { id: 'a1', name: 'approve' },
          { id: 'a2', name: 'reject' },
        ],
      })

      const groups = wrapper.vm.groupedActions
      expect(groups).toHaveLength(1)
      expect(groups[0].category).toBe('')
      expect(groups[0].actions).toHaveLength(2)
    })

    it('returns empty when no actions', () => {
      const wrapper = createWrapper({ actions: [] })
      expect(wrapper.vm.groupedActions).toEqual([])
    })
  })

  describe('isActionDisabled', () => {
    it('returns true for disabled action', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.isActionDisabled({ disabled: true })).toBe(true)
    })

    it('evaluates condition expression', () => {
      const wrapper = createWrapper({
        record: { status: 'draft', amount: 100 },
      })
      expect(wrapper.vm.isActionDisabled({ condition: 'record.status === "draft"' })).toBe(false)
      expect(wrapper.vm.isActionDisabled({ condition: 'record.status === "approved"' })).toBe(true)
    })

    it('returns false on condition error', () => {
      const wrapper = createWrapper({ record: {} })
      // 使用 forbidden 路径触发 evaluateCondition 抛错（被 catch 后返回 true → 不禁用）
      // 注：safeExpression 是 fail-open 设计，解析错误时返回 true（visible）
      expect(wrapper.vm.isActionDisabled({ condition: '__proto__' })).toBe(false)
    })

    it('returns false for action without condition', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.isActionDisabled({})).toBe(false)
    })
  })

  describe('handleAction', () => {
    it('opens param dialog when action has params', async () => {
      const wrapper = createWrapper()
      const action = {
        id: 'a1',
        name: 'approve',
        params: [
          { name: 'comment', label: '备注', type: 'text', required: true },
        ],
      }

      wrapper.vm.handleAction(action)

      expect(wrapper.vm.paramDialogVisible).toBe(true)
      expect(wrapper.vm.currentAction).toEqual(action)
      expect(wrapper.vm.paramForm.comment).toBeNull()
    })

    it('opens confirm dialog when requireConfirm is true', async () => {
      const wrapper = createWrapper()
      const action = {
        id: 'a1',
        name: 'delete',
        requireConfirm: true,
        confirmTitle: '确认删除',
        confirmMessage: '确定要删除吗？',
      }

      wrapper.vm.handleAction(action)

      expect(wrapper.vm.confirmDialogVisible).toBe(true)
      expect(wrapper.vm.pendingAction).toEqual(action)
    })

    it('executes directly when no params and no confirm', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'refresh' }

      wrapper.vm.handleAction(action)

      expect(boService.executeAction).toHaveBeenCalled()
    })

    it('skips disabled action', async () => {
      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', disabled: true }

      wrapper.vm.handleAction(action)

      expect(boService.executeAction).not.toHaveBeenCalled()
    })

    it('initializes param form with defaults', async () => {
      const wrapper = createWrapper()
      const action = {
        id: 'a1',
        name: 'approve',
        params: [
          { name: 'priority', type: 'number', default: 5 },
          { name: 'comment', type: 'text' },
        ],
      }

      wrapper.vm.handleAction(action)

      expect(wrapper.vm.paramForm.priority).toBe(5)
      expect(wrapper.vm.paramForm.comment).toBeNull()
    })
  })

  describe('executeAction', () => {
    it('calls boService.executeAction with correct params', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批' }
      await wrapper.vm.executeAction(action, { comment: 'ok' })

      expect(boService.executeAction).toHaveBeenCalledWith('order', 1, 'approve', { comment: 'ok' })
    })

    it('emits success on successful execution', async () => {
      boService.executeAction.mockResolvedValue({ success: true, message: 'Done' })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批' }
      await wrapper.vm.executeAction(action, {})

      expect(wrapper.emitted('success')).toBeTruthy()
      expect(wrapper.emitted('execute')).toBeTruthy()
    })

    it('emits error on failed execution', async () => {
      boService.executeAction.mockResolvedValue({ success: false, message: 'Failed' })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批' }
      await wrapper.vm.executeAction(action, {})

      expect(wrapper.emitted('error')).toBeTruthy()
      expect(wrapper.emitted('execute')).toBeTruthy()
    })

    it('handles exception', async () => {
      boService.executeAction.mockRejectedValue(new Error('Network error'))

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批' }
      await wrapper.vm.executeAction(action, {})

      expect(wrapper.emitted('error')).toBeTruthy()
      expect(wrapper.vm.lastResult.success).toBe(false)
    })

    it('resets loading and current action after execution', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批' }
      await wrapper.vm.executeAction(action, {})

      expect(wrapper.vm.loading).toBe(false)
      expect(wrapper.vm.currentAction).toBeNull()
      expect(wrapper.vm.pendingAction).toBeNull()
    })

    it('shows result dialog on success when showResult is not false', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批' }
      await wrapper.vm.executeAction(action, {})

      expect(wrapper.vm.resultDialogVisible).toBe(true)
    })

    it('shows message instead of dialog when showResult is false', async () => {
      boService.executeAction.mockResolvedValue({ success: true, message: 'OK' })

      const wrapper = createWrapper()
      const action = { id: 'a1', name: 'approve', label: '审批', showResult: false }
      await wrapper.vm.executeAction(action, {})

      expect(wrapper.vm.resultDialogVisible).toBe(false)
      expect(ElMessage.success).toHaveBeenCalledWith('OK')
    })

    it('uses action id when name is not defined', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      const action = { id: 'approve_action' }
      await wrapper.vm.executeAction(action, {})

      expect(boService.executeAction).toHaveBeenCalledWith('order', 1, 'approve_action', {})
    })
  })

  describe('confirmExecute', () => {
    it('executes pending action', async () => {
      boService.executeAction.mockResolvedValue({ success: true })

      const wrapper = createWrapper()
      wrapper.vm.pendingAction = { id: 'a1', name: 'delete', label: '删除' }

      await wrapper.vm.confirmExecute()

      expect(boService.executeAction).toHaveBeenCalled()
      expect(wrapper.vm.confirmDialogVisible).toBe(false)
    })
  })

  describe('getButtonType', () => {
    it('returns action buttonType when defined', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.getButtonType({ buttonType: 'danger' })).toBe('danger')
    })

    it('returns action type when buttonType is not defined', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.getButtonType({ type: 'warning' })).toBe('warning')
    })

    it('returns primary as default', () => {
      const wrapper = createWrapper()
      expect(wrapper.vm.getButtonType({})).toBe('primary')
    })
  })

  describe('resultTitle', () => {
    it('returns success title on success', () => {
      const wrapper = createWrapper()
      wrapper.vm.lastResult = { success: true }
      expect(wrapper.vm.resultTitle).toBe('操作成功')
    })

    it('returns failure title on failure', () => {
      const wrapper = createWrapper()
      wrapper.vm.lastResult = { success: false }
      expect(wrapper.vm.resultTitle).toBe('操作失败')
    })
  })
})
