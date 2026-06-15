# AssociationSelector Component Context

> **目标文件**: `src/components/bo/AssociationSelector.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关联选择器。弹窗形式选择关联对象,支持搜索、过滤、批量选择。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Any | `null` | v-model |
| `targetType` | String | `''` | 目标对象类型 |
| `multiple` | Boolean | `false` | 多选 |
| `max` | Number | `0` | 最大选择数(0=不限) |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |
| `confirm` | `{items}` | 确认 |

### Slot
| Name | Description |
|------|-------------|
| `item` | 自定义项 |
| `filter` | 自定义过滤 |

## 3. 调用方

- `src/services/associationService.js`
- `src/components/common/SearchHelpDialog.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量候选(>1000)
- 批量选择
- 已选上限

## 6. 易错点

- ⚠️ **权限**: 只显示用户有权访问的对象

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |