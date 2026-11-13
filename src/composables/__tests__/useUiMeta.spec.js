/**
 * useUiMeta.spec.js - useUiMeta Composable 测试（T13-2/T13-3）
 *
 * 覆盖：单次请求 / 缓存命中 / 同 key 并发去重 / schema_version 变化重取 /
 *       接口失败 → meta=null 且 error 有值（含旧端点回退也失败）。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// metaService 依赖 auth store / api 常量，先 mock 再 import
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

import { metaService } from '@/services/metaService'
import { useUiMeta } from '@/composables/useUiMeta'

function makeMeta(type, version) {
  return {
    schema_version: version,
    object_type: type,
    label: type,
    list: { columns: [], actions: [] },
    detail: { sections: [] },
    form: { sections: [], fields: [{ key: 'code', label: '编码', widget: 'text' }] },
    filters: [],
    field_policies: {},
    actions: []
  }
}

describe('useUiMeta', () => {
  let requestSpy

  beforeEach(() => {
    metaService.clearCache()
    requestSpy = vi.spyOn(metaService, '_request')
  })

  afterEach(() => {
    requestSpy.mockRestore()
  })

  it('单次请求：load() 调一次 ui-meta，再次 load 命中缓存', async () => {
    requestSpy.mockResolvedValue({ success: true, data: makeMeta('ui_single', 'v1') })

    const { meta, loading, error, load, fieldIndex } = useUiMeta('ui_single')
    await load()

    expect(requestSpy).toHaveBeenCalledTimes(1)
    expect(requestSpy.mock.calls[0][1]).toBe('/meta/ui_single/ui-meta')
    expect(meta.value.schema_version).toBe('v1')
    expect(error.value).toBeNull()
    expect(loading.value).toBe(false)
    expect(fieldIndex.value.code.label).toBe('编码')

    await load()
    expect(requestSpy).toHaveBeenCalledTimes(1)
  })

  it('同 key 并发只发一次请求', async () => {
    let resolveRequest
    requestSpy.mockImplementation(() => new Promise(resolve => { resolveRequest = resolve }))

    const { meta, load } = useUiMeta('ui_concurrent')
    const first = load(true)
    const second = load(true)

    expect(requestSpy).toHaveBeenCalledTimes(1)
    resolveRequest({ success: true, data: makeMeta('ui_concurrent', 'v1') })
    await Promise.all([first, second])

    expect(meta.value.schema_version).toBe('v1')
    expect(requestSpy).toHaveBeenCalledTimes(1)
  })

  it('schema_version 变化（force）触发重取并整块替换', async () => {
    requestSpy.mockResolvedValueOnce({ success: true, data: makeMeta('ui_version', 'v1') })
    requestSpy.mockResolvedValueOnce({ success: true, data: makeMeta('ui_version', 'v2') })

    const { meta, load } = useUiMeta(ref('ui_version'))
    await load()
    expect(meta.value.schema_version).toBe('v1')

    await load(true)
    expect(requestSpy).toHaveBeenCalledTimes(2)
    expect(meta.value.schema_version).toBe('v2')
    expect(metaService._uiMetaCache.get('ui_version').schema_version).toBe('v2')
  })

  it('接口失败（回退旧端点也失败）→ meta=null 且 error 有值', async () => {
    requestSpy.mockRejectedValue(new Error('network down'))

    const { meta, error, load } = useUiMeta('ui_fail')
    await load()

    expect(meta.value).toBeNull()
    expect(error.value).toBeInstanceOf(Error)
    expect(error.value.message).toBe('network down')
    // ui-meta + 旧 3 端点各一次
    expect(requestSpy).toHaveBeenCalledTimes(4)
  })
})