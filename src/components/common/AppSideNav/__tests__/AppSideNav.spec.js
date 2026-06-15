/**
 * AppSideNav.spec.js - AppSideNav 组件测试
 *
 * 背景：AppSideNav 是 YonDesign 侧边导航组件，支持多级菜单、展开/折叠、active 状态。
 *
 * 测试模式：
 *   - mount() + stubs el-icon
 *   - 断言 nav-item 渲染、active class、展开状态
 *
 * 覆盖场景：
 *   1. 默认渲染
 *   2. items 渲染
 *   3. modelValue active 状态
 *   4. 点击叶子节点 emit
 *   5. 点击父节点展开/折叠
 *   6. children 渲染
 *   7. icon 渲染
 *   8. watch 自动展开
 *   9. isItemActive 逻辑
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AppSideNav from '../AppSideNav.vue'

const stubs = {
  'el-icon': {
    template: '<span class="el-icon-stub"><slot /></span>',
  },
}

function createWrapper(props = {}) {
  return mount(AppSideNav, {
    props: {
      items: [],
      modelValue: '',
      ...props,
    },
    global: { stubs },
  })
}

const simpleItems = [
  { key: 'home', label: '首页', to: '/home' },
  { key: 'about', label: '关于', to: '/about' },
]

const nestedItems = [
  {
    key: 'parent1',
    label: '父级 1',
    children: [
      { key: 'child1', label: '子级 1-1', to: '/child1' },
      { key: 'child2', label: '子级 1-2', to: '/child2' },
    ],
  },
  { key: 'parent2', label: '父级 2', to: '/parent2' },
]

const itemsWithIcons = [
  { key: 'home', label: '首页', icon: 'Home', to: '/home' },
  { key: 'settings', label: '设置', icon: 'Setting', to: '/settings' },
]

describe('AppSideNav', () => {
  // --- 1. 默认渲染 ---
  it('默认渲染', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-side-nav').exists()).toBe(true)
    expect(wrapper.find('.nav').exists()).toBe(true)
  })

  // --- 2. items 渲染 ---
  it('渲染 items', () => {
    const wrapper = createWrapper({ items: simpleItems })
    const navItems = wrapper.findAll('.nav-item')
    expect(navItems).toHaveLength(2)
  })

  it('渲染 item label', () => {
    const wrapper = createWrapper({ items: simpleItems })
    const labels = wrapper.findAll('.label')
    expect(labels[0].text()).toBe('首页')
    expect(labels[1].text()).toBe('关于')
  })

  // --- 3. modelValue active 状态 ---
  it('modelValue 匹配的 item 有 active class', () => {
    const wrapper = createWrapper({ items: simpleItems, modelValue: 'home' })
    const navItems = wrapper.findAll('.nav-item')
    expect(navItems[0].classes()).toContain('active')
    expect(navItems[1].classes()).not.toContain('active')
  })

  it('modelValue 变化时 active 状态更新', async () => {
    const wrapper = createWrapper({ items: simpleItems, modelValue: 'home' })
    await wrapper.setProps({ modelValue: 'about' })
    const navItems = wrapper.findAll('.nav-item')
    expect(navItems[0].classes()).not.toContain('active')
    expect(navItems[1].classes()).toContain('active')
  })

  // --- 4. 点击叶子节点 emit ---
  it('点击叶子节点 emit update:modelValue', async () => {
    const wrapper = createWrapper({ items: simpleItems, modelValue: '' })
    const navItem = wrapper.findAll('.nav-item')[0]
    await navItem.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['home'])
  })

  it('点击有 to 的节点才 emit', async () => {
    const items = [
      { key: 'no-to', label: '无 to' },
      { key: 'with-to', label: '有 to', to: '/path' },
    ]
    const wrapper = createWrapper({ items, modelValue: '' })
    const navItems = wrapper.findAll('.nav-item')

    await navItems[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()

    await navItems[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
  })

  // --- 5. 点击父节点展开/折叠 ---
  it('点击父节点展开', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    const parentItem = wrapper.findAll('.nav-item')[0]
    await parentItem.trigger('click')
    // 展开后应该有 children
    expect(wrapper.find('.nav-children').exists()).toBe(true)
  })

  it('点击父节点折叠', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    const parentItem = wrapper.findAll('.nav-item')[0]
    await parentItem.trigger('click') // 展开
    expect(wrapper.find('.nav-children').exists()).toBe(true)
    await parentItem.trigger('click') // 折叠
    expect(wrapper.find('.nav-children').exists()).toBe(false)
  })

  it('点击父节点不 emit update:modelValue', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    const parentItem = wrapper.findAll('.nav-item')[0]
    await parentItem.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  // --- 6. children 渲染 ---
  it('展开后渲染 children', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    const parentItem = wrapper.findAll('.nav-item')[0]
    await parentItem.trigger('click')
    const children = wrapper.findAll('.nav-item.child')
    expect(children).toHaveLength(2)
  })

  it('child label 正确', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    const parentItem = wrapper.findAll('.nav-item')[0]
    await parentItem.trigger('click')
    const childLabels = wrapper.findAll('.nav-item.child .label')
    expect(childLabels[0].text()).toBe('子级 1-1')
    expect(childLabels[1].text()).toBe('子级 1-2')
  })

  it('child active 状态', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: 'child1' })
    // watch 会自动展开 parent
    const children = wrapper.findAll('.nav-item.child')
    expect(children[0].classes()).toContain('active')
    expect(children[1].classes()).not.toContain('active')
  })

  // --- 7. icon 渲染 ---
  it('有 icon 时渲染 nav-icon', () => {
    const wrapper = createWrapper({ items: itemsWithIcons, modelValue: '' })
    const icons = wrapper.findAll('.nav-icon')
    expect(icons.length).toBeGreaterThan(0)
  })

  it('无 icon 时不渲染 nav-icon', () => {
    const wrapper = createWrapper({ items: simpleItems, modelValue: '' })
    expect(wrapper.find('.nav-icon').exists()).toBe(false)
  })

  // --- 8. watch 自动展开 ---
  it('modelValue 为 child key 时自动展开 parent', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: 'child1' })
    // watch immediate 触发
    expect(wrapper.find('.nav-children').exists()).toBe(true)
  })

  it('modelValue 变为 child key 时自动展开', async () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    expect(wrapper.find('.nav-children').exists()).toBe(false)
    await wrapper.setProps({ modelValue: 'child1' })
    expect(wrapper.find('.nav-children').exists()).toBe(true)
  })

  // --- 9. isItemActive 逻辑 ---
  it('父节点 active 当 child 被选中', () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: 'child1' })
    const parentItem = wrapper.findAll('.nav-item')[0]
    expect(parentItem.classes()).toContain('active')
  })

  it('父节点 active 当自身被选中', () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: 'parent2' })
    const parentItems = wrapper.findAll('.nav-item')
    // parent2 是第二个
    expect(parentItems[1].classes()).toContain('active')
  })

  // --- 10. 箭头图标 ---
  it('有 children 时渲染 arrow-icon', () => {
    const wrapper = createWrapper({ items: nestedItems, modelValue: '' })
    expect(wrapper.find('.arrow-icon').exists()).toBe(true)
  })

  it('无 children 时不渲染 arrow-icon', () => {
    const wrapper = createWrapper({ items: simpleItems, modelValue: '' })
    expect(wrapper.find('.arrow-icon').exists()).toBe(false)
  })
})
