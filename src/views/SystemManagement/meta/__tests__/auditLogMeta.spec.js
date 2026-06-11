/**
 * auditLogMeta.spec.js - 审计日志元数据配置测试
 *
 * M5: 前端扩展测试
 * 测试范围：
 * 1. 元数据基本结构完整性
 * 2. 表格列定义包含 log_category 和 log_level
 * 3. 过滤器定义包含日志类型和级别筛选
 * 4. 详情配置完整性
 * 5. API 配置完整性
 * 6. 元数据与后端 YAML 配置一致性
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
      expect(auditLogMeta.list.defaultSort.order).toBe('desc')
    })

    it('应该包含分页配置', () => {
      expect(auditLogMeta.list.pagination).toBeDefined()
      expect(auditLogMeta.list.pagination.pageSize).toBe(20)
    })
  })

  describe('表格列定义', () => {
    it('应该包含 log_category 列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'log_category')
      expect(col).toBeDefined()
      expect(col.label).toBe('日志类型')
      expect(col.type).toBe('tag')
      expect(col.sortable).toBe(true)
    })

    it('log_category 列应该有正确的选项', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'log_category')
      const values = col.options.map(o => o.value)
      expect(values).toContain('business')
      expect(values).toContain('security')
      expect(values).toContain('operation')
      expect(values).toContain('performance')
      expect(values).toContain('system')
    })

    it('应该包含 log_level 列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'log_level')
      expect(col).toBeDefined()
      expect(col.label).toBe('日志级别')
      expect(col.type).toBe('tag')
      expect(col.sortable).toBe(true)
    })

    it('log_level 列应该有正确的选项', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'log_level')
      const values = col.options.map(o => o.value)
      expect(values).toContain('DEBUG')
      expect(values).toContain('INFO')
      expect(values).toContain('WARNING')
      expect(values).toContain('ERROR')
      expect(values).toContain('CRITICAL')
    })

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

    it('应该包含业务标识列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'formatted_identity')
      expect(col).toBeDefined()
    })

    it('应该包含 IP 地址列', () => {
      const col = auditLogMeta.tableColumns.find(c => c.key === 'ip_address')
      expect(col).toBeDefined()
    })
  })

  describe('过滤器定义', () => {
    it('应该包含 log_category 过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'log_category')
      expect(filter).toBeDefined()
      expect(filter.label).toBe('日志类型')
      expect(filter.type).toBe('select')
      const values = filter.options.map(o => o.value)
      expect(values).toContain('business')
      expect(values).toContain('security')
    })

    it('应该包含 log_level 过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'log_level')
      expect(filter).toBeDefined()
      expect(filter.label).toBe('日志级别')
      expect(filter.type).toBe('select')
      const values = filter.options.map(o => o.value)
      expect(values).toContain('DEBUG')
      expect(values).toContain('INFO')
      expect(values).toContain('WARNING')
    })

    it('应该包含 action 过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'action')
      expect(filter).toBeDefined()
      expect(filter.type).toBe('select')
    })

    it('应该包含 object_type 过滤器', () => {
      const filter = auditLogMeta.filters.find(f => f.key === 'object_type')
      expect(filter).toBeDefined()
      expect(filter.type).toBe('select')
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

    it('详情应该包含基本信息分区', () => {
      const section = auditLogMeta.detail.sections.find(s => s.title === '基本信息')
      expect(section).toBeDefined()
      const fieldKeys = section.fields.map(f => f.key)
      expect(fieldKeys).toContain('id')
      expect(fieldKeys).toContain('created_at')
      expect(fieldKeys).toContain('log_category')
      expect(fieldKeys).toContain('log_level')
      expect(fieldKeys).toContain('action')
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

    it('log_category 在详情中应有 tag 类型和选项', () => {
      const basicSection = auditLogMeta.detail.sections.find(s => s.title === '基本信息')
      const categoryField = basicSection.fields.find(f => f.key === 'log_category')
      expect(categoryField.type).toBe('tag')
      expect(categoryField.options).toBeDefined()
      expect(categoryField.options.length).toBeGreaterThan(0)
    })

    it('log_level 在详情中应有 tag 类型和选项', () => {
      const basicSection = auditLogMeta.detail.sections.find(s => s.title === '基本信息')
      const levelField = basicSection.fields.find(f => f.key === 'log_level')
      expect(levelField.type).toBe('tag')
      expect(levelField.options).toBeDefined()
      expect(levelField.options.length).toBeGreaterThan(0)
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

  describe('元数据一致性', () => {
    it('过滤器中的 category 选项应与列定义一致', () => {
      const colOptions = auditLogMeta.tableColumns
        .find(c => c.key === 'log_category').options.map(o => o.value)
      const filterOptions = auditLogMeta.filters
        .find(f => f.key === 'log_category').options
        .filter(o => o.value !== '')
        .map(o => o.value)
      expect(filterOptions).toEqual(colOptions)
    })

    it('过滤器中的 level 选项应与列定义一致', () => {
      const colOptions = auditLogMeta.tableColumns
        .find(c => c.key === 'log_level').options.map(o => o.value)
      const filterOptions = auditLogMeta.filters
        .find(f => f.key === 'log_level').options
        .filter(o => o.value !== '')
        .map(o => o.value)
      expect(filterOptions).toEqual(colOptions)
    })

    it('详情中的 category 选项应与列定义一致', () => {
      const colOptions = auditLogMeta.tableColumns
        .find(c => c.key === 'log_category').options.map(o => o.value)
      const basicSection = auditLogMeta.detail.sections.find(s => s.title === '基本信息')
      const detailOptions = basicSection.fields
        .find(f => f.key === 'log_category').options.map(o => o.value)
      expect(detailOptions).toEqual(colOptions)
    })

    it('详情中的 level 选项应与列定义一致', () => {
      const colOptions = auditLogMeta.tableColumns
        .find(c => c.key === 'log_level').options.map(o => o.value)
      const basicSection = auditLogMeta.detail.sections.find(s => s.title === '基本信息')
      const detailOptions = basicSection.fields
        .find(f => f.key === 'log_level').options.map(o => o.value)
      expect(detailOptions).toEqual(colOptions)
    })
  })
})
