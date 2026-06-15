/**
 * AppShell.spec.js - AppShell 组件测试
 *
 * 背景：AppShell 是 YonDesign 布局外壳组件，提供 header/tabs/sidebar/content/footer 插槽。
 *
 * 测试模式：
 *   - mount() + 直接断言 slot 渲染和 class
 *
 * 覆盖场景：
 *   1. 默认渲染
 *   2. showSidebar prop
 *   3. showTabs prop
 *   4. sidebarWidth prop
 *   5. sidebarCollapsible prop
 *   6. header slot
 *   7. tabs slot
 *   8. sidebar slot
 *   9. default slot
 *   10. footer slot
 *   11. sidebar hidden class
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppShell from '../AppShell.vue'

function createWrapper(props = {}, slots = {}) {
  return mount(AppShell, {
    props: {
      ...props,
    },
    slots,
  })
}

describe('AppShell', () => {
  // --- 1. 默认渲染 ---
  it('默认渲染', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell').exists()).toBe(true)
  })

  // --- 2. showSidebar ---
  it('默认 showSidebar=true', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell__sidebar').exists()).toBe(true)
  })

  it('showSidebar=false 时不渲染 sidebar', () => {
    const wrapper = createWrapper({ showSidebar: false })
    expect(wrapper.find('.app-shell__sidebar').exists()).toBe(false)
  })

  // --- 3. showTabs ---
  it('默认 showTabs=false', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell__tabs-bar').exists()).toBe(false)
  })

  it('showTabs=true 时渲染 tabs bar', () => {
    const wrapper = createWrapper({ showTabs: true })
    expect(wrapper.find('.app-shell__tabs-bar').exists()).toBe(true)
  })

  // --- 4. sidebarWidth ---
  it('默认 sidebarWidth=240', () => {
    const wrapper = createWrapper()
    const sidebar = wrapper.find('.app-shell__sidebar')
    // 默认宽度不是 0，所以没有 hidden class
    expect(sidebar.classes()).not.toContain('app-shell__sidebar--hidden')
  })

  it('sidebarWidth=0 时添加 hidden class', () => {
    const wrapper = createWrapper({ sidebarWidth: 0 })
    const sidebar = wrapper.find('.app-shell__sidebar')
    expect(sidebar.classes()).toContain('app-shell__sidebar--hidden')
  })

  // --- 5. sidebarCollapsible ---
  it('sidebarCollapsible prop 存在', () => {
    const wrapper = createWrapper({ sidebarCollapsible: true })
    expect(wrapper.props('sidebarCollapsible')).toBe(true)
  })

  // --- 6. header slot ---
  it('header slot 渲染', () => {
    const wrapper = createWrapper({}, {
      header: '<div class="custom-header">Header</div>',
    })
    expect(wrapper.find('.custom-header').exists()).toBe(true)
  })

  it('未提供 header slot 时使用默认 header', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell__header').exists()).toBe(true)
  })

  // --- 7. tabs slot ---
  it('tabs slot 渲染', () => {
    const wrapper = createWrapper({ showTabs: true }, {
      tabs: '<div class="custom-tabs">Tabs</div>',
    })
    expect(wrapper.find('.custom-tabs').exists()).toBe(true)
  })

  // --- 8. sidebar slot ---
  it('sidebar slot 渲染', () => {
    const wrapper = createWrapper({}, {
      sidebar: '<div class="custom-sidebar">Sidebar</div>',
    })
    expect(wrapper.find('.custom-sidebar').exists()).toBe(true)
  })

  // --- 9. default slot ---
  it('default slot 渲染', () => {
    const wrapper = createWrapper({}, {
      default: '<div class="main-content">Main</div>',
    })
    expect(wrapper.find('.main-content').exists()).toBe(true)
  })

  // --- 10. footer slot ---
  it('未提供 footer slot 时不渲染 footer', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell__footer').exists()).toBe(false)
  })

  it('提供 footer slot 时渲染 footer', () => {
    const wrapper = createWrapper({}, {
      footer: '<div class="custom-footer">Footer</div>',
    })
    expect(wrapper.find('.custom-footer').exists()).toBe(true)
  })

  // --- 11. 结构完整性 ---
  it('包含 header/body/content 结构', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell__header').exists()).toBe(true)
    expect(wrapper.find('.app-shell__body').exists()).toBe(true)
    expect(wrapper.find('.app-shell__content').exists()).toBe(true)
  })

  it('body 包含 sidebar 和 content', () => {
    const wrapper = createWrapper()
    const body = wrapper.find('.app-shell__body')
    expect(body.find('.app-shell__sidebar').exists()).toBe(true)
    expect(body.find('.app-shell__content').exists()).toBe(true)
  })
})
