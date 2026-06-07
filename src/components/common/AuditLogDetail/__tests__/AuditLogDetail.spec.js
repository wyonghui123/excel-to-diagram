/**
 * AuditLogDetail.spec.js - 审计日志详情组件测试
 *
 * M5: 前端扩展测试
 * 测试范围：
 * 1. 计算属性：actionClass, actionLabel, isCreateAction, isDeleteAction
 * 2. 计算属性：formattedTime, changes
 * 3. 空日志数据处理
 * 4. 事件发射
 * 5. Props 传递
 */

import { describe, it, expect, vi, beforeEach, afterEach, afterAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

// 修复子组件 useStore 报错 + 真实 fetch 触发
const _origFetch = globalThis.fetch
const _origResizeObserver = globalThis.ResizeObserver
const _origMatchMedia = globalThis.matchMedia

beforeEach(() => {
  setActivePinia(createPinia())
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ success: true, data: [], message: '' })
  })
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  if (!globalThis.matchMedia) {
    globalThis.matchMedia = vi.fn().mockImplementation((q) => ({
      matches: false, media: q, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  }
})

afterEach(() => { vi.clearAllMocks() })

afterAll(() => {
  globalThis.fetch = _origFetch
  globalThis.ResizeObserver = _origResizeObserver
  globalThis.matchMedia = _origMatchMedia
})

const mockElDrawer = {
  name: 'ElDrawer',
  template: '<div class="mock-el-drawer"><slot /></div>',
  props: ['modelValue', 'title', 'size', 'direction', 'destroyOnClose'],
  emits: ['update:modelValue', 'close'],
}

const globalStubs = {
  'el-drawer': mockElDrawer,
}

const createLog = (overrides = {}) => ({
  id: 1,
  action: 'UPDATE',
  user_name: 'admin',
  object_type: 'user',
  object_id: 123,
  created_at: '2024-01-15T10:30:00',
  field_name: 'email',
  old_value: 'old@test.com',
  new_value: 'new@test.com',
  ...overrides,
})

describe('AuditLogDetail', () => {
  const mountComponent = async (props = {}) => {
    const AuditLogDetail = (await import('../AuditLogDetail.vue')).default
    return mount(AuditLogDetail, {
      global: { stubs: globalStubs },
      props: {
        visible: true,
        log: createLog(),
        ...props,
      },
    })
  }

  describe('计算属性', () => {
    it('actionClass 应该返回小写操作名', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'CREATE' }) })
      expect(wrapper.vm.actionClass).toBe('create')
    })

    it('actionClass 无日志时返回 unknown', async () => {
      const wrapper = await mountComponent({ log: null })
      expect(wrapper.vm.actionClass).toBe('unknown')
    })

    it('actionLabel 应该正确映射操作名', async () => {
      const testCases = [
        { action: 'CREATE', expected: '创建' },
        { action: 'UPDATE', expected: '更新' },
        { action: 'DELETE', expected: '删除' },
        { action: 'ASSIGN', expected: '分配' },
        { action: 'REVOKE', expected: '撤销' },
      ]
      for (const { action, expected } of testCases) {
        const wrapper = await mountComponent({ log: createLog({ action }) })
        expect(wrapper.vm.actionLabel).toBe(expected)
      }
    })

    it('actionLabel 未知操作应返回 UNKNOWN', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'UNKNOWN' }) })
      expect(wrapper.vm.actionLabel).toBe('UNKNOWN')
    })

    it('isCreateAction 应该正确判断', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'CREATE' }) })
      expect(wrapper.vm.isCreateAction).toBe(true)
      expect(wrapper.vm.isDeleteAction).toBe(false)
    })

    it('isDeleteAction 应该正确判断', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'DELETE' }) })
      expect(wrapper.vm.isCreateAction).toBe(false)
      expect(wrapper.vm.isDeleteAction).toBe(true)
    })

    it('formattedTime 应该格式化时间', async () => {
      const wrapper = await mountComponent({ log: createLog({ created_at: '2024-01-15T10:30:00' }) })
      const time = wrapper.vm.formattedTime
      expect(time).toContain('2024')
    })

    it('formattedTime 空时间应返回 -', async () => {
      const wrapper = await mountComponent({ log: createLog({ created_at: null }) })
      expect(wrapper.vm.formattedTime).toBe('-')
    })

    it('changes 应该返回 changes 数组', async () => {
      const changes = [
        { field: 'email', field_label: '邮箱', old_value: 'old@test.com', new_value: 'new@test.com' },
      ]
      const wrapper = await mountComponent({ log: createLog({ changes }) })
      expect(wrapper.vm.changes).toEqual(changes)
    })

    it('changes 应该返回 field_changes 数组作为备选', async () => {
      const field_changes = [
        { field: 'name', old_value: 'old', new_value: 'new' },
      ]
      const wrapper = await mountComponent({ log: createLog({ field_changes }) })
      expect(wrapper.vm.changes).toEqual(field_changes)
    })

    it('changes 无变更数据应返回空数组', async () => {
      const wrapper = await mountComponent({ log: createLog({ changes: undefined, field_changes: undefined }) })
      expect(wrapper.vm.changes).toEqual([])
    })
  })

  describe('DOM 渲染', () => {
    it('空日志应显示无日志数据', async () => {
      const wrapper = await mountComponent({ log: null })
      expect(wrapper.find('.ald-empty').exists()).toBe(true)
      expect(wrapper.text()).toContain('无日志数据')
    })

    it('有日志时不应显示空状态', async () => {
      const wrapper = await mountComponent({ log: createLog() })
      expect(wrapper.find('.ald-empty').exists()).toBe(false)
      expect(wrapper.find('.ald-content').exists()).toBe(true)
    })

    it('应该显示操作标签', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'UPDATE' }) })
      expect(wrapper.find('.ald-action-badge').exists()).toBe(true)
      expect(wrapper.find('.ald-action-badge').text()).toBe('更新')
      expect(wrapper.find('.ald-action-badge').classes()).toContain('ald-action--update')
    })

    it('应该显示操作人', async () => {
      const wrapper = await mountComponent({ log: createLog({ user_name: '张三' }) })
      expect(wrapper.text()).toContain('操作人')
      expect(wrapper.text()).toContain('张三')
    })

    it('应该显示对象类型', async () => {
      const wrapper = await mountComponent({ log: createLog({ object_type: 'user' }) })
      expect(wrapper.text()).toContain('对象类型')
      expect(wrapper.text()).toContain('user')
    })

    it('应该显示对象ID', async () => {
      const wrapper = await mountComponent({ log: createLog({ object_id: 42 }) })
      expect(wrapper.text()).toContain('对象ID')
      expect(wrapper.text()).toContain('42')
    })

    it('CREATE 操作应显示创建摘要', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'CREATE' }) })
      expect(wrapper.find('.ald-summary').exists()).toBe(true)
      expect(wrapper.text()).toContain('创建记录')
    })

    it('DELETE 操作应显示删除摘要', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'DELETE' }) })
      expect(wrapper.find('.ald-summary--delete').exists()).toBe(true)
      expect(wrapper.text()).toContain('删除记录')
    })

    it('UPDATE 操作有 changes 时应显示变更表格', async () => {
      const log = createLog({
        action: 'UPDATE',
        changes: [
          { field: 'email', field_label: '邮箱', old_value: 'old@test.com', new_value: 'new@test.com' },
        ],
      })
      const wrapper = await mountComponent({ log })
      expect(wrapper.find('.ald-change-table').exists()).toBe(true)
      expect(wrapper.text()).toContain('变更字段')
      expect(wrapper.text()).toContain('邮箱')
    })

    it('UPDATE 操作无 changes 但有 field_name 时应显示单字段变更', async () => {
      const wrapper = await mountComponent({ log: createLog({ action: 'UPDATE' }) })
      expect(wrapper.find('.ald-single-change').exists()).toBe(true)
      expect(wrapper.text()).toContain('email')
    })

    it('空值应显示 (空)', async () => {
      const wrapper = await mountComponent({
        log: createLog({ action: 'UPDATE', old_value: null, new_value: null }),
      })
      expect(wrapper.text()).toContain('(空)')
    })
  })

  describe('事件', () => {
    it('关闭抽屉应触发 update:visible 事件', async () => {
      const wrapper = await mountComponent()
      wrapper.vm.handleClose()
      await nextTick()
      expect(wrapper.emitted('update:visible')).toBeTruthy()
      expect(wrapper.emitted('update:visible')[0]).toEqual([false])
    })
  })

  describe('Props', () => {
    it('visible 应该正确传递给 el-drawer', async () => {
      const wrapper = await mountComponent({ visible: true })
      const drawer = wrapper.findComponent({ name: 'ElDrawer' })
      expect(drawer.props('modelValue')).toBe(true)
    })

    it('visible=false 时抽屉应关闭', async () => {
      const wrapper = await mountComponent({ visible: false })
      const drawer = wrapper.findComponent({ name: 'ElDrawer' })
      expect(drawer.props('modelValue')).toBe(false)
    })
  })
})
