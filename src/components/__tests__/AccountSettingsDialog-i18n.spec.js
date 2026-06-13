/**
 * 测试 AccountSettingsDialog.vue i18n 集成 (W5 i18n 迁移)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('AccountSettingsDialog i18n 集成 (W5)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('zh-CN locale 下显示中文（账户设置 title）', async () => {
    const { setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const { default: Dialog } = await import('@/components/AccountSettingsDialog.vue')
    const wrapper = await import('@vue/test-utils').then(m => m.mount(Dialog, {
      props: { visible: true },
      global: {
        stubs: {
          AppModal: { template: '<div><slot></slot></div>' },
          AppButton: { template: '<button><slot></slot></button>' },
          AppInput: { template: '<div></div>' },
          AppIcon: { template: '<i></i>' },
        },
      },
    }))
    // tabs 数组 label 应有中文
    expect(wrapper.vm.tabs.find(t => t.key === 'profile').label).toBe('个人信息')
    expect(wrapper.vm.tabs.find(t => t.key === 'security').label).toBe('安全设置')
    expect(wrapper.vm.tabs.find(t => t.key === 'preferences').label).toBe('偏好设置')
  })

  it('en-US locale 下显示英文', async () => {
    const { setLocale } = await import('@/i18n')
    setLocale('en-US')
    const { default: Dialog } = await import('@/components/AccountSettingsDialog.vue')
    const wrapper = await import('@vue/test-utils').then(m => m.mount(Dialog, {
      props: { visible: true },
      global: {
        stubs: {
          AppModal: { template: '<div><slot></slot></div>' },
          AppButton: { template: '<button><slot></slot></button>' },
          AppInput: { template: '<div></div>' },
          AppIcon: { template: '<i></i>' },
        },
      },
    }))
    expect(wrapper.vm.tabs.find(t => t.key === 'profile').label).toBe('Profile')
    expect(wrapper.vm.tabs.find(t => t.key === 'security').label).toBe('Security')
  })

  it('locale options 显示完整双语', async () => {
    const { setLocale } = await import('@/i18n')
    setLocale('en-US')
    const { default: Dialog } = await import('@/components/AccountSettingsDialog.vue')
    const wrapper = await import('@vue/test-utils').then(m => m.mount(Dialog, {
      props: { visible: true },
      global: {
        stubs: {
          AppModal: { template: '<div><slot></slot></div>' },
          AppButton: { template: '<button><slot></slot></button>' },
          AppInput: { template: '<div></div>' },
          AppIcon: { template: '<i></i>' },
        },
      },
    }))
    // localeOptions 应有 3 个
    expect(wrapper.vm.localeOptions).toHaveLength(3)
    expect(wrapper.vm.localeOptions[0].value).toBe('zh-CN')
    expect(wrapper.vm.localeOptions[1].value).toBe('en-US')
  })

  it('dateStyle/timeStyle/hourCycle options 都用 t()', async () => {
    const { setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const { default: Dialog } = await import('@/components/AccountSettingsDialog.vue')
    const wrapper = await import('@vue/test-utils').then(m => m.mount(Dialog, {
      props: { visible: true },
      global: {
        stubs: {
          AppModal: { template: '<div><slot></slot></div>' },
          AppButton: { template: '<button><slot></slot></button>' },
          AppInput: { template: '<div></div>' },
          AppIcon: { template: '<i></i>' },
        },
      },
    }))
    expect(wrapper.vm.dateStyleOptions).toHaveLength(4)
    expect(wrapper.vm.timeStyleOptions).toHaveLength(4)
    expect(wrapper.vm.hourCycleOptions).toHaveLength(2)
  })

  it('包含 30+ 个 t() 调用（覆盖 3 个 tab + 7 个 validation + 4 个 strength + ...）', async () => {
    const fs = await import('fs')
    const path = 'd:/filework/excel-to-diagram/src/components/AccountSettingsDialog.vue'
    const content = fs.readFileSync(path, 'utf-8')
    const matches = content.match(/t\(['"](?:accountSettings|changePassword|common)\./g) || []
    expect(matches.length).toBeGreaterThanOrEqual(30)
  })
})
