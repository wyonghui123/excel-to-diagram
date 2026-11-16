import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/utils/httpClient', () => {
  const makeNamespace = () => ({
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  })
  return { apiV1: makeNamespace(), apiV2: makeNamespace() }
})

import { apiV1, apiV2 } from '@/utils/httpClient'
import {
  applyOrderingBridge,
  buildFetcher,
  resolveRequest,
} from '@/services/metaResourceService'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('resolveRequest（v1 / v2 命名空间路由）', () => {
  it('/api/v1 前缀走 apiV1 并去掉前缀', () => {
    const resolved = resolveRequest('/api/v1/audit/logs')
    expect(resolved.namespace).toBe(apiV1)
    expect(resolved.path).toBe('/audit/logs')
  })

  it('/api/v2 前缀走 apiV2 并去掉前缀', () => {
    const resolved = resolveRequest('/api/v2/integrations/connections')
    expect(resolved.namespace).toBe(apiV2)
    expect(resolved.path).toBe('/integrations/connections')
  })

  it('裸路径保持现状（apiV2 + 原路径）', () => {
    const resolved = resolveRequest('/integrations/deliveries')
    expect(resolved.namespace).toBe(apiV2)
    expect(resolved.path).toBe('/integrations/deliveries')
  })
})

describe('applyOrderingBridge（ordering → sort_field/sort_direction）', () => {
  const paramsMap = { sort_field: 'sort_field', sort_direction: 'sort_direction' }

  it('降序拆分并删除 ordering', () => {
    expect(applyOrderingBridge({ page: 1, ordering: '-created_at' }, paramsMap))
      .toEqual({ page: 1, sort_field: 'created_at', sort_direction: 'desc' })
  })

  it('升序拆分', () => {
    expect(applyOrderingBridge({ ordering: 'created_at' }, paramsMap))
      .toEqual({ sort_field: 'created_at', sort_direction: 'asc' })
  })

  it('未声明桥接键时原样返回', () => {
    const params = { ordering: '-created_at' }
    expect(applyOrderingBridge(params, { page_size: 'pageSize' })).toBe(params)
  })

  it('无 ordering 时原样返回', () => {
    const params = { page: 1 }
    expect(applyOrderingBridge(params, paramsMap)).toBe(params)
  })
})

describe('buildFetcher（声明式 data_source）', () => {
  it('v1 端点按 params_map 映射并透传顶层 total', async () => {
    apiV1.get.mockResolvedValue({ success: true, data: [{ id: 1 }], total: 42 })
    const fetcher = buildFetcher({
      url: '/api/v1/audit/logs',
      items_path: 'data',
      total_path: 'total',
      params_map: {
        page_size: 'pageSize',
        start_date: 'created_at_start',
        sort_field: 'sort_field',
        sort_direction: 'sort_direction',
      },
    })

    const result = await fetcher({
      page: 1,
      pageSize: 20,
      created_at_start: '2026-01-01',
      ordering: '-created_at',
    })

    expect(apiV2.get).not.toHaveBeenCalled()
    expect(apiV1.get).toHaveBeenCalledWith('/audit/logs', {
      params: {
        page: 1,
        page_size: 20,
        start_date: '2026-01-01',
        sort_field: 'created_at',
        sort_direction: 'desc',
      },
    })
    expect(result.data).toEqual({ items: [{ id: 1 }], total: 42 })
  })

  it('v2 端点保持 data.items / data.total 取值不变', async () => {
    apiV2.get.mockResolvedValue({ success: true, data: { items: [{ a: 1 }], total: 3 } })
    const fetcher = buildFetcher({
      url: '/api/v2/integrations/connections',
      items_path: 'data.items',
      total_path: 'data.total',
      params_map: { page_size: 'pageSize' },
    })

    const result = await fetcher({ page: 1, pageSize: 10 })

    expect(apiV1.get).not.toHaveBeenCalled()
    expect(apiV2.get).toHaveBeenCalledWith('/integrations/connections', {
      params: { page: 1, page_size: 10 },
    })
    expect(result.data).toEqual({ items: [{ a: 1 }], total: 3 })
  })
})
