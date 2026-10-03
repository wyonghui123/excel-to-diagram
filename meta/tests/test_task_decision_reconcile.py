import pytest

pytestmark = pytest.mark.unit

import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 决策-生效跨库对账 CLI（B3 接线点②跨库分支）
测试 meta.tools.task_decision_reconcile.main（契约镜像 meta/tools/task_hold_reconcile.py）

覆盖目标：
  1. 库文件不存在 → 退出码 2（不静默新建空库）
  2. 干净库 → 退出码 0
  3. 存在 findings + --strict → 退出码 1
  4. 注入参数非法 JSON / 类型不符 → 退出码 2
"""

import json
from datetime import datetime

from meta.tools.task_decision_reconcile import main


def _build_db(tmp_path, name="b3_cli.db", *, with_done_task=False):
    from meta.core.datasource import get_data_source
    from meta.core.task_schema import ensure_task_tables

    path = str(tmp_path / name)
    ds = get_data_source("sqlite", database=path)
    with ds.transaction():
        ensure_task_tables(ds)
        if with_done_task:
            now = datetime.now().isoformat(timespec="seconds")
            ds.execute(
                "INSERT INTO tasks (id, title, type, status, executor_type, "
                "created_at, updated_at) VALUES (?, ?, 'approval', 'done', 'system', ?, ?)",
                ("T-BAD", "审批任务", now, now),
            )
    return path


def test_TC_B3CLI_001_库不存在退出2(tmp_path):
    assert main(["--db", str(tmp_path / "missing.db")]) == 2


def test_TC_B3CLI_002_干净库退出0(tmp_path, capsys):
    db = _build_db(tmp_path)

    assert main(["--db", db]) == 0
    assert "[OK] 无发现" in capsys.readouterr().out


def test_TC_B3CLI_003_strict有发现退出1(tmp_path, capsys):
    db = _build_db(tmp_path, with_done_task=True)
    capsys.readouterr()          # 丢弃建库阶段的 datasource 写告警，避免污染 JSON 解析

    assert main(["--db", db, "--strict", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["findings"][0]["kind"] == "done_without_effect"


def test_TC_B3CLI_004_注入参数非法退出2(tmp_path, capsys):
    db = _build_db(tmp_path)

    assert main(["--db", db, "--current-statuses-json", "{not json"]) == 2
    assert "[ERROR]" in capsys.readouterr().out