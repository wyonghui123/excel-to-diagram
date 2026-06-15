# graphqlClient Context

> **目标文件**: `src/services/graphqlClient.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

GraphQL 客户端。封装 GraphQL 查询/变更,支持缓存、订阅。

**架构位置**: P3 数据层 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `query` | `(document, variables) => Promise<T>` | 查询 |
| `mutate` | `(document, variables) => Promise<T>` | 变更 |
| `subscribe` | `(document, variables, onData) => Subscription` | 订阅 |
| `cacheRead` | `(query) => T` | 读缓存 |
| `cacheWrite` | `(query, data) => void` | 写缓存 |

## 3. 调用方

预期:
- 部分 service 可能用 GraphQL(需确认)
- 实时数据需求场景

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 订阅断线重连
- 缓存一致性
- 复杂查询性能
- N+1 查询

## 6. 易错点

- ⚠️ **缓存策略**: 必须明确失效时机
- ⚠️ **订阅生命周期**: 必须 cleanup
- ⚠️ **错误处理**: GraphQL 错误格式特殊

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |