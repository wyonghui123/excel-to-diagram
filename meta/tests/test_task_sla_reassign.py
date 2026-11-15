# -*- coding: utf-8 -*-
"""M4-4 SLA 开单 + 超时改派（spec §8.5）

覆盖:
  1. 开单派生：首步 sla_hours → {target_seconds, warn/alert, grace, on_breach} + due_at
  2. 开单落库：sla 单存在且目标与任务快照一致；无 sla_hours 不动
  3. 未越线不改派（告警不是触发）
  4. 越线（T2）改派一次 + worklog action=sla_reassign + 幂等（同轮重放不重复）
  5. 默认关闭：无 executor_config.sla_on_breach 不改派
  6. 兜底人缺失 / action≠reassign 不改派
  7. 非审批任务同样生效
  8. 终态任务不改派（错误收集，不中断整轮）
"""
import json
import os
from datetime import datetime, timedelta

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 15, 10, 0, 0)


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_delegation import ensure_delegation_tables
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_participation import ensure_participation_tables
    from meta.core.task_schema import ensure_task_tables
    from meta.core.task_sla import ensure_sla_tables

    source = get_data_source("sqlite", database=str(tmp_path / "sla_reassign.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
        ensure_participation_tables(source)
        ensure_delegation_tables(source)
        ensure_sla_tables(source)
    yield source


_COLS = ["id", "title", "type", "status", "priority", "app_id",
         "executor_type", "assign_policy", "executor_assignee",
         "executor_candidates", "executor_config", "inputs", "attempt",
         "workflow_run_id", "doc_ref", "doc_ref_type", "created_by",
         "created_at", "updated_at", "sla", "due_at"]


def _task_row(ds, task_id="T-1", *, type_="approval", status="waiting_approval",
              assignee="u1", candidates=None, sla=None, due_at=None,
              config=None):
    created = NOW - timedelta(hours=2)
    vals = [task_id, "SLA 测试任务", type_, status, "P2", "wms",
            "human", "direct", assignee,
            json.dumps(candidates or [assignee], ensure_ascii=False),
            json.dumps(config or {}, ensure_ascii=False),
            json.dumps({"doc_ref": "DOC-1"}, ensure_ascii=False), 1,
            "R-1", "DOC-1",
            "purchase_order" if type_ == "approval" else None,
            "u-sub", created.isoformat(timespec="seconds"),
            created.isoformat(timespec="seconds"),
            json.dumps(sla, ensure_ascii=False) if sla else None,
            due_at]
    ds.execute(
        "INSERT INTO tasks ({0}) VALUES ({1})".format(
            ", ".join(_COLS), ", ".join(["?"] * len(_COLS))), tuple(vals))
    return task_id


def _sla_cfg(seconds=3600, grace=0):
    return {"target_seconds": seconds, "warn_at_pct": 80, "alert_at_pct": 95,
            "grace_seconds": grace, "on_breach": None}


def _assignee(ds, task_id="T-1"):
    return ds.execute("SELECT executor_assignee FROM tasks WHERE id = ?",
                      (task_id,)).fetchall()[0][0]


def _tick(ds, now):
    from meta.core.task_tick import platform_tick
    return platform_tick(ds, now=now, dispatch=False, reclaim=False,
                         escalate=True, reconcile=False)


class TestSlaOpen:
    def test_TC_SLA_R_001_开单派生(self):
        from meta.services.approval_task_service import _resolve_sla

        cfg, due_at = _resolve_sla(
            {"steps": [{"step_no": 2, "sla_hours": 4},
                       {"step_no": 1, "sla_hours": 1.5}]}, NOW)
        assert cfg == {"target_seconds": 5400, "warn_at_pct": 80,
                       "alert_at_pct": 95, "grace_seconds": 0, "on_breach": None}
        assert due_at == (NOW + timedelta(seconds=5400)).isoformat(timespec="seconds")

        assert _resolve_sla({"steps": [{"step_no": 1}]}, NOW) == (None, None)
        assert _resolve_sla({"steps": []}, NOW) == (None, None)
        assert _resolve_sla({"steps": [{"step_no": 1, "sla_hours": 0}]}, NOW) == (None, None)

    def test_TC_SLA_R_002_开单落库(self, ds):
        from meta.core.task_sla import list_slas
        from meta.services.approval_task_service import _open_sla

        due = (NOW + timedelta(hours=1)).isoformat(timespec="seconds")
        _task_row(ds, sla=_sla_cfg(), due_at=due)
        _open_sla(ds, "T-1", NOW)

        rows = list_slas(ds, task_id="T-1", active_only=True)
        assert len(rows) == 1
        assert rows[0]["target_seconds"] == 3600
        assert rows[0]["due_at"] == due


class TestSlaReassign:
    def test_TC_SLA_R_003_未越线不改派(self, ds):
        due = (NOW + timedelta(hours=10)).isoformat(timespec="seconds")
        _task_row(ds, sla=_sla_cfg(3600 * 12), due_at=due,
                  config={"sla_on_breach": {"action": "reassign",
                                            "fallback_assignee": "u9"}})
        from meta.core.task_sla import open_sla_for_task
        open_sla_for_task(ds, "T-1", start_at=NOW - timedelta(hours=1))

        result = _tick(ds, NOW)
        assert result["sla_reassigns"] == []
        assert _assignee(ds) == "u1"

    def test_TC_SLA_R_004_越线改派一次且幂等(self, ds):
        from meta.core.task_sla import list_slas, open_sla_for_task

        due = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
        _task_row(ds, sla=_sla_cfg(3600), due_at=due,
                  config={"sla_on_breach": {"action": "reassign",
                                            "fallback_assignee": "u9",
                                            "reason": "审批超时兜底"}})
        open_sla_for_task(ds, "T-1", start_at=NOW - timedelta(hours=2))

        result = _tick(ds, NOW)
        assert result["counts"]["sla_reassigns"] == 1
        assert result["sla_reassigns"][0]["to_user"] == "u9"
        assert _assignee(ds) == "u9"
        sla_rows = list_slas(ds, task_id="T-1")
        assert sla_rows[0]["last_escalation_rung"] == 3

        result2 = _tick(ds, NOW)                       # 幂等：梯级已推进
        assert result2["sla_reassigns"] == []

        entries = ds.execute(
            "SELECT detail FROM task_worklogs WHERE task_id = ? AND summary = ?",
            ("T-1", "SLA 超时自动改派")).fetchall()
        assert entries and json.loads(entries[0][0])["action"] == "sla_reassign"

    def test_TC_SLA_R_005_默认关闭(self, ds):
        from meta.core.task_sla import open_sla_for_task

        due = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
        _task_row(ds, sla=_sla_cfg(3600), due_at=due)   # 无 sla_on_breach
        open_sla_for_task(ds, "T-1", start_at=NOW - timedelta(hours=2))

        result = _tick(ds, NOW)
        assert result["escalations"][0]["rung"] == 3   # 越线仍然产生告警事件
        assert result["sla_reassigns"] == []
        assert _assignee(ds) == "u1"

    def test_TC_SLA_R_006_兜底人缺失或动作不符不改派(self, ds):
        from meta.core.task_sla import open_sla_for_task

        due = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
        for cfg in ({"action": "reassign"},
                    {"action": "escalate_fallback", "fallback_assignee": "u9"}):
            ds.execute("DELETE FROM task_slas")
            ds.execute("DELETE FROM tasks")
            _task_row(ds, sla=_sla_cfg(3600), due_at=due,
                      config={"sla_on_breach": cfg})
            open_sla_for_task(ds, "T-1", start_at=NOW - timedelta(hours=2))
            result = _tick(ds, NOW)
            assert result["sla_reassigns"] == [], cfg
            assert _assignee(ds) == "u1"

    def test_TC_SLA_R_007_非审批任务同样生效(self, ds):
        from meta.core.task_sla import open_sla_for_task

        due = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
        _task_row(ds, type_="story", status="in_progress",
                  sla=_sla_cfg(3600), due_at=due,
                  config={"sla_on_breach": {"action": "reassign",
                                            "fallback_assignee": "u9"}})
        open_sla_for_task(ds, "T-1", start_at=NOW - timedelta(hours=2))

        result = _tick(ds, NOW)
        assert result["counts"]["sla_reassigns"] == 1
        assert _assignee(ds) == "u9"

    def test_TC_SLA_R_008_终态任务收集错误不中断(self, ds):
        from meta.core.task_sla import open_sla_for_task

        due = (NOW - timedelta(hours=1)).isoformat(timespec="seconds")
        _task_row(ds, status="done", sla=_sla_cfg(3600), due_at=due,
                  config={"sla_on_breach": {"action": "reassign",
                                            "fallback_assignee": "u9"}})
        open_sla_for_task(ds, "T-1", start_at=NOW - timedelta(hours=2))

        result = _tick(ds, NOW)
        assert result["sla_reassigns"] == []
        assert any(e["stage"] == "sla_reassign" for e in result["errors"])
        assert _assignee(ds) == "u1"