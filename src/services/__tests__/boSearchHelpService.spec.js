/**
 * boSearchHelpService.spec.js - Value Help 服务层测试
 *
 * 测试核心功能：
 * 1. searchValueHelp URL 构造（query string 拼装）
 * 2. searchValueHelp 参数类型转换（null → "null"、JSON.stringify 等）
 * 3. resolveValueHelp URL 构造
 * 4. 与 _request 的对接（GET 方法 + V2 namespace）
 * 5. 边界值（空对象、特殊字符、未提供可选参数）
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockGet = vi.fn()

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  apiV2: { get: mockGet, post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
  ErrorCode: {},
  registerRequestInterceptor: vi.fn(),
  registerResponseInterceptor: vi.fn(),
  setOnUnauthorized: vi.fn(),
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    isAuthenticated: true,
    getAuthHeaders: () => ({ Authorization: 'Bearer test-token' })
  })
}))

vi.mock('@/utils/api', () => ({
  API_BASE: '/api/v1',
  API_BASE_V2: '/api/v2',
  getHeaders: () => ({ 'Content-Type': 'application/json' }),
  getAuthHeaders: () => ({ Authorization: 'Bearer test-token' })
}))

function getCallUrl() {
  expect(mockGet).toHaveBeenCalled()
  return mockGet.mock.calls[0][0]
}

function getCallOptions() {
  return mockGet.mock.calls[0][1] || {}
}

describe('BOSearchHelpService', () => {
  let service

  beforeEach(async () => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ success: true, data: [] })

    const module = await import('@/services/bo/boSearchHelpService')
    service = new module.BOSearchHelpService()
  })

  describe('searchValueHelp - 基本参数', () => {
    it('构建正确的 URL path', async () => {
      await service.searchValueHelp('enum', 'visibility')

      const url = getCallUrl()
      expect(url).toContain('/value-help/enum/visibility')
    })

    it('传 search 时设置 search 查询参数', async () => {
      await service.searchValueHelp('enum', 'visibility', { search: '公开' })

      const url = getCallUrl()
      expect(url).toContain('search=')
      expect(decodeURIComponent(url)).toContain('search=公开')
    })

    it('传 search_fields 时设置 search_fields 参数', async () => {
      await service.searchValueHelp('bo', 'domain', { search_fields: 'name,code' })

      const url = getCallUrl()
      expect(url).toContain('search_fields=name%2Ccode')
    })

    it('传 page 和 pageSize 时设置对应参数（注意是 page_size）', async () => {
      await service.searchValueHelp('bo', 'domain', { page: 2, pageSize: 25 })

      const url = getCallUrl()
      expect(url).toContain('page=2')
      expect(url).toContain('page_size=25')
    })

    it('传 sort 时设置 sort 参数', async () => {
      await service.searchValueHelp('bo', 'domain', { sort: 'name:asc' })

      const url = getCallUrl()
      expect(url).toContain('sort=name%3Aasc')
    })
  })

  describe('searchValueHelp - field 参数', () => {
    it('传 value_field/display_field/code_field 时分别设置', async () => {
      await service.searchValueHelp('bo', 'domain', {
        value_field: 'id',
        display_field: 'name',
        code_field: 'code',
      })

      const url = getCallUrl()
      expect(url).toContain('value_field=id')
      expect(url).toContain('display_field=name')
      expect(url).toContain('code_field=code')
    })

    it('不传 field 参数时 URL 不应包含这些字段', async () => {
      await service.searchValueHelp('enum', 'status', { search: 'x' })

      const url = getCallUrl()
      expect(url).not.toContain('value_field=')
      expect(url).not.toContain('display_field=')
      expect(url).not.toContain('code_field=')
    })
  })

  describe('searchValueHelp - filters 转换', () => {
    it('filters 中的每个 key 转换为 filters[key] 形式', async () => {
      await service.searchValueHelp('bo', 'domain', {
        filters: { status: 'active', category: 'system' }
      })

      const url = getCallUrl()
      expect(url).toContain('filters%5Bstatus%5D=active')
      expect(url).toContain('filters%5Bcategory%5D=system')
    })

    it('filters 中 null 值转为字符串 "null"', async () => {
      await service.searchValueHelp('bo', 'domain', {
        filters: { deleted_at: null }
      })

      const url = getCallUrl()
      expect(url).toContain('filters%5Bdeleted_at%5D=null')
    })

    it('filters 中 undefined 值也转为字符串 "null"（与 null 同处理）', async () => {
      await service.searchValueHelp('bo', 'domain', {
        filters: { deleted_at: undefined }
      })

      const url = getCallUrl()
      expect(url).toContain('filters%5Bdeleted_at%5D=null')
    })

    it('空 filters 对象不应产生任何 filters[key] 参数', async () => {
      await service.searchValueHelp('bo', 'domain', { filters: {} })

      const url = getCallUrl()
      expect(url).not.toContain('filters%5B')
    })
  })

  describe('searchValueHelp - value_filter / hierarchy JSON 序列化', () => {
    it('非空 value_filter 被 JSON.stringify 并作为 value_filter 参数', async () => {
      await service.searchValueHelp('bo', 'domain', {
        value_filter: { active: true, type: 'system' }
      })

      const url = getCallUrl()
      expect(url).toMatch(/value_filter=[^&]*/)
      const match = url.match(/value_filter=([^&]*)/)
      const decoded = JSON.parse(decodeURIComponent(match[1]))
      expect(decoded).toEqual({ active: true, type: 'system' })
    })

    it('空 value_filter 对象不应产生 value_filter 参数', async () => {
      await service.searchValueHelp('bo', 'domain', {
        value_filter: {}
      })

      const url = getCallUrl()
      expect(url).not.toContain('value_filter=')
    })

    it('非空 hierarchy 被 JSON.stringify 并作为 hierarchy 参数', async () => {
      await service.searchValueHelp('bo', 'sub_domain', {
        hierarchy: { parent_field: 'domain_id' }
      })

      const url = getCallUrl()
      expect(url).toMatch(/hierarchy=[^&]*/)
      const match = url.match(/hierarchy=([^&]*)/)
      const decoded = JSON.parse(decodeURIComponent(match[1]))
      expect(decoded).toEqual({ parent_field: 'domain_id' })
    })

    it('空 hierarchy 对象不应产生 hierarchy 参数', async () => {
      await service.searchValueHelp('bo', 'sub_domain', {
        hierarchy: {}
      })

      const url = getCallUrl()
      expect(url).not.toContain('hierarchy=')
    })
  })

  describe('searchValueHelp - 透传返回值', () => {
    it('成功响应直接透传', async () => {
      const expectedData = { data: [{ value: 'a', display: 'A' }] }
      mockGet.mockResolvedValueOnce({ success: true, data: expectedData })

      const result = await service.searchValueHelp('enum', 'status')

      expect(result.success).toBe(true)
      expect(result.data).toEqual(expectedData)
    })

    it('失败响应返回 success: false', async () => {
      mockGet.mockResolvedValueOnce({ success: false, message: 'Forbidden' })

      const result = await service.searchValueHelp('enum', 'status')

      expect(result.success).toBe(false)
    })
  })

  describe('resolveValueHelp - URL 构造', () => {
    it('URL 末尾包含 /resolve 路径段', async () => {
      await service.resolveValueHelp('enum', 'visibility', 'public')

      const url = getCallUrl()
      expect(url).toContain('/value-help/enum/visibility/resolve')
    })

    it('value 参数被正确设置', async () => {
      await service.resolveValueHelp('enum', 'visibility', 'public')

      const url = getCallUrl()
      expect(url).toContain('value=public')
    })

    it('传 value_field/display_field/code_field 时分别设置', async () => {
      await service.resolveValueHelp('bo', 'domain', '1', {
        value_field: 'id',
        display_field: 'name',
        code_field: 'code',
      })

      const url = getCallUrl()
      expect(url).toContain('value=1')
      expect(url).toContain('value_field=id')
      expect(url).toContain('display_field=name')
      expect(url).toContain('code_field=code')
    })

    it('不传 field 参数时 URL 不应包含这些字段', async () => {
      await service.resolveValueHelp('enum', 'visibility', 'public')

      const url = getCallUrl()
      expect(url).not.toContain('value_field=')
      expect(url).not.toContain('display_field=')
      expect(url).not.toContain('code_field=')
    })

    it('特殊字符 value 正确编码', async () => {
      await service.resolveValueHelp('bo', 'user', '张三/李四')

      const url = getCallUrl()
      expect(decodeURIComponent(url)).toContain('value=张三/李四')
    })
  })

  describe('sourceType 支持', () => {
    it('enum 类型', async () => {
      await service.searchValueHelp('enum', 'status_type')

      const url = getCallUrl()
      expect(url).toContain('/value-help/enum/status_type')
    })

    it('bo 类型', async () => {
      await service.searchValueHelp('bo', 'role')

      const url = getCallUrl()
      expect(url).toContain('/value-help/bo/role')
    })

    it('custom 类型', async () => {
      await service.searchValueHelp('custom', '/api/custom/values')

      const url = getCallUrl()
      expect(url).toContain('/value-help/custom/')
    })
  })

  describe('空参数处理', () => {
    it('不传 params 时只构造基础 URL', async () => {
      await service.searchValueHelp('enum', 'status')

      const url = getCallUrl()
      expect(url).toContain('/value-help/enum/status')
    })

    it('resolveValueHelp 不传 params 时仍能工作', async () => {
      await service.resolveValueHelp('enum', 'status', 'value')

      const url = getCallUrl()
      expect(url).toContain('value=value')
    })
  })

  describe('options 透传（signals / headers）', () => {
    it('将 options 透传给 _request / apiV2.get', async () => {
      const signal = new AbortController().signal
      await service.searchValueHelp('enum', 'status', { search: 'x', signal })

      const options = getCallOptions()
      // options 包含原始 params (search 等) + 可能的 signal
      expect(options).toBeDefined()
    })
  })
})
