#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DB 损坏监控和诊断工具

功能：
1. 记录每次 DB 访问的时间、操作、WAL 状态
2. 检测 DB 损坏并记录详细信息
3. 生成诊断报告
"""
import sqlite3
import json
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import threading

class DBCorruptionMonitor:
    """DB 损坏监控器"""

    def __init__(self, db_path: str, log_dir: str = None):
        self.db_path = db_path
        self.log_dir = log_dir or os.path.join(os.path.dirname(db_path), "db_monitor_logs")
        os.makedirs(self.log_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._access_log = []
        self._corruption_events = []

    def log_access(self, operation: str, details: Dict[str, Any] = None):
        """记录 DB 访问"""
        with self._lock:
            entry = {
                "ts": datetime.now().isoformat(),
                "op": operation,
                "wal_size": self._get_wal_size(),
                "db_size": self._get_db_size(),
                "details": details or {}
            }
            self._access_log.append(entry)

            # 只保留最近 1000 条
            if len(self._access_log) > 1000:
                self._access_log = self._access_log[-1000:]

            # [DECORATIVE] v3.18: 写入访问日志文件（用于追踪）
            try:
                access_log_file = os.path.join(
                    self.log_dir,
                    f"access_{datetime.now().strftime('%Y%m%d')}.jsonl"
                )
                with open(access_log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def check_and_log_integrity(self) -> bool:
        """检查完整性并记录结果"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()

            is_ok = result[0] == "ok"

            if not is_ok:
                self._log_corruption(result[0])

            return is_ok
        except Exception as e:
            self._log_corruption(str(e))
            return False

    def _log_corruption(self, error_msg: str):
        """记录损坏事件"""
        with self._lock:
            event = {
                "ts": datetime.now().isoformat(),
                "error": error_msg,
                "wal_size": self._get_wal_size(),
                "db_size": self._get_db_size(),
                "wal_mode": self._get_wal_mode(),
                "pending_frames": self._get_pending_wal_frames(),
                "recent_accesses": self._access_log[-10:]  # 最近 10 次访问
            }
            self._corruption_events.append(event)

            # 写入日志文件
            log_file = os.path.join(self.log_dir, f"corruption_{datetime.now().strftime('%Y%m%d')}.jsonl")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def generate_diagnostic_report(self) -> Dict[str, Any]:
        """生成诊断报告"""
        return {
            "db_path": self.db_path,
            "db_size": self._get_db_size(),
            "wal_size": self._get_wal_size(),
            "wal_mode": self._get_wal_mode(),
            "pending_frames": self._get_pending_wal_frames(),
            "integrity": self._check_integrity(),
            "corruption_count": len(self._corruption_events),
            "recent_corruptions": self._corruption_events[-5:],
            "recent_accesses": self._access_log[-20:],
            "generated_at": datetime.now().isoformat()
        }

    def _get_wal_size(self) -> int:
        wal_path = self.db_path + "-wal"
        return Path(wal_path).stat().st_size if Path(wal_path).exists() else 0

    def _get_db_size(self) -> int:
        return Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0

    def _get_wal_mode(self) -> str:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            result = conn.execute("PRAGMA journal_mode").fetchone()
            conn.close()
            return result[0]
        except:
            return "unknown"

    def _get_pending_wal_frames(self) -> int:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            cursor = conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            busy, log_frames, checkpointed = cursor.fetchone()
            conn.close()
            return max(0, log_frames - checkpointed)
        except:
            return -1

    def _check_integrity(self) -> str:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result[0]
        except Exception as e:
            return f"error: {e}"


# 全局监控器实例
_global_monitor: Optional[DBCorruptionMonitor] = None
_monitor_lock = threading.Lock()


def get_monitor(db_path: str = None) -> DBCorruptionMonitor:
    """获取全局监控器"""
    global _global_monitor
    with _monitor_lock:
        if _global_monitor is None:
            if db_path is None:
                # 修正路径：module 在 meta/core/db_corruption_monitor.py
                # 所以父目录是 meta/core，再上一层才是 meta
                db_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "meta", "architecture.db"
                )
            _global_monitor = DBCorruptionMonitor(db_path)
        return _global_monitor


def diagnose_db(db_path: str = None) -> Dict[str, Any]:
    """诊断 DB 并生成报告"""
    monitor = get_monitor(db_path)
    return monitor.generate_diagnostic_report()


if __name__ == "__main__":
    # 命令行诊断工具
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else r"d:\filework\excel-to-diagram\meta\architecture.db"

    print("=" * 70)
    print("DB 损坏诊断报告")
    print("=" * 70)

    report = diagnose_db(db_path)

    print(f"\nDB 路径: {report['db_path']}")
    print(f"DB 大小: {report['db_size'] / 1024:.1f} KB")
    print(f"WAL 大小: {report['wal_size'] / 1024:.1f} KB")
    print(f"WAL 模式: {report['wal_mode']}")
    print(f"待处理 WAL frames: {report['pending_frames']}")
    print(f"完整性检查: {report['integrity']}")
    print(f"损坏事件数: {report['corruption_count']}")

    if report['recent_corruptions']:
        print("\n最近损坏事件:")
        for event in report['recent_corruptions']:
            print(f"  - {event['ts']}: {event['error'][:100]}")

    print("\n" + "=" * 70)
