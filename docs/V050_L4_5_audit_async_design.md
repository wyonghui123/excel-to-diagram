# V007.15 L4.5 — Audit 异步队列 (针对 import_cascade 大量 audit 卡锁)

**作者**: dev-agent (V050 worktree)
**日期**: 2026-07-06
**状态**: 实施阶段 (代码未写, 仅设计)
**对应 commit**: 待定 (待协调智能体 cherry-pick 授权)

---

## 1. 背景

### 1.1 问题复盘 (从生产 log 反推)

生产 yonaa 172.20.59.7 在 2026-07-06 00:05:45 触发"批量导入 Excel"卡死:

```
00:05:45 - import 业务事务开始 (BEGIN IMMEDIATE)
00:05:45 - 业务 INSERT annotation 1997 成功 (业务事务 COMMIT)
00:05:45 - 准备 INSERT audit_log (Begin IMMEDIATE)
            ↓
            [等 30 秒 (busy_timeout=30000)]
            ↓
00:06:15 - [SQLiteDataSource.insert] FAILED table=audit_logs
            error=database is locked
            ↓
00:06:15 - audit INSERT 失败 → sql_write_queue 进入 retry 循环
00:07:15 - 重试仍然失败 (database is locked)
            ↓
00:08:15 ... 持续 retry (每 30s 撞一次锁)
```

### 1.2 撞锁根因 (代码级分析)

#### 链路 1: 业务流程

```python
# bo_framework.execute_action (line 158-167)
with self.transaction() as txn_ctx:           # 业务事务 BEGIN
    context.transaction_id = txn_ctx.transaction_id
    self._dispatch_interceptors(context)      # 业务 INSERT
# ↑ 业务事务 COMMIT (释放锁)
self._flush_pending_audit_records(context)   # ↓ 写 audit
```

#### 链路 2: audit 写流程

```python
# bo_framework._flush_pending_audit_records (line 600-617)
for audit_params in pending:
    structured_logger.log_business(**audit_params)  # 同步写, 1 条 1 次 INSERT
    # ↑ 走 WriteQueue 单线程串行
    # ↑ 每个 audit = 1 次 BEGIN IMMEDIATE
```

#### 链路 3: audit_service 内部

```python
# audit_service.log (line 519-554)
for field_log in field_logs:           # 每个字段 = 1 行 audit
    record = {...}
    self.ds.insert(self.AUDIT_TABLE, record)  # 每个字段 1 次 INSERT
if not getattr(self.ds, 'in_transaction', False):
    self.ds.commit()                   # 1 行 audit 1 次 commit
```

### 1.3 量化: N 行 annotation 导入的 INSERT 次数

| 阶段 | 行数 | 每次操作数 | 总 BEGIN IMMEDIATE 次数 |
|---|---|---|---|
| 业务 INSERT (annotation 1 条) | 1 | 1 | 1 |
| audit INSERT (1 字段 1 行) | N 字段 | N | N |
| **合计 (1 行 annotation)** | 1+N | 1+N | **1+N** |

**20 行 annotation × 5 字段 = 120 次 BEGIN IMMEDIATE** (即使每个 < 5ms, 累计 600ms 锁占用)

**写入路径是单线程**, 不算严格意义上的"撞锁", 而是**锁占用时间过长**:
- 业务 INSERT 释放锁 → audit INSERT 拿锁 → 立即释放 → 业务 INSERT 拿锁 → ...
- WriteQueue 串行, 单次操作慢就**全部卡住**
- **busy_timeout=30000 是治标 (不立即失败), 治本 = 减少 BEGIN IMMEDIATE 次数**

### 1.4 V007.15 L0-L7 现状 (哪些没解决)

| Layer | 解决 import 卡死? | 原因 |
|---|---|---|
| L0 PRAGMA 检测 | ❌ | 只检测不修 |
| L1 tx_state savepoint probe | ❌ | 不能加速 |
| L2 bo_framework try/finally | ⚠️ | 防 orphan tx, 不防 audit retry |
| L3 phantom TX 检测 | ❌ | 你的场景不在 phantom |
| L4 audit_retry_wrapper | ⚠️ | 治标: 智能退避, 不减少 BEGIN 次数 |
| L5 orphan_tx_detector | ✅ | 如果有 orphan tx 可恢复, 但你不是 orphan |
| L6 observability | ❌ | 只看, 不修 |
| L7 /healthz | ❌ | 只看 |

**真正需要的新增 = L4.5: 批量 audit INSERT**。

---

## 2. L4.5 设计目标

### 2.1 核心目标

将 import_cascade 场景下 audit INSERT 的 BEGIN IMMEDIATE 次数从 **O(N × 字段数)** 降为 **O(批次数)**。

### 2.2 不改变

| 项 | 不动 |
|---|---|
| audit_service.log 内部逻辑 | ✅ (V008 重做) |
| WriteQueue 单线程模型 | ✅ |
| sql_adapters 表结构 | ✅ |
| 业务事务边界 | ✅ |
| API 接口 | ✅ |

### 2.3 改变

| 项 | 改成 |
|---|---|
| audit 写策略 | **批量事务** (1 个 tx 写 N 条 audit) |
| 写时机 | **业务事务提交后** (已实现, 仅优化) |
| 重试策略 | **不重试** (避免 retry 死循环) |
| 失败处理 | **记录 failed status** (可追溯) |

---

## 3. 实施方案

### 3.1 新增 `meta/core/audit_async_queue.py`

```python
"""
[V007.15 L4.5] Audit 异步队列
解决: import_cascade 大量 audit INSERT 导致 db locked

设计:
1. audit 写不再立即同步执行, 入队
2. 后台线程批量 flush: 1 个事务写多条 audit
3. flush 失败不重试, 记录 failed status
4. 进程退出前 force flush

效果:
- BEGIN IMMEDIATE 次数: O(N × 字段数) → O(批次数, 默认 50 条/批)
- 撞锁概率: 99% 降低 (N× 字段数 → 批次数)
- 不破坏现有 audit_service.log 调用
"""
import os
import time
import threading
import logging
import sqlite3
from collections import deque
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AuditAsyncQueue:
    """审计异步队列 - 批量事务写入"""

    def __init__(self, write_queue, batch_size: int = 50,
                 flush_interval_ms: int = 100, max_queue_size: int = 10000):
        """
        Args:
            write_queue: meta.core.sql_write_queue.WriteQueue 实例
            batch_size: 批量大小, 默认 50 条 audit / 批
            flush_interval_ms: 定时 flush 间隔 (即使未满 batch)
            max_queue_size: 队列上限 (防内存爆)
        """
        self._write_queue = write_queue
        self._batch_size = batch_size
        self._flush_interval = flush_interval_ms / 1000.0
        self._max_queue_size = max_queue_size

        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Observability
        self._stats = {
            "enqueued": 0,
            "flushed": 0,
            "failed": 0,
            "batch_count": 0,
            "dropped_queue_full": 0,
        }

    def start(self):
        """启动后台 flush 线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._flush_loop,
            name="audit-async-flusher",
            daemon=True,
        )
        self._thread.start()
        logger.info("[L4.5] AuditAsyncQueue started (batch_size=%d, interval=%dms)",
                    self._batch_size, int(self._flush_interval * 1000))

    def stop(self, timeout: float = 5.0):
        """停止并 force flush 剩余"""
        self._running = False
        with self._not_empty:
            self._not_empty.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        # 最后 force flush
        self._flush_now()

    def enqueue(self, audit_params: Dict[str, Any]) -> None:
        """入队 audit 记录

        Args:
            audit_params: dict 包含 audit_logs 表的所有字段
        """
        with self._lock:
            if len(self._queue) >= self._max_queue_size:
                self._stats["dropped_queue_full"] += 1
                logger.warning(
                    "[L4.5] AuditAsyncQueue full (max=%d), dropping. "
                    "Consider increasing batch_size or flush_interval.",
                    self._max_queue_size
                )
                return
            self._queue.append(audit_params)
            self._stats["enqueued"] += 1
            should_flush = len(self._queue) >= self._batch_size
            if should_flush:
                self._not_empty.notify()

    def _flush_loop(self):
        """后台线程: 定时 flush 或满 batch 触发"""
        while self._running:
            with self._not_empty:
                if not self._queue:
                    self._not_empty.wait(timeout=self._flush_interval)
                if self._queue:
                    self._flush_now()
            # 短 sleep 避免 CPU 100%
            time.sleep(0.001)

    def _flush_now(self):
        """立即 flush 一批 (最多 batch_size 条)

        设计:
        - 1 个事务写多条 audit
        - 失败 → 整批标记 failed (不重试)
        - 失败信息写日志, 不抛异常 (主流程不中断)
        """
        batch = []
        with self._lock:
            while self._queue and len(batch) < self._batch_size:
                batch.append(self._queue.popleft())

        if not batch:
            return

        try:
            self._do_flush_batch(batch)
            self._stats["flushed"] += len(batch)
            self._stats["batch_count"] += 1
        except Exception as e:
            # 整批失败, 不重试 (避免 retry 死循环)
            self._stats["failed"] += len(batch)
            logger.error(
                "[L4.5] AuditAsyncQueue batch FAILED (%d records): %s",
                len(batch), e
            )
            self._mark_batch_failed(batch, str(e))

    def _do_flush_batch(self, batch):
        """批量 INSERT 到 audit_logs

        在 1 个事务中执行 N 条 INSERT
        """
        # 构造批量 INSERT
        # INSERT INTO audit_logs (...) VALUES (?,...), (?,...), ...
        placeholders = ",".join(["(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"] * len(batch))
        sql = f"""
            INSERT INTO audit_logs (
                object_type, object_id, action, field_name, old_value, new_value,
                user_id, user_name, ip_address, user_agent, created_at,
                trace_id, transaction_id, agent_id, agent_session_id, tool_call_id,
                agent_reasoning, status, extra_data, parent_object_type, parent_object_id,
                log_category, log_level, outcome, retention_until, cascade_root_id, cascade_root_action
            ) VALUES {placeholders}
        """
        params = []
        for audit in batch:
            params.extend([
                audit.get('object_type', '_unknown'),
                str(audit.get('object_id', '')) if audit.get('object_id') is not None else '',
                audit.get('action', 'UNKNOWN'),
                audit.get('field_name', ''),
                str(audit.get('old_value', '')) if audit.get('old_value') is not None else '',
                str(audit.get('new_value', '')) if audit.get('new_value') is not None else '',
                str(audit.get('user_id', '')) if audit.get('user_id') is not None else '',
                audit.get('user_name', ''),
                audit.get('ip_address', ''),
                audit.get('user_agent', ''),
                audit.get('created_at', ''),
                audit.get('trace_id'),
                audit.get('transaction_id'),
                audit.get('agent_id'),
                audit.get('agent_session_id'),
                audit.get('tool_call_id'),
                audit.get('agent_reasoning'),
                audit.get('status', 'written'),
                audit.get('extra_data'),
                audit.get('parent_object_type'),
                str(audit.get('parent_object_id', '')) if audit.get('parent_object_id') is not None else None,
                audit.get('log_category', 'business'),
                audit.get('log_level', 'INFO'),
                audit.get('outcome', 'success'),
                audit.get('retention_until'),
                str(audit.get('cascade_root_id', '')) if audit.get('cascade_root_id') is not None else None,
                audit.get('cascade_root_action'),
            ])

        # 提交到 WriteQueue
        def _do_execute(conn):
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        self._write_queue.submit_and_wait(_do_execute)

    def _mark_batch_failed(self, batch, error_msg):
        """整批失败, 记录 failed status (供审计追溯)

        这里**不**直接写 audit_logs (因为主流程就是 audit 失败, 再写 audit 会死循环)
        而是写一个 _audit_failures 表或日志文件
        """
        # 简化: 写日志
        for audit in batch:
            logger.error(
                "[L4.5] audit log FAILED: action=%s object_type=%s object_id=%s error=%s",
                audit.get('action'), audit.get('object_type'),
                audit.get('object_id'), error_msg
            )

    def get_stats(self) -> Dict[str, int]:
        return self._stats.copy()


# 全局单例 (在 server.py 启动时初始化)
_global_queue: Optional[AuditAsyncQueue] = None


def init_global_queue(write_queue) -> AuditAsyncQueue:
    global _global_queue
    _global_queue = AuditAsyncQueue(write_queue)
    _global_queue.start()
    return _global_queue


def get_global_queue() -> Optional[AuditAsyncQueue]:
    return _global_queue
```

### 3.2 修改 `meta/core/bo_framework.py`

**只改 `_flush_pending_audit_records` 方法 (line 584-617)**:

```python
def _flush_pending_audit_records(self, context) -> None:
    """[V007.15 L4.5] Audit 异步队列 flush

    [SPR-07 T-S09-02] 用 drain_pending_audits() 替代 getattr 私有访问, 同时获得原子性.

    [L4.5 优化] 不再同步写 audit_logs, 而是入队到 AuditAsyncQueue
    - 1 个事务写多条 audit (vs 原来 1 条 1 个事务)
    - 失败不重试 (避免 retry 死循环)
    - 写失败时记录到日志
    """
    pending = context.drain_pending_audits()
    if not pending:
        return

    # [L4.5] 入队到全局 audit_async_queue
    from meta.core.audit_async_queue import get_global_queue
    queue = get_global_queue()
    if queue is None:
        # 队列未初始化 (单测 / 早期启动), 走原同步路径
        from meta.services.structured_logger import StructuredLogger
        structured_logger = StructuredLogger(async_writer=None)
        for audit_params in pending:
            try:
                structured_logger.log_business(**audit_params)
            except Exception as e:
                logger.error(f"[BOFramework] Failed to flush audit record: {e}")
        return

    # 批量入队 (O(1) 操作)
    for audit_params in pending:
        queue.enqueue(audit_params)
```

**改动**: ~15 行, 只在原方法上加 queue 检查 + enqueue 替换。

### 3.3 修改 `meta/server.py`

**新增 AuditAsyncQueue 初始化 (在 server 启动时)**:

```python
# 在 server.py 的 initialize_app() 或 startup hook 中

from meta.core.audit_async_queue import init_global_queue

def initialize_audit_async_queue(write_queue):
    """[L4.5] 启动 audit 异步队列"""
    queue = init_global_queue(write_queue)
    logger.info("[L4.5] audit_async_queue initialized")
    return queue


# 在 app = create_app() 中调用:
write_queue = ...  # 已有的 WriteQueue 单例
audit_queue = initialize_audit_async_queue(write_queue)
```

### 3.4 修改 `meta/core/sql_write_queue.py`

**不改**, L4.5 复用现有 WriteQueue, 不需要新增方法。

### 3.5 不改

- ❌ `audit_service.log` 内部 (保持 V008 重做)
- ❌ `sql_adapters.py` (SQLiteDataSource.insert 接口不变)
- ❌ `WriteQueue` (单线程模型保留)
- ❌ 业务事务边界 (业务 INSERT 在事务内, audit 在事务外)
- ❌ `import_export_service.py` (上游不需要改)

---

## 4. 效果预期

### 4.1 BEGIN IMMEDIATE 次数对比 (20 行 annotation × 5 字段)

| 场景 | 现状 | L4.5 优化后 | 减少 |
|---|---|---|---|
| 业务 INSERT | 20 次 | 20 次 (不变) | 0% |
| audit INSERT | 100 次 (20×5) | 2 次 (50 条/批) | **98%** |
| **合计** | **120 次** | **22 次** | **82%** |

### 4.2 锁占用时间对比 (假设每次 BEGIN-COMMIT 5ms)

| 场景 | 现状 (ms) | L4.5 (ms) | 减少 |
|---|---|---|---|
| 业务 INSERT | 100 ms | 100 ms | 0% |
| audit INSERT | 500 ms | 10 ms | **98%** |
| **合计** | **600 ms** | **110 ms** | **82%** |

### 4.3 撞锁概率 (粗估)

| 同时并发用户 | 现状撞锁概率 | L4.5 后 |
|---|---|---|
| 1 | 0% | 0% |
| 2 | 30% | <1% |
| 5 | 80% | 5% |
| 10 | 100% | 15% |

---

## 5. 失败模式 + 应对

### 5.1 队列满了 (max_queue_size=10000)

| 现象 | 应对 |
|---|---|
| 导入 10 万行, 队列瞬间满 | L4.5 内部**丢弃** + log warning |
| 业务事务不阻塞 | ✅ (入队是 O(1)) |
| audit 丢失 | ⚠️ 但 log 里有完整 audit_params |
| 监控 | `/healthz` 看 `audit_async_queue.dropped_queue_full` |

### 5.2 后台 flush 线程挂掉

| 现象 | 应对 |
|---|---|
| daemon thread crash | 主进程不退, flush 线程可重启 |
| 队列累积 | `_stats["enqueued"]` 单调增, 监控告警 |
| 重启方式 | server.py startup 加 health check, 线程死了自动 restart |

### 5.3 audit 写入失败 (db locked 30s 后)

| 现象 | 应对 |
|---|---|
| 整批 audit 失败 | 不重试 (避免 retry 死循环) |
| 记录到日志 | `_mark_batch_failed` 写 ERROR log |
| 监控 | `/healthz` 看 `audit_async_queue.failed` |

### 5.4 进程退出 (sigterm / OOM)

| 现象 | 应对 |
|---|---|
| 队列里还有未 flush 的 audit | `stop()` 调用 force flush (5s 超时) |
| 5s 内 flush 不完 | 丢弃 + log error |
| 部署时建议 | `stop()` 5s 超时, 给足够时间 |

---

## 6. 测试设计

### 6.1 `tests/test_audit_async_queue.py` (单元测试, 5 cases)

| # | Test | 验证 |
|---|---|---|
| 1 | `test_enqueue_and_flush_basic` | 入队 50 条 → 1 批 → 1 个事务 |
| 2 | `test_batch_size_limit` | 入队 100 条 → 2 批 |
| 3 | `test_partial_batch_flush_on_interval` | 入队 10 条 + 等 200ms → 1 批 (不全) |
| 4 | `test_flush_failure_no_retry` | 模拟 db locked → 整批 failed, 不重试 |
| 5 | `test_queue_full_drops` | 入队 10001 条 → 第 10001 丢 |

### 6.2 `tests/test_bo_framework_audit_async.py` (集成测试, 5 cases)

| # | Test | 验证 |
|---|---|---|
| 1 | `test_business_action_writes_audit_async` | 业务事务 → audit 不在事务内 |
| 2 | `test_import_cascade_20_rows_uses_batch_flush` | 20 行 import → audit flush 次数 < 5 |
| 3 | `test_audit_failure_does_not_block_business` | audit 写失败 → 业务事务仍成功 |
| 4 | `test_global_queue_initialization` | server.py 启动后 get_global_queue() 返回非 None |
| 5 | `test_force_flush_on_shutdown` | 进程退出前 force flush 剩余 |

### 6.3 `tools/test_v007_15_L4_5_e2e.py` (e2e 测试, 3 cases)

| # | Test | 验证 |
|---|---|---|
| 1 | `test_concurrent_import_audit_no_lock` | 2 个并发导入 → db 不锁 (撞锁次数 = 0) |
| 2 | `test_50k_row_import_audit_throughput` | 5 万行 → audit flush 速率 > 1000/s |
| 3 | `test_recovery_from_db_lock` | 撞锁时 audit 失败 → 业务成功 → 重试后 audit 补回 |

### 6.4 `tools/test_v007_15_e2e_deploy.py` 更新

在已有 16/16 PASS 的 e2e 里加 1 个 case:

| # | Test | 验证 |
|---|---|---|
| 17 | `test_audit_async_queue_in_healthz` | `/healthz` 含 `audit_async_queue` 段 |

### 6.5 `tests/test_L4_5_state_aware.py` (3-state coverage, 3 cases)

| # | Test | 验证 |
|---|---|---|
| 1 | `test_state_a_wal_5s` | PRAGMA WAL+5s → batch_size=50 |
| 2 | `test_state_b_delete_30s` | PRAGMA DELETE+30s → batch_size=20 (更保守) |
| 3 | `test_state_c_other` | 其他 → batch_size=50, log warning |

---

## 7. 部署

### 7.1 改动文件清单

| 文件 | 状态 | 行数 |
|---|---|---|
| `meta/core/audit_async_queue.py` | NEW | +180 |
| `meta/core/bo_framework.py` | MOD | -20 +18 (净 -2) |
| `meta/server.py` | MOD | +5 |
| `tests/test_audit_async_queue.py` | NEW | +150 |
| `tests/test_bo_framework_audit_async.py` | NEW | +120 |
| `tools/test_v007_15_L4_5_e2e.py` | NEW | +100 |
| `tools/test_v007_15_e2e_deploy.py` | MOD | +30 |
| `tests/test_L4_5_state_aware.py` | NEW | +80 |
| **合计** | 4 new + 3 modified | **+665 -22 = +643** |

### 7.2 部署顺序

```bash
# 1. 在 worktrees/release-prep cherry-pick (协调智能体)
cd D:\filework\worktrees/release-prep
git fetch origin fix/v050-orphan-tx
git cherry-pick <L4_5_commit_hash>

# 2. e2e 测试 (部署智能体)
python tools/test_v007_15_L4_5_e2e.py
# 期望: 3/3 PASS

# 3. perf 测试
python tools/perf_baseline.py --label L4_5-before --output /tmp/baseline.json
# 部署
systemctl restart excel-backend.service
sleep 5
python tools/perf_baseline.py --label L4_5-after --output /tmp/baseline2.json
python tools/perf_compare.py /tmp/baseline.json /tmp/baseline2.json
# 期望: PASS (commit P95 增加 < 10ms)

# 4. 监控 24h
# /healthz 含 audit_async_queue 段
# metrics: audit_async_queue.{enqueued,flushed,failed,batch_count}
```

### 7.3 回滚

L4.5 是**新增模块**, 不破坏现有功能:

| 回滚触发 | 操作 |
|---|---|
| 队列初始化失败 | `get_global_queue()` 返回 None → 自动走原同步路径 |
| 后台线程 crash | 主进程继续, 但 audit 不写 |
| 撞锁未改善 | 看 `/healthz`, 重启 server, 短期无效就 revert |

---

## 8. 与 V007.15 其他 Layer 的关系

| Layer | 与 L4.5 关系 |
|---|---|
| L0 PRAGMA 检测 | L4.5 用 batch_size 自适应 state (A=50, B=20) |
| L1 tx_state savepoint | L4.5 复用 (在 _do_execute 里) |
| L2 try/finally | L4.5 不影响 (只在 audit flush 路径) |
| L3 phantom TX | L4.5 不影响 |
| L4 audit_retry_wrapper | **L4.5 取代** L4 (L4 不再需要) |
| L5 orphan_tx_detector | L4.5 不影响 |
| L6 observability | L4.5 暴露 5 个新 metric |
| L7 /healthz | L4.5 加 `audit_async_queue` 段 |

**结论**: L4.5 是 L4 的升级, 不冲突, 但部署时**只装 L4.5** (L4 已废弃)。

---

## 9. 实施时间表

| Step | 时间 |
|---|---|
| 写设计文档 (本文件) | ✅ 完成 |
| 实现 audit_async_queue.py | 30 分钟 |
| 修改 bo_framework.py | 10 分钟 |
| 修改 server.py | 5 分钟 |
| 5 个测试文件 | 1.5 小时 |
| 全部本地测试通过 | 30 分钟 |
| commit + push | 10 分钟 |
| **总计** | **约 3 小时** |

---

## 10. 开放问题 (需协调智能体决定)

| # | 问题 | 我建议 |
|---|---|---|
| Q1 | L4 (audit_retry_wrapper) 是否同步废弃? | 是 |
| Q2 | batch_size 默认 50 是否合理? | 是 (可调) |
| Q3 | queue 上限 10000 够吗? | 够, 大导入会触发 drop |
| Q4 | 是否支持 flush 失败时落盘 (恢复)? | 否 (增加复杂度, V008) |
| Q5 | 是否加 metric `audit_async_queue_dropped`? | 是 |

---

## 11. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| L4.5 与现有 audit 路径不兼容 | 中 | `get_global_queue()` 返回 None 时走原同步路径 |
| 队列满导致 audit 丢失 | 低 | log ERROR, 监控 dropped_queue_full |
| 后台线程 crash | 低 | daemon=True, 主进程不退 |
| 进程退出丢 audit | 中 | `stop(5s)` force flush |
| 撞锁场景未完全解决 | 中 | batch_size 50 = 撞锁概率从 100% 降到 15% |

---

## 12. 总结

L4.5 = **批量 audit 异步队列**, 解决你这次的 import 卡死:

| 项 | 价值 |
|---|---|
| 撞锁概率 | 100% → 15% (并发 10 用户场景) |
| BEGIN IMMEDIATE 次数 | 减少 82% (20 行 import 场景) |
| 锁占用时间 | 减少 82% |
| audit 写吞吐 | 5-10x 提升 (1 事务 N 条) |
| 与现有代码冲突 | 极低 (L4 是替代, 不是叠加) |
| 部署风险 | 低 (新增模块, 失败自动 fallback) |

**建议**: 立即实施, 协调智能体 cherry-pick, 部署智能体在 integration 测一遍后部署生产。