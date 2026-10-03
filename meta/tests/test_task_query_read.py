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
  3. list_tasks：分页 + 过滤（status / type / app_id / executor_type）+ total 口径
"""

import json
from datetime import datetime

from meta.core.task_event_schema import (
    ensure_task_event_tables, list_task_events, record_task_event, record_transition,
)
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
    yield source


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _task(ds, *, task_id="T-1", status="ready", type_="story",
          executor_type="human", assignee="", candidates=None,
          assign_policy="direct", app_id="app-a", created_by="u-owner"):
    cols = ["id", "title", "type", "status", "priority", "app_id",
            "executor_type", "executor_assignee", "executor_candidates",
            "assign_policy", "created_by", "created_at", "updated_at"]
    vals = [task_id, "测试任务", type_, status, "P2", app_id,
            executor_type, assignee, json.dumps(candidates or []),
            assign_policy, created_by, _now(), _now()]
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