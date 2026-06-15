/**
 * AppLayout.spec.js - AppLayout 组件测试
 *
 * 背景：AppLayout 是 YonDesign 布局组件，组合 AppShell/TopNavHeader/AppTabs/AppSideNav。
 *       依赖 vue-router 和 tabStore，测试时需要 mock。
 *
 * 测试模式：
 *   - mount() + stubs 所有子组件
 *   - mock vue-router 和 tabStore
 *
 * 覆盖场景：
 *   1. 默认渲染
 *   2. showSidebar prop
 *   3. showTabs prop
 *   4. sidebarWidth prop
 *   5. sidebarItems 渲染
 *   6. sidebarActive prop
 *   7. maxTabs prop
 *   8. logo 相关 props
 *   9. breadcrumbs prop
 *   10. 事件 emit
 *   11. sidebar toggle
 *   12. slot 渲染
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AppLayout from '../AppLayout.vue'

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// Mock tabStore
const mockTabStore = {
  tabs: [],
  activeTabId: '',
  switchTab: vi.fn(),
  closeTab: vi.fn(),
}
vi.mock('@/stores/tabStore', () => ({
  useTabStore: () => mockTabStore,
}))

// Stubs
const stubs = {
  AppShell: {
    name: 'AppShell',
    template: `
      <div class="app-shell-stub">
        <div class="header-slot"><slot name="header" /></div>
        <div class="tabs-slot"><slot name="tabs" /></div>
        <div class="sidebar-slot"><slot name="sidebar" /></div>
        <div class="default-slot"><slot /></div>
        <div class="footer-slot"><slot name="footer" /></div>
      </div>
    `,
    props: ['showSidebar', 'showTabs', 'sidebarWidth'],
  },
  TopNavHeader: {
    name: 'TopNavHeader',
    template: '<div class="top-nav-header-stub" />',
    props: ['logoUrl', 'logoAlt', 'logoText', 'breadcrumbs'],
  },
  AppTabs: {
    name: 'AppTabs',
    template: '<div class="app-tabs-stub" />',
    props: ['tabs', 'modelValue', 'maxTabs'],
  },
  AppSideNav: {
    name: 'AppSideNav',
    template: '<div class="app-side-nav-stub" />',
    props: ['items', 'modelValue'],
  },
}

function createWrapper(props = {}, slots = {}) {
  return mount(AppLayout, {
    props: {
      sidebarItems: [],
      breadcrumbs: [],
      ...props,
    },
    slots,
    global: { stubs },
  })
}

describe('AppLayout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockTabStore.tabs = []
    mockTabStore.activeTabId = ''
  })

  // --- 1. 默认渲染 ---
  it('默认渲染', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-shell-stub').exists()).toBe(true)
  })

  // --- 2. showSidebar ---
  it('默认 showSidebar=true', () => {
    const wrapper = createWrapper()
    const shell = wrapper.findComponent({ name: 'AppShell' })
    expect(shell.props('showSidebar')).toBe(true)
  })

  it('showSidebar=false 传递', () => {
    const wrapper = createWrapper({ showSidebar: false })
    const shell = wrapper.findComponent({ name: 'AppShell' })
    expect(shell.props('showSidebar')).toBe(false)
  })

  // --- 3. showTabs ---
  it('默认 showTabs=true', () => {
    const wrapper = createWrapper()
    const shell = wrapper.findComponent({ name: 'AppShell' })
    expect(shell.props('showTabs')).toBe(true)
  })

  it('showTabs=false 传递', () => {
    const wrapper = createWrapper({ showTabs: false })
    const shell = wrapper.findComponent({ name: 'AppShell' })
    expect(shell.props('showTabs')).toBe(false)
  })

  // --- 4. sidebarWidth ---
  it('默认 sidebarWidth=240', () => {
    const wrapper = createWrapper()
    const shell = wrapper.findComponent({ name: 'AppShell' })
    // sidebarVisible 初始 false，所以 sidebarWidth 传 0
    expect(shell.props('sidebarWidth')).toBe(0)
  })

  // --- 5. sidebarItems ---
  it('sidebarItems 传递给 AppSideNav', () => {
    const items = [{ key: '1', label: 'Item 1' }]
    const wrapper = createWrapper({ sidebarItems: items, showSidebar: true })
    // sidebarVisible 初始 false，AppSideNav 不渲染
    // 需要 toggle sidebar
    const toggleBtn = wrapper.find('.sidebar-toggle-btn')
    toggleBtn.trigger('click')
    const sideNav = wrapper.findComponent({ name: 'AppSideNav' })
    expect(sideNav.exists()).toBe(true)
    expect(sideNav.props('items')).toEqual(items)
  })

  it('sidebarItems 为空时不渲染 AppSideNav', () => {
    const wrapper = createWrapper({ sidebarItems: [], showSidebar: true })
    const toggleBtn = wrapper.find('.sidebar-toggle-btn')
    toggleBtn.trigger('click')
    expect(wrapper.findComponent({ name: 'AppSideNav' }).exists()).toBe(false)
  })

  // --- 6. sidebarActive ---
  it('sidebarActive 传递给 AppSideNav', async () => {
    const items = [{ key: '1', label: 'Item 1' }]
    const wrapper = createWrapper({ sidebarItems: items, sidebarActive: '1', showSidebar: true })
    const toggleBtn = wrapper.find('.sidebar-toggle-btn')
    await toggleBtn.trigger('click')
    const sideNav = wrapper.findComponent({ name: 'AppSideNav' })
    expect(sideNav.props('modelValue')).toBe('1')
  })

  // --- 7. maxTabs ---
  it('默认 maxTabs=10', () => {
    const wrapper = createWrapper({ showTabs: true })
    const tabs = wrapper.findComponent({ name: 'AppTabs' })
    expect(tabs.props('maxTabs')).toBe(10)
  })

  it('maxTabs=5 传递', () => {
    const wrapper = createWrapper({ maxTabs: 5, showTabs: true })
    const tabs = wrapper.findComponent({ name: 'AppTabs' })
    expect(tabs.props('maxTabs')).toBe(5)
  })

  // --- 8. logo props ---
  it('logo props 传递给 TopNavHeader', () => {
    const wrapper = createWrapper({
      logoUrl: '/logo.png',
      logoAlt: 'My Logo',
      logoText: 'My App',
    })
    const header = wrapper.findComponent({ name: 'TopNavHeader' })
    expect(header.props('logoUrl')).toBe('/logo.png')
    expect(header.props('logoAlt')).toBe('My Logo')
    expect(header.props('logoText')).toBe('My App')
  })

  it('默认 logoText=ArchWorkspace', () => {
    const wrapper = createWrapper()
    const header = wrapper.findComponent({ name: 'TopNavHeader' })
    expect(header.props('logoText')).toBe('ArchWorkspace')
  })

  // --- 9. breadcrumbs ---
  it('breadcrumbs 传递给 TopNavHeader', () => {
    const breadcrumbs = [{ label: 'Home', path: '/' }]
    const wrapper = createWrapper({ breadcrumbs })
    const header = wrapper.findComponent({ name: 'TopNavHeader' })
    expect(header.props('breadcrumbs')).toEqual(breadcrumbs)
  })

  // --- 10. 事件 emit ---
  it('logo-click 事件 emit', async () => {
    const wrapper = createWrapper()
    const header = wrapper.findComponent({ name: 'TopNavHeader' })
    await header.vm.$emit('logo-click')
    expect(wrapper.emitted('logo-click')).toBeTruthy()
  })

  it('notification-click 事件 emit', async () => {
    const wrapper = createWrapper()
    const header = wrapper.findComponent({ name: 'TopNavHeader' })
    await header.vm.$emit('notification-click')
    expect(wrapper.emitted('notification-click')).toBeTruthy()
  })

  it('ai-click 事件 emit', async () => {
    const wrapper = createWrapper()
    const header = wrapper.findComponent({ name: 'TopNavHeader' })
    await header.vm.$emit('ai-click')
    expect(wrapper.emitted('ai-click')).toBeTruthy()
  })

  // --- 11. sidebar toggle ---
  it('点击 toggle 按钮切换 sidebar', async () => {
    const wrapper = createWrapper({ showTabs: true })
    const toggleBtn = wrapper.find('.sidebar-toggle-btn')
    expect(toggleBtn.classes()).not.toContain('is-active')
    await toggleBtn.trigger('click')
    expect(toggleBtn.classes()).toContain('is-active')
    await toggleBtn.trigger('click')
    expect(toggleBtn.classes()).not.toContain('is-active')
  })

  it('sidebar-collapse 事件 emit', async () => {
    const wrapper = createWrapper({ showTabs: true })
    const toggleBtn = wrapper.find('.sidebar-toggle-btn')
    await toggleBtn.trigger('click')
    expect(wrapper.emitted('sidebar-collapse')).toBeTruthy()
    expect(wrapper.emitted('sidebar-collapse')[0]).toEqual([true])
  })

  // --- 12. slot 渲染 ---
  it('默认 slot 渲染', () => {
    const wrapper = createWrapper({}, {
      default: '<div class="content">主内容</div>',
    })
    expect(wrapper.find('.content').exists()).toBe(true)
  })

  it('footer slot 渲染', () => {
    const wrapper = createWrapper({}, {
      footer: '<div class="footer">页脚</div>',
    })
    expect(wrapper.find('.footer').exists()).toBe(true)
  })

  // --- 13. tabs 渲染 ---
  it('showTabs=true 时渲染 tabs slot', () => {
    const wrapper = createWrapper({ showTabs: true })
    expect(wrapper.find('.app-tabs-stub').exists()).toBe(true)
  })

  it('showTabs=false 时不渲染 tabs slot', () => {
    const wrapper = createWrapper({ showTabs: false })
    expect(wrapper.find('.app-tabs-stub').exists()).toBe(false)
  })
})
