# DetailPageAssociationSection Component Context

> **目标文件**: `src/components/common/DetailPage/AssociationSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

DetailPage 关联项区域。展示对象的关联(只读)。

## 2. Props

| Name | Type | Description |
|------|------|-------------|
| `objectId` | String | 对象 ID |
| `associations` | Assoc[] | 关联定义 |

## 3. 调用方

- `src/components/common/DetailPage/DetailPage.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量关联(>100)
- 关联链接跳转

## 6. 易错点

- ⚠️ **点击跳转**: 关联项应可点击跳转

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |