import pytest

pytestmark = pytest.mark.unit

# 平台内部表（tasks / task_events 等）暂无 Factory；按仓库既有惯例走 raw SQL escape hatch。
import os
os.environ.setdefault('ALLOW_RAW_SQL', '1')

"""
后端测试套件 - P1 任务读路径（活动流 / 单任务可见性 / 监控列表）

覆盖目标：
  1. list_task_events：按 occurred_at 升序、limit 生效、payload/line_refs JSON 还原、空 task_id 拒绝
  2. task_detail：actor 可见（assignee / creator / candidate）→ dict；不可见 / 不存在 → None（fail-closed）
  3. list_tasks：分页 + 过滤（status / type / app_id / executor_type / doc_ref_*）+ total 口径
     + actor 行级可见性收敛（§9.13.4.1 单据侧只读投影）
"""

import json
from datetime import datetime

from meta.core.task_event_schema import (
    ensure_task_event_tables, list_task_events, record_task_event, record_transition,
)
from meta.core.task_idempotency import ensure_idempotency_table
from meta.core.task_inbox import task_detail
from meta.core.task_query import list_tasks
from meta.core.task_schema import ensure_task_tables


@pytest.fixture()
def ds(tmp_path):
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "p1read.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
        ensure_idempotency_table(source)
    yield source


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _task(ds, *, task_id="T-1", status="ready", type_="story",
          executor_type="human", assignee="", candidates=None,
          assign_policy="direct", app_id="app-a", created_by="u-owner",
          doc_ref_type=None, doc_ref=None, doc_ref_id=None, attempt=None,
          outputs=None):
    cols = ["id", "title", "type", "status", "priority", "app_id",
            "executor_type", "executor_assignee", "executor_candidates",
            "assign_policy", "created_by", "created_at", "updated_at"]
    vals = [task_id, "测试任务", type_, status, "P2", app_id,
            executor_type, assignee, json.dumps(candidates or []),
            assign_policy, created_by, _now(), _now()]
    if doc_ref_type is not None:
        cols.append("doc_ref_type")
        vals.append(doc_ref_type)
    if doc_ref is not None:
        cols.append("doc_ref")
        vals.append(doc_ref)
    if doc_ref_id is not None:
        cols.append("doc_ref_id")
        vals.append(doc_ref_id)
    if attempt is not None:
        cols.append("attempt")
        vals.append(attempt)
    if outputs is not None:
        cols.append("outputs")
        vals.append(json.dumps(outputs))
    ds.execute(
        f"INSERT INTO tasks ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})",
        tuple(vals),
    )
    return task_id


# ─────────────────────────────────────────────────────────────────────────────
# 1. 事件账读取
# ─────────────────────────────────────────────────────────────────────────────

class TestListTaskEvents:
    """TC-P1-001~004 活动流读取"""

    def test_TC_P1_001_按业务时间升序(self, ds):
        _task(ds, task_id="T-1", status="in_progress")
        with ds.transaction():
            record_transition(ds, task_id="T-1", from_status="ready", to_status="claimed",
                              actor="u-a", actor_kind="human", occurred_at="2026-10-04T09:00:00")
            record_transition(ds, task_id="T-1", from_status="claimed", to_status="in_progress",
                              actor="u-a", actor_kind="human", occurred_at="2026-10-04T10:00:00")

        events = list_task_events(ds, "T-1")

        assert [e["to_status"] for e in events] == ["claimed", "in_progress"]
        assert events[0]["occurred_at"] < events[1]["occurred_at"]

    def test_TC_P1_002_limit取最早段(self, ds):
        _task(ds, task_id="T-2", status="ready")
        with ds.transaction():
            for i in range(5):
                record_task_event(ds, task_id="T-2", event_type="created",
                                  to_status="pending", actor="u-a", actor_kind="human",
                                  occurred_at=f"2026-10-04T0{i}:00:00")
        events = list_task_events(ds, "T-2", limit=2)
        assert [e["occurred_at"] for e in events] == [
            "2026-10-04T00:00:00", "2026-10-04T01:00:00"]

    def test_TC_P1_003_payload与line_refs还原为对象(self, ds):
        _task(ds, task_id="T-3", status="claimed")
        with ds.transaction():
            record_transition(ds, task_id="T-3", from_status="ready", to_status="claimed",
                              actor="u-a", actor_kind="human",
                              payload={"edge": "approve"}, line_refs=[{"line": 3}])
        ev = list_task_events(ds, "T-3")[0]
        assert ev["payload"] == {"edge": "approve"}
        assert ev["line_refs"] == [{"line": 3}]

    def test_TC_P1_004_空task_id拒绝(self, ds):
        with pytest.raises(ValueError):
            list_task_events(ds, "")


# ─────────────────────────────────────────────────────────────────────────────
# 2. 单任务可见性
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskDetail:
    """TC-P1-010~013 fail-closed 可见性"""

    def test_TC_P1_010_认领人可见(self, ds):
        _task(ds, task_id="T-1", assignee="u-a")
        assert task_detail(ds, "T-1", actor="u-a")["id"] == "T-1"

    def test_TC_P1_011_创建人可见(self, ds):
        _task(ds, task_id="T-1", created_by="u-owner", assignee="u-a")
        assert task_detail(ds, "T-1", actor="u-owner")["id"] == "T-1"

    def test_TC_P1_012_候选可见(self, ds):
        _task(ds, task_id="T-1", assignee="", candidates=["u-c"], assign_policy="claim")
        assert task_detail(ds, "T-1", actor="u-c")["id"] == "T-1"

    def test_TC_P1_013_无关人不可见且空actor不可见(self, ds):
        _task(ds, task_id="T-1", assignee="u-a")
        assert task_detail(ds, "T-1", actor="u-x") is None
        assert task_detail(ds, "T-1", actor=None) is None
        assert task_detail(ds, "T-nope", actor="u-a") is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. 监控列表
# ─────────────────────────────────────────────────────────────────────────────

class TestListTasks:
    """TC-P1-020~023 分页 + 过滤"""

    def test_TC_P1_020_分页与total(self, ds):
        for i in range(3):
            _task(ds, task_id=f"T-{i}")
        out = list_tasks(ds, page=1, page_size=2)
        assert out["total"] == 3
        assert len(out["items"]) == 2
        assert out["page"] == 1 and out["page_size"] == 2

    def test_TC_P1_021_按status过滤(self, ds):
        _task(ds, task_id="T-ok", status="ready")
        _task(ds, task_id="T-bad", status="failed")
        out = list_tasks(ds, status="failed")
        assert out["total"] == 1
        assert out["items"][0]["id"] == "T-bad"

    def test_TC_P1_022_按executor_type与app_id过滤(self, ds):
        _task(ds, task_id="T-h", executor_type="human", app_id="app-a")
        _task(ds, task_id="T-w", executor_type="webhook", app_id="app-b")
        out = list_tasks(ds, executor_type="webhook", app_id="app-b")
        assert [i["id"] for i in out["items"]] == ["T-w"]

    def test_TC_P1_023_非法status拒绝(self, ds):
        with pytest.raises(ValueError):
            list_tasks(ds, status="not-a-status")

    def test_TC_P1_024_按单据引用过滤(self, ds):
        _task(ds, task_id="T-hit", type_="approval", doc_ref_type="purchase_order",
              doc_ref_id="7")
        _task(ds, task_id="T-other", type_="approval", doc_ref_type="purchase_order",
              doc_ref_id="8")
        _task(ds, task_id="T-other-bo", type_="approval", doc_ref_type="transfer_order",
              doc_ref_id="7")

        out = list_tasks(ds, type="approval", doc_ref_type="purchase_order",
                         doc_ref_id="7")

        assert out["total"] == 1
        assert out["items"][0]["id"] == "T-hit"
        assert out["items"][0]["doc_ref_type"] == "purchase_order"
        assert out["items"][0]["doc_ref_id"] == "7"

    def test_TC_P1_025_历史任务无单据引用不被命中(self, ds):
        # M1 回填不到的历史任务两列为空 ⇒ 单据维度查询不命中（前端按空态/兜底处理）
        _task(ds, task_id="T-legacy", type_="approval", doc_ref="7")

        out = list_tasks(ds, type="approval", doc_ref_type="purchase_order",
                         doc_ref_id="7")

        assert out["total"] == 0

    def test_TC_P1_026_actor按行级可见性收敛(self, ds):
        _task(ds, task_id="T-assignee", type_="approval", assignee="u-a",
              doc_ref_type="purchase_order", doc_ref_id="7")
        _task(ds, task_id="T-creator", type_="approval", created_by="u-a",
              assignee="u-b", doc_ref_type="purchase_order", doc_ref_id="7")
        _task(ds, task_id="T-candidate", type_="approval", assignee="",
              candidates=["u-a"], assign_policy="claim",
              doc_ref_type="purchase_order", doc_ref_id="7")

        mine = list_tasks(ds, type="approval", doc_ref_type="purchase_order",
                          doc_ref_id="7", actor="u-a")
        assert {i["id"] for i in mine["items"]} == {
            "T-assignee", "T-creator", "T-candidate"}
        assert mine["total"] == 3

        # 无关用户：空（fail-closed），且 total 取过滤后条数
        other = list_tasks(ds, type="approval", doc_ref_type="purchase_order",
                           doc_ref_id="7", actor="u-x")
        assert other["items"] == [] and other["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# REST 服务函数（不经 Flask 全栈）
# ─────────────────────────────────────────────────────────────────────────────

def _admin():
    return {"user_id": "u-admin", "permissions": ["*"]}


def test_TC_P1_030_事件流可见返回200(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", assignee="u-a")
    with ds.transaction():
        record_transition(ds, task_id="T-1", from_status="ready", to_status="claimed",
                          actor="u-a", actor_kind="human")

    payload, code = api.task_events_service("T-1", user={"user_id": "u-a"})

    assert code == 200
    assert payload["data"][0]["to_status"] == "claimed"


def test_TC_P1_031_事件流不可见返回404(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", assignee="u-a")

    payload, code = api.task_events_service("T-1", user={"user_id": "u-x"})

    assert code == 404
    assert payload["success"] is False


def test_TC_P1_032_详情可见返回任务(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", assignee="u-a")

    payload, code = api.task_detail_service("T-1", user={"user_id": "u-a"})

    assert code == 200
    assert payload["data"]["id"] == "T-1"


def test_TC_P1_033_认领成功(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", assignee="", candidates=["u-a"], assign_policy="claim")

    payload, code = api.task_claim_service("T-1", user={"user_id": "u-a"})

    assert code == 200
    assert payload["data"]["status"] == "claimed"
    assert payload["data"]["assignee"] == "u-a"


def test_TC_P1_034_认领非候选池返回409(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", assignee="", candidates=["u-a"], assign_policy="claim")

    payload, code = api.task_claim_service("T-1", user={"user_id": "u-x"})

    assert code == 409
    assert payload["success"] is False
    # 无副作用
    assert ds.execute("SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "ready"


def test_TC_P1_035_监控列表非管理员403(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1")

    payload, code = api.task_monitor_service(user={"user_id": "u-plain", "permissions": []})

    assert code == 403


def test_TC_P1_036_监控列表管理员200(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1")

    payload, code = api.task_monitor_service(user=_admin())

    assert code == 200
    assert payload["data"]["total"] == 1


def test_TC_P1_037_非管理员按单据查询且按可见性收敛(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _approval_task(ds, task_id="T-mine", assignee="u-a", doc_ref_id="7")
    _approval_task(ds, task_id="T-other", assignee="u-b", doc_ref_id="9")

    payload, code = api.task_monitor_service(
        user={"user_id": "u-a", "permissions": []},
        type="approval", doc_ref_type="purchase_order", doc_ref_id="7")

    assert code == 200
    data = payload["data"]
    assert data["total"] == 1
    assert data["items"][0]["id"] == "T-mine"
    assert data["items"][0]["doc_ref_id"] == "7"
    assert "stage_no" in data["items"][0]


def test_TC_P1_038_非管理员缺单据参数403(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _approval_task(ds, task_id="T-1", assignee="u-a", doc_ref_id="7")
    user = {"user_id": "u-a", "permissions": []}

    payload, code = api.task_monitor_service(user=user)
    assert code == 403

    payload, code = api.task_monitor_service(
        user=user, doc_ref_type="purchase_order")       # 只给一个参数同样拒绝
    assert code == 403

    payload, code = api.task_monitor_service(
        user=user, doc_ref_type="purchase_order", doc_ref_id="7")
    assert code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4. 任务动作端点（spec §9.13.4.2 / D-AP-17）
# ─────────────────────────────────────────────────────────────────────────────

def test_TC_P1_040_候选池成员ready可认领(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", candidates=["u-a"], assign_policy="claim")

    payload, code = api.task_actions_service("T-1", user={"user_id": "u-a"})

    assert code == 200
    actions = {a["action"]: a for a in payload["data"]["actions"]}
    assert "claim" in actions
    assert actions["claim"]["endpoint"] == "POST /api/v1/tasks/T-1/claim"
    assert actions["claim"]["to_state"] == "claimed"
    assert "decision" not in actions


def test_TC_P1_041_非候选人只读不显示认领(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", created_by="u-owner", candidates=["u-a"])

    payload, code = api.task_actions_service("T-1", user={"user_id": "u-owner"})

    assert code == 200
    assert "claim" not in {a["action"] for a in payload["data"]["actions"]}


def test_TC_P1_042_审批动作按权限fail_closed(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", status="waiting_approval", type_="approval",
          assignee="u-appr", created_by="u-owner",
          doc_ref_type="purchase_order")
    allowed = {"user_id": "u-appr", "permissions": ["purchase_order:approve"]}
    denied = {"user_id": "u-appr", "permissions": []}

    payload, code = api.task_actions_service("T-1", user=allowed)
    assert code == 200
    assert "decision" in {a["action"] for a in payload["data"]["actions"]}

    payload, code = api.task_actions_service("T-1", user=denied)
    assert code == 200
    assert "decision" not in {a["action"] for a in payload["data"]["actions"]}


def test_TC_P1_043_不可见任务返回404(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", assignee="u-a", created_by="u-owner")

    payload, code = api.task_actions_service("T-1", user={"user_id": "u-x"})

    assert code == 404
    assert payload["success"] is False


def test_TC_P1_044_管理员可见启动与决策(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    # 管理员的可见性仍走行级闸门（非可见性后门），因此让他作为执行人/创建人
    _task(ds, task_id="T-1", status="ready", assignee="u-admin")
    _task(ds, task_id="T-2", status="waiting_approval", type_="approval",
          assignee="u-admin")

    payload, _ = api.task_actions_service("T-1", user=_admin())
    assert "start" in {a["action"] for a in payload["data"]["actions"]}

    payload, _ = api.task_actions_service("T-2", user=_admin())
    assert "decision" in {a["action"] for a in payload["data"]["actions"]}


# ─────────────────────────────────────────────────────────────────────────────
# 5. 控制动作端点（spec §9.13.4.2 第 3/5 条 / §9.13.6 第 2 步）
# ─────────────────────────────────────────────────────────────────────────────

def test_TC_P1_045_创建人可取消任务(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", status="ready", created_by="u-owner")

    payload, code = api.task_cancel_service(
        "T-1", user={"user_id": "u-owner"}, reason="需求变更")

    assert code == 200
    assert payload["data"]["status"] == "cancelled"
    assert payload["data"]["from_status"] == "ready"
    row = ds.execute(
        "SELECT status, finished_at FROM tasks WHERE id='T-1'").fetchall()[0]
    assert row[0] == "cancelled" and row[1]          # 终态时间已写
    events = ds.execute(
        "SELECT from_status, to_status, actor FROM task_events "
        "WHERE task_id='T-1' AND to_status='cancelled'").fetchall()
    assert ("ready", "cancelled", "u-owner") in events


def test_TC_P1_046_非创建人不可取消(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", status="ready", created_by="u-owner", assignee="u-a")

    payload, code = api.task_cancel_service("T-1", user={"user_id": "u-a"})

    assert code == 403
    assert payload["success"] is False
    # 无副作用
    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "ready"


def test_TC_P1_047_终态任务不可取消(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", status="done", created_by="u-owner")

    payload, code = api.task_cancel_service("T-1", user={"user_id": "u-owner"})

    assert code == 409
    assert payload["success"] is False
    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "done"


def test_TC_P1_048_管理员可取消非本人创建的任务(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    # 管理员可见性仍走行级闸门：让他作为执行人
    _task(ds, task_id="T-1", status="in_progress",
          created_by="u-owner", assignee="u-admin")

    payload, code = api.task_cancel_service("T-1", user=_admin())

    assert code == 200
    assert payload["data"]["status"] == "cancelled"


def test_TC_P1_049_挂起与解除严格交替且不改状态列(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", status="in_progress",
          created_by="u-owner", assignee="u-a")
    user = {"user_id": "u-a"}

    held, code = api.task_hold_service(
        "T-1", user=user, hold_code="WAIT_STOCK", reason="缺料")
    assert code == 200
    assert held["data"]["status"] == "in_progress"    # 状态列不变

    dup, code = api.task_hold_service(
        "T-1", user=user, hold_code="WAIT_STOCK")
    assert code == 409                                # 重复 hold 拒绝
    assert dup["success"] is False

    resumed, code = api.task_resume_service(
        "T-1", user=user, hold_code="WAIT_STOCK")
    assert code == 200

    again, code = api.task_resume_service(
        "T-1", user=user, hold_code="WAIT_STOCK")
    assert code == 409                                # 重复释放拒绝

    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "in_progress"
    counts = dict(ds.execute(
        "SELECT event_type, COUNT(*) FROM task_events "
        "WHERE task_id='T-1' AND event_type IN ('hold','release') "
        "GROUP BY event_type").fetchall())
    assert counts == {"hold": 1, "release": 1}


def test_TC_P1_050_挂起缺hold_code返回400(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", status="in_progress", assignee="u-a")

    payload, code = api.task_hold_service(
        "T-1", user={"user_id": "u-a"}, hold_code="")

    assert code == 400
    assert payload["success"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 6. 审批撤回（withdraw）：单据回退 + 任务取消（§9.13.4.2 第 4 条）
# ─────────────────────────────────────────────────────────────────────────────

def _approval_task(ds, **kw):
    kw.setdefault("type_", "approval")
    kw.setdefault("status", "waiting_approval")
    kw.setdefault("assignee", "u-reviewer")
    kw.setdefault("created_by", "u-submitter")
    kw.setdefault("doc_ref_type", "purchase_order")
    kw.setdefault("doc_ref_id", "1")
    return _task(ds, **kw)


def test_TC_P1_051_提交人撤回审批且单据回退(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    import meta.core.task_withdraw as tw

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    calls = []

    def fake_withdraw(object_type, record_id):
        calls.append((object_type, record_id))
        return {"success": True,
                "data": {"new_status": "draft", "purchase_order_id": record_id}}

    monkeypatch.setattr(tw, "withdraw_approval", fake_withdraw)
    _approval_task(ds, task_id="T-1", doc_ref_id="7")

    payload, code = api.task_withdraw_service(
        "T-1", user={"user_id": "u-submitter"}, reason="填错金额")

    assert code == 200
    assert payload["data"]["status"] == "cancelled"
    assert payload["data"]["document"]["new_status"] == "draft"
    assert calls == [("purchase_order", "7")]
    row = ds.execute(
        "SELECT status, finished_at FROM tasks WHERE id='T-1'").fetchall()[0]
    assert row[0] == "cancelled" and row[1]
    events = ds.execute(
        "SELECT to_status, actor FROM task_events WHERE task_id='T-1'").fetchall()
    assert ("cancelled", "u-submitter") in events


def test_TC_P1_052_非提交人不可撤回(ds, monkeypatch):
    import meta.api.task_inbox_api as api

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _approval_task(ds, task_id="T-1")

    payload, code = api.task_withdraw_service(
        "T-1", user={"user_id": "u-reviewer"})

    assert code == 403
    assert payload["success"] is False
    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "waiting_approval"


def test_TC_P1_053_已有通过审批时禁止撤回(ds, monkeypatch):
    import meta.api.task_inbox_api as api
    import meta.core.task_withdraw as tw

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    called = []
    monkeypatch.setattr(tw, "withdraw_approval",
                        lambda *a: called.append(a) or {"success": True, "data": {}})
    _approval_task(ds, task_id="T-1", doc_ref_id="1")
    _task(ds, task_id="T-0", type_="approval", status="done",
          created_by="u-submitter", assignee="u-reviewer",
          doc_ref_type="purchase_order", doc_ref_id="1",
          outputs={"decision": "approve"})

    payload, code = api.task_withdraw_service(
        "T-1", user={"user_id": "u-submitter"})

    assert code == 409
    assert "有效审批通过" in payload["message"]
    assert called == []                                    # 未触达单据回退
    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "waiting_approval"


def test_TC_P1_054_非审批任务不能撤回(ds, monkeypatch):
    import meta.api.task_inbox_api as api

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    _task(ds, task_id="T-1", type_="story", status="waiting_approval",
          created_by="u-submitter")

    payload, code = api.task_withdraw_service(
        "T-1", user={"user_id": "u-submitter"})

    assert code == 409
    assert "非审批任务" in payload["message"]
    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "waiting_approval"


def test_TC_P1_055_单据回退失败不取消任务且可重试(ds, monkeypatch):
    """幂等键在失败时回滚：重试会再次尝试单据回退（不会把失败当成功）。"""
    import meta.api.task_inbox_api as api
    import meta.core.task_withdraw as tw

    monkeypatch.setattr(api, "_platform_ds", lambda: ds)
    state = {"ok": False, "calls": 0}

    def fake_withdraw(object_type, record_id):
        state["calls"] += 1
        if not state["ok"]:
            return {"success": False, "message": "撤回未生效", "code": "EFFECT_NOT_APPLIED"}
        return {"success": True, "data": {"new_status": "draft"}}

    monkeypatch.setattr(tw, "withdraw_approval", fake_withdraw)
    _approval_task(ds, task_id="T-1", doc_ref_id="7")
    user = {"user_id": "u-submitter"}

    payload, code = api.task_withdraw_service("T-1", user=user)
    assert code == 409
    assert ds.execute(
        "SELECT status FROM tasks WHERE id='T-1'").fetchall()[0][0] == "waiting_approval"

    state["ok"] = True
    payload, code = api.task_withdraw_service("T-1", user=user)
    assert code == 200
    assert state["calls"] == 2                             # 失败未被幂等账记住
    assert payload["data"]["status"] == "cancelled"