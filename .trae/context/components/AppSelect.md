# AppSelect Component Context

> **目标文件**: `src/components/common/AppSelect/AppSelect.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (50 tests)

## 1. 职责 (What)

通用选择器。基于 Element Plus `<el-select>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Any | `null` | v-model |
| `options` | Option[] | `[]` | 选项 |
| `multiple` | Boolean | `false` | 多选 |
| `filterable` | Boolean | `true` | 可搜索 |
| `clearable` | Boolean | `true` | 可清空 |
| `placeholder` | String | `''` | 占位符 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |
| `change` | `{value}` | 同上 |
| `clear` | - | 清空 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义选项 |

## 3. 调用方

- Element Plus `<el-select>`
- `src/components/common/MetaForm.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (50 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 大量选项(>1000)
- 多选 + 远程搜索
- 分组选项

## 6. 易错点

- ⚠️ **远程搜索**: 防抖
- ⚠️ **多选**: value 类型

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |