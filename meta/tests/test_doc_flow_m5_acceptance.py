# -*- coding: utf-8 -*-
"""M5-1 验收：SO → shipment 建单 + 取消补偿只冲销一次（spec §9.3.13）。

端到端串联四个接缝，而不是分别验证：
- S2：`run.inputs` → `task.meta.inputs_template` → `task.inputs`（advance_run 注入）
- S1：`BOActionExecutor` 执行 `doc_flow.derive` 建单，`outputs.edge_ids` 落库
- S3：`compensate_task` 把补偿任务改写为 `doc_flow.reverse`，执行后冲销原边
- 幂等：同一补偿任务重放、二次补偿均不产生新边，也不重复建单

对应验收表 M5-1：「建单成功；取消补偿只冲销一次，不重复建单」。
"""
import json
import os

os.environ.setdefault("ALLOW_RAW_SQL", "1")

import pytest

from meta.core.bo_action_executor import BOActionExecutor, OUTCOME_COMPLETED
from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_rule_store import ensure_doc_flow_rule_table, upsert_rules
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.table_name_validator import invalidate_cache
from meta.core.task_assignment import resolve_assignment
from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_idempotency import ensure_idempotency_table
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import advance_run, compensate_task, start_run
from meta.core.workflow_store import publish_workflow
from meta.services.bo_action_registrations import register_all_bo_actions
from meta.services.doc_flow_service import DocFlowService, init_doc_flow_service

SOURCE_BO = "df_m5_sales_line"
TARGET_BO = "df_m5_delivery"
RULE_ID = "df-m5-sales-to-delivery-v1"
WF_KEY = "wf-m5-so-shipment"
NODE_ID = "n1"
_REGISTERED_BOS = (SOURCE_BO, TARGET_BO)

#: S2 模板：整值占位取 run.inputs，验证 list/dict 类型不被字符串化
_INPUTS_TEMPLATE = {
    "rule_id": "{{run.inputs.rule_id}}",
    "sources": "{{run.inputs.sources}}",
    "target": "{{run.inputs.target}}",
}


def _field(fid, ftype, **kw):
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _metas():
    source = MetaObject(
        id=SOURCE_BO, name="M5 测试销售行", table_name="df_m5_sales_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING, required=True),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    target = MetaObject(
        id=TARGET_BO, name="M5 测试交货单", table_name="df_m5_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    return source, target


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "db"))
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    monkeypatch.delenv("ENABLED_APPS", raising=False)
    _clear_data_source_cache_for_testing()
    yield
    for bo_id in _REGISTERED_BOS:
        registry._objects.pop(bo_id, None)
    _clear_data_source_cache_for_testing()


@pytest.fixture()
def env(tmp_path):
    app_ds = get_data_source("sqlite", database=str(tmp_path / "biz.db"))
    platform_ds = get_data_source("sqlite", database=str(tmp_path / "platform.db"))
    source, target = _metas()
    registry.register(source)
    registry.register(target)
    invalidate_cache()
    sync_schema_from_meta(app_ds, [source, target])
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    upsert_rules(platform_ds, [
        {"rule_id": RULE_ID, "source_bo": SOURCE_BO, "target_bo": TARGET_BO},
    ])
    with platform_ds.transaction():
        ensure_task_tables(platform_ds)
        ensure_task_event_tables(platform_ds)
        ensure_idempotency_table(platform_ds)
    app_ds.insert("df_m5_sales_lines", {
        "id": 1, "order_no": "SO-M5-1", "quantity": 100.0,
        "unit": "PCS", "status": "open",
    })
    register_all_bo_actions()
    init_doc_flow_service(DocFlowService(app_ds, platform_ds))
    return app_ds, platform_ds


def _publish(ds):
    publish_workflow(
        ds, workflow_key=WF_KEY, name="M5 SO→shipment",
        nodes=[{
            "node_id": NODE_ID, "title": "建单", "step_number": 1,
            "executor_type": "system",
            "executor_assignee": "system",
            "assign_policy": "direct",
            "executor_config": {"action_id": "doc_flow.derive"},
            "meta": {"inputs_template": _INPUTS_TEMPLATE},
        }],
        edges=[],
    )


def _run_params():
    return {
        "rule_id": RULE_ID,
        "sources": [1],
        "target": {"mode": "create", "data": {"delivery_no": "DN-M5-1"}},
    }


def _task_inputs(ds, task_id):
    raw = ds.execute(
        "SELECT inputs FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]
    return json.loads(raw) if raw else None


def _task_outputs(ds, task_id):
    raw = ds.execute(
        "SELECT outputs FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0]
    return json.loads(raw) if raw else None


def _task_executor_config(ds, task_id):
    raw = ds.execute(
        "SELECT executor_config FROM tasks WHERE id = ?",
        (task_id,)).fetchall()[0][0]
    return json.loads(raw) if raw else {}


def _target_count(app_ds):
    return app_ds.execute(
        "SELECT COUNT(*) FROM df_m5_deliveries").fetchall()[0][0]


def _active_edge_ids(app_ds):
    return {row[0] for row in app_ds.execute(
        "SELECT id FROM doc_flow_edges WHERE status = 'active'").fetchall()}


def _edge_status(app_ds, edge_id):
    rows = app_ds.execute(
        "SELECT status FROM doc_flow_edges WHERE id = ?", (edge_id,)).fetchall()
    return rows[0][0] if rows else None


def _start_and_execute_derive(app_ds, platform_ds):
    """建 Run → S2 注入 inputs → 认领 → 执行 doc_flow.derive。"""
    _publish(platform_ds)
    run = start_run(platform_ds, workflow_key=WF_KEY, inputs=_run_params(),
                    doc_ref="SO-M5-1")
    task_id = run["task_ids"][NODE_ID]

    advanced = advance_run(platform_ds, run["run_id"])
    assert task_id in advanced["promoted"]
    assert advanced["blocked_reasons"] == {}
    # S2：整值占位保类型，list/dict 不被字符串化
    assert _task_inputs(platform_ds, task_id) == _run_params()

    claimed = resolve_assignment(platform_ds, task_id)
    assert claimed["status"] == "claimed"

    outcome = BOActionExecutor().start(platform_ds, task_id, run_as="tester")
    assert outcome["status"] == OUTCOME_COMPLETED
    outputs = _task_outputs(platform_ds, task_id)
    assert len(outputs["edge_ids"]) == 1
    return task_id, outputs["edge_ids"]


def _execute_compensation(platform_ds, comp_task_id):
    claimed = resolve_assignment(platform_ds, comp_task_id)
    assert claimed["status"] == "claimed"
    return BOActionExecutor().start(platform_ds, comp_task_id, run_as="tester")


class TestM5Acceptance:

    def test_create_then_cancel_reverses_exactly_once(self, env):
        app_ds, platform_ds = env

        task_id, edge_ids = _start_and_execute_derive(app_ds, platform_ds)
        assert _target_count(app_ds) == 1
        assert _active_edge_ids(app_ds) == set(edge_ids)

        comp = compensate_task(
            platform_ds, task_id, actor="tester", reason="客户取消",
            bo_action={"mode": "cancel"})
        comp_task_id = comp["task_id"]
        assert comp_task_id in comp["promoted"]
        # S3：补偿任务已改写为 doc_flow.reverse，且入参含 edge_ids
        assert _task_executor_config(platform_ds, comp_task_id)["action_id"] \
            == "doc_flow.reverse"
        comp_inputs = _task_inputs(platform_ds, comp_task_id)
        assert comp_inputs["edge_ids"] == edge_ids
        assert comp_inputs["mode"] == "cancel"

        outcome = _execute_compensation(platform_ds, comp_task_id)
        assert outcome["status"] == OUTCOME_COMPLETED
        comp_outputs = _task_outputs(platform_ds, comp_task_id)
        assert comp_outputs["reversed_edge_ids"] == edge_ids
        # 取消不建新的目标单，原边被冲销
        assert _target_count(app_ds) == 1
        assert _active_edge_ids(app_ds) == set()
        for edge_id in edge_ids:
            assert _edge_status(app_ds, edge_id) == "reversed"

    def test_replay_same_compensation_has_no_second_effect(self, env):
        app_ds, platform_ds = env

        task_id, edge_ids = _start_and_execute_derive(app_ds, platform_ds)
        comp = compensate_task(
            platform_ds, task_id, actor="tester", reason="客户取消",
            bo_action={"mode": "cancel"})
        comp_task_id = comp["task_id"]
        _execute_compensation(platform_ds, comp_task_id)

        # 同一补偿任务重放：幂等账返回首次结果，不再执行 Action
        replay = BOActionExecutor().start(platform_ds, comp_task_id, run_as="tester")
        assert replay["replayed"] is True
        assert replay["outputs"]["reversed_edge_ids"] == edge_ids
        assert _target_count(app_ds) == 1
        assert _active_edge_ids(app_ds) == set()

    def test_second_compensation_replays_without_second_reversal(self, env):
        app_ds, platform_ds = env

        task_id, edge_ids = _start_and_execute_derive(app_ds, platform_ds)
        first = compensate_task(
            platform_ds, task_id, actor="tester", reason="客户取消",
            bo_action={"mode": "cancel"})
        _execute_compensation(platform_ds, first["task_id"])

        # 业务侧再次发起补偿（新任务、新幂等键）→ 红字锚 replay，零变更
        second = compensate_task(
            platform_ds, task_id, actor="tester", reason="重复取消",
            bo_action={"mode": "cancel"})
        assert second["task_id"] != first["task_id"]
        outcome = _execute_compensation(platform_ds, second["task_id"])
        assert outcome["status"] == OUTCOME_COMPLETED

        outputs = _task_outputs(platform_ds, second["task_id"])
        assert outputs["reversed_edge_ids"] == []
        assert set(outputs["replayed"]) == set(edge_ids)
        # 只冲销一次：目标单仍为 1，边仍全部 reversed，无新边
        assert _target_count(app_ds) == 1
        assert _active_edge_ids(app_ds) == set()
        for edge_id in edge_ids:
            assert _edge_status(app_ds, edge_id) == "reversed"