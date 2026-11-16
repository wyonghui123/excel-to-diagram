import { afterEach, describe, expect, it } from 'vitest'

import {
  evalCondition,
  isActionVisible,
  isFieldReadonly,
  isVisible,
  mergeFieldPolicies,
  setCurrentRoles,
} from '@/services/metaResourceService'

afterEach(() => {
  setCurrentRoles(null)
})

describe('evalCondition（封闭文法）', () => {
  it('in 命中/未命中', () => {
    const condition = { field: 'status', in: ['failed', 'timeout'] }
    expect(evalCondition(condition, { status: 'failed' })).toBe(true)
    expect(evalCondition(condition, { status: 'success' })).toBe(false)
  })

  it('equals 数字/字符串宽松比较', () => {
    expect(evalCondition({ field: 'source', equals: 1 }, { source: '1' })).toBe(true)
    expect(evalCondition({ field: 'source', equals: 'manual' }, { source: 'auto' })).toBe(false)
  })

  it('not_empty 双向', () => {
    expect(evalCondition({ field: 'secret_ref', not_empty: true }, { secret_ref: 'x' })).toBe(true)
    expect(evalCondition({ field: 'secret_ref', not_empty: true }, { secret_ref: '' })).toBe(false)
    expect(evalCondition({ field: 'secret_ref', not_empty: false }, {})).toBe(true)
  })

  it('未知形式降级为可见', () => {
    expect(evalCondition({ field: 'status', and: [] }, {})).toBe(true)
    expect(evalCondition(null, {})).toBe(true)
  })
})

describe('isVisible / isActionVisible（roles）', () => {
  it('未注入角色上下文时放行', () => {
    expect(isVisible({ roles: ['admin'] }, {})).toBe(true)
  })

  it('注入后按角色过滤', () => {
    setCurrentRoles(['viewer'])
    expect(isVisible({ roles: ['admin'] }, {})).toBe(false)
    expect(isVisible({ roles: ['admin', 'viewer'] }, {})).toBe(true)
    expect(isActionVisible({ roles: ['viewer'] }, {})).toBe(true)
  })

  it('visible_when 为 false 时隐藏', () => {
    expect(isVisible({ visible_when: { field: 'status', equals: 'draft' } }, { status: 'done' }))
      .toBe(false)
  })
})

describe('isFieldReadonly', () => {
  it('后端策略优先', () => {
    expect(isFieldReadonly({ key: 'code' }, {}, { code: { writable: false } })).toBe(true)
  })

  it('readonly_when 条件命中', () => {
    const field = { key: 'source', readonly_when: { field: 'mode', equals: 'auto' } }
    expect(isFieldReadonly(field, { mode: 'auto' }, {})).toBe(true)
    expect(isFieldReadonly(field, { mode: 'manual' }, {})).toBe(false)
  })

  it('roles 不命中降级为只读（不隐藏）', () => {
    setCurrentRoles(['viewer'])
    expect(isFieldReadonly({ key: 'code', roles: ['admin'] }, {}, {})).toBe(true)
  })
})

describe('mergeFieldPolicies', () => {
  it('后端字段策略覆盖本地声明', () => {
    const merged = mergeFieldPolicies(
      { code: { readable: true, writable: false, roles: ['admin'] } },
      { key: 'code', writable: true, roles: ['viewer'] },
    )
    expect(merged.writable).toBe(false)
    expect(merged.roles).toEqual(['admin'])
  })

  it('后端无声明时保留本地声明', () => {
    const merged = mergeFieldPolicies({}, { key: 'code', roles: ['viewer'] })
    expect(merged.writable).toBe(true)
    expect(merged.roles).toEqual(['viewer'])
  })
})
