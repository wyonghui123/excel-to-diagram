/**
 * ConditionRuleBuilder 操作符 + 字段类型 helpers
 *
 * [v26 2026-08-26] 抽取自 ConditionRuleDialog.vue (v24/v25)
 *
 * 行业对照（v24 深度研究）:
 *   - Salesforce Filter: "Operators are not interchangeable across field types"
 *   - AWS IAM Condition: 严格按 field type 限定
 *   - Tableau Filter: 每种数据类型对应不同 filter card
 *
 * Field × Operator 矩阵:
 *   - integer/float/decimal:  =, ≠, >, <, ≥, ≤, 在列表中, 不在列表中
 *   - datetime/date/timestamp: =, ≠, 晚于, 早于, 不早于, 不晚于  (无 IN — 时间多值无业务语义)
 *   - boolean:                  =, ≠  (Salesforce/Tableau 标准)
 *   - text (长文本):            包含, 不包含  (LIKE / NOT LIKE)
 *   - string (短文本) / enum:   包含, 等于, 不等于, 在列表中, 不在列表中
 */

export interface OperatorOption {
  value: string
  label: string
}

/**
 * 字段元数据 — 与后端 FieldMetadata 字段对齐
 */
export interface FieldMeta {
  db_column?: string
  field_type?: string
  is_business_key?: boolean
  is_enum?: boolean
  enum_values?: string[] | null
  enum_ref?: string | null
  is_foreign_key?: boolean
  relation_object?: string
}

/**
 * 按字段类型返回合法操作符下拉项
 */
export function getOperatorOptions(fieldType) {
  const ft = (fieldType || 'string').toLowerCase()

  // 1. 数值类型
  if (['integer', 'number', 'decimal', 'float'].includes(ft)) {
    return [
      { value: '=', label: '=' },
      { value: '!=', label: '≠' },
      { value: '>', label: '>' },
      { value: '<', label: '<' },
      { value: '>=', label: '≥' },
      { value: '<=', label: '≤' },
      { value: 'IN', label: '在列表中' },
      { value: 'NOT IN', label: '不在列表中' },
    ]
  }

  // 2. 时间类型 — 严格排除 IN
  if (['date', 'datetime', 'timestamp'].includes(ft)) {
    return [
      { value: '=', label: '=' },
      { value: '!=', label: '≠' },
      { value: '>', label: '晚于' },
      { value: '<', label: '早于' },
      { value: '>=', label: '不早于' },
      { value: '<=', label: '不晚于' },
    ]
  }

  // 3. 布尔类型
  if (['boolean', 'bool'].includes(ft)) {
    return [
      { value: '=', label: '=' },
      { value: '!=', label: '≠' },
    ]
  }

  // 4. 长文本 (text) — 只支持 LIKE / NOT LIKE
  if (ft === 'text') {
    return [
      { value: 'LIKE', label: '包含' },
      { value: 'NOT LIKE', label: '不包含' },
    ]
  }

  // 5. 默认 string / enum
  return [
    { value: '=', label: '等于' },
    { value: '!=', label: '不等于' },
    { value: 'LIKE', label: '包含（模糊匹配）' },
    { value: 'IN', label: '在列表中（多值）' },
    { value: 'NOT IN', label: '不在列表中（多值）' },
  ]
}

/**
 * 业务主键字段判断（v18）
 *
 * - backend is_business_key=true → 是
 * - FK 字段（is_foreign_key + relation_object）→ 永远不是（v57）
 * - db_column 是 id / code / *_id / *_code → 视为业务主键候选（仅非 FK 兜底）
 */
export function isBusinessKeyField(fieldMeta) {
  if (!fieldMeta) return false
  if (fieldMeta.is_business_key) return true
  // [v57 2026-08-27] FK 字段绝不是业务主键 —— 必须走 relation picker。
  //   此前后缀启发式 (*_id / *_code) 把 service_module_id / version_id 等
  //   外键误判为业务主键，picker 错误回落到资源自身（业务对象树）。
  if (fieldMeta.is_foreign_key && fieldMeta.relation_object) return false
  const col = (fieldMeta.db_column || '').toLowerCase()
  return col === 'id' || col.endsWith('_id') || col.endsWith('_code')
}

/**
 * 字段类型 helper — 与 TableHeaderFilter / ConditionRuleDialog 同步
 */
export function isBooleanFieldType(ft) {
  return ['boolean', 'bool'].includes((ft || '').toLowerCase())
}

export function isDateFieldType(ft) {
  return ['date', 'datetime', 'timestamp'].includes((ft || '').toLowerCase())
}

export function isNumberFieldType(ft) {
  return ['integer', 'int', 'number', 'float', 'decimal'].includes((ft || '').toLowerCase())
}

/**
 * 值输入 placeholder
 *
 * @param operator 操作符（决定 placeholder 文案）
 * @param fieldType 字段类型（boolean 没有「多个值」提示）
 */
export function getRuleValuePlaceholder(rule) {
  const op = typeof rule === 'string' ? rule : rule.operator
  if (['IN', 'NOT IN'].includes(op)) {
    return '多个值用英文逗号分隔，如 1,2,3'
  }
  if (['LIKE', 'NOT LIKE'].includes(op)) {
    return '输入关键词（自动模糊匹配）'
  }
  return '值'
}

/**
 * boolean 字段值的选项（用于 AppSelect）
 *
 * value 用字符串 'true' / 'false'（与 picker/select 体系 string 形式一致）
 * 序列化时直接输出 true / false，不加引号（SQL 原生字面量）
 */
export const BOOLEAN_VALUE_OPTIONS = [
  { value: 'true', label: '是' },
  { value: 'false', label: '否' },
]