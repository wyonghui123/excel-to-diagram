# ObjectPageField Component Context

> **目标文件**: `src/components/common/ObjectPage/ObjectPageField.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

ObjectPage 单个字段。根据字段类型渲染对应输入控件。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `field` | Field | `{}` | 字段定义 |
| `value` | Any | `null` | 值 |
| `readonly` | Boolean | `false` | 只读 |
| `error` | String | `''` | 错误信息 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `change` | `{value}` | 值变化 |
| `blur` | - | 失焦 |

## 3. 调用方(依赖)

根据 field.type 渲染:
- 文本 → AppInput
- 数字 → AppInput (type=number)
- 枚举 → EnumSelect
- 外键 → ValueHelpField / FkLinkField
- 日期 → AppDatePicker
- 布尔 → 开关

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 80%

## 5. 边界场景

- 字段类型未知
- 错误显示
- 必填星号

## 6. 易错点

- ⚠️ **类型分发**: 必须覆盖所有字段类型
- ⚠️ **必填**: 视觉标识 + 提交校验

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |