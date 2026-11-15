# -*- coding: utf-8 -*-
"""M4-1 任务改派（spec §8.2）— 任务域通用能力，审批只是第一消费者

覆盖:
  1. 归属双列改写（candidates/assignee）+ 状态不变
  2. 参与流水留痕（旧 pending→transferred，新 transferred_in/pending）
  3. 工作日志（entry_type='note'，action=reassign），不伪造 TASK_EVENT
  4. 准入 fail-closed：非执行人/候选/受托人 → 403；终态 → 409
  5. 审批附加：waiting_approval + 目标≠提交人 + 目标有 {bo}:approve
  6. 委托：有效受托人准入期内可改派（归属仍写目标任务列）
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json

import pytest

from meta.core.task_assignment import (
    AssignmentError, AssignmentPermissionError, TaskNotFoundError, reassign_task,
)

pytestmark = pytest.mark.unit


def _build(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_delegation import ensure_delegation_tables
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_participation import ensure_participation_tables
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "reassign.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_participation_tables(source)
        ensure_delegation_tables(source)
    return source


@pytest.fixture()
def ds(tmp_path):
    yield _build(tmp_path)


def _task(ds, *, task_id="T-1", type_="story", status="in_progress",
          assignee="u1", candidates=None, created_by="owner",
          app_id="wms", doc_ref_type=None):
    cols = ["id", "title", "type", "status", "priority", "app_id",
            "executor_type", "assign_policy", "executor_assignee",
            "executor_candidates", "created_by", "created_at", "updated_at",
            "doc_ref_type"]
    vals = [task_id, "测试任务", type_, status, "normal", app_id,
            "human", "claim", assignee,
            json.dumps(candidates or [], ensure_ascii=False),
            created_by, "2026-11-15T09:00:00", "2026-11-15T09:00:00",
            doc_ref_type]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _participations(ds, task_id):
    rows = ds.execute(
        "SELECT participant, role, outcome FROM task_participations "
        "WHERE task_id = ? ORDER BY id", (task_id,)).fetchall()
    return {r[0]: {"role": r[1], "outcome": r[2]} for r in rows}


def _task_row(ds, task_id):
    r = ds.execute(
        "SELECT executor_assignee, executor_candidates, status FROM tasks WHERE id = ?",
        (task_id,)).fetchall()[0]
    return {"assignee": r[0], "candidates": json.loads(r[1] or "[]"), "status": r[2]}


def _worklogs(ds, task_id):
    return ds.execute(
        "SELECT entry_type, actor, summary, detail FROM task_worklogs "
        "WHERE task_id = ? ORDER BY created_at DESC", (task_id,)).fetchall()


class TestReassignOwnership:
    def test_TC_REASSIGN_001_执行人改派改写双列与参与流水(self, ds):
        from meta.core.task_participation import seed_participants

        _task(ds, task_id="T-1", assignee="u1", candidates=["u1", "u2"])
        with ds.transaction():
            seed_participants(ds, "T-1", ["u1", "u2"], created_by="owner")

        out = reassign_task(ds, "T-1", to_user="u3", actor="u1", reason="休假")

        row = _task_row(ds, "T-1")
        assert row["assignee"] == "u3"
        assert row["candidates"] == ["u3"]          # 真源：候选池 = 新执行人
        assert row["status"] == "in_progress"        # 状态不由改派迁移
        assert out["from_assignee"] == "u1"
        assert out["to_user"] == "u3"

        parts = _participations(ds, "T-1")
        assert parts["u1"]["outcome"] == "transferred"
        assert parts["u2"]["outcome"] == "transferred"   # 其他旧待决行一并转出
        assert parts["u3"]["role"] == "transferred_in"
        assert parts["u3"]["outcome"] == "pending"

    def test_TC_REASSIGN_002_工作日志不伪造事件(self, ds):
        _task(ds, task_id="T-1", assignee="u1")

        reassign_task(ds, "T-1", to_user="u2", actor="u1", reason="排班调整")

        logs = _worklogs(ds, "T-1")
        assert logs and logs[0][0] == "note"
        assert logs[0][1] == "u1"
        detail = json.loads(logs[0][3])
        assert detail["action"] == "reassign" and detail["to_user"] == "u2"
        # 改派不是状态迁移：事件账保持 0 条
        count = ds.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = ?", ("T-1",)).fetchall()[0][0]
        assert count == 0

    def test_TC_REASSIGN_003_目标已是执行人拒绝(self, ds):
        _task(ds, task_id="T-1", assignee="u1")

        with pytest.raises(AssignmentError, match="已是当前执行人"):
            reassign_task(ds, "T-1", to_user="u1", actor="u1", reason="x")

    def test_TC_REASSIGN_004_原因必填(self, ds):
        _task(ds, task_id="T-1", assignee="u1")

        with pytest.raises(AssignmentError, match="原因必填"):
            reassign_task(ds, "T-1", to_user="u2", actor="u1", reason="  ")

    def test_TC_REASSIGN_005_任务不存在(self, ds):
        with pytest.raises(TaskNotFoundError):
            reassign_task(ds, "T-NOPE", to_user="u2", actor="u1", reason="x")


class TestReassignAdmission:
    def test_TC_REASSIGN_010_候选池成员可改派(self, ds):
        _task(ds, task_id="T-1", assignee="u1", candidates=["u1", "u2"],
              status="ready")

        out = reassign_task(ds, "T-1", to_user="u5", actor="u2", reason="转派")

        assert out["to_user"] == "u5"
        assert _task_row(ds, "T-1")["assignee"] == "u5"

    def test_TC_REASSIGN_011_无关者fail_closed(self, ds):
        _task(ds, task_id="T-1", assignee="u1")

        with pytest.raises(AssignmentPermissionError):
            reassign_task(ds, "T-1", to_user="u2", actor="u9", reason="x")

    def test_TC_REASSIGN_012_终态拒绝(self, ds):
        for status in ("done", "failed", "cancelled"):
            _task(ds, task_id=f"T-{status}", assignee="u1", status=status)
            with pytest.raises(AssignmentError, match="终态"):
                reassign_task(ds, f"T-{status}", to_user="u2", actor="u1",
                              reason="x")

    def test_TC_REASSIGN_013_admin可改派(self, ds):
        _task(ds, task_id="T-1", assignee="u1")

        reassign_task(ds, "T-1", to_user="u2", actor="root", reason="强制",
                      admin=True)

        assert _task_row(ds, "T-1")["assignee"] == "u2"


class TestReassignApprovalHook:
    def test_TC_REASSIGN_020_审批须waiting_approval(self, ds):
        _task(ds, task_id="T-A", type_="approval", status="ready",
              assignee="ap1", created_by="owner", doc_ref_type="purchase_order")

        with pytest.raises(AssignmentError, match="waiting_approval"):
            reassign_task(ds, "T-A", to_user="ap2", actor="ap1", reason="x",
                          target_permitted=True)

    def test_TC_REASSIGN_021_目标不得是提交人(self, ds):
        _task(ds, task_id="T-A", type_="approval", status="waiting_approval",
              assignee="ap1", created_by="submitter",
              doc_ref_type="purchase_order")

        with pytest.raises(AssignmentError, match="提交人"):
            reassign_task(ds, "T-A", to_user="submitter", actor="ap1",
                          reason="x", target_permitted=True)

    def test_TC_REASSIGN_022_目标无审批权限fail_closed(self, ds):
        _task(ds, task_id="T-A", type_="approval", status="waiting_approval",
              assignee="ap1", created_by="submitter",
              doc_ref_type="purchase_order")

        with pytest.raises(AssignmentPermissionError, match="审批权限"):
            reassign_task(ds, "T-A", to_user="ap2", actor="ap1",
                          reason="x", target_permitted=False)

    def test_TC_REASSIGN_023_审批改派成功(self, ds):
        _task(ds, task_id="T-A", type_="approval", status="waiting_approval",
              assignee="ap1", created_by="submitter",
              doc_ref_type="purchase_order")

        out = reassign_task(ds, "T-A", to_user="ap2", actor="ap1", reason="换人",
                            target_permitted=True)

        assert out["to_user"] == "ap2"
        assert _task_row(ds, "T-A")["assignee"] == "ap2"


class TestReassignViaDelegation:
    def test_TC_REASSIGN_030_有效受托人可改派(self, ds):
        from meta.core.task_delegation import create_delegation

        _task(ds, task_id="T-1", assignee="u1", app_id="wms")
        create_delegation(ds, delegator="u1", delegate="u9",
                          scope_type="app", scope_value="wms")

        out = reassign_task(ds, "T-1", to_user="u2", actor="u9", reason="委托人休假")

        assert out["to_user"] == "u2"

    def test_TC_REASSIGN_031_范围不匹配不授权(self, ds):
        from meta.core.task_delegation import create_delegation

        _task(ds, task_id="T-1", assignee="u1", app_id="wms")
        create_delegation(ds, delegator="u1", delegate="u9",
                          scope_type="app", scope_value="tms")

        with pytest.raises(AssignmentPermissionError):
            reassign_task(ds, "T-1", to_user="u2", actor="u9", reason="x")

    def test_TC_REASSIGN_032_过期委托不授权(self, ds):
        from meta.core.task_delegation import create_delegation

        _task(ds, task_id="T-1", assignee="u1", app_id="wms")
        create_delegation(ds, delegator="u1", delegate="u9", scope_type="any",
                          effective_from="2026-01-01T00:00:00",
                          effective_to="2026-02-01T00:00:00")

        with pytest.raises(AssignmentPermissionError):
            reassign_task(ds, "T-1", to_user="u2", actor="u9", reason="x")