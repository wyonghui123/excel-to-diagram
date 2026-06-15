# TableHeaderFilter Component Context

> **目标文件**: `src/components/common/TableHeaderFilter/TableHeaderFilter.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

表头筛选器。表格列头点击触发的列内筛选下拉。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `column` | Column | `null` | 列定义 |
| `modelValue` | Any | `null` | 当前筛选值 |
| `options` | Option[] | `[]` | 选项(枚举/唯一值) |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义筛选 UI |

## 3. 调用方

- `src/components/common/MetaTable.vue`
- `src/services/filterService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量选项
- 多列筛选组合

## 6. 易错点

- ⚠️ **图标**: 已筛选列应显示筛选图标

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |