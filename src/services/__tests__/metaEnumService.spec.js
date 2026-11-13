/**
 * metaEnumService.spec.js - 批量枚举端点消费
 *
 * 覆盖：batch 单次请求 / 已缓存不重复请求 / 未知 name 返回 [] /
 *       失败抛错并清理 inflight / getEnum 底层走 batch 端点。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV2: { get: vi.fn() }
}))

vi.mock('@/utils/logger', () => ({
  logger: { warn: vi.fn(), error: vi.fn(), info: vi.fn() }
}))

import { apiV2 } from '@/utils/httpClient'
import { logger } from '@/utils/logger'
import { getEnum, getEnumBatch, _resetMetaCache } from '@/services/metaEnumService'

describe('metaEnumService', () => {
  beforeEach(() => {
    _resetMetaCache()
    apiV2.get.mockReset()
    logger.warn.mockReset()
  })

  it('getEnumBatch 去重后只发一次 batch 请求，并写入缓存', async () => {
    apiV2.get.mockResolvedValue({
      data: {
        task_status: [{ value: 'active', label: '启用' }],
        task_priority: [{ value: 'high', label: '高' }]
      }
    })

    const result = await getEnumBatch(['task_status', 'task_priority', 'task_status', '', null])

    expect(apiV2.get).toHaveBeenCalledTimes(1)
    expect(apiV2.get).toHaveBeenCalledWith('/meta/enums/batch', {
      params: { names: 'task_status,task_priority' }
    })
    expect(result.task_status).toEqual([{ value: 'active', label: '启用' }])
    expect(result.task_priority).toEqual([{ value: 'high', label: '高' }])
    expect(await getEnum('task_status')).toEqual([{ value: 'active', label: '启用' }])
    expect(apiV2.get).toHaveBeenCalledTimes(1)
  })

  it('已缓存的 name 不再请求', async () => {
    apiV2.get.mockResolvedValue({ data: { task_status: [{ value: 'active', label: '启用' }] } })

    await getEnumBatch(['task_status'])
    expect(apiV2.get).toHaveBeenCalledTimes(1)

    const again = await getEnumBatch(['task_status'])
    expect(apiV2.get).toHaveBeenCalledTimes(1)
    expect(again.task_status).toEqual([{ value: 'active', label: '启用' }])

    // 全部已缓存 => 不发请求（含空入参）
    await getEnumBatch([])
    expect(apiV2.get).toHaveBeenCalledTimes(1)
  })

  it('未知 / 缺失的 name 返回 []，兼容 { items } 形状', async () => {
    apiV2.get.mockResolvedValue({
      data: {
        task_status: { items: [{ value: 'active', label: '启用' }] }
      }
    })

    const result = await getEnumBatch(['task_status', 'not_exist'])

    expect(result.task_status).toEqual([{ value: 'active', label: '启用' }])
    expect(result.not_exist).toEqual([])
    expect(await getEnum('not_exist')).toEqual([])
  })

  it('失败时 warn 并抛错，且清理 inflight 允许重试', async () => {
    const err = new Error('boom')
    apiV2.get.mockRejectedValueOnce(err)

    await expect(getEnumBatch(['task_status'])).rejects.toThrow('boom')
    expect(logger.warn).toHaveBeenCalledTimes(1)

    apiV2.get.mockResolvedValueOnce({ data: { task_status: [{ value: 'active', label: '启用' }] } })
    const retry = await getEnumBatch(['task_status'])

    expect(apiV2.get).toHaveBeenCalledTimes(2)
    expect(retry.task_status).toEqual([{ value: 'active', label: '启用' }])
  })

  it('不同 name 集合并发时按 name 级合并 inflight，不重复请求同一 name', async () => {
    const first = {}
    first.promise = new Promise(resolve => {
      first.resolve = resolve
    })
    const second = {}
    second.promise = new Promise(resolve => {
      second.resolve = resolve
    })
    apiV2.get
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)

    const p1 = getEnumBatch(['a'])
    const p2 = getEnumBatch(['a', 'b'])

    expect(apiV2.get).toHaveBeenCalledTimes(2)
    expect(apiV2.get).toHaveBeenNthCalledWith(1, '/meta/enums/batch', { params: { names: 'a' } })
    expect(apiV2.get).toHaveBeenNthCalledWith(2, '/meta/enums/batch', { params: { names: 'b' } })

    first.resolve({ data: { a: [{ value: 'a1', label: 'A1' }] } })
    second.resolve({ data: { b: [{ value: 'b1', label: 'B1' }] } })

    const [r1, r2] = await Promise.all([p1, p2])
    expect(r1.a).toEqual([{ value: 'a1', label: 'A1' }])
    expect(r2.a).toEqual([{ value: 'a1', label: 'A1' }])
    expect(r2.b).toEqual([{ value: 'b1', label: 'B1' }])
    expect(apiV2.get).toHaveBeenCalledTimes(2)
  })

  it('getEnum 底层走 batch 端点（并发同一 name 只发一次）', async () => {
    apiV2.get.mockResolvedValue({ data: { role_type: [{ value: 'admin', label: '管理员' }] } })

    const [a, b] = await Promise.all([getEnum('role_type'), getEnum('role_type')])

    expect(apiV2.get).toHaveBeenCalledTimes(1)
    expect(apiV2.get).toHaveBeenCalledWith('/meta/enums/batch', { params: { names: 'role_type' } })
    expect(a).toEqual([{ value: 'admin', label: '管理员' }])
    expect(b).toEqual([{ value: 'admin', label: '管理员' }])
  })
})