# RelationFilterSection Component Context

> **目标文件**: `src/components/common/RelationScopeTree/RelationFilterSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关系过滤分区。RelationScopeTree 顶部的过滤区域,支持对象/关系类型筛选。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectTypes` | String[] | `[]` | 可选对象类型 |
| `relationTypes` | String[] | `[]` | 可选关系类型 |
| `selected` | Filter | `{}` | 当前过滤 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:selected` | `{value}` | 过滤变化 |

## 3. 调用方

- `src/components/common/RelationScopeTree/RelationScopeTree.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多选/单选
- 实时过滤

## 6. 易错点

- ⚠️ **联动**: 与树节点状态同步

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |