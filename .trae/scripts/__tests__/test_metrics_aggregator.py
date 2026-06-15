#!/usr/bin/env python3
"""
test_metrics_aggregator.py
===========================

FR-010 Custom Store 等效 - 可观测性指标聚合测试

测试 metrics_aggregator.py 的功能:
1. 从 agent-runs.jsonl 读取记录
2. 聚合 skill_invocation_total 指标
3. 聚合 skill_invocation_duration_seconds 指标
4. 聚合 skill_coverage_avg 指标
5. 输出 Prometheus 格式
6. 输出 JSON 格式
7. 按 skill/status 过滤
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# 脚本路径
SCRIPTS_DIR = Path(__file__).parent.parent
METRICS_SCRIPT = SCRIPTS_DIR / "metrics_aggregator.py"


@pytest.fixture
def temp_state_dir():
    """创建临时 state 目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        yield state_dir


@pytest.fixture
def sample_agent_runs(temp_state_dir):
    """创建示例 agent-runs.jsonl"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    records = [
        {
            "requestId": "test-001",
            "agentId": "agent-A",
            "skillName": "test-gen",
            "startedAt": "2026-06-13T10:00:00Z",
            "finishedAt": "2026-06-13T10:01:30Z",
            "status": "success",
            "files_changed": ["src/utils/test.spec.js"],
            "tokens_used": 3420,
            "coverage": {"lines": 85.5, "branches": 78.2},
            "target": "src/utils/test.js",
        },
        {
            "requestId": "test-002",
            "agentId": "agent-A",
            "skillName": "test-gen",
            "startedAt": "2026-06-13T10:05:00Z",
            "finishedAt": "2026-06-13T10:06:45Z",
            "status": "success",
            "files_changed": ["src/components/Test.spec.js"],
            "tokens_used": 4200,
            "coverage": {"lines": 92.0, "branches": 85.0},
            "target": "src/components/Test.vue",
        },
        {
            "requestId": "test-003",
            "agentId": "agent-B",
            "skillName": "code-review",
            "startedAt": "2026-06-13T10:10:00Z",
            "finishedAt": "2026-06-13T10:11:20Z",
            "status": "success",
            "files_changed": [],
            "tokens_used": 1500,
            "coverage": None,
            "target": "src/utils/helper.js",
        },
        {
            "requestId": "test-004",
            "agentId": "agent-A",
            "skillName": "test-gen",
            "startedAt": "2026-06-13T10:15:00Z",
            "finishedAt": "2026-06-13T10:16:10Z",
            "status": "failed",
            "files_changed": [],
            "tokens_used": 2800,
            "coverage": None,
            "target": "src/utils/broken.js",
        },
    ]

    with runs_file.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return temp_state_dir


def test_metrics_aggregator_exists():
    """测试脚本文件存在"""
    assert METRICS_SCRIPT.exists(), f"metrics_aggregator.py not found at {METRICS_SCRIPT}"


def test_metrics_aggregator_help():
    """测试脚本可以显示帮助信息"""
    result = subprocess.run(
        [sys.executable, str(METRICS_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "usage:" in result.stdout.lower() or "options" in result.stdout.lower()


def test_metrics_aggregator_prometheus_format(sample_agent_runs):
    """测试 Prometheus 格式输出"""
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "prometheus",
            "--state-dir",
            str(sample_agent_runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    output = result.stdout

    # 验证包含必要的 Prometheus 指标
    assert "skill_invocation_total" in output
    assert "skill_invocation_duration_seconds" in output
    assert "skill_tokens_used_total" in output
    assert "skill_files_changed_total" in output

    # 验证 test-gen skill 的指标
    assert 'skill_name="test-gen"' in output

    # 验证 status 标签
    assert 'status="success"' in output
    assert 'status="failed"' in output


def test_metrics_aggregator_json_format(sample_agent_runs):
    """测试 JSON 格式输出"""
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--state-dir",
            str(sample_agent_runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    # 验证必要字段
    assert "skill_invocation_total" in data
    assert "skill_invocation_duration_seconds" in data
    assert "skill_coverage_avg" in data
    assert "total_tokens_used" in data
    assert "total_files_changed" in data
    assert "records_processed" in data

    # 验证 test-gen 的调用次数
    assert "test-gen" in data["skill_invocation_total"]
    test_gen_counts = data["skill_invocation_total"]["test-gen"]
    assert test_gen_counts.get("success", 0) == 2
    assert test_gen_counts.get("failed", 0) == 1

    # 验证 code-review 的调用次数
    assert "code-review" in data["skill_invocation_total"]
    assert data["skill_invocation_total"]["code-review"].get("success", 0) == 1

    # 验证总 tokens
    assert data["total_tokens_used"] == 3420 + 4200 + 1500 + 2800

    # 验证总文件变更
    assert data["total_files_changed"] == 2  # 只有 2 个文件被变更


def test_metrics_aggregator_skill_filter(sample_agent_runs):
    """测试按 skill 过滤"""
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--skill",
            "test-gen",
            "--state-dir",
            str(sample_agent_runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    # 应该只包含 test-gen
    assert "test-gen" in data["skill_invocation_total"]
    assert "code-review" not in data["skill_invocation_total"]

    # 验证记录数
    assert data["records_processed"] == 3  # 3 条 test-gen 记录


def test_metrics_aggregator_status_filter(sample_agent_runs):
    """测试按 status 过滤"""
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--status",
            "success",
            "--state-dir",
            str(sample_agent_runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    # 应该只包含 success 状态的记录
    assert data["records_processed"] == 3  # 3 条 success 记录

    # 验证 test-gen 只有 success
    test_gen_counts = data["skill_invocation_total"]["test-gen"]
    assert test_gen_counts.get("success", 0) == 2
    assert "failed" not in test_gen_counts


def test_metrics_aggregator_empty_file(temp_state_dir):
    """测试空文件处理"""
    runs_file = temp_state_dir / "agent-runs.jsonl"
    runs_file.write_text("")

    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--state-dir",
            str(temp_state_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    assert data["records_processed"] == 0
    assert data["total_tokens_used"] == 0


def test_metrics_aggregator_missing_file(temp_state_dir):
    """测试文件不存在时的处理"""
    # 不创建 agent-runs.jsonl
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--state-dir",
            str(temp_state_dir),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    assert data["records_processed"] == 0


def test_metrics_aggregator_duration_calculation(sample_agent_runs):
    """测试持续时间计算"""
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--state-dir",
            str(sample_agent_runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    # 验证 test-gen 的持续时间
    assert "test-gen" in data["skill_invocation_duration_seconds"]
    test_gen_duration = data["skill_invocation_duration_seconds"]["test-gen"]

    # 应该有 3 条记录(2 success + 1 failed)
    assert test_gen_duration["count"] == 3

    # 验证平均时间(大约 90 秒)
    # test-001: 90s, test-002: 105s, test-004: 70s
    # 平均: (90 + 105 + 70) / 3 = 88.33s
    assert 85 <= test_gen_duration["avg"] <= 95


def test_metrics_aggregator_coverage_calculation(sample_agent_runs):
    """测试覆盖率计算"""
    result = subprocess.run(
        [
            sys.executable,
            str(METRICS_SCRIPT),
            "--format",
            "json",
            "--state-dir",
            str(sample_agent_runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)

    # 验证 test-gen 的覆盖率
    assert "test-gen" in data["skill_coverage_avg"]
    test_gen_coverage = data["skill_coverage_avg"]["test-gen"]

    # 应该只有 2 条记录有覆盖率(2 个 success)
    assert test_gen_coverage["count"] == 2

    # 验证平均覆盖率(85.5 + 92.0) / 2 = 88.75
    assert 88 <= test_gen_coverage["avg"] <= 89


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
