# -*- coding: utf-8 -*-
"""后端测试套件 - [C1] 编排实例层引擎（Run 实例化 / 依赖求值 / 进度派生）

测试 meta.core.workflow_engine 模块

覆盖目标（对齐 §12 C1 / §7.4 Run 模型 / 综合缝合 §3.2）:
  1. start_run: 定义版本 → Run（含 definition_snapshot 快照）+ 按节点克隆 Task
  2. 快照隔离: 发布新版本不影响在途 Run；快照是深拷贝而非共享引用
  3. deps 生成: 由 edges 反查入边 → tasks.deps[]（含 when）
  4. advance_run: pending→ready 依赖求值（复用 A2 守卫 + A3 事件账，幂等）
  5. run_progress: Run 无状态列，进度**派生**聚合（empty/pending/in_progress/done/failed）
  6. 事件账: created 事件与迁移配对（TASK_EVENT + WORKLOG）

注: 平台内部表（tasks / task_events / task_worklogs）暂无 Factory；按仓库既有惯例
走 raw SQL escape hatch（见 test_decision_effect.py 同款注释），避免整文件被
conftest 的 raw-SQL 门控拦跳。本文件 raw 写仅用于**预置任务状态**（done/failed），
其余全部走 public API。
"""

import os

os.environ.setdefault('ALLOW_RAW_SQL', '1')

from datetime import datetime

import pytest

from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import TASK_STATUSES, ensure_task_tables
from meta.core.workflow_engine import (
    RUN_STATUSES,
    WorkflowEngineError,
    advance_run,
    deps_satisfied,
    get_run,
    list_run_tasks,
    run_progress,
    start_run,
)
from meta.core.workflow_store import WorkflowStoreError, publish_workflow

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# 夹具 / 助手
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def ds(tmp_path):
    """独立临时平台库（任务四表 + 事件账两表）。"""
    from meta.core.datasource import get_data_source

    source = get_data_source("sqlite", database=str(tmp_path / "c1_engine.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    yield source


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _node(node_id, step=None, *, parent=None, group=None,
          title="节点", executor="human", **extra):
    node = {"node_id": node_id, "title": title, "executor_type": executor}
    if step is not None:
        node["step_number"] = step
    if parent is not None:
        node["parent_step_number"] = parent
    if group is not None:
        node["group_name"] = group
    node.update(extra)
    return node


def _linear_nodes():
    return [_node("n1", 1, title="受理"), _node("n2", 2, title="审批"),
            _node("n3", 3, title="归档")]


def _linear_edges():
    return [{"from": "n1", "to": "n2", "when": "done"},
            {"from": "n2", "to": "n3", "when": "done"}]


def _publish(ds, *, key="wf-a", nodes=None, edges=None, **kw):
    return publish_workflow(ds, workflow_key=key, name="流程A",
                            nodes=nodes if nodes is not None else _linear_nodes(),
                            edges=edges if edges is not None else _linear_edges(),
                            **kw)


def _tasks_by_node(ds, run_id):
    return {t["workflow_node_id"]: t for t in list_run_tasks(ds, run_id)}


def _count(ds, table, where="", params=()):
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return ds.execute(sql, params).fetchone()[0]


def _set_status(ds, task_id, status):
    """预置任务状态（仅测试用；平台内部表无 Factory）。"""
    with ds.transaction():
        ds.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                   (status, _now(), task_id))


# ─────────────────────────────────────────────────────────────────────────────
# start_run
# ─────────────────────────────────────────────────────────────────────────────

class TestStartRun:

    def test_creates_run_with_version_and_trigger(self, ds):
        """TC-WFE-001: Run 行写入，快照版本 = 定义版本"""
        _publish(ds)
        result = start_run(ds, workflow_key="wf-a", trigger_kind="manual",
                           doc_ref="SO-001", app_id="waybill", created_by="alice")
        run = get_run(ds, result["run_id"])
        assert run["workflow_version"] == 1
        assert run["trigger_kind"] == "manual"
        assert run["workflow_key"] == "wf-a"
        assert run["definition_snapshot"]["workflow"]["version"] == 1

    def test_clones_one_task_per_node_pending(self, ds):
        """TC-WFE-002: 每节点克隆一个 Task，初始 status=pending"""
        _publish(ds)
        result = start_run(ds, workflow_key="wf-a")
        tasks = list_run_tasks(ds, result["run_id"])
        assert len(tasks) == 3
        assert result["task_count"] == 3
        assert {t["status"] for t in tasks} == {"pending"}
        assert {t["workflow_node_id"] for t in tasks} == {"n1", "n2", "n3"}

    def test_deps_generated_from_edges(self, ds):
        """TC-WFE-003: deps 由入边生成（首节点空；下游指向上游任务 id）"""
        _publish(ds)
        result = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, result["run_id"])
        # 空 deps 落库为空值（_json_text 归一 [] → NULL），语义上等价「无依赖」
        assert not by_node["n1"]["deps"]
        assert by_node["n2"]["deps"] == [
            {"task_id": by_node["n1"]["id"], "when": "done"}]
        assert by_node["n3"]["deps"] == [
            {"task_id": by_node["n2"]["id"], "when": "done"}]

    def test_deps_when_defaults_to_done(self, ds):
        """TC-WFE-004: 边未声明 when → deps[].when = done"""
        _publish(ds, edges=[{"from": "n1", "to": "n2"}])
        result = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, result["run_id"])
        assert by_node["n2"]["deps"][0]["when"] == "done"

    def test_branch_block_deps(self, ds):
        """TC-WFE-005: 分支块节点各自持有挂载点任务的 deps"""
        nodes = [_node("n1", 1),
                 _node("a1", 2, parent=1, group="g"),
                 _node("a2", 3, parent=1, group="g")]
        edges = [{"from": "n1", "to": "a1"}, {"from": "n1", "to": "a2"}]
        _publish(ds, nodes=nodes, edges=edges)
        result = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, result["run_id"])
        assert [d["task_id"] for d in by_node["a1"]["deps"]] == [by_node["n1"]["id"]]
        assert [d["task_id"] for d in by_node["a2"]["deps"]] == [by_node["n1"]["id"]]

    def test_created_event_per_task(self, ds):
        """TC-WFE-006: 每任务落一条 created 事件"""
        _publish(ds)
        result = start_run(ds, workflow_key="wf-a")
        assert _count(ds, "task_events",
                      "workflow_run_id = ? AND event_type = 'created'",
                      (result["run_id"],)) == 3

    def test_doc_ref_and_app_id_propagated(self, ds):
        """TC-WFE-007: doc_ref / app_id 透传到克隆任务"""
        _publish(ds)
        result = start_run(ds, workflow_key="wf-a", doc_ref="SO-9", app_id="waybill")
        tasks = list_run_tasks(ds, result["run_id"])
        assert {t["doc_ref"] for t in tasks} == {"SO-9"}
        assert {t["app_id"] for t in tasks} == {"waybill"}

    def test_inputs_and_variables_persisted(self, ds):
        """TC-WFE-008: Run 入参 / 变量以 JSON 往返"""
        _publish(ds)
        result = start_run(ds, workflow_key="wf-a",
                           inputs={"doc_ref": "SO-1"}, variables={"k": 1})
        run = get_run(ds, result["run_id"])
        assert run["inputs"] == {"doc_ref": "SO-1"}
        assert run["variables"] == {"k": 1}

    def test_unknown_workflow_raises(self, ds):
        """TC-WFE-009: 定义不存在 → WorkflowStoreError"""
        with pytest.raises(WorkflowStoreError):
            start_run(ds, workflow_key="nope")


# ─────────────────────────────────────────────────────────────────────────────
# 快照隔离（C1 核心纪律）
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotIsolation:

    def test_new_version_does_not_change_inflight_run(self, ds):
        """TC-WFE-020: 发布 v2 后，在途 Run 的 definition_snapshot 逐字段不变"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        before = get_run(ds, run["run_id"])["definition_snapshot"]

        _publish(ds, nodes=[_node("n1", 1, title="受理V2"),
                            _node("n2", 2, title="审批"),
                            _node("n3", 3, title="归档")])

        after = get_run(ds, run["run_id"])["definition_snapshot"]
        assert after == before
        assert after["workflow"]["version"] == 1
        assert _tasks_by_node_snapshot(after)["n1"]["title"] == "受理"

    def test_new_run_picks_up_new_version(self, ds):
        """TC-WFE-021: v2 之后新建的 Run 使用 v2 快照"""
        _publish(ds)
        start_run(ds, workflow_key="wf-a")
        _publish(ds, nodes=[_node("n1", 1, title="受理V2"),
                            _node("n2", 2), _node("n3", 3)])
        run2 = start_run(ds, workflow_key="wf-a")
        assert run2["workflow_version"] == 2
        snapshot = get_run(ds, run2["run_id"])["definition_snapshot"]
        assert _tasks_by_node_snapshot(snapshot)["n1"]["title"] == "受理V2"

    def test_snapshot_is_persisted_copy_not_shared(self, ds):
        """TC-WFE-022: 篡改取出的快照不影响库内快照（深拷贝 + 持久化隔离）"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        snapshot = get_run(ds, run["run_id"])["definition_snapshot"]
        snapshot["nodes"][0]["title"] = "被篡改"
        re_read = get_run(ds, run["run_id"])["definition_snapshot"]
        assert _tasks_by_node_snapshot(re_read)["n1"]["title"] == "受理"

    def test_explicit_version_start(self, ds):
        """TC-WFE-023: 显式指定旧版本可实例化（版本化定义的价值）"""
        _publish(ds)
        _publish(ds, nodes=[_node("n1", 1, title="受理V2"),
                            _node("n2", 2), _node("n3", 3)])
        run = start_run(ds, workflow_key="wf-a", version=1)
        assert run["workflow_version"] == 1
        snapshot = get_run(ds, run["run_id"])["definition_snapshot"]
        assert _tasks_by_node_snapshot(snapshot)["n1"]["title"] == "受理"


def _tasks_by_node_snapshot(snapshot):
    return {n["node_id"]: n for n in snapshot["nodes"]}


# ─────────────────────────────────────────────────────────────────────────────
# deps_satisfied（纯函数）
# ─────────────────────────────────────────────────────────────────────────────

class TestDepsSatisfied:

    def test_empty_deps_satisfied(self):
        """TC-WFE-030: 无 deps → 满足（首节点）"""
        assert deps_satisfied([], {}) is True
        assert deps_satisfied(None, {}) is True

    def test_done_only(self):
        """TC-WFE-031: when=done 仅接受 done"""
        deps = [{"task_id": "t1", "when": "done"}]
        assert deps_satisfied(deps, {"t1": "done"}) is True
        assert deps_satisfied(deps, {"t1": "pending"}) is False
        assert deps_satisfied(deps, {"t1": "skipped"}) is False

    def test_skipped_only(self):
        """TC-WFE-032: when=skipped 仅接受 skipped"""
        deps = [{"task_id": "t1", "when": "skipped"}]
        assert deps_satisfied(deps, {"t1": "skipped"}) is True
        assert deps_satisfied(deps, {"t1": "done"}) is False

    def test_done_or_skipped(self):
        """TC-WFE-033: when=done_or_skipped 接受 done / skipped"""
        deps = [{"task_id": "t1", "when": "done_or_skipped"}]
        assert deps_satisfied(deps, {"t1": "done"}) is True
        assert deps_satisfied(deps, {"t1": "skipped"}) is True
        assert deps_satisfied(deps, {"t1": "failed"}) is False

    def test_failed_only(self):
        """TC-WFE-034: when=failed 仅接受 failed（补偿分支用）"""
        deps = [{"task_id": "t1", "when": "failed"}]
        assert deps_satisfied(deps, {"t1": "failed"}) is True
        assert deps_satisfied(deps, {"t1": "done"}) is False

    def test_and_semantics(self):
        """TC-WFE-035: 多 deps 为 AND 语义"""
        deps = [{"task_id": "t1", "when": "done"}, {"task_id": "t2", "when": "done"}]
        assert deps_satisfied(deps, {"t1": "done", "t2": "done"}) is True
        assert deps_satisfied(deps, {"t1": "done", "t2": "pending"}) is False

    def test_unknown_when_fail_closed(self):
        """TC-WFE-036: 未知 when → fail-closed（不满足）"""
        assert deps_satisfied([{"task_id": "t1", "when": "bogus"}],
                              {"t1": "done"}) is False

    def test_unknown_task_fail_closed(self):
        """TC-WFE-037: 未知任务 id → fail-closed"""
        assert deps_satisfied([{"task_id": "ghost", "when": "done"}], {}) is False

    def test_non_list_deps_fail_closed(self):
        """TC-WFE-038: deps 非数组 → fail-closed"""
        assert deps_satisfied({"task_id": "t1"}, {}) is False
        assert deps_satisfied(["x"], {}) is False


# ─────────────────────────────────────────────────────────────────────────────
# advance_run
# ─────────────────────────────────────────────────────────────────────────────

class TestAdvanceRun:

    def test_promotes_root_blocks_downstream(self, ds):
        """TC-WFE-040: 首节点提升为 ready，下游仍 pending（被 deps 阻断）"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, run["run_id"])

        result = advance_run(ds, run["run_id"])
        assert result["promoted"] == [by_node["n1"]["id"]]
        assert set(result["blocked"]) == {by_node["n2"]["id"], by_node["n3"]["id"]}

        after = _tasks_by_node(ds, run["run_id"])
        assert after["n1"]["status"] == "ready"
        assert after["n2"]["status"] == "pending"
        assert after["n3"]["status"] == "pending"

    def test_records_transition_event_and_worklog(self, ds):
        """TC-WFE-041: 提升落 A3 配对账（1 事件 + 1 WORKLOG）"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        advance_run(ds, run["run_id"])
        assert _count(ds, "task_events",
                      "workflow_run_id = ? AND event_type = 'status_changed'",
                      (run["run_id"],)) == 1
        assert _count(ds, "task_worklogs",
                      "workflow_run_id = ? AND entry_type = 'transition'",
                      (run["run_id"],)) == 1

    def test_idempotent_second_call(self, ds):
        """TC-WFE-042: 重复调用不再提升（幂等）"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        first = advance_run(ds, run["run_id"])
        second = advance_run(ds, run["run_id"])
        assert second["promoted"] == []
        assert set(second["blocked"]) == set(first["blocked"])
        assert _count(ds, "task_events",
                      "workflow_run_id = ? AND event_type = 'status_changed'",
                      (run["run_id"],)) == 1

    def test_cascade_after_upstream_done(self, ds):
        """TC-WFE-043: 上游 done 后，下一跳在同次 advance 内提升（单遍传播）"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, run["run_id"])

        advance_run(ds, run["run_id"])
        _set_status(ds, by_node["n1"]["id"], "done")

        result = advance_run(ds, run["run_id"])
        assert result["promoted"] == [by_node["n2"]["id"]]
        # n3 依赖 n2 仍 pending → 同遍不提升
        assert by_node["n3"]["id"] in result["blocked"]

        _set_status(ds, by_node["n2"]["id"], "done")
        result2 = advance_run(ds, run["run_id"])
        assert result2["promoted"] == [by_node["n3"]["id"]]

    def test_skipped_upstream_satisfies_done_or_skipped(self, ds):
        """TC-WFE-044: when=done_or_skipped 的上游 skipped → 下游可提升"""
        _publish(ds, edges=[{"from": "n1", "to": "n2", "when": "done_or_skipped"}])
        run = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, run["run_id"])
        _set_status(ds, by_node["n1"]["id"], "skipped")
        result = advance_run(ds, run["run_id"])
        # n2 因 skipped 上游满足而提升；n3 无入边（本次 edges 只声明 n1→n2）故一并提升
        assert by_node["n2"]["id"] in result["promoted"]
        assert set(result["promoted"]) == {by_node["n2"]["id"], by_node["n3"]["id"]}
        assert _tasks_by_node(ds, run["run_id"])["n2"]["status"] == "ready"


# ─────────────────────────────────────────────────────────────────────────────
# run_progress（派生聚合）
# ─────────────────────────────────────────────────────────────────────────────

class TestRunProgress:

    def test_unknown_run_is_empty(self, ds):
        """TC-WFE-050: 无任务的 Run → empty"""
        progress = run_progress(ds, "nope")
        assert progress["total"] == 0
        assert progress["status"] == "empty"

    def test_counts_cover_all_statuses(self, ds):
        """TC-WFE-051: counts 覆盖全部 11 态键"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        progress = run_progress(ds, run["run_id"])
        assert set(progress["counts"]) == set(TASK_STATUSES)
        assert progress["total"] == 3
        assert RUN_STATUSES == ("empty", "pending", "in_progress", "done", "failed")

    def test_pending_before_advance(self, ds):
        """TC-WFE-052: 全 pending → 派生 pending"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        assert run_progress(ds, run["run_id"])["status"] == "pending"

    def test_in_progress_after_advance(self, ds):
        """TC-WFE-053: 有 ready → 派生 in_progress"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        advance_run(ds, run["run_id"])
        assert run_progress(ds, run["run_id"])["status"] == "in_progress"

    def test_done_when_all_terminal(self, ds):
        """TC-WFE-054: 全部 done/skipped/cancelled → 派生 done"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, run["run_id"])
        _set_status(ds, by_node["n1"]["id"], "done")
        _set_status(ds, by_node["n2"]["id"], "skipped")
        _set_status(ds, by_node["n3"]["id"], "cancelled")
        progress = run_progress(ds, run["run_id"])
        assert progress["status"] == "done"
        assert progress["counts"]["done"] == 1
        assert progress["counts"]["skipped"] == 1

    def test_failed_dominates(self, ds):
        """TC-WFE-055: 任一 failed/dead → 派生 failed（优先于 done）"""
        _publish(ds)
        run = start_run(ds, workflow_key="wf-a")
        by_node = _tasks_by_node(ds, run["run_id"])
        _set_status(ds, by_node["n1"]["id"], "failed")
        _set_status(ds, by_node["n2"]["id"], "done")
        assert run_progress(ds, run["run_id"])["status"] == "failed"
