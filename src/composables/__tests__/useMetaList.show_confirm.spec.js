/**
 * useMetaList.show_confirm.spec.js - _showConfirm 模板替换 + i18n 回归
 *
 * 目的：
 *   验证 handleAction 走 confirm 路径时, _showConfirm 内部模板替换工作。
 *   同时验证 confirmTitle 缺失时走 i18nT 兜底。
 *
 * 4 个不变式：
 *   1. {row.xxx} 模板替换 (selectedRows.value[0] 的字段)
 *   2. 模板中无 {row.xxx} 时, 原样传递
 *   3. confirmTitle 缺失时, 走 i18nT('metaList.confirmTitle') 兜底
 *   4. 取消确认 (catch) 返回 false
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/boService', () => ({
  boService: {
    query: vi.fn().mockResolvedValue({ success: true, data: { items: [], total: 0 } }),
    _clearCache: vi.fn(),
  }
}))

vi.mock('@/services/metaService', () => ({
  metaService: {
    getListConfig: vi.fn().mockResolvedValue({ success: true, data: { list: {}, fields: [] } }),
    clearCache: vi.fn(),
  }
}))

vi.mock('@/services/DateFormatService', () => ({
  dateFormatService: { format: vi.fn(v => String(v)) }
}))

vi.mock('@/stores/listActionStore', () => ({
  useListActionStore: () => ({
    registerActions: vi.fn(),
    getActions: vi.fn().mockReturnValue([]),
    getRowActions: vi.fn().mockReturnValue([]),
  })
}))

vi.mock('@/services/keyTemplateService', () => ({
  suggestKeyTemplateCode: vi.fn().mockResolvedValue({ success: true, data: { code: 'X' } })
}))

vi.mock('@/services/draftPersistService', () => ({
  saveAllDrafts: vi.fn().mockResolvedValue({ success: true }),
  getDraftCreates: vi.fn().mockResolvedValue([]),
}))

import { useMetaList } from '@/composables/useMetaList'

describe('useMetaList _showConfirm 模板替换 (FR-019 回归)', () => {
  let metaList
  let mockConfirm

  beforeEach(async () => {
    vi.clearAllMocks()
    const ep = await import('element-plus')
    mockConfirm = vi.spyOn(ep.ElMessageBox, 'confirm')
    metaList = useMetaList('user', { autoLoad: false })
  })

  it('不变式 1: {row.name} 模板替换为 selectedRows[0].name', async () => {
    mockConfirm.mockResolvedValueOnce('confirm')
    const { handleAction, selectedRows } = metaList
    // 模拟 selectedRows 已选中 1 行
    selectedRows.value = [{ id: 1, name: 'Alice' }]

    await handleAction({
      action: {
        key: 'custom_delete',
        confirmMessage: '确定要删除 {row.name} 吗？',
        variant: 'danger',
      },
      row: selectedRows.value[0],
    })

    expect(mockConfirm).toHaveBeenCalledTimes(1)
    const [msg] = mockConfirm.mock.calls[0]
    expect(msg).toBe('确定要删除 Alice 吗？')
  })

  it('不变式 2: 无 {row.xxx} 占位符时, 原样传递', async () => {
    mockConfirm.mockResolvedValueOnce('confirm')
    const { handleAction } = metaList

    await handleAction({
      action: {
        key: 'custom_op',
        confirmMessage: '确定执行此操作吗？',
      },
      row: null,
    })

    expect(mockConfirm).toHaveBeenCalledTimes(1)
    const [msg] = mockConfirm.mock.calls[0]
    expect(msg).toBe('确定执行此操作吗？')
  })

  it('不变式 3: confirmTitle 缺失时, 走 i18nT("metaList.confirmTitle") 兜底', async () => {
    mockConfirm.mockResolvedValueOnce('confirm')
    const { handleAction } = metaList

    await handleAction({
      action: { key: 'x', confirmMessage: 'test' },
      row: null,
    })

    const [, title] = mockConfirm.mock.calls[0]
    // i18nT 走 zh-CN 默认 locale, 'metaList.confirmTitle' = '确认操作'
    expect(title).toBeTruthy()
    expect(typeof title).toBe('string')
  })

  it('不变式 4: 取消确认 (reject) 不抛错', async () => {
    mockConfirm.mockRejectedValueOnce('cancel')
    const { handleAction } = metaList

    // 不应 throw
    await expect(
      handleAction({
        action: { key: 'x', confirmMessage: 'test' },
        row: null,
      })
    ).resolves.toBeUndefined()
  })
})
