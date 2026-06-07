import { describe, it, expect } from 'vitest'
import {
  transformColumns,
  inferColumnPriority,
  transformActions,
  inferActionPosition,
  mapVariant,
  inferColumnWidth,
  fixDatetimeColumns,
  enrichColumnsWithFieldMeta,
  getDefaultOrdering,
  filterRowActions,
  inferFieldEditConfig
} from '@/services/metaTransformService'

describe('metaTransformService', () => {
  // ===== transformColumns =====
  describe('transformColumns', () => {
    it('should transform basic column with key', () => {
      const result = transformColumns([{ key: 'name', label: '名称' }])
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('name')
      expect(result[0].prop).toBe('name')
      expect(result[0].label).toBe('名称')
    })

    it('should support field/id as key fallback', () => {
      const result = transformColumns([{ field: 'code', title: '编码' }])
      expect(result[0].key).toBe('code')
      expect(result[0].label).toBe('编码')
    })

    it('should infer datetime type for _at/_time/_date fields', () => {
      const result = transformColumns([{ key: 'created_at', type: 'text' }])
      expect(result[0].type).toBe('datetime')
    })

    it('should not infer datetime for id field', () => {
      const result = transformColumns([{ key: 'id', type: 'integer' }])
      expect(result[0].type).toBe('integer')
    })

    it('should set filterTriggerMode from options', () => {
      const result = transformColumns(
        [{ key: 'name' }],
        { filterDisplayMode: 'always' }
      )
      expect(result[0].filterTriggerMode).toBe('always')
    })

    it('should default filterTriggerMode to hover', () => {
      const result = transformColumns([{ key: 'name' }])
      expect(result[0].filterTriggerMode).toBe('hover')
    })

    it('should mark association columns as slot', () => {
      const result = transformColumns([{ key: 'items', type: 'association' }])
      expect(result[0].slot).toBe(true)
    })

    it('should set visible/default_visible true by default', () => {
      const result = transformColumns([{ key: 'name' }])
      expect(result[0].visible).toBe(true)
      expect(result[0].default_visible).toBe(true)
    })
  })

  // ===== inferColumnPriority =====
  describe('inferColumnPriority', () => {
    it('should return required for id', () => {
      expect(inferColumnPriority({ prop: 'id' })).toBe('required')
    })

    it('should return required for businessKey column', () => {
      expect(inferColumnPriority({ prop: 'code', businessKey: true })).toBe('required')
    })

    it('should return required for code/name/display_name', () => {
      expect(inferColumnPriority({ prop: 'code' })).toBe('required')
      expect(inferColumnPriority({ prop: 'name' })).toBe('required')
      expect(inferColumnPriority({ prop: 'display_name' })).toBe('required')
    })

    it('should return default for created_at', () => {
      expect(inferColumnPriority({ prop: 'created_at' })).toBe('default')
    })

    it('should return default for datetime type', () => {
      expect(inferColumnPriority({ prop: 'custom', type: 'datetime' })).toBe('default')
    })

    it('should return default for unknown columns', () => {
      expect(inferColumnPriority({ prop: 'description' })).toBe('default')
    })
  })

  // ===== transformActions =====
  describe('transformActions', () => {
    it('should transform action with id and label', () => {
      const result = transformActions([{ id: 'create', label: '新建' }])
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('create')
      expect(result[0].label).toBe('新建')
    })

    it('should use default labels for known actions', () => {
      const result = transformActions([{ id: 'create' }])
      expect(result[0].label).toBe('新建')
    })

    it('should filter out show=false actions', () => {
      const result = transformActions([
        { id: 'create' },
        { id: 'delete', show: false }
      ])
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('create')
    })

    it('should handle null/undefined input', () => {
      expect(transformActions(null)).toEqual([])
      expect(transformActions(undefined)).toEqual([])
    })
  })

  // ===== inferActionPosition =====
  describe('inferActionPosition', () => {
    it('should return batch for batch_ prefix', () => {
      expect(inferActionPosition({ id: 'batch_delete' })).toBe('batch')
      expect(inferActionPosition({ id: 'batch_custom' })).toBe('batch')
    })

    it('should return toolbar for create/new/add/import/export', () => {
      expect(inferActionPosition({ id: 'create' })).toBe('toolbar')
      expect(inferActionPosition({ id: 'import' })).toBe('toolbar')
    })

    it('should return row for edit/delete/view', () => {
      expect(inferActionPosition({ id: 'edit' })).toBe('row')
      expect(inferActionPosition({ id: 'delete' })).toBe('row')
    })

    it('should default to row for unknown actions', () => {
      expect(inferActionPosition({ id: 'custom_action' })).toBe('row')
    })
  })

  // ===== mapVariant =====
  describe('mapVariant', () => {
    it('should return empty string for row position', () => {
      expect(mapVariant('primary', 'row')).toBe('')
    })

    it('should map known variants for non-row positions', () => {
      expect(mapVariant('primary', 'toolbar')).toBe('primary')
      expect(mapVariant('danger', 'toolbar')).toBe('danger')
    })

    it('should return empty string for default/text variant', () => {
      expect(mapVariant('default', 'toolbar')).toBe('')
      expect(mapVariant('text', 'toolbar')).toBe('')
    })

    it('should pass through unknown variants', () => {
      expect(mapVariant('custom', 'toolbar')).toBe('custom')
    })
  })

  // ===== inferColumnWidth =====
  describe('inferColumnWidth', () => {
    it('should return narrow width for id fields', () => {
      const result = inferColumnWidth({ field: 'id' })
      expect(result.width).toBe(100)
      expect(result.minWidth).toBe(80)
    })

    it('should return wide width for datetime fields', () => {
      const result = inferColumnWidth({ type: 'datetime' })
      expect(result.width).toBe(160)
    })

    it('should return wide width for description fields', () => {
      const result = inferColumnWidth({ field: 'description' })
      expect(result.width).toBe(250)
    })

    it('should return narrow width for boolean fields', () => {
      const result = inferColumnWidth({ type: 'boolean' })
      expect(result.width).toBe(80)
    })

    it('should return default width for unknown fields', () => {
      const result = inferColumnWidth({ field: 'custom_field' })
      expect(result.width).toBe(120)
    })
  })

  // ===== fixDatetimeColumns =====
  describe('fixDatetimeColumns', () => {
    it('should set type=datetime for _at fields', () => {
      const cols = [{ key: 'created_at', prop: 'created_at', type: 'text' }]
      fixDatetimeColumns(cols)
      expect(cols[0].type).toBe('datetime')
    })

    it('should not change id field', () => {
      const cols = [{ key: 'id', prop: 'id', type: 'integer' }]
      fixDatetimeColumns(cols)
      expect(cols[0].type).toBe('integer')
    })

    it('should handle empty array', () => {
      expect(() => fixDatetimeColumns([])).not.toThrow()
    })

    it('should handle null', () => {
      expect(() => fixDatetimeColumns(null)).not.toThrow()
    })
  })

  // ===== enrichColumnsWithFieldMeta =====
  describe('enrichColumnsWithFieldMeta', () => {
    it('should enrich column with field type', () => {
      const columns = [{ prop: 'status', type: 'text' }]
      const fields = [{ id: 'status', type: 'enum' }]
      const result = enrichColumnsWithFieldMeta(columns, fields)
      expect(result[0].type).toBe('enum')
    })

    it('should match _id suffix fields', () => {
      const columns = [{ prop: 'user_id', type: 'text' }]
      const fields = [{ id: 'user', type: 'fk' }]
      const result = enrichColumnsWithFieldMeta(columns, fields)
      expect(result[0].type).toBe('fk')
    })

    it('should set businessKey from field', () => {
      const columns = [{ prop: 'code', type: 'text' }]
      const fields = [{ id: 'code', business_key: true }]
      const result = enrichColumnsWithFieldMeta(columns, fields)
      expect(result[0].businessKey).toBe(true)
    })

    it('should convert boolean enum_values to int', () => {
      const columns = [{ prop: 'active', type: 'text' }]
      const fields = [{ id: 'active', type: 'boolean', enum_values: [
        { label: '是', value: true },
        { label: '否', value: false }
      ]}]
      const result = enrichColumnsWithFieldMeta(columns, fields)
      expect(result[0].enum_values[0].value).toBe(1)
      expect(result[0].enum_values[1].value).toBe(0)
    })

    it('should return new array (immutable)', () => {
      const columns = [{ prop: 'name', type: 'text' }]
      const result = enrichColumnsWithFieldMeta(columns, [])
      expect(result).not.toBe(columns)
    })

    it('should return columns as-is for empty fields', () => {
      const columns = [{ prop: 'name', type: 'text' }]
      const result = enrichColumnsWithFieldMeta(columns, [])
      expect(result[0].type).toBe('text')
    })
  })

  // ===== getDefaultOrdering =====
  describe('getDefaultOrdering', () => {
    it('should return null for null metaConfig', () => {
      expect(getDefaultOrdering(null)).toBeNull()
    })

    it('should return defaultOrdering from list config', () => {
      const meta = { list: { defaultOrdering: '-updated_at' } }
      expect(getDefaultOrdering(meta)).toBe('-updated_at')
    })

    it('should return defaultSort with desc prefix', () => {
      const meta = { list: { defaultSort: { field: 'created_at', order: 'desc' } } }
      expect(getDefaultOrdering(meta)).toBe('-created_at')
    })

    it('should return defaultSort with asc no prefix', () => {
      const meta = { list: { defaultSort: { field: 'name', order: 'asc' } } }
      expect(getDefaultOrdering(meta)).toBe('name')
    })
  })

  // ===== filterRowActions =====
  describe('filterRowActions', () => {
    const actions = [
      { key: 'edit' },
      { key: 'delete' },
      { key: 'view' }
    ]

    it('should return all actions when no restrictions', () => {
      const result = filterRowActions(actions, {}, 'product', null, null, null)
      expect(result).toHaveLength(3)
    })

    it('should filter edit/delete for locked mutability', () => {
      const result = filterRowActions(actions, {}, 'product', 'locked', null, null)
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('view')
    })

    it('should filter edit for extensible mutability', () => {
      const result = filterRowActions(actions, {}, 'product', 'extensible', null, null)
      expect(result.find(a => a.key === 'edit')).toBeUndefined()
      expect(result.find(a => a.key === 'view')).toBeDefined()
    })

    it('should filter edit/delete for enum_type system category', () => {
      const result = filterRowActions(actions, { category: 'system' }, 'enum_type', null, null, null)
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('view')
    })

    it('should respect checkPermission callback', () => {
      const checkPermission = () => false
      const result = filterRowActions(actions, {}, 'product', null, checkPermission, null)
      expect(result).toHaveLength(0)
    })

    it('should respect evaluateCondition callback', () => {
      const evaluateCondition = () => false
      const result = filterRowActions(actions, {}, 'product', null, null, evaluateCondition)
      expect(result).toHaveLength(0)
    })
  })

  // ===== inferFieldEditConfig =====
  describe('inferFieldEditConfig', () => {
    it('should return null for null column', () => {
      expect(inferFieldEditConfig(null)).toBeNull()
    })

    it('should return value_help type for column with valueHelpConfig.source', () => {
      const col = {
        prop: 'user_id',
        valueHelpConfig: { source: 'user' },
        edit_required: true
      }
      const result = inferFieldEditConfig(col)
      expect(result.type).toBe('value_help')
      expect(result.required).toBe(true)
    })

    it('should infer switch type for boolean', () => {
      const col = { type: 'boolean' }
      const result = inferFieldEditConfig(col)
      expect(result.type).toBe('switch')
    })

    it('should infer number type for integer', () => {
      const col = { type: 'integer' }
      const result = inferFieldEditConfig(col)
      expect(result.type).toBe('number')
    })

    it('should use widget type over field type', () => {
      const col = { type: 'text', widget: 'select' }
      const result = inferFieldEditConfig(col)
      expect(result.type).toBe('select')
    })

    it('should use edit_type over all', () => {
      const col = { type: 'text', widget: 'select', edit_type: 'date' }
      const result = inferFieldEditConfig(col)
      expect(result.type).toBe('date')
    })

    it('should default to text type', () => {
      const col = { type: 'unknown_type' }
      const result = inferFieldEditConfig(col)
      expect(result.type).toBe('text')
    })

    it('should include options from enum_values', () => {
      const col = {
        type: 'enum',
        enum_values: [{ label: 'A', value: 1 }]
      }
      const result = inferFieldEditConfig(col)
      expect(result.options).toEqual([{ label: 'A', value: 1 }])
    })
  })
})
