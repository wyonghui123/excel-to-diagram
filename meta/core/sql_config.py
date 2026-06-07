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
    checkpoint_mode: str = "TRUNCATE"


@dataclass
class CheckpointConfig:
    interval: int = 50
    mode: str = "TRUNCATE"
    wal_size_threshold_mb: float = 50.0
    checkpoint_interval_seconds: float = 300.0


@dataclass
class MonitorConfig:
    enabled: bool = True
    slow_query_threshold_ms: float = 100.0
    slow_query_alert_threshold: int = 10
    slow_query_buffer_size: int = 200
    metrics_collect_interval_seconds: float = 15.0


@dataclass
class DatabaseConfig:
    db_path: str = ""
    use_pool: bool = True
    pool: PoolConfig = field(default_factory=PoolConfig)
    write_queue: WriteQueueConfig = field(default_factory=WriteQueueConfig)
    checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)

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
