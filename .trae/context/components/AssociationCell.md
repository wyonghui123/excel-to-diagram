# AssociationCell Component Context

> **目标文件**: `src/components/bo/AssociationCell.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关联表格单元格。在 BO 表格中展示关联对象(支持单/多)。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `value` | Any | `null` | 关联值(ID 或 ID[]) |
| `targetType` | String | `''` | 目标对象类型 |
| `displayField` | String | `'name'` | 显示字段 |
| `multiple` | Boolean | `false` | 多值 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `change` | `{value}` | 值变化 |
| `navigate` | `{targetId}` | 跳转 |

## 3. 调用方

- `src/components/bo/ActionExecutor.vue`
- `src/components/common/MetaTable.vue`(关联列)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多值超长省略
- 关联对象已删除
- 跳转权限

## 6. 易错点

- ⚠️ **批量加载**: 多值必须批量显示字段
- ⚠️ **删除态**: 已删除对象应显示"[已删除]"

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |