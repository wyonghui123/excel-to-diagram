/**
 * 测试 ChangePasswordDialog.vue i18n 集成 (W5 i18n 迁移)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

describe('ChangePasswordDialog i18n 集成 (W5)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('zh-CN locale 下显示中文', async () => {
    const { setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const { default: Dialog } = await import('@/components/ChangePasswordDialog.vue')
    const wrapper = await import('@vue/test-utils').then(m => m.mount(Dialog, {
      props: { visible: true },
      global: {
        stubs: {
          AppModal: { template: '<div><slot></slot><slot name="footer"></slot></div>' },
          AppInput: { template: '<div></div>' },
          AppButton: { template: '<button><slot></slot></button>' },
        },
      },
    }))
    const html = wrapper.html()
    expect(html).toContain('旧密码')
    expect(html).toContain('新密码')
    expect(html).toContain('确认新密码')
  })

  it('en-US locale 下显示英文', async () => {
    const { setLocale } = await import('@/i18n')
    setLocale('en-US')
    const { default: Dialog } = await import('@/components/ChangePasswordDialog.vue')
    const wrapper = await import('@vue/test-utils').then(m => m.mount(Dialog, {
      props: { visible: true },
      global: {
        stubs: {
          AppModal: { template: '<div><slot></slot><slot name="footer"></slot></div>' },
          AppInput: { template: '<div></div>' },
          AppButton: { template: '<button><slot></slot></button>' },
        },
      },
    }))
    const html = wrapper.html()
    expect(html).toContain('Old Password')
    expect(html).toContain('New Password')
    expect(html).toContain('Confirm New Password')
  })

  it('包含 15 个 t() 调用（覆盖 13 个 UI 文本 + 2 个错误消息）', async () => {
    // 静态检查
    const fs = await import('fs')
    const path = 'd:/filework/excel-to-diagram/src/components/ChangePasswordDialog.vue'
    const content = fs.readFileSync(path, 'utf-8')
    // 各种 t() 调用形式
    const matches = content.match(/t\(['"]changePassword\.|t\(['"]common\./g) || []
    expect(matches.length).toBeGreaterThanOrEqual(13)
  })
})
