/**
 * ConditionRuleBuilder 规则初始化工具
 *
 * [v28 2026-08-26] 抽取 initRuleForField 纯函数
 *   - 设计动机: ConditionRuleRow 的 onFieldChange 与 ConditionRuleDialog.loadFieldMetadata
 *     两处都对 rule 做"切换字段时的初始化"操作，但逻辑本应一致
 *   - 历史上父组件直接修改 rule 字段, 绕过 Row 的 onFieldChange, 导致
 *     operator 未校准、enumRef 未同步等 bug
 *   - 现在把 onFieldChange 抽成纯函数, Row 内部和父组件预填场景都调用同一函数
 *
 * 设计原则:
 *   - 输入: 当前 rule + 字段元数据 (FieldMeta | null)
 *   - 输出: 新 rule 对象 (不可变, 避免外部引用漂移)
 *   - 副作用: 无 (纯函数)
 *   - 职责: 字段切换时一次性完成所有元数据同步 + operator 校验 + value/picker 缓存重置
 */

import type { RuleNode, FieldMeta } from './types.ts'
import { getOperatorOptions, isBusinessKeyField } from './operators.ts'

/**
 * 根据字段元数据初始化/重置 rule
 *
 * 调用时机:
 *   - 用户在 Row 内切换字段 (AppSelect change)
 *   - 父组件预填第一行默认字段 (loadFieldMetadata)
 *
 * @param rule    当前 rule (可能已有 field/operator/value)
 * @param meta    字段元数据 (db_column 匹配), null 时按 string 兜底
 *
 * @returns 新的 RuleNode (immutable, 不修改入参)
 */
export function initRuleForField(rule: RuleNode, meta: FieldMeta | null): RuleNode {
  const field = meta?.db_column ?? rule.field
  const fieldType = meta?.field_type || 'string'

  // operator 校验: 旧 operator 在新 fieldType 的合法操作符集合内则保留,
  // 否则切换到该 fieldType 的第一个合法 operator
  const validOps = getOperatorOptions(fieldType).map((o) => o.value)
  const newOp = validOps.includes(rule.operator) ? rule.operator : (validOps[0] || "=")

  return {
    ...rule,
    field,
    fieldType,
    operator: newOp,
    value: '',  // 重置值
    relationObject: meta?.is_foreign_key ? meta.relation_object : '',
    isBusinessKey: meta ? isBusinessKeyField(meta) : false,
    isEnum: !!meta?.is_enum,
    enumValues: meta?.enum_values || null,
    enumRef: meta?.enum_ref || null,
    pickerVisible: false,
    pickerSelectedIds: [],
    pickerSelectedItems: [],
  }
}