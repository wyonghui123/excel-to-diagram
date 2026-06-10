/**
 * useFieldPolicy.spec.js - 字段策略 Composable 测试
 *
 * 测试核心功能：
 * 1. editableMap/visibleMap/immutableMap 计算属性
 * 2. isEditable 判断优先级
 * 3. isVisible/isImmutable 判断
 * 4. evaluateMutability 三种模式
 * 5. isNewRowCheck 新行检测
 * 6. getEditableFields/getReadonlyFields 批量过滤
 * 7. isRowEditable 行级可编辑性
 * 8. isSystemField 系统字段判断
 */

import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useFieldPolicy } from '@/composables/useFieldPolicy'

function createMetaConfig(fields) {
  return ref({ fields })
}

describe('useFieldPolicy', () => {
  describe('isSystemField', () => {
    it('identifies system fields correctly', () => {
      const metaConfig = createMetaConfig([])
      const { isSystemField } = useFieldPolicy(metaConfig)

      expect(isSystemField('id')).toBe(true)
      expect(isSystemField('created_at')).toBe(true)
      expect(isSystemField('updated_at')).toBe(true)
      expect(isSystemField('created_by')).toBe(true)
      expect(isSystemField('updated_by')).toBe(true)
      expect(isSystemField('is_system')).toBe(true)
    })

    it('identifies non-system fields correctly', () => {
      const metaConfig = createMetaConfig([])
      const { isSystemField } = useFieldPolicy(metaConfig)

      expect(isSystemField('username')).toBe(false)
      expect(isSystemField('name')).toBe(false)
      expect(isSystemField('status')).toBe(false)
      expect(isSystemField('email')).toBe(false)
    })

    it('handles case-insensitive check', () => {
      const metaConfig = createMetaConfig([])
      const { isSystemField } = useFieldPolicy(metaConfig)

      expect(isSystemField('ID')).toBe(true)
      expect(isSystemField('Created_At')).toBe(true)
    })

    it('handles null/undefined input', () => {
      const metaConfig = createMetaConfig([])
      const { isSystemField } = useFieldPolicy(metaConfig)

      expect(isSystemField(null)).toBe(false)
      expect(isSystemField(undefined)).toBe(false)
    })
  })

  describe('editableMap', () => {
    it('returns empty map when no fields', () => {
      const metaConfig = ref({})
      const { editableMap } = useFieldPolicy(metaConfig)
      expect(Object.keys(editableMap.value)).toHaveLength(0)
    })

    it('marks system fields as not editable', () => {
      const metaConfig = createMetaConfig([
        { id: 'id' },
        { id: 'created_at' },
        { id: 'updated_by' },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['id']).toBe(false)
      expect(editableMap.value['created_at']).toBe(false)
      expect(editableMap.value['updated_by']).toBe(false)
    })

    it('does not block immutable fields in editableMap (delegates to isEditable)', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', semantics: { immutable: true } },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['code']).toBe(true)
    })

    it('respects ui.editable = false', () => {
      const metaConfig = createMetaConfig([
        { id: 'status', ui: { editable: false } },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['status']).toBe(false)
    })

    it('marks normal fields as editable', () => {
      const metaConfig = createMetaConfig([
        { id: 'name' },
        { id: 'email' },
        { id: 'description' },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['name']).toBe(true)
      expect(editableMap.value['email']).toBe(true)
      expect(editableMap.value['description']).toBe(true)
    })

    it('handles mixed field configurations', () => {
      const metaConfig = createMetaConfig([
        { id: 'id' },
        { id: 'code', semantics: { immutable: true } },
        { id: 'status', ui: { editable: false } },
        { id: 'name' },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['id']).toBe(false)
      expect(editableMap.value['status']).toBe(false)
      expect(editableMap.value['code']).toBe(true)
      expect(editableMap.value['name']).toBe(true)
    })

    it('marks readonly_always fields as not editable', () => {
      const metaConfig = createMetaConfig([
        { id: 'version_id', semantics: { readonly_always: true } },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['version_id']).toBe(false)
    })

    it('does not block business_key fields in editableMap (delegates to isEditable)', () => {
      const metaConfig = createMetaConfig([
        { id: 'username', semantics: { business_key: true } },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['username']).toBe(true)
    })

    it('marks computed fields as not editable', () => {
      const metaConfig = createMetaConfig([
        { id: 'user_count', computed: true },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['user_count']).toBe(false)
    })

    it('respects field.editable = false from backend', () => {
      const metaConfig = createMetaConfig([
        { id: 'created_at', editable: false },
        { id: 'updated_at', editable: false },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['created_at']).toBe(false)
      expect(editableMap.value['updated_at']).toBe(false)
    })

    it('does not block immutable fields in editableMap (delegates to isEditable)', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', semantics: { immutable: true } },
      ])
      const { editableMap } = useFieldPolicy(metaConfig)

      expect(editableMap.value['code']).toBe(true)
    })
  })

  describe('visibleMap', () => {
    it('marks system fields as not visible', () => {
      const metaConfig = createMetaConfig([
        { id: 'id' },
        { id: 'created_at' },
      ])
      const { visibleMap } = useFieldPolicy(metaConfig)

      expect(visibleMap.value['id']).toBe(false)
      expect(visibleMap.value['created_at']).toBe(false)
    })

    it('respects ui.visible = false', () => {
      const metaConfig = createMetaConfig([
        { id: 'password_hash', ui: { visible: false } },
      ])
      const { visibleMap } = useFieldPolicy(metaConfig)

      expect(visibleMap.value['password_hash']).toBe(false)
    })

    it('marks normal fields as visible', () => {
      const metaConfig = createMetaConfig([
        { id: 'name' },
        { id: 'email' },
      ])
      const { visibleMap } = useFieldPolicy(metaConfig)

      expect(visibleMap.value['name']).toBe(true)
      expect(visibleMap.value['email']).toBe(true)
    })

    it('marks fields as invisible when field.visible = false', () => {
      const metaConfig = createMetaConfig([
        { id: 'password', visible: false },
        { id: 'name', visible: true },
      ])
      const { visibleMap } = useFieldPolicy(metaConfig)

      expect(visibleMap.value['password']).toBe(false)
      expect(visibleMap.value['name']).toBe(true)
    })
  })

  describe('immutableMap', () => {
    it('marks system fields as immutable', () => {
      const metaConfig = createMetaConfig([
        { id: 'id' },
        { id: 'created_at' },
      ])
      const { immutableMap } = useFieldPolicy(metaConfig)

      expect(immutableMap.value['id']).toBe(true)
      expect(immutableMap.value['created_at']).toBe(true)
    })

    it('marks semantics.immutable fields as immutable', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', semantics: { immutable: true } },
        { id: 'name' },
      ])
      const { immutableMap } = useFieldPolicy(metaConfig)

      expect(immutableMap.value['code']).toBe(true)
      expect(immutableMap.value['name']).toBe(false)
    })

    it('marks field.immutable as immutable from backend', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', immutable: true },
      ])
      const { immutableMap } = useFieldPolicy(metaConfig)

      expect(immutableMap.value['code']).toBe(true)
    })
  })

  describe('readonlyAlwaysMap', () => {
    it('marks readonly_always fields', () => {
      const metaConfig = createMetaConfig([
        { id: 'version_id', semantics: { readonly_always: true } },
        { id: 'name' },
      ])
      const { readonlyAlwaysMap } = useFieldPolicy(metaConfig)

      expect(readonlyAlwaysMap.value['version_id']).toBe(true)
      expect(readonlyAlwaysMap.value['name']).toBe(false)
    })

    it('returns false when no semantics', () => {
      const metaConfig = createMetaConfig([
        { id: 'description' },
      ])
      const { readonlyAlwaysMap } = useFieldPolicy(metaConfig)

      expect(readonlyAlwaysMap.value['description']).toBe(false)
    })
  })

  describe('businessKeyMap', () => {
    it('marks business_key fields', () => {
      const metaConfig = createMetaConfig([
        { id: 'username', semantics: { business_key: true } },
        { id: 'name' },
      ])
      const { businessKeyMap } = useFieldPolicy(metaConfig)

      expect(businessKeyMap.value['username']).toBe(true)
      expect(businessKeyMap.value['name']).toBe(false)
    })
  })

  describe('isEditable', () => {
    it('returns false for system fields', () => {
      const metaConfig = createMetaConfig([{ id: 'id' }])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('id')).toBe(false)
      expect(isEditable('created_at')).toBe(false)
    })

    it('returns false for immutable fields on existing rows', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', semantics: { immutable: true } },
      ])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('code', { id: 1 })).toBe(false)
    })

    it('returns true for immutable fields on new rows (create mode)', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', semantics: { immutable: true } },
      ])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('code', { id: '__new_1' })).toBe(true)
      expect(isEditable('code', { id: 1, _isNew: true })).toBe(true)
    })

    it('returns false for readonly_always fields even on new rows', () => {
      const metaConfig = createMetaConfig([
        { id: 'version_id', semantics: { readonly_always: true } },
      ])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('version_id')).toBe(false)
      expect(isEditable('version_id', { id: '__new_1' })).toBe(false)
      expect(isEditable('version_id', { id: 1, _isNew: true })).toBe(false)
    })

    it('returns false for business_key fields on existing rows, true on new rows', () => {
      const metaConfig = createMetaConfig([
        { id: 'username', semantics: { business_key: true } },
      ])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('username', { id: 1 })).toBe(false)
      expect(isEditable('username', { id: '__new_1' })).toBe(true)
      expect(isEditable('username', { id: 1, _isNew: true })).toBe(true)
    })

    it('returns false for computed fields', () => {
      const metaConfig = createMetaConfig([
        { id: 'user_count', computed: true },
      ])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('user_count')).toBe(false)
    })

    it('returns false for ui.editable = false', () => {
      const metaConfig = createMetaConfig([
        { id: 'status', ui: { editable: false } },
      ])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('status')).toBe(false)
    })

    it('returns true for normal fields', () => {
      const metaConfig = createMetaConfig([{ id: 'name' }])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('name')).toBe(true)
    })

    it('evaluates mutability when provided', () => {
      const metaConfig = createMetaConfig([{ id: 'name' }])
      const { isEditable } = useFieldPolicy(metaConfig)

      expect(isEditable('name', {}, 'locked')).toBe(false)
      expect(isEditable('name', {}, 'fully_editable')).toBe(true)
      expect(isEditable('name', { is_system: false }, 'extensible')).toBe(true)
      expect(isEditable('name', { is_system: true }, 'extensible')).toBe(false)
    })

    // [FIX 2026-06-10] 新增行 (enum_value.code 等业务主键) 在 API 加载时
    // 必须用本地 readonly_always / system 兜底，否则 immutable 字段无法录入。
    describe('with backend field-policies loaded (simulating read context)', () => {
      it('allows editing immutable business_key field on new row even when API says editable=false', () => {
        const metaConfig = createMetaConfig([
          { id: 'code', semantics: { business_key: true, immutable: true } },
        ])
        const { isEditable, fieldPolicies } = useFieldPolicy(metaConfig)
        // 模拟后端在 read context 返回的策略
        fieldPolicies.value = {
          code: { editable: false, visible: true, required: true },
        }

        // 现有行：API 说不可编辑 → 不可编辑
        expect(isEditable('code', { id: 1 })).toBe(false)
        // 新增行：必须用本地语义重新评估 → 可编辑
        expect(isEditable('code', { id: '__new_1' })).toBe(true)
        expect(isEditable('code', { id: 1, _isNew: true })).toBe(true)
      })

      it('keeps readonly_always fields un-editable on new rows even with API', () => {
        const metaConfig = createMetaConfig([
          { id: 'enum_type_id', semantics: { readonly_always: true, parent_key: true } },
        ])
        const { isEditable, fieldPolicies } = useFieldPolicy(metaConfig)
        fieldPolicies.value = {
          enum_type_id: { editable: false, visible: true, required: true },
        }

        expect(isEditable('enum_type_id', { id: '__new_1' })).toBe(false)
        expect(isEditable('enum_type_id', { id: 1, _isNew: true })).toBe(false)
      })

      it('keeps system fields un-editable on new rows even with API', () => {
        const metaConfig = createMetaConfig([{ id: 'id' }])
        const { isEditable, fieldPolicies } = useFieldPolicy(metaConfig)
        fieldPolicies.value = {
          id: { editable: false, visible: false, required: false },
        }

        expect(isEditable('id', { id: '__new_1' })).toBe(false)
      })

      it('respects ui.editable=false on new rows even with API', () => {
        const metaConfig = createMetaConfig([
          { id: 'status', ui: { editable: false } },
        ])
        const { isEditable, fieldPolicies } = useFieldPolicy(metaConfig)
        fieldPolicies.value = {
          status: { editable: false, visible: true, required: false },
        }

        // 新行时 ui.editable=false 仍不可编辑（与 fallback 行为一致）
        expect(isEditable('status', { id: '__new_1' })).toBe(false)
      })

      it('keeps existing-row behavior unchanged with API loaded', () => {
        const metaConfig = createMetaConfig([{ id: 'name' }])
        const { isEditable, fieldPolicies } = useFieldPolicy(metaConfig)
        fieldPolicies.value = {
          name: { editable: true, visible: true, required: false },
        }

        // 现有行：API 说可编辑 → 可编辑
        expect(isEditable('name', { id: 1 })).toBe(true)
        // 新增行：API 说可编辑 → 仍可编辑
        expect(isEditable('name', { id: '__new_1' })).toBe(true)
      })
    })
  })

  describe('isVisible', () => {
    it('returns false for system fields', () => {
      const metaConfig = createMetaConfig([{ id: 'id' }])
      const { isVisible } = useFieldPolicy(metaConfig)

      expect(isVisible('id')).toBe(false)
    })

    it('returns false for ui.visible = false', () => {
      const metaConfig = createMetaConfig([
        { id: 'secret', ui: { visible: false } },
      ])
      const { isVisible } = useFieldPolicy(metaConfig)

      expect(isVisible('secret')).toBe(false)
    })

    it('returns true for normal fields', () => {
      const metaConfig = createMetaConfig([{ id: 'name' }])
      const { isVisible } = useFieldPolicy(metaConfig)

      expect(isVisible('name')).toBe(true)
    })
  })

  describe('isImmutable', () => {
    it('returns true for system fields', () => {
      const metaConfig = createMetaConfig([{ id: 'id' }])
      const { isImmutable } = useFieldPolicy(metaConfig)

      expect(isImmutable('id')).toBe(true)
    })

    it('returns true for immutable semantic fields', () => {
      const metaConfig = createMetaConfig([
        { id: 'code', semantics: { immutable: true } },
      ])
      const { isImmutable } = useFieldPolicy(metaConfig)

      expect(isImmutable('code')).toBe(true)
    })

    it('returns false for normal fields', () => {
      const metaConfig = createMetaConfig([{ id: 'name' }])
      const { isImmutable } = useFieldPolicy(metaConfig)

      expect(isImmutable('name')).toBe(false)
    })
  })

  describe('evaluateMutability', () => {
    it('returns false for locked', () => {
      const metaConfig = createMetaConfig([])
      const { evaluateMutability } = useFieldPolicy(metaConfig)

      expect(evaluateMutability('name', {}, 'locked')).toBe(false)
    })

    it('returns true for fully_editable', () => {
      const metaConfig = createMetaConfig([])
      const { evaluateMutability } = useFieldPolicy(metaConfig)

      expect(evaluateMutability('name', {}, 'fully_editable')).toBe(true)
    })

    it('returns false for system fields in extensible mode', () => {
      const metaConfig = createMetaConfig([])
      const { evaluateMutability } = useFieldPolicy(metaConfig)

      expect(evaluateMutability('id', {}, 'extensible')).toBe(false)
    })

    it('returns false for is_system rows in extensible mode', () => {
      const metaConfig = createMetaConfig([])
      const { evaluateMutability } = useFieldPolicy(metaConfig)

      expect(evaluateMutability('name', { is_system: true }, 'extensible')).toBe(false)
    })

    it('returns true for non-system rows in extensible mode', () => {
      const metaConfig = createMetaConfig([])
      const { evaluateMutability } = useFieldPolicy(metaConfig)

      expect(evaluateMutability('name', { is_system: false }, 'extensible')).toBe(true)
    })

    it('returns true for unknown mutability', () => {
      const metaConfig = createMetaConfig([])
      const { evaluateMutability } = useFieldPolicy(metaConfig)

      expect(evaluateMutability('name', {}, 'unknown')).toBe(true)
    })
  })

  describe('isNewRowCheck', () => {
    it('detects __new_ prefix', () => {
      const metaConfig = createMetaConfig([])
      const { isNewRowCheck } = useFieldPolicy(metaConfig)

      expect(isNewRowCheck({ id: '__new_1' })).toBe(true)
      expect(isNewRowCheck({ id: '__new_abc' })).toBe(true)
    })

    it('detects _isNew flag', () => {
      const metaConfig = createMetaConfig([])
      const { isNewRowCheck } = useFieldPolicy(metaConfig)

      expect(isNewRowCheck({ id: 1, _isNew: true })).toBe(true)
      expect(isNewRowCheck({ id: 1, _isNew: false })).toBe(false)
    })

    it('returns false for existing rows', () => {
      const metaConfig = createMetaConfig([])
      const { isNewRowCheck } = useFieldPolicy(metaConfig)

      expect(isNewRowCheck({ id: 1 })).toBe(false)
      expect(isNewRowCheck({ id: 42 })).toBe(false)
    })

    it('returns false for null row', () => {
      const metaConfig = createMetaConfig([])
      const { isNewRowCheck } = useFieldPolicy(metaConfig)

      expect(isNewRowCheck(null)).toBe(false)
      expect(isNewRowCheck(undefined)).toBe(false)
    })
  })

  describe('getEditableFields', () => {
    it('filters editable fields', () => {
      const metaConfig = createMetaConfig([
        { id: 'id' },
        { id: 'name' },
        { id: 'code', semantics: { immutable: true } },
        { id: 'email' },
      ])
      const { getEditableFields } = useFieldPolicy(metaConfig)

      const result = getEditableFields(['id', 'name', 'code', 'email'])
      expect(result).toEqual(['name', 'email'])
    })

    it('respects mutability', () => {
      const metaConfig = createMetaConfig([
        { id: 'name' },
      ])
      const { getEditableFields } = useFieldPolicy(metaConfig)

      expect(getEditableFields(['name'], {}, 'locked')).toEqual([])
      expect(getEditableFields(['name'], {}, 'fully_editable')).toEqual(['name'])
    })
  })

  describe('getReadonlyFields', () => {
    it('filters readonly fields', () => {
      const metaConfig = createMetaConfig([
        { id: 'id' },
        { id: 'name' },
        { id: 'code', semantics: { immutable: true } },
      ])
      const { getReadonlyFields } = useFieldPolicy(metaConfig)

      const result = getReadonlyFields(['id', 'name', 'code'])
      expect(result).toEqual(['id', 'code'])
    })
  })

  describe('isRowEditable', () => {
    it('returns true when no mutability', () => {
      const metaConfig = createMetaConfig([])
      const { isRowEditable } = useFieldPolicy(metaConfig)

      expect(isRowEditable({ id: 1 })).toBe(true)
    })

    it('returns false for locked mutability', () => {
      const metaConfig = createMetaConfig([])
      const { isRowEditable } = useFieldPolicy(metaConfig)

      expect(isRowEditable({ id: 1 }, 'locked')).toBe(false)
    })

    it('returns true for fully_editable mutability', () => {
      const metaConfig = createMetaConfig([])
      const { isRowEditable } = useFieldPolicy(metaConfig)

      expect(isRowEditable({ id: 1 }, 'fully_editable')).toBe(true)
    })

    it('returns true for create action in extensible mode', () => {
      const metaConfig = createMetaConfig([])
      const { isRowEditable } = useFieldPolicy(metaConfig)

      expect(isRowEditable({}, 'extensible', 'create')).toBe(true)
    })

    it('returns false for is_system rows in extensible mode', () => {
      const metaConfig = createMetaConfig([])
      const { isRowEditable } = useFieldPolicy(metaConfig)

      expect(isRowEditable({ is_system: true }, 'extensible', 'update')).toBe(false)
    })

    it('returns true for non-system rows in extensible mode', () => {
      const metaConfig = createMetaConfig([])
      const { isRowEditable } = useFieldPolicy(metaConfig)

      expect(isRowEditable({ is_system: false }, 'extensible', 'update')).toBe(true)
    })
  })
})
