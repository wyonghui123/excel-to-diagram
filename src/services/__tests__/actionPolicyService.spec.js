/**
 * actionPolicyService 单元测试
 *
 * [P1-B 2026-07-25] 验证行级动作策略规则的正确性
 *   - 覆盖: isNewRow / isSystemRow / canPerformAction 各分支
 *   - 对齐: metaTransformService.filterRowActions 的硬编码原行为
 */

import { describe, it, expect } from 'vitest'
import {
  normalizeActionKey,
  isNewRow,
  isSystemRow,
  canPerformAction,
  filterByRowPolicy,
} from '../actionPolicyService'

describe('actionPolicyService', () => {
  // ===== normalizeActionKey =====
  describe('normalizeActionKey', () => {
    it('归一化 edit/update/modify → edit', () => {
      expect(normalizeActionKey({ key: 'edit' })).toBe('edit')
      expect(normalizeActionKey({ key: 'UPDATE' })).toBe('edit')
      expect(normalizeActionKey({ key: 'Modify' })).toBe('edit')
    })

    it('归一化 create/new/add/新建 → create', () => {
      expect(normalizeActionKey({ key: 'create' })).toBe('create')
      expect(normalizeActionKey({ key: 'NEW' })).toBe('create')
      expect(normalizeActionKey({ key: '新建' })).toBe('create')
    })

    it('归一化 delete/remove/drop → delete', () => {
      expect(normalizeActionKey({ key: 'delete' })).toBe('delete')
      expect(normalizeActionKey({ key: 'REMOVE' })).toBe('delete')
    })

    it('归一化 view/read/detail → view', () => {
      expect(normalizeActionKey({ key: 'view' })).toBe('view')
      expect(normalizeActionKey({ key: 'read' })).toBe('view')
      expect(normalizeActionKey({ key: 'detail' })).toBe('view')
    })

    it('未知 key 原样返回 (lowercase)', () => {
      expect(normalizeActionKey({ key: 'export' })).toBe('export')
      expect(normalizeActionKey({ key: 'CUSTOM' })).toBe('custom')
    })

    it('接受字符串 action key', () => {
      expect(normalizeActionKey('edit')).toBe('edit')
      expect(normalizeActionKey('DELETE')).toBe('delete')
    })

    it('空值安全', () => {
      expect(normalizeActionKey({})).toBe('')
      expect(normalizeActionKey(null)).toBe('')
      expect(normalizeActionKey(undefined)).toBe('')
    })
  })

  // ===== isNewRow =====
  describe('isNewRow', () => {
    it('_isNew=true → true', () => {
      expect(isNewRow({ _isNew: true })).toBe(true)
    })

    it('id 以 __new_ 开头 → true', () => {
      expect(isNewRow({ id: '__new_123' })).toBe(true)
    })

    it('普通行 → false', () => {
      expect(isNewRow({ id: 123 })).toBe(false)
      expect(isNewRow({ id: 'abc' })).toBe(false)
      expect(isNewRow({})).toBe(false)
      expect(isNewRow(null)).toBe(false)
    })

    it('_isNew=false → false', () => {
      expect(isNewRow({ _isNew: false, id: 1 })).toBe(false)
    })
  })

  // ===== isSystemRow =====
  describe('isSystemRow', () => {
    it('is_system=true → true', () => {
      expect(isSystemRow({ is_system: true })).toBe(true)
    })

    it('system_value=true → true', () => {
      expect(isSystemRow({ system_value: true })).toBe(true)
    })

    it('普通行 → false', () => {
      expect(isSystemRow({ is_system: false })).toBe(false)
      expect(isSystemRow({})).toBe(false)
      expect(isSystemRow(null)).toBe(false)
    })
  })

  // ===== canPerformAction =====
  describe('canPerformAction', () => {
    it('默认允许 (无规则匹配)', () => {
      const result = canPerformAction({ key: 'view' }, { id: 1 }, {})
      expect(result.allowed).toBe(true)
      expect(result.reason).toBe('')
    })

    it('view 总是允许 (即使 locked/extensible)', () => {
      expect(canPerformAction({ key: 'view' }, {}, { rowMutability: 'locked' }).allowed).toBe(true)
      expect(canPerformAction({ key: 'view' }, {}, { rowMutability: 'extensible' }).allowed).toBe(true)
    })

    // 规则 1: 新增行
    it('新增行禁 edit/delete', () => {
      const row = { _isNew: true }
      expect(canPerformAction({ key: 'edit' }, row, {}).allowed).toBe(false)
      expect(canPerformAction({ key: 'delete' }, row, {}).allowed).toBe(false)
      expect(canPerformAction({ key: 'update' }, row, {}).allowed).toBe(false)
    })

    it('新增行允许 view', () => {
      expect(canPerformAction({ key: 'view' }, { _isNew: true }, {}).allowed).toBe(true)
    })

    it('新增行 (id=__new_xxx) 也被识别', () => {
      const row = { id: '__new_456' }
      expect(canPerformAction({ key: 'edit' }, row, {}).allowed).toBe(false)
    })

    // 规则 2: enum_type + category=system
    it('enum_type + category=system 禁 edit/delete', () => {
      const row = { category: 'system' }
      const ctx = { objectType: 'enum_type' }
      expect(canPerformAction({ key: 'edit' }, row, ctx).allowed).toBe(false)
      expect(canPerformAction({ key: 'delete' }, row, ctx).allowed).toBe(false)
    })

    it('enum_type + category=custom 允许 edit/delete', () => {
      const row = { category: 'custom' }
      const ctx = { objectType: 'enum_type' }
      expect(canPerformAction({ key: 'edit' }, row, ctx).allowed).toBe(true)
    })

    it('非 enum_type 不应用 category=system 规则', () => {
      const row = { category: 'system' }
      const ctx = { objectType: 'product' }
      expect(canPerformAction({ key: 'edit' }, row, ctx).allowed).toBe(true)
    })

    // 规则 3: rowMutability=locked
    it('locked 禁 edit/delete', () => {
      const ctx = { rowMutability: 'locked' }
      expect(canPerformAction({ key: 'edit' }, {}, ctx).allowed).toBe(false)
      expect(canPerformAction({ key: 'delete' }, {}, ctx).allowed).toBe(false)
      expect(canPerformAction({ key: 'update' }, {}, ctx).allowed).toBe(false)
    })

    it('locked 允许 view', () => {
      expect(canPerformAction({ key: 'view' }, {}, { rowMutability: 'locked' }).allowed).toBe(true)
    })

    // 规则 4: rowMutability=extensible
    it('extensible 禁 edit', () => {
      expect(canPerformAction({ key: 'edit' }, {}, { rowMutability: 'extensible' }).allowed).toBe(false)
    })

    it('extensible + 非系统行 允许 delete', () => {
      const row = { is_system: false }
      expect(canPerformAction({ key: 'delete' }, row, { rowMutability: 'extensible' }).allowed).toBe(true)
    })

    it('extensible + 系统行 (is_system=true) 禁 delete', () => {
      const row = { is_system: true }
      const result = canPerformAction({ key: 'delete' }, row, { rowMutability: 'extensible' })
      expect(result.allowed).toBe(false)
      expect(result.reason).toContain('系统')
    })

    it('extensible + 系统行 (system_value=true) 禁 delete', () => {
      const row = { system_value: true }
      expect(canPerformAction({ key: 'delete' }, row, { rowMutability: 'extensible' }).allowed).toBe(false)
    })

    it('extensible 允许 view', () => {
      expect(canPerformAction({ key: 'view' }, {}, { rowMutability: 'extensible' }).allowed).toBe(true)
    })

    // 规则 5: fullEditable / null
    it('fullEditable 全部允许', () => {
      const ctx = { rowMutability: 'fullEditable' }
      expect(canPerformAction({ key: 'edit' }, {}, ctx).allowed).toBe(true)
      expect(canPerformAction({ key: 'delete' }, {}, ctx).allowed).toBe(true)
    })

    it('rowMutability=null 全部允许', () => {
      expect(canPerformAction({ key: 'edit' }, {}, {}).allowed).toBe(true)
      expect(canPerformAction({ key: 'delete' }, {}, {}).allowed).toBe(true)
    })

    // 多规则组合: 新增行 + locked
    it('多规则组合: 新增行 + locked → 仍然禁 edit', () => {
      const row = { _isNew: true }
      const ctx = { rowMutability: 'locked' }
      expect(canPerformAction({ key: 'edit' }, row, ctx).allowed).toBe(false)
    })

    // 返回 reason
    it('拒绝时返回非空 reason', () => {
      const result = canPerformAction({ key: 'edit' }, {}, { rowMutability: 'locked' })
      expect(result.allowed).toBe(false)
      expect(result.reason).toBeTruthy()
    })
  })

  // ===== filterByRowPolicy =====
  describe('filterByRowPolicy', () => {
    const actions = [
      { key: 'edit' },
      { key: 'delete' },
      { key: 'view' },
    ]

    it('无限制时全部通过', () => {
      const result = filterByRowPolicy(actions, { id: 1 }, {})
      expect(result).toHaveLength(3)
    })

    it('locked 仅 view 通过', () => {
      const result = filterByRowPolicy(actions, {}, { rowMutability: 'locked' })
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('view')
    })

    it('extensible 过滤 edit', () => {
      const result = filterByRowPolicy(actions, {}, { rowMutability: 'extensible' })
      expect(result.find(a => a.key === 'edit')).toBeUndefined()
      expect(result.find(a => a.key === 'view')).toBeDefined()
      expect(result.find(a => a.key === 'delete')).toBeDefined()
    })

    it('enum_type + system 仅 view 通过', () => {
      const result = filterByRowPolicy(actions, { category: 'system' }, { objectType: 'enum_type' })
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('view')
    })

    it('extensible + 系统行 仅 view 通过', () => {
      const result = filterByRowPolicy(actions, { is_system: true }, { rowMutability: 'extensible' })
      expect(result).toHaveLength(1)
      expect(result[0].key).toBe('view')
    })

    it('非数组输入返回空数组', () => {
      expect(filterByRowPolicy(null, {}, {})).toEqual([])
      expect(filterByRowPolicy(undefined, {}, {})).toEqual([])
      expect(filterByRowPolicy('abc', {}, {})).toEqual([])
    })
  })
})
