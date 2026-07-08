# -*- coding: utf-8 -*-
"""
[V007.15 L0] 启动时 SQLite 运行时配置检测

设计动机:
- 生产可能有 3 种配置:
  - State A: WAL + busy_timeout=5000 (worktree-V049 base 8bfcbff)
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
            # busy_timeout is connection-level in Python 3.12+, not DB-level
            # So we need to also check if connection pool/manager has set it
            # For now, read default + check journal_mode (which IS DB-level)
            journal_raw = conn.execute("PRAGMA journal_mode").fetchone()[0]
            # busy_timeout default is 5000ms in Python sqlite3, but apps may
            # set it via connection pool. We detect it here but understand
            # that in production it should be matched to sql_connection_pool.py
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
