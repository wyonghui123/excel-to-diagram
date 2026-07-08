# -*- coding: utf-8 -*-
"""
数据库配置管理

集中管理数据库连接池、写队列、监控等配置项。
支持从环境变量和配置文件加载。
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    max_readers: int = 5
    idle_timeout: float = 300.0
    max_lifetime: float = 3600.0
    acquire_timeout: float = 30.0
    db_timeout: float = 30.0
    wal_auto_checkpoint: int = 1000


@dataclass
class WriteQueueConfig:
    max_queue_size: int = 1000
    submit_timeout: float = 30.0
    operation_timeout: float = 60.0
    checkpoint_interval: int = 50
    # [V007.40 BUG-FIX] 默认 TRUNCATE → PASSIVE
    # 背景: V007.39 修了显式调用的 checkpoint (sql_write_queue.py, server.py, db_admin_api.py),
    #       但漏了配置默认值的源头. 任何用 WriteQueueConfig() 默认初始化的代码
    #       (如 sql_adapters.py pool 初始化) 都会走 TRUNCATE, 每次连接建立时
    #       截断 WAL 文件 → 读连接 mmap 视图失效 → disk I/O error.
    # 修法: 默认改 PASSIVE, 不阻塞读, 不截断 WAL, 由 force_passive_checkpoint 周期性推.
    checkpoint_mode: str = "PASSIVE"


@dataclass
class CheckpointConfig:
    interval: int = 50
    # [V007.40 BUG-FIX] 默认 TRUNCATE → PASSIVE
    # 背景: 同上, 任何用 CheckpointConfig() 默认初始化的代码 (如 CheckpointManager
    #       默认参数, execute_checkpoint 显式调用) 都会走 TRUNCATE.
    # 修法: 默认改 PASSIVE. RESTART 仍可作为低峰期 (2-5 点) 显式触发.
    mode: str = "PASSIVE"
    wal_size_threshold_mb: float = 50.0
    checkpoint_interval_seconds: float = 300.0


@dataclass
class MonitorConfig:
    enabled: bool = True
    slow_query_threshold_ms: float = 100.0
    slow_query_alert_threshold: int = 10
    slow_query_buffer_size: int = 200
    metrics_collect_interval_seconds: float = 15.0


# [V007.41 BUG-FIX] safe_connect 工厂配置
# 背景: V007.40 在 17 个文件复制 timeout + check_same_thread + busy_timeout 三件套,
#       V007.41 集中到 meta/core/safe_connect.py, 配置项集中在本类.
# 默认值与 V007.40 / sql_connection_pool.py db_timeout=30.0 保持一致.
@dataclass
class SafeConnectConfig:
    """V007.41 L0 裸连接工厂配置

    字段:
        timeout: sqlite3.connect() 的 timeout 参数 (秒)
        busy_timeout_ms: PRAGMA busy_timeout (毫秒)
        check_same_thread: 是否允许多线程共享
        enforce_write_in_tx: safe_connect_for_write 是否强制外层事务
        tx_state_unknown_passthrough: tx_state 探测 UNKNOWN 时是否降级放行
    """
    timeout: float = 30.0
    busy_timeout_ms: int = 30000
    check_same_thread: bool = False
    enforce_write_in_tx: bool = True
    tx_state_unknown_passthrough: bool = True


@dataclass
class DatabaseConfig:
    db_path: str = ""
    use_pool: bool = True
    pool: PoolConfig = field(default_factory=PoolConfig)
    write_queue: WriteQueueConfig = field(default_factory=WriteQueueConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    safe_connect: SafeConnectConfig = field(default_factory=SafeConnectConfig)

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        config = cls()
        config.db_path = os.environ.get(
            "DATABASE_PATH",
            os.environ.get("SQLITE_DB_PATH", ""),
        )
        config.use_pool = os.environ.get(
            "DATABASE_USE_POOL", "true"
        ).lower() in ("true", "1", "yes")

        pool_max = os.environ.get("DATABASE_POOL_MAX_READERS")
        if pool_max:
            config.pool.max_readers = int(pool_max)

        pool_idle = os.environ.get("DATABASE_POOL_IDLE_TIMEOUT")
        if pool_idle:
            config.pool.idle_timeout = float(pool_idle)

        pool_acquire = os.environ.get("DATABASE_POOL_ACQUIRE_TIMEOUT")
        if pool_acquire:
            config.pool.acquire_timeout = float(pool_acquire)

        cp_interval = os.environ.get("DATABASE_CHECKPOINT_INTERVAL")
        if cp_interval:
            config.write_queue.checkpoint_interval = int(cp_interval)

        cp_mode = os.environ.get("DATABASE_CHECKPOINT_MODE")
        if cp_mode:
            config.write_queue.checkpoint_mode = cp_mode

        slow_threshold = os.environ.get("DATABASE_SLOW_QUERY_THRESHOLD_MS")
        if slow_threshold:
            config.monitor.slow_query_threshold_ms = float(slow_threshold)

        monitor_enabled = os.environ.get("DATABASE_MONITOR_ENABLED")
        if monitor_enabled:
            config.monitor.enabled = monitor_enabled.lower() in ("true", "1", "yes")

        return config

    def to_connect_kwargs(self) -> dict:
        kwargs = {
            "path": self.db_path,
            "max_readers": self.pool.max_readers,
            "idle_timeout": self.pool.idle_timeout,
            "max_lifetime": self.pool.max_lifetime,
            "acquire_timeout": self.pool.acquire_timeout,
            "checkpoint_interval": self.write_queue.checkpoint_interval,
            "checkpoint_mode": self.write_queue.checkpoint_mode,
        }
        return kwargs


_default_config: Optional[DatabaseConfig] = None


def get_database_config() -> DatabaseConfig:
    global _default_config
    if _default_config is None:
        _default_config = DatabaseConfig.from_env()
    return _default_config


def set_database_config(config: DatabaseConfig):
    global _default_config
    _default_config = config


# [V007.41] safe_connect 单例配置 + 工厂函数
_default_safe_connect_config: Optional[SafeConnectConfig] = None


def get_safe_connect_config() -> SafeConnectConfig:
    """[V007.41] 获取 safe_connect 工厂配置 (单例).

    支持环境变量覆盖:
        SAFE_CONNECT_TIMEOUT          - 覆盖 timeout (秒, float)
        SAFE_CONNECT_BUSY_TIMEOUT_MS  - 覆盖 busy_timeout_ms (int)
        SAFE_CONNECT_ENFORCE_TX       - 'false'/'0'/'no'/'off' 关闭强制事务检查
    """
    global _default_safe_connect_config
    if _default_safe_connect_config is None:
        _default_safe_connect_config = SafeConnectConfig()

        timeout_env = os.environ.get('SAFE_CONNECT_TIMEOUT')
        if timeout_env:
            try:
                _default_safe_connect_config.timeout = float(timeout_env)
            except ValueError:
                pass

        busy_env = os.environ.get('SAFE_CONNECT_BUSY_TIMEOUT_MS')
        if busy_env:
            try:
                _default_safe_connect_config.busy_timeout_ms = int(busy_env)
            except ValueError:
                pass

        enforce_env = os.environ.get('SAFE_CONNECT_ENFORCE_TX', '').strip().lower()
        if enforce_env in ('false', '0', 'no', 'off'):
            _default_safe_connect_config.enforce_write_in_tx = False

    return _default_safe_connect_config


def set_safe_connect_config(config: SafeConnectConfig) -> None:
    """[V007.41] 重置 safe_connect 工厂配置 (测试 / 紧急覆盖用)."""
    global _default_safe_connect_config
    _default_safe_connect_config = config
