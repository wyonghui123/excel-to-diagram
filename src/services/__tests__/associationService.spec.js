/**
 * associationService.spec.js - BO 关联管理 service 单测
 *
 * 覆盖矩阵（16 个用例）：
 * 1.  associate — 成功 + 缓存失效
 * 2.  associate — 失败 + 不失效
 * 3.  dissociate — 成功 + 缓存失效
 * 4.  dissociate — 失败 + 不失效
 * 5.  queryV2 — 缓存未命中 → 调 API → 写缓存
 * 6.  queryV2 — 缓存命中 → 不调 API
 * 7.  countV2 — 成功
 * 8.  assignV2 — 成功 + 缓存失效
 * 9.  unassignV2 — 成功 + 缓存失效
 * 10. batchAssignV2 — 成功 + 缓存失效
 * 11. batchUnassignV2 — 成功 + 缓存失效
 * 12. isSuccess — 纯函数
 * 13. extractItems — 纯函数
 * 14. buildAssocCacheKey — 纯函数
 * 15. LRU 缓存失效验证（写操作后读缓存被清除）
 * 16. clearCache — 按 objectType 清除 / 全部清除
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---- 用 vi.hoisted 提升变量，使 vi.mock factory 可访问 ----
const { mockCacheInstance, mockApiV1, mockApiV2, _cacheStore } = vi.hoisted(() => {
  const _cacheStore = new Map()
  const mockCacheInstance = {
    get: vi.fn(key => _cacheStore.get(key) ?? null),
    set: vi.fn((key, data, timeout) => { _cacheStore.set(key, data) }),
    delete: vi.fn(key => { _cacheStore.delete(key) }),
    deleteByPrefix: vi.fn(prefix => {
      for (const key of [..._cacheStore.keys()]) {
        if (key.startsWith(prefix)) _cacheStore.delete(key)
      }
    }),
    clear: vi.fn(() => { _cacheStore.clear() }),
  }
  const mockApiV2 = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  }
  const mockApiV1 = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  }
  return { mockCacheInstance, mockApiV1, mockApiV2, _cacheStore }
})

vi.mock('@/utils/lruCache', () => ({
  LRUCache: vi.fn(() => mockCacheInstance),
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: mockApiV1,
  apiV2: mockApiV2,
}))

// ---- import after mocks ----
import {
  associate,
  dissociate,
  queryV2,
  countV2,
  assignV2,
  unassignV2,
  batchAssignV2,
  batchUnassignV2,
  isSuccess,
  extractItems,
  buildAssocCacheKey,
  clearCache,
} from '@/services/associationService'

describe('associationService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    _cacheStore.clear()
  })

  // ====================================================================
  // 1. associate
  // ====================================================================
  describe('associate', () => {
    it('TC-1: 成功时调用 API 并使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ success: true })
      const result = await associate('order', 1, 'items', 100)
      expect(result.success).toBe(true)
      expect(mockApiV2.post).toHaveBeenCalledWith(
        '/bo/order/1/associations/items',
        { target_id: 100 }
      )
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })

    it('TC-2: 失败时不使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ success: false })
      const result = await associate('order', 1, 'items', 100)
      expect(result.success).toBe(false)
      expect(mockCacheInstance.deleteByPrefix).not.toHaveBeenCalled()
    })

    it('TC-2b: 带 targetType 时 body 包含 target_type', async () => {
      mockApiV2.post.mockResolvedValue({ success: true })
      await associate('order', 1, 'items', 100, 'product')
      expect(mockApiV2.post).toHaveBeenCalledWith(
        '/bo/order/1/associations/items',
        { target_id: 100, target_type: 'product' }
      )
    })
  })

  // ====================================================================
  // 2. dissociate
  // ====================================================================
  describe('dissociate', () => {
    it('TC-3: 成功时调用 API 并使缓存失效', async () => {
      mockApiV2.delete.mockResolvedValue({ success: true })
      const result = await dissociate('order', 1, 'items', 100)
      expect(result.success).toBe(true)
      expect(mockApiV2.delete).toHaveBeenCalledWith(
        '/bo/order/1/associations/items?target_id=100'
      )
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })

    it('TC-4: 失败时不使缓存失效', async () => {
      mockApiV2.delete.mockResolvedValue({ success: false })
      const result = await dissociate('order', 1, 'items', 100)
      expect(result.success).toBe(false)
      expect(mockCacheInstance.deleteByPrefix).not.toHaveBeenCalled()
    })

    it('TC-4b: 带 targetType 时 query string 包含 target_type', async () => {
      mockApiV2.delete.mockResolvedValue({ success: true })
      await dissociate('order', 1, 'items', 100, 'product')
      expect(mockApiV2.delete).toHaveBeenCalledWith(
        '/bo/order/1/associations/items?target_id=100&target_type=product'
      )
    })
  })

  // ====================================================================
  // 3. queryV2
  // ====================================================================
  describe('queryV2', () => {
    it('TC-5: 缓存未命中 → 调 API → 写缓存', async () => {
      const apiResult = { success: true, data: { items: [{ id: 1 }] } }
      mockApiV2.get.mockResolvedValue(apiResult)
      mockCacheInstance.get.mockReturnValue(null)

      const result = await queryV2('order', 1, 'items')

      expect(result).toEqual(apiResult)
      expect(mockApiV2.get).toHaveBeenCalledWith('/bo/order/1/$associations/items')
      expect(mockCacheInstance.set).toHaveBeenCalled()
    })

    it('TC-6: 缓存命中 → 不调 API', async () => {
      const cached = { success: true, data: { items: [{ id: 1 }] } }
      mockCacheInstance.get.mockReturnValue(cached)

      const result = await queryV2('order', 1, 'items')

      expect(result).toEqual(cached)
      expect(mockApiV2.get).not.toHaveBeenCalled()
      expect(mockCacheInstance.set).not.toHaveBeenCalled()
    })
  })

  // ====================================================================
  // 4. countV2
  // ====================================================================
  describe('countV2', () => {
    it('TC-7: 成功返回计数并写缓存', async () => {
      const apiResult = { success: true, data: { count: 42 } }
      mockApiV2.get.mockResolvedValue(apiResult)
      mockCacheInstance.get.mockReturnValue(null)

      const result = await countV2('order', 1, 'items')

      expect(result).toEqual(apiResult)
      expect(mockApiV2.get).toHaveBeenCalledWith('/bo/order/1/$associations/items/count')
      expect(mockCacheInstance.set).toHaveBeenCalled()
    })
  })

  // ====================================================================
  // 5. assignV2 / unassignV2
  // ====================================================================
  describe('assignV2', () => {
    it('TC-8: 成功时使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ success: true })
      const result = await assignV2('order', 1, 'items', { target_id: 100 })
      expect(result.success).toBe(true)
      expect(mockApiV2.post).toHaveBeenCalledWith(
        '/bo/order/1/$associations/items/assign',
        { target_id: 100 }
      )
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })

    it('TC-8b: 204 No Content 返回 true 并使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ status: 204 })
      const result = await assignV2('order', 1, 'items', { target_id: 100 })
      expect(result).toBe(true)
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })
  })

  describe('unassignV2', () => {
    it('TC-9: 成功时使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ success: true })
      const result = await unassignV2('order', 1, 'items', { target_id: 100 })
      expect(result.success).toBe(true)
      expect(mockApiV2.post).toHaveBeenCalledWith(
        '/bo/order/1/$associations/items/unassign',
        { target_id: 100 }
      )
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })

    it('TC-9b: 204 No Content 返回 true 并使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ status: 204 })
      const result = await unassignV2('order', 1, 'items', { target_id: 100 })
      expect(result).toBe(true)
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })
  })

  // ====================================================================
  // 6. batchAssignV2 / batchUnassignV2
  // ====================================================================
  describe('batchAssignV2', () => {
    it('TC-10: 成功时使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ success: true })
      const result = await batchAssignV2('order', 1, 'items', [1, 2, 3])
      expect(result.success).toBe(true)
      expect(mockApiV2.post).toHaveBeenCalledWith(
        '/bo/order/1/$associations/items/batch_assign',
        { target_ids: [1, 2, 3] }
      )
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })
  })

  describe('batchUnassignV2', () => {
    it('TC-11: 成功时使缓存失效', async () => {
      mockApiV2.post.mockResolvedValue({ success: true })
      const result = await batchUnassignV2('order', 1, 'items', [1, 2])
      expect(result.success).toBe(true)
      expect(mockApiV2.post).toHaveBeenCalledWith(
        '/bo/order/1/$associations/items/batch_unassign',
        { target_ids: [1, 2] }
      )
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalled()
    })
  })

  // ====================================================================
  // 7. isSuccess — 纯函数
  // ====================================================================
  describe('isSuccess', () => {
    it('TC-12: 各种输入的正确判断', () => {
      expect(isSuccess(true)).toBe(true)
      expect(isSuccess({ success: true })).toBe(true)
      expect(isSuccess({ success: true, data: {} })).toBe(true)
      expect(isSuccess(false)).toBe(false)
      expect(isSuccess(null)).toBe(false)
      expect(isSuccess(undefined)).toBe(false)
      expect(isSuccess({ success: false })).toBe(false)
      expect(isSuccess({})).toBe(false)
      expect(isSuccess('ok')).toBe(false)
    })
  })

  // ====================================================================
  // 8. extractItems — 纯函数
  // ====================================================================
  describe('extractItems', () => {
    it('TC-13: 各种输入结构的正确提取', () => {
      // { data: { items: [...] } }
      expect(extractItems({ data: { items: [1, 2] } })).toEqual([1, 2])
      // { items: [...] }
      expect(extractItems({ items: [3] })).toEqual([3])
      // [...] 直接数组
      expect(extractItems([4, 5])).toEqual([4, 5])
      // null / undefined / 空对象
      expect(extractItems(null)).toEqual([])
      expect(extractItems(undefined)).toEqual([])
      expect(extractItems({})).toEqual([])
    })
  })

  // ====================================================================
  // 9. buildAssocCacheKey — 纯函数
  // ====================================================================
  describe('buildAssocCacheKey', () => {
    it('TC-14: 构建正确的缓存键', () => {
      const key = buildAssocCacheKey('order', 1, 'items', { page: 1 })
      expect(key).toBe('order:1:items:{"page":"1"}')
    })

    it('TC-14b: 无参数时缓存键包含空对象', () => {
      const key = buildAssocCacheKey('order', 1, 'items')
      expect(key).toBe('order:1:items:{}')
    })

    it('TC-14c: 过滤 null/undefined/空字符串参数', () => {
      const key = buildAssocCacheKey('order', 1, 'items', { page: 1, q: null, r: undefined, s: '' })
      expect(key).toBe('order:1:items:{"page":"1"}')
    })
  })

  // ====================================================================
  // 10. LRU 缓存失效验证
  // ====================================================================
  describe('LRU 缓存失效验证', () => {
    it('TC-15: 写操作后读缓存被清除', async () => {
      // 先让 queryV2 写缓存
      const apiResult = { success: true, data: { items: [{ id: 1 }] } }
      mockApiV2.get.mockResolvedValue(apiResult)
      mockCacheInstance.get.mockReturnValue(null)
      await queryV2('order', 1, 'items')

      // 验证 set 被调用（缓存已写入）
      expect(mockCacheInstance.set).toHaveBeenCalled()

      // 执行写操作（associate）
      mockApiV2.post.mockResolvedValue({ success: true })
      await associate('order', 1, 'items', 100)

      // 验证 deleteByPrefix 被调用（缓存被清除）
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalledWith('order:assoc:items:1:')
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalledWith('order:assocV2:items:1:')
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalledWith('order:assocCount:items:1:')
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalledWith('order:query:')
    })
  })

  // ====================================================================
  // 11. clearCache
  // ====================================================================
  describe('clearCache', () => {
    it('TC-16: 按 objectType 清除缓存', () => {
      clearCache('order')
      expect(mockCacheInstance.deleteByPrefix).toHaveBeenCalledWith('order:')
    })

    it('TC-16b: 无参数时清除全部缓存', () => {
      clearCache()
      expect(mockCacheInstance.clear).toHaveBeenCalled()
    })
  })
})
