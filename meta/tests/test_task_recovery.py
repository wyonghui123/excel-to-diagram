# -*- coding: utf-8 -*-
"""后端测试套件 - [C4] 受控转移：跳过（ready→skipped）与补偿（新建补偿任务）

测试 meta.core.workflow_engine 的 skip_task / compensate_task

覆盖目标（对齐 §12 C4 / §3.3 定律 1 / 综合 §5.3）:
  1. 跳过: 仅 ready 合法 → 经状态机守卫 + 配对落账（TASK_EVENT + WORKLOG）
  2. 传播**复用** advance_run: when=done_or_skipped 的下游提升；
     when=done 的下游保持 pending（不写第二套级联）
  3. 非 ready / 不存在 / 重复跳过 → 确定性错误
  4. 补偿: 仅 done 任务 + 属 Run；新建补偿任务（pending → advance 提升为 ready）
  5. 新旧链路: meta.compensates_task_id（直接前驱）+ meta.reference_task_id（链根）
  6. **任务侧不写对象表**: bo_action 只作为声明落 meta，不代调

注: 平台内部表（tasks / task_events）暂无 Factory；按仓库既有惯例走 raw SQL
escape hatch（同 test_decision_effect.py 注释），raw 写仅用于**预置状态**。

对应方案: docs/superpowers/specs/2026-09-07-task-model-design.md §12.1 C4 / §7.2
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import json
from datetime import datetime

import pytest

from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import (
    WorkflowEngineError,
    advance_run,
    compensate_task,
    list_run_tasks,
    skip_task,
    start_run,
)
from meta.core.workflow_store import publish_workflow

pytestmark = pytest.mark.unit

WF_KEY = "wf-c4"


# ─────────────────────────────────────────────────────────────────────────────
# 夹具 / 助手
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（任务四表 + 事件账两表）。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "c4.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    yield source


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _node(node_id, step, title="节点", executor="human"):
    return {"node_id": node_id, "title": title, "executor_type": executor,
            "step_number": step}


def _two_node_run(ds, edges=None):
    """发布两节点定义并实例化；advance 后 n1 为 ready、n2 待 n1。

    默认声明 n1→n2 边 —— 否则两节点都无 deps，会被 advance 一并提升。
    """
    publish_workflow(ds, workflow_key=WF_KEY, name="C4 流程",
                     nodes=[_node("n1", 1, "受理"), _node("n2", 2, "复核")],
                     edges=edges if edges is not None
                     else [{"from": "n1", "to": "n2", "when": "done"}])
    run = start_run(ds, workflow_key=WF_KEY)
    advance_run(ds, run["run_id"])
    return run


def _set_status(ds, task_id, status):
    """预置任务状态（仅测试用；平台内部表无 Factory）。"""
    with ds.transaction():
        ds.execute("UPDATE tasks SET status = ?, finished_at = ?, updated_at = ? "
                   "WHERE id = ?", (status, _now(), _now(), task_id))


def _task_row(ds, task_id):
    row = ds.execute("SELECT status, finished_at, workflow_run_id, workflow_node_id, "
                     "meta FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return {"status": row[0], "finished_at": row[1], "workflow_run_id": row[2],
            "workflow_node_id": row[3],
            "meta": json.loads(row[4]) if row[4] else {}}


def _count(ds, sql, params=()):
    return ds.execute(sql, params).fetchone()[0]


def _insert_loose_ready_task(ds, task_id):
    """预置一张不属任何 Run 的 ready 任务（覆盖「无 Run 不传播」分支）。"""
    with ds.transaction():
        ds.execute(
            "INSERT INTO tasks (id, title, type, status, priority, executor_type, "
            "assign_policy, claim_timeout_seconds, attempt, created_at, updated_at) "
            "VALUES (?, '游离任务', 'story', 'ready', 'P2', 'human', 'direct', "
            "300, 1, ?, ?)", (task_id, _now(), _now()))


# ─────────────────────────────────────────────────────────────────────────────
# 1. 跳过
# ─────────────────────────────────────────────────────────────────────────────

class TestSkipTask:

    def test_skip_ready_task_transitions_and_records(self, ds):
        """TC-WFR-001: ready → skipped；TASK_EVENT 与 WORKLOG 配对落账"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        # advance 已为 n1 落一条 pending→ready 的 WORKLOG，故用增量断言「配对」
        worklogs_before = _count(ds, "SELECT COUNT(*) FROM task_worklogs WHERE task_id = ?",
                                 (n1,))

        result = skip_task(ds, n1, actor="alice", actor_kind="human",
                           reason="条件边判定为否")

        assert result["status"] == "skipped"
        assert result["from_status"] == "ready"
        assert _task_row(ds, n1)["status"] == "skipped"
        assert _count(ds, "SELECT COUNT(*) FROM task_events WHERE task_id = ? "
                          "AND event_type = 'status_changed' AND from_status = 'ready' "
                          "AND to_status = 'skipped'", (n1,)) == 1
        assert _count(ds, "SELECT COUNT(*) FROM task_worklogs WHERE task_id = ?",
                      (n1,)) == worklogs_before + 1

    def test_skip_marks_finished_at(self, ds):
        """TC-WFR-002: 跳过属终态 → finished_at 落值"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        skip_task(ds, n1)
        assert _task_row(ds, n1)["finished_at"]

    def test_skip_non_ready_rejected(self, ds):
        """TC-WFR-003: pending 任务（状态机无 pending→skipped）→ 报错且状态不变"""
        run = _two_node_run(ds)
        n2 = run["task_ids"]["n2"]          # n2 仍 pending（等 n1）
        with pytest.raises(WorkflowEngineError):
            skip_task(ds, n2)
        assert _task_row(ds, n2)["status"] == "pending"

    def test_skip_unknown_task_rejected(self, ds):
        """TC-WFR-004: 不存在的任务 → 报错"""
        with pytest.raises(WorkflowEngineError):
            skip_task(ds, "no-such-task")

    def test_skip_twice_rejected(self, ds):
        """TC-WFR-005: 重复跳过（终态无出边）→ 报错"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        skip_task(ds, n1)
        with pytest.raises(WorkflowEngineError):
            skip_task(ds, n1)

    def test_skip_propagates_by_when_semantics(self, ds):
        """TC-WFR-006: 传播复用 advance_run —— done_or_skipped 下游提升、done 不提升"""
        publish_workflow(ds, workflow_key=WF_KEY, name="C4 三节点",
                         nodes=[_node("n1", 1), _node("n2", 2), _node("n3", 3)],
                         edges=[{"from": "n1", "to": "n2", "when": "done_or_skipped"},
                                {"from": "n1", "to": "n3", "when": "done"}])
        run = start_run(ds, workflow_key=WF_KEY)
        advance_run(ds, run["run_id"])      # n1 → ready
        ids = run["task_ids"]

        result = skip_task(ds, ids["n1"])

        assert result["promoted"] == [ids["n2"]]
        assert _task_row(ds, ids["n2"])["status"] == "ready"
        assert _task_row(ds, ids["n3"])["status"] == "pending"

    def test_skip_task_without_run_does_not_propagate(self, ds):
        """TC-WFR-007: 无 Run 的 ready 任务可跳过，promoted 为空（不误调 advance）"""
        _insert_loose_ready_task(ds, "loose-1")
        result = skip_task(ds, "loose-1")
        assert result["status"] == "skipped"
        assert result["promoted"] == []


# ─────────────────────────────────────────────────────────────────────────────
# 2. 补偿
# ─────────────────────────────────────────────────────────────────────────────

class TestCompensateTask:

    def test_creates_linked_compensation_task(self, ds):
        """TC-WFR-020: done 任务 → 新建补偿任务，携带新旧链路"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        _set_status(ds, n1, "done")

        result = compensate_task(ds, n1, actor="bob", reason="业务变更需红字")

        new = _task_row(ds, result["task_id"])
        assert new["status"] == "ready"                 # advance 已提升
        assert new["meta"]["compensates_task_id"] == n1
        assert new["meta"]["reference_task_id"] == n1
        assert new["meta"]["reason"] == "业务变更需红字"
        assert new["workflow_run_id"] == run["run_id"]
        assert new["workflow_node_id"] == "n1"          # 同一节点（重跑该步）

    def test_new_task_title_and_attempt(self, ds):
        """TC-WFR-021: 补偿任务标题带前缀、attempt 复位为 1"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        _set_status(ds, n1, "done")
        result = compensate_task(ds, n1)
        row = ds.execute("SELECT title, attempt FROM tasks WHERE id = ?",
                         (result["task_id"],)).fetchone()
        assert row[0].startswith("补偿：")
        assert row[1] == 1

    def test_compensation_recorded_as_created_event(self, ds):
        """TC-WFR-022: 补偿任务落 created 事件（载荷含链路）"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        _set_status(ds, n1, "done")
        result = compensate_task(ds, n1)

        payload = ds.execute(
            "SELECT payload FROM task_events WHERE task_id = ? AND event_type = 'created'",
            (result["task_id"],)).fetchone()[0]
        assert json.loads(payload)["compensates_task_id"] == n1

    def test_requires_done_task(self, ds):
        """TC-WFR-023: 仅 done 可补偿（ready / failed 均拒）"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]              # ready
        with pytest.raises(WorkflowEngineError):
            compensate_task(ds, n1)
        _set_status(ds, n1, "failed")
        with pytest.raises(WorkflowEngineError):
            compensate_task(ds, n1)

    def test_requires_run_bound_task(self, ds):
        """TC-WFR-024: 不属任何 Run 的任务 → 拒绝（补偿只在编排实例内）"""
        _insert_loose_ready_task(ds, "loose-2")
        _set_status(ds, "loose-2", "done")
        with pytest.raises(WorkflowEngineError):
            compensate_task(ds, "loose-2")

    def test_chain_root_inherited_on_second_compensation(self, ds):
        """TC-WFR-025: 对补偿任务再补偿 → reference_task_id 仍指向链根"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        _set_status(ds, n1, "done")
        first = compensate_task(ds, n1)

        _set_status(ds, first["task_id"], "done")
        second = compensate_task(ds, first["task_id"])

        meta = _task_row(ds, second["task_id"])["meta"]
        assert meta["compensates_task_id"] == first["task_id"]   # 直接前驱
        assert meta["reference_task_id"] == n1                   # 链根不变

    def test_bo_action_declared_not_invoked(self, ds):
        """TC-WFR-026: bo_action 只落声明 —— 无 app 数据源也能补偿（任务不写对象表）"""
        run = _two_node_run(ds)
        n1 = run["task_ids"]["n1"]
        _set_status(ds, n1, "done")
        declaration = {"action_id": "reverse_outbound", "mode": "red_ink_edge"}
        result = compensate_task(ds, n1, bo_action=declaration)
        assert _task_row(ds, result["task_id"])["meta"]["bo_action"] == declaration

    def test_compensation_visible_in_run_tasks(self, ds):
        """TC-WFR-027: 补偿任务属同一 Run（Run 任务集 +1）"""
        run = _two_node_run(ds)
        before = len(list_run_tasks(ds, run["run_id"]))
        n1 = run["task_ids"]["n1"]
        _set_status(ds, n1, "done")
        compensate_task(ds, n1)
        assert len(list_run_tasks(ds, run["run_id"])) == before + 1