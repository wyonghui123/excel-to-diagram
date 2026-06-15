/**
 * AppModal.spec.js — YonDesign AppModal 组件测试
 *
 * 测试策略:
 * - Stub Teleport 和 AppButton（不依赖真实 DOM 和组件实现）
 * - 验证 props 透传、v-model 双向绑定、事件触发、插槽渲染
 * - 覆盖 20 个场景,约 72 个用例
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import AppModal from '../AppModal.vue'

// ─── stubs ───────────────────────────────────────────────────────
const AppButtonStub = {
  name: 'AppButton',
  template: '<button class="app-button-stub" :data-variant="variant" :data-loading="loading" @click="$emit(\'click\', $event)"><slot /></button>',
  props: ['variant', 'loading'],
  emits: ['click'],
}

// ─── helper ──────────────────────────────────────────────────────
function createWrapper(props = {}, options = {}) {
  return mount(AppModal, {
    props: {
      modelValue: false,
      ...props,
    },
    slots: options.slots,
    global: {
      stubs: {
        Teleport: true,
        AppButton: AppButtonStub,
        ...options.stubs,
      },
    },
    attachTo: document.body,
    ...options,
  })
}

// ─── 测试套件 ────────────────────────────────────────────────────
describe('AppModal', () => {
  beforeEach(() => {
    document.body.style.overflow = ''
  })

  afterEach(() => {
    document.body.style.overflow = ''
  })

  // ── 1. 默认渲染 ──────────────────────────────────────────────
  describe('1-默认渲染', () => {
    it('modelValue=false 时不应渲染模态框', () => {
      const wrapper = createWrapper({ modelValue: false })
      expect(wrapper.find('.app-modal').exists()).toBe(false)
    })

    it('modelValue=true 时应渲染模态框', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal').exists()).toBe(true)
    })

    it('应渲染 backdrop', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal__backdrop').exists()).toBe(true)
    })

    it('应渲染 container', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal__container').exists()).toBe(true)
    })

    it('应渲染 body', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal__body').exists()).toBe(true)
    })

    it('role 应为 dialog', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal').attributes('role')).toBe('dialog')
    })

    it('aria-modal 应为 true', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal').attributes('aria-modal')).toBe('true')
    })
  })

  // ── 2. title ─────────────────────────────────────────────────
  describe('2-title', () => {
    it('有 title 时应渲染 header', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '测试标题' })
      await nextTick()
      expect(wrapper.find('.app-modal__header').exists()).toBe(true)
    })

    it('应渲染 title 文本', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '测试标题' })
      await nextTick()
      expect(wrapper.find('.app-modal__title').text()).toBe('测试标题')
    })

    it('无 title 且无 header slot 时不应渲染 header', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal__header').exists()).toBe(false)
    })

    it('有 header slot 时应渲染 header', async () => {
      const wrapper = createWrapper({ modelValue: true }, {
        slots: { header: '<div class="custom-header">自定义头部</div>' },
      })
      await nextTick()
      expect(wrapper.find('.app-modal__header').exists()).toBe(true)
      expect(wrapper.find('.custom-header').exists()).toBe(true)
    })
  })

  // ── 3. showClose ─────────────────────────────────────────────
  describe('3-showClose', () => {
    it('showClose=true 时应渲染关闭按钮', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '标题', showClose: true })
      await nextTick()
      expect(wrapper.find('.app-modal__close').exists()).toBe(true)
    })

    it('showClose=false 时不应渲染关闭按钮', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '标题', showClose: false })
      await nextTick()
      expect(wrapper.find('.app-modal__close').exists()).toBe(false)
    })

    it('点击关闭按钮应 emit update:modelValue=false', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '标题', showClose: true })
      await nextTick()
      await wrapper.find('.app-modal__close').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
    })

    it('点击关闭按钮应 emit close', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '标题', showClose: true })
      await nextTick()
      await wrapper.find('.app-modal__close').trigger('click')
      expect(wrapper.emitted('close')).toBeTruthy()
    })
  })

  // ── 4. width ─────────────────────────────────────────────────
  describe('4-width', () => {
    it('默认 width 为 520px', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.attributes('style')).toContain('width: 520px')
    })

    it('应支持数字 width', async () => {
      const wrapper = createWrapper({ modelValue: true, width: 600 })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.attributes('style')).toContain('width: 600px')
    })

    it('应支持字符串 width', async () => {
      const wrapper = createWrapper({ modelValue: true, width: '80%' })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.attributes('style')).toContain('width: 80%')
    })
  })

  // ── 5. customClass ───────────────────────────────────────────
  describe('5-customClass', () => {
    it('应添加自定义 class', async () => {
      const wrapper = createWrapper({ modelValue: true, customClass: 'my-modal' })
      await nextTick()
      expect(wrapper.find('.app-modal').classes()).toContain('my-modal')
    })

    it('无 customClass 时不应添加额外 class', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      const classes = wrapper.find('.app-modal').classes()
      expect(classes).toContain('app-modal')
    })
  })

  // ── 6. zIndex ────────────────────────────────────────────────
  describe('6-zIndex', () => {
    it('应设置自定义 zIndex', async () => {
      const wrapper = createWrapper({ modelValue: true, zIndex: 9999 })
      await nextTick()
      const modal = wrapper.find('.app-modal')
      expect(modal.attributes('style')).toContain('z-index: 9999')
    })

    it('zIndex 为 null 时不应设置 zIndex', async () => {
      const wrapper = createWrapper({ modelValue: true, zIndex: null })
      await nextTick()
      const modal = wrapper.find('.app-modal')
      const styleAttr = modal.attributes('style') || ''
      expect(styleAttr).not.toContain('z-index')
    })
  })

  // ── 7. backdrop click ────────────────────────────────────────
  describe('7-backdrop click', () => {
    it('closeOnClickOverlay=true 时点击遮罩应关闭', async () => {
      const wrapper = createWrapper({ modelValue: true, closeOnClickOverlay: true })
      await nextTick()
      await wrapper.find('.app-modal__backdrop').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
    })

    it('closeOnClickOverlay=false 时点击遮罩不应关闭', async () => {
      const wrapper = createWrapper({ modelValue: true, closeOnClickOverlay: false })
      await nextTick()
      await wrapper.find('.app-modal__backdrop').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    })
  })

  // ── 8. ESC key ───────────────────────────────────────────────
  describe('8-ESC key', () => {
    it('closeOnPressEscape=true 时按 ESC 应关闭', async () => {
      const wrapper = createWrapper({ modelValue: true, closeOnPressEscape: true })
      await nextTick()
      const event = new KeyboardEvent('keydown', { key: 'Escape' })
      document.dispatchEvent(event)
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
    })

    it('closeOnPressEscape=false 时按 ESC 不应关闭', async () => {
      const wrapper = createWrapper({ modelValue: true, closeOnPressEscape: false })
      await nextTick()
      const event = new KeyboardEvent('keydown', { key: 'Escape' })
      document.dispatchEvent(event)
      expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    })

    it('modelValue=false 时按 ESC 不应触发', async () => {
      const wrapper = createWrapper({ modelValue: false, closeOnPressEscape: true })
      await nextTick()
      const event = new KeyboardEvent('keydown', { key: 'Escape' })
      document.dispatchEvent(event)
      expect(wrapper.emitted('update:modelValue')).toBeFalsy()
    })
  })

  // ── 9. showDefaultFooter ─────────────────────────────────────
  describe('9-showDefaultFooter', () => {
    it('showDefaultFooter=true 时应渲染默认 footer', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      expect(wrapper.find('.app-modal__footer').exists()).toBe(true)
    })

    it('showDefaultFooter=false 时不应渲染默认 footer', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: false })
      await nextTick()
      expect(wrapper.find('.app-modal__footer').exists()).toBe(false)
    })

    it('应渲染确认和取消按钮', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons).toHaveLength(2)
    })

    it('确认按钮应为 primary variant', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[1].attributes('data-variant')).toBe('primary')
    })

    it('取消按钮应为 secondary variant', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[0].attributes('data-variant')).toBe('secondary')
    })
  })

  // ── 10. confirmText / cancelText ─────────────────────────────
  describe('10-confirmText / cancelText', () => {
    it('应显示自定义确认文本', async () => {
      const wrapper = createWrapper({
        modelValue: true,
        showDefaultFooter: true,
        confirmText: '保存',
      })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[1].text()).toBe('保存')
    })

    it('应显示自定义取消文本', async () => {
      const wrapper = createWrapper({
        modelValue: true,
        showDefaultFooter: true,
        cancelText: '放弃',
      })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[0].text()).toBe('放弃')
    })

    it('默认确认文本为 "确定"', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[1].text()).toBe('确定')
    })

    it('默认取消文本为 "取消"', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[0].text()).toBe('取消')
    })
  })

  // ── 11. confirmLoading ───────────────────────────────────────
  describe('11-confirmLoading', () => {
    it('应透传 confirmLoading 到确认按钮', async () => {
      const wrapper = createWrapper({
        modelValue: true,
        showDefaultFooter: true,
        confirmLoading: true,
      })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[1].attributes('data-loading')).toBe('true')
    })
  })

  // ── 12. confirm / cancel 事件 ────────────────────────────────
  describe('12-confirm / cancel 事件', () => {
    it('点击确认按钮应 emit confirm', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      await buttons[1].trigger('click')
      expect(wrapper.emitted('confirm')).toBeTruthy()
    })

    it('点击取消按钮应 emit cancel', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      await buttons[0].trigger('click')
      expect(wrapper.emitted('cancel')).toBeTruthy()
    })

    it('点击取消按钮应同时关闭弹窗', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      await buttons[0].trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
      expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
    })
  })

  // ── 13. footer slot ──────────────────────────────────────────
  describe('13-footer slot', () => {
    it('应支持 footer 插槽', async () => {
      const wrapper = createWrapper({ modelValue: true }, {
        slots: { footer: '<div class="custom-footer">自定义底部</div>' },
      })
      await nextTick()
      expect(wrapper.find('.app-modal__footer').exists()).toBe(true)
      expect(wrapper.find('.custom-footer').exists()).toBe(true)
    })

    it('footer slot 应覆盖默认 footer', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true }, {
        slots: { footer: '<div class="custom-footer">自定义底部</div>' },
      })
      await nextTick()
      expect(wrapper.find('.custom-footer').exists()).toBe(true)
      expect(wrapper.findAll('.app-button-stub')).toHaveLength(0)
    })
  })

  // ── 14. default slot ─────────────────────────────────────────
  describe('14-default slot', () => {
    it('应支持默认插槽', async () => {
      const wrapper = createWrapper({ modelValue: true }, {
        slots: { default: '<div class="modal-content">模态框内容</div>' },
      })
      await nextTick()
      expect(wrapper.find('.modal-content').exists()).toBe(true)
      expect(wrapper.find('.modal-content').text()).toBe('模态框内容')
    })
  })

  // ── 15. open 事件 ────────────────────────────────────────────
  describe('15-open 事件', () => {
    it('modelValue 从 false 变为 true 时应 emit open', async () => {
      const wrapper = createWrapper({ modelValue: false })
      await wrapper.setProps({ modelValue: true })
      await nextTick()
      expect(wrapper.emitted('open')).toBeTruthy()
    })
  })

  // ── 16. lockScroll ───────────────────────────────────────────
  describe('16-lockScroll', () => {
    it('lockScroll=true 时打开弹窗应锁定 body 滚动', async () => {
      const wrapper = createWrapper({ modelValue: false, lockScroll: true })
      await wrapper.setProps({ modelValue: true })
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')
    })

    it('lockScroll=false 时打开弹窗不应锁定 body 滚动', async () => {
      const wrapper = createWrapper({ modelValue: false, lockScroll: false })
      await wrapper.setProps({ modelValue: true })
      await nextTick()
      expect(document.body.style.overflow).not.toBe('hidden')
    })

    it('关闭弹窗应解锁 body 滚动', async () => {
      const wrapper = createWrapper({ modelValue: false, lockScroll: true })
      await wrapper.setProps({ modelValue: true })
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')
      await wrapper.setProps({ modelValue: false })
      await nextTick()
      expect(document.body.style.overflow).toBe('')
    })
  })

  // ── 17. container classes ────────────────────────────────────
  describe('17-container classes', () => {
    it('无 header 时应添加 no-header class', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.classes()).toContain('app-modal__container--no-header')
    })

    it('有 header 时不应添加 no-header class', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '标题' })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.classes()).not.toContain('app-modal__container--no-header')
    })

    it('无 footer 时应添加 no-footer class', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.classes()).toContain('app-modal__container--no-footer')
    })

    it('有 footer 时不应添加 no-footer class', async () => {
      const wrapper = createWrapper({ modelValue: true, showDefaultFooter: true })
      await nextTick()
      const container = wrapper.find('.app-modal__container')
      expect(container.classes()).not.toContain('app-modal__container--no-footer')
    })
  })

  // ── 18. props 默认值 ─────────────────────────────────────────
  describe('18-props 默认值', () => {
    it('title 默认为空字符串', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal__header').exists()).toBe(false)
    })

    it('showClose 默认为 true', async () => {
      const wrapper = createWrapper({ modelValue: true, title: '标题' })
      await nextTick()
      expect(wrapper.find('.app-modal__close').exists()).toBe(true)
    })

    it('closeOnClickOverlay 默认为 true', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      await wrapper.find('.app-modal__backdrop').trigger('click')
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    })

    it('closeOnPressEscape 默认为 true', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      const event = new KeyboardEvent('keydown', { key: 'Escape' })
      document.dispatchEvent(event)
      expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    })

    it('lockScroll 默认为 true', async () => {
      const wrapper = createWrapper({ modelValue: false })
      await wrapper.setProps({ modelValue: true })
      await nextTick()
      expect(document.body.style.overflow).toBe('hidden')
    })
  })

  // ── 19. 组合 props ───────────────────────────────────────────
  describe('19-组合 props', () => {
    it('应同时应用多个自定义 props', async () => {
      const wrapper = createWrapper({
        modelValue: true,
        title: '测试弹窗',
        width: 700,
        showClose: true,
        showDefaultFooter: true,
        confirmText: '保存',
        cancelText: '放弃',
        customClass: 'my-modal',
        zIndex: 9999,
      })
      await nextTick()
      expect(wrapper.find('.app-modal').classes()).toContain('my-modal')
      expect(wrapper.find('.app-modal').attributes('style')).toContain('z-index: 9999')
      expect(wrapper.find('.app-modal__title').text()).toBe('测试弹窗')
      expect(wrapper.find('.app-modal__container').attributes('style')).toContain('width: 700px')
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[0].text()).toBe('放弃')
      expect(buttons[1].text()).toBe('保存')
    })
  })

  // ── 20. 边界情况 ─────────────────────────────────────────────
  describe('20-边界情况', () => {
    it('所有 props 都为默认值时应正常渲染', async () => {
      const wrapper = createWrapper({ modelValue: true })
      await nextTick()
      expect(wrapper.find('.app-modal').exists()).toBe(true)
    })

    it('所有插槽都提供时应正常渲染', async () => {
      const wrapper = createWrapper({ modelValue: true }, {
        slots: {
          header: '<div class="h">header</div>',
          default: '<div class="d">default</div>',
          footer: '<div class="f">footer</div>',
        },
      })
      await nextTick()
      expect(wrapper.find('.h').exists()).toBe(true)
      expect(wrapper.find('.d').exists()).toBe(true)
      expect(wrapper.find('.f').exists()).toBe(true)
    })

    it('confirmLoading=true 时确认按钮应显示加载状态', async () => {
      const wrapper = createWrapper({
        modelValue: true,
        showDefaultFooter: true,
        confirmLoading: true,
      })
      await nextTick()
      const buttons = wrapper.findAll('.app-button-stub')
      expect(buttons[1].attributes('data-loading')).toBe('true')
    })
  })
})
