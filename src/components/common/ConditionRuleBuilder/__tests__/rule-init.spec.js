/**
 * ConditionRuleBuilder initRuleForField 测试
 *
 * [v28 2026-08-26] 验证字段切换时的初始化纯函数
 *   - 覆盖 boolean/datetime/string/integer/fk 5 类字段元数据
 *   - 覆盖 operator 校验切换（合法保留 / 非法切换）
 *   - 覆盖 picker 缓存重置
 *   - 覆盖不可变性 (不修改入参)
 *
 * 运行: npx vitest run src/components/common/ConditionRuleBuilder/__tests__/rule-init.spec.js
 */
import { describe, it, expect } from 'vitest'
import { initRuleForField } from '../rule-init.ts'

/** 构造基础 rule (模拟 createDefaultRule 输出) */
function makeRule(overrides = {}) {
  return {
    type: 'rule',
    id: 'rule-1',
    field: '',
    fieldType: 'string',
    operator: 'IN',
    value: '',
    relationObject: '',
    isBusinessKey: false,
    isEnum: false,
    enumValues: null,
    enumRef: null,
    pickerVisible: false,
    pickerSelectedIds: [],
    pickerSelectedItems: [],
    ...overrides,
  }
}

describe('initRuleForField - 基础字段类型', () => {
  it('string 字段 → operator 保留 IN（合法）', () => {
    const rule = makeRule({ operator: 'IN' })
    const meta = { db_column: 'name', field_type: 'string' }
    const next = initRuleForField(rule, meta)
    expect(next.field).toBe('name')
    expect(next.fieldType).toBe('string')
    expect(next.operator).toBe('IN')  // IN 是 string 合法操作符
    expect(next.value).toBe('')
  })

  it('integer 字段 → operator 从 IN 切换为 = (IN 对整数也合法, 这里验证保留)', () => {
    const rule = makeRule({ operator: 'IN' })
    const meta = { db_column: 'age', field_type: 'integer' }
    const next = initRuleForField(rule, meta)
    expect(next.field).toBe('age')
    expect(next.fieldType).toBe('integer')
    expect(next.operator).toBe('IN')  // integer 的合法操作符含 IN
  })

  // [v28 修复核心场景] 历史 bug: boolean 字段 + 默认 operator=IN
  it('boolean 字段 → operator 从 IN 切换为 = (IN 不合法)', () => {
    const rule = makeRule({ operator: 'IN' })
    const meta = { db_column: 'is_active', field_type: 'boolean' }
    const next = initRuleForField(rule, meta)
    expect(next.field).toBe('is_active')
    expect(next.fieldType).toBe('boolean')
    expect(next.operator).toBe('=')  // 关键修复: IN 不在 boolean 合法集合中, 切换到第一个 = '=
    expect(next.value).toBe('')
  })

  // [v28 修复核心场景] 历史 bug: datetime 字段 + 默认 operator=IN
  it('datetime 字段 → operator 从 IN 切换为 =', () => {
    const rule = makeRule({ operator: 'IN' })
    const meta = { db_column: 'created_at', field_type: 'datetime' }
    const next = initRuleForField(rule, meta)
    expect(next.field).toBe('created_at')
    expect(next.fieldType).toBe('datetime')
    expect(next.operator).toBe('=')
  })

  it('text 字段 → LIKE 合法, 保留 LIKE', () => {
    const rule = makeRule({ operator: 'LIKE' })
    const meta = { db_column: 'description', field_type: 'text' }
    const next = initRuleForField(rule, meta)
    expect(next.operator).toBe('LIKE')  // text 仅支持 LIKE/NOT LIKE
  })

  it('text 字段 → IN 非法, 切换为 LIKE (text 的第一个合法操作符)', () => {
    const rule = makeRule({ operator: 'IN' })
    const meta = { db_column: 'description', field_type: 'text' }
    const next = initRuleForField(rule, meta)
    expect(next.operator).toBe('LIKE')  // IN 不在 text 合法集合, 切到第一个 LIKE
  })
})

describe('initRuleForField - FK / 业务主键 / enum', () => {
  it('FK 字段 → 设置 relationObject + isBusinessKey=false (v57: FK 绝不是业务主键)', () => {
    // [v57 修正] 此前 *_id 后缀启发式把 product_id 等 FK 误判为业务主键，
    //   导致 FK picker 错误回落到资源自身（业务对象树）。
    //   FK 字段必须走 relation picker (target_bo=relation_object)。
    const rule = makeRule()
    const meta = {
      db_column: 'product_id',
      field_type: 'integer',
      is_foreign_key: true,
      relation_object: 'product',
    }
    const next = initRuleForField(rule, meta)
    expect(next.relationObject).toBe('product')
    expect(next.isBusinessKey).toBe(false)  // FK 不触发 self-reference picker
  })

  it('FK 字段 (db_column 无 *_id/*_code 后缀) → isBusinessKey=false', () => {
    const rule = makeRule()
    const meta = {
      db_column: 'tag',
      field_type: 'integer',
      is_foreign_key: true,
      relation_object: 'product',
    }
    const next = initRuleForField(rule, meta)
    expect(next.relationObject).toBe('product')
    expect(next.isBusinessKey).toBe(false)  // 无 *_id/*_code 后缀
  })

  it('业务主键字段 → 设置 isBusinessKey=true, 不带 relation_object', () => {
    const rule = makeRule()
    const meta = {
      db_column: 'id',
      field_type: 'integer',
      is_business_key: true,
    }
    const next = initRuleForField(rule, meta)
    expect(next.isBusinessKey).toBe(true)
    expect(next.relationObject).toBe('')
  })

  it('id 字段 (db_column 命中 *_id/*_code 前缀) → isBusinessKey=true', () => {
    const rule = makeRule()
    const meta = { db_column: 'domain_id', field_type: 'integer' }
    const next = initRuleForField(rule, meta)
    expect(next.isBusinessKey).toBe(true)
  })

  it('固定枚举字段 → 设置 isEnum=true + enumValues', () => {
    const rule = makeRule()
    const meta = {
      db_column: 'status',
      field_type: 'string',
      is_enum: true,
      enum_values: ['active', 'inactive', 'pending'],
    }
    const next = initRuleForField(rule, meta)
    expect(next.isEnum).toBe(true)
    expect(next.enumValues).toEqual(['active', 'inactive', 'pending'])
    expect(next.enumRef).toBe(null)
  })

  it('引用枚举字段 → 设置 isEnum=true + enumRef', () => {
    const rule = makeRule()
    const meta = {
      db_column: 'priority',
      field_type: 'string',
      is_enum: true,
      enum_ref: 'priority_enum',
    }
    const next = initRuleForField(rule, meta)
    expect(next.isEnum).toBe(true)
    expect(next.enumRef).toBe('priority_enum')
    expect(next.enumValues).toBe(null)
  })
})

describe('initRuleForField - value/picker 缓存重置', () => {
  it('value 非空 → 重置为空', () => {
    const rule = makeRule({ value: 'old value' })
    const meta = { db_column: 'name', field_type: 'string' }
    const next = initRuleForField(rule, meta)
    expect(next.value).toBe('')
  })

  it('pickerVisible=true → 重置为 false', () => {
    const rule = makeRule({ pickerVisible: true })
    const meta = { db_column: 'name', field_type: 'string' }
    const next = initRuleForField(rule, meta)
    expect(next.pickerVisible).toBe(false)
  })

  it('pickerSelectedIds 有值 → 重置为空数组', () => {
    const rule = makeRule({ pickerSelectedIds: ['1', '2'], pickerSelectedItems: [{ id: '1', name: 'A' }] })
    const meta = { db_column: 'product_id', field_type: 'integer', is_foreign_key: true, relation_object: 'product' }
    const next = initRuleForField(rule, meta)
    expect(next.pickerSelectedIds).toEqual([])
    expect(next.pickerSelectedItems).toEqual([])
  })
})

describe('initRuleForField - 不可变性', () => {
  it('不修改入参 rule', () => {
    const rule = makeRule({ value: 'old', pickerVisible: true })
    const original = JSON.parse(JSON.stringify(rule))
    const meta = { db_column: 'name', field_type: 'string' }
    initRuleForField(rule, meta)
    expect(rule).toEqual(original)  // rule 未被修改
  })

  it('返回新对象引用', () => {
    const rule = makeRule()
    const meta = { db_column: 'name', field_type: 'string' }
    const next = initRuleForField(rule, meta)
    expect(next).not.toBe(rule)
  })

  it('meta=null 时按 string 兜底', () => {
    const rule = makeRule({ operator: '=' })
    const next = initRuleForField(rule, null)
    expect(next.fieldType).toBe('string')
    expect(next.operator).toBe('=')
    expect(next.isBusinessKey).toBe(false)
    expect(next.relationObject).toBe('')
  })
})