/**
 * AppAlert.spec.js - AppAlert 组件测试
 *
 * 背景：AppAlert 是 YonDesign 提示组件，支持 info/success/warning/error 四种类型。
 *
 * 覆盖场景：
 *   1. 默认渲染
 *   2. type prop（info/success/warning/error）
 *   3. showIcon prop
 *   4. 默认 slot
 *   5. props 默认值
 *   6. role 属性
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppAlert from '../AppAlert.vue'

function createWrapper(props = {}, slots = {}) {
  return mount(AppAlert, { props, slots })
}

describe('AppAlert', () => {
  // --- 1. 默认渲染 ---
  it('默认渲染', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-alert').exists()).toBe(true)
  })

  // --- 2. type prop ---
  it.each(['info', 'success', 'warning', 'error'])(
    'type=%s 添加对应 class',
    (type) => {
      const wrapper = createWrapper({ type })
      expect(wrapper.classes()).toContain(`app-alert--${type}`)
    }
  )

  it('默认 type 为 info', () => {
    const wrapper = createWrapper()
    expect(wrapper.classes()).toContain('app-alert--info')
  })

  // --- 3. showIcon ---
  it('默认 showIcon=true 渲染图标', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('.app-alert__icon').exists()).toBe(true)
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('showIcon=false 不渲染图标', () => {
    const wrapper = createWrapper({ showIcon: false })
    expect(wrapper.find('.app-alert__icon').exists()).toBe(false)
  })

  // --- 4. 默认 slot ---
  it('默认 slot 渲染内容', () => {
    const wrapper = createWrapper({}, {
      default: '提示信息',
    })
    expect(wrapper.find('.app-alert__content').text()).toBe('提示信息')
  })

  it('slot 支持 HTML', () => {
    const wrapper = createWrapper({}, {
      default: '<strong>加粗</strong>',
    })
    expect(wrapper.find('strong').exists()).toBe(true)
  })

  // --- 5. 组合 props ---
  it('type=success + showIcon=false', () => {
    const wrapper = createWrapper({ type: 'success', showIcon: false })
    expect(wrapper.classes()).toContain('app-alert--success')
    expect(wrapper.find('.app-alert__icon').exists()).toBe(false)
  })

  it('type=error + showIcon=true', () => {
    const wrapper = createWrapper({ type: 'error', showIcon: true })
    expect(wrapper.classes()).toContain('app-alert--error')
    expect(wrapper.find('.app-alert__icon').exists()).toBe(true)
  })

  // --- 6. role 属性 ---
  it('role=alert', () => {
    const wrapper = createWrapper()
    expect(wrapper.attributes('role')).toBe('alert')
  })

  // --- 7. 不同 type 渲染不同图标 ---
  it.each(['info', 'success', 'warning', 'error'])(
    'type=%s 渲染对应 SVG 图标',
    (type) => {
      const wrapper = createWrapper({ type })
      const svg = wrapper.find('.app-alert__icon svg')
      expect(svg.exists()).toBe(true)
    }
  )
})
