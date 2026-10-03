# -*- coding: utf-8 -*-
"""后端测试套件 - [F1] hold / release 事件化 + 当前态派生视图（不改状态列）

测试 meta.core.task_hold 的 hold_task / release_task / current_holds /
ensure_hold_view / rebuild_hold_view / hold_findings

覆盖目标（对齐 §12 F1 / §12.1 Q3 / 综合 §6.3）:
  1. **不改状态列**: hold / release 前后 tasks 行逐字段不变（护住纪律核心回归）
  2. 事件化: hold / release 各落一条 TASK_EVENT；不产生 status_changed / WORKLOG
  3. 严格交替: 重复 hold 同码 / 释放未激活 / 空 hold_code / 任务不存在 → 确定性错误
  4. 派生态: active_flag 差值语义、多码并存互不干扰、release 后可再 hold
  5. 视图: ensure 幂等、rebuild 原子替换 + 修复漂移、视图缺失读取报错
  6. 巡检: 干净态 ok；账缺失 / 视图缺失 / 未交替 / 缺 hold_code 均被机器发现
  7. CLI: --json 机读 / --strict 退出码 / --rebuild 端到端 / 缺库 exit 2

注: 平台内部表（tasks / task_events）暂无 Factory；按仓库既有惯例走 raw SQL
escape hatch（同 test_decision_effect.py 注释），raw 写仅用于**预置脏数据**。

对应方案: docs/superpowers/specs/2026-09-07-task-model-design.md §12 F1 / §12.1 Q3
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
import uuid

import pytest

from meta.core.task_event_schema import (
    TASK_EVENT_TABLE,
    WORKLOG_TABLE,
    ensure_task_event_tables,
)
from meta.core.task_hold import (
    HOLD_VIEW,
    TaskHoldError,
    current_holds,
    ensure_hold_view,
    hold_findings,
    hold_task,
    hold_view_exists,
    rebuild_hold_view,
    release_task,
)
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import advance_run, list_run_tasks, start_run
from meta.core.workflow_store import publish_workflow
from meta.tools.task_hold_reconcile import main as hold_reconcile_main

pytestmark = pytest.mark.unit

WF_KEY = "wf-f1"
AT = "2026-10-03T10:00:00"


# ─────────────────────────────────────────────────────────────────────────────
# 夹具 / 助手
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（任务四表 + 事件账两表 + hold 派生视图）。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "f1.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_hold_view(source)
    yield source


def _single_task(ds, key=WF_KEY):
    """发布单节点定义并实例化；advance 后该节点为 ready。"""
    publish_workflow(ds, workflow_key=key, name="F1 流程",
                     nodes=[{"node_id": "n1", "title": "受理",
                             "executor_type": "human", "step_number": 1}],
                     edges=None)
    run = start_run(ds, workflow_key=key)
    advance_run(ds, run["run_id"])
    tasks = list_run_tasks(ds, run["run_id"])
    return run, tasks[0]


def _task_snapshot(ds, task_id):
    """任务整行快照（逐字段比对，锁死「不改状态列」）。"""
    return ds.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def _count(ds, sql, params=()):
    return ds.execute(sql, params).fetchone()[0]


def _raw_event(ds, task_id, event_type, payload, occurred_at=AT):
    """绕过入口 API 直插事件（预置脏数据用）。"""
    with ds.transaction():
        ds.execute(
            "INSERT INTO {0} (id, task_id, event_type, payload, occurred_at, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?)".format(TASK_EVENT_TABLE),
            (uuid.uuid4().hex, task_id, event_type, payload, occurred_at, occurred_at),
        )


# ─────────────────────────────────────────────────────────────────────────────
# ① 写路径：hold / release
# ─────────────────────────────────────────────────────────────────────────────

class TestHoldAndRelease:
    def test_hold_writes_event_only_row_unchanged(self, ds):
        """TC-WFH-001: hold 只落一条事件，tasks 整行（含 status）逐字段不变。"""
        _, task = _single_task(ds)
        before = _task_snapshot(ds, task["id"])

        event_id = hold_task(
            ds, task["id"], hold_code="Q1", reason="质量待判",
            actor="u-1", actor_kind="human", doc_ref="SO-1", occurred_at=AT)

        assert _task_snapshot(ds, task["id"]) == before          # 整行不变
        rows = ds.execute(
            "SELECT id, event_type, from_status, to_status, actor, actor_kind, "
            "reason, payload, doc_ref, occurred_at FROM {0} WHERE id = ?".format(
                TASK_EVENT_TABLE), (event_id,)).fetchall()
        assert len(rows) == 1
        eid, etype, from_s, to_s, actor, akind, reason, payload, doc_ref, occ = rows[0]
        assert (eid, etype) == (event_id, "hold")
        assert from_s is None and to_s is None                    # 非迁移事件
        assert (actor, akind) == ("u-1", "human")
        assert reason == "质量待判"
        assert json.loads(payload)["hold_code"] == "Q1"
        assert doc_ref == "SO-1"
        assert occ == AT

    def test_hold_records_no_status_event_or_worklog(self, ds):
        """TC-WFH-002: hold 不新增 status_changed，也不写 WORKLOG。"""
        _, task = _single_task(ds)
        events_before = _count(ds, "SELECT COUNT(*) FROM {0}".format(TASK_EVENT_TABLE))
        logs_before = _count(ds, "SELECT COUNT(*) FROM {0}".format(WORKLOG_TABLE))
        transitions_before = _count(
            ds, "SELECT COUNT(*) FROM {0} WHERE event_type = 'status_changed'".format(
                TASK_EVENT_TABLE))

        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        assert _count(ds, "SELECT COUNT(*) FROM {0}".format(TASK_EVENT_TABLE)) \
            == events_before + 1
        assert _count(
            ds,
            "SELECT COUNT(*) FROM {0} WHERE event_type = 'status_changed'".format(
                TASK_EVENT_TABLE)) == transitions_before
        assert _count(ds, "SELECT COUNT(*) FROM {0}".format(WORKLOG_TABLE)) \
            == logs_before

    def test_duplicate_hold_rejected(self, ds):
        """TC-WFH-003: 同 (task, hold_code) 未释放前重复 hold 被拒绝。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        with pytest.raises(TaskHoldError):
            hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        assert _count(
            ds, "SELECT COUNT(*) FROM {0} WHERE event_type = 'hold'".format(
                TASK_EVENT_TABLE)) == 1

    def test_release_requires_active_hold(self, ds):
        """TC-WFH-004: 未 hold 直接 release 被拒绝，账本不落脏事件。"""
        _, task = _single_task(ds)
        before = _count(ds, "SELECT COUNT(*) FROM {0}".format(TASK_EVENT_TABLE))
        with pytest.raises(TaskHoldError):
            release_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        assert _count(ds, "SELECT COUNT(*) FROM {0}".format(TASK_EVENT_TABLE)) == before

    def test_release_clears_active_flag(self, ds):
        """TC-WFH-005: release 后派生态回落到 0；任务行仍不变。"""
        _, task = _single_task(ds)
        before = _task_snapshot(ds, task["id"])
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        release_task(ds, task["id"], hold_code="Q1", reason="质量通过",
                     actor="u-2", actor_kind="human", occurred_at="2026-10-03T11:00:00")

        assert _task_snapshot(ds, task["id"]) == before
        row = [r for r in current_holds(ds, active_only=False)
               if r["task_id"] == task["id"]][0]
        assert row["active_flag"] == 0
        assert row["event_count"] == 2
        assert current_holds(ds) == []                    # active_only 默认

    def test_hold_code_required(self, ds):
        """TC-WFH-006: hold_code 为空 → hold / release 均拒绝。"""
        _, task = _single_task(ds)
        with pytest.raises(TaskHoldError):
            hold_task(ds, task["id"], hold_code="  ", occurred_at=AT)
        with pytest.raises(TaskHoldError):
            release_task(ds, task["id"], hold_code="", occurred_at=AT)

    def test_unknown_task_rejected(self, ds):
        """TC-WFH-007: 任务不存在 → 拒绝，事件账不落脏。"""
        before = _count(ds, "SELECT COUNT(*) FROM {0}".format(TASK_EVENT_TABLE))
        with pytest.raises(TaskHoldError):
            hold_task(ds, "no-such-task", hold_code="Q1", occurred_at=AT)
        with pytest.raises(TaskHoldError):
            release_task(ds, "no-such-task", hold_code="Q1", occurred_at=AT)
        assert _count(ds, "SELECT COUNT(*) FROM {0}".format(TASK_EVENT_TABLE)) == before

    def test_multiple_codes_independent(self, ds):
        """TC-WFH-008: 同任务多 hold 码并存，释放其一不影响另一。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        hold_task(ds, task["id"], hold_code="CREDIT", occurred_at=AT)

        active = {r["hold_code"]: r["active_flag"] for r in current_holds(ds)}
        assert active == {"Q1": 1, "CREDIT": 1}

        release_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        active = {r["hold_code"]: r["active_flag"]
                  for r in current_holds(ds, active_only=False)}
        assert active == {"Q1": 0, "CREDIT": 1}

    def test_release_then_hold_again_allowed(self, ds):
        """TC-WFH-009: release 后同码可再次 hold（严格交替，账本累积）。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        release_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        row = current_holds(ds)[0]
        assert row["hold_code"] == "Q1"
        assert row["active_flag"] == 1
        assert row["event_count"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# ② 当前态派生视图
# ─────────────────────────────────────────────────────────────────────────────

class TestCurrentHolds:
    def test_view_derives_active_flag(self, ds):
        """TC-WFH-020: 视图按 (task, hold_code) 差值派生当前态。"""
        _, task = _single_task(ds)
        assert hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        rows = current_holds(ds, task_id=task["id"])
        assert len(rows) == 1
        r = rows[0]
        assert r["hold_code"] == "Q1"
        assert r["active_flag"] == 1
        assert r["event_count"] == 1
        assert r["first_hold_at"] == AT
        assert r["last_event_at"] == AT

    def test_active_only_filter(self, ds):
        """TC-WFH-021: active_only 过滤已释放的 hold 组。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        hold_task(ds, task["id"], hold_code="Q2", occurred_at=AT)
        release_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        assert [r["hold_code"] for r in current_holds(ds)] == ["Q2"]
        assert [r["hold_code"] for r in current_holds(ds, active_only=False)] \
            == ["Q1", "Q2"]

    def test_filter_by_task_and_run(self, ds):
        """TC-WFH-022: 可按 task_id / run_id 过滤。"""
        run, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        assert len(current_holds(ds, task_id=task["id"])) == 1
        assert len(current_holds(ds, run_id=run["run_id"])) == 1
        assert current_holds(ds, task_id="no-such-task") == []
        assert current_holds(ds, run_id="no-such-run") == []

    def test_view_missing_raises(self, ds):
        """TC-WFH-023: 派生视图缺失时读取 fail-loud（不直查事件明细）。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        with ds.transaction():
            ds.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))

        with pytest.raises(TaskHoldError):
            current_holds(ds)

    def test_ensure_view_idempotent(self, ds):
        """TC-WFH-024: ensure 幂等（已存在返回 False，不覆盖）。"""
        assert hold_view_exists(ds)
        assert ensure_hold_view(ds) is False

    def test_rebuild_restores_drift(self, ds):
        """TC-WFH-025: 视图被篡改 → 巡检发现漂移 → rebuild 修复。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        with ds.transaction():
            ds.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))
            ds.execute("CREATE VIEW {0} AS SELECT 1 AS task_id".format(HOLD_VIEW))

        report = hold_findings(ds)
        assert "HOLD_VIEW_SQL_DRIFT" in report.codes()

        rebuilt = rebuild_hold_view(ds)
        assert rebuilt.ok and rebuilt.view_rebuilt and rebuilt.view_existed
        assert rebuilt.error == ""
        assert "HOLD_VIEW_SQL_DRIFT" not in hold_findings(ds).codes()
        assert current_holds(ds)[0]["active_flag"] == 1

    def test_rebuild_when_view_missing(self, ds):
        """TC-WFH-026: 视图缺失时 rebuild 直接建出（view_existed=False）。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        with ds.transaction():
            ds.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))

        rebuilt = rebuild_hold_view(ds)
        assert rebuilt.ok and rebuilt.view_rebuilt and not rebuilt.view_existed
        assert current_holds(ds)[0]["hold_code"] == "Q1"


# ─────────────────────────────────────────────────────────────────────────────
# ③ 巡检（同形态兄弟巡检域）
# ─────────────────────────────────────────────────────────────────────────────

class TestHoldFindings:
    def test_clean_state_ok(self, ds):
        """TC-WFH-040: 正常交替 → 巡检 ok，无 findings。"""
        _, task = _single_task(ds)
        hold_task(ds, task["id"], hold_code="Q1", occurred_at=AT)
        hold_task(ds, task["id"], hold_code="Q2", occurred_at=AT)
        release_task(ds, task["id"], hold_code="Q1", occurred_at=AT)

        report = hold_findings(ds)
        assert report.ok and report.findings == []
        assert report.hold_event_count == 3
        assert report.active_hold_count == 1

    def test_event_table_missing(self, tmp_path):
        """TC-WFH-041: 事件账不存在 → fail-loud 早返回。"""
        from meta.core.datasource import get_data_source

        source = get_data_source("sqlite", database=str(tmp_path / "empty.db"))
        report = hold_findings(source)
        assert not report.ok
        assert report.codes() == ["HOLD_EVENT_TABLE_MISSING"]

    def test_view_missing_flagged(self, ds):
        """TC-WFH-042: 视图缺失 → HOLD_VIEW_MISSING。"""
        with ds.transaction():
            ds.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))
        report = hold_findings(ds)
        assert "HOLD_VIEW_MISSING" in report.codes()

    def test_alternation_violation_flagged(self, ds):
        """TC-WFH-043: 绕过入口直写两条 hold → 差值=2 → HOLD_STATE_INCONSISTENT。"""
        _, task = _single_task(ds)
        _raw_event(ds, task["id"], "hold", json.dumps({"hold_code": "Q1"}))
        _raw_event(ds, task["id"], "hold", json.dumps({"hold_code": "Q1"}))

        report = hold_findings(ds)
        assert not report.ok
        assert "HOLD_STATE_INCONSISTENT" in report.codes()
        assert report.active_hold_count == 0     # 差值 2 不算激活

    def test_event_without_code_flagged(self, ds):
        """TC-WFH-044: hold 事件缺 hold_code → HOLD_EVENT_WITHOUT_CODE。"""
        _, task = _single_task(ds)
        _raw_event(ds, task["id"], "hold", None)

        report = hold_findings(ds)
        assert not report.ok
        assert "HOLD_EVENT_WITHOUT_CODE" in report.codes()

    def test_non_hold_events_not_counted(self, ds):
        """TC-WFH-045: created / status_changed 不计入 hold 事件数。"""
        _, task = _single_task(ds)
        report = hold_findings(ds)
        assert report.hold_event_count == 0
        assert report.ok


# ─────────────────────────────────────────────────────────────────────────────
# ④ CLI（meta.tools.task_hold_reconcile；触发式运维脚本）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_file(tmp_path):
    """落盘平台库（CLI 需要真实文件路径）。"""
    from meta.core.datasource import get_data_source

    path = str(tmp_path / "cli.db")
    source = get_data_source("sqlite", database=path)
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_hold_view(source)
    return path


class TestCli:
    def test_cli_json_clean(self, db_file, capsys):
        """TC-WFH-050: --json 机读输出（无 rebuild 时该字段为 null）。"""
        from meta.core.datasource import get_data_source

        ds = get_data_source("sqlite", database=db_file)
        _raw_event(ds, "t-1", "hold", json.dumps({"hold_code": "Q1"}))
        _raw_event(ds, "t-1", "release", json.dumps({"hold_code": "Q1"}))

        code = hold_reconcile_main(["--db", db_file, "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert payload["report"]["ok"] is True
        assert payload["report"]["hold_event_count"] == 2
        assert payload["report"]["active_hold_count"] == 0
        assert payload["rebuild"] is None

    def test_cli_strict_exit_code(self, db_file):
        """TC-WFH-051: --strict 仅在 error 级 findings 时退出码 1。"""
        from meta.core.datasource import get_data_source

        ds = get_data_source("sqlite", database=db_file)
        with ds.transaction():
            ds.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))

        assert hold_reconcile_main(["--db", db_file]) == 0            # 非 strict
        assert hold_reconcile_main(["--db", db_file, "--strict"]) == 1

    def test_cli_rebuild_restores_view(self, db_file, capsys):
        """TC-WFH-052: --rebuild 重建视图并复检（端到端）。"""
        from meta.core.datasource import get_data_source

        ds = get_data_source("sqlite", database=db_file)
        with ds.transaction():
            ds.execute("DROP VIEW IF EXISTS {0}".format(HOLD_VIEW))

        assert hold_reconcile_main(["--db", db_file, "--rebuild"]) == 0
        assert hold_view_exists(ds)
        assert "视图重建: OK" in capsys.readouterr().out

    def test_cli_missing_db_exit_2(self, tmp_path):
        """TC-WFH-053: --db 指向不存在文件 → exit 2（不静默新建空库）。"""
        assert hold_reconcile_main(
            ["--db", str(tmp_path / "nope.db")]) == 2