/**
 * 测试 t() 插值功能
 */
import { describe, it, expect, beforeEach } from 'vitest'

describe('t() 插值功能 (W5 增强)', () => {
  beforeEach(() => {
    if (typeof localStorage !== 'undefined') localStorage.setItem('app-locale', 'zh-CN')
  })

  it('单参数插值：替换 {key} 占位符', async () => {
    const { t, setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const result = t('validationPanel.greeting', '你好 {name}', { name: '张三' })
    expect(result).toBe('你好 张三')
  })

  it('多参数插值：替换多个 {key}', async () => {
    const { t, setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const result = t('validationPanel.greeting2', '{greet} {name}!', { greet: 'Hi', name: 'Tom' })
    expect(result).toBe('Hi Tom!')
  })

  it('数字插值：自动转 string', async () => {
    const { t, setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const result = t('validationPanel.summary', '总数: {count}', { count: 42 })
    expect(result).toBe('总数: 42')
  })

  it('无 params 时保留原始占位符', async () => {
    const { t, setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const result = t('validationPanel.summary', '总数: {count}')
    expect(result).toBe('总数: {count}')
  })

  it('params 中缺 key 时保留占位符', async () => {
    const { t, setLocale } = await import('@/i18n')
    setLocale('zh-CN')
    const result = t('validationPanel.summary', '总数: {count} / {total}', { count: 5 })
    expect(result).toBe('总数: 5 / {total}')
  })

  it('en-US locale 下的插值', async () => {
    const { t, setLocale } = await import('@/i18n')
    setLocale('en-US')
    const result = t('validationPanel.summary', 'Total: {count}', { count: 10 })
    expect(result).toBe('Total: 10')
  })
})
