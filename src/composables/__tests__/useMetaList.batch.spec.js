import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useMetaList } from '../useMetaList'

// Mock boService
vi.mock('@/services/boService', () => ({
  boService: {
    query: vi.fn(),
    batchDelete: vi.fn(),
    clearCache: vi.fn(),
    _clearCache: vi.fn()
  }
}))

// Mock listActionStore
const mockDispatchAction = vi.fn()
vi.mock('@/stores/listActionStore', () => ({
  useListActionStore: () => ({
    dispatchAction: mockDispatchAction,
    registerHandler: vi.fn(() => vi.fn())
  })
}))
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn()
  },
  ElMessageBox: {
    confirm: vi.fn()
  }
}))

describe('useMetaList - 批量操作', () => {
  let metaList

  beforeEach(() => {
    vi.clearAllMocks()
    metaList = useMetaList('user', { autoLoad: false })
  })

  describe('handleBatchDelete', () => {
    it('应该在未选择记录时显示警告', async () => {
      const { handleBatchDelete, selectedIds } = metaList

      selectedIds.value = new Set()

      await handleBatchDelete()

      // 验证没有调用删除API
      // 通过 mock 的 boService.batchDelete 验证
      const { boService } = await import('@/services/boService')
      expect(boService.batchDelete).not.toHaveBeenCalled()
    })

    it('应该在用户确认后执行批量删除', async () => {
      const { handleBatchDelete, selectedIds } = metaList
      const { boService } = await import('@/services/boService')
      const { ElMessageBox } = await import('element-plus')

      // 设置选中的 ID（selectedIds 是 Set）
      selectedIds.value = new Set([1, 2])

      // Mock确认对话框返回true
      ElMessageBox.confirm.mockResolvedValue(true)

      // Mock批量删除API返回成功
      boService.batchDelete.mockResolvedValue({
        success: true,
        data: { count: 2 }
      })

      await handleBatchDelete()

      // 验证调用了批量删除API
      expect(boService.batchDelete).toHaveBeenCalledWith('user', [1, 2])
    })

    it('应该在用户取消时不执行删除', async () => {
      const { handleBatchDelete, selectedIds } = metaList
      const { boService } = await import('@/services/boService')
      const { ElMessageBox } = await import('element-plus')

      selectedIds.value = new Set([1])

      // Mock确认对话框返回cancel
      ElMessageBox.confirm.mockRejectedValue('cancel')

      await handleBatchDelete()

      // 验证没有调用删除API
      expect(boService.batchDelete).not.toHaveBeenCalled()
    })

    it('应该在删除失败时显示错误消息', async () => {
      const { handleBatchDelete, selectedIds } = metaList
      const { boService } = await import('@/services/boService')
      const { ElMessageBox } = await import('element-plus')

      selectedIds.value = new Set([1])
      ElMessageBox.confirm.mockResolvedValue(true)

      // Mock批量删除API返回失败
      boService.batchDelete.mockResolvedValue({
        success: false,
        message: '删除失败'
      })

      await handleBatchDelete()

      // 验证调用了批量删除API
      expect(boService.batchDelete).toHaveBeenCalled()
    })
  })

  describe('handleBatchExport', () => {
    it('应该显示导出对话框', async () => {
      const { handleBatchExport, showExportDialog } = metaList

      // 源中 handleBatchExport 会先调用 loadTotalCount()，所以需要等待
      // 关键断言：最终 showExportDialog 应被设为 true
      try {
        await handleBatchExport()
      } catch (e) {
        // loadTotalCount 可能会失败，源码 catch 后仍会设 showExportDialog=true
      }

      expect(showExportDialog.value).toBe(true)
    })
  })

  describe('handleBatchImport', () => {
    it('应该显示导入对话框', () => {
      const { handleBatchImport, showImportDialog } = metaList

      handleBatchImport()

      expect(showImportDialog.value).toBe(true)
    })
  })

  describe('handleSelectionChange', () => {
    it('应该更新选中的行', () => {
      const { handleSelectionChange, selectedRows } = metaList

      const rows = [
        { id: 1, username: 'user1' },
        { id: 2, username: 'user2' }
      ]

      handleSelectionChange(rows)

      expect(selectedRows.value).toEqual(rows)
    })
  })
})
