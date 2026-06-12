/**
 * useAuditLogs.spec.js - 审计日志 Composable 测试
 *
 * 测试核心功能�? * 1. loadLogs - 加载审计日志
 * 2. setFilters - 设置过滤条件
 * 3. setPage - 翻页
 * 4. clearFilters - 清空过滤条件
 * 5. autoLoad 行为
 * 6. 错误处理
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/auditLogService', () => ({
  getLogsByObject: vi.fn(),
  getRelatedEvents: vi.fn(),
  getByTransactionId: vi.fn()
}))

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual,
    onMounted: vi.fn((fn) => fn()),
  }
})

import * as auditLogService from '@/services/auditLogService'
import { useAuditLogs } from '@/composables/useAuditLogs'

describe('useAuditLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('has correct default values', () => {
      const { logs, total, loading, currentPage, filters } = useAuditLogs('user', 1, { autoLoad: false })

      expect(logs.value).toEqual([])
      expect(total.value).toBe(0)
      expect(loading.value).toBe(false)
      expect(currentPage.value).toBe(1)
      expect(filters.value).toEqual({})
    })
  })

  describe('loadLogs', () => {
    it('loads audit logs successfully', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: {
          items: [
            { id: 1, action: 'create', user: 'admin' },
            { id: 2, action: 'update', user: 'editor' },
          ],
          total: 2,
        },
      })

      const { loadLogs, logs, total } = useAuditLogs('user', 1, { autoLoad: false })
      const result = await loadLogs()

      expect(result.success).toBe(true)
      expect(logs.value).toHaveLength(2)
      expect(total.value).toBe(2)
      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({ page: 1, pageSize: 20 })
      )
    })

    it('requires objectType and objectId', async () => {
      const { loadLogs } = useAuditLogs('', null, { autoLoad: false })
      const result = await loadLogs()

      expect(result.success).toBe(false)
      expect(result.message).toBe('objectType and objectId are required')
    })

    it('handles load failure', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: false,
        message: 'Access denied',
      })

      const { loadLogs, logs } = useAuditLogs('user', 1, { autoLoad: false })
      const result = await loadLogs()

      expect(result.success).toBe(false)
      expect(logs.value).toEqual([])
    })

    it('passes page and pageSize params', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadLogs } = useAuditLogs('user', 1, { autoLoad: false, pageSize: 50 })
      await loadLogs({ page: 3 })

      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({ page: 3, pageSize: 50 })
      )
    })

    it('passes filters', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadLogs, filters } = useAuditLogs('user', 1, { autoLoad: false })
      filters.value = { action: 'update' }
      await loadLogs()

      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({ filters: expect.objectContaining({ action: 'update' }) })
      )
    })

    it('merges param filters with existing filters', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadLogs, filters } = useAuditLogs('user', 1, { autoLoad: false })
      filters.value = { action: 'update' }
      await loadLogs({ filters: { user: 'admin' } })

      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({ filters: expect.objectContaining({ action: 'update', user: 'admin' }) })
      )
    })

    it('sets loading state during request', async () => {
      let resolveLoad
      auditLogService.getLogsByObject.mockReturnValue(new Promise(resolve => { resolveLoad = resolve }))

      const { loadLogs, loading } = useAuditLogs('user', 1, { autoLoad: false })
      const promise = loadLogs()

      expect(loading.value).toBe(true)

      resolveLoad({ success: true, data: { items: [], total: 0 } })
      await promise

      expect(loading.value).toBe(false)
    })
  })

  describe('setFilters', () => {
    it('sets filters and reloads', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { setFilters, filters, currentPage } = useAuditLogs('user', 1, { autoLoad: false })
      await setFilters({ action: 'create' })

      expect(filters.value).toEqual({ action: 'create' })
      expect(currentPage.value).toBe(1)
      expect(auditLogService.getLogsByObject).toHaveBeenCalled()
    })

    it('resets page to 1', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { setFilters, currentPage } = useAuditLogs('user', 1, { autoLoad: false })
      currentPage.value = 5
      await setFilters({ action: 'create' })

      expect(currentPage.value).toBe(1)
    })
  })

  describe('setPage', () => {
    it('sets page and reloads', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { setPage, currentPage } = useAuditLogs('user', 1, { autoLoad: false })
      await setPage(3)

      expect(currentPage.value).toBe(3)
      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({ page: 3 })
      )
    })
  })

  describe('clearFilters', () => {
    it('clears filters and reloads', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { clearFilters, filters, currentPage } = useAuditLogs('user', 1, { autoLoad: false })
      filters.value = { action: 'create' }
      currentPage.value = 5

      await clearFilters()

      expect(filters.value).toEqual({})
      expect(currentPage.value).toBe(1)
      expect(auditLogService.getLogsByObject).toHaveBeenCalled()
    })
  })

  describe('autoLoad', () => {
    it('auto-loads on mount when enabled', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      useAuditLogs('user', 1, { autoLoad: true })

      expect(auditLogService.getLogsByObject).toHaveBeenCalled()
    })

    it('does not auto-load when disabled', () => {
      useAuditLogs('user', 1, { autoLoad: false })

      expect(auditLogService.getLogsByObject).not.toHaveBeenCalled()
    })

    it('does not auto-load when objectType is missing', () => {
      useAuditLogs('', 1, { autoLoad: true })

      expect(auditLogService.getLogsByObject).not.toHaveBeenCalled()
    })

    it('does not auto-load when objectId is missing', () => {
      useAuditLogs('user', null, { autoLoad: true })

      expect(auditLogService.getLogsByObject).not.toHaveBeenCalled()
    })
  })

  describe('custom pageSize', () => {
    it('uses custom page size', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadLogs } = useAuditLogs('user', 1, { autoLoad: false, pageSize: 50 })
      await loadLogs()

      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({ pageSize: 50 })
      )
    })
  })

  // [FIX 2026-06-12] 父对象查询: 角色详情"操作日志" tab 同时拉子对象日志
  describe('parentObjectType / parentObjectId (FR 角色详情操作日志)', () => {
    it('passes parentObjectType/parentObjectId to getLogsByObject', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [{ id: 1, object_type: 'role_menu' }], total: 1 },
      })

      const { loadLogs, logs, total } = useAuditLogs('role', 22, {
        autoLoad: false,
        parentObjectType: 'role',
        parentObjectId: 22,
      })
      const result = await loadLogs()

      expect(result.success).toBe(true)
      expect(logs.value).toHaveLength(1)
      expect(logs.value[0].object_type).toBe('role_menu')
      expect(total.value).toBe(1)
      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'role', 22,
        expect.objectContaining({
          parentObjectType: 'role',
          parentObjectId: 22,
        })
      )
    })

    it('passes undefined when parentObjectType/parentObjectId not provided (向后兼容)', async () => {
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadLogs } = useAuditLogs('user', 1, { autoLoad: false })
      await loadLogs()

      // 旧调用方不应被强制传 parentObjectType/parentObjectId
      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'user', 1,
        expect.objectContaining({
          parentObjectType: undefined,
          parentObjectId: undefined,
        })
      )
    })

    it('支持响应式 ref 形式的 parentObjectId (RoleDetailDrawer 的 computed(() => role.id))', async () => {
      const { ref } = await import('vue')
      const roleIdRef = ref(22)
      auditLogService.getLogsByObject.mockResolvedValue({
        success: true,
        data: { items: [], total: 0 },
      })

      const { loadLogs } = useAuditLogs('role', roleIdRef, {
        autoLoad: false,
        parentObjectType: 'role',
        parentObjectId: roleIdRef,
      })
      await loadLogs()

      expect(auditLogService.getLogsByObject).toHaveBeenCalledWith(
        'role', 22,
        expect.objectContaining({
          parentObjectType: 'role',
          parentObjectId: 22,
        })
      )

      // 切换 ref 后再 load, 应该传新值
      roleIdRef.value = 99
      await loadLogs()
      expect(auditLogService.getLogsByObject).toHaveBeenLastCalledWith(
        'role', 99,
        expect.objectContaining({
          parentObjectType: 'role',
          parentObjectId: 99,
        })
      )
    })
  })
})
