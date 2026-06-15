# EnumSelect Component Context

> **目标文件**: `src/components/common/EnumSelect.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

枚举选择器。基于 enumService 加载指定枚举,展示为下拉选择。

**架构位置**: MetaForm 字段类型之一

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Any | `null` | v-model |
| `enumCode` | String | `''` | 枚举 code |
| `multiple` | Boolean | `false` | 多选 |
| `showAll` | Boolean | `false` | 显示"全部"选项 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |
| `change` | `{value}` | 同上 |

## 3. 调用方(依赖)

- `src/services/enumService.js`
- `src/components/common/AppSelect.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 枚举不存在
- 多级枚举
- 翻译

## 6. 易错点

- ⚠️ **缓存**: enumService 应缓存
- ⚠️ **value 类型**: string vs number

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |