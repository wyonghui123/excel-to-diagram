// HelpCenterDrawer - P0 placeholder unit test
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import HelpCenterDrawer from '../HelpCenterDrawer.vue'

describe('HelpCenterDrawer - P0 placeholder', () => {
  let wrapper

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
  })

  it('does not render drawer content when modelValue is false', () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: false }
    })
    expect(wrapper.find('.help-drawer').exists()).toBe(false)
  })

  it('renders drawer content when modelValue is true', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    expect(document.querySelector('.help-drawer')).toBeTruthy()
  })

  it('emits update:modelValue false when close button clicked', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()

    const closeBtn = document.querySelector('.help-drawer__close')
    expect(closeBtn).toBeTruthy()
    closeBtn.click()
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('emits update:modelValue false when mask clicked', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()

    const mask = document.querySelector('.help-drawer__mask')
    expect(mask).toBeTruthy()
    mask.click()
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })

  it('renders the placeholder content for P0 stage', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()

    expect(document.querySelector('.help-drawer__placeholder')).toBeTruthy()
    expect(document.querySelector('.help-drawer__placeholder-title').textContent).toContain('User Guide')
  })

  it('opens help URL in new tab when placeholder button clicked', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()

    const btn = document.querySelector('.help-drawer__placeholder button')
    expect(btn).toBeTruthy()
    btn.click()
    await nextTick()

    expect(openSpy).toHaveBeenCalled()
    expect(openSpy.mock.calls[0][0]).toBe('/docs/user-guide/index.html')

    openSpy.mockRestore()
  })

  it('locks body scroll when drawer opens and restores on close', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: false }
    })

    await wrapper.setProps({ modelValue: true })
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')

    await wrapper.setProps({ modelValue: false })
    await nextTick()
    expect(document.body.style.overflow).toBe('')
  })

  it('uses custom helpUrl when provided', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    wrapper = mount(HelpCenterDrawer, {
      props: {
        modelValue: true,
        helpUrl: '/custom/help/index.html',
        attachTo: document.body
      }
    })
    await nextTick()

    const btn = document.querySelector('.help-drawer__placeholder button')
    btn.click()

    expect(openSpy.mock.calls[0][0]).toBe('/custom/help/index.html')
    openSpy.mockRestore()
  })

  it('applies custom width from prop', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, width: 1200, attachTo: document.body }
    })
    await nextTick()

    const drawerWrapper = document.querySelector('.help-drawer__wrapper')
    expect(drawerWrapper.style.width).toBe('1200px')
  })
})
