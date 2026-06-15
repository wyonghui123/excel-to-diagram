# AssociationNavigationMenu Component Context

> **目标文件**: `src/components/common/MetaListPage/AssociationNavigationMenu.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关联导航菜单。在 MetaListPage 中提供关联对象的快速跳转菜单。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `associations` | Assoc[] | `[]` | 关联定义 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `navigate` | `{assocType, targetId}` | 跳转 |

## 3. 调用方

- `src/components/common/MetaListPage/MetaListPage.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多关联类型
- 权限拦截

## 6. 易错点

- ⚠️ **路由**: 跳转应保留面包屑

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |