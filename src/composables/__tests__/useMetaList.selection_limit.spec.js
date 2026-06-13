/**
 * useMetaList.selection_limit.spec.js - FR-008 v1 选区上限行为守卫
 *
 * 目的：
 *   useMetaList 跨页选择 (Gmail 模式) 时, 防止 selectedIds Set 无界累积。
 *   MAX_SELECTION_LIMIT = 1000, 超限截断 + warning + selectionLimitHit 置位。
 *
 * 4 个不变式：
 *   1. selectAllCurrentPage 超限时, selectedIds 被截断到 MAX_SELECTION_LIMIT
 *   2. selectAllCurrentPage 超限时, selectionLimitHit 置为 true
 *   3. selectAllPages 超限时, 同 selectAllCurrentPage 行为
 *   4. clearAllSelection 重置 selectionLimitHit
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock boService + metaService
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

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
  ElMessageBox: { confirm: vi.fn() },
  ElNotification: vi.fn(),
}))

import { useMetaList } from '@/composables/useMetaList'

describe('useMetaList 选区上限 (FR-008 v1)', () => {
  let metaList

  beforeEach(() => {
    vi.clearAllMocks()
    metaList = useMetaList('user', { autoLoad: false })
  })

  describe('不变式 1: selectAllCurrentPage 超限时, selectedIds 截断到 MAX_SELECTION_LIMIT', () => {
    it('1000 条以下不截断', () => {
      const { data, selectAllCurrentPage, selectedIds } = metaList
      // 构造 999 行数据
      data.value = Array.from({ length: 999 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectedIds.value.size).toBe(999)
    })

    it('1001 条超限, 截断到 1000', () => {
      const { data, selectAllCurrentPage, selectedIds, MAX_SELECTION_LIMIT } = metaList
      data.value = Array.from({ length: 1001 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectedIds.value.size).toBe(MAX_SELECTION_LIMIT)
    })

    it('5000 条超限, 截断到 1000', () => {
      const { data, selectAllCurrentPage, selectedIds, MAX_SELECTION_LIMIT } = metaList
      data.value = Array.from({ length: 5000 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectedIds.value.size).toBe(MAX_SELECTION_LIMIT)
    })
  })

  describe('不变式 2: selectAllCurrentPage 超限时, selectionLimitHit 置为 true', () => {
    it('1001 条触发 selectionLimitHit = true', () => {
      const { data, selectAllCurrentPage, selectionLimitHit } = metaList
      data.value = Array.from({ length: 1001 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectionLimitHit.value).toBe(true)
    })

    it('999 条不触发 selectionLimitHit', () => {
      const { data, selectAllCurrentPage, selectionLimitHit } = metaList
      data.value = Array.from({ length: 999 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectionLimitHit.value).toBe(false)
    })
  })

  describe('不变式 3: selectAllPages 超限行为同 selectAllCurrentPage', () => {
    it('selectAllPages 1001 条触发截断 + selectionLimitHit', () => {
      const { data, selectAllPages, selectedIds, selectionLimitHit, isAllPagesSelected, MAX_SELECTION_LIMIT } = metaList
      data.value = Array.from({ length: 1001 }, (_, i) => ({ id: i + 1 }))
      selectAllPages()
      expect(selectedIds.value.size).toBe(MAX_SELECTION_LIMIT)
      expect(selectionLimitHit.value).toBe(true)
      expect(isAllPagesSelected.value).toBe(true)
    })
  })

  describe('不变式 4: clearAllSelection 重置 selectionLimitHit', () => {
    it('触发上限后, clearAllSelection 重置 selectionLimitHit = false', () => {
      const { data, selectAllCurrentPage, clearAllSelection, selectionLimitHit, selectedIds, isAllPagesSelected } = metaList
      data.value = Array.from({ length: 1001 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectionLimitHit.value).toBe(true)
      clearAllSelection()
      expect(selectionLimitHit.value).toBe(false)
      expect(selectedIds.value.size).toBe(0)
      expect(isAllPagesSelected.value).toBe(false)
    })
  })

  describe('回归: 选区未超限行为不变', () => {
    it('少量行不触发 warning', () => {
      const { data, selectAllCurrentPage, selectedIds } = metaList
      data.value = Array.from({ length: 50 }, (_, i) => ({ id: i + 1 }))
      selectAllCurrentPage()
      expect(selectedIds.value.size).toBe(50)
      // 期望未截断
      expect(selectedIds.value.size).not.toBe(0)
    })
  })
})
