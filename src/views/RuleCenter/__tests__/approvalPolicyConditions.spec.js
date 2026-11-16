import { describe, it, expect } from 'vitest'
import {
  OP_ALIASES,
  normalizeOp,
  conditionsToTree,
  treeToConditions,
  validateSteps,
} from '../approvalPolicyConditions'

const step = (overrides = {}) => ({
  step_no: 1,
  approver_type: 'role',
  approver_ref: 'manager',
  min_amount: null,
  max_amount: null,
  ...overrides,
})

describe('normalizeOp', () => {
  it('符号 → 规范名', () => {
    expect(OP_ALIASES['>=']).toBe('ge')
    expect(normalizeOp('>=')).toBe('ge')
    expect(normalizeOp('=')).toBe('eq')
    expect(normalizeOp('!=')).toBe('ne')
    expect(normalizeOp('<>')).toBe('ne')
    expect(normalizeOp('<=')).toBe('le')
  })

  it('规范名幂等 / 大小写不敏感', () => {
    expect(normalizeOp('ge')).toBe('ge')
    expect(normalizeOp('IN')).toBe('in')
    expect(normalizeOp('NOT_IN')).toBe('not_in')
  })

  it('未知 op 原样返回', () => {
    expect(normalizeOp('xor')).toBe('xor')
    expect(normalizeOp('CUSTOM_OP')).toBe('CUSTOM_OP')
    expect(normalizeOp('')).toBe('')
  })
})

describe('conditionsToTree / treeToConditions', () => {
  it('空条件数组往返为空树 / 空数组', () => {
    const tree = conditionsToTree([])
    expect(tree.type).toBe('group')
    expect(tree.children).toEqual([])
    expect(tree.droppedCount).toBe(0)
    expect(treeToConditions(tree)).toEqual([])
  })

  it('单项往返保持 field_id / operator / value', () => {
    const conditions = [{ field_id: 'gross_amount', operator: 'ge', value: 10000 }]
    const tree = conditionsToTree(conditions)
    expect(tree.children).toHaveLength(1)
    const rule = tree.children[0]
    expect(rule.type).toBe('rule')
    expect(rule.field).toBe('gross_amount')
    expect(rule.operator).toBe('>=')
    expect(rule.fieldType).toBe('number')
    expect(treeToConditions(tree)).toEqual(conditions)
  })

  it('多项往返等价', () => {
    const conditions = [
      { field_id: 'gross_amount', operator: 'ge', value: 1000 },
      { field_id: 'domain_type', operator: 'eq', value: 'CORE' },
      { field_id: 'description', operator: 'like', value: 'urgent' },
    ]
    const tree = conditionsToTree(conditions)
    expect(tree.children).toHaveLength(3)
    expect(treeToConditions(tree)).toEqual(conditions)
  })

  it('输入用符号 operator 时归一为规范名', () => {
    const tree = conditionsToTree([{ field_id: 'gross_amount', operator: '>=', value: 500 }])
    expect(tree.children[0].operator).toBe('>=')
    expect(treeToConditions(tree)).toEqual([
      { field_id: 'gross_amount', operator: 'ge', value: 500 },
    ])
  })

  it('历史别名 op 仍可读取（写入统一为 operator）', () => {
    const tree = conditionsToTree([{ field_id: 'code', op: 'like', value: 'A%' }])
    expect(tree.children[0].operator).toBe('LIKE')
    expect(treeToConditions(tree)).toEqual([
      { field_id: 'code', operator: 'like', value: 'A%' },
    ])
  })

  it('详情行（value_number / value_text / value_json）可回填', () => {
    const tree = conditionsToTree([
      { field_id: 'gross_amount', operator: 'ge', value_number: 1000 },
      { field_id: 'code', operator: 'like', value_text: 'A%' },
      { field_id: 'tags', operator: 'in', value_json: '["a","b"]' },
    ])
    expect(tree.children.map(rule => rule.value)).toEqual([1000, 'A%', ['a', 'b']])
  })

  it('缺 field_id 的项被丢弃并计数', () => {
    const tree = conditionsToTree([
      { operator: 'eq', value: 1 },
      null,
      'not-an-object',
      { field_id: 'code', operator: 'eq', value: 'A' },
    ])
    expect(tree.children).toHaveLength(1)
    expect(tree.children[0].field).toBe('code')
    expect(tree.droppedCount).toBe(3)
  })

  it('未完成行（空字段）不进入保存数组', () => {
    const tree = {
      type: 'group',
      id: 'root',
      connector: 'AND',
      children: [
        { type: 'rule', id: 'r1', field: '', operator: '=', value: '' },
        { type: 'rule', id: 'r2', field: 'code', operator: '=', value: 'A' },
      ],
    }
    expect(treeToConditions(tree)).toEqual([
      { field_id: 'code', operator: 'eq', value: 'A' },
    ])
  })
})

describe('validateSteps', () => {
  it('正常 3 步（金额区间首尾相接）通过', () => {
    const result = validateSteps([
      step({ step_no: 1, min_amount: null, max_amount: 1000 }),
      step({ step_no: 2, min_amount: 1000, max_amount: 5000 }),
      step({ step_no: 3, min_amount: 5000, max_amount: null }),
    ])
    expect(result.ok).toBe(true)
    expect(result.errors).toEqual([])
  })

  it('无序输入按 step_no 升序校验通过', () => {
    const result = validateSteps([
      step({ step_no: 3, approver_ref: 'c' }),
      step({ step_no: 1, approver_ref: 'a' }),
      step({ step_no: 2, approver_ref: 'b' }),
    ])
    expect(result.ok).toBe(true)
  })

  it('步骤序号跳号 → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1 }),
      step({ step_no: 3 }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('步骤序号'))).toBe(true)
  })

  it('步骤序号重复 → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1 }),
      step({ step_no: 1 }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('步骤序号'))).toBe(true)
  })

  it('金额区间重叠 → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1, min_amount: 0, max_amount: 5000 }),
      step({ step_no: 2, min_amount: 1000, max_amount: null }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('金额区间重叠/断档'))).toBe(true)
  })

  it('金额区间断档 → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1, min_amount: 0, max_amount: 1000 }),
      step({ step_no: 2, min_amount: 2000, max_amount: null }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('金额区间重叠/断档'))).toBe(true)
  })

  it('前一步无上界而后一步有下界 → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1, min_amount: 0, max_amount: null }),
      step({ step_no: 2, min_amount: 1000, max_amount: null }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('金额区间重叠/断档'))).toBe(true)
  })

  it('min_amount > max_amount → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1, min_amount: 5000, max_amount: 1000 }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('min_amount'))).toBe(true)
  })

  it('缺 approver_ref → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1, approver_ref: '' }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('approver_ref'))).toBe(true)
  })

  it('缺 approver_type → 失败', () => {
    const result = validateSteps([
      step({ step_no: 1, approver_type: '' }),
    ])
    expect(result.ok).toBe(false)
    expect(result.errors.some(err => err.includes('approver_type'))).toBe(true)
  })

  it('空步骤列表通过（无步骤不校验区间）', () => {
    expect(validateSteps([])).toEqual({ ok: true, errors: [] })
  })
})
