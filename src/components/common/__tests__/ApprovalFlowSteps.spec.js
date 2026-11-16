import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ApprovalFlowSteps from '../ApprovalFlowSteps.vue'

const STEPS = [
  { step_no: 1, approverLabel: 'procurement_manager', approveMode: 'any', slaHours: 24, state: 'done', actor: 'u-a', occurredAt: '2026-11-10 09:00' },
  { step_no: 2, approverLabel: '', approveMode: 'all', slaHours: null, state: 'active', actor: '', occurredAt: '' },
  { step_no: 3, approverLabel: 'gm', approveMode: 'custom_mode', slaHours: null, state: 'pending', actor: '', occurredAt: '' }
]

function mountSteps(props = {}) {
  return mount(ApprovalFlowSteps, {
    props,
    global: {
      stubs: {
        'el-tag': { name: 'el-tag', template: '<span class="tag-stub"><slot /></span>' }
      }
    }
  })
}

describe('ApprovalFlowSteps', () => {
  it('三种 state 渲染对应中文标签与步骤序号', () => {
    const w = mountSteps({ steps: STEPS })
    const items = w.findAll('[data-test="flow-step"]')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toContain('已完成')
    expect(items[1].text()).toContain('进行中')
    expect(items[2].text()).toContain('待处理')
    expect(w.findAll('[data-test="flow-step-no"]').map(n => n.text())).toEqual(['第 1 步', '第 2 步', '第 3 步'])
    expect(items[0].classes()).toContain('afs-step--done')
    expect(items[1].classes()).toContain('afs-step--active')
    expect(items[2].classes()).toContain('afs-step--pending')
  })

  it('审批人 / 审批方式 / SLA 文案（空审批人 → 待分配，未知方式原样）', () => {
    const w = mountSteps({ steps: STEPS })
    const items = w.findAll('[data-test="flow-step"]')
    expect(items[0].text()).toContain('procurement_manager')
    expect(items[0].text()).toContain('任一人通过')
    expect(items[0].text()).toContain('24 小时内')
    expect(items[1].text()).toContain('待分配')
    expect(items[1].text()).toContain('全部通过')
    expect(items[1].text()).not.toContain('小时内')
    expect(items[2].text()).toContain('custom_mode')
  })

  it('missReason 非空 → 渲染未命中提示', () => {
    const w = mountSteps({ steps: STEPS, missReason: '未命中策略，回落默认链' })
    expect(w.find('[data-test="flow-miss-reason"]').text()).toBe('未命中策略，回落默认链')
  })

  it('仅 done 且 actor 非空 → 渲染处理人与时间', () => {
    const w = mountSteps({ steps: STEPS })
    const actors = w.findAll('[data-test="flow-step-actor"]')
    expect(actors).toHaveLength(1)
    expect(actors[0].text()).toContain('u-a')
    expect(actors[0].text()).toContain('2026-11-10 09:00')
  })

  it('空 steps → 渲染空 ol', () => {
    const w = mountSteps()
    expect(w.find('ol.afs-list').exists()).toBe(true)
    expect(w.findAll('[data-test="flow-step"]')).toHaveLength(0)
  })
})
