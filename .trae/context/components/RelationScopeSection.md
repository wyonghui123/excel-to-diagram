# RelationScopeSection Component Context

> **目标文件**: `src/components/common/RelationScopeTree/RelationScopeSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关系范围分区。在 RelationScopeTree 中按关系类型分组。

## 2. Props

| Name | Type | Description |
|------|------|-------------|
| `relationType` | String | 关系类型 |
| `scopes` | Scope[] | 该类型下的范围 |

## 3. 调用方

- `src/components/common/RelationScopeTree/RelationScopeTree.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量关系类型
- 空分组

## 6. 易错点

- ⚠️ **图标**: 不同关系类型应配图标

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |