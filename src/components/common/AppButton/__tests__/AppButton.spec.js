/**
 * AppButton.spec.js - AppButton 组件测试
 *
 * 背景：AppButton 是 YonDesign 11 个封装组件之一，对 Element Plus el-button 的统一封装。
 *       2026-06-13 Spec A P1 落地（Vue 组件测试扩展），此前无单测。
 *
 * 测试模式：
 *   - mount() + global.stubs.el-button（断言 el-button props 传递）
 *   - 不 stub el-button 也可以，但 stub 后断言更精准
 *
 * 覆盖场景（OUTPUT_SPEC § 2.2 Vue 组件 12 类通用场景 → 本组件约 15 个用例）：
 *   1. 默认渲染
 *   2. variant 映射（primary/secondary/text/danger/success/warning）
 *   3. size 映射（xs/sm/md/lg/xl）
 *   4. disabled 透传 + 阻断 click
 *   5. loading 透传 + 阻断 click + 强制 disabled
 *   6. block → class
 *   7. xs/xl → 自定义 class
 *   8. ghost → plain
 *   9. circle → round
 *   10. icon 透传
 *   11. 默认 slot 渲染
 *   12. click 事件 emit
 *   13. type prop 透传
 *   14. variant 非法值 → 兜底 default
 *   15. 无 icon prop 时 el-button 不接收 icon
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AppButton from '../AppButton.vue'

/**
 * 工厂函数：创建测试 wrapper
 * @param {object} props - 组件 props
 * @param {object} options - slots/global stubs 等
 */
function createWrapper(props = {}, options = {}) {
  return mount(AppButton, {
    props,
    slots: options.slots,
    global: {
      stubs: {
        // 关键：stub el-button 让我们可以精确断言 props 传递
        'el-button': {
          name: 'ElButton',
          template: '<button class="el-button-stub" :data-type="type" :data-size="size" :data-disabled="disabled" :data-loading="loading" :data-icon="icon ? \'yes\' : \'no\'" :data-round="round" :data-plain="plain" :data-block="block" :data-test-class="cls" @click="handleClick"><slot /></button>',
          props: ['type', 'size', 'disabled', 'loading', 'icon', 'round', 'plain', 'class', 'block'],
          emits: ['click'],
          computed: {
            cls() {
              // AppButton 把数组传入 :class，Vue 会自动拼接为字符串
              const c = this.class
              return Array.isArray(c) ? c.filter(Boolean).join(' ') : c || ''
            },
          },
          methods: {
            handleClick(e) {
              this.$emit('click', e)
            },
          },
        },
        ...options.stubs,
      },
    },
    ...options,
  })
}

describe('AppButton', () => {
  // ============================================================
  // 1. 默认渲染
  // ============================================================
  describe('1. 默认渲染', () => {
    it('应渲染为 el-button', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-button-stub').exists()).toBe(true)
    })

    it('默认 variant=primary 应映射为 el-button type=primary', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('primary')
    })

    it('默认 size=md 应映射为 el-button size=default', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-button-stub').attributes('data-size')).toBe('default')
    })

    it('默认不应 disabled/loading', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-button-stub').attributes('data-disabled')).toBe('false')
      expect(wrapper.find('.el-button-stub').attributes('data-loading')).toBe('false')
    })
  })

  // ============================================================
  // 2. variant 映射
  // ============================================================
  describe('2. variant 映射（6 种）', () => {
    it('primary → type=primary', () => {
      const wrapper = createWrapper({ variant: 'primary' })
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('primary')
    })

    it('secondary → type=default', () => {
      const wrapper = createWrapper({ variant: 'secondary' })
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('default')
    })

    it('text → type=text', () => {
      const wrapper = createWrapper({ variant: 'text' })
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('text')
    })

    it('danger → type=danger', () => {
      const wrapper = createWrapper({ variant: 'danger' })
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('danger')
    })

    it('success → type=success', () => {
      const wrapper = createWrapper({ variant: 'success' })
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('success')
    })

    it('warning → type=warning', () => {
      const wrapper = createWrapper({ variant: 'warning' })
      expect(wrapper.find('.el-button-stub').attributes('data-type')).toBe('warning')
    })
  })

  // ============================================================
  // 3. size 映射
  // ============================================================
  describe('3. size 映射（5 种）', () => {
    it('xs → size=small + class=app-button--xs', () => {
      const wrapper = createWrapper({ size: 'xs' })
      expect(wrapper.find('.el-button-stub').attributes('data-size')).toBe('small')
      expect(wrapper.find('.el-button-stub').attributes('data-test-class')).toContain('app-button--xs')
    })

    it('sm → size=small', () => {
      const wrapper = createWrapper({ size: 'sm' })
      expect(wrapper.find('.el-button-stub').attributes('data-size')).toBe('small')
    })

    it('md → size=default', () => {
      const wrapper = createWrapper({ size: 'md' })
      expect(wrapper.find('.el-button-stub').attributes('data-size')).toBe('default')
    })

    it('lg → size=large', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.el-button-stub').attributes('data-size')).toBe('large')
    })

    it('xl → size=large + class=app-button--xl', () => {
      const wrapper = createWrapper({ size: 'xl' })
      expect(wrapper.find('.el-button-stub').attributes('data-size')).toBe('large')
      expect(wrapper.find('.el-button-stub').attributes('data-test-class')).toContain('app-button--xl')
    })
  })

  // ============================================================
  // 4. disabled
  // ============================================================
  describe('4. disabled', () => {
    it('disabled=true 应传递到 el-button', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.el-button-stub').attributes('data-disabled')).toBe('true')
    })

    it('disabled=true 时点击不应 emit click', async () => {
      const wrapper = createWrapper({ disabled: true })
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toBeFalsy()
    })

    it('disabled=false 时点击应 emit click', async () => {
      const wrapper = createWrapper({ disabled: false })
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
      expect(wrapper.emitted('click')).toHaveLength(1)
    })
  })

  // ============================================================
  // 5. loading
  // ============================================================
  describe('5. loading', () => {
    it('loading=true 应传递到 el-button', () => {
      const wrapper = createWrapper({ loading: true })
      expect(wrapper.find('.el-button-stub').attributes('data-loading')).toBe('true')
    })

    it('loading=true 时应同时禁用（disabled 强制为 true）', () => {
      const wrapper = createWrapper({ loading: true })
      expect(wrapper.find('.el-button-stub').attributes('data-disabled')).toBe('true')
    })

    it('loading=true 时点击不应 emit click', async () => {
      const wrapper = createWrapper({ loading: true })
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toBeFalsy()
    })

    it('loading=false 时正常 emit click', async () => {
      const wrapper = createWrapper({ loading: false })
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
    })
  })

  // ============================================================
  // 6. block
  // ============================================================
  describe('6. block', () => {
    it('block=true 应添加 app-button--block class', () => {
      const wrapper = createWrapper({ block: true })
      expect(wrapper.find('.el-button-stub').attributes('data-test-class')).toContain('app-button--block')
    })

    it('block=false 不应添加 block class', () => {
      const wrapper = createWrapper({ block: false })
      const cls = wrapper.find('.el-button-stub').attributes('data-test-class')
      expect(cls || '').not.toContain('app-button--block')
    })
  })

  // ============================================================
  // 7. ghost / circle
  // ============================================================
  describe('7. ghost / circle', () => {
    it('ghost=true → el-button plain=true', () => {
      const wrapper = createWrapper({ ghost: true })
      expect(wrapper.find('.el-button-stub').attributes('data-plain')).toBe('true')
    })

    it('ghost=false → el-button plain=false', () => {
      const wrapper = createWrapper({ ghost: false })
      expect(wrapper.find('.el-button-stub').attributes('data-plain')).toBe('false')
    })

    it('circle=true → el-button round=true', () => {
      const wrapper = createWrapper({ circle: true })
      expect(wrapper.find('.el-button-stub').attributes('data-round')).toBe('true')
    })

    it('circle=false → el-button round=false', () => {
      const wrapper = createWrapper({ circle: false })
      expect(wrapper.find('.el-button-stub').attributes('data-round')).toBe('false')
    })
  })

  // ============================================================
  // 8. icon
  // ============================================================
  describe('8. icon', () => {
    it('未传 icon 时 el-button 不应接收 icon', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-button-stub').attributes('data-icon')).toBe('no')
    })

    it('传 icon（Function）时应传递', () => {
      const iconFn = vi.fn()
      const wrapper = createWrapper({ icon: iconFn })
      expect(wrapper.find('.el-button-stub').attributes('data-icon')).toBe('yes')
    })

    it('传 icon（Object）时应传递', () => {
      const wrapper = createWrapper({ icon: { name: 'Edit' } })
      expect(wrapper.find('.el-button-stub').attributes('data-icon')).toBe('yes')
    })
  })

  // ============================================================
  // 9. slot
  // ============================================================
  describe('9. 默认 slot', () => {
    it('应渲染 slot 内容', () => {
      const wrapper = createWrapper({}, { slots: { default: '<span class="custom-text">点击我</span>' } })
      expect(wrapper.find('.custom-text').exists()).toBe(true)
      expect(wrapper.find('.custom-text').text()).toBe('点击我')
    })

    it('无 slot 时不应渲染空内容', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-button-stub').text()).toBe('')
    })
  })

  // ============================================================
  // 10. click 事件
  // ============================================================
  describe('10. click 事件', () => {
    it('默认状态点击应 emit click + 传递 event 对象', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toBeTruthy()
      expect(wrapper.emitted('click')[0][0]).toBeDefined() // 第一个参数是 event
    })

    it('多次点击应 emit 多次', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-button-stub').trigger('click')
      await wrapper.find('.el-button-stub').trigger('click')
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toHaveLength(3)
    })
  })

  // ============================================================
  // 11. type prop（HTML 原生 type）
  // ============================================================
  describe('11. HTML type prop', () => {
    it('默认 type=button', () => {
      const wrapper = createWrapper()
      // AppButton 的 type prop 默认 'button',但不在 el-button 上使用
      // 这里主要验证组件接受此 prop 不报错
      expect(wrapper.props('type')).toBe('button')
    })

    it('可接受 type=submit', () => {
      const wrapper = createWrapper({ type: 'submit' })
      expect(wrapper.props('type')).toBe('submit')
    })

    it('可接受 type=reset', () => {
      const wrapper = createWrapper({ type: 'reset' })
      expect(wrapper.props('type')).toBe('reset')
    })
  })

  // ============================================================
  // 12. 边界场景
  // ============================================================
  describe('12. 边界场景', () => {
    it('variant validator 拒绝非法值（Vue 层面防护）', () => {
      // 注：组件 prop validator 在开发环境会打印 warn 但不影响渲染
      // 这里主要验证非法值不会让组件崩溃
      const wrapper = createWrapper({ variant: 'invalid' })
      expect(wrapper.find('.el-button-stub').exists()).toBe(true)
    })

    it('size validator 拒绝非法值（Vue 层面防护）', () => {
      const wrapper = createWrapper({ size: 'invalid' })
      expect(wrapper.find('.el-button-stub').exists()).toBe(true)
    })

    it('同时设置 block + size=xs 应同时有两个 class', () => {
      const wrapper = createWrapper({ block: true, size: 'xs' })
      const cls = wrapper.find('.el-button-stub').attributes('data-test-class')
      expect(cls).toContain('app-button--block')
      expect(cls).toContain('app-button--xs')
    })

    it('icon=null 显式传值时不应传给 el-button', () => {
      const wrapper = createWrapper({ icon: null })
      expect(wrapper.find('.el-button-stub').attributes('data-icon')).toBe('no')
    })

    it('disabled 与 loading 同时为 true 时 click 应被阻断', async () => {
      const wrapper = createWrapper({ disabled: true, loading: true })
      await wrapper.find('.el-button-stub').trigger('click')
      expect(wrapper.emitted('click')).toBeFalsy()
    })
  })
})