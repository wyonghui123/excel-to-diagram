import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events / task_idempotency）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - 审批决策提交服务（B3 接线点①）
测试 meta.api.task_decision_api.submit_decision（§9.7 / §12.1 B3 / Q1）

覆盖目标：
  1. admin + approve → 200，任务 done，BO 收到 effect_key={task_id}:{attempt}
  2. 非 admin → fail-closed（409），任务不变
  3. 客户端禁传 submitter_id / four_eyes / reviewer_permission → 400，且未调 BO
  4. 四眼原则：审核人 == 提交人 → 409
  5. BO 无生效回执 → 502 retryable，任务不变
  6. reject 同样要生效 → 200，任务 failed
"""

import json
from datetime import datetime

from meta.api.task_decision_api import submit_decision

ADMIN = {"user_id": "u-admin", "username": "admin", "permissions": ["*"]}
PLAIN = {"user_id": "u-plain", "username": "plain", "permissions": []}


def _now():
    return datetime.now().isoformat(timespec="seconds")


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source
    from meta.core.task_event_schema import ensure_task_event_tables
    from meta.core.task_idempotency import ensure_idempotency_table
    from meta.core.task_schema import ensure_task_tables

    source = get_data_source("sqlite", database=str(tmp_path / "decision_api.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
    yield source


@pytest.fixture()
def registry():
    from meta.core.bo_action_registry import bo_action_registry

    saved = dict(bo_action_registry._actions)
    bo_action_registry.clear()
    yield bo_action_registry
    bo_action_registry._actions.clear()
    bo_action_registry._actions.update(saved)


def _approval_task(ds, *, task_id="T-A1", status="waiting_approval", attempt=1,
                   doc_ref="DOC-1", created_by="u-sub"):
    config = {"decision_actions": {"approve": "demo.approve", "reject": "demo.reject"}}
    cols = ["id", "title", "type", "status", "executor_type", "executor_config",
            "inputs", "attempt", "workflow_run_id", "doc_ref", "created_by",
            "priority", "created_at", "updated_at"]
    vals = [task_id, "审批任务", "approval", status, "system", json.dumps(config),
            json.dumps({"doc_ref": doc_ref}), attempt, "R-1", doc_ref, created_by,
            "P2", _now(), _now()]
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


def _register(registry, action_id, handler):
    registry.register(action_id, handler, description="B3 API 测试 action",
                      object_type="*", category="business",
                      input_schema={"type": "object", "properties": {}})


def _ok_handler(new_status="approved", calls=None):
    def _h(payload, context):
        if calls is not None:
            calls.append(context)
        return {"success": True, "data": {"new_status": new_status, "doc_ref": "DOC-1"}}

    return _h


def _status(ds, task_id):
    return ds.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]


class TestSubmitDecision:
    """TC-B3API-001~006 决策提交服务"""

    def test_TC_B3API_001_admin审批通过(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        _register(registry, "demo.reject", _ok_handler("rejected"))
        tid = _approval_task(ds)

        payload, code = submit_decision(
            ds, tid, user=ADMIN, body={"decision": "approve", "comment": "同意"})

        assert code == 200
        assert payload["success"] is True
        assert payload["data"]["task_status"] == "done"
        assert _status(ds, tid) == "done"
        assert calls[0]["effect_key"] == f"{tid}:1"   # §9.7 规范 2 键口径

    def test_TC_B3API_002_非admin被拒且任务不变(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        tid = _approval_task(ds)

        payload, code = submit_decision(
            ds, tid, user=PLAIN, body={"decision": "approve"})

        assert code == 409
        assert payload["success"] is False
        assert _status(ds, tid) == "waiting_approval"   # fail-closed
        assert calls == []                              # 守卫先于 BO，未调 BO

    def test_TC_B3API_003_禁传四眼与提交人字段(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler(calls=calls))
        tid = _approval_task(ds)

        payload, code = submit_decision(
            ds, tid, user=ADMIN,
            body={"decision": "approve", "submitter_id": "u-other"})

        assert code == 400
        assert _status(ds, tid) == "waiting_approval"
        assert calls == []

    def test_TC_B3API_004_四眼原则审核人不得为提交人(self, ds, registry):
        _register(registry, "demo.approve", _ok_handler())
        tid = _approval_task(ds, created_by="u-admin")   # 提交人 == 审核人

        payload, code = submit_decision(
            ds, tid, user=ADMIN, body={"decision": "approve"})

        assert code == 409
        assert _status(ds, tid) == "waiting_approval"

    def test_TC_B3API_005_无回执不迁移可重试(self, ds, registry):
        _register(registry, "demo.approve",
                  lambda p, c: {"success": True, "data": {}})   # 缺 new_status
        tid = _approval_task(ds)

        payload, code = submit_decision(
            ds, tid, user=ADMIN, body={"decision": "approve"})

        assert code == 502
        assert payload["retryable"] is True
        assert _status(ds, tid) == "waiting_approval"

    def test_TC_B3API_006_拒绝同样要生效(self, ds, registry):
        calls = []
        _register(registry, "demo.approve", _ok_handler())
        _register(registry, "demo.reject", _ok_handler("rejected", calls=calls))
        tid = _approval_task(ds)

        payload, code = submit_decision(
            ds, tid, user=ADMIN, body={"decision": "reject", "comment": "驳回"})

        assert code == 200
        assert payload["data"]["task_status"] == "failed"
        assert _status(ds, tid) == "failed"
        assert calls[0]["effect_key"] == f"{tid}:1"