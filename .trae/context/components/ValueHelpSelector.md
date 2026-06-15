# ValueHelpSelector Component Context

> **目标文件**: `src/components/common/ConditionRuleEditor/ValueHelpSelector.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

值帮助选择器。ConditionRuleEditor 内部使用,用于选择字段值。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Any | `null` | v-model |
| `field` | Field | `null` | 字段定义 |
| `operator` | String | `''` | 操作符 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |

## 3. 调用方

- `src/components/common/ConditionRuleEditor/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 不同字段类型
- 操作符影响 UI

## 6. 易错点

- ⚠️ **类型分发**: 根据 field.type 渲染

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |