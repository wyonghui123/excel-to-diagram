# -*- coding: utf-8 -*-
"""
[V007.15 L1] SQLite 事务状态探测 (Python 3.12+ conn.in_transaction)

原理:
- Python 3.12+ 有 conn.in_transaction 属性, 直接给出 SQLite 真实状态
- 之前用 SAVEPOINT 探测失败, 因为 Python 3.14 autocommit 模式下
  SAVEPOINT 始终成功 (即使不在事务中)
- 解决: 优先用 conn.in_transaction, 不存在时用 try-BEGIN 探测
"""
import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)


class TxState:
    NONE = "none"        # 不在事务中
    READ = "read"        # 只读事务
    WRITE = "write"      # 写事务
    UNKNOWN = "unknown"  # 探测失败


def get_tx_state(conn) -> str:
    """
    探测 SQLite 实际事务状态.

    Python 3.12+ 用 conn.in_transaction (官方 API, 最准确)
    降级方案: try BEGIN 嵌套 (legacy)
    """
    # Python 3.12+ has direct attribute
    if hasattr(conn, 'in_transaction'):
        try:
            if conn.in_transaction:
                return TxState.WRITE
            return TxState.NONE
        except Exception:
            pass

    # Fallback: try BEGIN IMMEDIATE without savepoint
    # 如果已 in tx, 会 raise. 否则会 start 一个新 tx, 需要 rollback
    try:
        conn.execute("BEGIN IMMEDIATE")
        # 刚 start 的, 必须 rollback (没改东西)
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        return TxState.NONE  # 之前不在 tx
    except sqlite3.OperationalError as e:
        err_str = str(e).lower()
        if "already in" in err_str or "within a transaction" in err_str:
            return TxState.WRITE
        return TxState.NONE
    except Exception as e:
        logger.warning(f"[V007.15 L1] tx_state probe failed: {e}")
        return TxState.UNKNOWN


@contextmanager
def tx_state_verified_action(conn, expected_state: str = TxState.NONE, action_label: str = ""):
    """
    Context manager: 验证事务状态, 但不强制 rollback.
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
