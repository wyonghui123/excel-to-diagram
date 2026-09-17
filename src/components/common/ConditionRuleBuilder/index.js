/**
 * ConditionRuleBuilder 入口
 *
 * [v28 2026-08-26] rule-init.ts (initRuleForField 纯函数)
 *   - 字段切换时的初始化逻辑统一入口
 *   - 解决历史 bug: 默认字段是 boolean/datetime 时 operator='IN' 非法
 *
 * [v27 2026-08-26] Phase 4 嵌套 AND/OR 子组
 *   - 新增 RuleBuilderGroup 递归组件
 *   - ConditionRuleBuilder 仅作顶层入口，内部递归调用 RuleBuilderGroup
 *
 * [v26 2026-08-26] 通用条件规则配置组件
 *   - 主组件: ConditionRuleBuilder
 *   - 子组件: ConditionRuleRow (单行 rule)
 *   - 类型:    types.ts
 *   - 序列化: serializers.ts
 *   - 操作符: operators.ts
 *   - picker helpers: rule-helpers.ts (fetcher/config/handler)
 */
import ConditionRuleBuilder from './ConditionRuleBuilder.vue'
import ConditionRuleRow from './ConditionRuleRow.vue'
import RuleBuilderGroup from './RuleBuilderGroup.vue'

export { ConditionRuleBuilder, ConditionRuleRow, RuleBuilderGroup }
export * from './types.ts'
export * from './serializers.ts'
export * from './operators.ts'
export * from './rule-helpers.ts'
export * from './rule-init.ts'

export default ConditionRuleBuilder
