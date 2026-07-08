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
import sqlite3
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
    """内部: 创建配好三件套的连接 (不负责事务探测)."""
    # Lazy import config: 避免循环依赖
    from meta.core.sql_config import get_safe_connect_config
    cfg = get_safe_connect_config()

    conn = sqlite3.connect(
        db_path,
        timeout=cfg.timeout,
        check_same_thread=cfg.check_same_thread,
    )
    conn.execute(f"PRAGMA busy_timeout = {cfg.busy_timeout_ms}")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def safe_connect_for_read(db_path: str) -> Iterator[sqlite3.Connection]:
    """[V007.41] L0 只读裸连接工厂.

    等价于:
        conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.row_factory = sqlite3.Row

    Yields:
        sqlite3.Connection (row_factory=sqlite3.Row)

    Note:
        自动 close; 即使业务代码 raise 也会清理连接.
    """
    _bump_counter('safe_connect_read_total')
    conn = _open_safe_connection(db_path)
    try:
        yield conn
    finally:
        try:
            conn.close()
        except Exception:
            # 双保险: close 失败不阻塞调用方
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


# 兼容 V007.40 的导出名 (临时, Phase 2 全部迁移后可移除)
__all__ = [
    "safe_connect",
    "safe_connect_for_read",
    "safe_connect_for_write",
]