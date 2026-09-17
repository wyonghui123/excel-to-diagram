/**
 * auditLogMeta.spec.js - 审计日志元数据配置测试
 *
 * 测试范围：
 * 1. 元数据基本结构完整性
 * 2. 表格列定义（含死列清理回归）
 * 3. 过滤器定义（含角色迁移后的 object_type 选项）
 * 4. 详情配置完整性
 * 5. API 配置完整性
 *
 * [FIX 2026-09-06] 配合审计日志死列清理 + 角色迁移对齐:
 * - log_category/log_level/action_kind/outcome 列与过滤器已移除
 *   (list API SELECT 不返回, audit_logs 表无 action_kind/outcome 列)
 * - formatted_identity(前端死字段) 已替换为 business_key(后端生成)
 * - object_type 过滤器新增 org/permission_set, role/user_group 保留为历史值
 */

import { describe, it, expect } from 'vitest'
import { auditLogMeta } from '../auditLogMeta'

describe('auditLogMeta', () => {
  describe('基本结构', () => {
    it('应该包含 object 标识', () => {
      expect(auditLogMeta.object).toBe('audit_log')
    })

    it('应该包含 name', () => {
      expect(auditLogMeta.name).toBe('审计日志')
    })

    it('应该包含 description', () => {
      expect(auditLogMeta.description).toBeDefined()
    })

    it('应该包含 list 配置', () => {
      expect(auditLogMeta.list).toBeDefined()
      expect(auditLogMeta.list.defaultSort).toBeDefined()
      expect(auditLogMeta.list.defaultSort.field).toBe('created_at')
      expect(auditLogMeta.list.defaultSort.direction).toBe('desc')
    })

    it('应该包含分页配置', () => {
      expect(auditLogMeta.list.pagination).toBeDefined()
      expect(auditLogMeta.list.pagination.pageSize).toBe(20)
    })
  })

  describe('表格列定义', () => {
    it('应该包含 action 列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'action')
      expect(col).toBeDefined()
      expect(col.label).toBe('操作类型')
      expect(col.sortable).toBe(true)
    })

    it('action 列应该包含 ASSOCIATE 和 DISSOCIATE', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'action')
      const values = col.options.map(o => o.value)
      expect(values).toContain('CREATE')
      expect(values).toContain('UPDATE')
      expect(values).toContain('DELETE')
      expect(values).toContain('ASSOCIATE')
      expect(values).toContain('DISSOCIATE')
    })

    it('应该包含操作时间列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'created_at')
      expect(col).toBeDefined()
      expect(col.type).toBe('datetime')
      expect(col.sortable).toBe(true)
    })

    it('应该包含操作人列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'user_name')
      expect(col).toBeDefined()
      expect(col.sortable).toBe(true)
    })

    it('业务标识列应该绑定 business_key (后端真实字段)', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'business_key')
      expect(col).toBeDefined()
      expect(col.label).toBe('业务标识')
    })

    it('不应再包含 formatted_identity 死字段列', () => {
      expect(auditLogMeta.tableColumns.find(c => c.key === 'formatted_identity')).toBeUndefined()
    })

    it('不应包含 list API 不返回的死列', () => {
      // audit_api.py GET /logs 的 SELECT 不返回这四个字段,
      // action_kind/outcome 在 audit_logs 表中也不存在
      const deadKeys = ['log_category', 'log_level', 'action_kind', 'outcome']
      for (const key of deadKeys) {
        expect(auditLogMeta.tableColumns.find(c => c.key === key)).toBeUndefined()
      }
    })

    it('应该包含 IP 地址列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'ip_address')
      expect(col).toBeDefined()
    })
  })

  describe('过滤器定义', () => {
    it('应该包含 action 过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'action')
      expect(filter).toBeDefined()
      expect(filter.type).toBe('select')
    })

    it('object_type 过滤器应该包含迁移后的 org 与 permission_set', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'object_type')
      expect(filter).toBeDefined()
      const values = filter.options.map(o => o.value)
      expect(values).toContain('org')
      expect(values).toContain('permission_set')
    })

    it('object_type 过滤器应该保留历史值 role/user_group 以检索迁移前日志', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'object_type')
      const values = filter.options.map(o => o.value)
      expect(values).toContain('role')
      expect(values).toContain('user_group')
    })

    it('不应包含死过滤器', () => {
      const deadKeys = ['log_category', 'log_level', 'action_kind', 'outcome']
      for (const key of deadKeys) {
        expect(auditLogMeta.filters.find(f => f.key === key)).toBeUndefined()
      }
    })

    it('应该包含 user_name 过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'user_name')
      expect(filter).toBeDefined()
    })

    it('应该包含时间范围过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'date_range')
      expect(filter).toBeDefined()
      expect(filter.type).toBe('datetime-range')
    })

    it('每个有选项的 select 过滤器应该有"全部"选项', () => {
      const selectFilters = auditLogMeta.filters.filter(f => f.type === 'select' && f.options && f.options.length > 0)
      for (const filter of selectFilters) {
        const hasAllOption = filter.options.some(o => o.value === '')
        expect(hasAllOption).toBe(true)
      }
    })
  })

  describe('详情配置', () => {
    it('应该包含详情配置', () => {
      expect(auditLogMeta.detail).toBeDefined()
      expect(auditLogMeta.detail.title).toBe('审计日志详情')
    })

    it('详情基本信息分区应该包含业务标识 (business_key)', () => {
      const section = auditLogMeta.detail.sections.find(s => s.title === '基本信息')
      expect(section).toBeDefined()
      const fieldKeys = section.fields.map(f => f.key)
      expect(fieldKeys).toContain('id')
      expect(fieldKeys).toContain('created_at')
      expect(fieldKeys).toContain('action')
      expect(fieldKeys).toContain('business_key')
    })

    it('详情不应包含死字段', () => {
      const deadKeys = ['log_category', 'log_level', 'formatted_identity']
      for (const section of auditLogMeta.detail.sections) {
        for (const key of deadKeys) {
          expect(section.fields.find(f => f.key === key)).toBeUndefined()
        }
      }
    })

    it('详情应该包含变更详情分区', () => {
      const section = auditLogMeta.detail.sections.find(s => s.title === '变更详情')
      expect(section).toBeDefined()
      const fieldKeys = section.fields.map(f => f.key)
      expect(fieldKeys).toContain('field_name')
      expect(fieldKeys).toContain('old_value')
      expect(fieldKeys).toContain('new_value')
    })

    it('详情应该包含操作人信息分区', () => {
      const section = auditLogMeta.detail.sections.find(s => s.title === '操作人信息')
      expect(section).toBeDefined()
      const fieldKeys = section.fields.map(f => f.key)
      expect(fieldKeys).toContain('user_id')
      expect(fieldKeys).toContain('user_name')
      expect(fieldKeys).toContain('ip_address')
    })

    it('详情应该包含追踪信息分区', () => {
      const section = auditLogMeta.detail.sections.find(s => s.title === '追踪信息')
      expect(section).toBeDefined()
      const fieldKeys = section.fields.map(f => f.key)
      expect(fieldKeys).toContain('trace_id')
      expect(fieldKeys).toContain('transaction_id')
    })
  })

  describe('API 配置', () => {
    it('应该包含 API 配置', () => {
      expect(auditLogMeta.api).toBeDefined()
      expect(auditLogMeta.api.baseUrl).toBe('/api/v1/audit')
    })

    it('应该包含 list 端点', () => {
      expect(auditLogMeta.api.endpoints.list).toBeDefined()
      expect(auditLogMeta.api.endpoints.list.method).toBe('GET')
      expect(auditLogMeta.api.endpoints.list.path).toBe('/logs')
    })

    it('list 端点应该支持 category 和 level 参数映射', () => {
      const params = auditLogMeta.api.endpoints.list.params
      expect(params.logCategory).toBe('log_category')
      expect(params.logLevel).toBe('log_level')
    })

    it('应该包含 detail 端点', () => {
      expect(auditLogMeta.api.endpoints.detail).toBeDefined()
      expect(auditLogMeta.api.endpoints.detail.method).toBe('GET')
      expect(auditLogMeta.api.endpoints.detail.path).toBe('/logs/:id')
    })
  })
})
