# -*- coding: utf-8 -*-
"""
慢查询日志

检测和记录超过阈值的 SQL 操作：
- 结构化 JSON 日志输出
- 内存缓冲区保留最近 N 条
- 统计慢查询频率
- 达到告警阈值触发通知
"""

import time
import json
import os
import logging
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SlowQueryRecord:
    sql: str
    params: Optional[tuple]
    elapsed_ms: float
    operation_type: str
    timestamp: float
    thread_id: int
    stack_trace: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sql": self.sql[:500],
            "params": str(self.params)[:200] if self.params else None,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "operation_type": self.operation_type,
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "thread_id": self.thread_id,
        }


class SlowQueryLogger:
    """慢查询检测与记录

    使用方式：
        slow_logger = SlowQueryLogger(threshold_ms=100)
        slow_logger.start()

        # 在操作完成后检查
        slow_logger.check(sql, params, elapsed_ms, "read")

        # 获取慢查询列表
        queries = slow_logger.get_recent(limit=20)
    """

    def __init__(
        self,
        threshold_ms: float = 100.0,
        alert_threshold: int = 10,
        buffer_size: int = 200,
        log_file: Optional[str] = None,
    ):
        self._threshold_ms = threshold_ms
        self._alert_threshold = alert_threshold
        self._buffer_size = buffer_size
        self._log_file = log_file
        self._buffer: deque = deque(maxlen=buffer_size)
        self._lock = threading.Lock()
        self._count_per_minute: Dict[str, List[float]] = {}
        self._total_count = 0
        self._alert_callbacks = []

    @property
    def threshold_ms(self) -> float:
        return self._threshold_ms

    def set_threshold(self, threshold_ms: float):
        self._threshold_ms = threshold_ms

    def add_alert_callback(self, callback):
        self._alert_callbacks.append(callback)

    def check(
        self,
        sql: str,
        params: Optional[tuple],
        elapsed_ms: float,
        operation_type: str = "unknown",
    ):
        if elapsed_ms < self._threshold_ms:
            return

        record = SlowQueryRecord(
            sql=sql,
            params=params,
            elapsed_ms=elapsed_ms,
            operation_type=operation_type,
            timestamp=time.time(),
            thread_id=threading.current_thread().ident or 0,
        )

        with self._lock:
            self._buffer.append(record)
            self._total_count += 1

            minute_key = datetime.now().strftime("%Y%m%d%H%M")
            if minute_key not in self._count_per_minute:
                self._count_per_minute[minute_key] = []
            self._count_per_minute[minute_key].append(elapsed_ms)

            if len(self._count_per_minute[minute_key]) >= self._alert_threshold:
                self._trigger_alert(minute_key, self._count_per_minute[minute_key])

        self._write_to_log(record)
        logger.warning(
            "Slow query detected: %s (%.1fms, type=%s)",
            sql[:100], elapsed_ms, operation_type,
        )

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            records = list(self._buffer)[-limit:]
        return [r.to_dict() for r in records]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._total_count
            recent = list(self._buffer)

        if recent:
            latencies = [r.elapsed_ms for r in recent]
            sorted_lat = sorted(latencies)
            avg = sum(latencies) / len(latencies)
            p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
            p95 = sorted_lat[p95_idx]
        else:
            avg = 0.0
            p95 = 0.0

        return {
            "total_count": total,
            "threshold_ms": self._threshold_ms,
            "alert_threshold": self._alert_threshold,
            "buffer_size": len(recent),
            "avg_elapsed_ms": round(avg, 3),
            "p95_elapsed_ms": round(p95, 3),
        }

    def start(self):
        logger.info(
            "SlowQueryLogger started (threshold=%.0fms, alert=%d/min)",
            self._threshold_ms, self._alert_threshold,
        )

    def stop(self):
        logger.info("SlowQueryLogger stopped (total_slow_queries=%d)", self._total_count)

    def _write_to_log(self, record: SlowQueryRecord):
        if not self._log_file:
            return
        try:
            log_entry = json.dumps(record.to_dict(), ensure_ascii=False)
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + "\n")
        except Exception as e:
            logger.error("Failed to write slow query log: %s", str(e))

    def _trigger_alert(self, minute_key: str, latencies: List[float]):
        alert_data = {
            "type": "slow_query_alert",
            "minute": minute_key,
            "count": len(latencies),
            "threshold": self._alert_threshold,
            "avg_ms": round(sum(latencies) / len(latencies), 3),
            "max_ms": round(max(latencies), 3),
        }
        for callback in self._alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                logger.error("Slow query alert callback error: %s", str(e))
