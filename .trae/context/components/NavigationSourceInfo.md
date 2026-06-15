# NavigationSourceInfo Component Context

> **目标文件**: `src/components/common/MetaListPage/NavigationSourceInfo.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

导航来源信息。展示当前页面的来源(如"从 BO_001 跳转过来")。

## 2. Props

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `source` | Object | `null` | 来源对象 |
| `breadcrumb` | Breadcrumb[] | `[]` | 面包屑 |

## 3. 调用方

- `src/components/common/MetaListPage/MetaListPage.vue`
- `src/components/common/MultiObjectManagementPage/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 跨多级跳转
- 来源对象已删除

## 6. 易错点

- ⚠️ **深度**: 来源不应无限长

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |