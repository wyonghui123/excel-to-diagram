/**
 * useEnumMeta.spec.js - 枚举预加载（批量）
 *
 * 覆盖：preloadEnums 写入 composable 缓存 / 失败 fail-soft 不抛。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/metaEnumService', () => ({
  getEnum: vi.fn(),
  getEnumBatch: vi.fn()
}))

vi.mock('@/utils/logger', () => ({
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() }
}))

import { getEnum, getEnumBatch } from '@/services/metaEnumService'
import { logger } from '@/utils/logger'
import { useEnumMeta, preloadEnums, _resetEnumMetaCache } from '@/composables/useEnumMeta'

describe('useEnumMeta', () => {
  beforeEach(() => {
    _resetEnumMetaCache()
    getEnum.mockReset()
    getEnumBatch.mockReset()
    logger.warn.mockReset()
  })

  it('preloadEnums 一次性写入缓存，load 命中后不再请求', async () => {
    getEnumBatch.mockResolvedValue({
      task_status: [
        { value: 'active', label: '启用', color: 'success' },
        { value: 'done', label: '完成' }
      ]
    })

    const result = await preloadEnums(['task_status', 'task_status', ''])
    expect(getEnumBatch).toHaveBeenCalledTimes(1)
    expect(getEnumBatch).toHaveBeenCalledWith(['task_status'])
    expect(result.task_status).toHaveLength(2)

    const { getItems, getItem, load } = useEnumMeta()
    expect(getItems('task_status')).toHaveLength(2)
    expect(getItem('task_status', 'active')).toEqual({ value: 'active', label: '启用', color: 'success' })

    // schemaVersion 为 undefined 时命中预加载缓存，不触发单数请求
    const entry = await load('task_status')
    expect(entry.items).toHaveLength(2)
    expect(getEnum).not.toHaveBeenCalled()
  })

  it('preloadEnums 失败时 fail-soft：warn 一次且不抛出', async () => {
    getEnumBatch.mockRejectedValue(new Error('network down'))

    await expect(preloadEnums(['task_status'])).resolves.toEqual({})
    expect(logger.warn).toHaveBeenCalledTimes(1)
  })

  it('空入参不发起请求', async () => {
    await expect(preloadEnums([])).resolves.toEqual({})
    await expect(preloadEnums()).resolves.toEqual({})
    expect(getEnumBatch).not.toHaveBeenCalled()
  })
})