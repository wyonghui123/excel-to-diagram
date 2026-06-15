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
        # [v3.18 Layer 1] thread-local storage: 每个 worker thread 自己开 SQLite 连接,
        # 避免跨线程访问 main thread 创建的 SQLite connection (不同 Python 解释器
        # 对 sqlite3 跨线程限制不同 — pythoncore-3.14-64 严, WindowsApps python 宽松)
        self._tls = threading.local()
        if self._running and not _TESTING_MODE:
            self._start_workers()
        elif _TESTING_MODE:
            self._running = False

    def set_data_source(self, data_source):
        self._ds = data_source

    def _get_thread_ds(self):
        """[v3.18 Layer 1] 拿到当前 thread 专属的 data_source.

        优先用 thread-local (worker 自己开的), 失败回退到主 ds.
        """
        # 1) thread-local 优先 (worker 自己开的 connection, 跨线程安全)
        tls_ds = getattr(self._tls, 'ds', None)
        if tls_ds is not None:
            return tls_ds
        # 2) 回退: 用主 ds (audit_logger 自己管的, 可能是 main thread 的)
        if self._ds is not None:
            return self._ds
        return None

    def _open_thread_local_connection(self, audit_fn):
        """[v3.18 Layer 1] 给当前 worker thread 打开独立 SQLite 连接.

        策略: 提取 audit_fn 闭包里的 action_executor.ds 的 path, 重建 sqlite3 连接.
        跨 Python 解释器 (pythoncore-3.14-64 vs WindowsApps) 都用 check_same_thread=False
        + 自管 connection, 避免 'SQLite objects created in a thread...' 异常.
        """
        try:
            import sqlite3 as _sqlite3
            # 优先从闭包 audit_fn 里拿 ds 的 db path
            db_path = None
            try:
                # audit_fn 是 lambda, 闭包 cell 里有 self (action_executor)
                cells = audit_fn.__closure__ or []
                for cell in cells:
                    obj = cell.cell_contents
                    if hasattr(obj, 'ds') and obj.ds is not None:
                        # obj 是 action_executor, 拿 ds.db_path
                        candidate = getattr(obj.ds, 'database', None) or getattr(obj.ds, 'db_path', None)
                        if candidate:
                            db_path = candidate
                            break
            except Exception:
                pass
            # 兜底: 从 _ds 拿
            if not db_path and self._ds is not None:
                db_path = getattr(self._ds, 'database', None) or getattr(self._ds, 'db_path', None)
            if not db_path:
                # 最后兜底: 用默认 path
                from pathlib import Path
                db_path = str(Path(__file__).parent.parent / 'architecture.db')

            # 打开独立连接 (worker thread 自己的, 跨线程安全)
            conn = _sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            # 包成 ds-like 适配器, 跟 action_executor.ds 接口一致
            ds = _ThreadLocalDS(conn, db_path)
            self._tls.ds = ds
            return ds
        except Exception as e:
            logger.error("Failed to open thread-local SQLite connection: %s", str(e))
            return None

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
                # [v3.18 Layer 1] 在 worker thread 上, 第一次执行前打开 thread-local 连接.
                # 解决 'SQLite objects created in a thread can only be used in that same thread'
                if getattr(self._tls, 'ds', None) is None:
                    self._open_thread_local_connection(task['fn'])

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
        # [v3.18 Layer 1] 优先用 thread-local ds, 回退到主 ds
        thread_ds = self._get_thread_ds()
        for attempt in range(max_retries):
            try:
                if not _read_is_connected(thread_ds):
                    logger.warning("Database not connected (thread=%s), skipping audit write", threading.current_thread().name)
                    return False

                in_txn = getattr(thread_ds, 'in_transaction', False)

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
                elif hasattr(thread_ds, 'begin_transaction'):
                    thread_ds.begin_transaction()
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
                        thread_ds.commit()
                    except Exception:
                        try:
                            thread_ds.rollback()
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

        self._persist_failed(
            audit_fn, trace_id, transaction_id, str(last_error),
            user_id=user_id, user_name=user_name,
            ip_address=ip_address, user_agent=user_agent,
        )
        return False

    def _persist_failed(self, audit_fn: Callable, trace_id: str = None,
                        transaction_id: str = None, error_message: str = "",
                        user_id: Any = None, user_name: str = None,
                        ip_address: str = None, user_agent: str = None):
        with self._stats_lock:
            self._stats['failed'] += 1

        logger.error(
            "Audit write failed after %d retries: trace_id=%s, error=%s",
            AUDIT_MAX_RETRIES, trace_id, error_message
        )

        # [v3.18 Layer 3] 从 audit_fn 闭包提取 obj 信息, 强制写 AUDIT_WRITE_FAILED 一条 audit
        obj_info = self._extract_obj_info(audit_fn)

        try:
            self._write_failed_record(
                trace_id, transaction_id, error_message,
                obj_info=obj_info,
                user_id=user_id, user_name=user_name,
                ip_address=ip_address, user_agent=user_agent,
            )
        except Exception as e:
            logger.error("Failed to persist audit failure record: %s", str(e))

    @staticmethod
    def _extract_obj_info(audit_fn: Callable) -> Dict[str, Any]:
        """[v3.18 Layer 3] 从 audit_fn 闭包 cell 里提取 object_type/object_id/action.

        audit_fn 是 action_executor._do_create 内部定义的 lambda, 闭包 cell 里
        有 meta_object / last_id / data 等. 用 inspect 解出来给 AUDIT_WRITE_FAILED 用.
        """
        info: Dict[str, Any] = {"object_type": "__audit_failure__", "object_id": "0", "action": "UNKNOWN"}
        try:
            if not callable(audit_fn):
                return info
            cells = audit_fn.__closure__ or []
            for cell in cells:
                try:
                    obj = cell.cell_contents
                except Exception:
                    continue
                # obj 是 action_executor 实例
                if hasattr(obj, 'ds') and hasattr(obj, 'audit_logger'):
                    # 这是 self, 从它看能不能拿到更多 — 不一定有
                    continue
                # 拿 cell 内的字符串/对象 (meta_object.id, last_id, data, etc.)
                if isinstance(obj, str) and obj in ('CREATE', 'UPDATE', 'DELETE'):
                    info['action'] = obj
                # 找 meta_object-like (有 .id 属性 + .table_name 之类)
                if hasattr(obj, 'id') and hasattr(obj, 'table_name') and callable(getattr(obj, 'get_persistent_fields', None)):
                    try:
                        info['object_type'] = str(obj.id)
                    except Exception:
                        pass
                # 找 last_id-like (int 或 str)
                if isinstance(obj, (int, str)) and not isinstance(obj, bool):
                    # 可能是 last_id (假设在 meta_object 之后)
                    if info['object_type'] != '__audit_failure__':
                        try:
                            info['object_id'] = str(obj)
                        except Exception:
                            pass
        except Exception:
            pass
        return info

    def _write_failed_record(self, trace_id: str = None,
                             transaction_id: str = None,
                             error_message: str = "",
                             obj_info: Dict[str, Any] = None,
                             user_id: Any = None, user_name: str = None,
                             ip_address: str = None, user_agent: str = None):
        # [v3.18 Layer 1] 优先用 thread-local ds
        thread_ds = self._get_thread_ds()
        if thread_ds is None:
            return
        if obj_info is None:
            obj_info = {"object_type": "__audit_failure__", "object_id": "0", "action": "UNKNOWN"}

        # [v3.18 Layer 3] 用 obj_info 填 object_type/id/action, 不再写死的 __audit_failure__
        failed_record = {
            "object_type": obj_info.get("object_type", "__audit_failure__"),
            "object_id": obj_info.get("object_id", "0"),
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": json.dumps({
                "original_action": obj_info.get("action", "UNKNOWN"),
                "error": error_message[:500] if error_message else "",
            }, ensure_ascii=False),
            "user_id": user_id,
            "user_name": user_name or "system",
            "ip_address": ip_address or "",
            "user_agent": user_agent or "",
            "created_at": datetime.now().isoformat(),
            "extra_data": json.dumps({
                "original_trace_id": trace_id,
                "original_transaction_id": transaction_id,
                "original_object_type": obj_info.get("object_type"),
                "original_object_id": obj_info.get("object_id"),
                "original_action": obj_info.get("action"),
                "failure_kind": "AUDIT_WRITE_FAILED",
            }, ensure_ascii=False),
            "trace_id": trace_id,
            "transaction_id": transaction_id,
            "status": "failed",
            "retry_count": AUDIT_MAX_RETRIES,
            "error_message": error_message[:500] if error_message else "",
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
            # [v3.18 FR-005] 标记 outcome=failure
            "outcome": "failure",
            # [v3.18 FR-003/004] system category + ERROR level
            "log_category": "system",
            "log_level": "ERROR",
        }

        try:
            thread_ds.insert("audit_logs", failed_record)
            if not thread_ds.in_transaction:
                thread_ds.commit()
            logger.warning(
                "[Layer 3] AUDIT_WRITE_FAILED recorded: object_type=%s object_id=%s action=%s error=%s",
                obj_info.get("object_type"),
                obj_info.get("object_id"),
                obj_info.get("action"),
                (error_message or "")[:200],
            )
        except Exception as e:
            logger.error("Failed to insert AUDIT_WRITE_FAILED record: %s", str(e))

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


class _ThreadLocalDS:
    """[v3.18 Layer 1] worker thread 专用的 ds 适配器.

    把 sqlite3.Connection 包装成跟 action_executor.ds 兼容的接口
    (insert / execute / commit / in_transaction / is_connected / begin_transaction / rollback),
    解决 'SQLite objects created in a thread can only be used in that same thread' 问题.
    """
    def __init__(self, conn, db_path):
        self._conn = conn
        self.database = db_path
        self.db_path = db_path
        self._in_txn = False

    @property
    def is_connected(self):
        try:
            self._conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    @property
    def in_transaction(self):
        return self._in_txn

    def begin_transaction(self):
        try:
            self._conn.execute("BEGIN")
            self._in_txn = True
        except Exception:
            self._in_txn = False

    def commit(self):
        try:
            self._conn.commit()
        finally:
            self._in_txn = False

    def rollback(self):
        try:
            self._conn.rollback()
        finally:
            self._in_txn = False

    def execute(self, sql, params=None):
        """返回 sqlite3.Cursor (兼容 fetchall / fetchone)"""
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)

    def executemany(self, sql, seq):
        return self._conn.executemany(sql, seq)

    def insert(self, table, record):
        """兼容 ds.insert(table, dict) — 跟 SqliteDataSource 同语义."""
        if not record:
            return
        cols = list(record.keys())
        placeholders = ','.join('?' * len(cols))
        col_list = ','.join(f'"{c}"' for c in cols)
        values = [record[c] for c in cols]
        sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
        cur = self._conn.execute(sql, values)
        return cur.lastrowid

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
