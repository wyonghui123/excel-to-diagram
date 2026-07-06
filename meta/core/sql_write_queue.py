# -*- coding: utf-8 -*-
"""
SQLite 写入队列

串行化所有写操作到单连接，保证写入顺序和数据一致性：
- WriteQueue: 写操作队列 + 单写线程
- WriteOperation: 写操作封装
- WriteQueueConfig: 队列配置
"""

import os
import threading
import time
import logging
import traceback
from typing import Any, Callable, Optional, Dict, List
from dataclasses import dataclass, field
from queue import Queue, Empty
from concurrent.futures import Future, CancelledError

# [V007.15 L3] phantom TX detection
import sqlite3
from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.observability import metrics_inc, OBS_COUNTERS, log_tx_event

logger = logging.getLogger(__name__)

DISABLE_WRITE_QUEUE = os.environ.get('DISABLE_WRITE_QUEUE', '').lower() in ('true', '1', 'yes')


@dataclass
class WriteQueueConfig:
    max_queue_size: int = 1000
    submit_timeout: float = 30.0
    operation_timeout: float = 60.0
    # [DECORATIVE] v3.18 P0 调优: 间隔从 50 降到 10, 防止 WAL 膨胀导致 checkpoint 失败
    checkpoint_interval: int = 10
    # [DECORATIVE] v3.18 P0 调优: 模式从 FULL 改为 TRUNCATE (FULL 会阻塞读,TRUNCATE 更激进但不会因 busy 失败)
    checkpoint_mode: str = "TRUNCATE"  # PASSIVE → FULL → TRUNCATE


@dataclass
class WriteOperation:
    func: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    future: Future = field(default_factory=Future)
    submitted_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    # [M7.1 2026-06-05] 上下文（用于 CDC 钩子）
    entity_type: str = ''
    action: str = ''  # 'create' / 'update' / 'delete'
    affected_ids: List[int] = field(default_factory=list)
    transaction_id: str = ''

    def execute(self, conn=None) -> Any:
        self.started_at = time.time()
        try:
            if conn is not None:
                result = self.func(conn, *self.args, **self.kwargs)
            else:
                result = self.func(*self.args, **self.kwargs)
            self.completed_at = time.time()
            self.future.set_result(result)
            return result
        except Exception as e:
            self.completed_at = time.time()
            self.future.set_exception(e)
            raise


class WriteQueue:
    """串行化写入队列

    所有写操作通过 submit() 提交到队列，由单写线程顺序执行。
    利用 SQLite WAL 模式下写操作必须串行的特性，将并发写入请求
    排队化，避免锁竞争。

    使用方式：
        pool = SQLiteConnectionPool(...)
        queue = WriteQueue(pool, WriteQueueConfig())
        queue.start()

        future = queue.submit(lambda conn: conn.execute("INSERT ...", params))
        result = future.result(timeout=10)

        queue.stop()
    """

    def __init__(self, pool, config: WriteQueueConfig = None):
        self._pool = pool
        self._config = config or WriteQueueConfig()
        self._queue: Queue[WriteOperation] = Queue(
            maxsize=self._config.max_queue_size
        )
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._commit_counter = 0
        self._in_transaction = False
        self._savepoint_counter = 0
        # [M7.1 2026-06-05] commit 钩子列表（外部订阅）
        self._commit_hooks: List[Callable] = []

        self._stats = {
            "submitted_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "timeout_count": 0,
            "queue_full_count": 0,
            "total_wait_time": 0.0,
            "total_exec_time": 0.0,
            "checkpoint_count": 0,
        }
        self._recent_latencies: List[float] = []
        self._max_recent = 100

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    def start(self):
        if DISABLE_WRITE_QUEUE:
            logger.info("WriteQueue disabled (test mode)")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._write_loop,
            name="sqlite-writer",
            daemon=True,
        )
        self._thread.start()
        logger.info("WriteQueue started")

    def stop(self, timeout: float = 10.0):
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("WriteQueue stopped")

    def submit(
        self,
        func: Callable,
        *args,
        timeout: float = None,
        **kwargs,
    ) -> Future:
        if DISABLE_WRITE_QUEUE:
            future = Future()
            try:
                if self._pool and hasattr(self._pool, '_writer_conn') and self._pool._writer_conn:
                    conn = self._pool._writer_conn.connection
                    result = func(conn, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
            return future

        timeout = timeout if timeout is not None else self._config.submit_timeout
        op = WriteOperation(func=func, args=args, kwargs=kwargs)

        try:
            self._queue.put(op, timeout=timeout)
            self._stats["submitted_count"] += 1
        except Exception:
            self._stats["queue_full_count"] += 1
            op.future.set_exception(
                TimeoutError("Write queue is full (depth={0})".format(self.depth))
            )

        return op.future

    def submit_and_wait(
        self,
        func: Callable,
        *args,
        submit_timeout: float = None,
        result_timeout: float = None,
        **kwargs,
    ) -> Any:
        submit_timeout = (
            submit_timeout
            if submit_timeout is not None
            else self._config.submit_timeout
        )
        result_timeout = (
            result_timeout
            if result_timeout is not None
            else self._config.operation_timeout
        )
        if DISABLE_WRITE_QUEUE:
            if self._pool and hasattr(self._pool, '_writer_conn') and self._pool._writer_conn:
                conn = self._pool._writer_conn.connection
                return func(conn, *args, **kwargs)
            return func(*args, **kwargs)
        future = self.submit(func, *args, timeout=submit_timeout, **kwargs)
        return future.result(timeout=result_timeout)

    def execute_write(
        self,
        sql: str,
        params: Optional[tuple] = None,
        auto_commit: bool = True,
    ) -> Any:
        def _do_execute(conn):
            cursor = conn.cursor()
            if params:
                result = cursor.execute(sql, params)
            else:
                result = cursor.execute(sql)
            if auto_commit and not self._in_transaction:
                conn.commit()
            return result

        return self.submit_and_wait(_do_execute)

    def begin_transaction(self):
        """
        开始显式事务

        优化：增加事务状态检测，避免嵌套事务问题。

        [V007.15 L3] 加 phantom TX 检测:
        - 用 savepoint probe 探测 SQLite 真实状态
        - 如果 SQLite in tx 但 Python state=False → phantom, 强制 ROLLBACK
        - 然后正常 BEGIN IMMEDIATE
        """
        if self._in_transaction:
            # 已经标记 in_tx, 跳过
            metrics_inc('begin_skipped_already_in_tx')
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
                metrics_inc('phantom_tx_detected')
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                self._in_transaction = False

            try:
                # 2026-06-05 修复：使用 BEGIN IMMEDIATE 防止多进程写冲突
                conn.execute("BEGIN IMMEDIATE")
                self._in_transaction = True
                metrics_inc('begin_success')
                logger.debug("WriteQueue: Transaction started")
            except Exception as e:
                error_str = str(e).lower()
                if "cannot start a transaction within a transaction" in error_str:
                    # 连接已经在事务中，更新状态
                    logger.warning("WriteQueue: Connection already in transaction, updating state")
                    self._in_transaction = True
                elif "locked" in error_str or "busy" in error_str:
                    metrics_inc('begin_locked')
                    log_tx_event('begin', None, 'locked', str(e))
                    logger.error("WriteQueue: Failed to begin transaction (locked): %s", error_str)
                    raise
                else:
                    logger.error("WriteQueue: Failed to begin transaction: %s", error_str)
                    raise

        self.submit_and_wait(_do_begin)

    def commit(self):
        def _do_commit(conn):
            conn.commit()
            self._in_transaction = False
            self._commit_counter += 1
            if self._commit_counter >= self._config.checkpoint_interval:
                self._commit_counter = 0
                try:
                    conn.execute(
                        "PRAGMA wal_checkpoint({0})".format(
                            self._config.checkpoint_mode
                        )
                    )
                    self._stats["checkpoint_count"] += 1
                    try:
                        from meta.core.db_health_monitor import get_monitor
                        monitor = get_monitor()
                        monitor.record_checkpoint()
                        snap = monitor.collect_snapshot()
                        if snap.warnings:
                            logger.warning("DB Health after checkpoint: %s", snap.warnings)
                    except Exception:
                        pass
                except Exception:
                    pass

        self.submit_and_wait(_do_commit)
        # [M7.1 2026-06-05] commit 成功后触发钩子
        self._fire_commit_hooks()

    def add_commit_hook(self, hook: Callable) -> None:
        """[M7.1] 注册 commit 钩子。
        
        钩子签名: hook(op: WriteOperation) -> None
        钩子在 commit() 成功返回后调用，异常被隔离不影响后续钩子。
        """
        self._commit_hooks.append(hook)

    def _fire_commit_hooks(self) -> None:
        """[M7.1] 触发所有 commit 钩子。
        
        取最近一次提交的 WriteOperation 上下文（如果有）。
        """
        if not self._commit_hooks:
            return
        # 取最近一个 entity_type 非空的 op（来自 _last_operations 列表）
        last_ops = getattr(self, '_last_operations', None) or []
        for op in last_ops:
            if not op.entity_type:
                continue
            for hook in self._commit_hooks:
                try:
                    hook(op)
                except Exception as e:
                    logger.error(f"[WriteQueue.M7.1] commit hook error: {e}")

    def rollback(self):
        def _do_rollback(conn):
            conn.rollback()
            self._in_transaction = False

        self.submit_and_wait(_do_rollback)

    def set_savepoint(self, name: str = None) -> str:
        self._savepoint_counter += 1
        sp_name = name or "sp_{0}".format(self._savepoint_counter)

        def _do_savepoint(conn):
            conn.execute("SAVEPOINT {0}".format(sp_name))

        self.submit_and_wait(_do_savepoint)
        return sp_name

    def rollback_to(self, savepoint_name: str):
        def _do_rollback_to(conn):
            conn.execute("ROLLBACK TO SAVEPOINT {0}".format(savepoint_name))

        self.submit_and_wait(_do_rollback_to)

    def release_savepoint(self, savepoint_name: str):
        def _do_release(conn):
            conn.execute("RELEASE SAVEPOINT {0}".format(savepoint_name))

        self.submit_and_wait(_do_release)

    def checkpoint(self, mode: str = "TRUNCATE"):
        def _do_checkpoint(conn):
            conn.execute("PRAGMA wal_checkpoint({0})".format(mode))
            self._stats["checkpoint_count"] += 1

        self.submit_and_wait(_do_checkpoint)

    def flush(self, timeout: float = 30.0):
        barrier = threading.Event()

        def _flush_op(_conn):
            barrier.set()

        self.submit(_flush_op)
        barrier.wait(timeout=timeout)

    def _write_loop(self):
        logger.debug("Write thread started")
        while self._running:
            try:
                try:
                    op = self._queue.get(timeout=1.0)
                except Empty:
                    continue

                if op is None:
                    continue

                wait_time = time.time() - op.submitted_at
                self._stats["total_wait_time"] += wait_time

                # [V007.20 2026-07-06] 撞锁重试机制
                # 背景: yonaa 1w+ annotation import 卡 40% (HANDOFF_V007_20_BUSY_TIMEOUT.md)
                #       WriteQueue 单写线程 + audit_async_queue + async_audit_writer 三条
                #       路径同时写 audit_logs, 撞锁 (SQLITE_BUSY 'database is locked') 频率高.
                #       之前: 撞锁 1 次就 fail, audit 写失败链递归放大.
                # 修法: 撞锁视为暂时性错误, sleep + 重试 N 次 (指数 backoff)
                #       配合 busy_timeout=30000 (sql_connection_pool.py V007.20 L4)
                # 注意: 不用 op.execute() 因为 WriteOperation.execute 失败时
                #       永久 set_exception 到 future (第 2 次会 raise InvalidStateError).
                #       retry 时直接调 op.func 拿到结果, 全部 attempt 成功后才 set_result.
                _retryable_errors = ("database is locked", "disk i/o error", "database is busy")
                _max_retries = 5
                _op_success = False
                for attempt in range(_max_retries + 1):
                    try:
                        op.started_at = time.time()
                        with self._pool.writer() as conn:
                            result = op.func(conn, *op.args, **op.kwargs)
                        op.completed_at = time.time()
                        # 全部 attempt 成功后才标记 future 完成
                        if not op.future.done():
                            op.future.set_result(result)
                        _op_success = True
                        exec_time = op.completed_at - op.started_at
                        self._stats["completed_count"] += 1
                        self._stats["total_exec_time"] += exec_time
                        self._recent_latencies.append(exec_time)
                        if len(self._recent_latencies) > self._max_recent:
                            self._recent_latencies.pop(0)
                        if attempt > 0:
                            self._stats["retry_success_count"] = \
                                self._stats.get("retry_success_count", 0) + 1
                            logger.info(
                                "WriteQueue retry success after %d attempts: %s",
                                attempt, str(op.func)[:80]
                            )
                        break  # 成功, 退出 retry loop
                    except Exception as e:
                        err_str = str(e).lower()
                        is_retryable = any(re in err_str for re in _retryable_errors)
                        if is_retryable and attempt < _max_retries:
                            # 撞锁重试: 指数 backoff 50ms * 2^attempt + 随机抖动
                            import random as _random
                            delay = 0.05 * (2 ** attempt) + _random.uniform(0, 0.02)
                            self._stats["retry_count"] = \
                                self._stats.get("retry_count", 0) + 1
                            logger.warning(
                                "WriteQueue retryable error (attempt %d/%d, sleep %.3fs): %s | op=%s",
                                attempt + 1, _max_retries, delay, err_str,
                                str(op.func)[:80]
                            )
                            time.sleep(delay)
                            # 注意: 不重新入队 (_queue.put), 立即重试避免其他 op 插队
                            # 因为撞锁通常很快释放 (其他 connection commit)
                            continue
                        # 不可重试 或 已达 max_retries
                        if not op.future.done():
                            op.future.set_exception(e)
                        self._stats["failed_count"] += 1
                        logger.error("Write operation failed: %s", str(e))
                        logger.debug("Traceback: %s", traceback.format_exc())
                        break

            except Exception as e:
                logger.error("Write loop error: %s", str(e))

        logger.debug("Write thread exiting")

    def get_stats(self) -> Dict[str, Any]:
        stats = self._stats.copy()
        stats["depth"] = self.depth
        stats["in_transaction"] = self._in_transaction
        stats["commit_counter"] = self._commit_counter

        completed = stats["completed_count"]
        if completed > 0:
            stats["avg_wait_time_ms"] = (
                stats["total_wait_time"] / (stats["submitted_count"] or 1) * 1000
            )
            stats["avg_exec_time_ms"] = stats["total_exec_time"] / completed * 1000
        else:
            stats["avg_wait_time_ms"] = 0.0
            stats["avg_exec_time_ms"] = 0.0

        if self._recent_latencies:
            sorted_lat = sorted(self._recent_latencies)
            n = len(sorted_lat)
            stats["p50_exec_time_ms"] = sorted_lat[n // 2] * 1000
            stats["p95_exec_time_ms"] = sorted_lat[int(n * 0.95)] * 1000
            stats["p99_exec_time_ms"] = sorted_lat[int(n * 0.99)] * 1000
        else:
            stats["p50_exec_time_ms"] = 0.0
            stats["p95_exec_time_ms"] = 0.0
            stats["p99_exec_time_ms"] = 0.0

        if completed > 0:
            window = 60.0
            stats["throughput_per_sec"] = completed / window
        else:
            stats["throughput_per_sec"] = 0.0

        return stats

