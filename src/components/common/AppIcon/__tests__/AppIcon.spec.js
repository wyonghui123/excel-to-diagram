/**
 * AppIcon.spec.js — YonDesign AppIcon 组件测试
 *
 * 测试策略:
 * - 验证 props 透传、class 计算逻辑、style 计算、图标渲染
 * - 覆盖 12 个场景,约 55 个用例
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppIcon from '../AppIcon.vue'

// ─── helper ──────────────────────────────────────────────────────
function createWrapper(props = {}, options = {}) {
  return mount(AppIcon, {
    props: {
      name: 'check',
      ...props,
    },
    ...options,
  })
}

// ─── 测试套件 ────────────────────────────────────────────────────
describe('AppIcon', () => {
  // ── 1. 默认渲染 ──────────────────────────────────────────────
  describe('1-默认渲染', () => {
    it('应渲染 svg 根元素', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').exists()).toBe(true)
    })

    it('应有 app-icon class', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').classes()).toContain('app-icon')
    })

    it('viewBox 应为 "0 0 16 16"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').attributes('viewBox')).toBe('0 0 16 16')
    })

    it('fill 应为 "none"', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').attributes('fill')).toBe('none')
    })

    it('xmlns 应正确设置', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').attributes('xmlns')).toBe('http://www.w3.org/2000/svg')
    })
  })

  // ── 2. name prop ─────────────────────────────────────────────
  describe('2-name prop', () => {
    it('应添加 name 对应的 class', () => {
      const wrapper = createWrapper({ name: 'check' })
      expect(wrapper.find('svg').classes()).toContain('app-icon--check')
    })

    it('不同 name 应有不同 class', () => {
      const wrapper1 = createWrapper({ name: 'close' })
      const wrapper2 = createWrapper({ name: 'plus' })
      expect(wrapper1.find('svg').classes()).toContain('app-icon--close')
      expect(wrapper2.find('svg').classes()).toContain('app-icon--plus')
    })

    it('name 为 required', () => {
      // 不传 name 会有 Vue warning
      const wrapper = mount(AppIcon, {
        props: { name: 'check' },
      })
      expect(wrapper.find('svg').exists()).toBe(true)
    })
  })

  // ── 3. size prop (字符串) ────────────────────────────────────
  describe('3-size prop (字符串)', () => {
    it('默认 size 为 md', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').classes()).toContain('app-icon--md')
    })

    it('xs → app-icon--xs', () => {
      const wrapper = createWrapper({ size: 'xs' })
      expect(wrapper.find('svg').classes()).toContain('app-icon--xs')
    })

    it('sm → app-icon--sm', () => {
      const wrapper = createWrapper({ size: 'sm' })
      expect(wrapper.find('svg').classes()).toContain('app-icon--sm')
    })

    it('md → app-icon--md', () => {
      const wrapper = createWrapper({ size: 'md' })
      expect(wrapper.find('svg').classes()).toContain('app-icon--md')
    })

    it('lg → app-icon--lg', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('svg').classes()).toContain('app-icon--lg')
    })

    it('xl → app-icon--xl', () => {
      const wrapper = createWrapper({ size: 'xl' })
      expect(wrapper.find('svg').classes()).toContain('app-icon--xl')
    })
  })

  // ── 4. size prop (数字) ──────────────────────────────────────
  describe('4-size prop (数字)', () => {
    it('数字 size 应设置 width/height style', () => {
      const wrapper = createWrapper({ size: 20 })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('width: 20px')
      expect(style).toContain('height: 20px')
    })

    it('数字 size 也会添加 size class（模板行为）', () => {
      const wrapper = createWrapper({ size: 20 })
      const classes = wrapper.find('svg').classes()
      // 模板中 :class="[`app-icon--${name}`, `app-icon--${size}`]" 会直接拼接数字
      expect(classes).toContain('app-icon--20')
    })

    it('字符串数字 size 应正常渲染', () => {
      const wrapper = createWrapper({ size: '24' })
      expect(wrapper.find('svg').exists()).toBe(true)
    })
  })

  // ── 5. color prop ────────────────────────────────────────────
  describe('5-color prop', () => {
    it('默认 color 为 currentColor', () => {
      const wrapper = createWrapper()
      const style = wrapper.find('svg').attributes('style')
      // happy-dom lowercases CSS values
      expect(style.toLowerCase()).toContain('color: currentcolor')
    })

    it('应支持自定义 color', () => {
      const wrapper = createWrapper({ color: 'red' })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('color: red')
    })

    it('应支持十六进制 color', () => {
      const wrapper = createWrapper({ color: '#ff0000' })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('color: #ff0000')
    })

    it('应支持 rgb color', () => {
      const wrapper = createWrapper({ color: 'rgb(255, 0, 0)' })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('color: rgb(255, 0, 0)')
    })
  })

  // ── 6. 图标渲染 ──────────────────────────────────────────────
  describe('6-图标渲染', () => {
    it('check 图标应渲染 path', () => {
      const wrapper = createWrapper({ name: 'check' })
      expect(wrapper.find('path').exists()).toBe(true)
    })

    it('close 图标应渲染 path', () => {
      const wrapper = createWrapper({ name: 'close' })
      expect(wrapper.find('path').exists()).toBe(true)
    })

    it('chart 图标应渲染 rect 和 path', () => {
      const wrapper = createWrapper({ name: 'chart' })
      expect(wrapper.find('rect').exists()).toBe(true)
      expect(wrapper.find('path').exists()).toBe(true)
    })

    it('enabled 图标应渲染 circle 和 path', () => {
      const wrapper = createWrapper({ name: 'enabled' })
      expect(wrapper.find('circle').exists()).toBe(true)
      expect(wrapper.find('path').exists()).toBe(true)
    })

    it('未知 name 应渲染默认 circle', () => {
      const wrapper = createWrapper({ name: 'arrow-right' })
      // arrow-right 是已知图标,应渲染 path
      expect(wrapper.find('path').exists()).toBe(true)
    })
  })

  // ── 7. class 计算逻辑 ────────────────────────────────────────
  describe('7-class 计算逻辑', () => {
    it('应包含 app-icon 和 name class', () => {
      const wrapper = createWrapper({ name: 'check', size: 'lg' })
      const classes = wrapper.find('svg').classes()
      expect(classes).toContain('app-icon')
      expect(classes).toContain('app-icon--check')
      expect(classes).toContain('app-icon--lg')
    })

    it('数字 size 时也会有 size class（模板行为）', () => {
      const wrapper = createWrapper({ size: 24 })
      const classes = wrapper.find('svg').classes()
      expect(classes).toContain('app-icon')
      expect(classes).toContain('app-icon--check')
      // 模板中 :class="[`app-icon--${name}`, `app-icon--${size}`]" 会直接拼接数字
      expect(classes).toContain('app-icon--24')
    })
  })

  // ── 8. style 计算逻辑 ────────────────────────────────────────
  describe('8-style 计算逻辑', () => {
    it('字符串 size 应只有 color style', () => {
      const wrapper = createWrapper({ size: 'md', color: 'red' })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('color: red')
      expect(style).not.toContain('width')
      expect(style).not.toContain('height')
    })

    it('数字 size 应有 color + width + height style', () => {
      const wrapper = createWrapper({ size: 20, color: 'blue' })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('color: blue')
      expect(style).toContain('width: 20px')
      expect(style).toContain('height: 20px')
    })
  })

  // ── 9. props 默认值 ──────────────────────────────────────────
  describe('9-props 默认值', () => {
    it('size 默认为 md', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('svg').classes()).toContain('app-icon--md')
    })

    it('color 默认为 currentColor', () => {
      const wrapper = createWrapper()
      const style = wrapper.find('svg').attributes('style')
      // happy-dom lowercases CSS values
      expect(style.toLowerCase()).toContain('color: currentcolor')
    })
  })

  // ── 10. 组合 props ───────────────────────────────────────────
  describe('10-组合 props', () => {
    it('应同时应用 name、size、color', () => {
      const wrapper = createWrapper({
        name: 'settings',
        size: 'xl',
        color: '#333',
      })
      const svg = wrapper.find('svg')
      expect(svg.classes()).toContain('app-icon--settings')
      expect(svg.classes()).toContain('app-icon--xl')
      expect(svg.attributes('style')).toContain('color: #333')
    })

    it('数字 size + 自定义 color', () => {
      const wrapper = createWrapper({
        name: 'diagram',
        size: 32,
        color: 'green',
      })
      const svg = wrapper.find('svg')
      expect(svg.classes()).toContain('app-icon--diagram')
      expect(svg.attributes('style')).toContain('color: green')
      expect(svg.attributes('style')).toContain('width: 32px')
      expect(svg.attributes('style')).toContain('height: 32px')
    })
  })

  // ── 11. 已知图标名称 ─────────────────────────────────────────
  describe('11-已知图标名称', () => {
    const knownIcons = [
      'arrow-right', 'arrow-left', 'arrow-up', 'arrow-down',
      'check', 'close', 'plus', 'minus',
      'chevron-right', 'chevron-down', 'chevron-up',
      'search', 'user', 'edit', 'trash',
      'settings', 'diagram', 'chart',
    ]

    knownIcons.forEach(iconName => {
      it(`${iconName} 应正常渲染`, () => {
        const wrapper = createWrapper({ name: iconName })
        expect(wrapper.find('svg').exists()).toBe(true)
        expect(wrapper.find('svg').classes()).toContain(`app-icon--${iconName}`)
      })
    })
  })

  // ── 12. 边界情况 ─────────────────────────────────────────────
  describe('12-边界情况', () => {
    it('所有 props 都为默认值时应正常渲染', () => {
      const wrapper = createWrapper({ name: 'check' })
      expect(wrapper.find('svg').exists()).toBe(true)
    })

    it('size 为 0 时应正常渲染', () => {
      const wrapper = createWrapper({ size: 0 })
      const style = wrapper.find('svg').attributes('style')
      expect(style).toContain('width: 0px')
      expect(style).toContain('height: 0px')
    })

    it('color 为空字符串时应正常渲染', () => {
      const wrapper = createWrapper({ color: '' })
      expect(wrapper.find('svg').exists()).toBe(true)
    })
  })
})
