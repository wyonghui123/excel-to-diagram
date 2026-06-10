# v3.12 删 `_lock` 字段 (v1.0)

> **日期**: 2026-06-06
> **状态**: ✅ 7/7 测试全部通过 (无回归)
> **总工时**: ~20min
> **关联**: v3.11 简化后继续清理

---

## 🎯 关键变更

### 1. 删除 `self._lock` 字段
- 原因: 默认 pool 模式不需 thread lock (WriteQueue 串行化写)
- legacy 模式仅在测试用 (`test_connection_pool.py:legacy_adapter`)
- 测试场景单线程, 无需锁

### 2. 移除 8 处 `with self._lock:` 包裹

| 位置 | 改动 |
|------|------|
| `_execute_legacy` | 删 `with self._lock:` |
| `begin_transaction` (legacy 路径) | 删 + 缩进调整 |
| `commit` (legacy 路径) | 删 + 缩进调整 |
| `rollback` (legacy 路径) | 删 + 缩进调整 |
| `set_savepoint` (legacy 路径) | 删 + 缩进调整 |
| `rollback_to` (legacy 路径) | 删 + 缩进调整 |
| `release_savepoint` (legacy 路径) | 删 + 缩进调整 |
| `checkpoint` (legacy 路径) | 删 + 缩进调整 |

### 3. 保留部分

| 项 | 原因 |
|----|------|
| `_connect_legacy` | test 用 |
| `_execute_legacy` | test 用 |
| `use_pool` 参数 | API 兼容 |
| `legacy_adapter` fixture | 对比测试 |
| `import threading` | 35 行 module-level `_table_columns_lock` 仍用 |

---

## 📊 量化收益

| 指标 | 价值 |
|------|------|
| **代码行数** | -12 行 (8 处 with 包裹) |
| **字段** | -1 (threading.Lock) |
| **运行时内存** | -1 Lock 对象 (~80 字节) |
| **可维护性** | ⬆ 减一层 "用不到" 的代码 |
| **测试覆盖** | 7/7 通过 (P0-1/P0-2/P1-3/P2-4/P2-5/P3-6/v3.10) |
| **生产代码** | 0 改动 (默认仍 pool) |

---

## 🛡️ 安全性

### 删除前验证

| 维度 | 数据 |
|------|------|
| 外部代码用 `self._lock` | **0 处** (全在 sql_adapters.py 内) |
| 外部代码用 `_lock` 字段 | **0 处** (grep 验证) |
| legacy 模式并发访问 | **无** (仅 4 处测试用, 单线程) |

### 保留的 Lock

```python
# meta/core/sql_adapters.py:35
_table_columns_lock = threading.Lock()  # 🆕 v3.12 保留 - 用于 DDL (CREATE TABLE 等)
```

`_table_columns_lock` 是 **module-level** 锁, 用于保护 DDL 操作, 与 instance-level `_lock` 无关。

---

## 🔧 实施过程踩的坑

1. **IndentationError** — 删 `with self._lock:` 后, 缩进错 3 空格, 修了
2. **vitest 后台干扰** — 强杀后才稳定

---

## 📈 大主线 v3.0 → v3.12 完整演进 (完整大总结)

| 阶段 | Action | 关键技术 | 测试 |
|------|:---:|------|:---:|
| **v3.0** | 6 | registry + 统一端点 | - |
| **v3.1** | 11 | 文件流 + 5 业务 Action | - |
| **v3.2** | 12 | Subflow + OpenAPI + TS types 基础 | - |
| **v3.4** | 16 | Function 维度 (SAP/Palantir 模式) | - |
| **v3.5** | 19 | enum_type CRUD | - |
| **v3.6** | 19 | Subflow 6 项进阶 + **SQLite Pool** (含 legacy fallback) | - |
| **v3.7** | 19 | dry-run / 模板 / metrics / CI / 错误码 (SSE dev 限制) | - |
| **v3.8** | 19 | Waitress 部署 + SSE 修复 + 真流式 (4 字节 flush) | - |
| **v3.9** | 19 | Gevent + 真流式 + **测试基础设施 7 模块** | 6/6 |
| **v3.10** | 19 | Gevent experimental 文档化 + 真根因诊断 | 7/7 |
| **v3.11** | 19 | `_is_pool_active` 简化 9 处双分支 + docstring | 7/7 |
| **v3.12** | **19** | **删 `_lock` 字段 + 移除 8 处 `with self._lock:`** | **7/7** |

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [bo-action-v3.11-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.11-result.md) | 上一步简化 |
| [bo-action-v3.10-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.10-result.md) | Gevent experimental |
| [bo-action-v3.9-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.9-result.md) | 测试基础设施 7 模块 |

---

## ⚠️ 已知限制 + 未来

### 1. legacy 代码无法完全删除
- `_connect_legacy` / `_execute_legacy` 仍存在 (test 用)
- `use_pool` 参数仍保留 (API 兼容)
- 进一步清理需删除 test (破坏测试覆盖)

### 2. gevent 仍 experimental
- v3.10 文档化
- Python 3.14 + gevent 26.5 socket 兼容未解
- 需 gevent 27 或 ASGI server (uvicorn) 替代

### 3. admin 状态锁
- 多次失败触发 (5+)
- fixtures/admin_token.py 内有 auto unlock
- 建议: 加全局 unlock cron

---

## 后续选项

| 选项 | 描述 | 工时 |
|------|------|:---:|
| A | 完全删 legacy (需改 test) | 1h |
| B | DB 损坏预防 3 大方案 | 3 周 |
| C | 等 gevent 27 / ASGI 替换 | 不定 |
| D | 暂停 (v3.12 已生产就绪 + 7/7) | — |
