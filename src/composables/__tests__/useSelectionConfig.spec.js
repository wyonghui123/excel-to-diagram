/**
 * 测试 useSelectionConfig composable (FR-008 v2)
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref } from 'vue'

describe('useSelectionConfig (FR-008 v2)', () => {
  const originalLocation = window.location

  beforeEach(() => {
    // Default mock
    delete window.location
    window.location = { search: '' }
  })

  afterEach(() => {
    window.location = originalLocation
    vi.restoreAllMocks()
  })

  it('默认 5000，无任何配置时', async () => {
    const { useSelectionConfig, DEFAULT_LIMIT } = await import('@/composables/useSelectionConfig')
    const { finalLimit, source, sourceLabel } = useSelectionConfig()
    expect(finalLimit.value).toBe(DEFAULT_LIMIT)
    expect(source.value).toBe('default')
    expect(sourceLabel.value).toBe('系统默认')
  })

  it('URL 参数优先（HARD_LIMIT 截断）', async () => {
    window.location.search = '?max_selection=20000'
    const { useSelectionConfig, HARD_LIMIT } = await import('@/composables/useSelectionConfig')
    const { finalLimit, source } = useSelectionConfig()
    expect(finalLimit.value).toBe(20000)
    expect(source.value).toBe('url')
  })

  it('URL 参数超大时截断到 HARD_LIMIT', async () => {
    window.location.search = '?max_selection=99999999'
    const { useSelectionConfig, HARD_LIMIT } = await import('@/composables/useSelectionConfig')
    const { finalLimit } = useSelectionConfig()
    expect(finalLimit.value).toBe(HARD_LIMIT)
    expect(finalLimit.value).toBe(100000)
  })

  it('URL 参数无效字符串时降级到默认', async () => {
    window.location.search = '?max_selection=abc'
    const { useSelectionConfig, DEFAULT_LIMIT } = await import('@/composables/useSelectionConfig')
    const { finalLimit } = useSelectionConfig()
    // parseInt('abc') is NaN → fallback to DEFAULT_LIMIT
    expect(finalLimit.value).toBe(DEFAULT_LIMIT)
  })

  it('用户偏好 > 页面级 > BO > 系统 > 默认', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')

    // BO yaml: 1000
    const bo = { selection: { max_count: 1000 } }
    // Page: 5000
    const page = 5000
    // User: 10000
    const user = { selection: { max_count: 10000 } }

    const { finalLimit, source } = useSelectionConfig({
      maxSelection: page,
      boConfig: bo,
      userPreferences: user,
    })
    expect(finalLimit.value).toBe(10000)
    expect(source.value).toBe('user')
  })

  it('页面级 > BO > 系统', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { finalLimit, source } = useSelectionConfig({
      maxSelection: 7777,
      boConfig: { selection: { max_count: 1000 } },
    })
    expect(finalLimit.value).toBe(7777)
    expect(source.value).toBe('page')
  })

  it('BO > 系统', async () => {
    // 模拟 VITE_DEFAULT_MAX_SELECTION
    const originalEnv = import.meta.env
    Object.defineProperty(import.meta, 'env', {
      value: { ...originalEnv, VITE_DEFAULT_MAX_SELECTION: '999' },
      configurable: true,
    })

    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { finalLimit, source } = useSelectionConfig({
      boConfig: { selection: { max_count: 1000 } },
    })
    expect(finalLimit.value).toBe(1000)
    expect(source.value).toBe('bo')

    // Restore env
    Object.defineProperty(import.meta, 'env', { value: originalEnv, configurable: true })
  })

  it('validateSelection: 在限制内返回 proceed', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { validateSelection } = useSelectionConfig()
    const result = validateSelection(100)
    expect(result.ok).toBe(true)
    expect(result.action).toBe('proceed')
  })

  it('validateSelection: 超过 80% 警告', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { validateSelection } = useSelectionConfig()
    // 5000 * 0.8 = 4000, choose 4500
    const result = validateSelection(4500)
    expect(result.ok).toBe(true)
    expect(result.action).toBe('warn')
  })

  it('validateSelection: 超过限制 degrade', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { validateSelection } = useSelectionConfig()
    const result = validateSelection(10000)
    expect(result.ok).toBe(false)
    expect(result.action).toBe('degrade')
  })

  it('warningThreshold 从 BO 配置覆盖默认 0.8', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { warningThreshold } = useSelectionConfig({
      boConfig: { selection: { warning_threshold: 0.5 } },
    })
    expect(warningThreshold.value).toBe(0.5)
  })

  it('allowOverride 从 BO 配置覆盖默认 true', async () => {
    const { useSelectionConfig } = await import('@/composables/useSelectionConfig')
    const { allowOverride } = useSelectionConfig({
      boConfig: { selection: { allow_override: false } },
    })
    expect(allowOverride.value).toBe(false)
  })

  it('HARD_LIMIT 常量 = 100000', async () => {
    const { HARD_LIMIT } = await import('@/composables/useSelectionConfig')
    expect(HARD_LIMIT).toBe(100000)
  })

  it('DEFAULT_LIMIT 常量 = 5000', async () => {
    const { DEFAULT_LIMIT } = await import('@/composables/useSelectionConfig')
    expect(DEFAULT_LIMIT).toBe(5000)
  })

  it('URL_PARAM_KEY 常量 = max_selection', async () => {
    const { URL_PARAM_KEY } = await import('@/composables/useSelectionConfig')
    expect(URL_PARAM_KEY).toBe('max_selection')
  })
})
