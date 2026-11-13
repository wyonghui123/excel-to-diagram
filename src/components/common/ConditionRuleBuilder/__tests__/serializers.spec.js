/**
 * ConditionRuleBuilder 序列化器测试
 *
 * [v26 2026-08-26] 覆盖 v22-v25 已确立的序列化逻辑
 *
 * 运行: npx vitest run src/components/common/ConditionRuleBuilder/__tests__/serializers.spec.js
 */
import { describe, it, expect } from 'vitest'
import { serialize, serializeDisplay, formatValue, isBooleanFieldType, isDateFieldType, isNumberFieldType } from '../serializers.ts'

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

// [FIX 2026-09-12] 行级连接符模型: v27 UI 中行连接符存在每个 rule.connector
//   (顶层组无组级连接符控件, root.connector 恒为 'AND' 且从不被 UI 更新)。
//   旧实现统一用 group.connector 拼接 → 用户行首选「或」公式仍输出 AND。
describe('serialize - 行级 connector (rule.connector 驱动)', () => {
  it('root.connector=AND 恒定, 行 rule.connector=OR → 输出 OR (用户报障场景)', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'id', fieldType: 'integer', operator: 'IN', value: '61' },
        { type: 'rule', connector: 'OR', field: 'domain_id', fieldType: 'integer', operator: 'IN', value: '111' }
      ]
    }
    expect(serialize(tree)).toBe('id IN (61) OR domain_id IN (111)')
  })

  it('混合连接符平铺输出 (求值依赖标准优先级 AND > OR)', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
        { type: 'rule', connector: 'OR', field: 'b', fieldType: 'integer', operator: '=', value: '2' },
        { type: 'rule', connector: 'AND', field: 'c', fieldType: 'integer', operator: '=', value: '3' }
      ]
    }
    expect(serialize(tree)).toBe('a = 1 OR b = 2 AND c = 3')
  })

  it('子组 connector 驱动: 顶层 AND + 子组 OR → 子组间输出 OR', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'id', fieldType: 'integer', operator: '=', value: '1' },
        {
          type: 'group', connector: 'OR',
          children: [{ type: 'rule', field: 'status', fieldType: 'string', operator: '=', value: 'active' }]
        }
      ]
    }
    expect(serialize(tree)).toBe("id = 1 OR (status = 'active')")
  })

  it('child.connector 缺失时回落 group.connector (v26 旧树兼容)', () => {
    const tree = {
      type: 'group',
      connector: 'OR',
      children: [
        { type: 'rule', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
        { type: 'rule', field: 'b', fieldType: 'integer', operator: '=', value: '2' }
      ]
    }
    expect(serialize(tree)).toBe('a = 1 OR b = 2')
  })

  it('serializeDisplay 行级 OR → 中文「或」', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'id', operator: 'IN', value: '61' },
        { type: 'rule', connector: 'OR', field: 'domain_id', operator: 'IN', value: '111' }
      ]
    }
    expect(serializeDisplay(tree)).toBe('id 属于 (61) 或 domain_id 属于 (111)')
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
    // [FIX 2026-09-12] 树模型对齐 v27 UI: child.connector = 与前一兄弟的连接符
    //   (子组由 tag-row 且/或控制, 组内行由行首 segmented 控制)
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: 'state', fieldType: 'string', operator: '=', value: 'TX' },
            { type: 'rule', connector: 'AND', field: 'case_type', fieldType: 'string', operator: '=', value: 'auto_accident' }
          ]
        },
        {
          type: 'group', connector: 'OR',
          children: [
            { type: 'rule', field: 'state', fieldType: 'string', operator: '=', value: 'FL' },
            { type: 'rule', connector: 'AND', field: 'case_type', fieldType: 'string', operator: '=', value: 'truck_accident' }
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
          connector: 'AND',
          children: [
            {
              type: 'group',
              connector: 'AND',
              children: [
                { type: 'rule', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
                { type: 'rule', connector: 'AND', field: 'b', fieldType: 'integer', operator: '=', value: '2' }
              ]
            },
            { type: 'rule', connector: 'OR', field: 'c', fieldType: 'integer', operator: '=', value: '3' }
          ]
        },
        { type: 'rule', connector: 'AND', field: 'd', fieldType: 'integer', operator: '=', value: '4' }
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
    // [FIX 2026-09-12] 空 part 连同 connector 跳过 — 旧实现输出 "() AND id = 1" 脏公式
    expect(serialize(tree)).toBe('id = 1')
  })

  it('嵌套组内 rule 字段未填 → 空行跳过 (不产生前导连接符)', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        {
          type: 'group',
          connector: 'AND',
          children: [
            { type: 'rule', field: '', fieldType: 'string', operator: '', value: '' },
            { type: 'rule', connector: 'AND', field: 'status', fieldType: 'string', operator: '=', value: 'active' }
          ]
        }
      ]
    }
    // [FIX 2026-09-12] 旧实现输出 "( AND status = 'active')" 前导连接符脏公式
    expect(serialize(tree)).toBe("(status = 'active')")
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
          // [FIX 2026-09-12] child.connector = 与前一兄弟的连接符 (v27 UI 语义)
          type: 'group', connector: 'OR',
          children: [
            { type: 'rule', field: 'created_at', fieldType: 'datetime', operator: '>', value: '2026-01-01 00:00:00' },
            { type: 'rule', connector: 'AND', field: 'is_active', fieldType: 'boolean', operator: '=', value: 'true' }
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

// [2026-11-13 spec-rule-model §12.6.1 方案 C] NOT 归一化: 非组内唯一原子规则
//   按映射表在运算符级取反, 输出永不出现 `NOT (`（后端只吃扁平 AND 文本）
describe('serialize - NOT 归一化 (非组 · 方案 C)', () => {
  const negateGroup = (rule, extra = {}) => ({
    type: 'group',
    id: 'grp-negate',
    connector: 'AND',
    negate: true,
    children: [rule],
    ...extra
  })

  const wrap = (child, connector = 'AND') => ({
    type: 'group',
    connector: 'AND',
    children: [{ ...child, connector }]
  })

  it('= → !=', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'status', fieldType: 'string', operator: '=', value: 'active' }))
    expect(serialize(tree)).toBe("status != 'active'")
  })

  it('!= → =', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'status', fieldType: 'string', operator: '!=', value: 'active' }))
    expect(serialize(tree)).toBe("status = 'active'")
  })

  it('IN → NOT IN', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'id', fieldType: 'integer', operator: 'IN', value: '1,2,3' }))
    expect(serialize(tree)).toBe('id NOT IN (1, 2, 3)')
  })

  it('NOT IN → IN', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'id', fieldType: 'integer', operator: 'NOT IN', value: '1,2' }))
    expect(serialize(tree)).toBe('id IN (1, 2)')
  })

  it('LIKE → NOT LIKE (保留 % 通配)', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'description', fieldType: 'text', operator: 'LIKE', value: '核心' }))
    expect(serialize(tree)).toBe("description NOT LIKE '%核心%'")
  })

  it('NOT LIKE → LIKE', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'description', fieldType: 'text', operator: 'NOT LIKE', value: '测试' }))
    expect(serialize(tree)).toBe("description LIKE '%测试%'")
  })

  it('比较运算符对称取反: > ↔ <=, >= ↔ <, < ↔ >=, <= ↔ >', () => {
    const cases = [
      ['>', '<=', '18'],
      ['>=', '<', '18'],
      ['<', '>=', '18'],
      ['<=', '>', '18'],
    ]
    cases.forEach(([src, dst, val]) => {
      const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'age', fieldType: 'integer', operator: src, value: val }))
      expect(serialize(tree)).toBe(`age ${dst} ${val}`)
    })
  })

  it('与小写等价的运算符大小写不敏感 (in → NOT IN)', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'id', fieldType: 'integer', operator: 'in', value: '9' }))
    expect(serialize(tree)).toBe('id NOT IN (9)')
  })

  it('未映射运算符无法安全取反 → 整段跳过 (不产出 NOT ( 脏公式)', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'name', fieldType: 'string', operator: 'BETWEEN', value: '1,2' }))
    const expr = serialize(tree)
    expect(expr).toBe('')
    expect(expr).not.toContain('NOT (')
  })

  it('未映射运算符跳过时, 兄弟规则仍正常输出且不带 NOT (', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
        { ...negateGroup({ type: 'rule', id: 'r1', field: 'name', fieldType: 'string', operator: 'BETWEEN', value: '1,2' }), connector: 'AND' },
        { type: 'rule', connector: 'AND', field: 'c', fieldType: 'integer', operator: '=', value: '3' }
      ]
    }
    const expr = serialize(tree)
    expect(expr).toBe('a = 1 AND c = 3')
    expect(expr).not.toContain('NOT (')
  })

  it('negate 组只允许单条 rule: 多子节点时不做取反, 按普通组输出括号', () => {
    // UI 已禁用该形状, 此处验证序列化侧防御: 不误吞子节点、不产生 NOT (
    const tree = wrap({
      type: 'group',
      id: 'grp-bad',
      connector: 'AND',
      negate: true,
      children: [
        { type: 'rule', id: 'r1', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
        { type: 'rule', connector: 'AND', id: 'r2', field: 'b', fieldType: 'integer', operator: '=', value: '2' }
      ]
    })
    const expr = serialize(tree)
    expect(expr).toBe('(a = 1 AND b = 2)')
    expect(expr).not.toContain('NOT (')
  })

  it('非组与兄弟规则的连接符沿用 child.connector', () => {
    const tree = {
      type: 'group',
      connector: 'AND',
      children: [
        { type: 'rule', field: 'a', fieldType: 'integer', operator: '=', value: '1' },
        { ...negateGroup({ type: 'rule', id: 'r1', field: 'status', fieldType: 'string', operator: '=', value: 'active' }), connector: 'OR' }
      ]
    }
    expect(serialize(tree)).toBe("a = 1 OR status != 'active'")
  })

  it('serializeDisplay 非组同构取反 (中文「不等于 / 不属于」)', () => {
    const tree = wrap(negateGroup({ type: 'rule', id: 'r1', field: 'status', operator: '=', value: 'active' }))
    expect(serializeDisplay(tree, { status: '状态' })).toBe("状态 不等于 'active'")

    const treeIn = wrap(negateGroup({ type: 'rule', id: 'r2', field: 'id', operator: 'IN', value: '1,2' }))
    expect(serializeDisplay(treeIn, { id: '业务对象' })).toBe('业务对象 不属于 (1, 2)')
  })

  it('普通组 negate 缺失/false 时行为不变 (零回归)', () => {
    const tree = wrap({ type: 'group', id: 'g1', connector: 'OR', children: [{ type: 'rule', id: 'r1', field: 'a', fieldType: 'integer', operator: '=', value: '1' }] })
    expect(serialize(tree)).toBe('(a = 1)')
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
