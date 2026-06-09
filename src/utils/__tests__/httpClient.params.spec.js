/**
 * Regression test: httpClient 必须把 options.params 拼到 URL query string
 *
 * 背景: 2026-06-08 发现 httpClient.request() 直接用 `${baseUrl}${path}` 构造 URL,
 *       完全忽略 options.params, 导致 loadConditionRules({ role_id: 1803 })
 *       实际请求是 GET /api/v1/permission-rules (无 query string),
 *       后端走 get_all_rules() 分支, 任意角色都看到全部规则.
 *
 * 受影响的接口: 13+ 处 (见 permissionService.js 全部 { params } 调用)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    sessionReady: true,
    isLoggedIn: true,
    csrfToken: 'test-csrf',
  }),
}))

vi.mock('@/utils/api', () => ({
  API_BASE: '/api/v1',
  API_BASE_V2: '/api/v2',
  getHeaders: () => ({ 'Content-Type': 'application/json', 'X-CSRF': 'test-csrf' }),
}))

vi.mock('@/utils/logger', () => ({
  logger: { debug: vi.fn(), warn: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

function mockSuccessResponse(data = {}) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ success: true, data, message: '' }),
  })
}

describe('httpClient query params (regression: get_all_rules bug)', () => {
  let apiV1, clearInflightCache

  beforeEach(async () => {
    vi.clearAllMocks()
    const mod = await import('../httpClient.js')
    apiV1 = mod.apiV1
    clearInflightCache = mod.clearInflightCache
    clearInflightCache()
  })

  afterEach(() => {
    clearInflightCache()
  })

  it('应该把单个 string 参数拼到 URL (主问题: role_id 丢失)', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/permission-rules', { params: { role_id: '1803' } })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toBe('/api/v1/permission-rules?role_id=1803')
  })

  it('应该把 number 参数拼到 URL', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/roles', { params: { page: 2 } })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toBe('/api/v1/roles?page=2')
  })

  it('应该把多个参数拼到 URL', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/users', { params: { keyword: 'admin', page_size: 20 } })

    const calledUrl = mockFetch.mock.calls[0][0]
    // URLSearchParams 顺序: 插入顺序
    expect(calledUrl).toContain('/api/v1/users?')
    expect(calledUrl).toContain('keyword=admin')
    expect(calledUrl).toContain('page_size=20')
  })

  it('不传 params 时 URL 不应带 ?', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/users')

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toBe('/api/v1/users')
  })

  it('params 为空对象时 URL 不应带 ?', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/users', { params: {} })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toBe('/api/v1/users')
  })

  it('应该跳过 null 和 undefined 值', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/users', { params: { keyword: 'a', page: null, size: undefined } })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('keyword=a')
    expect(calledUrl).not.toContain('page=')
    expect(calledUrl).not.toContain('size=')
  })

  it('应该对值做 URL 编码 (中文/特殊字符)', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/search', { params: { q: '权限 测试' } })

    const calledUrl = mockFetch.mock.calls[0][0]
    // URLSearchParams 用 application/x-www-form-urlencoded 编码: 空格 → '+', 中文 → %E7...
    // 用 URLSearchParams 自己解析验证 (decodeURIComponent 不处理 '+')
    const qs = calledUrl.split('?')[1]
    const parsed = new URLSearchParams(qs).get('q')
    expect(parsed).toBe('权限 测试')
  })

  it('apiV2 也应该支持 params (跟 apiV1 一致)', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    const mod = await import('../httpClient.js')
    await mod.apiV2.get('/bo/role', { params: { limit: 50 } })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('/api/v2/bo/role?')
    expect(calledUrl).toContain('limit=50')
  })

  it('应该对带不同 params 的请求独立去重 (不是按 URL 单独去重)', async () => {
    // 关键: GET /permission-rules?role_id=1 和 ?role_id=2 是不同请求
    // dedupe cache key 应该包含 params
    mockFetch.mockImplementation(() => mockSuccessResponse([]))

    const p1 = apiV1.get('/permission-rules', { params: { role_id: 1 }, dedupe: false })
    const p2 = apiV1.get('/permission-rules', { params: { role_id: 2 }, dedupe: false })
    await Promise.all([p1, p2])

    expect(mockFetch).toHaveBeenCalledTimes(2)
    const urls = mockFetch.mock.calls.map(c => c[0])
    expect(urls).toContain('/api/v1/permission-rules?role_id=1')
    expect(urls).toContain('/api/v1/permission-rules?role_id=2')
  })

  it('download (responseType=blob) 也应该支持 params', async () => {
    mockFetch.mockImplementation(() => Promise.resolve({
      ok: true,
      status: 200,
      blob: () => Promise.resolve(new Blob(['test'])),
    }))

    await apiV1.download('/files/export', { params: { format: 'xlsx' } })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('/api/v1/files/export?')
    expect(calledUrl).toContain('format=xlsx')
  })

  it('数组值应展开为同名多次参数 (用于后端 SQL IN / getlist)', async () => {
    // [FIX-2026-06-08] 之前 JSON.stringify() 错误:
    //   filter_product_id: [18, 19] → ?filter_product_id=%5B18%2C19%5D (单值)
    //   后端 Flask request.args.getlist('filter_product_id') 拿到 ['"[18,19]"']
    //   SQL IN ('[18,19]') 不匹配任何记录
    // 现在应展开: ?filter_product_id=18&filter_product_id=19
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/management-dimensions/version/instances', {
      params: { filter_product_id: [18, 19, 16, 1] }
    })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('filter_product_id=18')
    expect(calledUrl).toContain('filter_product_id=19')
    expect(calledUrl).toContain('filter_product_id=16')
    expect(calledUrl).toContain('filter_product_id=1')

    // 不应包含 JSON 数组字符串
    expect(calledUrl).not.toContain('%5B18')
    expect(calledUrl).not.toContain('18%2C19')

    // 同名参数出现 4 次
    const matches = calledUrl.match(/filter_product_id=/g)
    expect(matches && matches.length).toBe(4)
  })

  it('空数组应被跳过 (不发任何 filter_ 参数)', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/management-dimensions/version/instances', {
      params: { filter_product_id: [] }
    })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).not.toContain('filter_product_id=')
  })

  it('数组里的 null/空字符串应被跳过', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/test', {
      params: { ids: [1, null, 2, '', undefined, 3] }
    })

    const calledUrl = mockFetch.mock.calls[0][0]
    expect(calledUrl).toContain('ids=1')
    expect(calledUrl).toContain('ids=2')
    expect(calledUrl).toContain('ids=3')
    const matches = calledUrl.match(/ids=/g)
    expect(matches && matches.length).toBe(3)
  })

  it('普通对象 (非数组) 应 JSON 化', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse([]))
    await apiV1.get('/test', {
      params: { filter_meta: { a: 1, b: 2 } }
    })

    const calledUrl = mockFetch.mock.calls[0][0]
    // URL 编码后的 JSON 字符串
    const decoded = decodeURIComponent(calledUrl)
    expect(decoded).toContain('filter_meta=')
    expect(decoded).toContain('{"a":1,"b":2}')
  })
})