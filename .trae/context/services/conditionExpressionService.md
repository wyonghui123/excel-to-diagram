# conditionExpressionService Context

> **目标文件**: `src/services/conditionExpressionService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (Where)

条件表达式管理。提供表达式的解析、求值、校验能力。

**架构位置**: P2 辅助 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `parseExpression` | `(str) => AST` | 字符串 → AST |
| `evaluate` | `(expr, context) => any` | 求值 |
| `validateExpression` | `(expr) => ValidationResult` | 校验 |
| `getVariables` | `(expr) => string[]` | 提取变量 |

## 3. 调用方

预期:
- `src/components/common/ConditionRuleEditor/`
- `src/components/common/ValueHelpSelector.vue`
- `src/services/filterService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 ConditionRuleEditor 验证 |

## 5. 边界场景

- 嵌套括号
- 字符串转义
- 函数调用安全性
- 类型不匹配
- 无限递归

## 6. 易错点

- ⚠️ **安全**: 表达式求值必须沙箱化
- ⚠️ **性能**: 复杂表达式可能慢
- ⚠️ **错误信息**: 错误位置必须可定位

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |