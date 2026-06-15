/**
 * AppCollapse.spec.js — YonDesign AppCollapse 组件测试
 *
 * 测试策略:
 * - Stub AppIcon（不依赖真实图标实现）
 * - 验证 props 透传、展开/折叠逻辑、事件触发、插槽渲染、键盘交互
 * - 覆盖 18 个场景,约 58 个用例
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AppCollapse from '../AppCollapse.vue'

// ─── stubs ───────────────────────────────────────────────────────
const AppIconStub = {
  name: 'AppIcon',
  template: '<span class="app-icon-stub" :data-name="name" :data-size="size"></span>',
  props: ['name', 'size'],
}

// ─── helper ──────────────────────────────────────────────────────
function createWrapper(props = {}, options = {}) {
  return mount(AppCollapse, {
    props,
    slots: options.slots,
    global: {
      stubs: {
        AppIcon: AppIconStub,
        ...options.stubs,
      },
    },
    ...options,
  })
}

// ─── 测试套件 ────────────────────────────────────────────────────
describe('AppCollapse', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── 1. 默认渲染 ──────────────────────────────────────────────
  describe('1-默认渲染', () => {
    it('应渲染 app-collapse 根元素', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse').exists()).toBe(true)
    })

    it('应渲染 header', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__header').exists()).toBe(true)
    })

    it('应渲染 header-content', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__header-content').exists()).toBe(true)
    })

    it('应渲染 arrow 图标', () => {
      const wrapper = createWrapper()
      const arrow = wrapper.findComponent(AppIconStub)
      expect(arrow.exists()).toBe(true)
      expect(arrow.attributes('data-name')).toBe('chevron-down')
    })

    it('默认状态为折叠', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })
  })

  // ── 2. title prop ────────────────────────────────────────────
  describe('2-title prop', () => {
    it('应渲染 title 文本', () => {
      const wrapper = createWrapper({ title: '测试标题' })
      expect(wrapper.find('.app-collapse__title').exists()).toBe(true)
      expect(wrapper.find('.app-collapse__title').text()).toBe('测试标题')
    })

    it('无 title 时不应渲染 title 元素', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__title').exists()).toBe(false)
    })
  })

  // ── 3. icon prop ─────────────────────────────────────────────
  describe('3-icon prop', () => {
    it('有 icon 时应渲染 icon', () => {
      const wrapper = createWrapper({ icon: 'settings' })
      const icons = wrapper.findAllComponents(AppIconStub)
      expect(icons.length).toBeGreaterThan(0)
      const icon = icons.find(i => i.attributes('data-name') === 'settings')
      expect(icon).toBeTruthy()
    })

    it('无 icon 时不应渲染 icon', () => {
      const wrapper = createWrapper()
      const icons = wrapper.findAllComponents(AppIconStub)
      const icon = icons.find(i => i.attributes('data-name') !== 'chevron-down')
      expect(icon).toBeFalsy()
    })

    it('应透传 iconSize', () => {
      const wrapper = createWrapper({ icon: 'settings', iconSize: 20 })
      const icons = wrapper.findAllComponents(AppIconStub)
      const icon = icons.find(i => i.attributes('data-name') === 'settings')
      expect(icon.attributes('data-size')).toBe('20')
    })

    it('iconSize 默认为 16', () => {
      const wrapper = createWrapper({ icon: 'settings' })
      const icons = wrapper.findAllComponents(AppIconStub)
      const icon = icons.find(i => i.attributes('data-name') === 'settings')
      expect(icon.attributes('data-size')).toBe('16')
    })
  })

  // ── 4. defaultExpanded prop ──────────────────────────────────
  describe('4-defaultExpanded prop', () => {
    it('defaultExpanded=true 时应展开', () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
    })

    it('defaultExpanded=false 时应折叠', () => {
      const wrapper = createWrapper({ defaultExpanded: false })
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })

    it('defaultExpanded 变化时应响应', async () => {
      const wrapper = createWrapper({ defaultExpanded: false })
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
      
      await wrapper.setProps({ defaultExpanded: true })
      await nextTick()
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
    })
  })

  // ── 5. disabled prop ─────────────────────────────────────────
  describe('5-disabled prop', () => {
    it('disabled=true 时应添加 disabled class', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.app-collapse--disabled').exists()).toBe(true)
    })

    it('disabled=true 时点击不应展开', async () => {
      const wrapper = createWrapper({ disabled: true })
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })

    it('disabled=true 时不应触发事件', async () => {
      const wrapper = createWrapper({ disabled: true })
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('change')).toBeFalsy()
      expect(wrapper.emitted('update:expanded')).toBeFalsy()
    })

    it('disabled=true 时 tabindex 应为 -1', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.app-collapse__header').attributes('tabindex')).toBe('-1')
    })

    it('disabled=false 时 tabindex 应为 0', () => {
      const wrapper = createWrapper({ disabled: false })
      expect(wrapper.find('.app-collapse__header').attributes('tabindex')).toBe('0')
    })
  })

  // ── 6. size prop ─────────────────────────────────────────────
  describe('6-size prop', () => {
    it('sm → app-collapse--sm', () => {
      const wrapper = createWrapper({ size: 'sm' })
      expect(wrapper.find('.app-collapse--sm').exists()).toBe(true)
    })

    it('md → app-collapse--md', () => {
      const wrapper = createWrapper({ size: 'md' })
      expect(wrapper.find('.app-collapse--md').exists()).toBe(true)
    })

    it('lg → app-collapse--lg', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.app-collapse--lg').exists()).toBe(true)
    })

    it('默认 size 为 md', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse--md').exists()).toBe(true)
    })
  })

  // ── 7. 点击展开/折叠 ────────────────────────────────────────
  describe('7-点击展开/折叠', () => {
    it('点击 header 应展开', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
    })

    it('再次点击应折叠', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
      
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })

    it('展开时应触发 change 事件', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('change')[0]).toEqual([true])
    })

    it('折叠时应触发 change 事件', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('change')[0]).toEqual([false])
    })

    it('展开时应触发 update:expanded 事件', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('update:expanded')).toBeTruthy()
      expect(wrapper.emitted('update:expanded')[0]).toEqual([true])
    })

    it('折叠时应触发 update:expanded 事件', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('update:expanded')).toBeTruthy()
      expect(wrapper.emitted('update:expanded')[0]).toEqual([false])
    })
  })

  // ── 8. 键盘交互 ─────────────────────────────────────────────
  describe('8-键盘交互', () => {
    it('Enter 键应展开', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('keydown.enter')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
    })

    it('Space 键应展开', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('keydown.space')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
    })

    it('disabled 时 Enter 键不应展开', async () => {
      const wrapper = createWrapper({ disabled: true })
      await wrapper.find('.app-collapse__header').trigger('keydown.enter')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })

    it('disabled 时 Space 键不应展开', async () => {
      const wrapper = createWrapper({ disabled: true })
      await wrapper.find('.app-collapse__header').trigger('keydown.space')
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })
  })

  // ── 9. arrow 图标状态 ───────────────────────────────────────
  describe('9-arrow 图标状态', () => {
    it('折叠时 arrow 不应有 expanded class', () => {
      const wrapper = createWrapper()
      const arrow = wrapper.findComponent(AppIconStub)
      expect(arrow.classes()).not.toContain('app-collapse__arrow--expanded')
    })

    it('展开时 arrow 应有 expanded class', async () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      const arrow = wrapper.findComponent(AppIconStub)
      expect(arrow.classes()).toContain('app-collapse__arrow--expanded')
    })

    it('点击后 arrow class 应切换', async () => {
      const wrapper = createWrapper()
      const arrow = wrapper.findComponent(AppIconStub)
      expect(arrow.classes()).not.toContain('app-collapse__arrow--expanded')
      
      await wrapper.find('.app-collapse__header').trigger('click')
      await nextTick()
      expect(arrow.classes()).toContain('app-collapse__arrow--expanded')
    })
  })

  // ── 10. header 插槽 ─────────────────────────────────────────
  describe('10-header 插槽', () => {
    it('应支持 header 插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { header: '<div class="custom-header">自定义头部</div>' },
      })
      expect(wrapper.find('.custom-header').exists()).toBe(true)
      expect(wrapper.find('.custom-header').text()).toBe('自定义头部')
    })

    it('header 插槽应覆盖默认内容', () => {
      const wrapper = createWrapper({ title: '原标题' }, {
        slots: { header: '<div class="custom-header">自定义头部</div>' },
      })
      expect(wrapper.find('.custom-header').exists()).toBe(true)
      expect(wrapper.find('.app-collapse__title').exists()).toBe(false)
    })
  })

  // ── 11. extra 插槽 ──────────────────────────────────────────
  describe('11-extra 插槽', () => {
    it('应支持 extra 插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { extra: '<div class="custom-extra">额外内容</div>' },
      })
      expect(wrapper.find('.app-collapse__extra').exists()).toBe(true)
      expect(wrapper.find('.custom-extra').exists()).toBe(true)
    })

    it('无 extra 插槽时不应渲染 extra 容器', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__extra').exists()).toBe(false)
    })
  })

  // ── 12. default 插槽 ────────────────────────────────────────
  describe('12-default 插槽', () => {
    it('应支持默认插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { default: '<div class="collapse-content">折叠内容</div>' },
      })
      expect(wrapper.find('.collapse-content').exists()).toBe(true)
      expect(wrapper.find('.collapse-content').text()).toBe('折叠内容')
    })

    it('折叠时内容容器应存在（v-show 控制显隐）', () => {
      const wrapper = createWrapper({}, {
        slots: { default: '<div class="collapse-content">折叠内容</div>' },
      })
      // v-show 在 happy-dom 中 isVisible() 不一定准确，检查元素存在即可
      expect(wrapper.find('.app-collapse__content').exists()).toBe(true)
      // 折叠状态时不应有 expanded class
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })

    it('展开时内容应显示', async () => {
      const wrapper = createWrapper({ defaultExpanded: true }, {
        slots: { default: '<div class="collapse-content">折叠内容</div>' },
      })
      const content = wrapper.find('.app-collapse__content')
      expect(content.isVisible()).toBe(true)
    })
  })

  // ── 13. class 计算逻辑 ──────────────────────────────────────
  describe('13-class 计算逻辑', () => {
    it('应包含基础 class', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse').exists()).toBe(true)
    })

    it('应包含 size class', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.app-collapse--lg').exists()).toBe(true)
    })

    it('展开时应添加 expanded class', () => {
      const wrapper = createWrapper({ defaultExpanded: true })
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
    })

    it('disabled 时应添加 disabled class', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.app-collapse--disabled').exists()).toBe(true)
    })
  })

  // ── 14. props 默认值 ────────────────────────────────────────
  describe('14-props 默认值', () => {
    it('title 默认为空字符串', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__title').exists()).toBe(false)
    })

    it('icon 默认为空字符串', () => {
      const wrapper = createWrapper()
      const icons = wrapper.findAllComponents(AppIconStub)
      const icon = icons.find(i => i.attributes('data-name') !== 'chevron-down')
      expect(icon).toBeFalsy()
    })

    it('iconSize 默认为 16', () => {
      const wrapper = createWrapper({ icon: 'settings' })
      const icons = wrapper.findAllComponents(AppIconStub)
      const icon = icons.find(i => i.attributes('data-name') === 'settings')
      expect(icon.attributes('data-size')).toBe('16')
    })

    it('defaultExpanded 默认为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(false)
    })

    it('disabled 默认为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse--disabled').exists()).toBe(false)
    })

    it('size 默认为 md', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse--md').exists()).toBe(true)
    })
  })

  // ── 15. 组合 props ──────────────────────────────────────────
  describe('15-组合 props', () => {
    it('应同时应用多个自定义 props', () => {
      const wrapper = createWrapper({
        title: '测试标题',
        icon: 'settings',
        iconSize: 20,
        defaultExpanded: true,
        size: 'lg',
      })
      expect(wrapper.find('.app-collapse__title').text()).toBe('测试标题')
      expect(wrapper.find('.app-collapse--lg').exists()).toBe(true)
      expect(wrapper.find('.app-collapse--expanded').exists()).toBe(true)
      
      const icons = wrapper.findAllComponents(AppIconStub)
      const icon = icons.find(i => i.attributes('data-name') === 'settings')
      expect(icon.attributes('data-size')).toBe('20')
    })
  })

  // ── 16. 边界情况 ────────────────────────────────────────────
  describe('16-边界情况', () => {
    it('所有 props 都为默认值时应正常渲染', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse').exists()).toBe(true)
    })

    it('所有插槽都提供时应正常渲染', () => {
      // 注意: extra slot 嵌套在默认 header 内容中
      // 提供 header slot 会覆盖默认内容(包括 extra)
      // 要测试 extra,需使用 title 触发默认 header 渲染
      const wrapper = createWrapper({ title: '标题' }, {
        slots: {
          default: '<div class="d">default</div>',
          extra: '<div class="e">extra</div>',
        },
      })
      expect(wrapper.find('.d').exists()).toBe(true)
      expect(wrapper.find('.e').exists()).toBe(true)
    })

    it('快速连续点击应正常处理', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('click')
      await wrapper.find('.app-collapse__header').trigger('click')
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('change')).toHaveLength(3)
    })
  })

  // ── 17. 事件完整性 ──────────────────────────────────────────
  describe('17-事件完整性', () => {
    it('应支持所有 2 个事件: change, update:expanded', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.app-collapse__header').trigger('click')
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('update:expanded')).toBeTruthy()
    })
  })

  // ── 18. 动画相关 ────────────────────────────────────────────
  describe('18-动画相关', () => {
    it('应渲染 content 容器', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__content').exists()).toBe(true)
    })

    it('应渲染 body 容器', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-collapse__body').exists()).toBe(true)
    })
  })
})
