#!/usr/bin/env python3
"""
prune_agent_logs.py
===================

按 Spec v1.1 FR-016 要求,清理 .trae/state/agent-runs.jsonl 超过 90 天的日志。

功能:
1. 扫描 .trae/state/ 下的 *.jsonl 文件
2. 超过 90 天的记录 → 生成聚合指标后归档或删除
3. 聚合指标写入 .trae/state/agent-runs-aggregated.jsonl(永久保留)
4. 输出清理报告(数量、时间、聚合指标)

使用:
    python .trae/scripts/prune_agent_logs.py [--dry-run] [--retention-days 90]

可选:
    --dry-run       只扫描,不删除
    --retention-days N   保留天数(默认 90)
    --archive       删除前归档到 archive/ 目录(默认 True)
    --no-archive    直接删除,不归档

依赖:
    Python 3.10+ (标准库 only)
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_RETENTION_DAYS = 90  # Spec v1.1 FR-016 默认
STATE_DIR = Path(__file__).resolve().parent.parent / "state"
ARCHIVE_DIR = STATE_DIR / "archive"
AGGREGATED_FILE = STATE_DIR / "agent-runs-aggregated.jsonl"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class LogEntry:
    """单条 agent-runs 记录"""

    raw: dict[str, Any]
    timestamp: datetime

    @classmethod
    def from_jsonl(cls, line: str) -> "LogEntry | None":
        """解析单行 JSONL"""
        line = line.strip()
        if not line:
            return None
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        # 提取时间戳(多种格式兼容)
        ts_str = data.get("startedAt") or data.get("timestamp") or data.get("ts")
        if not ts_str:
            return None
        try:
            # ISO 8601
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            return None
        return cls(raw=data, timestamp=ts)

    @property
    def age_days(self) -> float:
        """距今天数"""
        now = datetime.now(timezone.utc)
        return (now - self.timestamp).total_seconds() / 86400


@dataclass
class PruneReport:
    """清理报告"""

    files_scanned: int = 0
    files_archived: int = 0
    files_deleted: int = 0
    records_total: int = 0
    records_kept: int = 0
    records_pruned: int = 0
    records_by_skill: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    records_by_status: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_scanned": self.files_scanned,
            "files_archived": self.files_archived,
            "files_deleted": self.files_deleted,
            "records_total": self.records_total,
            "records_kept": self.records_kept,
            "records_pruned": self.records_pruned,
            "records_by_skill": dict(self.records_by_skill),
            "records_by_status": dict(self.records_by_status),
        }


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def iter_entries(path: Path) -> Iterator[LogEntry]:
    """迭代 JSONL 文件中的所有有效条目"""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                entry = LogEntry.from_jsonl(line)
                if entry:
                    yield entry
    except OSError as exc:
        print(f"[WARN] Failed to read {path}: {exc}", file=sys.stderr)


def aggregate_entries(entries: list[LogEntry]) -> dict[str, Any]:
    """生成聚合指标"""
    by_skill: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    for entry in entries:
        skill = entry.raw.get("skillName", "unknown")
        status = entry.raw.get("status", "unknown")
        by_skill[skill] += 1
        by_status[status] += 1
    return {
        "aggregated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "by_skill": dict(by_skill),
        "by_status": dict(by_status),
    }


def archive_file(path: Path, archive_dir: Path) -> Path | None:
    """归档文件(gzip 压缩)"""
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d")
        archive_name = f"{path.stem}.{ts}.gz"
        archive_path = archive_dir / archive_name
        with path.open("rb") as src, gzip.open(archive_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return archive_path
    except OSError as exc:
        print(f"[WARN] Failed to archive {path}: {exc}", file=sys.stderr)
        return None


def prune_file(
    path: Path,
    retention_days: float,
    dry_run: bool,
    archive: bool,
    report: PruneReport,
    state_dir: Path | None = None,
) -> None:
    """处理单个 JSONL 文件"""
    entries = list(iter_entries(path))
    if not entries:
        return

    report.files_scanned += 1
    report.records_total += len(entries)

    # 分类:保留 vs 删除
    keep_entries: list[LogEntry] = []
    prune_entries: list[LogEntry] = []
    for entry in entries:
        if entry.age_days > retention_days:
            prune_entries.append(entry)
        else:
            keep_entries.append(entry)

    report.records_kept += len(keep_entries)
    report.records_pruned += len(prune_entries)

    # 更新统计
    for entry in entries:
        skill = entry.raw.get("skillName", "unknown")
        status = entry.raw.get("status", "unknown")
        report.records_by_skill[skill] += 1
        report.records_by_status[status] += 1

    if dry_run:
        print(
            f"[DRY-RUN] {path.name}: total={len(entries)}, "
            f"keep={len(keep_entries)}, prune={len(prune_entries)}"
        )
        return

    # 使用传入的 state_dir 或默认
    effective_state_dir = state_dir or STATE_DIR
    effective_archive_dir = effective_state_dir / "archive"
    effective_aggregated_file = effective_state_dir / "agent-runs-aggregated.jsonl"

    # 1. 归档/删除旧记录
    if prune_entries:
        if archive:
            archive_file(path, effective_archive_dir)
            report.files_archived += 1
        # 写聚合指标
        if effective_state_dir.exists():
            agg = aggregate_entries(prune_entries)
            with effective_aggregated_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(agg, ensure_ascii=False) + "\n")

    # 2. 写回保留的记录
    if keep_entries:
        with path.open("w", encoding="utf-8") as f:
            for entry in keep_entries:
                f.write(json.dumps(entry.raw, ensure_ascii=False) + "\n")
    else:
        # 全删除
        path.unlink(missing_ok=True)
        report.files_deleted += 1
        print(f"[INFO] Removed {path.name} (all records expired)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=float,
        default=DEFAULT_RETENTION_DAYS,
        help=f"Retention days (default: {DEFAULT_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan, do not delete",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        default=True,
        help="Archive before delete (default: True)",
    )
    parser.add_argument(
        "--no-archive",
        action="store_false",
        dest="archive",
        help="Delete without archive",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=STATE_DIR,
        help=f"State dir (default: {STATE_DIR})",
    )
    args = parser.parse_args()

    state_dir: Path = args.state_dir
    if not state_dir.exists():
        print(f"[ERROR] State dir not found: {state_dir}", file=sys.stderr)
        return 1

    print(f"[INFO] Scanning {state_dir} (retention={args.retention_days} days)")
    if args.dry_run:
        print("[INFO] DRY-RUN mode: no changes will be made")

    report = PruneReport()
    jsonl_files = sorted(state_dir.glob("agent-runs*.jsonl"))
    for path in jsonl_files:
        prune_file(path, args.retention_days, args.dry_run, args.archive, report, state_dir)

    # 输出报告
    print("\n" + "=" * 60)
    print("Prune Report")
    print("=" * 60)
    for key, value in report.to_dict().items():
        print(f"  {key}: {value}")
    print("=" * 60)

    # 写报告到文件
    report_file = state_dir / "prune-report-latest.json"
    if not args.dry_run:
        report_file.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())