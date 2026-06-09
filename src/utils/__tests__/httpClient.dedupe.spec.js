/**
 * FR-017: httpClient in-flight GET 请求去重 单测
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock fetch
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

// Mock auth store
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    sessionReady: true,
    isLoggedIn: true,
    csrfToken: 'test-csrf',
  }),
}))

// Mock api utils
vi.mock('@/utils/api', () => ({
  API_BASE: '/api/v1',
  API_BASE_V2: '/api/v2',
  getHeaders: () => ({ 'Content-Type': 'application/json', 'X-CSRF': 'test-csrf' }),
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: { debug: vi.fn(), warn: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

describe('httpClient in-flight deduplication (FR-017)', () => {
  let apiV1, clearInflightCache, getInflightCount

  beforeEach(async () => {
    vi.clearAllMocks()
    // Dynamic import to get fresh module
    const mod = await import('../httpClient.js')
    apiV1 = mod.apiV1
    clearInflightCache = mod.clearInflightCache
    getInflightCount = mod.getInflightCount
    clearInflightCache()
  })

  afterEach(() => {
    clearInflightCache()
  })

  function mockSuccessResponse(data = {}) {
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true, data, message: '' }),
    })
  }

  it('should dedupe concurrent GET requests to same URL', async () => {
    let resolveFirst
    const firstPromise = new Promise(r => { resolveFirst = r })

    mockFetch.mockImplementationOnce(() => firstPromise)
    mockFetch.mockImplementationOnce(() => mockSuccessResponse({ dup: true }))

    // Fire two concurrent GET requests
    const p1 = apiV1.get('/users')
    const p2 = apiV1.get('/users')

    // Only one fetch call should have been made
    expect(mockFetch).toHaveBeenCalledTimes(1)

    // Resolve the first request
    resolveFirst(mockSuccessResponse({ users: [] }).value || await mockSuccessResponse({ users: [] }))

    const r1 = await p1
    const r2 = await p2

    // Both should get the same result
    expect(r1.success).toBe(true)
    expect(r2.success).toBe(true)
    // Only 1 fetch call was made
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('should NOT dedupe POST requests', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse({ ok: true }))

    const p1 = apiV1.post('/users', { name: 'a' })
    const p2 = apiV1.post('/users', { name: 'b' })

    await Promise.all([p1, p2])

    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('should NOT dedupe when dedupe=false', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse({ ok: true }))

    const p1 = apiV1.get('/users')
    const p2 = apiV1.get('/users', { dedupe: false })

    await Promise.all([p1, p2])

    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('should NOT dedupe when signal is provided', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse({ ok: true }))

    const controller = new AbortController()
    const p1 = apiV1.get('/users')
    const p2 = apiV1.get('/users', { signal: controller.signal })

    await Promise.all([p1, p2])

    expect(mockFetch).toHaveBeenCalledTimes(2)
    controller.abort()
  })

  it('should NOT dedupe blob/download requests', async () => {
    const blobResp = {
      ok: true,
      status: 200,
      blob: () => Promise.resolve(new Blob(['test'])),
    }
    mockFetch.mockImplementation(() => Promise.resolve(blobResp))

    const p1 = apiV1.download('/files/1')
    const p2 = apiV1.download('/files/1')

    await Promise.all([p1, p2])

    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('should clear cache after request completes', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse({ ok: true }))

    await apiV1.get('/users')
    expect(getInflightCount()).toBe(0)

    await apiV1.get('/users')
    expect(getInflightCount()).toBe(0)
  })

  it('should clear cache even when request fails', async () => {
    mockFetch.mockImplementation(() => Promise.reject(new TypeError('Network error')))

    await apiV1.get('/bad-url')
    expect(getInflightCount()).toBe(0)
  })

  it('should allow new request after previous one completes', async () => {
    mockFetch.mockImplementation(() => mockSuccessResponse({ seq: 1 }))

    const r1 = await apiV1.get('/users')
    expect(r1.success).toBe(true)

    mockFetch.mockImplementation(() => mockSuccessResponse({ seq: 2 }))

    const r2 = await apiV1.get('/users')
    expect(r2.success).toBe(true)

    // Two separate fetch calls (not deduped because sequential)
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('clearInflightCache should empty the cache', async () => {
    let resolveFirst
    mockFetch.mockImplementation(() => new Promise(r => { resolveFirst = r }))

    apiV1.get('/slow')

    // Request is in-flight
    expect(getInflightCount()).toBe(1)

    clearInflightCache()
    expect(getInflightCount()).toBe(0)

    // Clean up: resolve the pending request
    resolveFirst(await mockSuccessResponse({ ok: true }))
  })
})
