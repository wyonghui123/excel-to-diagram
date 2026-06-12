/**
 * auditLogService.spec.js - 审计日志服务测试
 *
 * 覆盖核心纯函数 + API 函数:
 * 1. buildLogFilter - URL filter 参数构建 (含 parent_object)
 * 2. getLogsByObject - 含 parentObjectType/parentObjectId 的 API 调用
 * 3. formatLogAction / formatLogLevel / formatLogCategory / getFieldDisplayName
 * 4. parseTargetDisplay
 *
 * [FIX 2026-06-12] 父对象查询支持 - RoleDetailDrawer 同时拉子对象日志
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/utils/httpClient', () => ({
  apiV1: { get: vi.fn() },
  apiV2: { get: vi.fn() },
}))

vi.mock('@/services/associationService', () => ({
  extractItems: vi.fn((r) => r?.data?.items || []),
}))

import { apiV1, apiV2 } from '@/utils/httpClient'
import * as auditLogService from '@/services/auditLogService'

describe('auditLogService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('buildLogFilter', () => {
    it('空 filters 返回空对象', () => {
      expect(auditLogService.buildLogFilter()).toEqual({})
      expect(auditLogService.buildLogFilter({})).toEqual({})
    })

    it('基础字段映射正确', () => {
      const out = auditLogService.buildLogFilter({
        action: 'CREATE',
        level: 'INFO',
        category: 'permission',
        user: 'admin',
        startDate: '2026-06-01',
        endDate: '2026-06-12',
        objectType: 'role',
        objectId: 22,
        transactionId: 'tx-1',
      })
      expect(out).toEqual({
        action: 'CREATE',
        level: 'INFO',
        category: 'permission',
        user: 'admin',
        start_date: '2026-06-01',
        end_date: '2026-06-12',
        object_type: 'role',
        object_id: 22,
        transaction_id: 'tx-1',
      })
    })

    it('[FIX 2026-06-12] parentObjectType/parentObjectId 映射到 parent_object_*', () => {
      const out = auditLogService.buildLogFilter({
        objectType: 'role',
        objectId: 22,
        parentObjectType: 'role',
        parentObjectId: 22,
      })
      expect(out).toEqual({
        object_type: 'role',
        object_id: 22,
        parent_object_type: 'role',
        parent_object_id: '22', // 强转 string
      })
    })

    it('parentObjectId 数字 0 仍被保留', () => {
      const out = auditLogService.buildLogFilter({ parentObjectId: 0 })
      expect(out.parent_object_id).toBe('0')
    })

    it('未提供 parentObjectId 时不会出现在结果中', () => {
      const out = auditLogService.buildLogFilter({ parentObjectType: 'role' })
      expect(out).toEqual({ parent_object_type: 'role' })
      expect('parent_object_id' in out).toBe(false)
    })
  })

  describe('getLogsByObject', () => {
    it('传递 parentObjectType/parentObjectId 到 query string', async () => {
      apiV1.get.mockResolvedValue({
        success: true,
        data: [
          { id: 1, object_type: 'role_menu' },
          { id: 2, object_type: 'role_permissions' },
        ],
        total: 2,
      })

      const result = await auditLogService.getLogsByObject('role', 22, {
        page: 1,
        pageSize: 20,
        parentObjectType: 'role',
        parentObjectId: 22,
      })

      expect(result.success).toBe(true)
      expect(result.data.items).toHaveLength(2)
      expect(result.data.total).toBe(2)

      // 验证 query string 包含 parent_object_type/parent_object_id
      const calledUrl = apiV1.get.mock.calls[0][0]
      expect(calledUrl).toMatch(/object_type=role/)
      expect(calledUrl).toMatch(/object_id=22/)
      expect(calledUrl).toMatch(/parent_object_type=role/)
      expect(calledUrl).toMatch(/parent_object_id=22/)
    })

    it('不传 parentObjectType/parentObjectId 时不附加相关参数 (向后兼容)', async () => {
      apiV1.get.mockResolvedValue({ success: true, data: [], total: 0 })

      await auditLogService.getLogsByObject('user', 1, { page: 1, pageSize: 20 })

      const calledUrl = apiV1.get.mock.calls[0][0]
      expect(calledUrl).toMatch(/object_type=user/)
      expect(calledUrl).toMatch(/object_id=1/)
      expect(calledUrl).not.toMatch(/parent_object_type/)
      expect(calledUrl).not.toMatch(/parent_object_id/)
    })

    it('响应已经是 v2 BO 格式 (data.items + data.total) 时原样返回', async () => {
      apiV1.get.mockResolvedValue({
        success: true,
        data: { items: [{ id: 1 }], total: 1 },
      })

      const result = await auditLogService.getLogsByObject('role', 22)
      expect(result).toEqual({
        success: true,
        data: { items: [{ id: 1 }], total: 1 },
      })
    })
  })

  describe('formatLogAction / formatLogLevel / formatLogCategory', () => {
    it('formatLogAction 映射常见 action', () => {
      expect(auditLogService.formatLogAction('CREATE')).toBe('创建')
      expect(auditLogService.formatLogAction('UPDATE')).toBe('更新')
      expect(auditLogService.formatLogAction('DELETE')).toBe('删除')
      expect(auditLogService.formatLogAction('UNKNOWN')).toBe('UNKNOWN')
      expect(auditLogService.formatLogAction('')).toBe('')
    })

    it('formatLogLevel 映射 level', () => {
      expect(auditLogService.formatLogLevel('INFO')).toBe('信息')
      expect(auditLogService.formatLogLevel('ERROR')).toBe('错误')
    })

    it('formatLogCategory 映射 category', () => {
      expect(auditLogService.formatLogCategory('permission')).toBe('权限')
      expect(auditLogService.formatLogCategory('security')).toBe('安全')
    })
  })

  describe('parseTargetDisplay', () => {
    it('null/undefined 返回空字符串', () => {
      expect(auditLogService.parseTargetDisplay(null)).toBe('')
      expect(auditLogService.parseTargetDisplay(undefined)).toBe('')
    })

    it('字符串 JSON 解析为对象', () => {
      expect(auditLogService.parseTargetDisplay('{"name":"foo"}')).toBe('foo')
    })

    it('非 JSON 字符串原样返回', () => {
      expect(auditLogService.parseTargetDisplay('plain')).toBe('plain')
    })

    it('对象取 name/display_name/code', () => {
      expect(auditLogService.parseTargetDisplay({ name: 'A' })).toBe('A')
      expect(auditLogService.parseTargetDisplay({ display_name: 'B' })).toBe('B')
      expect(auditLogService.parseTargetDisplay({ code: 'C' })).toBe('C')
    })
  })
})
