# -*- coding: utf-8 -*-
"""V007.41 safe_connect - 统一 L0 裸连接工厂

[V007.41 BUG-FIX] 背景:
  - V007.40 在 17 个文件复制 timeout + check_same_thread + busy_timeout 三件套
  - V007.41 集中到本模块, 强制全项目唯一入口
  - 写连接强制走 bo_framework.transaction(), 根治 silent partial commit

设计原则:
  - 单一入口: 所有 sqlite3.connect(...) 必须走这里 (verify_v007_41.py 强制)
  - 事务感知: 写连接强制在外层事务中; 只读连接可选
  - 可观测: 每次调用记 metric (read/write/no_tx/unknown 分类)
  - 可降级: 探测失败 warn + metric, 不阻塞业务

用法:
    # 只读 (V1 直连)
    from meta.core.safe_connect import safe_connect_for_read
    with safe_connect_for_read(db_path) as conn:
        cursor = conn.execute("SELECT ...")

    # 写 (V3, 必须在外层事务内)
    from meta.core.safe_connect import safe_connect_for_write
    with bo_framework.transaction() as txn:
        with safe_connect_for_write(db_path) as conn:
            cursor = conn.execute("INSERT ...")
            # 自动 commit 由外层 txn 负责, 不要 conn.commit()!

    # 兼容 (V0, 临时/紧急, metric 标记)
    from meta.core.safe_connect import safe_connect
    with safe_connect(db_path, mode="write_force_no_tx") as conn:
        ...
"""
from __future__ import annotations

import logging
import os
import random as _random
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterator, Optional

from meta.core.sqlite_tx_state import get_tx_state, TxState

logger = logging.getLogger(__name__)


def _bump_counter(counter_key: str, value: int = 1) -> None:
    """递增 OBS_COUNTERS 中对应 metric, 失败降级 log."""
    try:
        # Lazy import: 避免 safe_connect 被加载时强制 observability 初始化
        from meta.core.observability import metrics_inc
        metrics_inc(counter_key, value)
    except Exception as e:
        logger.debug(f"[V007.41] safe_connect metric bump failed (degraded): {e}")


def _is_enforce_disabled() -> bool:
    """V007.41 FR-002 逃生口: 环境变量关闭事务强制检查.

    Returns:
        True 表示关闭 enforce_write_in_tx (仅 metric 警告, 不 raise)
    """
    val = os.environ.get('BO_FRAMEWORK_TX_FORCE', '').strip().lower()
    return val in ('false', '0', 'no', 'off')


def _open_safe_connection(db_path: str) -> sqlite3.Connection:
    """内部: 创建配好安全三件套 + mmap_size=0 的连接."""
    # Lazy import config: 避免循环依赖
    from meta.core.sql_config import get_safe_connect_config
    cfg = get_safe_connect_config()

    conn = sqlite3.connect(
        db_path,
        timeout=cfg.timeout,
        check_same_thread=cfg.check_same_thread,
    )
    conn.execute(f"PRAGMA busy_timeout = {cfg.busy_timeout_ms}")
    # [V007.49 BUG-FIX] journal_mode=DELETE: WAL 模式并发读写触发 disk I/O error
    # journal_mode 是 DB-level 持久化 PRAGMA, 首次设后自动继承, 此处做幂等保护
    conn.execute("PRAGMA journal_mode=DELETE")
    # [V007.46 BUG-FIX] 禁用 mmap: 108MB DB 上 mmap 导致 disk I/O error
    conn.execute("PRAGMA mmap_size = 0")
    conn.execute("PRAGMA cache_size = -2000")
    conn.row_factory = sqlite3.Row
    return conn


class _RetryingReadConnection:
    """[V007.48] Proxy sqlite3.Connection with disk I/O error retry.

    背景: safe_connect_for_read() 创建的裸连接无重试保护,
    WAL 写锁持有时读连接拿到坏 page → 直接抛 disk I/O error.
    sql_adapters.py 的读池有 Decorrelated Jitter 重试, 但 safe_connect 走的直连没有.

    修法: 用代理类包装 execute(), 返回 _RetryingCursor,
    cursor 的 fetchone/fetchall 也在 disk I/O error 时重连重试.
    """

    _RETRYABLE_ERRORS = ("disk i/o", "database is locked")

    def __init__(self, conn: sqlite3.Connection, db_path: str):
        object.__setattr__(self, '_conn', conn)
        object.__setattr__(self, '_db_path', db_path)
        object.__setattr__(self, '_max_retries', int(os.environ.get('SAFE_CONNECT_READ_RETRY_MAX', '3')))
        object.__setattr__(self, '_retry_base', float(os.environ.get('SAFE_CONNECT_READ_RETRY_BASE_MS', '200')) / 1000.0)
        object.__setattr__(self, '_retry_cap', 2.0)

    def execute(self, sql: str, params=None):
        """Execute SQL, return _RetryingCursor (with retry on fetch)."""
        return _RetryingCursor(self, sql, params)

    def _raw_execute(self, sql: str, params=None):
        """Direct execute on underlying connection (no retry wrapper)."""
        if params is not None:
            return self._conn.execute(sql, params)
        return self._conn.execute(sql)

    def _reconnect(self):
        """Close bad connection, open new one."""
        try:
            self._conn.close()
        except Exception:
            pass
        object.__setattr__(self, '_conn', _open_safe_connection(self._db_path))

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def cursor(self):
        """Return raw cursor (callers that use cursor().execute() bypass retry)."""
        return self._conn.cursor()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __iter__(self):
        return iter(self._conn)


class _RetryingCursor:
    """[V007.48] Cursor proxy: fetchone/fetchall retry on disk I/O error.

    On retryable error, reconnects and re-executes the original SQL,
    then retries the fetch. Uses Decorrelated Jitter (AWS 2015)
    matching sql_adapters.py pattern.
    """

    def __init__(self, conn_proxy: _RetryingReadConnection, sql: str, params):
        self._proxy = conn_proxy
        self._sql = sql
        self._params = params
        self._cursor = None
        self._needs_execute = True

    def _ensure_executed(self):
        if not self._needs_execute:
            return
        self._cursor = self._proxy._raw_execute(self._sql, self._params)
        self._needs_execute = False

    def fetchone(self):
        return self._fetch_with_retry('fetchone')

    def fetchall(self):
        return self._fetch_with_retry('fetchall')

    def fetchmany(self, size=None):
        return self._fetch_with_retry('fetchmany', size)

    def _fetch_with_retry(self, method: str, *args):
        max_retries = self._proxy._max_retries
        retry_base = self._proxy._retry_base
        retry_cap = self._proxy._retry_cap
        prev_sleep = retry_base
        last_error = None

        for attempt in range(max_retries):
            try:
                self._ensure_executed()
                if method == 'fetchone':
                    result = self._cursor.fetchone()
                elif method == 'fetchall':
                    result = self._cursor.fetchall()
                else:
                    result = self._cursor.fetchmany(args[0]) if args else self._cursor.fetchmany()
                if attempt > 0:
                    _bump_counter('safe_connect_read_retry_success_total')
                return result
            except sqlite3.OperationalError as e:
                last_error = e
                err_str = str(e).lower()
                is_retryable = any(tok in err_str for tok in _RetryingReadConnection._RETRYABLE_ERRORS)

                if is_retryable and attempt < max_retries - 1:
                    delay = min(retry_cap, _random.uniform(retry_base, prev_sleep * 3))
                    prev_sleep = delay
                    _bump_counter('safe_connect_read_retry_total')
                    logger.warning(
                        "[V007.48] safe_connect_for_read: retrying %s "
                        "(attempt %d/%d, sleep %.3fs): %s",
                        method, attempt + 1, max_retries, delay, err_str
                    )
                    time.sleep(delay)
                    self._proxy._reconnect()
                    self._cursor = None
                    self._needs_execute = True
                    continue

                if "closed database" in err_str and attempt < max_retries - 1:
                    time.sleep(0.05 * (attempt + 1))
                    self._proxy._reconnect()
                    self._cursor = None
                    self._needs_execute = True
                    continue

                raise
        raise last_error

    def close(self):
        if self._cursor:
            try:
                self._cursor.close()
            except Exception:
                pass

    def __getattr__(self, name):
        self._ensure_executed()
        return getattr(self._cursor, name)

    def __iter__(self):
        self._ensure_executed()
        return iter(self._cursor)


@contextmanager
def safe_connect_for_read(db_path: str) -> Iterator[sqlite3.Connection]:
    """[V007.41+V007.48] L0 只读裸连接工厂 (含 disk I/O error 重试).

    等价于:
        conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row

    [V007.48] 返回 _RetryingReadConnection 代理:
        conn.execute("SELECT ...").fetchone() 在 disk I/O error 时自动重连重试
        重试策略: Decorrelated Jitter (同 sql_adapters.py), 默认 3 次, base=200ms, cap=2s
        环境变量: SAFE_CONNECT_READ_RETRY_MAX (默认 3), SAFE_CONNECT_READ_RETRY_BASE_MS (默认 200)

    Yields:
        _RetryingReadConnection (兼容 sqlite3.Connection 接口)

    Note:
        自动 close; 即使业务代码 raise 也会清理连接.
    """
    _bump_counter('safe_connect_read_total')
    conn = _open_safe_connection(db_path)
    proxy = _RetryingReadConnection(conn, db_path)
    try:
        yield proxy
    finally:
        try:
            proxy.close()
        except Exception:
            pass


@contextmanager
def safe_connect_for_write(
    db_path: str,
    *,
    force_no_tx: bool = False,
) -> Iterator[sqlite3.Connection]:
    """[V007.41] L0 写裸连接工厂, 强制 V3 事务上下文.

    [V007.41 BUG-FIX] 背景:
        L0 写不参与外层事务 = silent partial commit 风险.
        修法: 用 sqlite_tx_state 探测外层事务状态, NONE 时 raise.

    Args:
        db_path: 数据库路径
        force_no_tx: True = 绕过检查 (admin/一次性脚本专用, metric 标记)

    Raises:
        ConnectionRefusedError: 无外层事务且 force_no_tx=False

    Yields:
        sqlite3.Connection

    Note:
        调用方**必须**在外层事务中 (bo_framework.transaction() / ds.transaction() / UnitOfWork);
        自动 commit 由外层 txn 负责, 本函数不调用 conn.commit()!
    """
    _bump_counter('safe_connect_write_total')

    # Lazy config import
    from meta.core.sql_config import get_safe_connect_config
    cfg = get_safe_connect_config()

    enforce = cfg.enforce_write_in_tx and not _is_enforce_disabled()

    if enforce and not force_no_tx:
        # 用临时只读连接探测 (不创建新事务, 不影响业务)
        with safe_connect_for_read(db_path) as probe_conn:
            state = get_tx_state(probe_conn)

        if state == TxState.NONE:
            _bump_counter('safe_connect_write_no_tx_total')
            raise ConnectionRefusedError(
                "[V007.41] safe_connect_for_write requires outer transaction. "
                "Use 'with bo_framework.transaction() as txn:' or call from within "
                "ds.transaction()/UnitOfWork. If this is an admin one-shot, pass "
                "force_no_tx=True or set env BO_FRAMEWORK_TX_FORCE=false."
            )
        elif state == TxState.UNKNOWN:
            _bump_counter('safe_connect_tx_state_unknown_total')
            logger.warning(
                "[V007.41] tx_state probe UNKNOWN, write proceeding (degraded). "
                "File=%s", db_path
            )

    if force_no_tx:
        _bump_counter('safe_connect_write_no_tx_total')
        logger.warning(
            "[V007.41] force_no_tx=True, write bypassing tx enforcement (db_path=%s)",
            db_path
        )

    conn = _open_safe_connection(db_path)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            pass


@contextmanager
def safe_connect(
    db_path: str,
    *,
    mode: str = "auto",
) -> Iterator[sqlite3.Connection]:
    """[V007.41] 兼容旧调用, 自动判断 read/write.

    Args:
        db_path: 数据库路径
        mode: "auto" | "read" | "write" | "write_force_no_tx"

    Note:
        "auto" 默认按 read 处理 (保守, 不强制事务).
        业务热路径建议明确指定 mode, 便于审计.

    Warning:
        本函数是为兼容旧代码引入, 新代码请直接用 safe_connect_for_read/write.
    """
    if mode == "read":
        with safe_connect_for_read(db_path) as conn:
            yield conn
    elif mode == "write":
        with safe_connect_for_write(db_path) as conn:
            yield conn
    elif mode == "write_force_no_tx":
        with safe_connect_for_write(db_path, force_no_tx=True) as conn:
            yield conn
    elif mode == "auto":
        # auto 模式默认按 read 处理
        logger.debug("[V007.41] safe_connect mode=auto, defaulting to read (db_path=%s)", db_path)
        with safe_connect_for_read(db_path) as conn:
            yield conn
    else:
        raise ValueError(
            f"[V007.41] safe_connect invalid mode='{mode}'. "
            f"Expected: 'auto' | 'read' | 'write' | 'write_force_no_tx'."
        )
    # [V007.46 BUG-FIX 2026-07-09] 记录 safe_connect 调用 (验证 V007.41+V007.46 真部署)
    try:
        from meta.core.diagnostics import record_safe_connect_call
        record_safe_connect_call(mode)
    except Exception:
        pass


# 兼容 V007.40 的导出名 (临时, Phase 2 全部迁移后可移除)
__all__ = [
    "safe_connect",
    "safe_connect_for_read",
    "safe_connect_for_write",
]