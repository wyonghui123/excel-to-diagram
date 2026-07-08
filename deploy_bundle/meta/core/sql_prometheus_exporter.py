# -*- coding: utf-8 -*-
"""
Prometheus 指标导出器

将数据库监控指标导出为 Prometheus 格式，
集成到现有的 Prometheus + Grafana 监控体系。
"""

import time
import logging
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SQLPrometheusExporter:
    """数据库 Prometheus 指标导出器

    使用方式：
        exporter = SQLPrometheusExporter(monitor)
        exporter.setup()

        # 在 /metrics 端点中调用
        output = exporter.generate_latest()
    """

    def __init__(self, monitor=None):
        self._monitor = monitor
        self._metrics = {}
        self._setup_done = False

    def setup(self):
        try:
            from prometheus_client import (
                Gauge, Counter, Histogram, CollectorRegistry, generate_latest,
            )
            self._prometheus_available = True
            self._registry = CollectorRegistry()

            self._gauge_pool_active_readers = Gauge(
                "sqlite_pool_active_readers",
                "Active reader connections",
                registry=self._registry,
            )
            self._gauge_pool_idle_readers = Gauge(
                "sqlite_pool_idle_readers",
                "Idle reader connections",
                registry=self._registry,
            )
            self._gauge_pool_max_readers = Gauge(
                "sqlite_pool_max_readers",
                "Maximum reader connections",
                registry=self._registry,
            )
            self._gauge_write_queue_depth = Gauge(
                "sqlite_write_queue_depth",
                "Current write queue depth",
                registry=self._registry,
            )
            self._gauge_wal_file_size_bytes = Gauge(
                "sqlite_wal_file_size_bytes",
                "WAL file size in bytes",
                registry=self._registry,
            )
            self._gauge_db_file_size_bytes = Gauge(
                "sqlite_db_file_size_bytes",
                "Database file size in bytes",
                registry=self._registry,
            )
            self._gauge_read_avg_ms = Gauge(
                "sqlite_read_avg_ms",
                "Average read operation time in ms",
                registry=self._registry,
            )
            self._gauge_write_avg_ms = Gauge(
                "sqlite_write_avg_ms",
                "Average write operation time in ms",
                registry=self._registry,
            )
            self._gauge_read_p95_ms = Gauge(
                "sqlite_read_p95_ms",
                "P95 read operation time in ms",
                registry=self._registry,
            )
            self._gauge_write_p95_ms = Gauge(
                "sqlite_write_p95_ms",
                "P95 write operation time in ms",
                registry=self._registry,
            )

            self._counter_read_ops = Counter(
                "sqlite_read_operations_total",
                "Total read operations",
                registry=self._registry,
            )
            self._counter_write_ops = Counter(
                "sqlite_write_operations_total",
                "Total write operations",
                registry=self._registry,
            )
            self._counter_lock_timeouts = Counter(
                "sqlite_lock_timeouts_total",
                "Total lock timeouts",
                registry=self._registry,
            )
            self._counter_connection_errors = Counter(
                "sqlite_connection_errors_total",
                "Total connection errors",
                registry=self._registry,
            )
            self._counter_checkpoint_count = Counter(
                "sqlite_checkpoint_count_total",
                "Total checkpoint executions",
                registry=self._registry,
            )
            self._counter_slow_queries = Counter(
                "sqlite_slow_queries_total",
                "Total slow queries",
                registry=self._registry,
            )
            self._counter_rollback_count = Counter(
                "sqlite_transaction_rollbacks_total",
                "Total transaction rollbacks",
                registry=self._registry,
            )

            self._setup_done = True
            logger.info("Prometheus exporter setup complete")
        except ImportError:
            self._prometheus_available = False
            logger.info("prometheus_client not installed, using text format exporter")

    def update_metrics(self):
        if not self._monitor:
            return

        metrics = self._monitor.collect_metrics()

        if self._setup_done and self._prometheus_available:
            pool = metrics.get("pool", {})
            if pool.get("mode") != "legacy":
                self._gauge_pool_active_readers.set(pool.get("active_readers", 0))
                self._gauge_pool_idle_readers.set(pool.get("idle_readers", 0))
                self._gauge_pool_max_readers.set(pool.get("max_readers", 0))

            wq = metrics.get("write_queue", {})
            if wq.get("mode") != "legacy":
                self._gauge_write_queue_depth.set(wq.get("depth", 0))

            storage = metrics.get("storage", {})
            if storage.get("mode") != "memory":
                self._gauge_db_file_size_bytes.set(storage.get("db_size_bytes", 0))
                self._gauge_wal_file_size_bytes.set(storage.get("wal_size_bytes", 0))

            read_ops = metrics.get("read_ops", {})
            self._gauge_read_avg_ms.set(read_ops.get("avg_ms", 0))
            self._gauge_read_p95_ms.set(read_ops.get("p95_ms", 0))

            write_ops = metrics.get("write_ops", {})
            self._gauge_write_avg_ms.set(write_ops.get("avg_ms", 0))
            self._gauge_write_p95_ms.set(write_ops.get("p95_ms", 0))

        self._metrics = metrics

    def generate_latest(self) -> str:
        if self._setup_done and self._prometheus_available:
            from prometheus_client import generate_latest
            self.update_metrics()
            return generate_latest(self._registry).decode('utf-8')
        return self._generate_text_format()

    def _generate_text_format(self) -> str:
        if not self._monitor:
            return ""

        metrics = self._monitor.collect_metrics()
        lines = []

        def _add_metric(name, value, metric_type="gauge", help_text=""):
            lines.append("# HELP {0} {1}".format(name, help_text))
            lines.append("# TYPE {0} {1}".format(name, metric_type))
            lines.append("{0} {1}".format(name, value))

        pool = metrics.get("pool", {})
        if pool.get("mode") != "legacy":
            _add_metric("sqlite_pool_active_readers", pool.get("active_readers", 0), "gauge", "Active reader connections")
            _add_metric("sqlite_pool_idle_readers", pool.get("idle_readers", 0), "gauge", "Idle reader connections")
            _add_metric("sqlite_pool_max_readers", pool.get("max_readers", 0), "gauge", "Maximum reader connections")

        wq = metrics.get("write_queue", {})
        if wq.get("mode") != "legacy":
            _add_metric("sqlite_write_queue_depth", wq.get("depth", 0), "gauge", "Current write queue depth")

        storage = metrics.get("storage", {})
        if storage.get("mode") != "memory":
            _add_metric("sqlite_db_file_size_bytes", storage.get("db_size_bytes", 0), "gauge", "Database file size")
            _add_metric("sqlite_wal_file_size_bytes", storage.get("wal_size_bytes", 0), "gauge", "WAL file size")

        read_ops = metrics.get("read_ops", {})
        _add_metric("sqlite_read_operations_total", read_ops.get("count", 0), "counter", "Total read operations")
        _add_metric("sqlite_read_avg_ms", read_ops.get("avg_ms", 0), "gauge", "Average read time")
        _add_metric("sqlite_read_p95_ms", read_ops.get("p95_ms", 0), "gauge", "P95 read time")

        write_ops = metrics.get("write_ops", {})
        _add_metric("sqlite_write_operations_total", write_ops.get("count", 0), "counter", "Total write operations")
        _add_metric("sqlite_write_avg_ms", write_ops.get("avg_ms", 0), "gauge", "Average write time")
        _add_metric("sqlite_write_p95_ms", write_ops.get("p95_ms", 0), "gauge", "P95 write time")

        errors = metrics.get("errors", {})
        _add_metric("sqlite_lock_timeouts_total", errors.get("lock_timeouts", 0), "counter", "Total lock timeouts")
        _add_metric("sqlite_connection_errors_total", errors.get("connection_errors", 0), "counter", "Total connection errors")
        _add_metric("sqlite_slow_queries_total", errors.get("slow_queries", 0), "counter", "Total slow queries")
        _add_metric("sqlite_transaction_rollbacks_total", errors.get("rollbacks", 0), "counter", "Total rollbacks")

        return "\n".join(lines) + "\n"
