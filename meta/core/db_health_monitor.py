import os
import time
import sqlite3
import logging
import threading
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class HealthThresholds:
    wal_size_warn_bytes: int = 1 * 1024 * 1024
    wal_size_crit_bytes: int = 5 * 1024 * 1024
    wal_pending_frames_warn: int = 100
    wal_pending_frames_crit: int = 500
    integrity_check_interval: int = 200
    temp_file_count_warn: int = 100
    temp_file_age_hours: int = 2


@dataclass
class DBHealthSnapshot:
    timestamp: float = field(default_factory=time.time)
    db_size_bytes: int = 0
    wal_size_bytes: int = 0
    shm_size_bytes: int = 0
    wal_pending_frames: int = 0
    checkpoint_count: int = 0
    integrity_status: str = "unknown"
    concurrent_processes: int = 0
    temp_file_count: int = 0
    warnings: list = field(default_factory=list)


class DBHealthMonitor:
    def __init__(self, db_path: str, thresholds: HealthThresholds = None,
                 temp_dir: str = None):
        self._db_path = db_path
        self._thresholds = thresholds or HealthThresholds()
        self._temp_dir = temp_dir or os.path.join(os.path.dirname(db_path), "..", "test_temp")
        self._lock = threading.Lock()
        self._snapshots: list = []
        self._max_snapshots = 20
        self._checkpoint_count = 0
        self._integrity_counter = 0
        self._enabled = True

    @property
    def db_path(self) -> str:
        return self._db_path

    def record_checkpoint(self):
        with self._lock:
            self._checkpoint_count += 1
            self._integrity_counter += 1

    def collect_snapshot(self, force_integrity: bool = False) -> DBHealthSnapshot:
        snap = DBHealthSnapshot()

        db_file = Path(self._db_path)
        if db_file.exists():
            snap.db_size_bytes = db_file.stat().st_size

        wal_file = Path(self._db_path + "-wal")
        if wal_file.exists():
            snap.wal_size_bytes = wal_file.stat().st_size

        shm_file = Path(self._db_path + "-shm")
        if shm_file.exists():
            snap.shm_size_bytes = shm_file.stat().st_size

        snap.concurrent_processes = self._detect_concurrent()

        snap.temp_file_count = self._count_temp_files()

        snap.checkpoint_count = self._checkpoint_count

        should_check_integrity = force_integrity
        if not should_check_integrity and self._integrity_counter >= self._thresholds.integrity_check_interval:
            should_check_integrity = True
            self._integrity_counter = 0

        if should_check_integrity:
            snap.integrity_status = self._check_integrity_readonly()

        try:
            with sqlite3.connect(self._db_path, timeout=5) as conn:
                # [DECORATIVE] v3.18: PASSIVE → FULL（强制刷写，防止 WAL 残留导致损坏）
                cursor = conn.execute("PRAGMA wal_checkpoint(FULL)")
                busy, log_frames, checkpointed = cursor.fetchone()
                snap.wal_pending_frames = log_frames - checkpointed
                if snap.wal_pending_frames < 0:
                    snap.wal_pending_frames = 0
        except Exception as e:
            snap.warnings.append(f"wal_checkpoint failed: {e}")

        if snap.wal_size_bytes > self._thresholds.wal_size_crit_bytes:
            snap.warnings.append(
                f"WAL size CRITICAL: {snap.wal_size_bytes / 1024 / 1024:.1f}MB > "
                f"{self._thresholds.wal_size_crit_bytes / 1024 / 1024:.1f}MB"
            )
        elif snap.wal_size_bytes > self._thresholds.wal_size_warn_bytes:
            snap.warnings.append(
                f"WAL size WARNING: {snap.wal_size_bytes / 1024:.1f}KB"
            )

        if snap.wal_pending_frames > self._thresholds.wal_pending_frames_crit:
            snap.warnings.append(
                f"WAL pending frames CRITICAL: {snap.wal_pending_frames} > {self._thresholds.wal_pending_frames_crit}"
            )
        elif snap.wal_pending_frames > self._thresholds.wal_pending_frames_warn:
            snap.warnings.append(
                f"WAL pending frames WARNING: {snap.wal_pending_frames}"
            )

        if snap.concurrent_processes > 1:
            snap.warnings.append(
                f"Concurrent DB access detected: {snap.concurrent_processes} processes"
            )

        if snap.temp_file_count > self._thresholds.temp_file_count_warn:
            snap.warnings.append(
                f"Temp file count HIGH: {snap.temp_file_count} > {self._thresholds.temp_file_count_warn}"
            )

        with self._lock:
            self._snapshots.append(snap)
            if len(self._snapshots) > self._max_snapshots:
                self._snapshots = self._snapshots[-self._max_snapshots:]

        return snap

    def get_report(self) -> dict:
        with self._lock:
            if not self._snapshots:
                return {"status": "no_data", "message": "No snapshots collected yet"}

            latest = self._snapshots[-1]
            warnings = list(latest.warnings)

            if len(self._snapshots) >= 2:
                prev = self._snapshots[-2]
                wal_delta = latest.wal_pending_frames - prev.wal_pending_frames
                if wal_delta > 50:
                    warnings.append(f"WAL growing rapidly: +{wal_delta} frames since last check")

            return {
                "status": "critical" if any("CRITICAL" in w for w in warnings)
                else "warning" if warnings else "healthy",
                "timestamp": latest.timestamp,
                "metrics": {
                    "db_size_mb": round(latest.db_size_bytes / 1048576, 2),
                    "wal_size_kb": round(latest.wal_size_bytes / 1024, 1),
                    "wal_pending_frames": latest.wal_pending_frames,
                    "checkpoint_count": latest.checkpoint_count,
                    "integrity_status": latest.integrity_status,
                    "concurrent_processes": latest.concurrent_processes,
                    "temp_file_count": latest.temp_file_count,
                },
                "warnings": warnings,
                "snapshot_count": len(self._snapshots),
            }

    def log_health(self):
        report = self.get_report()
        if report["warnings"]:
            logger.warning("DB Health: %s - %s", report["status"], "; ".join(report["warnings"]))
        else:
            logger.debug("DB Health: %s", report["status"])
        return report

    def _detect_concurrent(self) -> int:
        count = 0
        try:
            db_dir = os.path.dirname(self._db_path)
            db_name = os.path.basename(self._db_path)
            for fname in [db_name, db_name + "-wal", db_name + "-shm"]:
                fpath = os.path.join(db_dir, fname)
                if os.path.exists(fpath):
                    try:
                        fd = os.open(fpath, os.O_RDONLY)
                        os.close(fd)
                    except OSError:
                        count += 1
        except Exception:
            pass
        return count

    def _count_temp_files(self) -> int:
        if not os.path.exists(self._temp_dir):
            return 0
        count = 0
        try:
            for fname in os.listdir(self._temp_dir):
                if fname.startswith("tmp") or fname.startswith("worker_"):
                    count += 1
        except Exception:
            pass
        return count

    def _check_integrity_readonly(self) -> str:
        try:
            with sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True, timeout=5) as conn:
                r = conn.execute("PRAGMA integrity_check").fetchone()
                return r[0]
        except Exception as e:
            return f"error: {e}"

    def disable(self):
        self._enabled = False

    def enable(self):
        self._enabled = True


_global_monitor: Optional[DBHealthMonitor] = None
_monitor_lock = threading.Lock()


def get_monitor(db_path: str = None) -> DBHealthMonitor:
    global _global_monitor
    with _monitor_lock:
        if _global_monitor is None:
            if db_path is None:
                db_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "meta", "architecture.db"
                )
            _global_monitor = DBHealthMonitor(db_path)
        return _global_monitor


def init_monitor(db_path: str, thresholds: HealthThresholds = None) -> DBHealthMonitor:
    global _global_monitor
    with _monitor_lock:
        _global_monitor = DBHealthMonitor(db_path, thresholds=thresholds)
        logger.info("DBHealthMonitor initialized for %s", db_path)
        return _global_monitor
