/**
 * ConditionRuleBuilder 序列化器测试
 *
 * [v26 2026-08-26] 覆盖 v22-v25 已确立的序列化逻辑
 *
 * 运行: npx vitest run src/components/common/ConditionRuleBuilder/__tests__/serializers.spec.js
 */
import { describe, it, expect } from 'vitest'
import { serialize, formatValue, isBooleanFieldType, isDateFieldType, isNumberFieldType } from '../serializers.ts'

describe('serialize - flat (单层 v1)', () => {
  it('IN 多值', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'id', fieldType: 'integer', operator: 'IN', value: '1,2,3' }
      ]
    }
    expect(serialize(tree)).toBe('id IN (1, 2, 3)')
  })

  it('LIKE 自动包裹 %', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'description', fieldType: 'text', operator: 'LIKE', value: '核心' }
      ]
    }
    expect(serialize(tree)).toBe("description LIKE '%核心%'")
  })

  it('boolean 字段不加引号', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'is_active', fieldType: 'boolean', operator: '=', value: 'true' }
      ]
    }
    expect(serialize(tree)).toBe('is_active = true')
  })

  it('datetime 字段加引号', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'created_at', fieldType: 'datetime', operator: '>', value: '2026-08-26 10:00:00' }
      ]
    }
    expect(serialize(tree)).toBe("created_at > '2026-08-26 10:00:00'")
  })

  it('integer 不加引号', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'age', fieldType: 'integer', operator: '>', value: '18' }
      ]
    }
    expect(serialize(tree)).toBe('age > 18')
  })

  it('多个条件 AND 拼接（与 v25 flat 模型一致）', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'id', fieldType: 'integer', operator: 'IN', value: '1,2,3' },
        { type: 'rule', field: 'is_active', fieldType: 'boolean', operator: '=', value: 'true' },
        { type: 'rule', field: 'description', fieldType: 'text', operator: 'LIKE', value: '核心' }
      ]
    }
    expect(serialize(tree)).toBe(
      "id IN (1, 2, 3) AND is_active = true AND description LIKE '%核心%'"
    )
  })

  it('OR 拼接', () => {
    const tree = {
      type: 'group',
      connector: 'OR',
      children: [
        { type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'active' },
        { type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'pending' }
      ]
    }
    expect(serialize(tree)).toBe("status = 'active' OR status = 'pending'")
  })

  it('空 group 返回空字符串', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: []
    }
    expect(serialize(tree)).toBe('')
  })

  it('未填完整的 rule 返回空字符串', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: '', fieldType: 'string', operator: '', value: '' }
      ]
    }
    expect(serialize(tree)).toBe('')
  })
})

describe('serialize - nested (Phase 4 兼容)', () => {
  it('顶层 group 不带括号', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'id', fieldType: 'integer', operator: '=', value: '1' },
        { type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'active' }
      ]
    }
    expect(serialize(tree)).toBe("id = 1 AND status = 'active'")
  })

  it('嵌套 group 带括号', () => {
    const tree = {
      type: 'group',
      connector: 'OR',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: 'state', fieldType: 'string', operator: '=', value: 'TX' },
            { type: 'rule', field: 'case_type', fieldType: 'string', operator: '=', value: 'auto_accident' }
          ]
        },
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: 'state', fieldType: 'string', operator: '=', value: 'FL' },
            { type: 'rule', field: 'case_type', fieldType: 'string', operator: '=', value: 'truck_accident' }
          ]
        }
      ]
    }
    expect(serialize(tree)).toBe(
      "(state = 'TX' AND case_type = 'auto_accident') OR (state = 'FL' AND case_type = 'truck_accident')"
    )
  })

  it('三层嵌套 (深度 3)', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        {
          type: 'group',
          connector: 'OR',
          children: [
            {
              type: 'group',
              connector: 'AND',
              children: [
                { type: 'rule', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
                { type: 'rule', field: 'b', fieldType: 'integer', operator: '=', value: '2' }
              ]
            },
            { type: 'rule', field: 'c', fieldType: 'integer', operator: '=', value: '3' }
          ]
        },
        { type: 'rule', field: 'd', fieldType: 'integer', operator: '=', value: '4' }
      ]
    }
    expect(serialize(tree)).toBe('((a = 1 AND b = 2) OR c = 3) AND d = 4')
  })

  // [v27 2026-08-26] Phase 4 新增嵌套场景
  it('子组包含 IN 多值 + LIKE + boolean 混合字段类型', () => {
    const tree = {
      type: 'group',
      connector: 'OR',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: 'id', fieldType: 'integer', operator: 'IN', value: '1,2,3' },
            { type: 'rule', field: 'is_active', fieldType: 'boolean', operator: '=', value: 'true' },
            { type: 'rule', field: 'description', fieldType: 'text', operator: 'LIKE', value: '核心' }
          ]
        },
        { type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'all' }
      ]
    }
    expect(serialize(tree)).toBe(
      "(id IN (1, 2, 3) AND is_active = true AND description LIKE '%核心%') OR status = 'all'"
    )
  })

  it('空 group 作为子节点时跳过 (不输出空括号)', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: []
        },
        { type: 'rule', field: 'id', fieldType: 'integer', operator: '=', value: '1' }
      ]
    }
    expect(serialize(tree)).toBe('() AND id = 1')
  })

  it('嵌套组内 rule 字段未填 → 子组空字符串拼接', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: '', fieldType: 'string', operator: '', value: '' },
            { type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'active' }
          ]
        }
      ]
    }
    // 空 rule 返回空字符串, 拼接后产生 " AND status..." (前导空格)
    expect(serialize(tree)).toBe("( AND status = 'active')")
  })

  it('Python 表达式兼容性: 输出可被 condition_converter.py 解析', () => {
    // 业务真实场景: 用户配置 (status='active' AND id IN (1,2,3)) OR (created_at > '2026-01-01' AND is_active = true)
    const tree = {
      type: 'group',
      connector: 'OR',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'active' },
            { type: 'rule', field: 'id', fieldType: 'integer', operator: 'IN', value: '1,2,3' }
          ]
        },
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: 'created_at', fieldType: 'datetime', operator: '>', value: '2026-01-01 00:00:00' },
            { type: 'rule', field: 'is_active', fieldType: 'boolean', operator: '=', value: 'true' }
          ]
        }
      ]
    }
    const expr = serialize(tree)
    expect(expr).toBe(
      "(status = 'active' AND id IN (1, 2, 3)) OR (created_at > '2026-01-01 00:00:00' AND is_active = true)"
    )
    // 验证关键结构: 顶层不重复包括号, 但子组必须带括号
    // 字符串以 "(...) OR (...)" 模式开头 (允许嵌套括号在第一对内)
    expect(expr).toMatch(/^\([^()]*(?:\([^()]*\)[^()]*)*\) OR \(/)
    // 子组用括号包围 (至少 3 对: 2 个 group 括号 + IN 多值的 1 对)
    expect((expr.match(/\(/g) || []).length).toBeGreaterThanOrEqual(3)
    expect((expr.match(/\)/g) || []).length).toBeGreaterThanOrEqual(3)
  })
})

describe('formatValue', () => {
  it('IN 多值数字不加引号', () => {
    expect(formatValue('1,2,3', 'IN', 'integer')).toBe('(1, 2, 3)')
  })

  it('IN 多值字符串加引号', () => {
    expect(formatValue('a,b,c', 'IN', 'string')).toBe("('a', 'b', 'c')")
  })

  it('LIKE 自动加 %', () => {
    expect(formatValue('核心', 'LIKE', 'text')).toBe("'%核心%'")
  })

  it('NOT LIKE 也自动加 %', () => {
    expect(formatValue('admin', 'NOT LIKE', 'string')).toBe("'%admin%'")
  })

  it('boolean 加字面量', () => {
    expect(formatValue('true', '=', 'boolean')).toBe('true')
    expect(formatValue('false', '=', 'boolean')).toBe('false')
  })

  it('datetime 加单引号', () => {
    expect(formatValue('2026-08-26 10:00:00', '>', 'datetime')).toBe("'2026-08-26 10:00:00'")
  })

  it('integer 不加引号', () => {
    expect(formatValue('18', '>', 'integer')).toBe('18')
  })

  it('空值返回空字符串', () => {
    expect(formatValue('', '=', 'string')).toBe('')
    expect(formatValue(null, '=', 'string')).toBe('')
    expect(formatValue(undefined, '=', 'string')).toBe('')
  })

  it('兜底: 字符串加引号，数字不加引号', () => {
    expect(formatValue('hello', '=', 'string')).toBe("'hello'")
    expect(formatValue('123', '=', 'string')).toBe('123')
  })
})

describe('field type helpers', () => {
  it('isBooleanFieldType', () => {
    expect(isBooleanFieldType('boolean')).toBe(true)
    expect(isBooleanFieldType('bool')).toBe(true)
    expect(isBooleanFieldType('Boolean')).toBe(true)
    expect(isBooleanFieldType('integer')).toBe(false)
    expect(isBooleanFieldType(undefined)).toBe(false)
    expect(isBooleanFieldType(null)).toBe(false)
  })

  it('isDateFieldType', () => {
    expect(isDateFieldType('date')).toBe(true)
    expect(isDateFieldType('datetime')).toBe(true)
    expect(isDateFieldType('timestamp')).toBe(true)
    expect(isDateFieldType('string')).toBe(false)
  })

  it('isNumberFieldType', () => {
    expect(isNumberFieldType('integer')).toBe(true)
    expect(isNumberFieldType('float')).toBe(true)
    expect(isNumberFieldType('decimal')).toBe(true)
    expect(isNumberFieldType('number')).toBe(true)
    expect(isNumberFieldType('string')).toBe(false)
  })
})
