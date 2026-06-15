# ObjectScopeSection Component Context

> **目标文件**: `src/components/common/RelationScopeTree/ObjectScopeSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

对象域分区。在 RelationScopeTree 中按对象类型分组。

## 2. Props

| Name | Type | Description |
|------|------|-------------|
| `objectType` | String | 对象类型 |
| `scopes` | Scope[] | 该类型下的范围 |

## 3. 调用方

- `src/components/common/RelationScopeTree/RelationScopeTree.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多对象类型
- 对象类型图标

## 6. 易错点

- ⚠️ **图标**: 不同对象类型应配图标

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |