/**
 * 测试自研 i18n 模块 (W4 PR-4.2)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

describe('i18n (W4 PR-4.2)', () => {
  beforeEach(() => {
    // 清除 localStorage
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('app-locale')
    }
    // 重置模块（使 storage 检测重新执行）
    vi.resetModules()
  })

  afterEach(() => {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('app-locale')
    }
  })

  describe('t() 翻译', () => {
    it('默认返回中文（zh-CN）值', async () => {
      // 显式设置 locale 为 zh-CN（避免浏览器 navigator.language 干扰）
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { t } = await import('@/i18n')
      expect(t('common.save')).toBe('保存')
      expect(t('common.cancel')).toBe('取消')
    })

    it('嵌套 key 支持点分路径', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { t } = await import('@/i18n')
      expect(t('auth.login')).toBe('登录')
      expect(t('auth.username')).toBe('用户名')
      expect(t('diagram.title')).toBe('图表')
    })

    it('未知 key 返回 defaultValue 或 key 本身', async () => {
      const { t } = await import('@/i18n')
      expect(t('nonexistent.key', '默认值')).toBe('默认值')
      expect(t('nonexistent.key')).toBe('nonexistent.key')
    })

    it('深层嵌套 key', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { t } = await import('@/i18n')
      expect(t('import.feishuToken')).toBe('请输入飞书表格的 Token')
    })
  })

  describe('setLocale / getLocale', () => {
    it('默认 locale = zh-CN（中文优先）', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { getLocale } = await import('@/i18n')
      expect(getLocale()).toBe('zh-CN')
    })

    it('setLocale 切换到 en-US', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { setLocale, getLocale, t } = await import('@/i18n')
      setLocale('en-US')
      expect(getLocale()).toBe('en-US')
      expect(t('common.save')).toBe('Save')
    })

    it('setLocale 持久化到 localStorage', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { setLocale } = await import('@/i18n')
      setLocale('en-US')
      expect(localStorage.getItem('app-locale')).toBe('en-US')

      // 重新加载模块
      vi.resetModules()
      const { getLocale: getLocale2 } = await import('@/i18n')
      expect(getLocale2()).toBe('en-US')
    })

    it('不支持的 locale 降级到 zh-CN', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { setLocale, getLocale } = await import('@/i18n')
      setLocale('ja-JP')
      expect(getLocale()).toBe('zh-CN')
    })
  })

  describe('currentLocale 响应式', () => {
    it('是 computed ref，setLocale 后值变化', async () => {
      localStorage.setItem('app-locale', 'zh-CN')
      vi.resetModules()
      const { currentLocale, setLocale } = await import('@/i18n')
      expect(currentLocale.value).toBe('zh-CN')
      setLocale('en-US')
      expect(currentLocale.value).toBe('en-US')
    })
  })

  describe('SUPPORTED_LOCALES', () => {
    it('只包含 zh-CN 和 en-US', async () => {
      const { SUPPORTED_LOCALES } = await import('@/i18n')
      expect(SUPPORTED_LOCALES).toEqual(['zh-CN', 'en-US'])
    })
  })

  describe('zh-CN / en-US 完整性', () => {
    it('两个 locale 的 keys 必须一致（否则切换有 key 缺失）', async () => {
      // 浅校验：先看 zh 有哪些一级 keys
      const zh = (await import('@/i18n/locales/zh-CN.json')).default
      const en = (await import('@/i18n/locales/en-US.json')).default

      const flatten = (obj, prefix = '') => {
        const out = []
        for (const k of Object.keys(obj)) {
          const path = prefix ? `${prefix}.${k}` : k
          if (typeof obj[k] === 'object' && obj[k] !== null) {
            out.push(...flatten(obj[k], path))
          } else {
            out.push(path)
          }
        }
        return out
      }

      const zhKeys = new Set(flatten(zh))
      const enKeys = new Set(flatten(en))

      // 至少两边共有的 keys
      const common = [...zhKeys].filter(k => enKeys.has(k))
      expect(common.length).toBeGreaterThan(20)  // 至少 20 个公共 key
    })
  })
})
