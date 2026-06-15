# AppDatePicker Component Context

> **目标文件**: `src/components/common/AppDatePicker/AppDatePicker.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (53 tests)

## 1. 职责 (What)

日期选择器。基于 Element Plus `<el-date-picker>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Date/String | `null` | v-model |
| `type` | String | `'date'` | date / datetime / daterange / datetimerange |
| `format` | String | `'YYYY-MM-DD'` | 显示格式 |
| `valueFormat` | String | `''` | 绑定格式 |
| `placeholder` | String | `''` | 占位符 |
| `disabledDate` | Function | `null` | 禁用日期判断 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |
| `change` | `{value}` | 同上 |
| `blur` | `{event}` | 失焦 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义单元格 |

## 3. 调用方

- Element Plus `<el-date-picker>`
- `src/services/DateFormatService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (53 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 范围选择(开始 > 结束)
- 时区
- 国际化

## 6. 易错点

- ⚠️ **valueFormat**: 与显示格式分离
- ⚠️ **时区**: 必须明确

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |