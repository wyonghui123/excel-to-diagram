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
        """
        if self._in_transaction:
            logger.debug("WriteQueue: Already in transaction, skipping BEGIN")
            return
        
        def _do_begin(conn):
            try:
                # 检查连接的实际事务状态
                # SQLite没有直接的PRAGMA查询事务状态，但我们可以通过尝试BEGIN来检测
                # 2026-06-05 修复：使用 BEGIN IMMEDIATE 防止多进程写冲突
                conn.execute("BEGIN IMMEDIATE")
                self._in_transaction = True
                logger.debug("WriteQueue: Transaction started")
            except Exception as e:
                error_str = str(e)
                if "cannot start a transaction within a transaction" in error_str:
                    # 连接已经在事务中，更新状态
                    logger.warning("WriteQueue: Connection already in transaction, updating state")
                    self._in_transaction = True
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

                try:
                    with self._pool.writer() as conn:
                        op.execute(conn)
                    self._stats["completed_count"] += 1
                    exec_time = op.completed_at - op.started_at
                    self._stats["total_exec_time"] += exec_time
                    self._recent_latencies.append(exec_time)
                    if len(self._recent_latencies) > self._max_recent:
                        self._recent_latencies.pop(0)
                except Exception as e:
                    self._stats["failed_count"] += 1
                    logger.error("Write operation failed: %s", str(e))
                    logger.debug("Traceback: %s", traceback.format_exc())

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
