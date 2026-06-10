# v3.11 Legacy Code 简化 (v1.0)

> **日期**: 2026-06-06
> **状态**: ✅ 7/7 测试全部通过 (无回归)
> **总工时**: ~30min
> **关联**: v3.10 调研 + v3.6 SQLite Pool 实施

---

## 🎯 关键发现

### v3.6 SQLite Pool 实施已有 legacy fallback

调研发现 v3.6 实施 `SQLiteConnectionPool` 时, 保留了 legacy 模式作为**安全 fallback**:
- pool 初始化失败 → fallback to legacy
- 单测试用 `use_pool=False` 验证对比

### 简化目标

| 维度 | 简化前 | 简化后 |
|------|------|------|
| **双分支判断** | 9 处 `if self._use_pool and self._write_queue:` | 1 处 `if self._is_pool_active:` |
| **代码可读性** | 重复模式 | 单一 `property` 抽象 |
| **docstring** | "legacy 模式: 单连接 + threading.Lock（向后兼容降级）" | "🆕 v3.11 简化: 默认 pool, legacy 仅 fallback" |
| **外部行为** | - | 100% 不变 (仅内部重构) |

---

## 🛠️ 实施变更

### 文件: `meta/core/sql_adapters.py`

**改动 1: 新增 `_is_pool_active` property**

```python
@property
def _is_pool_active(self) -> bool:
    """🆕 v3.11: 简化判断 - pool 模式激活中?"""
    return self._use_pool and self._write_queue is not None
```

**改动 2: 9 处双分支简化**

| 位置 | 简化前 | 简化后 |
|------|------|------|
| `execute` | `if self._use_pool and self._pool and self._write_queue:` | `if self._is_pool_active and self._pool:` |
| `begin_transaction` | `if self._use_pool and self._write_queue:` | `if self._is_pool_active:` |
| `in_transaction` | (同) | (同) |
| `commit` | (同) | (同) |
| `rollback` | (同) | (同) |
| `set_savepoint` | (同) | (同) |
| `rollback_to` | (同) | (同) |
| `release_savepoint` | (同) | (同) |
| `checkpoint` | (同) | (同) |

**改动 3: docstring 简化**

```python
# 旧
"""SQLite 数据源适配器
支持两种运行模式：
- pool 模式（默认）：读写分离连接池 + WriteQueue 串行化写入
- legacy 模式：单连接 + threading.Lock（向后兼容降级）
"""

# 新
"""SQLite 数据源适配器
🆕 v3.11 简化:
- 默认模式: 读写分离连接池 + WriteQueue 串行化写入
- legacy 模式: 仅在 pool 初始化失败时 fallback (内部)
- use_pool=False 仅用于测试 (`meta/tests/test_connection_pool.py:legacy_adapter`)
"""
```

---

## 📊 量化收益

| 指标 | 价值 |
|------|------|
| **代码行数** | -10 行 (重复模式 → property) |
| **可维护性** | ⬆ 显著提升 (新逻辑只需改 1 处) |
| **外部行为** | 0 变化 (内部重构) |
| **测试覆盖** | 7/7 通过 (P0-1 / P0-2 / P1-3 / P2-4 / P2-5 / P3-6 / v3.10) |
| **生产代码** | 0 改动 (79 处 `SQLiteAdapter()` 默认 use_pool=True) |

---

## 🛡️ 安全性

### 保留的 Legacy 部分 (有 fallback 价值)

| 项 | 保留原因 |
|----|---------|
| `_connect_legacy` 方法 | pool 初始化失败的 fallback |
| `_lock` 字段 | legacy 模式同步用 |
| `_execute_legacy` 方法 | legacy 模式 query 路径 |
| `use_pool` 参数 | API 向后兼容 |
| `legacy_adapter` 测试 fixture | 对比测试 |

### 调研确认

| 维度 | 数据 |
|------|------|
| 生产代码用 `use_pool=False` | **0 处** |
| 测试用 `use_pool=False` | **1 处** (`meta/tests/test_connection_pool.py:53`) |
| 内部 `_use_pool` 引用 | 0 (全改为 `_is_pool_active`) |
| pool 默认启用 | ✅ (run `check_legacy.py` 验证) |

---

## 🔧 实施过程踩的坑

1. **vitest 后台跑** — 强杀后才稳定
2. **gevent_server.py 文档化已 v3.10 完成** — 此次未动
3. **外部 import path 验证** — grep 确认 `use_pool=False` 仅 1 处测试

---

## 📈 大主线 v3.0 → v3.11 完整演进

| 阶段 | Action 数 | 关键技术 |
|------|:---:|------|
| v3.0 | 6 | registry + 统一端点 |
| v3.1 | 11 | 文件流 + 5 业务 Action |
| v3.2 | 12 | Subflow + OpenAPI + TS types 基础 |
| v3.4 | 16 | Function 维度 |
| v3.5 | 19 | enum_type CRUD |
| v3.6 | 19 | Subflow 6 项 + **SQLite Pool (含 legacy fallback)** |
| v3.7 | 19 | dry-run / 模板 / metrics / CI / 错误码 |
| v3.8 | 19 | Waitress + SSE 修复 |
| v3.9 | 19 | Gevent + 真流式 + 测试 7 模块 |
| v3.10 | 19 | Gevent experimental 文档化 + Pool 复用 + 7/7 |
| **v3.11** | **19** | **Legacy 代码简化 + _is_pool_active + 7/7** |

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [bo-action-v3.10-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.10-result.md) | v3.10 调研触发 |
| [bo-action-v3.9-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.9-result.md) | v3.9 gevent + 测试 7 模块 |

---

## ⚠️ 已知限制

### 1. 进一步清理需要更大重构
- `_lock` 字段删除需要 100% 确认无外部用 (已确认 0 处)
- `_execute_legacy` 删除需删除 `use_pool=False` 参数 (但会破坏 1 处测试)

### 2. admin 状态被锁
- 多次失败触发 (5+)
- fixtures/admin_token.py 内有 auto unlock
- 建议: 加全局 unlock cron

### 3. gevent 仍 experimental
- v3.10 文档化
- Python 3.14 + gevent 26.5 socket 兼容问题未解
- 需 gevent 27 或 ASGI server (uvicorn) 替代

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-06 | 提取 _is_pool_active 简化 9 处双分支, docstring 简化, 7/7 不回归 |
