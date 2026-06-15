# AppInput Component Context

> **目标文件**: `src/components/common/AppInput/AppInput.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (59 tests)

## 1. 职责 (What)

通用输入框。基于 Element Plus 二次封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | String | `''` | v-model |
| `type` | String | `'text'` | text / password / number / textarea |
| `placeholder` | String | `''` | 占位符 |
| `clearable` | Boolean | `true` | 是否可清空 |
| `maxlength` | Number | `null` | 最大长度 |
| `showWordLimit` | Boolean | `false` | 显示字数 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |
| `blur` | `{event}` | 失焦 |
| `enter` | `{event}` | 回车 |

## 3. 调用方

- Element Plus `<el-input>`
- `src/components/common/MetaForm.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (59 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90% ✅ 已达成

## 5. 边界场景

- 极长输入
- 粘贴富文本
- 中文输入防抖

## 6. 易错点

- ⚠️ **trim**: 默认不 trim,需明确

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |