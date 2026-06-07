/**
 * enumService 单元测试
 *
 * 目标：覆盖 EnumService 当前 API
 *  - loadOptions / preload
 *  - 缓存管理 (clearCache / clearCacheFor)
 *  - getCacheStatus / getPerformanceStats
 *  - _normalizeEnumValues (内部规范化)
 *
 * 策略：mock @/utils/httpClient 的 apiV1
 * 使用 vi.hoisted 避免 isolate:false + 并行 worker 下的 mock 链断裂
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { EnumService } from '../enumService.js'

// vi.hoisted 让 mock 函数引用在 import 之前就创建
const mocks = vi.hoisted(() => ({
  apiV1Get: vi.fn(),
  apiV2Get: vi.fn()
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: mocks.apiV1Get },
  apiV2: { get: mocks.apiV2Get }
}))

import { apiV1 } from '@/utils/httpClient'

// 工具：构造 httpClient 标准响应
function okResp(data) {
  return {
    success: true,
    data,
    message: '',
    httpStatus: 200,
    traceId: 'trace-test'
  }
}

function failResp(httpStatus, message = 'error') {
  return {
    success: false,
    data: null,
    message,
    code: 'ERR',
    httpStatus,
    traceId: 'trace-test'
  }
}

describe('EnumService', () => {
  beforeEach(() => {
    // 直接重置 hoisted mock（确保即使 import 被重置也生效）
    mocks.apiV1Get.mockReset()
    EnumService.clearCache()
    EnumService.resetPerformanceStats()
  })

  afterEach(() => {
    mocks.apiV1Get.mockReset()
    EnumService.clearCache()
  })

  describe('loadOptions', () => {
    it('应该从高速端点加载枚举选项并规范化为 value/label', async () => {
      const mockData = [
        { code: 'active', name: '活跃' },
        { code: 'inactive', name: '非活跃' }
      ]
      apiV1.get.mockResolvedValueOnce(okResp(mockData))

      const result = await EnumService.loadOptions('test_enum')

      expect(result).toHaveLength(2)
      expect(result[0].value).toBe('active')
      expect(result[0].label).toBe('活跃')
      expect(apiV1.get).toHaveBeenCalledTimes(1)
      expect(apiV1.get).toHaveBeenCalledWith(
        expect.stringContaining('/enums/test_enum/options'),
        expect.any(Object)
      )
    })

    it('高速端点 404 时应该降级到标准端点', async () => {
      const fallbackData = [{ code: 'fallback', name: '降级' }]
      apiV1.get
        .mockResolvedValueOnce(failResp(404, 'Not found'))
        .mockResolvedValueOnce(okResp(fallbackData))

      const result = await EnumService.loadOptions('test_enum')

      expect(result).toHaveLength(1)
      expect(result[0].value).toBe('fallback')
      expect(apiV1.get).toHaveBeenCalledTimes(2)
      expect(apiV1.get).toHaveBeenNthCalledWith(
        2,
        expect.stringContaining('/enum-types/test_enum/values'),
        expect.any(Object)
      )
    })

    it('应该使用缓存（第二次不调 API）', async () => {
      const mockData = [{ code: 'c1', name: '缓存' }]
      apiV1.get.mockResolvedValue(okResp(mockData))

      const r1 = await EnumService.loadOptions('cached_enum')
      const r2 = await EnumService.loadOptions('cached_enum')

      expect(r1).toEqual(r2)
      expect(apiV1.get).toHaveBeenCalledTimes(1)
    })

    it('空 enumTypeId 应该抛出错误', async () => {
      await expect(EnumService.loadOptions('')).rejects.toThrow(/enumTypeId is required/)
      await expect(EnumService.loadOptions(null)).rejects.toThrow(/enumTypeId is required/)
    })

    it('API 失败时（非 404）应该抛出错误', async () => {
      apiV1.get.mockResolvedValue(failResp(500, 'Server error'))

      await expect(EnumService.loadOptions('fail_enum')).rejects.toThrow()
    })
  })

  describe('preload', () => {
    it('应该预加载多个枚举并返回 Map', async () => {
      apiV1.get.mockResolvedValue(
        okResp([{ code: 'c1', name: 'n1' }])
      )

      const result = await EnumService.preload(['enum1', 'enum2'])

      expect(result).toBeInstanceOf(Map)
      expect(result.size).toBe(2)
      expect(result.get('enum1')).toHaveLength(1)
      expect(result.get('enum2')).toHaveLength(1)
    })

    it('空数组应该返回空 Map', async () => {
      const result = await EnumService.preload([])
      expect(result).toBeInstanceOf(Map)
      expect(result.size).toBe(0)
    })
  })

  describe('缓存管理', () => {
    it('clearCache 应该清空所有缓存', async () => {
      apiV1.get.mockResolvedValue(okResp([{ code: 'c', name: 'n' }]))

      await EnumService.loadOptions('cache_test_a')
      await EnumService.loadOptions('cache_test_b')
      expect(EnumService._cache.size).toBe(2)

      EnumService.clearCache()
      expect(EnumService._cache.size).toBe(0)
    })

    it('clearCacheFor 应该只清空指定枚举', async () => {
      apiV1.get.mockResolvedValue(okResp([{ code: 'c', name: 'n' }]))

      await EnumService.loadOptions('specific_a')
      await EnumService.loadOptions('specific_b')
      expect(EnumService._cache.size).toBe(2)

      EnumService.clearCacheFor('specific_a')
      expect(EnumService._cache.has('specific_a')).toBe(false)
      expect(EnumService._cache.has('specific_b')).toBe(true)
      expect(EnumService._cache.size).toBe(1)
    })
  })

  describe('getCacheStatus', () => {
    it('空缓存应该返回 total=0', () => {
      const status = EnumService.getCacheStatus()
      expect(status.total).toBe(0)
      expect(status.maxSize).toBe(100)
      expect(status.entries).toEqual([])
    })

    it('有缓存时应该返回条目信息', async () => {
      apiV1.get.mockResolvedValue(okResp([{ code: 'c1', name: 'n1' }]))

      await EnumService.loadOptions('status_test')

      const status = EnumService.getCacheStatus()
      expect(status.total).toBe(1)
      expect(status.entries).toHaveLength(1)
      expect(status.entries[0].enumTypeId).toBe('status_test')
      expect(status.entries[0].size).toBe(1)
    })
  })

  describe('getPerformanceStats', () => {
    it('应该返回包含核心统计字段的对象', () => {
      const stats = EnumService.getPerformanceStats()
      expect(stats).toHaveProperty('totalRequests')
      expect(stats).toHaveProperty('cacheHits')
      expect(stats).toHaveProperty('cacheMisses')
      expect(stats).toHaveProperty('cacheHitRate')
      expect(stats).toHaveProperty('endpointUsage')
    })
  })

  describe('_normalizeEnumValues', () => {
    it('应该将 code/name 格式转换为 value/label 并保留原字段', () => {
      const result = EnumService._normalizeEnumValues([
        { code: 'c1', name: 'n1' },
        { code: 'c2', name: 'n2' }
      ])
      expect(result).toEqual([
        { value: 'c1', label: 'n1', code: 'c1', name: 'n1' },
        { value: 'c2', label: 'n2', code: 'c2', name: 'n2' }
      ])
    })

    it('非数组输入应该返回空数组', () => {
      expect(EnumService._normalizeEnumValues(null)).toEqual([])
      expect(EnumService._normalizeEnumValues(undefined)).toEqual([])
      expect(EnumService._normalizeEnumValues('not array')).toEqual([])
      expect(EnumService._normalizeEnumValues({})).toEqual([])
    })

    it('应该兼容 value/label 格式', () => {
      const result = EnumService._normalizeEnumValues([
        { value: 'v1', label: 'l1' }
      ])
      expect(result).toEqual([
        { value: 'v1', label: 'l1', code: 'v1', name: 'l1' }
      ])
    })
  })
})
