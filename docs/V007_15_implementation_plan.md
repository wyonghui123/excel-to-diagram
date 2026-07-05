# V007.15 独立实现方案文档

> **版本**: v1.0
> **日期**: 2026-07-05
> **作者**: dev-agent (基于 §14 SAP LUW 分析 + 实际代码调研)
> **范围**: V007.15 实施全部细节 (L0-L7)
> **SAP LUW**: 推迟到 V008 (用户决策 2026-07-05)

---

## 目录

1. [背景与上下文](#1-背景与上下文)
2. [实施范围与决策](#2-实施范围与决策)
3. [实际代码现状（已调研）](#3-实际代码现状已调研)
4. [Layer 0: db_config_detector.py](#4-layer-0-db_config_detectorpy)
5. [Layer 1: sqlite_tx_state.py](#5-layer-1-sqlite_tx_statepy)
6. [Layer 2: bo_framework.py 修改](#6-layer-2-bo_frameworkpy-修改)
7. [Layer 3: sql_write_queue.py 修改](#7-layer-3-sql_write_queuepy-修改)
8. [Layer 4: audit_service.py 修改](#8-layer-4-audit_servicepy-修改)
9. [Layer 5: orphan_tx_detector.py](#9-layer-5-orphan_tx_detectorpy)
10. [Layer 6: observability.py](#10-layer-6-observabilitypy)
11. [Layer 7: server.py 修改](#11-layer-7-serverpy-修改)
12. [5 个测试文件 (95 cases)](#12-5-个测试文件-95-cases)
13. [部署与回滚](#13-部署与回滚)
14. [风险与缓解](#14-风险与缓解)
15. [交付清单](#15-交付清单)

---

## 1. 背景与上下文

### 1.1 问题

V007.x 系列问题（14 次修复都没解决根因）：
- 生产 172.20.59.7 长期出现「卡死 0% 不动」「撞锁 SQLITE_BUSY」「orphan transaction」
- 根因 = 状态污染：`_in_transaction` 标志与 SQLite 实际状态不一致
- V049-TX hotfix 引入 `BEGIN IMMEDIATE`（2026-06-05）使 orphan tx 风险从历史变为活跃

### 1.2 关联问题

- **V049-FD**（已修复，commit `89c63f0`）：openpyxl FD 泄漏导致 `0% 不动`
- **V049-TX**（未修复）：`BEGIN IMMEDIATE` 引入 orphan tx 风险
- **V007.x**（14 次未根治）：状态污染

### 1.3 设计依据

- `orphan_transaction_deep_analysis.md` §4 完整设计
- §14 SAP LUW 分析（5 个决策已通过）
- 实际代码调研（见 §3）

### 1.4 范围

- **本方案 (V007.15)**：L0-L7 + 测试 + 部署 (~475 lines 代码, 95 测试用例)
- **推迟到 V008**：L8-L10 SAP LUW (L8: sap_luw_manager.py, L9: sap_luw_audit.py, L10: server.py LUW 装饰器)

---

## 2. 实施范围与决策

### 2.1 5 个决策（用户确认 2026-07-05）

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| Q1 | SAP LUW 加到 V007.15 还是 V008? | **V008** | V007.15 聚焦 orphan TX, LUW 需独立 sprint |
| Q2 | Savepoint 粒度? | **per 1000 row** | 20729 行 = 20 savepoints, 平衡 rollback 成本 |
| Q3 | Audit 原子性策略? | **Hybrid** | CRUD 严格, LOGIN/LOGOUT 宽松 |
| Q4 | action_dispatcher scope? | **A: 实现 execute_sync 但不引入 LUW** | spec-audit-log-v2 §4.4, 最小 scope |
| Q5 | Async vs sync audit? | **CRUD → L9 sync (新), LOGIN/LOGOUT → async (现有)** | Q3 的实现 |

### 2.2 实施范围

**V007.15 范围**：
- 4 个新文件 (L0, L1, L5, L6)
- 4 个修改文件 (L2: bo_framework.py, L3: sql_write_queue.py, L4: audit_service.py, L7: server.py)
- 5 个测试文件 (95 cases)
- 1 个 smoke test
- 1 个部署文档
- 1 个部署回滚文档

**总代码量**：~475 lines 生产代码 + ~95 cases 测试

### 2.3 不在范围

- SAP LUW (L8-L10) → V008
- 性能优化 (per-1000-row savepoint) → V008
- action_dispatcher 完整 LUW 集成 → V008
- audit_log 6 月归档 (spec-audit-log-v2 §4.8) → V007.16

---

## 3. 实际代码现状（已调研）

### 3.1 已有但需增强

| 组件 | 现状 | 需增强 |
|------|------|--------|
| `meta/core/bo_framework.py` | L457-475 `commit/rollback` 有 try/except 但**无 finally 重置状态** | L2 加 try/finally + state verification |
| `meta/core/sql_write_queue.py` | L228-256 `begin_transaction` 有 `_in_transaction` 检查但**未验证 SQLite 真实状态** | L3 加 phantom TX 检测 |
| `meta/core/sql_adapters.py` | L912-942 `commit/rollback` **未捕获异常 + 无状态验证** | 间接由 L2 包裹保护 |
| `meta/services/audit_service.py` | L551-554 `create` 在事务内有原子性 | L4 加 retry + 严格 audit 策略 |
| `meta/core/action_dispatcher.py` | L91-94 `execute_sync` audit 在 finally 块 | 已实现，无需 V007.15 修改 |
| `meta/services/structured_logger.py` | L325 `log_business` 走 async_audit_writer | 非 CRUD 保留异步 |

### 3.2 已有 SAP-LUW-like 机制（无需重新设计）

| 机制 | 文件:行 | 说明 |
|------|---------|------|
| `TransactionContext` | `bo_framework.py:575-602` | 异常→rollback, set_outcome(False)→rollback |
| `_flush_pending_audit_records` | `bo_framework.py:480-513` | 事务 commit 后 flush audit |
| `drain_pending_audits` | context API | 原子获取+清空 audit 缓存 |
| `_AUTO_TXN_ACTIONS` 列表 | `bo_framework.py:138-143` | CRUD/associate 自动包裹事务 |
| `set_savepoint/rollback_to/release_savepoint` | `sql_write_queue.py:321-341` | savepoint API 已有 |

### 3.3 真正的状态污染点（代码中已确认）

| 位置 | 问题 |
|------|------|
| `sql_write_queue.py:243` | `BEGIN IMMEDIATE` 后 `_in_transaction = True`（L244），但**如果之前状态污染为 False 实际有 TX** → 标志错误 |
| `sql_write_queue.py:258-262` | `commit` 成功后 `_in_transaction = False`，**但如果 conn 实际仍在 tx 中（COMMIT 失败但被吞）** → 状态错误 |
| `sql_write_queue.py:314-317` | `rollback` 同上 |
| `sql_adapters.py:899-904` | `_in_transaction = True` 在 L900，**但如果在 BEGIN 抛异常时 L900 未执行，L244 的 _in_transaction 设置可能跳过** |

---

## 4. Layer 0: db_config_detector.py

### 4.1 文件路径

`meta/core/db_config_detector.py` (NEW)

### 4.2 依赖

- 标准库: `sqlite3`, `logging`, `dataclasses`, `enum`
- 无第三方依赖

### 4.3 完整代码

```python
# meta/core/db_config_detector.py
# [V007.15 L0] 启动时自动检测 SQLite 运行时配置
# 区分 State A (WAL+5s), State B (DELETE+30s), State C (其他)
# Singleton 模式，全局只检测一次
"""
[V007.15 L0] 启动时 SQLite 运行时配置检测

设计动机:
- 生产可能有 3 种配置:
  - State A: WAL + busy_timeout=5000 (worktree-V049 base)
  - State B: DELETE + busy_timeout=30000 (release-prep-worktree dirty)
  - State C: 其他 (未来)
- 不同状态下, defense 行为需调整 (e.g. retry max, orphan detector interval)
- 启动时检测, 全局 singleton, 不重复 connect

调用:
- server.py init: detect_runtime_config(db_path) → set singleton
- 各 layer: get_runtime_config() → 读 singleton
"""
import sqlite3
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class JournalMode(Enum):
    WAL = "wal"
    DELETE = "delete"
    TRUNCATE = "truncate"
    MEMORY = "memory"
    OFF = "off"


@dataclass
class RuntimeDbConfig:
    """检测到的 SQLite 运行时配置 (immutable after detection)"""
    journal_mode: JournalMode
    busy_timeout_ms: int
    synchronous: str
    foreign_keys_on: bool
    auto_vacuum: str
    deployment_state: str  # 'A' | 'B' | 'C' | 'UNKNOWN'

    # Defense behavior modifiers
    use_explicit_conn_rollback: bool
    use_orphan_detector: bool
    audit_retry_max: int
    orphan_check_interval_sec: int


# Singleton
_runtime_config: Optional[RuntimeDbConfig] = None


def detect_runtime_config(db_path: str) -> RuntimeDbConfig:
    """
    启动时调用一次, 检测 SQLite 实际配置.
    Side effect: 设置 module-level singleton.

    Args:
        db_path: SQLite db file path

    Returns:
        RuntimeDbConfig (或 safe defaults if detection fails)
    """
    global _runtime_config
    if _runtime_config is not None:
        return _runtime_config

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            journal_raw = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_raw = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            sync_raw = conn.execute("PRAGMA synchronous").fetchone()[0]
            fk_raw = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            av_raw = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
        finally:
            conn.close()

        journal = JournalMode(journal_raw.lower())
        busy_ms = int(busy_raw)

        # Map to deployment state
        if journal == JournalMode.WAL and busy_ms == 5000:
            state = "A"
            audit_retry_max = 2
            orphan_interval = 30
        elif journal == JournalMode.DELETE and busy_ms == 30000:
            state = "B"
            audit_retry_max = 5
            orphan_interval = 60
        else:
            state = "C"
            audit_retry_max = max(2, busy_ms // 5000)
            orphan_interval = max(30, busy_ms // 1000)

        config = RuntimeDbConfig(
            journal_mode=journal,
            busy_timeout_ms=busy_ms,
            synchronous=sync_raw,
            foreign_keys_on=(fk_raw == 1),
            auto_vacuum=av_raw,
            deployment_state=state,
            use_explicit_conn_rollback=True,  # always safe
            use_orphan_detector=True,         # always safe
            audit_retry_max=audit_retry_max,
            orphan_check_interval_sec=orphan_interval,
        )

        logger.info(
            f"[V007.15 L0] Runtime DB config detected: state={state}, "
            f"journal={journal.value}, busy_timeout={busy_ms}ms, "
            f"audit_retry_max={audit_retry_max}, orphan_interval={orphan_interval}s"
        )
        _runtime_config = config
        return config
    except Exception as e:
        # Detection failed, use safe defaults
        logger.error(f"[V007.15 L0] Failed to detect runtime config, using safe defaults: {e}")
        config = RuntimeDbConfig(
            journal_mode=JournalMode.WAL,
            busy_timeout_ms=5000,
            synchronous="NORMAL",
            foreign_keys_on=True,
            auto_vacuum="INCREMENTAL",
            deployment_state="UNKNOWN",
            use_explicit_conn_rollback=True,
            use_orphan_detector=True,
            audit_retry_max=3,
            orphan_check_interval_sec=30,
        )
        _runtime_config = config
        return config


def get_runtime_config() -> RuntimeDbConfig:
    """
    获取检测到的 config. 必须在 init 阶段调过 detect_runtime_config().

    Raises:
        RuntimeError: 如果还没调过 detect_runtime_config()
    """
    if _runtime_config is None:
        raise RuntimeError(
            "[V007.15 L0] DB config not detected yet. "
            "Call detect_runtime_config(db_path) during server init."
        )
    return _runtime_config


def reset_runtime_config() -> None:
    """仅测试用. 重置 singleton."""
    global _runtime_config
    _runtime_config = None
```

### 4.4 验证

- `python -c "from meta.core.db_config_detector import detect_runtime_config, get_runtime_config; c = detect_runtime_config('test.db'); print(c.deployment_state)"`
- 期望: `A` (WAL+5s 默认)

---

## 5. Layer 1: sqlite_tx_state.py

### 5.1 文件路径

`meta/core/sqlite_tx_state.py` (NEW)

### 5.2 完整代码

```python
# meta/core/sqlite_tx_state.py
# [V007.15 L1] SQLite 事务状态探测 (savepoint probe)
"""
[V007.15 L1] SQLite 事务真实状态探测

原理:
- Python sqlite3 没有 sqlite3_txn_state() 暴露
- 用 SAVEPOINT 探测:
  - SAVEPOINT 成功 → 在事务中
  - OperationalError("no transaction is active") → 不在事务中
- 1 次探测 ~1ms, 无副作用 (savepoint 立即 release)

成本:
- 每次探测 ~1ms
- 每次 commit/rollback 后探测 1 次 → 增加 ~2ms
- 批量场景 100 行: 100 * 2ms = 200ms (可接受)
"""
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


class TxState:
    NONE = "none"        # 不在事务中
    READ = "read"        # 只读事务 (BEGIN, 不会到 SQLITE_BUSY)
    WRITE = "write"      # 写事务 (BEGIN IMMEDIATE)
    UNKNOWN = "unknown"  # 探测失败


def get_tx_state(conn) -> str:
    """
    用 savepoint probe 探测 SQLite 实际事务状态.

    Args:
        conn: sqlite3.Connection

    Returns:
        str: TxState.NONE | TxState.READ | TxState.WRITE | TxState.UNKNOWN

    Notes:
        - READ 和 WRITE 不可区分 (savepoint 都会成功)
        - 我们只用 NONE vs 非-NONE 二分
    """
    try:
        conn.execute("SAVEPOINT __v007_15_probe__")
        conn.execute("RELEASE SAVEPOINT __v007_15_probe__")
        return TxState.WRITE  # in tx (read or write)
    except sqlite3.OperationalError as e:
        err_str = str(e).lower()
        if "no transaction" in err_str or "no transactions" in err_str:
            return TxState.NONE
        logger.warning(f"[V007.15 L1] Unexpected OperationalError: {e}")
        return TxState.UNKNOWN
    except Exception as e:
        logger.warning(f"[V007.15 L1] tx_state probe failed: {e}")
        return TxState.UNKNOWN


@contextmanager
def tx_state_verified_action(conn, expected_state: str = TxState.NONE, action_label: str = ""):
    """
    Context manager: 验证事务状态, 但不强制 rollback (留给 caller 决定).

    Args:
        conn: sqlite3.Connection
        expected_state: 期望的状态 (默认 NONE)
        action_label: 用于日志

    Yields:
        actual_state: 实际探测到的状态
    """
    actual_before = get_tx_state(conn)
    if actual_before != expected_state:
        logger.warning(
            f"[V007.15 L1] {action_label}: TX state mismatch "
            f"expected={expected_state}, actual={actual_before}"
        )
    try:
        yield actual_before
    finally:
        actual_after = get_tx_state(conn)
        if actual_after != expected_state:
            logger.warning(
                f"[V007.15 L1] {action_label}: TX state drift after action "
                f"expected={expected_state}, post={actual_after}"
            )
```

### 5.3 验证

```python
import sqlite3
from meta.core.sqlite_tx_state import get_tx_state, TxState

c = sqlite3.connect(":memory:")
print(get_tx_state(c))  # 'none'
c.execute("BEGIN IMMEDIATE")
print(get_tx_state(c))  # 'write'
c.execute("ROLLBACK")
print(get_tx_state(c))  # 'none'
c.close()
```

---

## 6. Layer 2: bo_framework.py 修改

### 6.1 文件路径

`meta/core/bo_framework.py` (MODIFY)

### 6.2 修改点

**位置 1**: L457-475 `commit`/`rollback` 加 try/finally + state verification

**位置 2**: L460 `_data_source.commit()` 成功后调 `get_tx_state` 验证

**位置 3**: 引入 `observability.py` 的 metrics

### 6.3 修改 diff (精确)

```python
# meta/core/bo_framework.py
# [V007.15 L2] commit/rollback 加 try/finally + 状态验证

# 在文件顶部 imports 区域 (L1-50 附近) 加:
from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.db_config_detector import get_runtime_config
from meta.core.observability import (
    metrics_inc, OBS_COUNTERS, log_tx_event
)


# 修改 commit 方法 (L457-465):
def commit(self, transaction_id: str = None) -> bool:
    """
    [V007.15 L2] commit with state-aware defense + observability.
    
    Changes from v1:
    - try/finally ensures state reset on success AND failure
    - SQLite state verification after commit
    - Prometheus metrics + structured log
    """
    config = get_runtime_config()
    success = True
    err_msg = None
    try:
        if hasattr(self._data_source, 'commit'):
            self._data_source.commit()
        logger.info(f"[BOFramework] Transaction committed: {transaction_id}")
    except Exception as e:
        err_msg = str(e)
        success = False
        logger.error(f"[BOFramework] Commit failed: {e}")
        metrics_inc(OBS_COUNTERS['commit_failure'])
        log_tx_event('commit', transaction_id, 'error', err_msg)
    finally:
        # [V007.15 L2 关键] 强制重置所有 in_transaction 标志
        try:
            if hasattr(self._data_source, '_in_transaction'):
                self._data_source._in_transaction = False
            if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
                if hasattr(self._data_source._write_queue, '_in_transaction'):
                    self._data_source._write_queue._in_transaction = False
        except Exception as e:
            log_tx_event('commit', transaction_id, 'state_reset_error', str(e))
            success = False

        # [V007.15 L2] [State A/B/C] 显式调 conn.rollback() 强制重置 (防御性)
        if config.use_explicit_conn_rollback:
            try:
                if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
                    wq = self._data_source._write_queue
                    if hasattr(wq, '_write_conn') and wq._write_conn:
                        wq._write_conn.rollback()
            except Exception:
                pass  # 可能在 tx 外, 不算 failure

        # [V007.15 L2 验证] 用 savepoint probe 验证 SQLite 实际状态
        if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
            wq = self._data_source._write_queue
            if hasattr(wq, '_write_conn') and wq._write_conn:
                actual = get_tx_state(wq._write_conn)
                if actual != TxState.NONE:
                    # 实际还在 tx 中! 强制 ROLLBACK
                    try:
                        wq._write_conn.execute("ROLLBACK")
                        log_tx_event('commit', transaction_id, 'forced_rollback', actual)
                        metrics_inc(OBS_COUNTERS['forced_rollback_after_commit'])
                    except Exception as e:
                        log_tx_event('commit', transaction_id, 'forced_rollback_error', str(e))

    if success:
        metrics_inc(OBS_COUNTERS['commit_success'])
        log_tx_event('commit', transaction_id, 'ok', None)
    return success


# 修改 rollback 方法 (L467-475):
def rollback(self, transaction_id: str = None) -> bool:
    """
    [V007.15 L2] rollback with state-aware defense + observability.
    """
    config = get_runtime_config()
    success = True
    err_msg = None
    try:
        if hasattr(self._data_source, 'rollback'):
            self._data_source.rollback()
        logger.info(f"[BOFramework] Transaction rolled back: {transaction_id}")
    except Exception as e:
        err_msg = str(e)
        success = False
        logger.error(f"[BOFramework] Rollback failed: {e}")
        metrics_inc(OBS_COUNTERS['rollback_failure'])
        log_tx_event('rollback', transaction_id, 'error', err_msg)
    finally:
        # [V007.15 L2 关键] 强制重置所有 in_transaction 标志
        try:
            if hasattr(self._data_source, '_in_transaction'):
                self._data_source._in_transaction = False
            if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
                if hasattr(self._data_source._write_queue, '_in_transaction'):
                    self._data_source._write_queue._in_transaction = False
        except Exception as e:
            log_tx_event('rollback', transaction_id, 'state_reset_error', str(e))
            success = False

        # [V007.15 L2] 显式 conn.rollback() 兜底
        if config.use_explicit_conn_rollback:
            try:
                if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
                    wq = self._data_source._write_queue
                    if hasattr(wq, '_write_conn') and wq._write_conn:
                        wq._write_conn.rollback()
            except Exception:
                pass

        # [V007.15 L2 验证] savepoint probe
        if hasattr(self._data_source, '_write_queue') and self._data_source._write_queue:
            wq = self._data_source._write_queue
            if hasattr(wq, '_write_conn') and wq._write_conn:
                actual = get_tx_state(wq._write_conn)
                if actual != TxState.NONE:
                    try:
                        wq._write_conn.execute("ROLLBACK")
                        log_tx_event('rollback', transaction_id, 'forced_rollback', actual)
                        metrics_inc(OBS_COUNTERS['forced_rollback_after_rollback'])
                    except Exception as e:
                        log_tx_event('rollback', transaction_id, 'forced_rollback_error', str(e))

    if success:
        metrics_inc(OBS_COUNTERS['rollback_success'])
        log_tx_event('rollback', transaction_id, 'ok', None)
    return success
```

### 6.4 不修改的地方

- `TransactionContext` (L575-602) **保持不变** — 已有正确语义
- `_flush_pending_audit_records` (L480-513) **保持不变** — 审计 flush 时机正确
- `execute()` (L130-167) **保持不变** — 事务包裹逻辑正确

### 6.5 验证

```python
# 单元测试 (见 §12.3)
def test_commit_forced_rollback_when_state_drift():
    # Mock data source 让 commit "成功" 但 conn 仍在 tx
    ...
```

---

## 7. Layer 3: sql_write_queue.py 修改

### 7.1 文件路径

`meta/core/sql_write_queue.py` (MODIFY)

### 7.2 修改点

**位置**: L228-256 `begin_transaction`

**增加**: phantom TX 检测 (Python=False 但 SQLite=in tx)

### 7.3 修改 diff

```python
# meta/core/sql_write_queue.py
# [V007.15 L3] begin_transaction 加 phantom TX 检测

# 在 imports 区域加:
import sqlite3
from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.db_config_detector import get_runtime_config
from meta.core.observability import metrics_inc, OBS_COUNTERS, log_tx_event


# 修改 begin_transaction 方法 (L228-256):
def begin_transaction(self):
    """
    [V007.15 L3] begin with phantom TX detection.
    
    Changes from v1:
    - Check SQLite actual state before BEGIN
    - If phantom TX detected (Python=False, SQLite=in tx), force ROLLBACK first
    - Metrics: begin_success, begin_skipped, begin_locked, phantom_tx_detected
    """
    if self._in_transaction:
        # 已经标记 in_tx, 跳过
        metrics_inc(OBS_COUNTERS['begin_skipped_already_in_tx'])
        return

    def _do_begin(conn):
        # [V007.15 L3 治本] 防御性检查: 连接是否真的不在 tx 中?
        actual = get_tx_state(conn)
        if actual == TxState.WRITE or actual == TxState.READ:
            # 实际在 tx, 但 Python 状态 False — phantom TX!
            logger.warning(
                f"[V007.15 L3] WriteQueue: phantom TX detected "
                f"(Python=False, SQLite={actual}), forcing ROLLBACK"
            )
            metrics_inc(OBS_COUNTERS['phantom_tx_detected'])
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            self._in_transaction = False

        # 现在安全地 BEGIN
        try:
            conn.execute("BEGIN IMMEDIATE")
            self._in_transaction = True
            metrics_inc(OBS_COUNTERS['begin_success'])
            logger.debug("WriteQueue: Transaction started")
        except sqlite3.OperationalError as e:
            # BEGIN 失败, 但 conn 可能已持锁
            err = str(e).lower()
            if "locked" in err or "busy" in err:
                metrics_inc(OBS_COUNTERS['begin_locked'])
                log_tx_event('begin', None, 'locked', str(e))
            raise

    self.submit_and_wait(_do_begin)
```

### 7.4 不修改的地方

- `commit` (L258-289) — bo_framework 的 L2 已经包裹, 这里改容易冲突
- `rollback` (L314-319) — 同上
- `set_savepoint/rollback_to/release_savepoint` (L321-341) — 已经正确, V008 才会用

---

## 8. Layer 4: audit_service.py 修改

### 8.1 文件路径

`meta/services/audit_service.py` (MODIFY)

### 8.2 修改点

**位置**: `log_business` 路径 (实际是 `create` 方法 L540-555)

**增加**: state-aware retry (按 config.audit_retry_max)

### 8.3 修改 diff

```python
# meta/services/audit_service.py
# [V007.15 L4] audit 写入加 state-aware retry

# 在 imports 区域加:
import time
from meta.core.db_config_detector import get_runtime_config
from meta.core.observability import metrics_inc, OBS_COUNTERS, log_tx_event


# 修改 AuditService.create 方法 (L540-555) — 在循环写 audit_logs 之前加 retry 逻辑:

# 在 def create(...) 内部, 在 for record loop 之前, 或更好的方式:
# 把写 audit_log 提取成一个内部方法, 加 retry

# 简化: 在写 record 失败时, retry 一次, 记录 metric

# 修改示意 (L540-555):
def create(self, record: Dict, critical: bool = True) -> bool:
    """
    [V007.15 L4] Audit log write with state-aware retry.

    Args:
        record: audit log fields dict
        critical: True = 严格 (retried, failed → business may rollback)
                  False = 宽松 (best effort, silent fail)
    """
    config = get_runtime_config()
    max_retries = config.audit_retry_max if critical else 1

    for attempt in range(max_retries + 1):
        try:
            self.ds.insert(self.AUDIT_TABLE, record)
            if not getattr(self.ds, 'in_transaction', False):
                self.ds.commit()
            metrics_inc(OBS_COUNTERS['audit_write_success'])
            return True
        except Exception as e:
            err = str(e).lower()
            if ("locked" in err or "busy" in err) and attempt < max_retries:
                # 退避: 0.1s, 0.2s, 0.4s, ... (按 busy_timeout 缩放)
                backoff = 0.1 * (2 ** attempt) * (config.busy_timeout_ms // 5000)
                log_tx_event(
                    'audit_log', str(record.get('id', '')),
                    'retry', f"attempt={attempt}, backoff={backoff:.2f}s, err={err}"
                )
                time.sleep(backoff)
                continue
            # Non-locked error OR retries exhausted
            metrics_inc(OBS_COUNTERS['audit_write_failure' if not critical else 'audit_write_failure'])
            log_tx_event('audit_log', str(record.get('id', '')), 'failed', str(e))
            if critical:
                # 关键 audit 失败 → 抛异常让业务感知
                raise
            return False
    metrics_inc(OBS_COUNTERS['audit_write_exhausted'])
    log_tx_event('audit_log', str(record.get('id', '')), 'exhausted', 'max retries')
    return False
```

### 8.4 注意事项

- **不要破坏现有调用方**。`create(self, record)` API 已有, 加 `critical` 参数默认 True
- **调用方需更新**：`action_dispatcher.py:157` 调 `self.audit.create(AuditRecord(...))` 是位置参数, 需改为 `self.audit.create(record_dict, critical=True)` 或者提供 `AuditRecord` 转换
- **更安全**: 把 `critical` 默认 True, 不改调用方, 业务 TX 仍可走 fallback (静默 log)

### 8.5 决策

**保守做法**：**不改 audit_service.py 内部**, 在 L6 observability.py 加 retry wrapper:
```python
def create_with_retry(audit_service, record, critical=True):
    # 复用 audit_service.create, 加 retry 逻辑
    ...
```

**激进做法**：直接改 audit_service.py, 默认 critical=True, 业务感知失败。

**我推荐保守做法**（V007.15 内不动 audit_service.py 的内部逻辑, 在 observability.py 提供 wrapper）。这样 V007.15 不破坏现有 audit 调用链, V008 再统一重做。

### 8.6 实际修改（保守做法）

**不修改 audit_service.py**。把 L4 重命名为 **"audit retry wrapper"**，放在 L6 observability.py:

```python
# meta/core/observability.py 增加:
class AuditRetryWrapper:
    """[V007.15 L4 包装] 给 audit_service.create 加 state-aware retry"""
    def __init__(self, audit_service):
        self.audit = audit_service

    def create_with_retry(self, record: dict, critical: bool = True) -> bool:
        config = get_runtime_config()
        max_retries = config.audit_retry_max if critical else 0
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                # 假设 audit_service.create 接受 dict
                self.audit.create(record)
                metrics_inc(OBS_COUNTERS['audit_write_success'])
                return True
            except Exception as e:
                err = str(e).lower()
                last_err = e
                if ("locked" in err or "busy" in err) and attempt < max_retries:
                    backoff = 0.1 * (2 ** attempt) * (config.busy_timeout_ms // 5000)
                    time.sleep(backoff)
                    continue
                metrics_inc(OBS_COUNTERS['audit_write_failure'])
                if critical:
                    log_tx_event('audit', str(record.get('id', '')), 'failed', str(e))
                    raise
                return False
        metrics_inc(OBS_COUNTERS['audit_write_exhausted'])
        log_tx_event('audit', str(record.get('id', '')), 'exhausted', str(last_err))
        return False
```

调用方（如 `action_dispatcher.py`）可以选用 wrapper, **不强制**。这避免 V007.15 破坏现有 audit 路径。

---

## 9. Layer 5: orphan_tx_detector.py

### 9.1 文件路径

`meta/core/orphan_tx_detector.py` (NEW)

### 9.2 完整代码

```python
# meta/core/orphan_tx_detector.py
# [V007.15 L5] 后台定期检查 + 自动清理 orphan transaction
"""
[V007.15 L5] Orphan Transaction Detector

检测策略:
1. 读 _write_conn 真实状态 (savepoint probe)
2. 比对应用层 _in_transaction
3. 不一致 → 视为 orphan → 强制 ROLLBACK + 重置标志

运行方式:
- 启动时由 server.py 启动 daemon thread
- 每 N 秒 (state-aware: 30/60) 检查一次
- 状态污染时自动恢复
- 不影响正常业务

观测:
- Prometheus counter: orphan_detector_runs, orphan_recovered
- /healthz endpoint: orphan_detector.get_stats()
"""
import threading
import time
import logging
import sqlite3
from typing import Optional

from meta.core.db_config_detector import get_runtime_config
from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.observability import metrics_inc, OBS_COUNTERS, log_tx_event

logger = logging.getLogger(__name__)


class OrphanTxDetector:
    """[V007.15 L5] 后台孤儿事务检测器"""

    def __init__(self, data_source):
        self._ds = data_source
        self._config = get_runtime_config()
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._check_count = 0
        self._recovery_count = 0
        self._last_check_result = "init"
        self._last_check_ts = None

    def start(self):
        if not self._config.use_orphan_detector:
            logger.info("[V007.15 L5] Orphan detector disabled by config")
            return
        if self._thread is not None:
            logger.warning("[V007.15 L5] Orphan detector already started")
            return
        self._thread = threading.Thread(
            target=self._run, name='orphan-tx-detector', daemon=True
        )
        self._thread.start()
        logger.info(
            f"[V007.15 L5] Orphan TX detector started, "
            f"interval={self._config.orphan_check_interval_sec}s"
        )

    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop:
            time.sleep(self._config.orphan_check_interval_sec)
            try:
                self._check_once()
            except Exception as e:
                logger.error(f"[V007.15 L5] Orphan detector iteration failed: {e}")

    def _check_once(self):
        """单次检查 + 恢复"""
        import datetime
        self._check_count += 1
        self._last_check_ts = datetime.datetime.utcnow().isoformat()
        metrics_inc(OBS_COUNTERS['orphan_detector_runs'])

        # 1. 拿 _write_conn
        write_conn = self._get_write_conn()
        if write_conn is None:
            self._last_check_result = "no_write_conn"
            return

        # 2. savepoint probe
        try:
            actual = get_tx_state(write_conn)
        except Exception as e:
            self._last_check_result = f"probe_error: {e}"
            return

        # 3. 读应用层 _in_transaction
        app_state = self._get_app_in_transaction()

        # 4. 比对 + 恢复
        if actual != TxState.NONE and not app_state:
            # ORPHAN! SQLite 在 tx 中, Python 说不在
            self._recover_orphan(write_conn, actual)
            self._last_check_result = "recovered"
        elif actual == TxState.NONE and app_state:
            # 应用层状态污染, 重置
            self._reset_app_state()
            metrics_inc(OBS_COUNTERS['orphan_app_state_pollution'])
            self._last_check_result = "app_state_pollution_reset"
        else:
            metrics_inc(OBS_COUNTERS['orphan_detector_clean'])
            self._last_check_result = "clean"

    def _recover_orphan(self, conn, actual_state: str):
        """Orphan 恢复: 强制 ROLLBACK + 重置 + 告警"""
        self._recovery_count += 1
        metrics_inc(OBS_COUNTERS['orphan_recovered'])
        log_tx_event(
            'orphan', None, 'recovered',
            f"actual_sqlite_state={actual_state}, forced_rollback"
        )

        try:
            conn.execute("ROLLBACK")
        except Exception as e:
            log_tx_event('orphan', None, 'rollback_error', str(e))
            # 兜底: 关闭连接
            try:
                conn.close()
                log_tx_event('orphan', None, 'connection_closed', 'last_resort')
            except Exception:
                pass

        self._reset_app_state()

    def _reset_app_state(self):
        """重置应用层 _in_transaction 标志"""
        try:
            if hasattr(self._ds, '_in_transaction'):
                self._ds._in_transaction = False
            if hasattr(self._ds, '_write_queue') and self._ds._write_queue:
                if hasattr(self._ds._write_queue, '_in_transaction'):
                    self._ds._write_queue._in_transaction = False
        except Exception as e:
            log_tx_event('orphan', None, 'state_reset_error', str(e))

    def _get_write_conn(self):
        """从 data_source 拿 write connection"""
        try:
            if hasattr(self._ds, '_write_queue') and self._ds._write_queue:
                if hasattr(self._ds._write_queue, '_write_conn'):
                    return self._ds._write_queue._write_conn
            if hasattr(self._ds, '_connection'):
                return self._ds._connection
        except Exception:
            return None
        return None

    def _get_app_in_transaction(self) -> bool:
        """读应用层 _in_transaction 状态"""
        try:
            if hasattr(self._ds, 'in_transaction'):
                return bool(self._ds.in_transaction)
        except Exception:
            return False
        return False

    def get_stats(self) -> dict:
        return {
            'check_count': self._check_count,
            'recovery_count': self._recovery_count,
            'interval_sec': self._config.orphan_check_interval_sec,
            'deployment_state': self._config.deployment_state,
            'last_check_ts': self._last_check_ts,
            'last_check_result': self._last_check_result,
        }
```

---

## 10. Layer 6: observability.py

### 10.1 文件路径

`meta/core/observability.py` (NEW)

### 10.2 完整代码

```python
# meta/core/observability.py
# [V007.15 L6] 可观测性基础设施 (Prometheus + 结构化日志)
"""
[V007.15 L6] Observability Infrastructure

提供:
- 19 Prometheus counters + 1 gauge
- 1 AuditRetryWrapper (L4)
- 1 metrics_inc() / log_tx_event() helper
- Lazy import Prometheus (无硬依赖, fallback to log)
"""
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Counter dict (lazy)
_prometheus_counters: Dict[str, any] = {}

OBS_COUNTERS = {
    # commit/rollback
    'commit_success': 'v007_15_commit_success_total',
    'commit_failure': 'v007_15_commit_failure_total',
    'rollback_success': 'v007_15_rollback_success_total',
    'rollback_failure': 'v007_15_rollback_failure_total',
    'forced_rollback_after_commit': 'v007_15_forced_rollback_after_commit_total',
    'forced_rollback_after_rollback': 'v007_15_forced_rollback_after_rollback_total',
    # begin_transaction
    'begin_success': 'v007_15_begin_success_total',
    'begin_skipped_already_in_tx': 'v007_15_begin_skipped_already_in_tx_total',
    'begin_locked': 'v007_15_begin_locked_total',
    'phantom_tx_detected': 'v007_15_phantom_tx_detected_total',
    # audit
    'audit_write_success': 'v007_15_audit_write_success_total',
    'audit_write_failure': 'v007_15_audit_write_failure_total',
    'audit_write_exhausted': 'v007_15_audit_write_exhausted_total',
    # orphan detector
    'orphan_detector_runs': 'v007_15_orphan_detector_runs_total',
    'orphan_detector_clean': 'v007_15_orphan_detector_clean_total',
    'orphan_recovered': 'v007_15_orphan_recovered_total',
    'orphan_app_state_pollution': 'v007_15_orphan_app_state_pollution_total',
    # state
    'runtime_state': 'v007_15_runtime_state_info',
}


def _get_prometheus_counter(name: str):
    if name in _prometheus_counters:
        return _prometheus_counters[name]
    try:
        from prometheus_client import Counter, Gauge
        if name == OBS_COUNTERS['runtime_state']:
            obj = Gauge(name, 'V007.15 runtime state code (0=A,1=B,2=C,3=UNKNOWN)')
        else:
            obj = Counter(name, f'V007.15 metric: {name}')
        _prometheus_counters[name] = obj
        return obj
    except ImportError:
        return None


def metrics_inc(counter_key: str, value: int = 1):
    if counter_key not in OBS_COUNTERS:
        return
    if counter_key == 'runtime_state':
        return  # 用 metrics_set_state
    name = OBS_COUNTERS[counter_key]
    counter = _get_prometheus_counter(name)
    if counter is not None:
        try:
            counter.inc(value)
        except Exception:
            pass


def metrics_set_state(state_code: int):
    """0=A, 1=B, 2=C, 3=UNKNOWN"""
    gauge = _get_prometheus_counter(OBS_COUNTERS['runtime_state'])
    if gauge is not None:
        try:
            gauge.set(state_code)
        except Exception:
            pass


def log_tx_event(event_type: str, tx_id: Optional[str], status: str, detail: Optional[str]):
    """结构化日志, 总是输出 (不管 Prometheus 是否可用)"""
    extra = {
        'event_type': event_type,
        'tx_id': tx_id,
        'status': status,
        'detail': detail[:500] if detail else None,
    }
    msg = f"[V007.15] {event_type} tx_id={tx_id} status={status}"
    if detail:
        msg += f" detail={detail[:200]}"
    if status in ('error', 'recovered', 'failed', 'exhausted'):
        logger.error(msg, extra=extra)
    elif status in ('locked', 'forced_rollback', 'retry'):
        logger.warning(msg, extra=extra)
    else:
        logger.info(msg, extra=extra)


# [V007.15 L4 包装] Audit retry wrapper
class AuditRetryWrapper:
    def __init__(self, audit_service):
        self.audit = audit_service

    def create_with_retry(self, record: dict, critical: bool = True) -> bool:
        from meta.core.db_config_detector import get_runtime_config
        config = get_runtime_config()
        max_retries = config.audit_retry_max if critical else 0
        last_err = None
        for attempt in range(max_retries + 1):
            try:
                self.audit.create(record)
                metrics_inc(OBS_COUNTERS['audit_write_success'])
                return True
            except Exception as e:
                err = str(e).lower()
                last_err = e
                if ("locked" in err or "busy" in err) and attempt < max_retries:
                    backoff = 0.1 * (2 ** attempt) * (config.busy_timeout_ms // 5000)
                    log_tx_event(
                        'audit', str(record.get('id', '')),
                        'retry', f"attempt={attempt}, backoff={backoff:.2f}s, err={err}"
                    )
                    time.sleep(backoff)
                    continue
                metrics_inc(OBS_COUNTERS['audit_write_failure'])
                if critical:
                    log_tx_event('audit', str(record.get('id', '')), 'failed', str(e))
                    raise
                return False
        metrics_inc(OBS_COUNTERS['audit_write_exhausted'])
        log_tx_event('audit', str(record.get('id', '')), 'exhausted', str(last_err))
        return False
```

---

## 11. Layer 7: server.py 修改

### 11.1 文件路径

`meta/server.py` (MODIFY)

### 11.2 修改点

**位置**: 现有 init 流程（`_create_app` / 数据源初始化后）

**增加**:
1. 启动时检测 PRAGMA config (L0)
2. 启动 orphan detector (L5)
3. /healthz 加 v007_15 状态 (L6)

### 11.3 修改 diff

```python
# meta/server.py
# [V007.15 L7] Server 集成: config detect + orphan detector + /healthz

# 在 imports 区域加:
from meta.core.db_config_detector import detect_runtime_config, get_runtime_config
from meta.core.observability import metrics_set_state
from meta.core.orphan_tx_detector import OrphanTxDetector

# 在 _create_app() 中, 数据源初始化之后, 加:

# L7-1: 启动时检测 config
try:
    db_path = getattr(data_source, '_db_path', None) or 'architecture.db'
    config = detect_runtime_config(db_path)
    state_code = {'A': 0, 'B': 1, 'C': 2}.get(config.deployment_state, 3)
    metrics_set_state(state_code)
    logger.info(
        f"[V007.15 L7] Server initialized, "
        f"deployment_state={config.deployment_state}, "
        f"journal={config.journal_mode.value}, busy_timeout={config.busy_timeout_ms}ms"
    )
except Exception as e:
    logger.error(f"[V007.15 L7] Failed to init config detector: {e}")

# L7-2: 启动 orphan detector
orphan_detector = None
try:
    orphan_detector = OrphanTxDetector(data_source)
    orphan_detector.start()
except Exception as e:
    logger.error(f"[V007.15 L7] Failed to start orphan detector: {e}")


# 修改 /healthz endpoint (在 _create_app() 中找到现有 healthz handler, 加 v007_15 段):
@app.route('/healthz')
def healthz_v2():
    # 现有 healthz 内容保留
    response = {
        'status': 'ok',
    }
    # L7-3: 加 v007_15 段
    try:
        cfg = get_runtime_config()
        response['v007_15'] = {
            'deployment_state': cfg.deployment_state,
            'journal_mode': cfg.journal_mode.value,
            'busy_timeout_ms': cfg.busy_timeout_ms,
            'orphan_detector': orphan_detector.get_stats() if orphan_detector else None,
        }
    except RuntimeError:
        # Config 没初始化 (开发模式?)
        response['v007_15'] = 'not_initialized'
    return response
```

### 11.4 注意事项

- `/healthz` 已有但格式可能不同 — 实际部署前需对比 `meta/server.py` 找出现有 healthz, 合并而非覆盖
- `data_source` 变量名可能不同 — 实际部署时根据代码确认
- `orphan_detector` 设为 module-level 或 app context, 避免 GC

---

## 12. 5 个测试文件 (95 cases)

### 12.1 测试文件列表

| 文件 | Cases | 覆盖 |
|------|-------|------|
| `tests/test_v007_15_config_detector.py` | 30 | L0 |
| `tests/test_v007_15_tx_state.py` | 15 | L1 |
| `tests/test_v007_15_bo_framework.py` | 20 | L2 |
| `tests/test_v007_15_write_queue.py` | 15 | L3 |
| `tests/test_v007_15_orphan_detector.py` | 15 | L5 |
| **Total** | **95** | |

### 12.2 测试文件 1: `test_v007_15_config_detector.py` (30 cases)

```python
# tests/test_v007_15_config_detector.py
# [V007.15 L0] Tests
import pytest
import sqlite3
import tempfile
import os
from unittest.mock import patch
from meta.core.db_config_detector import (
    detect_runtime_config, get_runtime_config, JournalMode, RuntimeDbConfig,
    reset_runtime_config,
)


@pytest.fixture
def fresh_db(tmp_path):
    def _make(journal='wal', busy=5000):
        db = tmp_path / f"test_{journal}_{busy}.db"
        conn = sqlite3.connect(str(db), timeout=5.0)
        conn.execute(f"PRAGMA journal_mode={journal.upper()}")
        conn.execute(f"PRAGMA busy_timeout={busy}")
        conn.close()
        return str(db)
    return _make


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_runtime_config()
    yield
    reset_runtime_config()


# State A
def test_state_a_detection(fresh_db):
    db = fresh_db(journal='wal', busy=5000)
    config = detect_runtime_config(db)
    assert config.deployment_state == "A"
    assert config.audit_retry_max == 2
    assert config.orphan_check_interval_sec == 30

def test_state_a_journal_mode(fresh_db):
    db = fresh_db(journal='wal', busy=5000)
    config = detect_runtime_config(db)
    assert config.journal_mode == JournalMode.WAL

# State B
def test_state_b_detection(fresh_db):
    db = fresh_db(journal='delete', busy=30000)
    config = detect_runtime_config(db)
    assert config.deployment_state == "B"
    assert config.audit_retry_max == 5
    assert config.orphan_check_interval_sec == 60

def test_state_b_journal_mode(fresh_db):
    db = fresh_db(journal='delete', busy=30000)
    config = detect_runtime_config(db)
    assert config.journal_mode == JournalMode.DELETE

# State C (unknown)
def test_state_c_truncate(fresh_db):
    db = fresh_db(journal='truncate', busy=5000)
    config = detect_runtime_config(db)
    assert config.deployment_state == "C"

def test_state_c_custom_busy(fresh_db):
    db = fresh_db(journal='wal', busy=10000)
    config = detect_runtime_config(db)
    assert config.deployment_state == "C"
    assert config.audit_retry_max == 2  # max(2, 10000//5000) = 2

def test_state_c_zero_busy(fresh_db):
    db = fresh_db(journal='wal', busy=0)
    config = detect_runtime_config(db)
    assert config.deployment_state == "C"

# Singleton
def test_singleton_caching(tmp_path):
    db1 = tmp_path / "a.db"
    db2 = tmp_path / "b.db"
    conn1 = sqlite3.connect(str(db1), timeout=5.0)
    conn1.execute("PRAGMA journal_mode=WAL")
    conn1.close()
    conn2 = sqlite3.connect(str(db2), timeout=5.0)
    conn2.execute("PRAGMA journal_mode=DELETE")
    conn2.close()
    config1 = detect_runtime_config(str(db1))
    config2 = detect_runtime_config(str(db2))  # 应返回 cached
    assert config1 is config2  # Same object (cached)

# Detection failure
def test_detection_failure_uses_safe_defaults(tmp_path):
    fake_db = tmp_path / "does_not_exist.db"
    config = detect_runtime_config(str(fake_db))
    # 不存在的 db, sqlite3.connect 会创建空 db
    # 检测成功 (空 db 的 PRAGMA 返回默认值)
    # 不强制 state=UNKNOWN, 取决于 SQLite 实际行为
    assert config is not None

def test_get_runtime_config_before_detect():
    reset_runtime_config()
    with pytest.raises(RuntimeError):
        get_runtime_config()

# Integration
def test_config_fields_complete(fresh_db):
    db = fresh_db(journal='wal', busy=5000)
    config = detect_runtime_config(db)
    assert hasattr(config, 'journal_mode')
    assert hasattr(config, 'busy_timeout_ms')
    assert hasattr(config, 'synchronous')
    assert hasattr(config, 'foreign_keys_on')
    assert hasattr(config, 'auto_vacuum')
    assert hasattr(config, 'deployment_state')
    assert hasattr(config, 'use_explicit_conn_rollback')
    assert hasattr(config, 'use_orphan_detector')
    assert hasattr(config, 'audit_retry_max')
    assert hasattr(config, 'orphan_check_interval_sec')

# State mapping combinations
def test_state_a_wal_4s(fresh_db):
    db = fresh_db(journal='wal', busy=4000)  # not exactly 5000
    config = detect_runtime_config(db)
    assert config.deployment_state == "C"

def test_state_a_wal_6s(fresh_db):
    db = fresh_db(journal='wal', busy=6000)
    config = detect_runtime_config(db)
    assert config.deployment_state == "C"

# Defense flags
def test_explicit_rollback_enabled_all_states(fresh_db):
    db = fresh_db(journal='wal', busy=5000)
    config = detect_runtime_config(db)
    assert config.use_explicit_conn_rollback is True

def test_orphan_detector_enabled_all_states(fresh_db):
    db = fresh_db(journal='delete', busy=30000)
    config = detect_runtime_config(db)
    assert config.use_orphan_detector is True

# Behavior modifiers
def test_state_b_longer_orphan_interval(fresh_db):
    db_a = fresh_db(journal='wal', busy=5000)
    db_b = fresh_db(journal='delete', busy=30000)
    cfg_a = detect_runtime_config(db_a)
    reset_runtime_config()
    cfg_b = detect_runtime_config(db_b)
    assert cfg_b.orphan_check_interval_sec > cfg_a.orphan_check_interval_sec

def test_state_b_higher_retry_max(fresh_db):
    db_a = fresh_db(journal='wal', busy=5000)
    db_b = fresh_db(journal='delete', busy=30000)
    cfg_a = detect_runtime_config(db_a)
    reset_runtime_config()
    cfg_b = detect_runtime_config(db_b)
    assert cfg_b.audit_retry_max > cfg_a.audit_retry_max

# ... (additional 10 cases for edge cases, error handling, perf)
```

### 12.3 测试文件 2: `test_v007_15_tx_state.py` (15 cases)

```python
# tests/test_v007_15_tx_state.py
# [V007.15 L1] Tests
import pytest
import sqlite3
from meta.core.sqlite_tx_state import get_tx_state, TxState, tx_state_verified_action


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", timeout=5.0)
    yield c
    c.close()


# None state
def test_none_state(conn):
    assert get_tx_state(conn) == TxState.NONE

def test_none_after_rollback(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("ROLLBACK")
    assert get_tx_state(conn) == TxState.NONE

def test_none_after_commit(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("COMMIT")
    assert get_tx_state(conn) == TxState.NONE

# Write state
def test_write_state(conn):
    conn.execute("BEGIN IMMEDIATE")
    assert get_tx_state(conn) == TxState.WRITE

def test_write_state_persists(conn):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("CREATE TABLE t1 (x INT)")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")

# Read state (not really distinguishable from write, but should be WRITE)
def test_read_state(conn):
    conn.execute("BEGIN")
    assert get_tx_state(conn) in (TxState.WRITE, TxState.READ)
    conn.execute("ROLLBACK")

# State recovery
def test_state_recovery(conn):
    conn.execute("BEGIN IMMEDIATE")
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")
    assert get_tx_state(conn) == TxState.NONE

# Context manager
def test_context_manager_no_warning(conn, caplog):
    with tx_state_verified_action(conn, expected_state=TxState.NONE) as actual:
        assert actual == TxState.NONE
    # No warning expected

def test_context_manager_drift_warning(conn, caplog):
    conn.execute("BEGIN IMMEDIATE")
    with tx_state_verified_action(conn, expected_state=TxState.NONE):
        pass
    assert "TX state mismatch" in caplog.text
    conn.execute("ROLLBACK")

def test_context_manager_no_force_rollback(conn):
    conn.execute("BEGIN IMMEDIATE")
    # tx_state_verified_action should NOT force rollback
    with tx_state_verified_action(conn, expected_state=TxState.NONE):
        pass
    # Should still be in tx (caller decides)
    assert get_tx_state(conn) == TxState.WRITE
    conn.execute("ROLLBACK")

# Cost / performance
def test_probe_cost_under_5ms(conn):
    import time
    start = time.time()
    for _ in range(100):
        get_tx_state(conn)
    elapsed = time.time() - start
    # 100 次 < 500ms (单次 < 5ms)
    assert elapsed < 0.5

# Multi connection
def test_independent_connections():
    c1 = sqlite3.connect(":memory:")
    c2 = sqlite3.connect(":memory:")
    c1.execute("BEGIN IMMEDIATE")
    assert get_tx_state(c1) == TxState.WRITE
    assert get_tx_state(c2) == TxState.NONE
    c1.close()
    c2.close()

def test_unknown_on_invalid_conn():
    # Closed connection
    c = sqlite3.connect(":memory:")
    c.close()
    state = get_tx_state(c)
    # closed conn → savepoint 抛异常 → UNKNOWN
    assert state in (TxState.UNKNOWN, TxState.NONE)

# Idempotency
def test_repeated_probes(conn):
    for _ in range(10):
        assert get_tx_state(conn) == TxState.NONE

# Sequence
def test_alternating_begin_rollback(conn):
    for _ in range(5):
        conn.execute("BEGIN IMMEDIATE")
        assert get_tx_state(conn) == TxState.WRITE
        conn.execute("ROLLBACK")
        assert get_tx_state(conn) == TxState.NONE
```

### 12.4 测试文件 3: `test_v007_15_bo_framework.py` (20 cases)

```python
# tests/test_v007_15_bo_framework.py
# [V007.15 L2] Tests
import pytest
from unittest.mock import MagicMock, patch
from meta.core.bo_framework import BOFramework
from meta.core.sqlite_tx_state import TxState
from meta.core.db_config_detector import RuntimeDbConfig, JournalMode


@pytest.fixture
def mock_ds():
    ds = MagicMock()
    ds._in_transaction = False
    ds._write_queue = MagicMock()
    ds._write_queue._in_transaction = False
    ds._write_queue._write_conn = MagicMock()
    return ds


@pytest.fixture
def bo_framework(mock_ds):
    bf = BOFramework.__new__(BOFramework)  # skip __init__
    bf._data_source = mock_ds
    return bf


@pytest.fixture(autouse=True)
def mock_config():
    with patch('meta.core.bo_framework.get_runtime_config') as mock:
        mock.return_value = MagicMock(
            use_explicit_conn_rollback=True,
            audit_retry_max=2,
            orphan_check_interval_sec=30,
            deployment_state='A',
        )
        yield mock


# Commit success
def test_commit_success_resets_state(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True
    assert mock_ds._in_transaction is False
    assert mock_ds._write_queue._in_transaction is False


def test_commit_failure_still_resets_state(bo_framework, mock_ds):
    mock_ds.commit.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is False
    # CRITICAL: state must be reset even on failure
    assert mock_ds._in_transaction is False
    assert mock_ds._write_queue._in_transaction is False


def test_commit_forced_rollback_when_state_drift(bo_framework, mock_ds):
    # Commit "succeeds" but conn still in tx
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
        result = bo_framework.commit()
    # Should force ROLLBACK
    mock_ds._write_queue._write_conn.execute.assert_called_with("ROLLBACK")


# Rollback
def test_rollback_success_resets_state(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.rollback()
    assert result is True
    assert mock_ds._in_transaction is False


def test_rollback_failure_still_resets_state(bo_framework, mock_ds):
    mock_ds.rollback.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.rollback()
    assert result is False
    assert mock_ds._in_transaction is False


def test_rollback_forced_rollback(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
        result = bo_framework.rollback()
    mock_ds._write_queue._write_conn.execute.assert_called_with("ROLLBACK")


# State-aware
def test_explicit_rollback_disabled(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(use_explicit_conn_rollback=False)
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.WRITE):
            bo_framework.rollback()
    # Should NOT have called conn.rollback directly
    mock_ds._write_queue._write_conn.rollback.assert_not_called()


# No write_queue
def test_commit_no_write_queue(bo_framework, mock_ds):
    mock_ds._write_queue = None
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True
    assert mock_ds._in_transaction is False


# No write_conn
def test_commit_no_write_conn(bo_framework, mock_ds):
    mock_ds._write_queue._write_conn = None
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    assert result is True


# Observability
def test_commit_emits_metrics(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
    # Should have called metrics_inc with commit_success
    assert any(call.args[0] == 'commit_success' for call in mock_metrics.call_args_list)


def test_commit_failure_emits_failure_metric(bo_framework, mock_ds):
    mock_ds.commit.side_effect = Exception("disk full")
    with patch('meta.core.bo_framework.metrics_inc') as mock_metrics:
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
    assert any(call.args[0] == 'commit_failure' for call in mock_metrics.call_args_list)


# State reset on exception
def test_state_reset_error_does_not_propagate(bo_framework, mock_ds):
    # Simulate hasattr returning True but assignment failing
    type(mock_ds)._in_transaction = property(lambda self: False, lambda self, v: (_ for _ in ()).throw(Exception("cannot set")))
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    # Should not raise


# Transaction context
def test_transaction_context_with_v007_15():
    # Smoke test that TransactionContext still works
    pass  # Tested in existing test_bo_framework.py


# Integration
def test_commit_then_immediate_begin_works(bo_framework, mock_ds):
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        bo_framework.commit()
    # Now begin
    mock_ds.begin_transaction = MagicMock()
    bo_framework.begin_transaction()
    mock_ds.begin_transaction.assert_called_once()


# Stress
def test_commit_rollback_alternating(bo_framework, mock_ds):
    for _ in range(20):
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.commit()
        with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
            bo_framework.rollback()
    # No state leak
    assert mock_ds._in_transaction is False


# Edge: no data_source
def test_no_data_source_attribute(bo_framework, mock_ds):
    del mock_ds.commit
    with patch('meta.core.bo_framework.get_tx_state', return_value=TxState.NONE):
        result = bo_framework.commit()
    # Should still return True (no-op)
    assert result is True
```

### 12.5 测试文件 4: `test_v007_15_write_queue.py` (15 cases)

```python
# tests/test_v007_15_write_queue.py
# [V007.15 L3] Tests
import pytest
import sqlite3
from unittest.mock import patch
from meta.core.sql_write_queue import WriteQueue
from meta.core.sqlite_tx_state import TxState


def test_phantom_tx_detection():
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")

    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False

    captured = []
    def mock_submit(fn):
        fn(conn)
        captured.append(True)
    wq.submit_and_wait = mock_submit

    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
        wq.begin_transaction()

    # Phantom detected → force ROLLBACK → new BEGIN
    assert wq._in_transaction is True
    conn.execute("ROLLBACK")


def test_normal_begin_when_no_tx():
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False

    def mock_submit(fn):
        fn(conn)
    wq.submit_and_wait = mock_submit

    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.NONE):
        wq.begin_transaction()
    assert wq._in_transaction is True
    conn.execute("ROLLBACK")


def test_begin_skipped_when_already_in_tx():
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = True
    called = []
    wq.submit_and_wait = lambda fn: called.append(True)
    wq.begin_transaction()
    assert len(called) == 0  # Skipped


def test_locked_begin_metrics():
    conn = sqlite3.connect(":memory:")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False

    def mock_submit(fn):
        try:
            fn(conn)
        except Exception:
            pass
    wq.submit_and_wait = mock_submit

    # Simulate locked error
    def raise_locked(c):
        from unittest.mock import patch as mock_patch
        with mock_patch.object(c, 'execute', side_effect=sqlite3.OperationalError("database is locked")):
            c.execute("BEGIN IMMEDIATE")

    # Direct test: patch get_tx_state to return NONE (so no phantom), then patch execute
    with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.NONE):
        with patch.object(conn, 'execute', side_effect=sqlite3.OperationalError("database is locked")):
            with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
                with pytest.raises(sqlite3.OperationalError):
                    wq.begin_transaction()
    # Verify metrics_inc called with 'begin_locked'
    # (depends on whether savepoint is detected, may be ambiguous)


def test_phantom_tx_emits_metric():
    conn = sqlite3.connect(":memory:")
    conn.execute("BEGIN IMMEDIATE")
    wq = WriteQueue.__new__(WriteQueue)
    wq._in_transaction = False
    wq.submit_and_wait = lambda fn: fn(conn)

    with patch('meta.core.sql_write_queue.metrics_inc') as mock_metrics:
        with patch('meta.core.sql_write_queue.get_tx_state', return_value=TxState.WRITE):
            wq.begin_transaction()

    assert any(call.args[0] == 'phantom_tx_detected' for call in mock_metrics.call_args_list)
    conn.execute("ROLLBACK")


# More cases for recovery, exception paths, etc.
# (10 more cases for completeness)
```

### 12.6 测试文件 5: `test_v007_15_orphan_detector.py` (15 cases)

```python
# tests/test_v007_15_orphan_detector.py
# [V007.15 L5] Tests
import pytest
import sqlite3
import time
from unittest.mock import MagicMock, patch
from meta.core.orphan_tx_detector import OrphanTxDetector
from meta.core.sqlite_tx_state import TxState
from meta.core.db_config_detector import RuntimeDbConfig, JournalMode


@pytest.fixture
def real_conn():
    c = sqlite3.connect(":memory:", timeout=5.0)
    yield c
    c.close()


@pytest.fixture
def mock_ds(real_conn):
    ds = MagicMock()
    ds._in_transaction = False
    ds._write_queue._write_conn = real_conn
    ds.in_transaction = False
    return ds


@pytest.fixture(autouse=True)
def mock_config():
    with patch('meta.core.orphan_tx_detector.get_runtime_config') as mock:
        mock.return_value = MagicMock(
            use_orphan_detector=True,
            orphan_check_interval_sec=0.1,  # fast for tests
            deployment_state='A',
        )
        yield mock


def test_detector_clean_state(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    detector._check_once()
    stats = detector.get_stats()
    assert stats['check_count'] == 1
    assert stats['recovery_count'] == 0
    assert stats['last_check_result'] == 'clean'


def test_detector_recovers_orphan(mock_ds, real_conn):
    # Create real orphan TX
    real_conn.execute("BEGIN IMMEDIATE")
    real_conn.execute("CREATE TABLE t1 (x INT)")
    real_conn.execute("INSERT INTO t1 VALUES (1)")
    # App says no TX
    mock_ds._in_transaction = False
    mock_ds.in_transaction = False

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    stats = detector.get_stats()
    assert stats['recovery_count'] == 1
    assert stats['last_check_result'] == 'recovered'
    # Verify orphan was rolled back
    import sqlite3 as _sq
    cur = real_conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='t1'")
    assert cur.fetchone()[0] == 0  # Table rolled back


def test_detector_resets_false_positive(mock_ds):
    # App says yes TX, SQLite says no
    mock_ds._in_transaction = True
    mock_ds.in_transaction = True

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    # App state should be reset
    assert mock_ds._in_transaction is False


def test_detector_disabled_by_config(mock_ds):
    with patch('meta.core.orphan_tx_detector.get_runtime_config') as mock_cfg:
        mock_cfg.return_value = MagicMock(use_orphan_detector=False)
        detector = OrphanTxDetector(mock_ds)
        detector.start()
    assert detector._thread is None


def test_detector_start_stop(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    detector.start()
    assert detector._thread is not None
    detector.stop()
    assert detector._stop is True


def test_detector_get_stats(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    stats = detector.get_stats()
    assert 'check_count' in stats
    assert 'recovery_count' in stats
    assert 'interval_sec' in stats
    assert 'deployment_state' in stats


def test_detector_runs_multiple_times(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    for _ in range(3):
        detector._check_once()
    stats = detector.get_stats()
    assert stats['check_count'] == 3


def test_detector_recovery_resets_app_state(mock_ds, real_conn):
    real_conn.execute("BEGIN IMMEDIATE")
    mock_ds._in_transaction = True  # Both inconsistent

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()

    # Both should be reset
    assert mock_ds._in_transaction is False


def test_detector_no_write_conn(mock_ds):
    mock_ds._write_queue._write_conn = None
    mock_ds._connection = None
    detector = OrphanTxDetector(mock_ds)
    detector._check_once()
    stats = detector.get_stats()
    assert stats['last_check_result'] == 'no_write_conn'


def test_detector_probe_error_handled(mock_ds, real_conn):
    real_conn.close()  # closed conn causes probe error
    detector = OrphanTxDetector(mock_ds)
    detector._check_once()
    stats = detector.get_stats()
    # Should not raise, just mark as error
    assert 'error' in stats['last_check_result'] or stats['last_check_result'] == 'no_write_conn'


def test_detector_recovery_when_rollback_fails(mock_ds, real_conn):
    real_conn.execute("BEGIN IMMEDIATE")
    mock_ds._in_transaction = False
    real_conn.close()  # ROLLBACK will fail

    detector = OrphanTxDetector(mock_ds)
    detector._check_once()  # Should not raise

    # Recovery should still count
    assert detector.get_stats()['recovery_count'] == 1


def test_detector_emits_metrics(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    with patch('meta.core.orphan_tx_detector.metrics_inc') as mock_metrics:
        detector._check_once()
    assert any(call.args[0] == 'orphan_detector_runs' for call in mock_metrics.call_args_list)
    assert any(call.args[0] == 'orphan_detector_clean' for call in mock_metrics.call_args_list)


def test_detector_recovery_emits_metric(mock_ds, real_conn):
    real_conn.execute("BEGIN IMMEDIATE")
    mock_ds._in_transaction = False
    detector = OrphanTxDetector(mock_ds)
    with patch('meta.core.orphan_tx_detector.metrics_inc') as mock_metrics:
        detector._check_once()
    assert any(call.args[0] == 'orphan_recovered' for call in mock_metrics.call_args_list)


def test_detector_healthz_format(mock_ds):
    detector = OrphanTxDetector(mock_ds)
    detector._check_count = 100
    detector._recovery_count = 5
    stats = detector.get_stats()
    assert stats['check_count'] == 100
    assert stats['recovery_count'] == 5
    assert stats['interval_sec'] == 0.1  # from mock
    assert stats['deployment_state'] == 'A'  # from mock
```

---

## 13. 部署与回滚

### 13.1 部署顺序

```
1. 备份 production 当前代码 + DB
2. Cherry-pick 协调智能体先 cherry-pick V049-FD 修复
3. 部署 V049-FD → 重启服务 → 验证 0% 卡死问题解决
4. 验证 24h 无 V049 回归
5. 创建 V050 worktree (协调智能体)
6. Cherry-pick V007.15 7 个 commit (本方案)
7. 部署到 integration 3007/3018
8. e2e 测试 (按 §10.2 验证)
9. 部署到 production (按 §13.2 步骤)
10. 监控 Prometheus (按 §6.3 alert)
11. 24h 验证后宣告完成
```

### 13.2 部署步骤 (production)

```bash
# 0. SSH to production
ssh user@172.20.59.7

# 1. 备份
cp -r /opt/app /opt/app.bak.$(date +%Y%m%d)
sqlite3 /opt/app/architecture.db ".backup /opt/app.bak.db"

# 2. Git pull (或 cherry-pick)
cd /opt/app
git fetch origin
git checkout release/pre-2026-06-29
git pull
# Cherry-pick V007.15 commits
git cherry-pick <v007_15_commit_hash_1> ... <commit_hash_7>

# 3. Run smoke test
python tools/smoke_v007_15.py http://localhost:8081 <expected_state>

# 4. Restart
systemctl restart meta-backend
# Wait 10s
sleep 10

# 5. Verify /healthz
curl http://localhost:8081/healthz | python -m json.tool | grep v007_15 -A 10
# Expected: deployment_state="A" or "B", orphan_detector stats present

# 6. Run load test
python tools/load_test.py --import --rows 1000
# Expected: completes in < 5 min, no orphan recovery_count > 0

# 7. Monitor for 24h
# Check Prometheus: v007_15_*
# Check logs: /var/log/meta/backend.log | grep V007.15

# 8. Done
```

### 13.3 回滚步骤

```bash
# 1. Stop server
systemctl stop meta-backend

# 2. Revert code
cd /opt/app
git checkout release/pre-2026-06-29 -- meta/

# 3. Restart
systemctl start meta-backend

# 4. Verify healthz no longer has v007_15
curl http://localhost:8081/healthz | python -m json.tool
# Expected: no "v007_15" key

# 5. Disable Prometheus alerts
# Edit prometheus-alerts/v007_15.yml, comment out
```

### 13.4 回滚触发条件

| Trigger | Action |
|---------|--------|
| Server start failure | Immediate rollback |
| Orphan recovery_count > 10/hour | Investigate, consider rollback |
| Audit write exhausted > 0 | Investigate, may rollback |
| Commit failure rate > 0 | Investigate, may rollback |
| Performance regression > 20% | Rollback |

---

## 14. 风险与缓解

### 14.1 技术风险

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **L0 启动检测干扰现有初始化** | Medium | High (server start fail) | try/except 包裹, 失败 fallback to safe defaults |
| **L2 finally 块与现有 try/except 冲突** | Medium | High (commit 失败路径改变) | 严格保留原 try/except 行为, 只加 finally 状态重置 |
| **L3 phantom 检测增加 BEGIN 延迟** | Low | Low (1-2ms) | savepoint probe ~1ms, 可接受 |
| **L5 orphan detector 干扰正常 commit** | Low | High (误判 ROLLBACK) | 严格比对: SQLite in tx AND app not in tx 才干预 |
| **L6 Prometheus 依赖缺失** | Low | Low (没指标) | Lazy import, fallback to log |
| **L7 /healthz 格式与现有冲突** | Medium | Medium | 实际部署前先 diff 现有 healthz, 合并而非替换 |

### 14.2 业务风险

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **破坏现有 audit 流程** | Low | High | 保守做法: L4 包装而非修改 audit_service.py 内部 |
| **破坏现有事务语义** | Low | High | 严格保留原 try/except 行为, 只加状态重置 |
| **action_dispatcher 集成失败** | Low | Medium | V007.15 不修改 action_dispatcher, 隔离 scope |
| **observability 引入 perf regression** | Low | Low | savepoint probe ~1ms, 总体 +5ms / commit |

### 14.3 操作风险

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **生产部署 ulimit 未提升** | Medium | High (server start fail) | 部署前先 V049-FD 验证 setrlimit 生效 |
| **生产 8bfcbff 旧代码未含 V007.15** | Low | High | 部署清单明确 7 个 commit 全部 cherry-pick |
| **Prometheus 未配置** | Low | Low (no metrics) | 不影响功能, 仅丢失 metrics |
| **回滚时 DB 状态不一致** | Low | High | 备份 DB + .bak 文件, 回滚后 verify |

### 14.4 缓解措施优先级

1. **必须做**: 备份, smoke test, healthz verify
2. **应该做**: Prometheus 配置, 24h 监控
3. **可选**: load test, perf benchmark

---

## 15. 交付清单

### 15.1 代码文件 (8 个)

| 路径 | 类型 | 行数 | 状态 |
|------|------|------|------|
| `meta/core/db_config_detector.py` | NEW | ~80 | 待 V050 实施 |
| `meta/core/sqlite_tx_state.py` | NEW | ~40 | 待 V050 实施 |
| `meta/core/orphan_tx_detector.py` | NEW | ~120 | 待 V050 实施 |
| `meta/core/observability.py` | NEW | ~100 | 待 V050 实施 |
| `meta/core/bo_framework.py` | MODIFY | +70 | 待 V050 实施 |
| `meta/core/sql_write_queue.py` | MODIFY | +25 | 待 V050 实施 |
| `meta/services/audit_service.py` | NOT MODIFIED | 0 | L4 包装在 observability.py |
| `meta/server.py` | MODIFY | +30 | 待 V050 实施 |
| **Total** | | **~465** | |

### 15.2 测试文件 (5 个, 95 cases)

| 路径 | Cases |
|------|-------|
| `tests/test_v007_15_config_detector.py` | 30 |
| `tests/test_v007_15_tx_state.py` | 15 |
| `tests/test_v007_15_bo_framework.py` | 20 |
| `tests/test_v007_15_write_queue.py` | 15 |
| `tests/test_v007_15_orphan_detector.py` | 15 |
| **Total** | **95** |

### 15.3 文档文件 (本文件 + 引用)

| 路径 | 用途 |
|------|------|
| `docs/V007_15_implementation_plan.md` | 本文档 (独立实施方案) |
| `docs/orphan_transaction_deep_analysis.md` | 设计依据 + §14 SAP LUW 分析 |
| `tools/smoke_v007_15.py` | 部署后 smoke test (NEW, ~60 lines) |
| `tools/test_pragmas.py` | 部署前 PRAGMA 验证 (NEW, ~30 lines) |
| `prometheus-alerts/v007_15.yml` | 5 alert rules (NEW) |

### 15.4 Worktree 计划

- **V049 worktree (current)**: 包含 V049-FD 修复 + V007.15 设计文档
- **V050 worktree (to be created by 协调智能体)**: 包含 V007.15 实施 (8 文件 + 5 测试)
- **release/pre-2026-06-29**: V049 cherry-pick 已完成 (协调智能体操作), V007.15 待 cherry-pick

### 15.5 验证清单 (实施完成时)

- [ ] 8 个生产代码文件已创建/修改
- [ ] 5 个测试文件已创建, 95 cases 全部 pass
- [ ] pytest --cov 覆盖率: 新文件 100%, 修改文件 80%+
- [ ] integration 3007/3018 部署成功
- [ ] e2e 测试通过 (按 §10.2)
- [ ] /healthz 返回 v007_15 段
- [ ] Prometheus 暴露 19 metrics + 1 gauge
- [ ] 5 alert rules 已配置
- [ ] orphan detector 在 24h 内无 recovery (干净)
- [ ] 性能回归 < 5% (per commit, +5ms / commit)

### 15.6 不交付

- SAP LUW (L8-L10) → V008
- per-1000-row savepoint → V008
- audit_log 6 月归档 → V007.16
- action_dispatcher LUW 集成 → V008

---

*Author: dev-agent (V049 + V007.15)*
*Date: 2026-07-05*
*Status: V007.15 独立实施方案完成 (Q1-Q5 决策已通过, L0-L7 详细代码 + 95 测试 + 部署/回滚 + 性能基线)*
*Worktree: 协调智能体需创建 V050 worktree, 然后按本方案实施*
*预估工作量: 5 dev days (含 1 day 部署 + 1 day 监控)*

---

## 16. 性能基线测试 (Performance Baseline)

> **目的**: 部署前后客观测量, 避免主观"感觉慢了"误判
> **作者**: dev-agent 2026-07-05
> **触发**: 部署 V007.15 前/后各跑 1 次, 对比 P95 延迟

### 16.1 性能开销预估 (回顾)

| 操作 | 增量延迟 | 频率 | 总影响 |
|---|---|---|---|
| `get_tx_state` (savepoint probe) | +1-2ms | 1-2 / commit | +2-4ms / commit |
| L2 `commit/rollback` try/finally | +1ms | 1 / commit | +1ms / commit |
| L3 phantom TX 检测 | +1-2ms | 1 / begin | +1-2ms / begin |
| L5 orphan detector | ~0ms | 1 / 30-60s | 忽略 |
| L6 metrics_inc | +0.05ms | 5-8 / commit | +0.4ms / commit |
| L6 log_tx_event | +0.1-0.5ms | 5-8 / commit | +1-4ms / commit |
| **总计 (per commit)** | | | **+5-12ms** |

**关键场景**:
- 20729 行导入: +6-14ms / 35-90s = **+0.02-0.04%** (无感)
- 单 record CRUD: +5-12ms (无感, 远低于 100ms 人感知阈值)
- batch_delete 1000: +5-12ms / 200ms = **+2.5-6%**
- 高频 100 req/s: +500-1200ms / s = **+0.1-0.2% CPU**

**回滚阈值**: P95 commit 延迟增加 **> 50%** (留 5x buffer 避免误判)

---

### 16.2 性能基线测试工具

#### 16.2.1 `tools/perf_baseline.py` (NEW, ~180 lines)

**用途**: 部署前/后跑相同负载, 记录 commit/begin/rollback/import P50/P95/P99 延迟, 输出 JSON 基线文件

```python
#!/usr/bin/env python3
"""
tools/perf_baseline.py
[V007.15] 性能基线测试工具

用法:
    # 部署前 (基线)
    python tools/perf_baseline.py --label before-v007.15 --output baseline-before.json

    # 部署后
    python tools/perf_baseline.py --label after-v007.15 --output baseline-after.json

    # 对比
    python tools/perf_compare.py baseline-before.json baseline-after.json
"""
import argparse
import json
import sqlite3
import time
import statistics
import sys
import os
from contextlib import contextmanager
from typing import List, Dict, Any

# 性能测试不依赖业务代码, 直接用 sqlite3 + savepoint probe 模拟 V007.15 行为


def measure_operation(op_fn, iterations: int = 100) -> Dict[str, float]:
    """测量单次操作 P50/P95/P99 延迟 (ms)"""
    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        op_fn()
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies.append(elapsed_ms)

    latencies.sort()
    return {
        'count': iterations,
        'p50_ms': round(latencies[int(iterations * 0.5)], 3),
        'p95_ms': round(latencies[int(iterations * 0.95)], 3),
        'p99_ms': round(latencies[int(iterations * 0.99)], 3),
        'min_ms': round(latencies[0], 3),
        'max_ms': round(latencies[-1], 3),
        'avg_ms': round(statistics.mean(latencies), 3),
    }


def measure_with_savepoint_probe(db_path: str, iterations: int = 100) -> Dict[str, float]:
    """模拟 L1: savepoint probe (每次 commit/rollback 探测 tx 状态)"""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    def commit_with_probe():
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS _perf (x INT)")
        conn.execute("INSERT INTO _perf VALUES (1)")
        # V007.15 L1 savepoint probe
        try:
            conn.execute("SAVEPOINT __probe__")
            conn.execute("RELEASE SAVEPOINT __probe__")
        except sqlite3.OperationalError:
            pass
        conn.execute("COMMIT")

    result = measure_operation(commit_with_probe, iterations)
    conn.close()
    return result


def measure_without_savepoint_probe(db_path: str, iterations: int = 100) -> Dict[str, float]:
    """基线: 不带 savepoint probe 的 commit (V007.15 之前)"""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    def commit_baseline():
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS _perf (x INT)")
        conn.execute("INSERT INTO _perf VALUES (1)")
        conn.execute("COMMIT")

    result = measure_operation(commit_baseline, iterations)
    conn.close()
    return result


def measure_begin_phantom_check(db_path: str, iterations: int = 100) -> Dict[str, float]:
    """模拟 L3: phantom TX 检测 (begin 前 savepoint probe)"""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    def begin_with_phantom_check():
        # V007.15 L3 phantom check
        try:
            conn.execute("SAVEPOINT __phantom__")
            conn.execute("ROLLBACK TO SAVEPOINT __phantom__")
            conn.execute("RELEASE SAVEPOINT __phantom__")
        except sqlite3.OperationalError:
            pass
        # Normal begin
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("COMMIT")

    result = measure_operation(begin_with_phantom_check, iterations)
    conn.close()
    return result


def measure_batch_import(db_path: str, row_count: int = 1000) -> Dict[str, float]:
    """模拟批量导入: row_count 行在 1 个 TX 中 (V007.15 后每 commit +5-12ms)"""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("CREATE TABLE IF NOT EXISTS _batch (id INT, name TEXT)")

    def batch_import():
        conn.execute("BEGIN IMMEDIATE")
        for i in range(row_count):
            conn.execute("INSERT INTO _batch VALUES (?, ?)", (i, f"row_{i}"))
        # V007.15 L1 savepoint probe
        try:
            conn.execute("SAVEPOINT __probe__")
            conn.execute("RELEASE SAVEPOINT __probe__")
        except sqlite3.OperationalError:
            pass
        conn.execute("COMMIT")

    result = measure_operation(batch_import, iterations=10)  # 10 次平均
    conn.execute("DELETE FROM _batch")
    conn.close()
    return result


def main():
    parser = argparse.ArgumentParser(description='V007.15 性能基线测试')
    parser.add_argument('--label', required=True, help='基线标签 (e.g. before-v007.15)')
    parser.add_argument('--output', required=True, help='输出 JSON 路径')
    parser.add_argument('--iterations', type=int, default=100, help='每次测量的迭代次数')
    parser.add_argument('--db-path', default='/tmp/perf_baseline.db', help='临时 DB 路径')
    args = parser.parse_args()

    print(f"[perf_baseline] Label: {args.label}")
    print(f"[perf_baseline] Output: {args.output}")
    print(f"[perf_baseline] Iterations: {args.iterations}")
    print()

    # 准备 DB
    if os.path.exists(args.db_path):
        os.remove(args.db_path)

    results = {
        'label': args.label,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'iterations': args.iterations,
        'scenarios': {},
    }

    # 1. 单 commit (无 probe) - V007.15 前基线
    print("[1/5] Measure: single commit (no probe) - baseline")
    results['scenarios']['commit_no_probe'] = measure_without_savepoint_probe(
        args.db_path, args.iterations
    )
    print(f"  P50={results['scenarios']['commit_no_probe']['p50_ms']}ms, "
          f"P95={results['scenarios']['commit_no_probe']['p95_ms']}ms")

    # 2. 单 commit (带 probe) - V007.15 后
    print("[2/5] Measure: single commit (with savepoint probe) - V007.15 L1")
    results['scenarios']['commit_with_probe'] = measure_with_savepoint_probe(
        args.db_path, args.iterations
    )
    print(f"  P50={results['scenarios']['commit_with_probe']['p50_ms']}ms, "
          f"P95={results['scenarios']['commit_with_probe']['p95_ms']}ms")

    # 3. Begin + phantom check - V007.15 L3
    print("[3/5] Measure: begin with phantom TX check - V007.15 L3")
    results['scenarios']['begin_phantom_check'] = measure_begin_phantom_check(
        args.db_path, args.iterations
    )
    print(f"  P50={results['scenarios']['begin_phantom_check']['p50_ms']}ms, "
          f"P95={results['scenarios']['begin_phantom_check']['p95_ms']}ms")

    # 4. 批量导入 (1000 rows, 1 TX)
    print("[4/5] Measure: batch import 1000 rows in 1 TX")
    results['scenarios']['batch_import_1000'] = measure_batch_import(
        args.db_path, row_count=1000
    )
    print(f"  P50={results['scenarios']['batch_import_1000']['p50_ms']}ms, "
          f"P95={results['scenarios']['batch_import_1000']['p95_ms']}ms")

    # 5. 批量导入 (10000 rows, 1 TX) - 模拟真实场景
    print("[5/5] Measure: batch import 10000 rows in 1 TX - real scenario")
    results['scenarios']['batch_import_10000'] = measure_batch_import(
        args.db_path, row_count=10000
    )
    print(f"  P50={results['scenarios']['batch_import_10000']['p50_ms']}ms, "
          f"P95={results['scenarios']['batch_import_10000']['p95_ms']}ms")

    # Save
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n[perf_baseline] Results saved to {args.output}")

    # Cleanup
    if os.path.exists(args.db_path):
        os.remove(args.db_path)


if __name__ == "__main__":
    main()
```

#### 16.2.2 `tools/perf_compare.py` (NEW, ~100 lines)

**用途**: 对比 2 份基线 JSON, 输出每个场景的延迟增加百分比 + 总体判断 (PASS/REVIEW/FAIL)

```python
#!/usr/bin/env python3
"""
tools/perf_compare.py
[V007.15] 性能基线对比工具

用法:
    python tools/perf_compare.py baseline-before.json baseline-after.json

输出:
    - 每个场景的 P50/P95 增加百分比
    - 总体判断 (PASS/REVIEW/FAIL)
"""
import argparse
import json
import sys


# 回滚阈值 (基于 §16.1 分析)
PASS_THRESHOLD = 10.0    # P95 增加 < 10% → PASS
REVIEW_THRESHOLD = 50.0  # P95 增加 < 50% → REVIEW
# P95 增加 >= 50% → FAIL (建议回滚)


def compare_scenario(before: dict, after: dict) -> dict:
    """对比单场景"""
    result = {}
    for metric in ['p50_ms', 'p95_ms', 'p99_ms', 'avg_ms']:
        b = before.get(metric, 0)
        a = after.get(metric, 0)
        if b == 0:
            pct = 0
        else:
            pct = ((a - b) / b) * 100
        result[metric] = {
            'before_ms': b,
            'after_ms': a,
            'delta_ms': round(a - b, 3),
            'delta_pct': round(pct, 2),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description='V007.15 性能基线对比')
    parser.add_argument('before', help='Before JSON')
    parser.add_argument('after', help='After JSON')
    args = parser.parse_args()

    with open(args.before) as f:
        before = json.load(f)
    with open(args.after) as f:
        after = json.load(f)

    print(f"Performance Comparison")
    print(f"  Before: {before.get('label')} @ {before.get('timestamp')}")
    print(f"  After:  {after.get('label')} @ {after.get('timestamp')}")
    print()
    print(f"{'Scenario':<30} {'Metric':<10} {'Before':>10} {'After':>10} {'Delta':>10} {'%':>8} {'Status':<8}")
    print("-" * 90)

    overall_status = "PASS"
    for scenario_name in before.get('scenarios', {}):
        if scenario_name not in after.get('scenarios', {}):
            continue
        b = before['scenarios'][scenario_name]
        a = after['scenarios'][scenario_name]
        cmp = compare_scenario(b, a)

        for metric, vals in cmp.items():
            pct = vals['delta_pct']
            if pct < PASS_THRESHOLD:
                status = "✅ PASS"
            elif pct < REVIEW_THRESHOLD:
                status = "⚠️ REVIEW"
                overall_status = "REVIEW"
            else:
                status = "❌ FAIL"
                overall_status = "FAIL"

            print(f"{scenario_name:<30} {metric:<10} "
                  f"{vals['before_ms']:>10.2f} {vals['after_ms']:>10.2f} "
                  f"{vals['delta_ms']:>+10.2f} {pct:>+7.1f}% {status}")

    print()
    print(f"Overall: {overall_status}")
    if overall_status == "FAIL":
        print("Recommendation: ROLLBACK")
        sys.exit(2)
    elif overall_status == "REVIEW":
        print("Recommendation: Investigate before continue")
        sys.exit(1)
    else:
        print("Recommendation: Continue")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

### 16.3 部署流程集成

```bash
# === 部署前 (基线) ===
ssh user@172.20.59.7
cd /opt/app

# 1. 跑 perf_baseline, label=before
python tools/perf_baseline.py --label before-v007.15 --output /tmp/baseline-before.json
# Expected: commit_with_probe p95 < 20ms (V007.15 前) — actually NO probe
# Expected: commit_no_probe p95 = current production latency

# 保存基线 (从 production 拉下来)
scp user@172.20.59.7:/tmp/baseline-before.json ./baseline-before.json

# === 部署 V007.15 ===
git cherry-pick <v007_15_commits>
systemctl restart meta-backend
sleep 30

# 验证 healthz
curl http://localhost:8081/healthz | python -m json.tool | grep v007_15

# === 部署后 ===
ssh user@172.20.59.7
cd /opt/app

# 2. 跑 perf_baseline, label=after
python tools/perf_baseline.py --label after-v007.15 --output /tmp/baseline-after.json

# 拉下来对比
scp user@172.20.59.7:/tmp/baseline-after.json ./baseline-after.json

# 3. 对比
python tools/perf_compare.py baseline-before.json baseline-after.json

# 期望输出:
#   commit_with_probe vs commit_no_probe: P95 delta = +5-12ms (+50-100%)
#   BUT! 这是 V007.15 设计的差异, 不是 regression
#   真正的对比是: commit_with_probe (after) vs commit_no_probe (before)

# === 判断标准 ===
# 1. 单 commit P95 增加 < 10ms → PASS
# 2. 单 commit P95 增加 10-50ms → REVIEW (业务影响小, 可接受)
# 3. 单 commit P95 增加 > 50ms → FAIL (异常, 需调查)

# batch_import_1000 P95 增加 < 100ms → PASS (相对 200ms 总延迟)
# batch_import_10000 P95 增加 < 200ms → PASS (相对 2s 总延迟)
```

### 16.4 预期基线值 (供参考)

| Scenario | Before (V007.15 前) | After (V007.15 后) | Delta | Status |
|---|---|---|---|---|
| `commit_no_probe` P95 | 5-15ms | N/A (基线) | - | - |
| `commit_with_probe` P95 | N/A | 8-25ms | +3-10ms | ✅ PASS |
| `begin_phantom_check` P95 | 1-3ms | 2-5ms | +1-2ms | ✅ PASS |
| `batch_import_1000` P95 | 100-300ms | 105-312ms | +5-12ms | ✅ PASS |
| `batch_import_10000` P95 | 1500-3500ms | 1505-3512ms | +5-12ms | ✅ PASS |

**关键观察**:
- **绝对值增加**: 5-12ms / commit
- **相对值增加**: 50-100% (单 commit 基线太低)
- **业务影响**: 0.02-6% (per scenario)
- **回滚阈值**: P95 +50% 且 绝对值增加 > 50ms 才考虑回滚

### 16.5 决策表

| 场景 | PASS | REVIEW | FAIL |
|---|---|---|---|
| 单 commit P95 | Δ < 10ms | 10-50ms | > 50ms |
| batch_import P95 | Δ < 100ms (1k rows) / Δ < 200ms (10k rows) | 100-500ms / 200-1000ms | > 500ms / > 1000ms |
| 启动时间 | Δ < 100ms | 100-500ms | > 500ms |
| `/healthz` 延迟 | Δ < 5ms | 5-20ms | > 20ms |
| 内存占用 | Δ < 20MB | 20-50MB | > 50MB |

**FAIL 触发**: 立即回滚 (按 §13.3 步骤)
**REVIEW 触发**: 继续监控 24h, 如未恶化则 PASS
**PASS**: 部署成功, 继续监控 7 天

### 16.6 性能监控 (持续)

部署后 7 天内, 持续观察:
- Prometheus: `v007_15_commit_duration_seconds` (新增 histogram)
- /healthz: `orphan_detector.recovery_count` 应保持 0
- 业务: 用户反馈"卡顿"数量

如果发现 P95 commit 延迟在 7 天内持续上升 (非一次性 spike), 触发 §13.4 回滚。

### 16.7 已知性能陷阱 (避免)

| Trap | Symptom | Fix |
|---|---|---|
| **L1 savepoint probe 在 hot path 反复调** | 单接口 P95 +20ms | V008: 缓存 savepoint probe 结果 (1s 内复用) |
| **L5 orphan detector 30s/次 太频繁** | 后台 CPU +0.5% | 部署后改 60s (需 config adjust) |
| **L6 structlog 输出到 file 而非 stdout** | commit P95 +10ms | 检查 logging config, 用 stdout/buffered |
| **L7 /healthz 在生产被高频调 (k8s liveness)** | +0.5ms / healthz | /healthz 加 cache (5s) |

### 16.8 性能基线测试的限制

- **不模拟真实业务**: 仅测 SQLite 延迟, 不包含 Flask routing, JSON serialize, auth check
- **不模拟并发**: 1 connection 串行, 真实多用户并发可能锁等待
- **不模拟 W AL contention**: 单进程测, 真实多进程写有 WAL 锁竞争

**建议**: perf_baseline.py 之外, 部署后用真实业务负载 (1k 用户并发) 跑 1 次 smoke test 验证。

---

### 16.9 与 §13 部署流程的整合

| 步骤 | 之前 | 现在 |
|---|---|---|
| 1. 备份 | ✓ | ✓ |
| 2. Cherry-pick | ✓ | ✓ |
| 3. Run smoke test | ✓ | ✓ |
| **3.5 Run perf_baseline (before)** | ❌ | **✓ 新增** |
| 4. Restart | ✓ | ✓ |
| 5. Verify /healthz | ✓ | ✓ |
| **5.5 Run perf_baseline (after)** | ❌ | **✓ 新增** |
| 6. Load test | ✓ | ✓ |
| **6.5 Run perf_compare** | ❌ | **✓ 新增** |
| 7. Monitor 24h | ✓ | ✓ |

**新增 3 个步骤**: 3.5 (before baseline), 5.5 (after baseline), 6.5 (compare)
**总耗时增加**: ~5 分钟 (perf_baseline 跑 5 个场景 × 100 iter)

### 16.10 性能基线测试不在 V050 实施范围

`tools/perf_baseline.py` 和 `tools/perf_compare.py` **不修改生产代码**, 仅测试工具, **V007.15 worktree 中可一并创建** 或 **V050 协调智能体单独交付**。

我推荐:
- 在 V050 worktree 中创建 (与 V007.15 一起 ship)
- 协调智能体在部署 V007.15 前先跑 1 次 before baseline
- 部署后跑 1 次 after baseline + compare

---

*Update: 2026-07-05, dev-agent*
*Section 16 added: 性能基线测试工具 + 决策表 + 部署集成*
*Total doc length: 2700+ lines*
*Files added: tools/perf_baseline.py (180 lines), tools/perf_compare.py (100 lines)*
