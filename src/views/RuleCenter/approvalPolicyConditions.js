/**
 * 审批策略条件：ConditionRuleBuilder 树 ↔ 后端 conditions JSON 互转 + 步骤本地校验
 *
 * 落库形态：[{ field_id, operator, value }]（后端 approval_policy_admin_service._condition_row
 * 只读 `operator`，写成 `op` 会被静默回落为 `=`；`value` 由后端拆到 value_text/value_number/value_json）。
 * 读取历史/详情行时兼容 `op` 别名与 value_text/value_number/value_json 三列。
 * 构建器树中 operator 用符号（=、>=、IN ...），与 ConditionRuleBuilder 下拉一致；
 * treeToConditions 统一归一为规范名。
 */

/** 运算符别名（含符号/规范名）→ 规范名 */
export const OP_ALIASES = {
  '=': 'eq',
  '==': 'eq',
  eq: 'eq',
  '!=': 'ne',
  '<>': 'ne',
  ne: 'ne',
  '>': 'gt',
  gt: 'gt',
  '>=': 'ge',
  ge: 'ge',
  '<': 'lt',
  lt: 'lt',
  '<=': 'le',
  le: 'le',
  in: 'in',
  not_in: 'not_in',
  'not in': 'not_in',
  between: 'between',
  is_null: 'is_null',
  'is null': 'is_null',
  is_not_null: 'is_not_null',
  'is not null': 'is_not_null',
  like: 'like',
}

/** 规范名 → 构建器下拉符号 */
const OP_SYMBOLS = {
  eq: '=',
  ne: '!=',
  gt: '>',
  ge: '>=',
  lt: '<',
  le: '<=',
  in: 'IN',
  not_in: 'NOT IN',
  between: 'BETWEEN',
  is_null: 'IS NULL',
  is_not_null: 'IS NOT NULL',
  like: 'LIKE',
}

/** 符号/别名 → 规范名；无法识别时原样返回 */
export function normalizeOp(op) {
  const text = String(op ?? '').trim()
  if (!text) return ''
  return OP_ALIASES[text.toLowerCase()] ?? text
}

function opToSymbol(op) {
  const canonical = normalizeOp(op)
  return OP_SYMBOLS[canonical] || canonical
}

/** 缺字段元数据时按运算符推断类型，保证算子下拉能回显 */
function inferFieldType(canonicalOp) {
  if (['gt', 'ge', 'lt', 'le', 'between'].includes(canonicalOp)) return 'number'
  if (canonicalOp === 'like') return 'text'
  return 'string'
}

function isBlank(value) {
  return value === null || value === undefined || String(value).trim() === ''
}

function findFieldMeta(field, fieldMetadata) {
  const key = String(field ?? '').trim()
  if (!key) return null
  return (fieldMetadata || []).find(
    meta => String(meta?.db_column ?? '') === key
      || String(meta?.id ?? '') === key
      || String(meta?.name ?? '') === key
  ) || null
}

/** 详情/落库行的值：兼容 value / value_number / value_text / value_json 四种来源 */
function readConditionValue(item) {
  if (!item) return ''
  if (item.value !== undefined && item.value !== null && item.value !== '') return item.value
  if (item.value_number !== undefined && item.value_number !== null) return item.value_number
  if (item.value_text !== undefined && item.value_text !== null) return item.value_text
  if (item.value_json !== undefined && item.value_json !== null) {
    const raw = item.value_json
    if (typeof raw !== 'string') return raw
    try {
      return JSON.parse(raw)
    } catch {
      return raw
    }
  }
  return ''
}

function buildRuleNode(item, index, fieldMetadata) {
  const field = String(item.field_id ?? item.field ?? '').trim()
  if (!field) return null
  // `operator` 是落库/详情字段；`op` 仅为历史别名
  const canonicalOp = normalizeOp(item.operator ?? item.op ?? 'eq')
  if (!canonicalOp) return null
  const meta = findFieldMeta(field, fieldMetadata)
  return {
    type: 'rule',
    id: `rule-${index + 1}`,
    connector: 'AND',
    field,
    fieldType: meta?.field_type || inferFieldType(canonicalOp),
    operator: opToSymbol(canonicalOp),
    value: readConditionValue(item),
    relationObject: meta?.is_foreign_key ? (meta.relation_object || '') : '',
    isBusinessKey: !!meta?.is_business_key,
    isEnum: !!meta?.is_enum,
    enumValues: meta?.enum_values || null,
    enumRef: meta?.enum_ref || null,
    allowedOperators: meta?.allowed_operators,
  }
}

/**
 * 落库条件数组 → 构建器树（单层 AND 组）
 *
 * 无法识别的项（非对象 / 缺 field_id）丢弃，并在根节点 droppedCount 上计数。
 * @param {Array} conditions 落库条件 [{ field_id, op, value }]
 * @param {Array} fieldMetadata 字段元数据（可选，用于 fieldType / picker）
 */
export function conditionsToTree(conditions, fieldMetadata = []) {
  const children = []
  let droppedCount = 0
  ;(Array.isArray(conditions) ? conditions : []).forEach((item) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      droppedCount += 1
      return
    }
    const node = buildRuleNode(item, children.length, fieldMetadata)
    if (!node) {
      droppedCount += 1
      return
    }
    children.push(node)
  })
  return { type: 'group', id: 'root', connector: 'AND', children, droppedCount }
}

/**
 * 构建器树 → 落库条件数组（递归展开所有叶子，op 归一为规范名）
 * 空字段 / 空运算符的未完成行会被跳过。
 */
export function treeToConditions(tree) {
  const result = []
  const walk = (node) => {
    if (!node) return
    if (node.type === 'rule') {
      const field = String(node.field ?? '').trim()
      const canonicalOp = normalizeOp(node.operator)
      if (!field || !canonicalOp) return
      result.push({ field_id: field, operator: canonicalOp, value: node.value ?? '' })
      return
    }
    ;(node.children || []).forEach(walk)
  }
  walk(tree)
  return result
}

/**
 * 步骤本地校验（与后端必填规则一致，不新增后端规则）
 *
 * 四类规则：
 *  1. step_no 去重排序后必须连续 1..n
 *  2. 单步 min_amount > max_amount
 *  3. 相邻两步金额区间重叠/断档（空金额 = 无界）
 *  4. approver_type / approver_ref 必填
 *
 * @param {Array} steps 表单步骤行
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateSteps(steps) {
  const list = Array.isArray(steps) ? steps : []
  const errors = []
  const rows = list.map((step, index) => ({
    step_no: Number(step?.step_no ?? index + 1),
    min_amount: step?.min_amount,
    max_amount: step?.max_amount,
    approver_type: step?.approver_type,
    approver_ref: step?.approver_ref,
  }))

  // 1. 步骤序号：排序后逐个比对 1..n（跳号 / 重复都会不一致）
  const sortedNos = rows.map(row => row.step_no).sort((a, b) => a - b)
  const continuous = sortedNos.every((no, index) => no === index + 1)
  if (!continuous) {
    errors.push(`步骤序号必须是连续的 1..${rows.length}（当前：${sortedNos.join(', ')}）`)
  }

  // 2. 单步金额区间 + 4. 审批人必填
  rows.forEach((row) => {
    if (!isBlank(row.min_amount) && !isBlank(row.max_amount)
      && Number(row.min_amount) > Number(row.max_amount)) {
      errors.push(`第 ${row.step_no} 步 min_amount 不能大于 max_amount`)
    }
    if (isBlank(row.approver_type)) {
      errors.push(`第 ${row.step_no} 步 approver_type 不能为空`)
    }
    if (isBlank(row.approver_ref)) {
      errors.push(`第 ${row.step_no} 步 approver_ref 不能为空`)
    }
  })

  // 3. 相邻步骤金额区间：空 = 无界
  //    - 仅一侧有界 → 区间无法首尾相接（重叠/断档）
  //    - 两侧都有界 → 前一步 max 必须恰好等于下一步 min，否则重叠或断档
  const ordered = [...rows].sort((a, b) => a.step_no - b.step_no)
  for (let i = 0; i < ordered.length - 1; i += 1) {
    const prev = ordered[i]
    const next = ordered[i + 1]
    const prevMaxBlank = isBlank(prev.max_amount)
    const nextMinBlank = isBlank(next.min_amount)
    // 两步都没配金额分级（同为无界）→ 不做区间校验
    if (prevMaxBlank && nextMinBlank) continue
    let bad = false
    if (prevMaxBlank || nextMinBlank) {
      bad = true
    } else {
      const prevMax = Number(prev.max_amount)
      const nextMin = Number(next.min_amount)
      if (prevMax !== nextMin) bad = true
    }
    if (bad) {
      errors.push(
        `步骤 ${prev.step_no} 与步骤 ${next.step_no} 金额区间重叠/断档（空金额视为无界）`
      )
    }
  }

  return { ok: errors.length === 0, errors }
}
