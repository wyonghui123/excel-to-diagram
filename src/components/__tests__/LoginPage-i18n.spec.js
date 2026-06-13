/**
 * 测试 LoginPage.vue i18n 集成 (W5 i18n 迁移)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'

describe('LoginPage i18n 集成 (W5)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('app-locale', 'zh-CN')
    }
  })

  it('zh-CN locale 下显示中文', async () => {
    const { default: LoginPage } = await import('@/components/LoginPage.vue')
    const wrapper = mount(LoginPage, {
      global: {
        mocks: {
          $router: { push: () => {} },
          $route: { query: {} },
        },
        stubs: {
          // 防止 router 调用
        },
      },
    })
    await nextTick()
    const html = wrapper.html()
    // 至少 1 个中文 key 出现
    expect(html).toContain('用户名')
    expect(html).toContain('密码')
  })

  it('en-US locale 下显示英文', async () => {
    // [修复] 在 import 之前 reset module + 设 localStorage
    const { setLocale } = await import('@/i18n')
    setLocale('en-US')
    const { default: LoginPage } = await import('@/components/LoginPage.vue')
    const wrapper = mount(LoginPage, {
      global: {
        mocks: {
          $router: { push: () => {} },
          $route: { query: {} },
        },
      },
    })
    await nextTick()
    const html = wrapper.html()
    expect(html).toContain('Username')
    expect(html).toContain('Password')
  })

  it('包含 8 个 t() 调用（6 个文本 + 2 个 placeholder）', async () => {
    // 静态检查 - 源码包含 8 个 t() 调用
    const fs = await import('fs')
    const path = 'd:/filework/excel-to-diagram/src/components/LoginPage.vue'
    const content = fs.readFileSync(path, 'utf-8')
    // 同时匹配 {{ t( 和 :placeholder="t( / :xxx="t(
    const interpolationMatches = content.match(/\{\{\s*t\(/g) || []
    const attrMatches = content.match(/=\s*"t\(/g) || []
    const total = interpolationMatches.length + attrMatches.length
    expect(total).toBeGreaterThanOrEqual(8)
  })
})
