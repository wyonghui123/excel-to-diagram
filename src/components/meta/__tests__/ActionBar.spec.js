/**
 * ActionBar.spec.js - T13-6 动作条
 *
 * 验证：enabled=false/pending → 按钮 disabled + tooltip reason；
 * 点击已启用按钮 emit 正确 payload；danger 动作走确认框。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElTooltip, ElMessageBox } from 'element-plus'

const { getAction } = vi.hoisted(() => ({ getAction: vi.fn() }))

vi.mock('@/composables/useBatchActions', () => {
  const useBatchActions = () => ({
    getAction,
    request: vi.fn(),
    clear: vi.fn(),
    results: new Map()
  })
  return { useBatchActions, default: useBatchActions }
})

import ActionBar from '@/components/meta/ActionBar.vue'

const ACTIONS = [
  { id: 'edit', label: '编辑', style: 'primary' },
  { id: 'delete', label: '删除', style: 'danger' },
  { id: 'view', label: '查看' }
]

function mockVerdicts(map = {}) {
  getAction.mockImplementation((id, action) => {
    const key = `${id}:${action.id || action.key}`
    return map[key] || { enabled: true, reason: '', required_permission: '' }
  })
}

function mountBar(props = {}) {
  return mount(ActionBar, {
    props: {
      objectType: 'demo',
      actions: ACTIONS,
      ids: [1, 2],
      ...props
    }
  })
}

describe('ActionBar（T13-6）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockVerdicts()
  })

  it('enabled=false → 按钮 disabled 且 tooltip 展示 reason 文案', () => {
    mockVerdicts({
      '1:edit': { enabled: false, reason: 'no_permission', required_permission: 'demo:edit' },
      '2:edit': { enabled: false, reason: 'no_permission', required_permission: 'demo:edit' }
    })
    const wrapper = mountBar()

    const buttons = wrapper.findAll('button')
    expect(buttons[0].attributes('disabled')).toBeDefined()
    expect(buttons[2].attributes('disabled')).toBeUndefined()

    const tooltips = wrapper.findAllComponents(ElTooltip)
    expect(tooltips[0].props('content')).toBe('无权限执行该动作')
    expect(tooltips[2].props('content')).toBe('')
  })

  it('pending → 全部按钮 disabled', () => {
    mockVerdicts({
      '1:edit': { enabled: false, reason: 'pending' },
      '2:edit': { enabled: false, reason: 'pending' },
      '1:delete': { enabled: false, reason: 'pending' },
      '2:delete': { enabled: false, reason: 'pending' },
      '1:view': { enabled: false, reason: 'pending' },
      '2:view': { enabled: false, reason: 'pending' }
    })
    const wrapper = mountBar()

    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(3)
    buttons.forEach(button => expect(button.attributes('disabled')).toBeDefined())
    expect(wrapper.findAllComponents(ElTooltip)[0].props('content')).toBe('正在校验动作可用性…')
  })

  it('点击已启用按钮 emit { action, ids }', async () => {
    const wrapper = mountBar()

    await wrapper.findAll('button')[2].trigger('click')

    expect(wrapper.emitted('action')).toEqual([[{ action: 'view', ids: [1, 2] }]])
  })

  it('disabled 按钮点击不 emit', async () => {
    mockVerdicts({
      '1:view': { enabled: false, reason: 'precondition_false' },
      '2:view': { enabled: false, reason: 'precondition_false' }
    })
    const wrapper = mountBar()

    await wrapper.findAll('button')[2].trigger('click')

    expect(wrapper.emitted('action')).toBeUndefined()
  })

  it('hideDisabled 只渲染可用动作', () => {
    mockVerdicts({
      '1:delete': { enabled: false, reason: 'no_permission' },
      '2:delete': { enabled: false, reason: 'no_permission' }
    })
    const wrapper = mountBar({ hideDisabled: true })

    const labels = wrapper.findAll('button').map(button => button.text())
    expect(labels).toEqual(['编辑', '查看'])
  })

  it('danger 动作确认后才 emit，取消则不 emit', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
    const wrapper = mountBar()

    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('action')).toEqual([[{ action: 'delete', ids: [1, 2] }]])

    confirm.mockRejectedValueOnce('cancel')
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.emitted('action')).toHaveLength(1)
  })

  it('动作样式映射到 el-button type', () => {
    const wrapper = mountBar()

    const buttons = wrapper.findAllComponents(ElButton)
    expect(buttons[0].props('type')).toBe('primary')
    expect(buttons[1].props('type')).toBe('danger')
    expect(buttons[2].props('type')).toBe('')
  })
})