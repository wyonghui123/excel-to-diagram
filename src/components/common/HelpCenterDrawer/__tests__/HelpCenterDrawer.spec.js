// HelpCenterDrawer - P1 iframe embed unit tests
import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import HelpCenterDrawer from '../HelpCenterDrawer.vue'

describe('HelpCenterDrawer - P1 iframe', () => {
  let wrapper

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
    document.body.style.overflow = ''
  })

  it('does not render drawer content when modelValue is false', () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: false }
    })
    expect(document.querySelector('.help-drawer')).toBeNull()
  })

  it('renders drawer with iframe when modelValue is true', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    expect(document.querySelector('.help-drawer')).toBeTruthy()
    const iframe = document.querySelector('.help-drawer__iframe')
    expect(iframe).toBeTruthy()
    expect(iframe.tagName).toBe('IFRAME')
  })

  it('uses default helpUrl pointing to /docs/user-guide/index.html', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    const iframe = document.querySelector('.help-drawer__iframe')
    expect(iframe.getAttribute('src')).toBe('/docs/user-guide/index.html')
  })

  it('respects custom helpUrl prop', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: {
        modelValue: true,
        helpUrl: '/custom/help/index.html',
        attachTo: document.body
      }
    })
    await nextTick()
    const iframe = document.querySelector('.help-drawer__iframe')
    expect(iframe.getAttribute('src')).toBe('/custom/help/index.html')
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

  it('opens helpUrl in new tab when header action button clicked', async () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()

    const btn = document.querySelector('.help-drawer__header-btn')
    expect(btn).toBeTruthy()
    btn.click()
    await nextTick()

    expect(openSpy).toHaveBeenCalled()
    expect(openSpy.mock.calls[0][0]).toBe('/docs/user-guide/index.html')
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

  it('bumps iframe key when drawer is reopened', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()
    const iframeEl1 = document.querySelector('.help-drawer__iframe')
    expect(iframeEl1).toBeTruthy()

    await wrapper.setProps({ modelValue: false })
    await nextTick()
    expect(document.querySelector('.help-drawer__iframe')).toBeNull()

    await wrapper.setProps({ modelValue: true })
    await nextTick()
    const iframeEl2 = document.querySelector('.help-drawer__iframe')
    expect(iframeEl2).toBeTruthy()
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

  it('closes drawer when Escape is pressed', async () => {
    wrapper = mount(HelpCenterDrawer, {
      props: { modelValue: true, attachTo: document.body }
    })
    await nextTick()

    const evt = new KeyboardEvent('keydown', { key: 'Escape' })
    document.dispatchEvent(evt)
    await nextTick()

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([false])
  })
})
