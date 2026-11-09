# -*- coding: utf-8 -*-
"""S3 接缝：`compensate_task()` 补偿执行配置适配（spec §9.3.13 S3）。

覆盖:
- system 任务 + bo_action → 补偿任务改写为 `doc_flow.reverse`，
  `inputs=params` 且继承原任务 `outputs.edge_ids`
- `partial/update/compensate` 缺 ref_id → REF_ID_REQUIRED
- `mode=none` → 直接 skipped，不建补偿任务
- 人工任务保持原执行配置（不誤改写）
- 未知 mode → 确定性错误
- ref_id / params 显式传入优先，mode 归一为语义名
"""
import json
import os

os.environ.setdefault("ALLOW_RAW_SQL", "1")

import pytest

from meta.services.bo_action_registrations import register_all_bo_actions
from meta.core.datasource import get_data_source
from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import WorkflowEngineError, compensate_task, start_run
from meta.core.workflow_store import publish_workflow

pytestmark = pytest.mark.unit

WF_KEY = "wf-s3"


@pytest.fixture()
def ds(tmp_path):
    source = get_data_source("sqlite", database=str(tmp_path / "s3.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    register_all_bo_actions()
    yield source


def _publish(ds, *, executor="system", action_id="doc_flow.derive"):
    nodes = [{
        "node_id": "n1", "title": "建单", "step_number": 1,
        "executor_type": executor,
    }]
    if action_id:
        nodes[0]["executor_config"] = {"action_id": action_id}
    publish_workflow(ds, workflow_key=WF_KEY, name="S3 流程",
                     nodes=nodes, edges=[])
    return start_run(ds, workflow_key=WF_KEY)


def _mark_done(ds, task_id, outputs=None):
    ds.update("tasks", task_id, {
        "status": "done",
        "outputs": json.dumps(outputs) if outputs is not None else None,
    })


def _read_task(ds, task_id):
    rows = ds.execute(
        "SELECT executor_type, executor_config, inputs, outputs, meta "
        "FROM tasks WHERE id = ?", (task_id,)).fetchall()
    keys = ("executor_type", "executor_config", "inputs", "outputs", "meta")
    record = dict(zip(keys, rows[0]))
    for key in ("executor_config", "inputs", "outputs", "meta"):
        if isinstance(record[key], str) and record[key]:
            record[key] = json.loads(record[key])
    return record


def _task_count(ds):
    return ds.execute("SELECT COUNT(*) FROM tasks").fetchall()[0][0]


class TestCompensationAdapter:

    def test_system_task_rewrites_to_reverse_action(self, ds):
        run = _publish(ds)
        _mark_done(ds, run["task_ids"]["n1"], {"edge_ids": ["e1", "e2"]})

        result = compensate_task(ds, run["task_ids"]["n1"],
                                 bo_action={"mode": "cancel"})

        task = _read_task(ds, result["task_id"])
        assert task["executor_type"] == "system"
        assert task["executor_config"]["action_id"] == "doc_flow.reverse"
        assert task["executor_config"]["params"] == {
            "mode": "cancel", "edge_ids": ["e1", "e2"]}
        assert task["inputs"] == task["executor_config"]["params"]
        assert task["meta"]["compensation_mode"] == "cancel"
        assert task["meta"]["bo_action"] == {"mode": "cancel"}

    def test_ref_required_for_partial_update_compensate(self, ds):
        run = _publish(ds)
        _mark_done(ds, run["task_ids"]["n1"], {"edge_ids": ["e1"]})

        for mode in ("partial", "update", "compensate"):
            with pytest.raises(WorkflowEngineError) as exc:
                compensate_task(ds, run["task_ids"]["n1"],
                                bo_action={"mode": mode})
            assert "REF_ID_REQUIRED" in str(exc.value)

    def test_none_mode_skips_without_new_task(self, ds):
        run = _publish(ds)
        _mark_done(ds, run["task_ids"]["n1"], {"edge_ids": ["e1"]})
        before = _task_count(ds)

        result = compensate_task(ds, run["task_ids"]["n1"],
                                 bo_action={"mode": "none"})

        assert result["skipped"] is True
        assert result["task_id"] is None
        assert _task_count(ds) == before

    def test_human_task_keeps_executor_config(self, ds):
        run = _publish(ds, executor="human", action_id=None)
        _mark_done(ds, run["task_ids"]["n1"])

        result = compensate_task(ds, run["task_ids"]["n1"],
                                 bo_action={"mode": "cancel"})

        task = _read_task(ds, result["task_id"])
        assert task["executor_type"] == "human"
        assert task["executor_config"] is None
        assert task["inputs"] is None

    def test_explicit_params_and_ref_id_are_merged(self, ds):
        run = _publish(ds)
        _mark_done(ds, run["task_ids"]["n1"], {"edge_ids": ["e1"]})

        result = compensate_task(
            ds, run["task_ids"]["n1"],
            bo_action={"mode": "red_ink_edge"},
            ref_id="RED-9",
            params={"quantity": 5.0, "edge_ids": ["e2"]})

        task = _read_task(ds, result["task_id"])
        assert task["executor_config"]["params"] == {
            "mode": "update", "quantity": 5.0,
            "edge_ids": ["e2"], "ref_id": "RED-9"}

    def test_unknown_mode_raises(self, ds):
        run = _publish(ds)
        _mark_done(ds, run["task_ids"]["n1"])
        with pytest.raises(WorkflowEngineError) as exc:
            compensate_task(ds, run["task_ids"]["n1"],
                            bo_action={"mode": "explode"})
        assert "未知补偿 mode" in str(exc.value)


class TestPublishActionGuard:

    def test_unregistered_action_rejected(self, ds):
        from meta.core.workflow_store import WorkflowStoreError

        with pytest.raises(WorkflowStoreError) as exc:
            publish_workflow(ds, workflow_key="wf-bad", name="坏流程",
                             nodes=[{
                                 "node_id": "n1", "title": "x",
                                 "step_number": 1, "executor_type": "system",
                                 "executor_config": {"action_id": "nope.action"},
                             }], edges=[])
        assert "ACTION_NOT_REGISTERED" in str(exc.value)