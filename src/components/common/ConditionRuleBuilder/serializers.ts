/**
 * ConditionRuleBuilder 序列化器
 *
 * 把条件树 (GroupNode | RuleNode) 序列化为 Python 表达式字符串
 * 与后端 condition_converter.py 兼容
 *
 * [v26 2026-08-26] 抽取自 ConditionRuleDialog.vue
 *   - 序列化算法: 递归拼接, group 嵌套时自动加括号
 *   - 兼容性: 与 v25 flat 模型输出 100% 一致 (顶层不带括号)
 */

import { isBooleanFieldType, isDateFieldType, isNumberFieldType } from './operators.ts'
import type { ConditionNode, GroupNode, RuleNode } from './types.ts'

/**
 * 序列化条件树为 Python 表达式
 *
 * @example
 * serialize({ type: 'group', connector: 'AND', children: [ruleA, ruleB] })
 *   => "A AND B"
 *
 * @example
 * serialize({
 *   type: 'group', connector: 'OR',
 *   children: [
 *     { type: 'group', connector: 'AND', children: [ruleA, ruleB] },
 *     { type: 'group', connector: 'AND', children: [ruleC, ruleD] }
 *   ]
 * })
 *   => "(A AND B) OR (C AND D)"
 */
export function serialize(tree: ConditionNode): string {
  if (tree.type === 'rule') {
    return serializeRule(tree as RuleNode)
  }
  return serializeGroup(tree as GroupNode, false)
}

/**
 * 序列化 Group 节点
 * @param isNested 是否嵌套（决定是否包裹括号）
 */
function serializeGroup(group: GroupNode, isNested: boolean): string {
  const parts = group.children.map((c) => {
    if (c.type === 'rule') {
      return serializeRule(c as RuleNode)
    }
    return serializeGroup(c as GroupNode, true)
  })

  // connector 拼接（最后一个不带 connector）
  let result = parts[0] ?? ''
  for (let i = 1; i < parts.length; i++) {
    result += ` ${group.connector} ${parts[i]}`
  }

  // 嵌套 group 才包括号（顶层不包）
  return isNested ? `(${result})` : result
}

/**
 * 序列化单条规则 (field OP value)
 *
 * 核心原则（v22-v25 已确立）:
 *   - IN/NOT IN: 多值逗号分隔，包裹括号
 *   - LIKE/NOT LIKE: 自动加 %value% 通配符
 *   - boolean: true/false 字面量（不加引号）
 *   - datetime: 加单引号字符串字面量
 *   - number: 不加引号数字字面量
 *   - 默认: 数字不加引号，字符串加单引号
 */
function serializeRule(rule: RuleNode): string {
  const { field, operator, value, fieldType } = rule
  if (!field || !operator) return ''
  const valueStr = formatValue(value, operator, fieldType)
  // [v55 2026-08-27] 未选值的未完成规则不进入表达式（如新增预填的 "id IN "）。
  //   此前输出 "id IN "（尾随空格），被 parseConditionToRuleRows 视为有损公式，
  //   导致新增空条件打开弹窗时高级模式被误判默认展开。
  if (!valueStr) return ''
  return `${field} ${operator} ${valueStr}`
}

/**
 * 格式化值
 *
 * @param value - 用户输入的值（字符串/数字/布尔/数组）
 * @param operator - 操作符
 * @param fieldType - 字段类型（用于 boolean / datetime / number 特判）
 */
export function formatValue(
  value: any,
  operator: string,
  fieldType: string
): string {
  if (value === '' || value == null) return ''

  // IN / NOT IN: 逗号分隔，包裹括号
  if (['IN', 'NOT IN'].includes(operator)) {
    const values = String(value).split(',').map((v) => v.trim()).filter(Boolean)
    if (values.length === 0) return ''
    return '(' + values.map((v) => (isNaN(Number(v)) ? `'${v}'` : v)).join(', ') + ')'
  }

  // LIKE / NOT LIKE: 自动包裹 %value%
  if (['LIKE', 'NOT LIKE'].includes(operator)) {
    const v = String(value).trim()
    return `'%${v}%'`
  }

  // boolean: 不加引号
  if (isBooleanFieldType(fieldType)) {
    return String(value)
  }

  // datetime: 加单引号字符串字面量
  if (isDateFieldType(fieldType)) {
    return `'${value}'`
  }

  // number: 不加引号
  if (isNumberFieldType(fieldType)) {
    return String(value)
  }

  // 默认: 数字不加引号，其他加引号
  return isNaN(Number(value)) ? `'${value}'` : String(value)
}

// isBooleanFieldType / isDateFieldType / isNumberFieldType 已在 operators.ts 中定义
// 在此 re-export 以保持向后兼容
export { isBooleanFieldType, isDateFieldType, isNumberFieldType } from './operators.ts'

/**
 * [v45 2026-08-27] 展示用序列化器 — 字段用中文 label，值用 picker 已选 name
 *
 * 背景：serialize() 输出的是后端可执行表达式（db_column + 原始 ID），
 * 如 "id IN (16, 17)"。直接拿来做行级按钮预览对用户不友好。
 * serializeDisplay() 用同构算法输出人类可读版本：
 *   - field → labelMap[db_column]（fieldMetadata.name，如「业务对象」）
 *   - 操作符/连接词 → 中文描述（IN→属于 / NOT IN→不属于 / AND→且 / OR→或）
 *   - value → pickerSelectedItems[].name（用户在 picker 里看到的显示名）
 *     兜底回落 formatValue() 原始值（pickerSelectedItems 为空时，如高级模式手写）
 */
// [v46 2026-08-27] 展示用中文操作符映射
const OPERATOR_DISPLAY_MAP: Record<string, string> = {
  'IN': '属于',
  'NOT IN': '不属于',
  'EQ': '等于',
  '=': '等于',
  'NE': '不等于',
  '!=': '不等于',
  'GT': '大于',
  '>': '大于',
  'GE': '大于等于',
  '>=': '大于等于',
  'LT': '小于',
  '<': '小于',
  'LE': '小于等于',
  '<=': '小于等于',
  'LIKE': '包含',
  'NOT LIKE': '不包含',
}

function displayOperator(op: string): string {
  return OPERATOR_DISPLAY_MAP[op] || op
}

function displayConnector(conn: string): string {
  if (String(conn).toUpperCase() === 'OR') return '或'
  return '且'
}

export function serializeDisplay(tree: any, labelMap: Record<string, string> = {}): string {
  if (tree.type === 'rule') {
    return serializeRuleDisplay(tree, labelMap)
  }
  return serializeGroupDisplay(tree, false, labelMap)
}

function serializeGroupDisplay(group: any, isNested: boolean, labelMap: Record<string, string>): string {
  const parts = group.children.map((c: any) => {
    if (c.type === 'rule') return serializeRuleDisplay(c, labelMap)
    return serializeGroupDisplay(c, true, labelMap)
  })
  let result = parts[0] ?? ''
  for (let i = 1; i < parts.length; i++) {
    result += ` ${displayConnector(group.connector)} ${parts[i]}`
  }
  return isNested ? `(${result})` : result
}

function serializeRuleDisplay(rule: any, labelMap: Record<string, string>): string {
  const { field, operator } = rule
  if (!field || !operator) return ''
  const fieldLabel = labelMap[field] || field

  // 值优先取 picker 已选项的显示名
  const names: string[] = (rule.pickerSelectedItems || [])
    .map((i: any) => i.name || String(i.id ?? i.value ?? ''))
    .filter(Boolean)

  let valueStr = ''
  if (names.length > 0 && ['IN', 'NOT IN'].includes(operator)) {
    valueStr = '(' + names.join('、') + ')'
  } else if (names.length === 1 && ['LIKE', 'NOT LIKE'].includes(operator)) {
    valueStr = names[0]
  } else {
    // 兜底：无 picker 缓存（高级模式手写 / number/datetime 手输）→ 用原始格式
    valueStr = formatValue(rule.value, operator, rule.fieldType)
  }
  return `${fieldLabel} ${displayOperator(operator)} ${valueStr}`
}

/**
 * [v47 2026-08-27] 表达式 → Rule Builder 规则行（反向解析）
 *
 * 背景：条件规则持久化在 data_permission_rules.condition（如 "id IN (16, 17)"）。
 * 页面刷新后前端无结构化规则快照（__rules 是内存态），弹窗回填需要从表达式重建。
 *
 * 支持 v1 flat 模型（单层 AND/OR，不解析嵌套括号）：
 *   parseConditionToRuleRows("id IN (16, 17) AND domain_type = 'CORE'")
 *     => [ {field:'id', operator:'IN', value:'16,17', connector:'AND'},
 *          {field:'domain_type', operator:'=', value:'CORE', connector:'AND'} ]
 */
export function parseConditionToRuleRows(expr: string): any[] {
  if (!expr || !expr.trim()) return []
  const parts = expr.split(/\s+(AND|OR)\s+/)
  const rules: any[] = []
  let nextConnector = 'AND'
  for (let i = 0; i < parts.length; i += 2) {
    const chunk = String(parts[i] || '').trim().replace(/^[(]+/, '').replace(/[)]+$/, '').trim()
    const m = chunk.match(/^([\w.]+)\s*(IN|NOT IN|LIKE|NOT LIKE|>=|<=|!=|=|>|<)\s*([\s\S]+)$/)
    if (m) {
      const field = m[1]
      const operator = m[2].toUpperCase()
      const rawVal = m[3].trim()
      let value = ''
      if (operator === 'IN' || operator === 'NOT IN') {
        value = rawVal.replace(/^\(+|\)+$/g, '')
          .split(',')
          .map((s) => s.trim().replace(/^'|'$/g, ''))
          .filter(Boolean)
          .join(', ')
      } else if (operator === 'LIKE' || operator === 'NOT LIKE') {
        value = rawVal.replace(/^'%?/, '').replace(/%?'$/, '')
      } else {
        value = rawVal.replace(/^'/, '').replace(/'$/, '')
      }
      rules.push({ type: 'rule', connector: i === 0 ? 'AND' : nextConnector, field, operator, value })
    }
    if (parts[i + 1]) nextConnector = String(parts[i + 1]).toUpperCase()
  }
  return rules
}

