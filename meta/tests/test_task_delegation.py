# -*- coding: utf-8 -*-
"""M4-3 委托（spec §8.4）— 准入期身份展开，不改归属

覆盖:
  1. 委托 CRUD：创建 / 列表 / active / 调整 / 撤销（撤销 = status='revoked'）
  2. 配置校验：自委托 / 缺 delegate / 范围缺值 / 非法范围 / 区间倒置 / 区间重叠 → 400
  3. 权限：非 admin 不能代配、不能改他人配置（403）；admin 可代配；不存在 404；未登录 401
  4. 有效期命中 → 可代投票且记 decided_by / on_behalf_of
  5. 有效期外 / 已撤销 / 范围不符 → 409（非参与人）
  6. 委托给任务提交人（created_by）→ 409（四眼）
  7. 委托人自己仍可投（不受委托影响）
  8. 收件箱可见性：受托人在「todo」分区看到任务
  9. scope_type='type' 对非审批任务生效
"""
import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json

import pytest

from meta.services.task_participation import (
    ParticipationConflictError,
    decide_with_participation,
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

    source = get_data_source("sqlite", database=str(tmp_path / "delegation.db"))
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
    registry.register(action_id, handler, description="M4-3 测试 action",
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
          mode="any", participants=None, created_by="u-sub", app_id="wms",
          with_actions=True):
    config = {"completion_mode": mode}
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
            None, json.dumps(candidates, ensure_ascii=False),
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


def _parts(ds, task_id="T-1"):
    from meta.core.task_participation import list_participations
    return {r["participant"]: r for r in list_participations(ds, task_id)}


def _admin():
    return {"user_id": "admin", "permissions": ["*"]}


def _user(uid):
    return {"user_id": uid, "permissions": []}


class TestDelegationCrud:
    """TC-DELEG-001~003 CRUD 与权限"""

    def test_TC_DELEG_001_生命周期(self, ds):
        from meta.api.task_delegation_api import (
            active_delegations_service, create_delegation_service,
            list_delegations_service, revoke_delegation_service,
            update_delegation_service,
        )

        payload, code = create_delegation_service(
            user=_user("u1"),
            body={"delegate": "u9", "scope_type": "any", "reason": "出差"},
            data_source=ds)
        assert code == 200
        delegation_id = payload["data"]["id"]
        assert payload["data"]["delegator"] == "u1"
        assert payload["data"]["status"] == "active"

        payload, code = list_delegations_service(user=_user("u1"), data_source=ds)
        assert code == 200 and payload["data"]["total"] == 1

        payload, code = active_delegations_service(user=_user("u9"), data_source=ds)
        assert code == 200 and [r["delegator"] for r in payload["data"]["items"]] == ["u1"]

        payload, code = update_delegation_service(
            delegation_id, user=_user("u1"),
            body={"effective_to": "2026-12-31T00:00:00", "reason": "改期"},
            data_source=ds)
        assert code == 200 and payload["data"]["effective_to"].startswith("2026-12-31")

        payload, code = revoke_delegation_service(
            delegation_id, user=_user("u1"), data_source=ds)
        assert code == 200 and payload["data"]["status"] == "revoked"

        payload, _ = active_delegations_service(user=_user("u9"), data_source=ds)
        assert payload["data"]["items"] == []                     # 撤销即失效
        payload, _ = list_delegations_service(
            user=_user("u1"), include_inactive=True, data_source=ds)
        assert payload["data"]["total"] == 1                      # 审计保留

    def test_TC_DELEG_002_配置校验400(self, ds):
        from meta.api.task_delegation_api import create_delegation_service

        cases = [
            {"delegate": "u1"},                                   # 自委托
            {},                                                   # 缺 delegate
            {"delegate": "u9", "scope_type": "app"},              # 范围缺值
            {"delegate": "u9", "scope_type": "weird", "scope_value": "x"},
            {"delegate": "u9", "effective_from": "2026-11-16T00:00:00",
             "effective_to": "2026-11-15T00:00:00"},              # 区间倒置
        ]
        for body in cases:
            _, code = create_delegation_service(
                user=_user("u1"), body=body, data_source=ds)
            assert code == 400, body

        create_delegation_service(
            user=_user("u1"),
            body={"delegate": "u9", "effective_from": "2026-11-15T00:00:00",
                  "effective_to": "2026-11-20T00:00:00"},
            data_source=ds)
        _, code = create_delegation_service(                   # 区间重叠
            user=_user("u1"),
            body={"delegate": "u9", "effective_from": "2026-11-18T00:00:00",
                  "effective_to": "2026-11-25T00:00:00"},
            data_source=ds)
        assert code == 400

    def test_TC_DELEG_003_权限边界(self, ds):
        from meta.api.task_delegation_api import (
            create_delegation_service, list_delegations_service,
            revoke_delegation_service, update_delegation_service,
        )

        _, code = create_delegation_service(
            user=_user("u2"), body={"delegator": "u1", "delegate": "u9"},
            data_source=ds)
        assert code == 403                                     # 非 admin 不能代配
        _, code = create_delegation_service(
            user=_admin(), body={"delegator": "u1", "delegate": "u9"},
            data_source=ds)
        assert code == 200                                     # admin 可代配
        row = list_delegations_service(user=_user("u1"), data_source=ds)[0]["data"]["items"][0]
        assert row["created_by"] == "admin"

        payload, _ = list_delegations_service(user=_user("u2"), data_source=ds)
        assert payload["data"]["items"] == []                   # 非 admin 只看自己

        _, code = update_delegation_service(
            row["id"], user=_user("u2"), body={"reason": "x"}, data_source=ds)
        assert code == 403
        _, code = revoke_delegation_service(
            row["id"], user=_user("u2"), data_source=ds)
        assert code == 403
        _, code = revoke_delegation_service(99999, user=_admin(), data_source=ds)
        assert code == 404

        _, code = create_delegation_service(
            user=None, body={"delegate": "u9"}, data_source=ds)
        assert code == 401


class TestDelegatedDecision:
    """TC-DELEG-004~009 决策准入展开"""

    def _delegate(self, ds, **kwargs):
        from meta.core.task_delegation import create_delegation
        with ds.transaction():
            return create_delegation(ds, delegator="u1", delegate="u9", **kwargs)

    def test_TC_DELEG_004_有效期命中可代投且留痕(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, participants=["u1", "u2"], mode="all")
        self._delegate(ds, scope_type="any",
                       effective_from="2026-11-15T09:00:00",
                       effective_to="2026-11-15T18:00:00")

        out = decide_with_participation(
            ds, "T-1", decision="approve", actor="u9",
            reviewer_permission=True, now="2026-11-15T10:00:00")

        assert out["status"] == "partially_approved"
        row = _parts(ds)["u1"]
        assert row["outcome"] == "accepted"
        assert row["decided_by"] == "u9"
        assert row["on_behalf_of"] == "u1"

    def test_TC_DELEG_005_有效期外与撤销后409(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, participants=["u1", "u2"], mode="all")
        row = self._delegate(ds, scope_type="any",
                             effective_from="2026-11-15T09:00:00",
                             effective_to="2026-11-15T10:00:00")

        with pytest.raises(ParticipationConflictError):       # 区间外
            decide_with_participation(
                ds, "T-1", decision="approve", actor="u9",
                reviewer_permission=True, now="2026-11-15T11:00:00")

        from meta.core.task_delegation import revoke_delegation
        with ds.transaction():
            revoke_delegation(ds, row["id"], now="2026-11-15T09:30:00")
        with pytest.raises(ParticipationConflictError):       # 已撤销
            decide_with_participation(
                ds, "T-1", decision="approve", actor="u9",
                reviewer_permission=True, now="2026-11-15T09:45:00")

    def test_TC_DELEG_006_范围不符409(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, type_="story", status="in_progress", mode="all",
              participants=["u1", "u2"], with_actions=False)
        self._delegate(ds, scope_type="type", scope_value="approval")

        with pytest.raises(ParticipationConflictError):
            decide_with_participation(
                ds, "T-1", decision="approve", actor="u9", now=NOW)

        # 范围命中（type=story）⇒ 非审批任务同样可代处理
        with ds.transaction():
            from meta.core.task_delegation import update_delegation
            for item in __import__("meta.core.task_delegation", fromlist=["list_delegations"]).list_delegations(ds, delegator="u1"):
                update_delegation(ds, item["id"], status="revoked")
        from meta.core.task_delegation import create_delegation
        with ds.transaction():
            create_delegation(ds, delegator="u1", delegate="u9",
                              scope_type="type", scope_value="story", now=NOW)

        out = decide_with_participation(
            ds, "T-1", decision="approve", actor="u9", now=NOW)
        assert out["status"] == "partially_approved"
        assert out["remaining"] == ["u2"]
        assert _parts(ds)["u1"]["on_behalf_of"] == "u1"

    def test_TC_DELEG_007_受托人是提交人409四眼(self, ds):
        _task(ds, participants=["u1"], created_by="u9")
        self._delegate(ds, scope_type="any")

        with pytest.raises(ParticipationConflictError):
            decide_with_participation(
                ds, "T-1", decision="approve", actor="u9",
                reviewer_permission=True, now=NOW)

    def test_TC_DELEG_008_委托人自己仍可投(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected"))
        _task(ds, participants=["u1", "u2"], mode="all")
        self._delegate(ds, scope_type="any")

        out = decide_with_participation(
            ds, "T-1", decision="approve", actor="u1",
            reviewer_permission=True, now=NOW)

        assert out["status"] == "partially_approved"
        row = _parts(ds)["u1"]
        assert row["decided_by"] == "u1"
        assert row["on_behalf_of"] is None

    def test_TC_DELEG_009_受托人收件箱可见(self, ds):
        from meta.core.task_inbox import inbox_query

        _task(ds, type_="story", status="in_progress",
              participants=["u1", "u2"], with_actions=False)
        self._delegate(ds, scope_type="any")

        result = inbox_query(ds, actor="u9")
        assert [e["task_id"] for e in result["entries"]] == ["T-1"]
        assert "todo" in result["entries"][0]["buckets"]