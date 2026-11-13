/**
 * 测试 useSelectionConfig composable (FR-008 v2)
 *
 * [B2-5 2026-11-13] 上限由后端 /meta/selection-limit 下发，URL 覆盖已移除。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV2: { get: vi.fn() },
}))

import { apiV2 } from '@/utils/httpClient'

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('useSelectionConfig (FR-008 v2)', () => {
  const originalLocation = window.location

  beforeEach(() => {
    delete window.location
    window.location = { search: '' }
    apiV2.get.mockResolvedValue({ success: true, data: { max_count: 5000, warning_threshold: 0.8 } })
  })

  afterEach(() => {
    window.location = originalLocation
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  async function loadComposable() {
    const mod = await import('@/composables/useSelectionConfig')
    mod._resetSelectionLimitForTest()
    return mod
  }

  it('默认 5000，无任何配置时', async () => {
    const { useSelectionConfig, DEFAULT_LIMIT } = await loadComposable()
    const { finalLimit, source, sourceLabel } = useSelectionConfig()
    await flush()
    expect(finalLimit.value).toBe(DEFAULT_LIMIT)
    expect(source.value).toBe('default')
    expect(sourceLabel.value).toBe('系统默认')
  })

  it('URL ?max_selection 不再生效（后端上限为唯一来源）', async () => {
    window.location.search = '?max_selection=20000'
    const { useSelectionConfig } = await loadComposable()
    const { finalLimit, source } = useSelectionConfig()
    await flush()
    expect(finalLimit.value).toBe(5000)
    expect(source.value).toBe('default')
  })

  it('用户配置超过后端上限时被后端封顶', async () => {
    apiV2.get.mockResolvedValue({ success: true, data: { max_count: 3000 } })
    const { useSelectionConfig } = await loadComposable()
    const { finalLimit, source, sourceLabel } = useSelectionConfig({
      userPreferences: { selection: { max_count: 10000 } },
    })
    await flush()
    expect(finalLimit.value).toBe(3000)
    expect(source.value).toBe('backend')
    expect(sourceLabel.value).toBe('后端配置')
  })

  it('后端不可用时降级到本地默认', async () => {
    apiV2.get.mockRejectedValue(new Error('offline'))
    const { useSelectionConfig, DEFAULT_LIMIT } = await loadComposable()
    const { finalLimit } = useSelectionConfig()
    await flush()
    expect(finalLimit.value).toBe(DEFAULT_LIMIT)
  })

  it('用户偏好 > 页面级 > BO > 系统 > 默认', async () => {
    apiV2.get.mockResolvedValue({ success: true, data: { max_count: 100000 } })
    const { useSelectionConfig } = await loadComposable()
    const { finalLimit, source } = useSelectionConfig({
      maxSelection: 5000,
      boConfig: { selection: { max_count: 1000 } },
      userPreferences: { selection: { max_count: 10000 } },
    })
    await flush()
    expect(finalLimit.value).toBe(10000)
    expect(source.value).toBe('user')
  })

  it('页面级 > BO > 系统', async () => {
    apiV2.get.mockResolvedValue({ success: true, data: { max_count: 100000 } })
    const { useSelectionConfig } = await loadComposable()
    const { finalLimit, source } = useSelectionConfig({
      maxSelection: 7777,
      boConfig: { selection: { max_count: 1000 } },
    })
    await flush()
    expect(finalLimit.value).toBe(7777)
    expect(source.value).toBe('page')
  })

  it('BO > 系统', async () => {
    const originalEnv = import.meta.env
    Object.defineProperty(import.meta, 'env', {
      value: { ...originalEnv, VITE_DEFAULT_MAX_SELECTION: '999' },
      configurable: true,
    })

    const { useSelectionConfig } = await loadComposable()
    const { finalLimit, source } = useSelectionConfig({
      boConfig: { selection: { max_count: 1000 } },
    })
    await flush()
    expect(finalLimit.value).toBe(1000)
    expect(source.value).toBe('bo')

    Object.defineProperty(import.meta, 'env', { value: originalEnv, configurable: true })
  })

  it('validateSelection: 在限制内返回 proceed', async () => {
    const { useSelectionConfig } = await loadComposable()
    const { validateSelection } = useSelectionConfig()
    await flush()
    const result = validateSelection(100)
    expect(result.ok).toBe(true)
    expect(result.action).toBe('proceed')
  })

  it('validateSelection: 超过 80% 警告', async () => {
    const { useSelectionConfig } = await loadComposable()
    const { validateSelection } = useSelectionConfig()
    await flush()
    const result = validateSelection(4500)
    expect(result.ok).toBe(true)
    expect(result.action).toBe('warn')
  })

  it('validateSelection: 超过限制 degrade', async () => {
    const { useSelectionConfig } = await loadComposable()
    const { validateSelection } = useSelectionConfig()
    await flush()
    const result = validateSelection(10000)
    expect(result.ok).toBe(false)
    expect(result.action).toBe('degrade')
  })

  it('warningThreshold 从 BO 配置覆盖默认 0.8', async () => {
    const { useSelectionConfig } = await loadComposable()
    const { warningThreshold } = useSelectionConfig({
      boConfig: { selection: { warning_threshold: 0.5 } },
    })
    await flush()
    expect(warningThreshold.value).toBe(0.5)
  })

  it('allowOverride 从 BO 配置覆盖默认 true', async () => {
    const { useSelectionConfig } = await loadComposable()
    const { allowOverride } = useSelectionConfig({
      boConfig: { selection: { allow_override: false } },
    })
    await flush()
    expect(allowOverride.value).toBe(false)
  })

  it('HARD_LIMIT / DEFAULT_LIMIT 常量', async () => {
    const { HARD_LIMIT, DEFAULT_LIMIT } = await loadComposable()
    expect(HARD_LIMIT).toBe(100000)
    expect(DEFAULT_LIMIT).toBe(5000)
  })
})