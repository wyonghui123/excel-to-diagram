#!/usr/bin/env python3
"""
metrics_aggregator.py
=====================

按 Spec v1.1 FR-010 要求,从 agent-runs.jsonl 生成 Prometheus 格式指标。

功能:
1. 读取 .trae/state/agent-runs.jsonl
2. 聚合指标:skill_invocation_total, skill_invocation_duration_seconds, skill_coverage_avg
3. 输出 Prometheus 文本格式或 JSON 格式
4. 支持按 skill_name/status 过滤

使用:
    python .trae/scripts/metrics_aggregator.py [--format prometheus|json] [--skill test-gen]

可选:
    --format prometheus   输出 Prometheus 文本格式(默认)
    --format json         输出 JSON 格式
    --skill <name>        只聚合指定 skill
    --status <status>     只聚合指定 status
    --state-dir <path>    自定义 state 目录

依赖:
    Python 3.10+ (标准库 only)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
AGENT_RUNS_FILE = STATE_DIR / "agent-runs.jsonl"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class MetricsData:
    """聚合指标数据"""

    skill_invocation_total: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    skill_invocation_duration_seconds: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    skill_coverage_avg: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    total_tokens_used: int = 0
    total_files_changed: int = 0
    records_processed: int = 0

    def to_prometheus(self) -> str:
        """转换为 Prometheus 文本格式"""
        lines = []

        # skill_invocation_total
        lines.append("# HELP skill_invocation_total Total number of skill invocations")
        lines.append("# TYPE skill_invocation_total counter")
        for skill_name, status_counts in sorted(self.skill_invocation_total.items()):
            for status, count in sorted(status_counts.items()):
                lines.append(
                    f'skill_invocation_total{{skill_name="{skill_name}",status="{status}"}} {count}'
                )

        # skill_invocation_duration_seconds
        lines.append(
            "# HELP skill_invocation_duration_seconds Duration of skill invocations in seconds"
        )
        lines.append("# TYPE skill_invocation_duration_seconds summary")
        for skill_name, durations in sorted(self.skill_invocation_duration_seconds.items()):
            if durations:
                avg_duration = sum(durations) / len(durations)
                lines.append(
                    f'skill_invocation_duration_seconds_sum{{skill_name="{skill_name}"}} {sum(durations):.3f}'
                )
                lines.append(
                    f'skill_invocation_duration_seconds_count{{skill_name="{skill_name}"}} {len(durations)}'
                )
                lines.append(
                    f'skill_invocation_duration_seconds_avg{{skill_name="{skill_name}"}} {avg_duration:.3f}'
                )

        # skill_coverage_avg (如果有 coverage 数据)
        lines.append("# HELP skill_coverage_avg Average test coverage percentage")
        lines.append("# TYPE skill_coverage_avg gauge")
        for skill_name, coverages in sorted(self.skill_coverage_avg.items()):
            if coverages:
                avg_coverage = sum(coverages) / len(coverages)
                lines.append(
                    f'skill_coverage_avg{{skill_name="{skill_name}"}} {avg_coverage:.1f}'
                )

        # 其他指标
        lines.append("# HELP skill_tokens_used_total Total tokens used by all skills")
        lines.append("# TYPE skill_tokens_used_total counter")
        lines.append(f"skill_tokens_used_total {self.total_tokens_used}")

        lines.append("# HELP skill_files_changed_total Total files changed by all skills")
        lines.append("# TYPE skill_files_changed_total counter")
        lines.append(f"skill_files_changed_total {self.total_files_changed}")

        lines.append("# HELP skill_records_processed_total Total records processed")
        lines.append("# TYPE skill_records_processed_total counter")
        lines.append(f"skill_records_processed_total {self.records_processed}")

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """转换为 JSON 格式"""
        return {
            "skill_invocation_total": {
                skill: dict(status_counts)
                for skill, status_counts in self.skill_invocation_total.items()
            },
            "skill_invocation_duration_seconds": {
                skill: {
                    "sum": sum(durations),
                    "count": len(durations),
                    "avg": sum(durations) / len(durations) if durations else 0,
                }
                for skill, durations in self.skill_invocation_duration_seconds.items()
            },
            "skill_coverage_avg": {
                skill: {
                    "avg": sum(coverages) / len(coverages) if coverages else 0,
                    "count": len(coverages),
                }
                for skill, coverages in self.skill_coverage_avg.items()
            },
            "total_tokens_used": self.total_tokens_used,
            "total_files_changed": self.total_files_changed,
            "records_processed": self.records_processed,
        }


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------


def parse_duration(started_at: str, finished_at: str) -> float | None:
    """计算持续时间(秒)"""
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finish = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        return (finish - start).total_seconds()
    except (ValueError, TypeError):
        return None


def extract_coverage(coverage_data: dict[str, Any] | None) -> float | None:
    """提取覆盖率数值"""
    if not coverage_data:
        return None
    # 优先使用 lines,其次 branches
    lines = coverage_data.get("lines")
    if lines is not None and isinstance(lines, (int, float)):
        return float(lines)
    branches = coverage_data.get("branches")
    if branches is not None and isinstance(branches, (int, float)):
        return float(branches)
    return None


def aggregate_metrics(
    state_dir: Path,
    skill_filter: str | None = None,
    status_filter: str | None = None,
) -> MetricsData:
    """聚合 agent-runs.jsonl 中的指标"""
    metrics = MetricsData()
    runs_file = state_dir / "agent-runs.jsonl"

    if not runs_file.exists():
        print(f"[WARN] Agent runs file not found: {runs_file}", file=sys.stderr)
        return metrics

    try:
        with runs_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                skill_name = record.get("skillName", "unknown")
                status = record.get("status", "unknown")

                # 应用过滤器
                if skill_filter and skill_name != skill_filter:
                    continue
                if status_filter and status != status_filter:
                    continue

                metrics.records_processed += 1

                # 1. skill_invocation_total
                metrics.skill_invocation_total[skill_name][status] += 1

                # 2. skill_invocation_duration_seconds
                started_at = record.get("startedAt")
                finished_at = record.get("finishedAt")
                if started_at and finished_at:
                    duration = parse_duration(started_at, finished_at)
                    if duration is not None and duration > 0:
                        metrics.skill_invocation_duration_seconds[skill_name].append(duration)

                # 3. skill_coverage_avg
                coverage_data = record.get("coverage")
                coverage = extract_coverage(coverage_data)
                if coverage is not None:
                    metrics.skill_coverage_avg[skill_name].append(coverage)

                # 4. tokens_used
                tokens = record.get("tokens_used")
                if tokens and isinstance(tokens, (int, float)):
                    metrics.total_tokens_used += int(tokens)

                # 5. files_changed
                files_changed = record.get("files_changed", [])
                if isinstance(files_changed, list):
                    metrics.total_files_changed += len(files_changed)

    except OSError as exc:
        print(f"[ERROR] Failed to read {runs_file}: {exc}", file=sys.stderr)

    return metrics


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=["prometheus", "json"],
        default="prometheus",
        help="Output format (default: prometheus)",
    )
    parser.add_argument(
        "--skill",
        type=str,
        default=None,
        help="Filter by skill name",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter by status (running/success/failed/denied)",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=STATE_DIR,
        help=f"State directory (default: {STATE_DIR})",
    )
    args = parser.parse_args()

    metrics = aggregate_metrics(args.state_dir, args.skill, args.status)

    if args.format == "prometheus":
        print(metrics.to_prometheus())
    else:
        print(json.dumps(metrics.to_json(), indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
