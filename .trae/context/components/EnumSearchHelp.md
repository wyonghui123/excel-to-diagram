# EnumSearchHelp Component Context

> **目标文件**: `src/components/common/EnumSearchHelp.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

枚举搜索帮助。枚举的搜索对话框版本,用于大量枚举项场景。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Any | `null` | v-model |
| `enumCode` | String | `''` | 枚举 code |
| `multiple` | Boolean | `false` | 多选 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 值变化 |

## 3. 调用方

- `src/services/enumService.js`
- `src/components/common/SearchHelpDialog.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量枚举(>100)
- 跨枚举搜索

## 6. 易错点

- ⚠️ **搜索**: 模糊匹配 code/name

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |