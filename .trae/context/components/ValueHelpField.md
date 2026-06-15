# ValueHelpField Component Context

> **目标文件**: `src/components/common/ValueHelpField.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

值帮助字段。F4 帮助(选择对话框),常用于外键字段。

**架构位置**: MetaForm 字段类型之一

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Any | `null` | v-model |
| `objectType` | String | `''` | 目标对象类型 |
| `displayField` | String | `'name'` | 显示字段 |
| `valueField` | String | `'id'` | 值字段 |
| `multiple` | Boolean | `false` | 多选 |
| `filters` | FilterField[] | `[]` | 预过滤条件 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |
| `change` | `{value, item}` | 详细变化 |

### Slot
| Name | Description |
|------|-------------|
| `display` | 自定义显示 |

## 3. 调用方(依赖)

- `src/components/common/SearchHelpDialog.vue`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量选项
- 远程搜索
- 关联过滤

## 6. 易错点

- ⚠️ **显示 vs 值**: 必须解耦
- ⚠️ **回显**: 显示已选对象的 displayField

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |