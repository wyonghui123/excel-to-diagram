/**
 * AppInput.spec.js - AppInput 组件测试
 *
 * 背景：AppInput 是 YonDesign 封装组件之一，对 Element Plus el-input 的统一封装。
 *       2026-06-13 Spec A P1 落地（Vue 组件测试扩展），此前无单测。
 *
 * 测试模式：mount() + global.stubs.el-input
 *
 * 覆盖场景（18 类）：
 *   1. 默认渲染
 *   2. v-model 双向绑定
 *   3. label + required 标记
 *   4. error 显示（error 优先于 hint）
 *   5. hint 显示（无 error 时）
 *   6. size 映射 (sm/md/lg)
 *   7. disabled 透传 + wrapper class
 *   8. readonly 透传
 *   9. clearable 透传
 *   10. type 透传 (text/password/number)
 *   11. showPasswordToggle
 *   12. prefix/suffix slot
 *   13. focus/blur 事件 + isFocused class
 *   14. change/clear/keydown 事件
 *   15. maxlength/min/max/step 透传
 *   16. prefixIcon/suffixIcon 透传
 *   17. wrapper classes 组合
 *   18. inputId 生成
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AppInput from '../AppInput.vue'

/**
 * 工厂函数：创建测试 wrapper
 */
function createWrapper(props = {}, options = {}) {
  return mount(AppInput, {
    props,
    slots: options.slots,
    global: {
      stubs: {
        'el-input': {
          name: 'ElInput',
          template: `
            <div class="el-input-stub"
              :data-model-value="modelValue"
              :data-type="type"
              :data-placeholder="placeholder"
              :data-disabled="disabled"
              :data-readonly="readonly"
              :data-maxlength="maxlength"
              :data-min="min"
              :data-max="max"
              :data-step="step"
              :data-autocomplete="autocomplete"
              :data-autofocus="autofocus"
              :data-name="name"
              :data-id="id"
              :data-size="size"
              :data-clearable="clearable"
              :data-show-password="showPassword"
              :data-prefix-icon="prefixIcon ? 'yes' : 'no'"
              :data-suffix-icon="suffixIcon ? 'yes' : 'no'"
            >
              <slot name="prefix" />
              <slot name="suffix" />
              <button class="el-input-stub__input" @input="onInput" @focus="onFocus" @blur="onBlur" @change="onChange" @keydown="onKeydown" @clear="onClear" />
            </div>
          `,
          props: [
            'modelValue', 'type', 'placeholder', 'disabled', 'readonly',
            'maxlength', 'min', 'max', 'step', 'autocomplete', 'autofocus',
            'name', 'id', 'size', 'clearable', 'showPassword',
            'prefixIcon', 'suffixIcon',
          ],
          emits: ['update:modelValue', 'focus', 'blur', 'change', 'keydown', 'clear'],
          methods: {
            onInput() { this.$emit('update:modelValue', 'new-value') },
            onFocus(e) { this.$emit('focus', e) },
            onBlur(e) { this.$emit('blur', e) },
            onChange() { this.$emit('change', 'changed-value') },
            onKeydown(e) { this.$emit('keydown', e) },
            onClear() { this.$emit('clear') },
          },
        },
        ...options.stubs,
      },
    },
    ...options,
  })
}

describe('AppInput', () => {
  // ============================================================
  // 1. 默认渲染
  // ============================================================
  describe('1. 默认渲染', () => {
    it('应渲染 wrapper.app-input', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-input').exists()).toBe(true)
    })

    it('应渲染 el-input-stub', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-input-stub').exists()).toBe(true)
    })

    it('默认 modelValue 应为空字符串', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-input-stub').attributes('data-model-value')).toBe('')
    })

    it('默认 type 应为 text', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-input-stub').attributes('data-type')).toBe('text')
    })

    it('默认不应有 label', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-input__label').exists()).toBe(false)
    })

    it('默认不应有 error/hint', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.app-input__error').exists()).toBe(false)
      expect(wrapper.find('.app-input__hint').exists()).toBe(false)
    })
  })

  // ============================================================
  // 2. v-model 双向绑定
  // ============================================================
  describe('2. v-model 双向绑定', () => {
    it('应传递 modelValue 到 el-input', () => {
      const wrapper = createWrapper({ modelValue: 'hello' })
      expect(wrapper.find('.el-input-stub').attributes('data-model-value')).toBe('hello')
    })

    it('el-input 输入时应 emit update:modelValue', async () => {
      const wrapper = createWrapper({ modelValue: '' })
      await wrapper.find('.el-input-stub__input').trigger('input')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0][0]).toBe('new-value')
    })

    it('el-input 输入时应同时 emit input', async () => {
      const wrapper = createWrapper({ modelValue: '' })
      await wrapper.find('.el-input-stub__input').trigger('input')
      expect(wrapper.emitted('input')).toBeTruthy()
      expect(wrapper.emitted('input')[0][0]).toBe('new-value')
    })

    it('应支持 Number 类型 modelValue', () => {
      const wrapper = createWrapper({ modelValue: 42 })
      expect(wrapper.find('.el-input-stub').attributes('data-model-value')).toBe('42')
    })
  })

  // ============================================================
  // 3. label + required
  // ============================================================
  describe('3. label + required', () => {
    it('传 label 时应渲染 label 元素', () => {
      const wrapper = createWrapper({ label: '用户名' })
      expect(wrapper.find('.app-input__label').exists()).toBe(true)
      expect(wrapper.find('.app-input__label').text()).toContain('用户名')
    })

    it('required=true 时应显示 * 标记', () => {
      const wrapper = createWrapper({ label: '用户名', required: true })
      expect(wrapper.find('.app-input__required').exists()).toBe(true)
      expect(wrapper.find('.app-input__required').text()).toBe('*')
    })

    it('required=false 时不应显示 * 标记', () => {
      const wrapper = createWrapper({ label: '用户名', required: false })
      expect(wrapper.find('.app-input__required').exists()).toBe(false)
    })

    it('无 label 时即使 required=true 也不显示 label', () => {
      const wrapper = createWrapper({ required: true })
      expect(wrapper.find('.app-input__label').exists()).toBe(false)
    })
  })

  // ============================================================
  // 4. error 显示
  // ============================================================
  describe('4. error 显示', () => {
    it('传 error 时应渲染 error 元素', () => {
      const wrapper = createWrapper({ error: '必填项' })
      expect(wrapper.find('.app-input__error').exists()).toBe(true)
      expect(wrapper.find('.app-input__error').text()).toBe('必填项')
    })

    it('有 error 时不应显示 hint（error 优先）', () => {
      const wrapper = createWrapper({ error: '必填项', hint: '请输入用户名' })
      expect(wrapper.find('.app-input__error').exists()).toBe(true)
      expect(wrapper.find('.app-input__hint').exists()).toBe(false)
    })

    it('有 error 时 wrapper 应添加 app-input--error class', () => {
      const wrapper = createWrapper({ error: '必填项' })
      expect(wrapper.find('.app-input--error').exists()).toBe(true)
    })
  })

  // ============================================================
  // 5. hint 显示
  // ============================================================
  describe('5. hint 显示', () => {
    it('传 hint（无 error）时应渲染 hint 元素', () => {
      const wrapper = createWrapper({ hint: '请输入用户名' })
      expect(wrapper.find('.app-input__hint').exists()).toBe(true)
      expect(wrapper.find('.app-input__hint').text()).toBe('请输入用户名')
    })

    it('同时有 error 和 hint 时应只显示 error', () => {
      const wrapper = createWrapper({ error: '必填', hint: '请输入' })
      expect(wrapper.find('.app-input__error').text()).toBe('必填')
      expect(wrapper.find('.app-input__hint').exists()).toBe(false)
    })
  })

  // ============================================================
  // 6. size 映射
  // ============================================================
  describe('6. size 映射', () => {
    it('sm → el-input size=small', () => {
      const wrapper = createWrapper({ size: 'sm' })
      expect(wrapper.find('.el-input-stub').attributes('data-size')).toBe('small')
      expect(wrapper.find('.app-input--sm').exists()).toBe(true)
    })

    it('md → el-input size=default', () => {
      const wrapper = createWrapper({ size: 'md' })
      expect(wrapper.find('.el-input-stub').attributes('data-size')).toBe('default')
      expect(wrapper.find('.app-input--md').exists()).toBe(true)
    })

    it('lg → el-input size=large', () => {
      const wrapper = createWrapper({ size: 'lg' })
      expect(wrapper.find('.el-input-stub').attributes('data-size')).toBe('large')
      expect(wrapper.find('.app-input--lg').exists()).toBe(true)
    })
  })

  // ============================================================
  // 7. disabled
  // ============================================================
  describe('7. disabled', () => {
    it('disabled=true 应传递到 el-input', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.el-input-stub').attributes('data-disabled')).toBe('true')
    })

    it('disabled=true 时 wrapper 应添加 app-input--disabled class', () => {
      const wrapper = createWrapper({ disabled: true })
      expect(wrapper.find('.app-input--disabled').exists()).toBe(true)
    })

    it('disabled=false 时不应有 disabled class', () => {
      const wrapper = createWrapper({ disabled: false })
      expect(wrapper.find('.app-input--disabled').exists()).toBe(false)
    })
  })

  // ============================================================
  // 8. readonly
  // ============================================================
  describe('8. readonly', () => {
    it('readonly=true 应传递到 el-input', () => {
      const wrapper = createWrapper({ readonly: true })
      expect(wrapper.find('.el-input-stub').attributes('data-readonly')).toBe('true')
    })
  })

  // ============================================================
  // 9. clearable
  // ============================================================
  describe('9. clearable', () => {
    it('clearable=true 应传递到 el-input', () => {
      const wrapper = createWrapper({ clearable: true })
      expect(wrapper.find('.el-input-stub').attributes('data-clearable')).toBe('true')
    })

    it('el-input clear 事件应 emit update:modelValue(空字符串) + clear', async () => {
      const wrapper = createWrapper({ modelValue: 'abc' })
      await wrapper.find('.el-input-stub__input').trigger('clear')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0][0]).toBe('')
      expect(wrapper.emitted('clear')).toBeTruthy()
    })
  })

  // ============================================================
  // 10. type 透传
  // ============================================================
  describe('10. type 透传', () => {
    it('type=text 应传递到 el-input', () => {
      const wrapper = createWrapper({ type: 'text' })
      expect(wrapper.find('.el-input-stub').attributes('data-type')).toBe('text')
    })

    it('type=password 应传递到 el-input', () => {
      const wrapper = createWrapper({ type: 'password' })
      expect(wrapper.find('.el-input-stub').attributes('data-type')).toBe('password')
    })

    it('type=number 应传递到 el-input', () => {
      const wrapper = createWrapper({ type: 'number' })
      expect(wrapper.find('.el-input-stub').attributes('data-type')).toBe('number')
    })

    it('type=textarea 应传递到 el-input', () => {
      const wrapper = createWrapper({ type: 'textarea' })
      expect(wrapper.find('.el-input-stub').attributes('data-type')).toBe('textarea')
    })
  })

  // ============================================================
  // 11. showPasswordToggle
  // ============================================================
  describe('11. showPasswordToggle', () => {
    it('type=password + showPasswordToggle=true → show-password=true', () => {
      const wrapper = createWrapper({ type: 'password', showPasswordToggle: true })
      expect(wrapper.find('.el-input-stub').attributes('data-show-password')).toBe('true')
    })

    it('type=text + showPasswordToggle=true → show-password=false（仅 password 类型生效）', () => {
      const wrapper = createWrapper({ type: 'text', showPasswordToggle: true })
      expect(wrapper.find('.el-input-stub').attributes('data-show-password')).toBe('false')
    })

    it('type=password + showPasswordToggle=false → show-password=false', () => {
      const wrapper = createWrapper({ type: 'password', showPasswordToggle: false })
      expect(wrapper.find('.el-input-stub').attributes('data-show-password')).toBe('false')
    })
  })

  // ============================================================
  // 12. prefix/suffix slot
  // ============================================================
  describe('12. prefix/suffix slot', () => {
    it('prefix slot 应渲染到 el-input 的 prefix 插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { prefix: '<span class="test-prefix">P</span>' },
      })
      expect(wrapper.find('.test-prefix').exists()).toBe(true)
    })

    it('suffix slot 应渲染到 el-input 的 suffix 插槽', () => {
      const wrapper = createWrapper({}, {
        slots: { suffix: '<span class="test-suffix">S</span>' },
      })
      expect(wrapper.find('.test-suffix').exists()).toBe(true)
    })
  })

  // ============================================================
  // 13. focus/blur 事件
  // ============================================================
  describe('13. focus/blur 事件', () => {
    it('focus 时应 emit focus', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-input-stub__input').trigger('focus')
      expect(wrapper.emitted('focus')).toBeTruthy()
    })

    it('focus 时 wrapper 应添加 app-input--focused class', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-input-stub__input').trigger('focus')
      expect(wrapper.find('.app-input--focused').exists()).toBe(true)
    })

    it('blur 时应 emit blur', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-input-stub__input').trigger('blur')
      expect(wrapper.emitted('blur')).toBeTruthy()
    })

    it('blur 后 wrapper 应移除 app-input--focused class', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-input-stub__input').trigger('focus')
      expect(wrapper.find('.app-input--focused').exists()).toBe(true)
      await wrapper.find('.el-input-stub__input').trigger('blur')
      expect(wrapper.find('.app-input--focused').exists()).toBe(false)
    })
  })

  // ============================================================
  // 14. change/keydown 事件
  // ============================================================
  describe('14. change/keydown 事件', () => {
    it('change 时应 emit change', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-input-stub__input').trigger('change')
      expect(wrapper.emitted('change')).toBeTruthy()
      expect(wrapper.emitted('change')[0][0]).toBe('changed-value')
    })

    it('keydown 时应 emit keydown', async () => {
      const wrapper = createWrapper()
      await wrapper.find('.el-input-stub__input').trigger('keydown')
      expect(wrapper.emitted('keydown')).toBeTruthy()
    })
  })

  // ============================================================
  // 15. maxlength/min/max/step 透传
  // ============================================================
  describe('15. 数值属性透传', () => {
    it('maxlength 应传递到 el-input', () => {
      const wrapper = createWrapper({ maxlength: 100 })
      expect(wrapper.find('.el-input-stub').attributes('data-maxlength')).toBe('100')
    })

    it('min 应传递到 el-input', () => {
      const wrapper = createWrapper({ min: 0 })
      expect(wrapper.find('.el-input-stub').attributes('data-min')).toBe('0')
    })

    it('max 应传递到 el-input', () => {
      const wrapper = createWrapper({ max: 999 })
      expect(wrapper.find('.el-input-stub').attributes('data-max')).toBe('999')
    })

    it('step 应传递到 el-input', () => {
      const wrapper = createWrapper({ step: 0.1 })
      expect(wrapper.find('.el-input-stub').attributes('data-step')).toBe('0.1')
    })
  })

  // ============================================================
  // 16. prefixIcon/suffixIcon 透传
  // ============================================================
  describe('16. icon 透传', () => {
    it('prefixIcon 应传递到 el-input', () => {
      const iconFn = vi.fn()
      const wrapper = createWrapper({ prefixIcon: iconFn })
      expect(wrapper.find('.el-input-stub').attributes('data-prefix-icon')).toBe('yes')
    })

    it('suffixIcon 应传递到 el-input', () => {
      const iconFn = vi.fn()
      const wrapper = createWrapper({ suffixIcon: iconFn })
      expect(wrapper.find('.el-input-stub').attributes('data-suffix-icon')).toBe('yes')
    })

    it('未传 icon 时不应传递', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-input-stub').attributes('data-prefix-icon')).toBe('no')
      expect(wrapper.find('.el-input-stub').attributes('data-suffix-icon')).toBe('no')
    })
  })

  // ============================================================
  // 17. wrapper classes 组合
  // ============================================================
  describe('17. wrapper classes 组合', () => {
    it('disabled + error 应同时有两个 class', () => {
      const wrapper = createWrapper({ disabled: true, error: '必填' })
      expect(wrapper.find('.app-input--disabled').exists()).toBe(true)
      expect(wrapper.find('.app-input--error').exists()).toBe(true)
    })

    it('focused + error 应同时有两个 class', async () => {
      const wrapper = createWrapper({ error: '必填' })
      await wrapper.find('.el-input-stub__input').trigger('focus')
      expect(wrapper.find('.app-input--focused').exists()).toBe(true)
      expect(wrapper.find('.app-input--error').exists()).toBe(true)
    })
  })

  // ============================================================
  // 18. inputId 生成
  // ============================================================
  describe('18. inputId 生成', () => {
    it('传 id 时应使用指定 id', () => {
      const wrapper = createWrapper({ id: 'my-input' })
      expect(wrapper.find('.el-input-stub').attributes('data-id')).toBe('my-input')
    })

    it('未传 id 时应自动生成 app-input-xxx', () => {
      const wrapper = createWrapper()
      // 自动生成的 id 格式: app-input-xxxxxxxxx (9 位随机字符)
      // 通过检查 wrapper 的 vm 来验证
      expect(wrapper.vm.inputId).toMatch(/^app-input-[a-z0-9]{9}$/)
    })

    it('两个未传 id 的实例应有不同的 inputId', () => {
      const w1 = createWrapper()
      const w2 = createWrapper()
      expect(w1.vm.inputId).not.toBe(w2.vm.inputId)
    })
  })

  // ============================================================
  // 19. 其他属性透传
  // ============================================================
  describe('19. 其他属性透传', () => {
    it('placeholder 应传递到 el-input', () => {
      const wrapper = createWrapper({ placeholder: '请输入...' })
      expect(wrapper.find('.el-input-stub').attributes('data-placeholder')).toBe('请输入...')
    })

    it('name 应传递到 el-input', () => {
      const wrapper = createWrapper({ name: 'username' })
      expect(wrapper.find('.el-input-stub').attributes('data-name')).toBe('username')
    })

    it('autocomplete 默认 off', () => {
      const wrapper = createWrapper()
      expect(wrapper.find('.el-input-stub').attributes('data-autocomplete')).toBe('off')
    })

    it('autofocus 应传递到 el-input', () => {
      const wrapper = createWrapper({ autofocus: true })
      expect(wrapper.find('.el-input-stub').attributes('data-autofocus')).toBe('true')
    })
  })
})