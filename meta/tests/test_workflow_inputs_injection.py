# -*- coding: utf-8 -*-
"""S2 接缝：`outputs → inputs` 注入（spec §9.3.13 S2）。

覆盖:
- 整值占位保留原类型（list/dict），字符串内嵌占位按 str() 拼接
- `run.inputs.<path>` 在首节点生效
- 缺失路径 → 不提升、保持 pending、blocked_reasons 给出路径
- 发布期引用非直接上游 / 语法非法 → INPUT_TEMPLATE_INVALID
- advance 重复调用幂等
"""
import json
import os

os.environ.setdefault("ALLOW_RAW_SQL", "1")

import pytest

from meta.core.datasource import get_data_source
from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_definition import WorkflowDefinitionError
from meta.core.workflow_engine import advance_run, start_run
from meta.core.workflow_store import publish_workflow

pytestmark = pytest.mark.unit

WF_KEY = "wf-s2"


@pytest.fixture()
def ds(tmp_path):
    source = get_data_source("sqlite", database=str(tmp_path / "s2.db"))
    with source.transaction():
        ensure_task_tables(source)
        ensure_task_event_tables(source)
    yield source


def _publish(ds, *, template, inputs=None, key=WF_KEY):
    nodes = [
        {"node_id": "n1", "title": "建单", "step_number": 1,
         "executor_type": "human"},
        {"node_id": "n2", "title": "收货", "step_number": 2,
         "executor_type": "human",
         "meta": {"inputs_template": template}},
    ]
    edges = [{"from": "n1", "to": "n2", "when": "done"}]
    publish_workflow(ds, workflow_key=key, name="S2 流程", nodes=nodes, edges=edges)
    return start_run(ds, workflow_key=key, inputs=inputs)


def _mark_done(ds, task_id, outputs):
    ds.update("tasks", task_id, {
        "status": "done", "outputs": json.dumps(outputs, ensure_ascii=False),
    })


def _read_task(ds, task_id):
    rows = ds.execute("SELECT status, inputs FROM tasks WHERE id = ?",
                      (task_id,)).fetchall()
    status, inputs = rows[0]
    return status, (json.loads(inputs) if inputs else None)


class TestInputsInjection:

    def test_injects_upstream_outputs_and_run_inputs(self, ds):
        run = _publish(ds, template={
            "edge_ids": "{{n1.outputs.edge_ids}}",
            "order_no": "{{run.inputs.order_no}}",
            "note": "doc-{{n1.outputs.doc_id}}",
            "keep": 3,
        }, inputs={"order_no": "SO-1"})
        _mark_done(ds, run["task_ids"]["n1"],
                   {"edge_ids": ["e1", "e2"], "doc_id": "T-9"})

        result = advance_run(ds, run["run_id"])

        n2 = run["task_ids"]["n2"]
        assert n2 in result["promoted"]
        status, inputs = _read_task(ds, n2)
        assert status == "ready"
        assert inputs == {
            "edge_ids": ["e1", "e2"],
            "order_no": "SO-1",
            "note": "doc-T-9",
            "keep": 3,
        }
        assert isinstance(inputs["edge_ids"], list)

    def test_unresolved_path_keeps_pending(self, ds):
        run = _publish(ds, template={"x": "{{n1.outputs.missing}}"})
        _mark_done(ds, run["task_ids"]["n1"], {})

        result = advance_run(ds, run["run_id"])

        n2 = run["task_ids"]["n2"]
        assert result["promoted"] == []
        assert n2 in result["blocked"]
        assert result["blocked_reasons"][n2] == (
            "INPUT_TEMPLATE_UNRESOLVED:n1.outputs.missing")
        status, inputs = _read_task(ds, n2)
        assert status == "pending"
        assert inputs is None

    def test_first_node_template_uses_run_inputs(self, ds):
        nodes = [{"node_id": "n1", "title": "首节点", "step_number": 1,
                  "executor_type": "human",
                  "meta": {"inputs_template": {
                      "order_no": "{{run.inputs.order_no}}"}}}]
        publish_workflow(ds, workflow_key="wf-s2-first", name="首节点流程",
                         nodes=nodes, edges=[])
        run = start_run(ds, workflow_key="wf-s2-first",
                        inputs={"order_no": "SO-7"})

        result = advance_run(ds, run["run_id"])

        assert result["promoted"] == [run["task_ids"]["n1"]]
        status, inputs = _read_task(ds, run["task_ids"]["n1"])
        assert status == "ready"
        assert inputs == {"order_no": "SO-7"}

    def test_advance_is_idempotent(self, ds):
        run = _publish(ds, template={"edge_ids": "{{n1.outputs.edge_ids}}"})
        _mark_done(ds, run["task_ids"]["n1"], {"edge_ids": ["e1"]})

        first = advance_run(ds, run["run_id"])
        second = advance_run(ds, run["run_id"])

        assert first["promoted"] == [run["task_ids"]["n2"]]
        assert second["promoted"] == []
        _, inputs = _read_task(ds, run["task_ids"]["n2"])
        assert inputs == {"edge_ids": ["e1"]}

    def test_publish_rejects_non_upstream_ref(self, ds):
        nodes = [
            {"node_id": "n1", "title": "A", "step_number": 1},
            {"node_id": "n2", "title": "B", "step_number": 2},
            {"node_id": "n3", "title": "C", "step_number": 3,
             "meta": {"inputs_template": {"x": "{{n1.outputs.x}}"}}},
        ]
        edges = [{"from": "n1", "to": "n2", "when": "done"},
                 {"from": "n2", "to": "n3", "when": "done"}]

        with pytest.raises(WorkflowDefinitionError) as exc:
            publish_workflow(ds, workflow_key="wf-s2-bad", name="非法引用",
                             nodes=nodes, edges=edges)

        assert any(f.code == "INPUT_TEMPLATE_INVALID" for f in exc.value.findings)

    def test_publish_rejects_invalid_syntax(self, ds):
        nodes = [
            {"node_id": "n1", "title": "A", "step_number": 1},
            {"node_id": "n2", "title": "B", "step_number": 2,
             "meta": {"inputs_template": {"x": "{{n1.outputs}}"}}},
        ]
        edges = [{"from": "n1", "to": "n2", "when": "done"}]

        with pytest.raises(WorkflowDefinitionError) as exc:
            publish_workflow(ds, workflow_key="wf-s2-syntax", name="非法语法",
                             nodes=nodes, edges=edges)

        assert any(f.code == "INPUT_TEMPLATE_INVALID" for f in exc.value.findings)
