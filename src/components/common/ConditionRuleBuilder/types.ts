/**
 * ConditionRuleBuilder 类型定义
 *
 * 通用条件规则配置组件（Rule + Group 树形结构）
 *
 * [v26 2026-08-26] 抽取自 ConditionRuleDialog.vue
 *   - 设计依据: docs/specs/spec-condition-rule-builder.md
 *   - 行业对照: Salesforce Filter, Proofpoint Cloud Rule Editor, MetacatUI QueryBuilder
 *   - 头部产品对照: SAP PFCG Authorization Field (字段/操作符/值) 多行模式
 */

/**
 * 字段元数据（由父组件传入，用于字段下拉 + 字段类型判断）
 *
 * 来源: 后端 GET /api/v1/meta/fields?resource_type=xxx
 *       或前端的 field_metadata store
 */
export interface FieldMetadata {
  id: number
  name: string
  db_column: string
  field_type: 'integer' | 'float' | 'decimal' | 'number'
                 | 'string' | 'text' | 'boolean' | 'bool'
                 | 'date' | 'datetime' | 'timestamp'
                 | 'enum' | string
  is_foreign_key?: boolean
  relation_object?: string
  is_business_key?: boolean
  is_enum?: boolean
  enum_values?: string[] | null
  enum_ref?: string | null
}

/**
 * 原子条件（叶子节点）
 */
export interface RuleNode {
  type: 'rule'
  id: string
  field: string
  fieldType: string
  operator: string
  value: string | number | boolean | Array<any>
  /** 关联元数据（用于 picker） */
  relationObject?: string
  isBusinessKey?: boolean
  isEnum?: boolean
  enumValues?: any[] | null
  enumRef?: string | null
}

/**
 * 组合条件（内部节点）
 */
export interface GroupNode {
  type: 'group'
  id: string
  connector: 'AND' | 'OR'
  /**
   * [2026-11-13 spec-rule-model §12.6.1 方案 C] 非组标记
   *   组内强制仅 1 条原子规则，序列化时按运算符取反（= ↔ !=、IN ↔ NOT IN ...），
   *   不输出 `NOT (...)`，保证后端扁平 AND 文本链路可消费。
   */
  negate?: boolean
  children: ConditionNode[]
}

/**
 * 条件节点（联合类型）
 */
export type ConditionNode = RuleNode | GroupNode

/**
 * 序列化结果（兼容 Python 表达式）
 */
export type ConditionExpression = string
