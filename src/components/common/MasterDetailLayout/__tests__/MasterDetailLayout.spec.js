/**
 * MasterDetailLayout.spec.js - 主从布局组件测试
 *
 * 测试核心功能：
 * 1. 默认渲染 (sidebar + detail)
 * 2. 折叠/展开 (collapse/expand)
 * 3. 宽度拖拽调整 (resize)
 * 4. minWidth / maxWidth 约束
 * 5. Slots 插槽
 *
 * 关键设计：折叠按钮在 sidebar header 内部（不与 resizer 重叠），
 * 展开按钮在 layout 根级别（sidebar 折叠时显示）。
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import MasterDetailLayout from '../MasterDetailLayout.vue'

const createWrapper = (props = {}, slots = {}) => {
  return mount(MasterDetailLayout, {
    props: {
      sidebarWidth: '320px',
      sidebarCollapsible: false,
      sidebarCollapsed: false,
      showBorder: true,
      minWidth: 200,
      maxWidth: 600,
      ...props
    },
    slots: {
      master: '<div class="master-content">master</div>',
      detail: '<div class="detail-content">detail</div>',
      ...slots
    },
    attachTo: document.body
  })
}

describe('MasterDetailLayout', () => {
  describe('rendering', () => {
    it('renders root, sidebar and detail', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.master-detail-layout').exists()).toBe(true)
      expect(wrapper.find('.master-detail-layout__sidebar').exists()).toBe(true)
      expect(wrapper.find('.master-detail-layout__detail').exists()).toBe(true)
    })

    it('renders default slots', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.master-content').exists()).toBe(true)
      expect(wrapper.find('.detail-content').exists()).toBe(true)
    })

    it('hides resizer when showBorder is false', () => {
      const wrapper = createWrapper({ showBorder: false })
      expect(wrapper.find('.master-detail-layout__resizer').exists()).toBe(false)
    })

    it('hides resizer when sidebar is collapsed', () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: true })
      expect(wrapper.find('.master-detail-layout__resizer').exists()).toBe(false)
    })

    it('renders collapse button when sidebarCollapsible and not collapsed', () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: false })
      expect(wrapper.find('.master-detail-layout__collapse-btn').exists()).toBe(true)
      expect(wrapper.find('.master-detail-layout__expand-btn').exists()).toBe(false)
    })

    it('renders expand button when sidebarCollapsible and collapsed', () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: true })
      expect(wrapper.find('.master-detail-layout__collapse-btn').exists()).toBe(false)
      expect(wrapper.find('.master-detail-layout__expand-btn').exists()).toBe(true)
    })

    it('renders neither button when not collapsible', () => {
      const wrapper = createWrapper({ sidebarCollapsible: false })
      expect(wrapper.find('.master-detail-layout__collapse-btn').exists()).toBe(false)
      expect(wrapper.find('.master-detail-layout__expand-btn').exists()).toBe(false)
    })
  })

  describe('collapse/expand', () => {
    it('emits collapse-change=true when collapse button is clicked', async () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: false })
      await wrapper.find('.master-detail-layout__collapse-btn').trigger('click')
      expect(wrapper.emitted('collapse-change')).toBeTruthy()
      expect(wrapper.emitted('collapse-change')[0][0]).toBe(true)
      expect(wrapper.emitted('update:sidebarCollapsed')).toBeTruthy()
    })

    it('emits collapse-change=false when expand button is clicked', async () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: true })
      await wrapper.find('.master-detail-layout__expand-btn').trigger('click')
      expect(wrapper.emitted('collapse-change')[0][0]).toBe(false)
    })

    it('sidebar width is 0 when collapsed', () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: true })
      const style = wrapper.find('.master-detail-layout__sidebar').attributes('style')
      expect(style).toContain('width: 0px')
    })

    it('sidebar width reflects sidebarWidth prop when expanded', () => {
      const wrapper = createWrapper({ sidebarWidth: '400px' })
      const style = wrapper.find('.master-detail-layout__sidebar').attributes('style')
      expect(style).toContain('width: 400px')
    })
  })

  describe('resize (drag to adjust width)', () => {
    it('renders resizer when showBorder is true and not collapsed', () => {
      const wrapper = createWrapper({ showBorder: true, sidebarCollapsed: false })
      expect(wrapper.find('.master-detail-layout__resizer').exists()).toBe(true)
    })

    it('collapse button does NOT overlap resizer', () => {
      // Regression: collapse button was position:absolute overlapping resizer, blocking drag
      // Fix: collapse button is now inside sidebar-header, expand button is only shown when collapsed
      const wrapper = createWrapper({
        sidebarWidth: '320px',
        sidebarCollapsible: true
      })

      const sidebar = wrapper.find('.master-detail-layout__sidebar')
      const collapseBtn = wrapper.find('.master-detail-layout__collapse-btn')
      const resizer = wrapper.find('.master-detail-layout__resizer')

      // Collapse button is INSIDE the sidebar (in sidebar-header)
      expect(sidebar.element.contains(collapseBtn.element)).toBe(true)
      // Resizer is OUTSIDE the sidebar (sibling)
      expect(sidebar.element.contains(resizer.element)).toBe(false)
    })

    it('expand button is available when sidebar is collapsed', async () => {
      const wrapper = createWrapper({
        sidebarCollapsible: true,
        sidebarCollapsed: true
      })

      const expandBtn = wrapper.find('.master-detail-layout__expand-btn')
      expect(expandBtn.exists()).toBe(true)
      await expandBtn.trigger('click')
      expect(wrapper.emitted('collapse-change')).toBeTruthy()
      expect(wrapper.emitted('collapse-change')[0][0]).toBe(false)
    })

    it('resizes sidebar on drag', async () => {
      const wrapper = createWrapper({
        sidebarWidth: '300px',
        minWidth: 200,
        maxWidth: 600
      })

      const resizer = wrapper.find('.master-detail-layout__resizer')

      const downEvent = new MouseEvent('mousedown', { clientX: 300, bubbles: true })
      resizer.element.dispatchEvent(downEvent)

      const moveEvent = new MouseEvent('mousemove', { clientX: 400, bubbles: true })
      document.dispatchEvent(moveEvent)
      await nextTick()

      const upEvent = new MouseEvent('mouseup', { bubbles: true })
      document.dispatchEvent(upEvent)
      await nextTick()

      const sidebar = wrapper.find('.master-detail-layout__sidebar')
      const style = sidebar.attributes('style')
      expect(style).toContain('width: 400px')
    })

    it('respects minWidth constraint during drag', async () => {
      const wrapper = createWrapper({
        sidebarWidth: '300px',
        minWidth: 200,
        maxWidth: 600
      })

      const resizer = wrapper.find('.master-detail-layout__resizer')

      resizer.element.dispatchEvent(new MouseEvent('mousedown', { clientX: 300, bubbles: true }))
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 50, bubbles: true }))
      await nextTick()
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await nextTick()

      const style = wrapper.find('.master-detail-layout__sidebar').attributes('style')
      expect(style).toContain('width: 200px')
    })

    it('respects maxWidth constraint during drag', async () => {
      const wrapper = createWrapper({
        sidebarWidth: '300px',
        minWidth: 200,
        maxWidth: 500
      })

      const resizer = wrapper.find('.master-detail-layout__resizer')

      resizer.element.dispatchEvent(new MouseEvent('mousedown', { clientX: 300, bubbles: true }))
      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 900, bubbles: true }))
      await nextTick()
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await nextTick()

      const style = wrapper.find('.master-detail-layout__sidebar').attributes('style')
      expect(style).toContain('width: 500px')
    })

    it('adds is-dragging class during drag for visual feedback', async () => {
      const wrapper = createWrapper()
      const resizer = wrapper.find('.master-detail-layout__resizer')

      expect(resizer.classes()).not.toContain('master-detail-layout__resizer--dragging')

      resizer.element.dispatchEvent(new MouseEvent('mousedown', { clientX: 320, bubbles: true }))
      await nextTick()

      expect(wrapper.find('.master-detail-layout__resizer').classes()).toContain('master-detail-layout__resizer--dragging')

      document.dispatchEvent(new MouseEvent('mousemove', { clientX: 350, bubbles: true }))
      document.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await nextTick()

      expect(wrapper.find('.master-detail-layout__resizer').classes()).not.toContain('master-detail-layout__resizer--dragging')
    })

    it('does not start resize when sidebar is collapsed', async () => {
      const wrapper = createWrapper({ sidebarCollapsible: true, sidebarCollapsed: true })
      expect(wrapper.find('.master-detail-layout__resizer').exists()).toBe(false)
    })
  })

  describe('cleanup', () => {
    it('removes document event listeners on unmount', () => {
      const removeSpy = vi.spyOn(document, 'removeEventListener')
      const wrapper = createWrapper()
      const resizer = wrapper.find('.master-detail-layout__resizer')

      resizer.element.dispatchEvent(new MouseEvent('mousedown', { clientX: 320, bubbles: true }))
      wrapper.unmount()

      expect(removeSpy).toHaveBeenCalledWith('mousemove', expect.any(Function))
      expect(removeSpy).toHaveBeenCalledWith('mouseup', expect.any(Function))
    })
  })
})
