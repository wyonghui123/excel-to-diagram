/**
 * AppCard.spec.js — YonDesign AppCard 组件测试
 *
 * 测试策略:
 * - 验证 props 透传、class 计算逻辑、插槽渲染、事件触发条件
 * - 覆盖 19 个场景,约 68 个用例
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AppCard from '../AppCard.vue'

// ─── helper ──────────────────────────────────────────────────────
function createWrapper(props = {}, options = {}) {
  return mount(AppCard, {
    props,
    slots: options.slots,
    ...options,
  })
}

// ─── 测试套件 ────────────────────────────────────────────────────
describe('AppCard', () => {
  // ── 1. 默认渲染 ──────────────────────────────────────────────
  describe('1-默认渲染', () => {
    it('应渲染 app-card 根元素', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').exists()).toBe(true)
    })

    it('应渲染 app-card__body', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card__body').exists()).toBe(true)
    })

    it('默认 size 为 md', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).toContain('app-card--md')
    })

    it('默认 shadow 为 sm', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).toContain('app-card--shadow-sm')
    })

    it('默认 border 为 default', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).toContain('app-card--border-default')
    })

    it('默认 radius 为 md', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).toContain('app-card--radius-md')
    })

    it('默认 hoverable 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--hoverable')
    })

    it('默认 clickable 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--clickable')
    })

    it('默认 disabled 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--disabled')
    })

    it('默认 loading 为 false', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--loading')
    })
  })

  // ── 2. title / subtitle ──────────────────────────────────────
  describe('2-title / subtitle', () => {
    it('应渲染 title', () => {
      const wrapper = createWrapper({ title: '卡片标题' })
      expect(wrapper.find('.app-card__title').exists()).toBe(true)
      expect(wrapper.find('.app-card__title').text()).toBe('卡片标题')
    })

    it('应渲染 subtitle', () => {
      const wrapper = createWrapper({ title: '标题', subtitle: '副标题' })
      expect(wrapper.find('.app-card__subtitle').exists()).toBe(true)
      expect(wrapper.find('.app-card__subtitle').text()).toBe('副标题')
    })

    it('有 title 时应渲染 header', () => {
      const wrapper = createWrapper({ title: '标题' })
      expect(wrapper.find('.app-card__header').exists()).toBe(true)
    })

    it('无 title 且无 header slot 时不应渲染 header', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card__header').exists()).toBe(false)
    })

    it('有 header slot 时应渲染 header', () => {
      const wrapper = createWrapper({}, {
        slots: { header: '<div class="custom-header">自定义头部</div>' },
      })
      expect(wrapper.find('.app-card__header').exists()).toBe(true)
      expect(wrapper.find('.custom-header').exists()).toBe(true)
    })

    it('无 subtitle 时不应渲染 subtitle 元素', () => {
      const wrapper = createWrapper({ title: '标题' })
      expect(wrapper.find('.app-card__subtitle').exists()).toBe(false)
    })
  })

  // ── 3. size 变体 ─────────────────────────────────────────────
  describe('3-size 变体', () => {
    it('sm → app-card--sm', () => {
      const wrapper = createWrapper({ size: 'sm' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--sm')
    })

    it('md → app-card--md', () => {
      const wrapper = createWrapper({ size: 'md' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--md')
    })

    it('lg → app-card--lg', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--lg')
    })

    it('body 应有对应 size class', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.app-card__body').classes()).toContain('app-card__body--lg')
    })
  })

  // ── 4. shadow 变体 ───────────────────────────────────────────
  describe('4-shadow 变体', () => {
    it('none → app-card--shadow-none', () => {
      const wrapper = createWrapper({ shadow: 'none' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--shadow-none')
    })

    it('sm → app-card--shadow-sm', () => {
      const wrapper = createWrapper({ shadow: 'sm' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--shadow-sm')
    })

    it('md → app-card--shadow-md', () => {
      const wrapper = createWrapper({ shadow: 'md' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--shadow-md')
    })

    it('lg → app-card--shadow-lg', () => {
      const wrapper = createWrapper({ shadow: 'lg' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--shadow-lg')
    })
  })

  // ── 5. border 变体 ───────────────────────────────────────────
  describe('5-border 变体', () => {
    it('default → app-card--border-default', () => {
      const wrapper = createWrapper({ border: 'default' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--border-default')
    })

    it('primary → app-card--border-primary', () => {
      const wrapper = createWrapper({ border: 'primary' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--border-primary')
    })

    it('success → app-card--border-success', () => {
      const wrapper = createWrapper({ border: 'success' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--border-success')
    })

    it('warning → app-card--border-warning', () => {
      const wrapper = createWrapper({ border: 'warning' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--border-warning')
    })

    it('error → app-card--border-error', () => {
      const wrapper = createWrapper({ border: 'error' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--border-error')
    })
  })

  // ── 6. radius 变体 ───────────────────────────────────────────
  describe('6-radius 变体', () => {
    it('none → app-card--radius-none', () => {
      const wrapper = createWrapper({ radius: 'none' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--radius-none')
    })

    it('sm → app-card--radius-sm', () => {
      const wrapper = createWrapper({ radius: 'sm' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--radius-sm')
    })

    it('md → app-card--radius-md', () => {
      const wrapper = createWrapper({ radius: 'md' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--radius-md')
    })

    it('lg → app-card--radius-lg', () => {
      const wrapper = createWrapper({ radius: 'lg' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--radius-lg')
    })

    it('xl → app-card--radius-xl', () => {
      const wrapper = createWrapper({ radius: 'xl' })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--radius-xl')
    })
  })

  // ── 7. hoverable ─────────────────────────────────────────────
  describe('7-hoverable', () => {
    it('hoverable=true 应添加 hoverable class', () => {
      const wrapper = createWrapper({ hoverable: true })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--hoverable')
    })

    it('hoverable=false 不应添加 hoverable class', () => {
      const wrapper = createWrapper({ hoverable: false })
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--hoverable')
    })
  })

  // ── 8. clickable ─────────────────────────────────────────────
  describe('8-clickable', () => {
    it('clickable=true 应添加 clickable class', () => {
      const wrapper = createWrapper({ clickable: true })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--clickable')
    })

    it('clickable=false 不应添加 clickable class', () => {
      const wrapper = createWrapper({ clickable: false })
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--clickable')
    })
  })

  // ── 9. disabled ──────────────────────────────────────────────
  describe('9-disabled', () => {
    it('disabled=true 应添加 disabled class', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--disabled')
    })

    it('disabled=false 不应添加 disabled class', () => {
      const wrapper = createWrapper({ disabled: false })
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--disabled')
    })
  })

  // ── 10. loading ──────────────────────────────────────────────
  describe('10-loading', () => {
    it('loading=true 应添加 loading class', () => {
      const wrapper = createWrapper({ loading: true })
      expect(wrapper.find('.app-card').classes()).toContain('app-card--loading')
    })

    it('loading=false 不应添加 loading class', () => {
      const wrapper = createWrapper({ loading: false })
      expect(wrapper.find('.app-card').classes()).not.toContain('app-card--loading')
    })
  })

  // ── 11. header slot ──────────────────────────────────────────
  describe('11-header slot', () => {
    it('应支持 header 插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { header: '<div class="custom-header">自定义头部</div>' },
      })
      expect(wrapper.find('.custom-header').exists()).toBe(true)
      expect(wrapper.find('.custom-header').text()).toBe('自定义头部')
    })

    it('header slot 应覆盖 title/subtitle', () => {
      const wrapper = createWrapper({ title: '原标题' }, {
        slots: { header: '<div class="custom-header">自定义头部</div>' },
      })
      expect(wrapper.find('.custom-header').exists()).toBe(true)
      expect(wrapper.find('.app-card__title').exists()).toBe(false)
    })
  })

  // ── 12. footer slot ──────────────────────────────────────────
  describe('12-footer slot', () => {
    it('应支持 footer 插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { footer: '<div class="custom-footer">底部内容</div>' },
      })
      expect(wrapper.find('.app-card__footer').exists()).toBe(true)
      expect(wrapper.find('.custom-footer').exists()).toBe(true)
      expect(wrapper.find('.custom-footer').text()).toBe('底部内容')
    })

    it('无 footer slot 时不应渲染 footer', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card__footer').exists()).toBe(false)
    })
  })

  // ── 13. extra slot ───────────────────────────────────────────
  describe('13-extra slot', () => {
    it('应支持 extra 插槽', () => {
      const wrapper = createWrapper({ title: '标题' }, {
        slots: { extra: '<div class="custom-extra">额外内容</div>' },
      })
      expect(wrapper.find('.app-card__extra').exists()).toBe(true)
      expect(wrapper.find('.custom-extra').exists()).toBe(true)
      expect(wrapper.find('.custom-extra').text()).toBe('额外内容')
    })

    it('无 extra slot 时不应渲染 extra 容器', () => {
      const wrapper = createWrapper({ title: '标题' })
      expect(wrapper.find('.app-card__extra').exists()).toBe(false)
    })
  })

  // ── 14. default slot ─────────────────────────────────────────
  describe('14-default slot', () => {
    it('应支持默认插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { default: '<div class="card-content">卡片内容</div>' },
      })
      expect(wrapper.find('.card-content').exists()).toBe(true)
      expect(wrapper.find('.card-content').text()).toBe('卡片内容')
    })
  })

  // ── 15. click 事件 ───────────────────────────────────────────
  describe('15-click 事件', () => {
    it('clickable=true 时点击应 emit click', async () => {
      const wrapper = createWrapper({ clickable: true })
      await wrapper.find('.app-card').trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
      expect(wrapper.emitted('click')).toHaveLength(1)
    })

    it('clickable=false 时点击不应 emit click', async () => {
      const wrapper = createWrapper({ clickable: false })
      await wrapper.find('.app-card').trigger('click')
      expect(wrapper.emitted('click')).toBeFalsy()
    })

    it('disabled=true 时点击不应 emit click', async () => {
      const wrapper = createWrapper({ clickable: true, disabled: true })
      await wrapper.find('.app-card').trigger('click')
      expect(wrapper.emitted('click')).toBeFalsy()
    })

    it('loading=true 时点击不应 emit click', async () => {
      const wrapper = createWrapper({ clickable: true, loading: true })
      await wrapper.find('.app-card').trigger('click')
      expect(wrapper.emitted('click')).toBeFalsy()
    })

    it('click 事件应传递 event 对象', async () => {
      const wrapper = createWrapper({ clickable: true })
      await wrapper.find('.app-card').trigger('click')
      expect(wrapper.emitted('click')[0][0]).toBeInstanceOf(Event)
    })
  })

  // ── 16. class 计算逻辑 ───────────────────────────────────────
  describe('16-class 计算逻辑', () => {
    it('应包含所有必需的 class', () => {
      const wrapper = createWrapper({
        size: 'lg',
        shadow: 'md',
        border: 'primary',
        radius: 'xl',
        hoverable: true,
        clickable: true,
      })
      const classes = wrapper.find('.app-card').classes()
      expect(classes).toContain('app-card')
      expect(classes).toContain('app-card--lg')
      expect(classes).toContain('app-card--shadow-md')
      expect(classes).toContain('app-card--border-primary')
      expect(classes).toContain('app-card--radius-xl')
      expect(classes).toContain('app-card--hoverable')
      expect(classes).toContain('app-card--clickable')
    })
  })

  // ── 17. props 默认值 ─────────────────────────────────────────
  describe('17-props 默认值', () => {
    it('title 默认为空字符串', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card__title').exists()).toBe(false)
    })

    it('subtitle 默认为空字符串', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card__subtitle').exists()).toBe(false)
    })
  })

  // ── 18. 组合 props ───────────────────────────────────────────
  describe('18-组合 props', () => {
    it('应同时应用多个自定义 props', () => {
      const wrapper = createWrapper({
        title: '测试卡片',
        subtitle: '副标题',
        size: 'lg',
        shadow: 'lg',
        border: 'success',
        radius: 'xl',
        hoverable: true,
        clickable: true,
        disabled: false,
        loading: false,
      })
      const card = wrapper.find('.app-card')
      expect(card.classes()).toContain('app-card--lg')
      expect(card.classes()).toContain('app-card--shadow-lg')
      expect(card.classes()).toContain('app-card--border-success')
      expect(card.classes()).toContain('app-card--radius-xl')
      expect(card.classes()).toContain('app-card--hoverable')
      expect(card.classes()).toContain('app-card--clickable')
      expect(wrapper.find('.app-card__title').text()).toBe('测试卡片')
      expect(wrapper.find('.app-card__subtitle').text()).toBe('副标题')
    })
  })

  // ── 19. 边界情况 ─────────────────────────────────────────────
  describe('19-边界情况', () => {
    it('所有 props 都为默认值时应正常渲染', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-card').exists()).toBe(true)
    })

    it('disabled + loading 同时为 true 时应正常渲染', () => {
      const wrapper = createWrapper({ disabled: true, loading: true })
      const classes = wrapper.find('.app-card').classes()
      expect(classes).toContain('app-card--disabled')
      expect(classes).toContain('app-card--loading')
    })

    it('所有插槽都提供时应正常渲染', () => {
      // 注意: extra slot 嵌套在 header slot 的默认内容中
      // 提供 header slot 会覆盖默认内容(包括 extra),所以 extra 不渲染
      // 要测试 extra,需使用 title 触发默认 header 渲染
      const wrapper = createWrapper({ title: '标题' }, {
        slots: {
          default: '<div class="d">default</div>',
          footer: '<div class="f">footer</div>',
          extra: '<div class="e">extra</div>',
        },
      })
      expect(wrapper.find('.d').exists()).toBe(true)
      expect(wrapper.find('.f').exists()).toBe(true)
      expect(wrapper.find('.e').exists()).toBe(true)
    })
  })
})
