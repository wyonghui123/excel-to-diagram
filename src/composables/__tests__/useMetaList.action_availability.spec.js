/**
 * useMetaList.action_availability.spec.js - B1-2 行级动作判定下沉守卫
 *
 * 验证：行级动作的权限/条件判定由后端 `actions/evaluate` 批量结果驱动，
 * 后端不可用（请求异常 / 返回失败 / 缺 verdict）时一律 fail-closed（不渲染按钮）。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'

vi.mock('@/services/boService', () => {
  const boService = {
    query: vi.fn(),
    evaluateActions: vi.fn(),
    _clearCache: vi.fn(),
    clearCache: vi.fn()
  }
  return { boService, default: boService }
})

vi.mock('@/services/metaService', () => {
  const metaService = {
    getViewConfig: vi.fn(),
    getUiMeta: vi.fn(),
    clearCache: vi.fn()
  }
  return { metaService, default: metaService }
})

import { useMetaList } from '@/composables/useMetaList'
import { boService } from '@/services/boService'
import { metaService } from '@/services/metaService'

function viewConfig() {
  return {
    success: true,
    data: {
      list: {
        columns: [
          { key: 'id', label: 'ID' },
          { key: 'name', label: '名称' }
        ],
        actions: [
          { id: 'submit', position: 'row', permission: 'crud_submit' },
          { id: 'delete', position: 'row', permission: 'crud_delete' }
        ],
        filters: []
      },
      fields: []
    }
  }
}

// [T13-9] ui-meta 聚合端点返回的是数据对象本身（非 {success,data} 包裹）
function uiMeta() {
  const legacy = viewConfig().data
  return {
    schema_version: 1,
    object_type: 'demo_object',
    label: '演示对象',
    list: legacy.list,
    detail: { sections: [], tabs: [] },
    form: { fields: [], tabs: [] },
    filters: [],
    field_policies: {},
    actions: []
  }
}

async function initWithRow({ evaluateActions }) {
  metaService.getUiMeta.mockResolvedValue(uiMeta())
  metaService.getViewConfig.mockResolvedValue(viewConfig())
  boService.query.mockResolvedValue({ success: true, data: { items: [{ id: 1, name: 'a' }], total: 1 } })
  boService.evaluateActions.mockImplementation(evaluateActions)

  const meta = useMetaList('demo_object', {})
  await meta.init()
  await flushPromises()
  await flushPromises()
  return meta
}

describe('useMetaList 行级动作后端批量判定（B1-2 fail-closed）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  it('actions/evaluate 请求异常时不渲染任何行级动作', async () => {
    const meta = await initWithRow({
      evaluateActions: () => Promise.reject(new Error('network down'))
    })

    expect(meta.data.value.length).toBe(1)
    expect(boService.evaluateActions).toHaveBeenCalled()
    expect(meta.getRowActions({ id: 1 })).toEqual([])
  })

  it('actions/evaluate 返回 success=false 时不渲染任何行级动作', async () => {
    const meta = await initWithRow({
      evaluateActions: () => Promise.resolve({ success: false, message: 'ERROR' })
    })

    expect(meta.data.value.length).toBe(1)
    expect(meta.getRowActions({ id: 1 })).toEqual([])
  })

  it('按后端 verdict 渲染：enabled=true 保留，enabled=false 隐藏', async () => {
    const meta = await initWithRow({
      evaluateActions: () => Promise.resolve({
        success: true,
        data: {
          1: {
            submit: { enabled: true, reason: '', required_permission: '' },
            delete: { enabled: false, reason: 'no_permission', required_permission: 'crud_delete' }
          }
        }
      })
    })

    expect(meta.data.value.length).toBe(1)
    expect(meta.getRowActions({ id: 1 }).map(a => a.key)).toEqual(['submit'])
  })

  it('有后端结果但缺少某动作 verdict 时，该动作隐藏（fail-closed）', async () => {
    const meta = await initWithRow({
      evaluateActions: () => Promise.resolve({
        success: true,
        data: {
          1: {
            submit: { enabled: true, reason: '', required_permission: '' }
          }
        }
      })
    })

    expect(meta.data.value.length).toBe(1)
    expect(meta.getRowActions({ id: 1 }).map(a => a.key)).toEqual(['submit'])
  })
})

describe('useMetaList 元数据来源：ui-meta 优先 + legacy 回退（T13-9）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    boService.query.mockResolvedValue({ success: true, data: { items: [{ id: 1, name: 'a' }], total: 1 } })
    boService.evaluateActions.mockResolvedValue({ success: true, data: {} })
  })

  it('getUiMeta reject 且 getViewConfig resolve 时，回退 legacy 且元数据加载成功', async () => {
    metaService.getUiMeta.mockRejectedValue(new Error('ui-meta 500'))
    metaService.getViewConfig.mockResolvedValue(viewConfig())

    const meta = useMetaList('demo_object', {})
    await meta.init()
    await flushPromises()
    await flushPromises()

    expect(metaService.getUiMeta).toHaveBeenCalledWith('demo_object')
    expect(metaService.getViewConfig).toHaveBeenCalled()
    expect(meta.columns.value.map(c => c.key)).toHaveLength(2)
    expect(meta.columns.value.map(c => c.key)).toEqual(expect.arrayContaining(['id', 'name']))
    expect(meta.data.value.length).toBe(1)
  })

  it('getUiMeta resolve 时，不再调用 getViewConfig', async () => {
    metaService.getUiMeta.mockResolvedValue(uiMeta())

    const meta = useMetaList('demo_object', {})
    await meta.init()
    await flushPromises()
    await flushPromises()

    expect(metaService.getUiMeta).toHaveBeenCalledWith('demo_object')
    expect(metaService.getViewConfig).not.toHaveBeenCalled()
    expect(meta.columns.value.map(c => c.key)).toHaveLength(2)
    expect(meta.columns.value.map(c => c.key)).toEqual(expect.arrayContaining(['id', 'name']))
  })

  it('actions/evaluate 返回 HTTP 500 时行级动作 fail-closed（不可用）', async () => {
    metaService.getUiMeta.mockResolvedValue(uiMeta())
    boService.evaluateActions.mockResolvedValue({ success: false, httpStatus: 500, message: 'Internal Server Error' })

    const meta = useMetaList('demo_object', {})
    await meta.init()
    await flushPromises()
    await flushPromises()

    expect(meta.data.value.length).toBe(1)
    expect(meta.getRowActions({ id: 1 })).toEqual([])
  })
})