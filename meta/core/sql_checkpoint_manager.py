# -*- coding: utf-8 -*-
"""
WAL Checkpoint 管理器

智能 Checkpoint 策略，防止 WAL 文件无限增长：
- WAL 大小触发：wal_size > threshold → 强制 checkpoint
- 时间触发：距上次 checkpoint > interval → checkpoint
- 低峰期触发：在低流量窗口执行 RESTART checkpoint
- 被动模式：检查是否有活跃读者
"""

import os
import time
import threading
import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CheckpointConfig:
    wal_size_threshold_mb: float = 50.0
    checkpoint_interval_seconds: float = 300.0
    low_traffic_window_start: int = 2
    low_traffic_window_end: int = 5
    passive_mode: bool = True
    restart_checkpoint_interval_hours: float = 6.0


class CheckpointManager:
    """智能 WAL Checkpoint 管理器

    策略优先级：
    1. WAL 大小超阈值 → PASSIVE checkpoint (不阻塞读, 不截断 WAL, 由 force_passive 周期性推)
    2. 时间间隔超阈值 → PASSIVE checkpoint
    3. 低峰期 → RESTART checkpoint（更彻底, 仅在 2-5 点低峰期执行）
    4. 被动模式 → PASSIVE checkpoint（不阻塞读者）

    [V007.40 BUG-FIX] 默认策略从 TRUNCATE → PASSIVE
    背景: V007.39 修了显式调用的 checkpoint, 但 sql_checkpoint_manager.should_checkpoint
          返回的 mode 仍是 TRUNCATE, execute_checkpoint 默认参数也是 TRUNCATE.
          TRUNCATE 截断 WAL → 读连接 mmap 视图失效 → disk I/O error.
    修法: 阈值触发用 PASSIVE, RESTART 留给低峰期专用 (low_traffic_restart 路径).
    """

    def __init__(
        self,
        db_path: str,
        write_queue=None,
        config: CheckpointConfig = None,
        get_active_readers: Optional[Callable[[], int]] = None,
    ):
        self._db_path = db_path
        self._write_queue = write_queue
        self._config = config or CheckpointConfig()
        self._get_active_readers = get_active_readers
        self._last_checkpoint_time = time.time()
        self._last_restart_checkpoint_time = time.time()
        self._checkpoint_count = 0
        self._restart_checkpoint_count = 0
        self._failed_checkpoint_count = 0
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def checkpoint_count(self) -> int:
        return self._checkpoint_count

    @property
    def last_checkpoint_ago(self) -> float:
        return time.time() - self._last_checkpoint_time

    def get_wal_size_bytes(self) -> int:
        if self._db_path == ":memory:":
            return 0
        wal_path = self._db_path + "-wal"
        if os.path.exists(wal_path):
            return os.path.getsize(wal_path)
        return 0

    def get_wal_size_mb(self) -> float:
        return self.get_wal_size_bytes() / (1024 * 1024)

    def get_db_size_bytes(self) -> int:
        if self._db_path == ":memory:":
            return 0
        if os.path.exists(self._db_path):
            return os.path.getsize(self._db_path)
        return 0

    def should_checkpoint(self) -> Dict[str, Any]:
        reasons = []
        wal_size_mb = self.get_wal_size_mb()
        time_since_last = time.time() - self._last_checkpoint_time

        if wal_size_mb > self._config.wal_size_threshold_mb:
            reasons.append({
                "type": "wal_size",
                "detail": "WAL {0:.1f}MB > threshold {1:.1f}MB".format(
                    wal_size_mb, self._config.wal_size_threshold_mb
                ),
                "priority": "high",
                # [V007.40 BUG-FIX] mode: TRUNCATE → PASSIVE
                # 阈值触发也用 PASSIVE, 避免截断 WAL 触发 I/O error
                "mode": "PASSIVE",
            })

        if time_since_last > self._config.checkpoint_interval_seconds:
            reasons.append({
                "type": "time_interval",
                "detail": "{0:.0f}s > interval {1:.0f}s".format(
                    time_since_last, self._config.checkpoint_interval_seconds
                ),
                "priority": "medium",
                # [V007.40 BUG-FIX] mode: TRUNCATE → PASSIVE
                "mode": "PASSIVE",
            })

        if self._is_low_traffic_window():
            time_since_restart = time.time() - self._last_restart_checkpoint_time
            if time_since_restart > self._config.restart_checkpoint_interval_hours * 3600:
                reasons.append({
                    "type": "low_traffic_restart",
                    "detail": "Low traffic window + {0:.1f}h since restart checkpoint".format(
                        time_since_restart / 3600
                    ),
                    "priority": "low",
                    "mode": "RESTART",
                })

        return {
            "should": len(reasons) > 0,
            "reasons": reasons,
            "wal_size_mb": wal_size_mb,
            "time_since_last_seconds": time_since_last,
        }

    def execute_checkpoint(self, mode: str = "PASSIVE") -> Dict[str, Any]:
        """[V007.40 BUG-FIX] 默认 TRUNCATE → PASSIVE

        背景: V007.40 漏修了 default parameter. should_checkpoint() 返回的 mode
              已改 PASSIVE, 但 execute_checkpoint 的默认参数仍是 TRUNCATE.
              任何 caller 不传 mode 时仍会走 TRUNCATE → 截断 WAL → I/O error.
        修法: 默认 PASSIVE. RESTART 仍可通过显式 mode="RESTART" 触发 (低峰期专用).
        """
        result = {
            "mode": mode,
            "wal_size_before_mb": self.get_wal_size_mb(),
            "timestamp": time.time(),
            "success": False,
        }

        if self._config.passive_mode and mode != "RESTART":
            active = 0
            if self._get_active_readers:
                active = self._get_active_readers()
            if active > 0:
                mode = "PASSIVE"
                result["mode"] = mode
                result["fallback_reason"] = "active_readers={0}".format(active)

        try:
            if self._write_queue:
                self._write_queue.checkpoint(mode)
            result["success"] = True
            self._checkpoint_count += 1
            self._last_checkpoint_time = time.time()
            if mode == "RESTART":
                self._restart_checkpoint_count += 1
                self._last_restart_checkpoint_time = time.time()
        except Exception as e:
            self._failed_checkpoint_count += 1
            result["error"] = str(e)
            logger.error("Checkpoint failed (mode=%s): %s", mode, str(e))

        result["wal_size_after_mb"] = self.get_wal_size_mb()
        return result

    def auto_checkpoint(self) -> Optional[Dict[str, Any]]:
        check = self.should_checkpoint()
        if not check["should"]:
            return None

        reasons = check["reasons"]
        high_priority = [r for r in reasons if r["priority"] == "high"]
        if high_priority:
            mode = high_priority[0]["mode"]
        else:
            mode = reasons[0]["mode"]

        return self.execute_checkpoint(mode)

    def start_monitor(self, interval_seconds: float = 30.0):
        if self._running:
            return
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_seconds,),
            name="checkpoint-monitor",
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Checkpoint monitor started (interval=%ss)", interval_seconds)

    def stop_monitor(self):
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        logger.info("Checkpoint monitor stopped")

    def _monitor_loop(self, interval: float):
        while self._running:
            try:
                self.auto_checkpoint()
            except Exception as e:
                logger.error("Auto-checkpoint error: %s", str(e))
            time.sleep(interval)

    def _is_low_traffic_window(self) -> bool:
        current_hour = time.localtime().tm_hour
        start = self._config.low_traffic_window_start
        end = self._config.low_traffic_window_end
        if start <= end:
            return start <= current_hour < end
        else:
            return current_hour >= start or current_hour < end

    def get_stats(self) -> Dict[str, Any]:
        return {
            "checkpoint_count": self._checkpoint_count,
            "restart_checkpoint_count": self._restart_checkpoint_count,
            "failed_checkpoint_count": self._failed_checkpoint_count,
            "last_checkpoint_ago_seconds": self.last_checkpoint_ago,
            "wal_size_mb": self.get_wal_size_mb(),
            "db_size_mb": self.get_db_size_bytes() / (1024 * 1024),
            "wal_threshold_mb": self._config.wal_size_threshold_mb,
            "checkpoint_interval_seconds": self._config.checkpoint_interval_seconds,
        }
