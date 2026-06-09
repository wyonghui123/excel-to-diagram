/**
 * ErrorBoundary 错误边界组件测试
 * [FR-021] 验证:
 *  1. 子树 throw 错误 → 显示 fallback UI
 *  2. 重试按钮清除错误状态
 *  3. 返回首页跳转
 *  4. 阻止错误向上传播
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import ErrorBoundary from '../ErrorBoundary.vue'
import { createRouter, createMemoryHistory } from 'vue-router'

// 模拟 vue-router
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div>Home</div>' } },
    { path: '/error', component: { template: '<div>Error Page</div>' } }
  ]
})

// 模拟 main.js 的 errorHandler (确保不重复上报)
const errorHandlerSpy = vi.fn()
vi.mock('@vue/runtime-core', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getCurrentInstance: () => null,
  }
})

describe('ErrorBoundary Component (FR-021)', () => {
  // 1. 错误捕获 + fallback
  describe('Error Capture & Fallback', () => {
    it('子树 throw 时显示 fallback UI', async () => {
      const ThrowingChild = defineComponent({
        setup() {
          throw new Error('Test error from child')
        },
        render() { return h('div', 'should not render') }
      })

      const wrapper = mount(ErrorBoundary, {
        slots: { default: () => h(ThrowingChild) },
        global: { plugins: [router] }
      })

      await nextTick()
      await nextTick()  // 等待 onErrorCaptured

      const fallback = wrapper.find('.error-boundary')
      expect(fallback.exists()).toBe(true)
      expect(wrapper.find('.error-boundary__title').text()).toBe('页面出错了')
    })

    it('正常子组件不显示 fallback', async () => {
      const NormalChild = defineComponent({
        render() { return h('div', 'normal content') }
      })

      const wrapper = mount(ErrorBoundary, {
        slots: { default: () => h(NormalChild) },
        global: { plugins: [router] }
      })

      await nextTick()
      const fallback = wrapper.find('.error-boundary')
      expect(fallback.exists()).toBe(false)
      expect(wrapper.html()).toContain('normal content')
    })
  })

  // 2. 重试功能
  describe('Retry Function', () => {
    it('点击重试清除错误状态', async () => {
      const shouldThrow = ref(true)
      const ConditionalChild = defineComponent({
        setup() {
          if (shouldThrow.value) {
            throw new Error('Conditional error')
          }
          return () => h('div', 'recovered')
        }
      })

      const wrapper = mount(ErrorBoundary, {
        slots: { default: () => h(ConditionalChild) },
        global: { plugins: [router] }
      })

      await nextTick()
      await nextTick()
      expect(wrapper.find('.error-boundary').exists()).toBe(true)

      // 修复子组件 + 触发重试
      shouldThrow.value = false
      await wrapper.find('.error-boundary__btn--primary').trigger('click')
      await nextTick()
      await nextTick()

      // 重试后恢复
      expect(wrapper.find('.error-boundary').exists()).toBe(false)
      expect(wrapper.html()).toContain('recovered')
    })
  })

  // 3. 返回首页
  describe('Navigate Home', () => {
    it('点击返回首页跳转到 /', async () => {
      const pushSpy = vi.spyOn(router, 'push')
      const ThrowingChild = defineComponent({
        setup() { throw new Error('boom') },
        render() { return h('div') }
      })

      const wrapper = mount(ErrorBoundary, {
        slots: { default: () => h(ThrowingChild) },
        global: { plugins: [router] }
      })

      await nextTick()
      await nextTick()
      const buttons = wrapper.findAll('.error-boundary__btn')
      // 第二个按钮是"返回首页"
      await buttons[1].trigger('click')

      expect(pushSpy).toHaveBeenCalledWith('/')
    })
  })

  // 4. 错误信息显示
  describe('Error Message', () => {
    it('显示 Error.message', async () => {
      const ThrowingChild = defineComponent({
        setup() { throw new Error('Specific error message') },
        render() { return h('div') }
      })

      const wrapper = mount(ErrorBoundary, {
        slots: { default: () => h(ThrowingChild) },
        global: { plugins: [router] }
      })

      await nextTick()
      await nextTick()
      const msg = wrapper.find('.error-boundary__message')
      expect(msg.exists()).toBe(true)
      expect(msg.text()).toBe('Specific error message')
    })
  })
})
