/**
 * graphqlClient.spec.js - M9 D3 前端 GraphQL 兼容层单测
 *
 * 测试设计：
 * - L1 工具函数：_snakeToPascal / _entityNameToRoot
 * - L2 callPost URL 路由：3 种 URL 模式
 * - L3 fetch 调用：验证 request body / headers
 * - L4 错误处理：401 / GraphQL errors
 * - L5 高级 API：query / mutation
 *
 * 不依赖 dev server（fetch mock）
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { graphqlClient } from '@/services/graphqlClient'
import { useAuthStore } from '@/stores/authStore'

// Mock authStore
vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(() => ({
    getAuthHeaders: vi.fn(() => ({ Authorization: 'Bearer test-token' })),
  })),
}))

// Mock fetch
const mockFetch = vi.fn()
global.fetch = mockFetch

beforeEach(() => {
  mockFetch.mockReset()
  // 默认成功响应
  mockFetch.mockResolvedValue({
    status: 200,
    json: async () => ({ data: { testField: 'test' } }),
  })
})

afterEach(() => {
  vi.clearAllMocks()
})


// =============================================================================
// L1 工具函数
// =============================================================================

describe('L1: 工具函数 (snake_case → PascalCase / root)', () => {
  it('T1.1: user_group → UserGroup', () => {
    expect(graphqlClient._snakeToPascal('user_group')).toBe('UserGroup')
  })

  it('T1.2: user → User (单字)', () => {
    expect(graphqlClient._snakeToPascal('user')).toBe('User')
  })

  it('T1.3: business_object → BusinessObject (多段)', () => {
    expect(graphqlClient._snakeToPascal('business_object')).toBe('BusinessObject')
  })

  it('T1.4: _entityNameToRoot: user_group → userGroup (camelCase)', () => {
    expect(graphqlClient._entityNameToRoot('user_group')).toBe('userGroup')
  })

  it('T1.5: _entityNameToRoot: user → user', () => {
    expect(graphqlClient._entityNameToRoot('user')).toBe('user')
  })

  it('T1.6: _endpoint 暴露', () => {
    expect(graphqlClient._endpoint).toBe('/graphql')
  })
})


// =============================================================================
// L2 callPost URL 路由（3 种模式）
// =============================================================================

describe('L2: callPost URL 路由 (3 模式)', () => {
  it('T2.1: POST /api/v2/bo/user_group + body → createUserGroup', async () => {
    await graphqlClient.callPost('/api/v2/bo/user_group', { code: 'ADMIN', name: 'Admin' })
    expect(mockFetch).toHaveBeenCalledTimes(1)
    // 验证 fetch URL
    expect(mockFetch.mock.calls[0][0]).toBe('/graphql')
    // 验证 body 内容
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.query).toContain('createUserGroup(input: $input)')
    expect(body.variables.input).toEqual({ code: 'ADMIN', name: 'Admin' })
  })

  it('T2.2: GET /api/v2/bo/user_group/1 → userGroup(id: 1)', async () => {
    await graphqlClient.callPost('/api/v2/bo/user_group/1', {})
    const callArgs = mockFetch.mock.calls[0]
    const body = JSON.parse(callArgs[1].body)
    expect(body.query).toContain('userGroup(id: $id)')
    expect(body.variables).toEqual({ id: 1 })
  })

  it('T2.3: GET /api/v2/bo/user (无 body) → users(page, pageSize)', async () => {
    await graphqlClient.callPost('/api/v2/bo/user', {})
    const callArgs = mockFetch.mock.calls[0]
    const body = JSON.parse(callArgs[1].body)
    expect(body.query).toContain('users(')
    expect(body.query).toContain('page: 1')
    expect(body.query).toContain('pageSize: 20')
  })

  it('T2.4: 不支持的 URL → errors 错误', async () => {
    const result = await graphqlClient.callPost('/api/v1/other/endpoint', {})
    expect(result.success).toBe(false)
    expect(result.errors[0].message).toContain('URL not supported in POC')
  })
})


// =============================================================================
// L3 fetch 调用细节
// =============================================================================

describe('L3: fetch 调用细节', () => {
  it('T3.1: 包含 Content-Type: application/json', async () => {
    await graphqlClient.query('{ test }')
    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers['Content-Type']).toBe('application/json')
  })

  it('T3.2: 包含 Authorization Bearer token（来自 authStore）', async () => {
    await graphqlClient.query('{ test }')
    const headers = mockFetch.mock.calls[0][1].headers
    expect(headers['Authorization']).toBe('Bearer test-token')
  })

  it('T3.3: 包含 credentials: include（CORS cookie）', async () => {
    await graphqlClient.query('{ test }')
    expect(mockFetch.mock.calls[0][1].credentials).toBe('include')
  })

  it('T3.4: body 包含 query + variables', async () => {
    await graphqlClient.query('query { test }', { id: 1 })
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.query).toBe('query { test }')
    expect(body.variables).toEqual({ id: 1 })
  })
})


// =============================================================================
// L4 错误处理
// =============================================================================

describe('L4: 错误处理', () => {
  it('T4.1: 401 → Unauthorized 错误', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 401,
      json: async () => ({}),
    })
    const result = await graphqlClient.query('{ test }')
    expect(result.success).toBe(false)
    expect(result.errors[0].message).toBe('Unauthorized')
  })

  it('T4.2: GraphQL errors → 返回 errors 数组', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      json: async () => ({
        errors: [{ message: 'Field not found' }],
      }),
    })
    const result = await graphqlClient.query('{ test }')
    expect(result.success).toBe(false)
    expect(result.errors[0].message).toBe('Field not found')
  })

  it('T4.3: 成功响应 → data 包含查询结果', async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      json: async () => ({
        data: { userGroups: [{ id: 1, name: 'admin' }] },
      }),
    })
    const result = await graphqlClient.query('{ userGroups { id name } }')
    expect(result.success).toBe(true)
    expect(result.data.userGroups).toEqual([{ id: 1, name: 'admin' }])
  })
})


// =============================================================================
// L5 高级 API
// =============================================================================

describe('L5: 高级 API (query / mutation)', () => {
  it('T5.1: query 直接调用', async () => {
    await graphqlClient.query('{ users(page: 1) { id } }')
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('T5.2: mutation 内部也走 _graphqlFetch', async () => {
    await graphqlClient.mutation('mutation { createUser(input: $input) { id } }', { input: { name: 'x' } })
    const body = JSON.parse(mockFetch.mock.calls[0][1].body)
    expect(body.query).toContain('createUser')
    expect(body.variables).toEqual({ input: { name: 'x' } })
  })

  it('T5.3: 无 authStore 时不报错（getAuthHeaders 可能不存在）', async () => {
    useAuthStore.mockReturnValueOnce(null)
    await expect(graphqlClient.query('{ test }')).resolves.toBeDefined()
  })
})
