#!/usr/bin/env python3
"""
test_prune_agent_logs.py
=========================

FR-016 Agent 日志保留策略(90天) - prune_agent_logs.py 测试

测试 prune_agent_logs.py 的功能:
1. 扫描 .trae/state/ 下的 *.jsonl 文件
2. 超过 90 天的记录归档/删除
3. 聚合指标写入 agent-runs-aggregated.jsonl
4. 输出清理报告
5. dry-run 模式不修改文件
6. 自定义保留天数
"""

import gzip
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# 脚本路径
SCRIPTS_DIR = Path(__file__).parent.parent
PRUNE_SCRIPT = SCRIPTS_DIR / "prune_agent_logs.py"


@pytest.fixture
def temp_state_dir():
    """创建临时 state 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        yield state_dir


def _make_record(days_ago: int, skill: str = "test-gen", status: str = "success") -> dict:
    """创建指定天前的记录"""
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "requestId": f"test-{days_ago}-{skill}",
        "agentId": "agent-A",
        "skillName": skill,
        "startedAt": ts.isoformat(),
        "finishedAt": (ts + timedelta(seconds=60)).isoformat(),
        "status": status,
        "files_changed": ["test.spec.js"],
        "tokens_used": 1000,
        "coverage": {"lines": 85.0},
        "target": "test.js",
    }


@pytest.fixture
def mixed_age_state(temp_state_dir):
    """创建包含不同年龄记录的 state 目录"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    records = [
        _make_record(10),   # 10 天前 - 保留
        _make_record(30),   # 30 天前 - 保留
        _make_record(89),   # 89 天前 - 保留
        _make_record(91),   # 91 天前 - 删除
        _make_record(120),  # 120 天前 - 删除
        _make_record(200),  # 200 天前 - 删除
        _make_record(50, skill="code-review"),  # 50 天前 code-review - 保留
        _make_record(100, skill="code-review"),  # 100 天前 code-review - 删除
    ]

    with runs_file.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return temp_state_dir


def test_prune_script_exists():
    """测试脚本文件存在"""
    assert PRUNE_SCRIPT.exists(), f"prune_agent_logs.py not found at {PRUNE_SCRIPT}"


def test_prune_dry_run(mixed_age_state):
    """测试 dry-run 模式不修改文件"""
    runs_file = mixed_age_state / "agent-runs.jsonl"
    original_content = runs_file.read_text(encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--dry-run",
            "--state-dir",
            str(mixed_age_state),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # 文件内容不应变化
    assert runs_file.read_text(encoding="utf-8") == original_content

    # 输出应包含 DRY-RUN 标记
    assert "DRY-RUN" in result.stdout

    # 应显示保留和删除的数量 (4 keep: 10/30/89/50-code-review, 4 prune: 91/120/200/100-code-review)
    assert "keep=4" in result.stdout
    assert "prune=4" in result.stdout


def test_prune_actual(mixed_age_state):
    """测试实际清理"""
    result = subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--state-dir",
            str(mixed_age_state),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # 验证保留的记录数
    runs_file = mixed_age_state / "agent-runs.jsonl"
    remaining = [
        line for line in runs_file.read_text(encoding="utf-8").strip().split("\n") if line.strip()
    ]
    assert len(remaining) == 4  # 保留 4 条 (10/30/89 days test-gen + 50 days code-review)

    # 验证聚合文件存在
    agg_file = mixed_age_state / "agent-runs-aggregated.jsonl"
    assert agg_file.exists()

    # 验证归档文件存在
    archive_dir = mixed_age_state / "archive"
    assert archive_dir.exists()
    archives = list(archive_dir.glob("*.gz"))
    assert len(archives) >= 1


def test_prune_custom_retention(temp_state_dir):
    """测试自定义保留天数"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    records = [
        _make_record(5),   # 5 天前
        _make_record(15),  # 15 天前
        _make_record(25),  # 25 天前
        _make_record(35),  # 35 天前
    ]

    with runs_file.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # 保留 20 天
    subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--retention-days",
            "20",
            "--state-dir",
            str(temp_state_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    remaining = [
        line for line in runs_file.read_text(encoding="utf-8").strip().split("\n") if line.strip()
    ]
    assert len(remaining) == 2  # 5 天和 15 天的保留


def test_prune_no_archive(temp_state_dir):
    """测试不归档直接删除"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    records = [_make_record(100), _make_record(200)]

    with runs_file.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--no-archive",
            "--state-dir",
            str(temp_state_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # 归档目录不应存在
    archive_dir = temp_state_dir / "archive"
    assert not archive_dir.exists()


def test_prune_empty_file(temp_state_dir):
    """测试空文件处理"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    runs_file.write_text("")

    result = subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--dry-run",
            "--state-dir",
            str(temp_state_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "records_total: 0" in result.stdout


def test_prune_all_expired(temp_state_dir):
    """测试所有记录都过期"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    records = [_make_record(100), _make_record(200), _make_record(300)]

    with runs_file.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--state-dir",
            str(temp_state_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # 文件应被删除(所有记录过期)
    assert not runs_file.exists()


def test_prune_report_file(mixed_age_state):
    """测试清理报告文件生成"""
    subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--state-dir",
            str(mixed_age_state),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    report_file = mixed_age_state / "prune-report-latest.json"
    assert report_file.exists()

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["records_total"] == 8
    assert report["records_kept"] == 4  # 10/30/89 days test-gen + 50 days code-review
    assert report["records_pruned"] == 4  # 91/120/200 days test-gen + 100 days code-review
    assert "test-gen" in report["records_by_skill"]


def test_prune_aggregated_metrics(mixed_age_state):
    """测试聚合指标写入"""
    subprocess.run(
        [
            sys.executable,
            str(PRUNE_SCRIPT),
            "--state-dir",
            str(mixed_age_state),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    agg_file = mixed_age_state / "agent-runs-aggregated.jsonl"
    assert agg_file.exists()

    agg_content = agg_file.read_text(encoding="utf-8").strip()
    assert agg_content  # 非空

    agg_data = json.loads(agg_content)
    assert "aggregated_at" in agg_data
    assert "count" in agg_data
    assert agg_data["count"] == 4  # 4 条被清理 (91/120/200 days test-gen + 100 days code-review)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
