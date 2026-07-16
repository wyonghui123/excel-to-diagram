# -*- coding: utf-8 -*-
"""
数据库监控指标采集器

集中采集数据库运行指标，供 Prometheus 导出和 API 查询：
- 连接池指标
- 写队列指标
- 操作延迟指标
- WAL/Checkpoint 指标
- 错误指标
"""

import time
import threading
import logging
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class OperationMetric:
    count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    max_time_ms: float = 0.0
    recent_latencies_ms: deque = field(default_factory=lambda: deque(maxlen=200))

    def record(self, elapsed_ms: float):
        self.count += 1
        self.total_time_ms += elapsed_ms
        self.min_time_ms = min(self.min_time_ms, elapsed_ms)
        self.max_time_ms = max(self.max_time_ms, elapsed_ms)
        self.recent_latencies_ms.append(elapsed_ms)

    @property
    def avg_ms(self) -> float:
        return self.total_time_ms / self.count if self.count > 0 else 0.0

    def percentile(self, p: float) -> float:
        if not self.recent_latencies_ms:
            return 0.0
        sorted_lat = sorted(self.recent_latencies_ms)
        idx = int(len(sorted_lat) * p / 100)
        idx = min(idx, len(sorted_lat) - 1)
        return sorted_lat[idx]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_time_ms, 3) if self.min_time_ms != float('inf') else 0,
            "max_ms": round(self.max_time_ms, 3),
            "p50_ms": round(self.percentile(50), 3),
            "p95_ms": round(self.percentile(95), 3),
            "p99_ms": round(self.percentile(99), 3),
        }


class SQLDatabaseMonitor:
    """数据库监控指标采集器

    使用方式：
        monitor = SQLDatabaseMonitor(adapter)
        monitor.start()

        # 在操作前后记录
        monitor.record_read(elapsed_ms)
        monitor.record_write(elapsed_ms)

        # 获取所有指标
        metrics = monitor.collect_metrics()
    """

    def __init__(self, adapter=None, db_path: str = ""):
        self._adapter = adapter
        self._db_path = db_path
        self._start_time = time.time()
        self._lock = threading.Lock()

        self._read_metric = OperationMetric()
        self._write_metric = OperationMetric()

        self._lock_timeout_count = 0
        self._connection_error_count = 0
        self._rollback_count = 0
        self._slow_query_count = 0

        self._slow_queries: deque = deque(maxlen=200)
        self._slow_query_threshold_ms = 100.0

        self._collect_thread: Optional[threading.Thread] = None
        self._running = False
        self._collect_interval = 15.0

    def set_slow_query_threshold(self, threshold_ms: float):
        self._slow_query_threshold_ms = threshold_ms

    def record_read(self, elapsed_ms: float, sql: str = ""):
        with self._lock:
            self._read_metric.record(elapsed_ms)
            if elapsed_ms > self._slow_query_threshold_ms:
                self._slow_query_count += 1
                self._slow_queries.append({
                    "type": "read",
                    "elapsed_ms": round(elapsed_ms, 3),
                    "sql": sql[:200] if sql else "",
                    "timestamp": time.time(),
                })

    def record_write(self, elapsed_ms: float, sql: str = ""):
        with self._lock:
            self._write_metric.record(elapsed_ms)
            if elapsed_ms > self._slow_query_threshold_ms:
                self._slow_query_count += 1
                self._slow_queries.append({
                    "type": "write",
                    "elapsed_ms": round(elapsed_ms, 3),
                    "sql": sql[:200] if sql else "",
                    "timestamp": time.time(),
                })

    def record_lock_timeout(self):
        with self._lock:
            self._lock_timeout_count += 1

    def record_connection_error(self):
        with self._lock:
            self._connection_error_count += 1

    def record_rollback(self):
        with self._lock:
            self._rollback_count += 1

    def collect_metrics(self) -> Dict[str, Any]:
        metrics = {
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "timestamp": time.time(),
        }

        if self._adapter and self._adapter.pool:
            pool_stats = self._adapter.get_pool_stats()
            metrics["pool"] = pool_stats
        else:
            metrics["pool"] = {"mode": "legacy"}

        if self._adapter and self._adapter.write_queue:
            queue_stats = self._adapter.get_write_queue_stats()
            metrics["write_queue"] = queue_stats
        else:
            metrics["write_queue"] = {"mode": "legacy"}

        with self._lock:
            metrics["read_ops"] = self._read_metric.to_dict()
            metrics["write_ops"] = self._write_metric.to_dict()
            metrics["errors"] = {
                "lock_timeouts": self._lock_timeout_count,
                "connection_errors": self._connection_error_count,
                "rollbacks": self._rollback_count,
                "slow_queries": self._slow_query_count,
            }
            metrics["slow_queries_recent"] = list(self._slow_queries)[-10:]

        db_path = self._db_path
        if not db_path and self._adapter:
            db_path = getattr(self._adapter, '_db_path', '')

        if db_path and db_path != ":memory:":
            metrics["storage"] = {
                "db_size_bytes": os.path.getsize(db_path) if os.path.exists(db_path) else 0,
                "wal_size_bytes": os.path.getsize(db_path + "-wal") if os.path.exists(db_path + "-wal") else 0,
                "shm_size_bytes": os.path.getsize(db_path + "-shm") if os.path.exists(db_path + "-shm") else 0,
            }
        else:
            metrics["storage"] = {"mode": "memory"}

        if self._adapter:
            metrics["health"] = self._adapter.health_check()

        return metrics

    def start(self, interval_seconds: float = 15.0):
        if self._running:
            return
        self._running = True
        self._collect_interval = interval_seconds
        self._collect_thread = threading.Thread(
            target=self._collect_loop,
            name="db-monitor",
            daemon=True,
        )
        self._collect_thread.start()
        logger.info("Database monitor started (interval=%ss)", interval_seconds)

    def stop(self):
        self._running = False
        if self._collect_thread and self._collect_thread.is_alive():
            self._collect_thread.join(timeout=5)
        logger.info("Database monitor stopped")

    def _collect_loop(self):
        while self._running:
            try:
                self.collect_metrics()
            except Exception as e:
                logger.error("Monitor collect error: %s", str(e))
            time.sleep(self._collect_interval)

    def get_slow_queries(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._slow_queries)[-limit:]

    def get_summary(self) -> Dict[str, Any]:
        metrics = self.collect_metrics()
        return {
            "uptime_seconds": metrics.get("uptime_seconds", 0),
            "read_ops_count": metrics.get("read_ops", {}).get("count", 0),
            "write_ops_count": metrics.get("write_ops", {}).get("count", 0),
            "read_avg_ms": metrics.get("read_ops", {}).get("avg_ms", 0),
            "write_avg_ms": metrics.get("write_ops", {}).get("avg_ms", 0),
            "read_p95_ms": metrics.get("read_ops", {}).get("p95_ms", 0),
            "write_p95_ms": metrics.get("write_ops", {}).get("p95_ms", 0),
            "slow_queries": metrics.get("errors", {}).get("slow_queries", 0),
            "lock_timeouts": metrics.get("errors", {}).get("lock_timeouts", 0),
            "db_size_mb": metrics.get("storage", {}).get("db_size_bytes", 0) / (1024 * 1024),
            "wal_size_mb": metrics.get("storage", {}).get("wal_size_bytes", 0) / (1024 * 1024),
        }
