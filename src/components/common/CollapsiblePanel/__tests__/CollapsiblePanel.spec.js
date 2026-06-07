/**
 * CollapsiblePanel.spec.js - 折叠面板组件测试
 *
 * 测试核心功能：
 * 1. 折叠/展开功能
 * 2. v-model 双向绑定
 * 3. 宽度拖拽调整
 * 4. Props 配置
 * 5. Slots 插槽
 * 6. Events 事件
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import CollapsiblePanel from '../CollapsiblePanel.vue'

// @element-plus/icons-vue 已在 src/test/setup.js 中全局 mock（Proxy 兜底）

const createWrapper = (props = {}, slots = {}) => {
  return mount(CollapsiblePanel, {
    props: {
      defaultExpanded: true,
      resizable: false,
      minWidth: 200,
      maxWidth: 600,
      defaultWidth: 280,
      ...props
    },
    slots,
    attachTo: document.body
  })
}

describe('CollapsiblePanel', () => {
  describe('rendering', () => {
    it('renders with default props', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.collapsible-panel').exists()).toBe(true)
      expect(wrapper.find('.collapsible-panel__container').exists()).toBe(true)
    })

    it('renders title when provided', () => {
      const wrapper = createWrapper({ title: 'Test Title' })
      expect(wrapper.find('.collapsible-panel__title').text()).toBe('Test Title')
    })

    it('renders badge when provided', () => {
      const wrapper = createWrapper({ badge: 5 })
      expect(wrapper.find('.collapsible-panel__badge').exists()).toBe(true)
      expect(wrapper.find('.collapsible-panel__badge').text()).toBe('5')
    })

    it('renders badge with max value', () => {
      // 源码直接将 badge 数字渲染为文本，没有 99+ 截断逻辑
      const wrapper = createWrapper({ badge: 150 })
      expect(wrapper.find('.collapsible-panel__badge').text()).toBe('150')
    })

    it('hides content when collapsed', () => {
      const wrapper = createWrapper({ defaultExpanded: false })
      expect(wrapper.find('.collapsible-panel').classes()).toContain('is-collapsed')
    })

    it('shows content when expanded', () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      expect(wrapper.find('.collapsible-panel').classes()).not.toContain('is-collapsed')
    })
  })

  describe('collapse/expand', () => {
    it('toggles on header click', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      await wrapper.find('.collapsible-panel__header').trigger('click')
      expect(wrapper.emitted('update:expanded')).toBeTruthy()
      expect(wrapper.emitted('toggle')).toBeTruthy()
    })

    it('emits false when collapsing', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      await wrapper.find('.collapsible-panel__header').trigger('click')
      expect(wrapper.emitted('update:expanded')[0][0]).toBe(false)
    })

    it('emits true when expanding', async () => {
      const wrapper = createWrapper({ defaultExpanded: false })
      await wrapper.find('.collapsible-panel__header').trigger('click')
      expect(wrapper.emitted('update:expanded')[0][0]).toBe(true)
    })

    it('does not toggle when collapsible is false', async () => {
      const wrapper = createWrapper({ collapsible: false, defaultExpanded: true })
      expect(wrapper.find('.collapsible-panel__header').exists()).toBe(false)
      expect(wrapper.emitted('update:expanded')).toBeFalsy()
    })

    it('updates width when collapsed', async () => {
      const wrapper = createWrapper({ defaultExpanded: true, defaultWidth: 280 })
      await wrapper.find('.collapsible-panel__header').trigger('click')
      const style = wrapper.find('.collapsible-panel').attributes('style')
      expect(style).toContain('width: 48px')
    })

    it('handles external expanded changes via watch', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      expect(wrapper.classes()).not.toContain('is-collapsed')
      await wrapper.setProps({ defaultExpanded: false })
      await nextTick()
      expect(wrapper.classes()).toContain('is-collapsed')
    })
  })

  describe('resize', () => {
    it('renders resizer when resizable is true', () => {
      const wrapper = createWrapper({ resizable: true, defaultExpanded: true })
      expect(wrapper.find('.collapsible-panel__resizer').exists()).toBe(true)
    })

    it('hides resizer when collapsed', () => {
      const wrapper = createWrapper({ resizable: true, defaultExpanded: false })
      expect(wrapper.find('.collapsible-panel__resizer').exists()).toBe(false)
    })

    it('emits resize event on drag', async () => {
      const wrapper = createWrapper({
        resizable: true,
        defaultExpanded: true,
        defaultWidth: 280,
        minWidth: 100,
        maxWidth: 500
      })

      const resizer = wrapper.find('.collapsible-panel__resizer')
      const rect = { left: 280, width: 0 }
      resizer.element.getBoundingClientRect = () => rect

      const startEvent = new MouseEvent('mousedown', { clientX: 280, bubbles: true })
      resizer.element.dispatchEvent(startEvent)

      const moveEvent = new MouseEvent('mousemove', { clientX: 320, bubbles: true })
      document.dispatchEvent(moveEvent)

      const upEvent = new MouseEvent('mouseup', { bubbles: true })
      document.dispatchEvent(upEvent)

      expect(wrapper.emitted('resize')).toBeTruthy()
      expect(wrapper.emitted('update:width')).toBeTruthy()
    })

    it('respects minWidth constraint', async () => {
      const wrapper = createWrapper({
        resizable: true,
        defaultExpanded: true,
        defaultWidth: 280,
        minWidth: 200
      })

      const resizer = wrapper.find('.collapsible-panel__resizer')
      const rect = { left: 280, width: 0 }
      resizer.element.getBoundingClientRect = () => rect

      const startEvent = new MouseEvent('mousedown', { clientX: 280, bubbles: true })
      resizer.element.dispatchEvent(startEvent)

      const moveEvent = new MouseEvent('mousemove', { clientX: 50, bubbles: true })
      document.dispatchEvent(moveEvent)

      const upEvent = new MouseEvent('mouseup', { bubbles: true })
      document.dispatchEvent(upEvent)

      const resizeEmit = wrapper.emitted('resize')[0][0]
      expect(resizeEmit).toBeGreaterThanOrEqual(200)
    })

    it('respects maxWidth constraint', async () => {
      const wrapper = createWrapper({
        resizable: true,
        defaultExpanded: true,
        defaultWidth: 280,
        maxWidth: 400
      })

      const resizer = wrapper.find('.collapsible-panel__resizer')
      const rect = { left: 280, width: 0 }
      resizer.element.getBoundingClientRect = () => rect

      const startEvent = new MouseEvent('mousedown', { clientX: 280, bubbles: true })
      resizer.element.dispatchEvent(startEvent)

      const moveEvent = new MouseEvent('mousemove', { clientX: 800, bubbles: true })
      document.dispatchEvent(moveEvent)

      const upEvent = new MouseEvent('mouseup', { bubbles: true })
      document.dispatchEvent(upEvent)

      const resizeEmit = wrapper.emitted('resize')[0][0]
      expect(resizeEmit).toBeLessThanOrEqual(400)
    })
  })

  describe('slots', () => {
    it('renders default slot content', () => {
      const wrapper = createWrapper({}, {
        default: '<div class="slot-content">Test Content</div>'
      })
      expect(wrapper.find('.slot-content').text()).toBe('Test Content')
    })

    it('renders header slot instead of title', () => {
      const wrapper = createWrapper({}, {
        header: '<span class="custom-header">Custom Header</span>',
        title: 'This should not appear'
      })
      expect(wrapper.find('.custom-header').exists()).toBe(true)
      expect(wrapper.find('.collapsible-panel__title').exists()).toBe(false)
    })

    it('renders extra slot content', () => {
      const wrapper = createWrapper({}, {
        extra: '<button class="extra-btn">Action</button>'
      })
      expect(wrapper.find('.extra-btn').text()).toBe('Action')
    })
  })

  describe('collapse position', () => {
    it('renders outside collapse button when collapsePosition is outside', () => {
      const wrapper = createWrapper({ collapsePosition: 'outside' })
      expect(wrapper.find('.collapsible-panel__collapse-btn').exists()).toBe(true)
    })

    it('hides outside collapse button when collapsePosition is header', () => {
      const wrapper = createWrapper({ collapsePosition: 'header' })
      expect(wrapper.find('.collapsible-panel__collapse-btn').exists()).toBe(false)
    })
  })

  describe('height', () => {
    it('applies height: 100% when heightFull is true', () => {
      const wrapper = createWrapper({ heightFull: true })
      const style = wrapper.find('.collapsible-panel').attributes('style')
      expect(style).toContain('height: 100%')
    })

    it('does not apply height when heightFull is false', () => {
      const wrapper = createWrapper({ heightFull: false })
      const style = wrapper.find('.collapsible-panel').attributes('style')
      expect(style).not.toContain('height')
    })
  })

  describe('custom class', () => {
    it('applies custom class', () => {
      const wrapper = createWrapper({ class: 'custom-class' })
      expect(wrapper.find('.collapsible-panel').classes()).toContain('custom-class')
    })
  })

  describe('watchers', () => {
    it('updates expanded state when defaultExpanded changes', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      await wrapper.setProps({ defaultExpanded: false })
      expect(wrapper.classes()).toContain('is-collapsed')
    })
  })
})
