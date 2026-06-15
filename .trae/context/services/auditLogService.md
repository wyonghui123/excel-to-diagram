# auditLogService Context

> **目标文件**: `src/services/auditLogService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P3
> **测试覆盖**: ⚠️ 0%
> **Healer**: **deny**(审计日志敏感,必须人工)

## 1. 职责 (What)

审计日志服务。记录用户的关键操作(登录、变更、删除),供审计与合规使用。

**架构位置**: P3 合规 service

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `log` | `(action, data) => Promise<void>` | 记录日志 |
| `list` | `(filter) => Promise<Log[]>` | 查询日志 |
| `getDetail` | `(id) => Promise<Log>` | 详情 |
| `export` | `(filter) => Promise<Blob>` | 导出 |

## 3. 调用方

预期:
- 几乎所有 service 调用(自动审计)
- `src/components/common/AuditLog/`
- `src/components/common/AuditLogDetail/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 AuditLog 验证 |

## 5. 边界场景

- 日志量(>1M 条)
- 日志归档
- 跨域时钟
- 字段脱敏

## 6. 易错点

- ⚠️ **不可篡改**: 日志必须 append-only
- ⚠️ **完整记录**: 必须含 user/timestamp/action/target
- ⚠️ **异步**: 不能阻塞主流程

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |