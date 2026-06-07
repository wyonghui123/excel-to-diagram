# -*- coding: utf-8 -*-
"""
数据库自动维护调度器

后台定时执行数据库维护任务：
- 定时 ANALYZE
- 定时 VACUUM
- 定时 integrity_check
- WAL 文件自动清理
- 慢查询统计报告
- 数据库文件增长趋势
"""

import time
import threading
import logging
import os
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceTask:
    name: str
    func: Callable
    interval_seconds: float
    last_run: float = 0
    run_count: int = 0
    error_count: int = 0
    last_result: Optional[Dict[str, Any]] = None
    enabled: bool = True


class MaintenanceScheduler:
    """数据库自动维护调度器

    使用方式：
        scheduler = MaintenanceScheduler(data_source)
        scheduler.add_task("analyze", analyze_func, interval=86400)
        scheduler.add_task("checkpoint", checkpoint_func, interval=300)
        scheduler.start()
    """

    def __init__(self, data_source=None, db_path: str = ""):
        self._data_source = data_source
        self._db_path = db_path
        self._tasks: Dict[str, MaintenanceTask] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._daily_stats: Dict[str, Any] = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "db_size_bytes": 0,
            "wal_size_bytes": 0,
            "slow_query_count": 0,
        }

    def add_task(self, name: str, func: Callable, interval_seconds: float, enabled: bool = True):
        self._tasks[name] = MaintenanceTask(
            name=name,
            func=func,
            interval_seconds=interval_seconds,
            enabled=enabled,
        )

    def remove_task(self, name: str):
        self._tasks.pop(name, None)

    def setup_default_tasks(self):
        ds = self._data_source
        if ds is None:
            return

        def _analyze():
            ds.execute("ANALYZE")
            return {"action": "ANALYZE", "status": "completed"}

        def _integrity_check():
            result = ds.query("PRAGMA integrity_check")
            return {"action": "integrity_check", "result": result}

        def _checkpoint():
            ds.checkpoint("TRUNCATE")
            return {"action": "checkpoint", "status": "completed"}

        def _record_db_size():
            db_path = getattr(ds, '_db_path', self._db_path)
            if db_path and db_path != ":memory:" and os.path.exists(db_path):
                db_size = os.path.getsize(db_path)
                wal_size = os.path.getsize(db_path + "-wal") if os.path.exists(db_path + "-wal") else 0
                self._daily_stats["db_size_bytes"] = db_size
                self._daily_stats["wal_size_bytes"] = wal_size
                return {"db_size_bytes": db_size, "wal_size_bytes": wal_size}
            return {"mode": "memory"}

        self.add_task("analyze", _analyze, interval_seconds=86400)
        self.add_task("integrity_check", _integrity_check, interval_seconds=21600)
        self.add_task("checkpoint", _checkpoint, interval_seconds=300)
        self.add_task("record_db_size", _record_db_size, interval_seconds=3600)

    def start(self, check_interval: float = 60.0):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            args=(check_interval,),
            name="db-maintenance",
            daemon=True,
        )
        self._thread.start()
        logger.info("Maintenance scheduler started (%d tasks)", len(self._tasks))

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        logger.info("Maintenance scheduler stopped")

    def _scheduler_loop(self, check_interval: float):
        while self._running:
            now = time.time()
            for name, task in self._tasks.items():
                if not task.enabled:
                    continue
                if now - task.last_run >= task.interval_seconds:
                    try:
                        result = task.func()
                        task.last_run = now
                        task.run_count += 1
                        task.last_result = result
                        logger.debug("Maintenance task '%s' completed", name)
                    except Exception as e:
                        task.error_count += 1
                        logger.error("Maintenance task '%s' failed: %s", name, str(e))

            today = datetime.now().strftime("%Y-%m-%d")
            if self._daily_stats["date"] != today:
                self._daily_stats = {
                    "date": today,
                    "db_size_bytes": self._daily_stats.get("db_size_bytes", 0),
                    "wal_size_bytes": self._daily_stats.get("wal_size_bytes", 0),
                    "slow_query_count": 0,
                }

            time.sleep(check_interval)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "tasks": {
                name: {
                    "enabled": task.enabled,
                    "interval_seconds": task.interval_seconds,
                    "run_count": task.run_count,
                    "error_count": task.error_count,
                    "last_run_ago_seconds": time.time() - task.last_run if task.last_run > 0 else None,
                }
                for name, task in self._tasks.items()
            },
            "daily_stats": self._daily_stats,
        }

    def enable_task(self, name: str):
        if name in self._tasks:
            self._tasks[name].enabled = True

    def disable_task(self, name: str):
        if name in self._tasks:
            self._tasks[name].enabled = False
