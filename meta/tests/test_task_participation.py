# -*- coding: utf-8 -*-
"""M4-2 参与归并与加签（spec §8.3）— 任务域通用能力，审批只是第一消费者

覆盖:
  1. 加签 = 新增 `role='added', outcome='pending'` 行 + candidates 双写（同事务）
  2. `require_all=true` → completion_mode='all' + worklog（action=completion_mode）
  3. 准入 fail-closed：无准入 403；终态 409
  4. `any` 模式：一票通过（BO 调用一次），其他参与人仍 pending
  5. `all` 模式：未齐 → `partially_approved` + remaining，无副作用；齐了才调 BO
  6. `all` 模式任一 reject → 立即失败，其余 pending 转 skipped
  7. 重复投票 / 非参与人 → 409
  8. 非审批任务 all 模式同逻辑但不调 BO（effect_applied=False，任务状态不变）
  9. 审批参与人缺 `{bo}:approve` → 403
 10. 参与进度视图 + API 可见性（无权 404）
 11. 委托代投票：写 decided_by/on_behalf_of；受托人是提交人 → 409（四眼）
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
from datetime import datetime

import pytest

from meta.services.task_participation import (
    ParticipationConflictError,
    ParticipationPermissionError,
    decide_with_participation,
    participate,
    participations_view,
)

pytestmark = pytest.mark.unit

NOW = "2026-11-15T09:00:00"


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_delegation import ensure_delegation_tables
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_participation import ensure_participation_tables
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "participation.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
        ensure_participation_tables(source)
        ensure_delegation_tables(source)
    yield source


@pytest.fixture()
def registry():
    from meta.core.bo_action_registry import bo_action_registry

    saved = dict(bo_action_registry._actions)
    bo_action_registry.clear()
    yield bo_action_registry
    bo_action_registry._actions.clear()
    bo_action_registry._actions.update(saved)


def _register(registry, action_id, handler):
    registry.register(action_id, handler, description="M4-2 测试 action",
                      object_type="*", category="business",
                      input_schema={"type": "object", "properties": {}})


def _ok_handler(new_status="approved", calls=None):
    def _h(payload, context):
        if calls is not None:
            calls.append(context)
        return {"success": True,
                "data": {"new_status": new_status, "doc_ref": "DOC-1"}}

    return _h


def _task(ds, *, task_id="T-1", type_="approval", status="waiting_approval",
          mode="any", participants=None, assignee=None, created_by="u-sub",
          with_actions=True, app_id="wms", extra_config=None):
    config = {"completion_mode": mode}
    if extra_config:
        config.update(extra_config)
    if with_actions:
        config["decision_actions"] = {
            "approve": "demo.approve", "reject": "demo.reject"}
    candidates = list(participants or [])
    cols = ["id", "title", "type", "status", "priority", "app_id",
            "executor_type", "assign_policy", "executor_assignee",
            "executor_candidates", "executor_config", "inputs", "attempt",
            "workflow_run_id", "doc_ref", "doc_ref_type", "created_by",
            "created_at", "updated_at"]
    vals = [task_id, "测试任务", type_, status, "P2", app_id, "human", "claim",
            assignee, json.dumps(candidates, ensure_ascii=False),
            json.dumps(config, ensure_ascii=False),
            json.dumps({"doc_ref": "DOC-1"}, ensure_ascii=False), 1, "R-1",
            "DOC-1", "purchase_order" if type_ == "approval" else None,
            created_by, NOW, NOW]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    if participants:
        from meta.core.task_participation import seed_participants
        with ds.transaction():
            seed_participants(ds, task_id, participants, created_by=created_by)
    return task_id


def _task_row(ds, task_id="T-1"):
    row = ds.execute(
        "SELECT status, executor_candidates, executor_config FROM tasks WHERE id = ?",
        (task_id,)).fetchall()[0]
    return {"status": row[0],
            "candidates": json.loads(row[1] or "[]"),
            "config": json.loads(row[2] or "{}")}


def _parts(ds, task_id="T-1"):
    from meta.core.task_participation import list_participations
    return {r["participant"]: r for r in list_participations(ds, task_id)}


def _worklogs(ds, task_id="T-1"):
    return ds.execute(
        "SELECT entry_type, actor, summary, detail FROM task_worklogs "
        "WHERE task_id = ? ORDER BY created_at DESC", (task_id,)).fetchall()


class TestParticipate:
    """TC-PART-001~003 加签"""

    def test_TC_PART_001_加签写参与行并与候选池双写(self, ds):
        _task(ds, task_id="T-1", participants=["u1", "u2"])

        out = participate(ds, "T-1", actor="u1", participant="u3",
                          comment="补设计评审", now=NOW)

        assert out["completion_mode"] == "any"
        assert out["counts"]["pending"] == 3
        parts = _parts(ds)
        assert parts["u3"]["role"] == "added"
        assert parts["u3"]["outcome"] == "pending"
        assert parts["u3"]["comment"] == "补设计评审"
        row = _task_row(ds)
        assert row["candidates"] == ["u1", "u2", "u3"]     # R8 双写
        assert row["status"] == "waiting_approval"         # 状态不由加签迁移

    def test_TC_PART_002_require_all转会签并留痕(self, ds):
        _task(ds, task_id="T-1", participants=["u1"])

        out = participate(ds, "T-1", actor="u1", require_all=True, now=NOW)

        assert out["completion_mode"] == "all"
        assert _task_row(ds)["config"]["completion_mode"] == "all"
        logs = [r for r in _worklogs(ds) if r[0] == "note"]
        detail = json.loads(logs[0][3])
        assert detail["action"] == "completion_mode"
        assert detail["from"] == "any" and detail["to"] == "all"

    def test_TC_PART_003_无准入与终态(self, ds):
        _task(ds, task_id="T-1", participants=["u1"])
        with pytest.raises(ParticipationPermissionError):
            participate(ds, "T-1", actor="u9")

        _task(ds, task_id="T-2", status="done", participants=["u1"])
        with pytest.raises(ParticipationConflictError):
            participate(ds, "T-2", actor="u1")

    def test_TC_PART_013_加签人收件箱可见(self, ds):
        from meta.core.task_inbox import inbox_query

        _task(ds, task_id="T-1", participants=["u1"])
        participate(ds, "T-1", actor="u1", participant="u3", now=NOW)

        result = inbox_query(ds, actor="u3")
        assert [e["task_id"] for e in result["entries"]] == ["T-1"]


class TestMergeDecision:
    """TC-PART-004~009 决策归并"""

    def test_TC_PART_004_any模式一票通过(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, task_id="T-1", mode="any", participants=["u1", "u2"])

        out = decide_with_participation(
            ds, "T-1", decision="approve", actor="u1",
            reviewer_permission=True, now=NOW)

        assert out["status"] == "completed"
        assert out["task_status"] == "done"
        assert len(calls) == 1
        parts = _parts(ds)
        assert parts["u1"]["outcome"] == "accepted"
        assert parts["u2"]["outcome"] == "pending"

    def test_TC_PART_005_all模式未齐无副作用(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, task_id="T-1", mode="all", participants=["u1", "u2", "u3"])

        first = decide_with_participation(
            ds, "T-1", decision="approve", actor="u1",
            reviewer_permission=True, now=NOW)
        assert first["status"] == "partially_approved"
        assert first["remaining"] == ["u2", "u3"]
        assert calls == []                                  # 不调 BO
        assert _task_row(ds)["status"] == "waiting_approval"
        assert [v["participant"] for v in first["votes"]] == ["u1"]

        second = decide_with_participation(
            ds, "T-1", decision="approve", actor="u2",
            reviewer_permission=True, now=NOW)
        assert second["remaining"] == ["u3"] and calls == []

        third = decide_with_participation(
            ds, "T-1", decision="approve", actor="u3",
            reviewer_permission=True, now=NOW)
        assert third["status"] == "completed"
        assert third["task_status"] == "done"
        assert len(calls) == 1
        assert third["remaining"] == []

    def test_TC_PART_006_all模式任一驳回即失败(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        _register(registry, "demo.reject", _ok_handler("rejected", calls=calls))
        _task(ds, task_id="T-1", mode="all", participants=["u1", "u2", "u3"])

        out = decide_with_participation(
            ds, "T-1", decision="reject", actor="u2",
            reviewer_permission=True, now=NOW)

        assert out["status"] == "completed"
        assert out["task_status"] == "failed"
        assert len(calls) == 1
        parts = _parts(ds)
        assert parts["u2"]["outcome"] == "rejected"
        assert parts["u1"]["outcome"] == "skipped"
        assert parts["u3"]["outcome"] == "skipped"

    def test_TC_PART_007_重复投票与非参与人(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, task_id="T-1", mode="all", participants=["u1", "u2"])

        decide_with_participation(ds, "T-1", decision="approve", actor="u1",
                                  reviewer_permission=True, now=NOW)
        with pytest.raises(ParticipationConflictError):
            decide_with_participation(ds, "T-1", decision="approve", actor="u1",
                                      reviewer_permission=True, now=NOW)
        with pytest.raises(ParticipationConflictError):
            decide_with_participation(ds, "T-1", decision="approve", actor="u9",
                                      reviewer_permission=True, now=NOW)

    def test_TC_PART_008_非审批任务all模式不调BO(self, ds):
        _task(ds, task_id="S-1", type_="story", status="in_progress",
              mode="all", participants=["u1", "u2"], with_actions=False)

        first = decide_with_participation(
            ds, "S-1", decision="approve", actor="u1", now=NOW)
        assert first["status"] == "partially_approved"
        assert first["remaining"] == ["u2"]

        second = decide_with_participation(
            ds, "S-1", decision="approve", actor="u2", now=NOW)
        assert second["status"] == "completed"
        assert second["effect_applied"] is False
        assert _task_row(ds, "S-1")["status"] == "in_progress"   # 状态机不动

    def test_TC_PART_009_审批参与人缺权限403(self, ds):
        _task(ds, task_id="T-1", participants=["u1"])
        with pytest.raises(ParticipationPermissionError):
            decide_with_participation(ds, "T-1", decision="approve", actor="u1",
                                      reviewer_permission=False, now=NOW)


class TestParticipationView:
    """TC-PART-010 进度视图与 API 可见性"""

    def test_TC_PART_010_视图与无权404(self, ds):
        _task(ds, task_id="T-1", participants=["u1", "u2"])
        participate(ds, "T-1", actor="u1", participant="u3", now=NOW)

        view = participations_view(ds, "T-1")
        assert view["completion_mode"] == "any"
        assert view["counts"]["pending"] == 3
        assert view["remaining"] == ["u1", "u2", "u3"]

        from meta.api.task_participation_api import task_participations_service
        payload, code = task_participations_service(
            "T-1", user={"user_id": "u1", "permissions": []}, data_source=ds)
        assert code == 200 and payload["data"]["counts"]["pending"] == 3

        payload, code = task_participations_service(
            "T-1", user={"user_id": "u9", "permissions": []}, data_source=ds)
        assert code == 404


class TestDelegatedVote:
    """TC-PART-011 委托代投票（M4-3 预留接线）"""

    def test_TC_PART_011_受托人代投票留痕(self, ds, registry):
        from meta.core.task_delegation import create_delegation

        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, task_id="T-1", mode="all", participants=["u1", "u2"])
        with ds.transaction():
            create_delegation(ds, delegator="u1", delegate="u9",
                              scope_type="any", now=NOW)

        out = decide_with_participation(
            ds, "T-1", decision="approve", actor="u9",
            reviewer_permission=True, now="2026-11-15T10:00:00")

        assert out["status"] == "partially_approved"
        assert out["remaining"] == ["u2"]
        row = _parts(ds)["u1"]
        assert row["outcome"] == "accepted"
        assert row["decided_by"] == "u9"
        assert row["on_behalf_of"] == "u1"

    def test_TC_PART_012_受托人是提交人409四眼(self, ds):
        from meta.core.task_delegation import create_delegation

        _task(ds, task_id="T-2", participants=["u1"], created_by="u9")
        with ds.transaction():
            create_delegation(ds, delegator="u1", delegate="u9",
                              scope_type="any", now=NOW)

        with pytest.raises(ParticipationConflictError):
            decide_with_participation(
                ds, "T-2", decision="approve", actor="u9",
                reviewer_permission=True, now="2026-11-15T10:00:00")


class TestQuorum:
    """TC-PART-014 quorum：N 中 M 通过（spec §9.4）"""

    def test_TC_PART_014_quorum达标即结算(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, task_id="T-1", mode="all", participants=["u1", "u2", "u3"],
              extra_config={"quorum_required": 2})

        first = decide_with_participation(
            ds, "T-1", decision="approve", actor="u1",
            reviewer_permission=True, now=NOW)
        assert first["status"] == "partially_approved"
        assert first["remaining"] == ["u2", "u3"]
        assert first["quorum_required"] == 2
        assert calls == []                                   # 未达下限不调 BO

        second = decide_with_participation(
            ds, "T-1", decision="approve", actor="u2",
            reviewer_permission=True, now=NOW)
        assert second["status"] == "completed"
        assert len(calls) == 1
        parts = _parts(ds)
        assert parts["u1"]["outcome"] == "accepted"
        assert parts["u2"]["outcome"] == "accepted"
        assert parts["u3"]["outcome"] == "skipped"           # 达标后未投票者作废


class TestNotifyReadOnly:
    """TC-PART-015~016 知会人只读（spec §9.4 / M5-4）"""

    def _seed_notify(self, ds):
        from meta.core.task_participation import seed_participants
        _task(ds, task_id="T-1", participants=["u1"])
        with ds.transaction():
            seed_participants(ds, "T-1", ["u2"], role="notify", created_by="u-sub")

    def test_TC_PART_015_知会人不能加签(self, ds):
        self._seed_notify(ds)
        with pytest.raises(ParticipationPermissionError, match="只读"):
            participate(ds, "T-1", actor="u2")

    def test_TC_PART_016_知会人不能投票(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        self._seed_notify(ds)
        with pytest.raises(ParticipationConflictError, match="只读"):
            decide_with_participation(
                ds, "T-1", decision="approve", actor="u2",
                reviewer_permission=True, now=NOW)