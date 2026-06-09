# -*- coding: utf-8 -*-
"""
异步审计日志写入器

参考 SAP V2 Update 模式：
- 业务事务提交后，审计日志通过线程池异步写入
- 审计写入失败不影响业务结果
- 支持重试和失败记录持久化
- 队列满时降级为同步写入
"""

import os
import time
import queue
import logging
import threading
import sqlite3
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Dict, Any

logger = logging.getLogger(__name__)

AUDIT_ASYNC_ENABLED = os.environ.get('AUDIT_ASYNC_ENABLED', 'true').lower() in ('true', '1', 'yes')
AUDIT_ASYNC_MAX_WORKERS = int(os.environ.get('AUDIT_ASYNC_MAX_WORKERS', '2'))
AUDIT_ASYNC_QUEUE_SIZE = int(os.environ.get('AUDIT_ASYNC_QUEUE_SIZE', '1000'))
AUDIT_MAX_RETRIES = int(os.environ.get('AUDIT_MAX_RETRIES', '3'))
AUDIT_RETRY_DELAY_BASE = float(os.environ.get('AUDIT_RETRY_DELAY_BASE', '0.1'))
_TESTING_MODE = os.environ.get('TESTING', '').lower() in ('true', '1', 'yes')


class AsyncAuditWriter:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, data_source=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(data_source)
        return cls._instance

    def _init(self, data_source=None):
        self._ds = data_source
        self._queue = queue.Queue(maxsize=AUDIT_ASYNC_QUEUE_SIZE)
        self._running = not os.environ.get('DISABLE_ASYNC_AUDIT_WRITER', '').lower() in ('true', '1', 'yes')
        self._workers = []
        self._stats = {
            'submitted': 0,
            'completed': 0,
            'failed': 0,
            'queue_size': 0,
        }
        self._stats_lock = threading.Lock()
        if self._running and not _TESTING_MODE:
            self._start_workers()
        elif _TESTING_MODE:
            self._running = False

    def set_data_source(self, data_source):
        self._ds = data_source

    def _start_workers(self):
        for i in range(AUDIT_ASYNC_MAX_WORKERS):
            t = threading.Thread(
                target=self._worker,
                name=f"audit-writer-{i}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
        logger.info(
            "AsyncAuditWriter started: workers=%d, queue_size=%d",
            AUDIT_ASYNC_MAX_WORKERS, AUDIT_ASYNC_QUEUE_SIZE
        )

    def submit(self, audit_fn: Callable, trace_id: str = None,
               transaction_id: str = None, user_id: Any = None,
               user_name: str = None, ip_address: str = None,
               user_agent: str = None) -> bool:
        if not callable(audit_fn):
            logger.error(
                "[CRITICAL] submit() received non-callable audit_fn: type=%s, value=%s, trace_id=%s. "
                "This indicates a bug in the caller - a boolean or other non-function value was passed "
                "instead of a callable function.",
                type(audit_fn).__name__, audit_fn, trace_id
            )
            import traceback
            logger.error("Call stack:\n%s", ''.join(traceback.format_stack()))
            with self._stats_lock:
                self._stats['failed'] += 1
            return False

        if not AUDIT_ASYNC_ENABLED or self._ds is None or not self._running:
            return self._write_sync(
                audit_fn, trace_id, transaction_id,
                user_id=user_id, user_name=user_name,
                ip_address=ip_address, user_agent=user_agent,
            )

        task = {
            'fn': audit_fn,
            'trace_id': trace_id,
            'transaction_id': transaction_id,
            'user_id': user_id,
            'user_name': user_name,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'submitted_at': time.time(),
        }

        try:
            self._queue.put_nowait(task)
            with self._stats_lock:
                self._stats['submitted'] += 1
            return True
        except queue.Full:
            logger.warning("Audit queue full, falling back to sync write")
            return self._write_sync(
                audit_fn, trace_id, transaction_id,
                user_id=user_id, user_name=user_name,
                ip_address=ip_address, user_agent=user_agent,
            )

    def _write_sync(self, audit_fn: Callable, trace_id: str = None,
                    transaction_id: str = None, user_id: Any = None,
                    user_name: str = None, ip_address: str = None,
                    user_agent: str = None) -> bool:
        result = self._write_with_retry(
            audit_fn, trace_id, transaction_id,
            user_id=user_id, user_name=user_name,
            ip_address=ip_address, user_agent=user_agent,
            is_fallback=True,
        )
        return result

    def _worker(self):
        while self._running:
            try:
                task = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self._write_with_retry(
                    task['fn'],
                    trace_id=task.get('trace_id'),
                    transaction_id=task.get('transaction_id'),
                    user_id=task.get('user_id'),
                    user_name=task.get('user_name'),
                    ip_address=task.get('ip_address'),
                    user_agent=task.get('user_agent'),
                )
            except Exception as e:
                logger.error("Audit worker unexpected error: %s", str(e))
            finally:
                self._queue.task_done()

    def _write_with_retry(self, audit_fn: Callable, trace_id: str = None,
                          transaction_id: str = None, is_fallback: bool = False,
                          user_id: Any = None, user_name: str = None,
                          ip_address: str = None, user_agent: str = None) -> bool:
        """
        带重试的审计日志写入

        优化：检测是否已在事务中，避免事务嵌套错误。
        审计日志写入不需要事务保护，直接执行即可。
        """
        # [FIX Bug1 2026-06-09] is_connected 是 @property 属性 (返回 bool),
        # 不是方法。当作方法调用会抛 'bool' object is not callable，导致 audit_fn 永远不执行。
        # 兼容两种定义：@property 和普通方法（用 callable 探测）。
        if not callable(audit_fn):
            logger.error(
                "[CRITICAL] _write_with_retry() received non-callable audit_fn: type=%s, value=%s, trace_id=%s. "
                "Caller likely passed a boolean return value instead of a function reference.",
                type(audit_fn).__name__, audit_fn, trace_id
            )
            with self._stats_lock:
                self._stats['failed'] += 1
            return False

        def _read_is_connected(ds):
            """读取 ds.is_connected 的当前值，兼容 @property 和 method 两种定义。"""
            if ds is None:
                return True  # ds 为 None 时跳过连接检查
            attr = getattr(ds, 'is_connected', None)
            if attr is None:
                return True
            # @property: attr 本身是 bool；method: attr 是 callable，返回 bool
            if callable(attr):
                try:
                    return bool(attr())
                except Exception:
                    return True
            return bool(attr)

        last_error = None
        max_retries = 1 if _TESTING_MODE else AUDIT_MAX_RETRIES
        for attempt in range(max_retries):
            try:
                if not _read_is_connected(self._ds):
                    logger.warning("Database not connected, skipping audit write")
                    return False

                in_txn = getattr(self._ds, 'in_transaction', False)

                if in_txn:
                    if not callable(audit_fn):
                        logger.error(
                            "[CRITICAL] audit_fn non-callable in in_txn branch: "
                            "type=%s, trace_id=%s", type(audit_fn).__name__, trace_id
                        )
                        with self._stats_lock:
                            self._stats['failed'] += 1
                        return False
                    logger.debug("Already in transaction, executing audit_fn directly")
                    audit_fn(trace_id=trace_id, transaction_id=transaction_id,
                             user_id=user_id, user_name=user_name,
                             ip_address=ip_address, user_agent=user_agent)
                elif hasattr(self._ds, 'begin_transaction'):
                    self._ds.begin_transaction()
                    try:
                        if not callable(audit_fn):
                            logger.error(
                                "[CRITICAL] audit_fn non-callable in transaction branch: "
                                "type=%s, trace_id=%s", type(audit_fn).__name__, trace_id
                            )
                            with self._stats_lock:
                                self._stats['failed'] += 1
                            return False
                        audit_fn(trace_id=trace_id, transaction_id=transaction_id,
                                 user_id=user_id, user_name=user_name,
                                 ip_address=ip_address, user_agent=user_agent)
                        self._ds.commit()
                    except Exception:
                        try:
                            self._ds.rollback()
                        except Exception:
                            pass
                        raise
                else:
                    if not callable(audit_fn):
                        logger.error(
                            "[CRITICAL] audit_fn became non-callable before else branch: "
                            "type=%s, value=%r, trace_id=%s",
                            type(audit_fn).__name__, audit_fn, trace_id
                        )
                        with self._stats_lock:
                            self._stats['failed'] += 1
                        return False
                    audit_fn(trace_id=trace_id, transaction_id=transaction_id,
                             user_id=user_id, user_name=user_name,
                             ip_address=ip_address, user_agent=user_agent)

                with self._stats_lock:
                    if is_fallback:
                        self._stats['fallback_sync'] += 1
                    else:
                        self._stats['completed'] += 1
                return True
            except TypeError as te:
                error_str = str(te)
                if "'bool' object is not callable" in error_str or "not callable" in error_str:
                    logger.error(
                        "[CRITICAL] TypeError in audit_fn call: %s. "
                        "audit_fn type=%s, trace_id=%s. "
                        "This confirms the caller passed a non-callable value.",
                        te, type(audit_fn).__name__, trace_id
                    )
                    import traceback
                    logger.error("Call stack:\n%s", ''.join(traceback.format_stack()))
                    last_error = te
                    break
                else:
                    last_error = te
                    if attempt < max_retries - 1:
                        continue
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                if "closed database" in error_str.lower() or "cannot operate on a closed" in error_str.lower():
                    logger.warning("Database closed, skipping audit write retry")
                    with self._stats_lock:
                        self._stats['failed'] += 1
                    return False
                
                if "cannot start a transaction within a transaction" in error_str:
                    logger.warning("Transaction nesting detected, trying direct write")
                    try:
                        if not callable(audit_fn):
                            logger.error(
                                "[CRITICAL] audit_fn non-callable in nesting retry: "
                                "type=%s, trace_id=%s", type(audit_fn).__name__, trace_id
                            )
                            with self._stats_lock:
                                self._stats['failed'] += 1
                            return False
                        audit_fn(trace_id=trace_id, transaction_id=transaction_id,
                                 user_id=user_id, user_name=user_name,
                                 ip_address=ip_address, user_agent=user_agent)
                        with self._stats_lock:
                            if is_fallback:
                                self._stats['fallback_sync'] += 1
                            else:
                                self._stats['completed'] += 1
                        return True
                    except Exception as e2:
                        last_error = e2
                
                if attempt < max_retries - 1:
                    delay = 0 if _TESTING_MODE else AUDIT_RETRY_DELAY_BASE * (attempt + 1)
                    if delay > 0:
                        logger.debug("Audit write attempt %d failed, retrying in %.2fs: %s", 
                                    attempt + 1, delay, error_str)
                        time.sleep(delay)

        self._persist_failed(audit_fn, trace_id, transaction_id, str(last_error))
        return False

    def _persist_failed(self, audit_fn: Callable, trace_id: str = None,
                        transaction_id: str = None, error_message: str = ""):
        with self._stats_lock:
            self._stats['failed'] += 1

        logger.error(
            "Audit write failed after %d retries: trace_id=%s, error=%s",
            AUDIT_MAX_RETRIES, trace_id, error_message
        )

        try:
            self._write_failed_record(trace_id, transaction_id, error_message)
        except Exception as e:
            logger.error("Failed to persist audit failure record: %s", str(e))

    def _write_failed_record(self, trace_id: str = None,
                             transaction_id: str = None,
                             error_message: str = ""):
        if self._ds is None:
            return

        failed_record = {
            "object_type": "__audit_failure__",
            "object_id": 0,
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": "",
            "user_id": None,
            "user_name": "system",
            "ip_address": "",
            "user_agent": "",
            "created_at": datetime.now().isoformat(),
            "extra_data": json.dumps({
                "original_trace_id": trace_id,
                "original_transaction_id": transaction_id,
            }),
            "trace_id": trace_id,
            "transaction_id": transaction_id,
            "status": "failed",
            "retry_count": AUDIT_MAX_RETRIES,
            "error_message": error_message,
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
        }

        try:
            self._ds.insert("audit_logs", failed_record)
            if not self._ds.in_transaction:
                self._ds.commit()
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            stats = dict(self._stats)
        stats['queue_size'] = self._queue.qsize()
        stats['queue_capacity'] = AUDIT_ASYNC_QUEUE_SIZE
        stats['workers'] = len(self._workers)
        stats['running'] = self._running
        return stats

    def flush(self, timeout: float = 5.0) -> bool:
        try:
            if _TESTING_MODE:
                    deadline = time.time() + min(timeout, 2.0)
                    while not self._queue.empty() and time.time() < deadline:
                        try:
                            task = self._queue.get_nowait()
                            try:
                                self._write_with_retry(
                                    task['fn'],
                                    task.get('trace_id'),
                                    task.get('transaction_id'),
                                    user_id=task.get('user_id'),
                                    user_name=task.get('user_name'),
                                    ip_address=task.get('ip_address'),
                                    user_agent=task.get('user_agent'),
                                )
                            except Exception:
                                pass
                        except queue.Empty:
                            break
                        finally:
                            try:
                                self._queue.task_done()
                            except Exception:
                                pass
                    return True
            self._queue.join()
            return True
        except Exception:
            return False

    def shutdown(self, timeout: float = 10.0):
        self._running = False
        try:
            if _TESTING_MODE:
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                        self._queue.task_done()
                    except queue.Empty:
                        break
            else:
                self._queue.join()
        except Exception:
            pass

        for t in self._workers:
            t.join(timeout=timeout / len(self._workers) if self._workers else timeout)

        logger.info("AsyncAuditWriter shutdown complete, stats: %s", self.get_stats())

    @classmethod
    def reset(cls):
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.shutdown(timeout=2.0 if _TESTING_MODE else 10.0)
                except Exception:
                    pass
                cls._instance = None


async_audit_writer = AsyncAuditWriter()
