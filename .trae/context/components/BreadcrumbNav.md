# BreadcrumbNav Component Context

> **目标文件**: `src/components/common/BreadcrumbNav/BreadcrumbNav.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

面包屑导航。展示当前页面的层级路径,支持点击跳转。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `items` | Breadcrumb[] | `[]` | 路径项 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `navigate` | `{path}` | 跳转 |

### Slot
| Name | Description |
|------|-------------|
| `item` | 自定义项 |

## 3. 调用方(依赖)

- `src/router/index.ts`
- `src/stores/navigation.js`(可能)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多级路径(>5)
- 跨工作区
- 动态面包屑

## 6. 易错点

- ⚠️ **同步**: 与路由同步
- ⚠️ **图标**: 首页图标

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |