# ErrorBoundary Component Context

> **目标文件**: `src/components/common/ErrorBoundary.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

错误边界。捕获子组件渲染错误,展示降级 UI,防止整个应用崩溃。

**架构位置**: 顶层 AppShell 包裹

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `fallback` | Component | `null` | 自定义降级 UI |
| `onError` | Function | `null` | 错误回调 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 子组件 |
| `fallback` | 自定义降级 |

## 3. 调用方

- 顶级应用包裹

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [X] (错误场景难 E2E) |

## 5. 边界场景

- 异步错误
- 嵌套 ErrorBoundary
- 错误恢复(重置)

## 6. 易错点

- ⚠️ **只能捕获渲染错误**: 不能捕获异步/事件处理错误
- ⚠️ **上报**: 必须上报到错误监控(如 Sentry)

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |