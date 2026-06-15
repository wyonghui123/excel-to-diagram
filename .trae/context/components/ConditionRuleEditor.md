# ConditionRuleEditor Component Context

> **目标文件**: `src/components/common/ConditionRuleEditor/ConditionRuleEditor.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (Where)

条件规则编辑器。可视化编辑"IF...THEN..."条件规则。

**架构位置**: MetaForm 高级字段类型

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Rule | `null` | v-model |
| `fields` | Field[] | `[]` | 可用字段 |
| `operators` | String[] | `[]` | 可用操作符 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |

### Slot
| Name | Description |
|------|-------------|
| `condition` | 自定义条件 |
| `action` | 自定义动作 |

## 3. 调用方(依赖)

- `src/services/conditionExpressionService.js`
- `src/components/common/ValueHelpSelector.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 嵌套条件(AND/OR)
- 复杂表达式
- 字段类型分发

## 6. 易错点

- ⚠️ **校验**: 表达式必须可解析
- ⚠️ **性能**: 复杂表达式编译耗时

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |