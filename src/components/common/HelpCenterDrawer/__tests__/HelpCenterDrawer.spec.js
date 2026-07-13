// HelpCenterDrawer - P3 unit tests
//   1) 操作场景 Tab + HelpAccordion 渲染
//   2) 最大化/还原
//   3) URL ?help=&step= 自动展开
//   4) 关闭 (close 按钮 / mask / Escape)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import HelpCenterDrawer from '../HelpCenterDrawer.vue'

// mock fetch: scenario.json
const fakeScenario = {
  scenario_id: 'archdata-management',
  title: '架构数据管理',
  summary: '...',
  total_steps: 4,
  steps: [
    { step_no: 1, title: 'S1', action: 'A1', expected: 'E1', tip: 'T1', screenshot: '', video: '' },
    { step_no: 2, title: 'S2', action: 'A2', expected: 'E2', tip: 'T2', screenshot: '', video: 'x.mp4' },
    { step_no: 3, title: 'S3', action: 'A3', expected: 'E3', tip: '', screenshot: '', video: '' },
    { step_no: 4, title: 'S4', action: 'A4', expected: 'E4', tip: '', screenshot: '', video: '' }
  ]
}

describe('HelpCenterDrawer - P3', () => {
  let wrapper
  let originalFetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => fakeScenario
    }))
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    globalThis.fetch = originalFetch
    document.body.style.overflow = ''
    // 清理 URL query
    if (window.history && window.history.replaceState) {
      window.history.replaceState({}, '', window.location.pathname)
    }
  })

  it('does not render drawer content when modelValue is false', () => {
    wrapper = mount(HelpCenterDrawer, { props: { modelValue: false } })
    expect(document.querySelector('.help-drawer')).toBeNull()
  })

  it('renders drawer with 操作场景 title when modelValue is true', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    expect(document.querySelector('.help-drawer')).toBeTruthy()
    expect(document.querySelector('.help-drawer__title').textContent).toContain('操作场景')
  })

  it('emits update:modelValue false when close button clicked', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    const closeBtn = document.querySelector('.help-drawer__close')
    expect(closeBtn).toBeTruthy()
    closeBtn.click()
    await nextTick()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('emits update:modelValue false when mask clicked', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    document.querySelector('.help-drawer__mask').click()
    await nextTick()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('toggles maximize class on header button click', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    const btn = document.querySelector('.help-drawer__header-btn')
    expect(btn).toBeTruthy()
    const wrap = document.querySelector('.help-drawer__wrapper')
    expect(wrap.classList.contains('is-maximized')).toBe(false)
    btn.click()
    await nextTick()
    expect(wrap.classList.contains('is-maximized')).toBe(true)
    btn.click()
    await nextTick()
    expect(wrap.classList.contains('is-maximized')).toBe(false)
  })

  it('applies custom width when not maximized', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, width: 1200, attachTo: document.body }
    })
    await nextTick()
    const wrap = document.querySelector('.help-drawer__wrapper')
    expect(wrap.style.width).toBe('1200px')
  })

  it('overrides width to 100% when maximized', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, width: 1200, attachTo: document.body }
    })
    await nextTick()
    document.querySelector('.help-drawer__header-btn').click()
    await nextTick()
    const wrap = document.querySelector('.help-drawer__wrapper')
    expect(wrap.classList.contains('is-maximized')).toBe(true)
    // 100% from CSS class
    expect(wrap.style.width).not.toBe('1200px')
  })

  it('Escape first restores maximize, then closes on second Escape', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    // 最大化
    document.querySelector('.help-drawer__header-btn').click()
    await nextTick()
    expect(document.querySelector('.help-drawer__wrapper').classList.contains('is-maximized')).toBe(true)
    // 第一次 Escape: 还原最大化
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(document.querySelector('.help-drawer__wrapper').classList.contains('is-maximized')).toBe(false)
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    // 第二次 Escape: 关闭
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('locks body scroll when drawer opens and restores on close', async () => {
    wrapper = mount(HelpCenterDrawer, { props: { modelValue: false } })
    await wrapper.setProps({ modelValue: true })
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')
    await wrapper.setProps({ modelValue: false })
    await nextTick()
    expect(document.body.style.overflow).toBe('')
  })

  it('uses default scenarioId archdata-management', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    await flushPromises()
    expect(globalThis.fetch).toHaveBeenCalledWith('/docs/scenarios/archdata-management/scenario.json')
  })

  it('passes initialStep prop down to HelpAccordion', async () => {
    window.history.replaceState({}, '', '?help=archdata-management&step=2')
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, initialStep: 2, attachTo: document.body }
    })
    await nextTick()
    await flushPromises()
    await nextTick()
    const collapses = document.querySelectorAll('.app-collapse')
    expect(collapses.length).toBe(4)
    expect(collapses[1].classList.contains('app-collapse--expanded')).toBe(true)
    expect(collapses[0].classList.contains('app-collapse--expanded')).toBe(false)
  })
})
