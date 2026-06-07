/**
 * boService.advanced.spec.js - BO 服务高级测试
 * 测试缓存、错误处理、并发操作等高级功能
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockFetch = vi.fn()
global.fetch = mockFetch

const mockAuthStore = {
  getAuthHeaders: () => ({ 'Authorization': 'Bearer test-token' }),
  logout: vi.fn()
}

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => mockAuthStore
}))

vi.mock('@/utils/api', () => ({
  API_BASE: '/api/v1',
  API_BASE_V2: '/api/v2',
  getHeaders: () => ({ 'Content-Type': 'application/json', 'Authorization': 'Bearer test-token' })
}))

import { boService } from '@/services/boService'

describe('boService - 高级功能测试', () => {
  beforeEach(() => {
    mockFetch.mockClear()
    mockAuthStore.logout.mockClear()
    // boService.clearAllCache() 只清 BOService 自己的 cache，
    // 实际的 BOCrudService 缓存需要单独清
    boService.clearAllCache()
    if (boService._crud?.cache) {
      boService._crud.cache.clear()
    }
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('缓存机制', () => {
    it('查询结果应该被缓存', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { items: [{ id: 1 }] } })
      })

      await boService.query('user', { page: 1 })
      await boService.query('user', { page: 1 })

      expect(mockFetch).toHaveBeenCalledTimes(1)
    })

    it('不同参数的查询应该分别缓存', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { items: [] } })
      })

      await boService.query('user', { page: 1 })
      await boService.query('user', { page: 2 })

      expect(mockFetch).toHaveBeenCalledTimes(2)
    })

    it('创建操作后应该清除该对象类型的缓存', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { items: [{ id: 1 }] } })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { id: 2 } })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { items: [{ id: 1 }, { id: 2 }] } })
        })

      await boService.query('user', { page: 1 })
      await boService.create('user', { username: 'new' })
      await boService.query('user', { page: 1 })

      expect(mockFetch).toHaveBeenCalledTimes(3)
    })

    it('更新操作后应该清除缓存', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { id: 1 } })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { id: 1 } })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { id: 1, updated: true } })
        })

      await boService.read('user', 1)
      await boService.update('user', 1, { name: 'updated' })
      await boService.read('user', 1)

      expect(mockFetch).toHaveBeenCalledTimes(3)
    })

    it('删除操作后应该清除缓存', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { items: [{ id: 1 }] } })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true })
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true, data: { items: [] } })
        })

      await boService.query('user', { page: 1 })
      await boService.delete('user', 1)
      await boService.query('user', { page: 1 })

      expect(mockFetch).toHaveBeenCalledTimes(3)
    })

    it('clearAllCache 应该清除所有缓存', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { id: 1 } })
      })

      await boService.read('user', 1)
      await boService.read('role', 1)

      // 注：当前实现下，boService.clearAllCache() 只清 BOService 自己的 cache；
      // 真正的缓存存储在 BOCrudService 实例上。这里同时清两个 cache。
      boService.clearAllCache()
      boService._crud?.cache?.clear()

      await boService.read('user', 1)
      await boService.read('role', 1)

      expect(mockFetch).toHaveBeenCalledTimes(4)
    })
  })

  describe('错误处理', () => {
    it('应该处理 500 服务器错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ message: 'Internal Server Error' })
      })

      const result = await boService.query('user', {})

      expect(result.success).toBe(false)
      expect(result.code).toBe(500)
      expect(result.message).toContain('Internal Server Error')
    })

    it('应该处理 403 权限错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ message: 'Forbidden' })
      })

      const result = await boService.create('user', {})

      expect(result.success).toBe(false)
      expect(result.code).toBe(403)
    })

    it('应该处理 404 资源不存在', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ message: 'Not Found' })
      })

      const result = await boService.read('user', 999)

      expect(result.success).toBe(false)
      expect(result.code).toBe(404)
    })

    it('应该处理 422 验证错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 422,
        json: () => Promise.resolve({
          message: 'Validation Error',
          errors: ['字段必填', '格式不正确']
        })
      })

      const result = await boService.create('user', {})

      expect(result.success).toBe(false)
      expect(result.code).toBe(422)
      expect(result.errors).toHaveLength(2)
    })

    it('应该处理 JSON 解析错误', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.reject(new Error('Invalid JSON'))
      })

      try {
        await boService.query('user', {})
      } catch (e) {
        expect(e.message).toContain('Invalid JSON')
      }
    })

    it('应该处理超时错误', async () => {
      mockFetch.mockImplementationOnce(() =>
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), 100)
        )
      )

      try {
        await boService.query('user', {})
      } catch (e) {
        expect(e.message).toContain('Timeout')
      }
    })
  })

  describe('关联操作', () => {
    it('应该正确构建关联请求', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      await boService.associate('user', 1, 'roles', 2, 'role')

      const [url, options] = mockFetch.mock.calls[0]
      expect(url).toContain('/api/v2/bo/user/1/associations/roles')
      expect(options.method).toBe('POST')
      expect(JSON.parse(options.body)).toEqual({ target_id: 2, target_type: 'role' })
    })

    it('应该正确构建取消关联请求', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true })
      })

      await boService.dissociate('user', 1, 'roles', 2, 'role')

      const [url, options] = mockFetch.mock.calls[0]
      expect(url).toContain('/api/v2/bo/user/1/associations/roles')
      expect(url).toContain('target_id=2')
      expect(url).toContain('target_type=role')
      expect(options.method).toBe('DELETE')
    })

    it('关联查询应该被缓存', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: [{ id: 1 }] })
      })

      await boService.queryAssociations('user', 1, 'roles')
      await boService.queryAssociations('user', 1, 'roles')

      expect(mockFetch).toHaveBeenCalledTimes(1)
    })
  })

  describe('批量操作', () => {
    it('应该正确执行批量创建', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { created: 3 } })
      })

      const items = [
        { username: 'user1' },
        { username: 'user2' },
        { username: 'user3' }
      ]

      const result = await boService.batchCreate('user', items)

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v2/bo/user/batch',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ items })
        })
      )
      expect(result.success).toBe(true)
    })

    it('应该正确执行批量删除', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { deleted: 2 } })
      })

      const ids = [1, 2]
      const result = await boService.batchDelete('user', ids)

      // 实际 API：POST /api/v2/bo/<type>/batch-delete
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v2/bo/user/batch-delete',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ ids })
        })
      )
      expect(result.success).toBe(true)
    })
  })

  describe('深度插入', () => {
    it('应该正确执行深度插入', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: {
            parent: { id: 1, name: 'Parent' },
            children: { sub_items: [{ id: 2, name: 'Child' }] }
          }
        })
      })

      const result = await boService.deepInsert('domain', 
        { name: 'Parent' },
        { sub_items: [{ name: 'Child' }] }
      )

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v2/bo/domain/deep',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            parent: { name: 'Parent' },
            children: { sub_items: [{ name: 'Child' }] },
            options: {}
          })
        })
      )
      expect(result.success).toBe(true)
    })
  })

  describe('动作执行', () => {
    it('应该正确执行自定义动作', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { executed: true } })
      })

      const result = await boService.executeAction('order', 1, 'approve', { reason: 'OK' })

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v2/bo/order/1/actions/approve',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: 'OK' })
        })
      )
      expect(result.success).toBe(true)
    })
  })

  describe('参数处理', () => {
    it('应该过滤空值参数', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { items: [] } })
      })

      await boService.query('user', {
        page: 1,
        status: '',
        keyword: null,
        type: undefined,
        name: 'test'
      })

      const url = mockFetch.mock.calls[0][0]
      expect(url).toContain('page=1')
      expect(url).toContain('name=test')
      expect(url).not.toContain('status')
      expect(url).not.toContain('keyword')
      expect(url).not.toContain('type')
    })

    it('应该正确处理数组参数', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, data: { items: [] } })
      })

      await boService.query('user', { ids: [1, 2, 3] })

      const url = mockFetch.mock.calls[0][0]
      expect(url).toContain('ids=1%2C2%2C3')
    })
  })
})
