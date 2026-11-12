# -*- coding: utf-8 -*-
"""S5 接缝：两域 trace 分工与关联（spec §9.3.13 S5）。

覆盖:
- `doc_flow` trace 信封零变化：不含 workflow / run / task 字段
- `task.outputs.edge_ids` 与实际边表一致（不修改边表 17 列）
- 按 `tasks.doc_ref` 可反查任务
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
from meta.core.rule_trace_service import RuleTraceService
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.table_name_validator import invalidate_cache
from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_idempotency import ensure_idempotency_table
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_engine import start_run
from meta.core.workflow_store import publish_workflow
from meta.services.bo_action_registrations import register_all_bo_actions
from meta.services.doc_flow_service import DocFlowService, init_doc_flow_service

SOURCE_BO = "df_s5_sales_line"
TARGET_BO = "df_s5_delivery"
RULE_ID = "df-s5-sales-to-delivery-v1"
WF_KEY = "wf-s5-trace"
_REGISTERED_BOS = (SOURCE_BO, TARGET_BO)

#: 编排域字段不得出现在 doc_flow 信封（两域各查各的）
_FORBIDDEN_KEYS = {
    "workflow_run_id", "workflow_key", "workflow_version",
    "run_id", "task_id", "task_status", "run_status",
}


def _field(fid, ftype, **kw):
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _metas():
    source = MetaObject(
        id=SOURCE_BO, name="S5 测试销售行", table_name="df_s5_sales_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING, required=True),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    target = MetaObject(
        id=TARGET_BO, name="S5 测试交货单", table_name="df_s5_deliveries",
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
    app_ds.insert("df_s5_sales_lines", {
        "id": 1, "order_no": "SO-S5-1", "quantity": 100.0,
        "unit": "PCS", "status": "open",
    })
    register_all_bo_actions()
    init_doc_flow_service(DocFlowService(app_ds, platform_ds))
    return app_ds, platform_ds


def _collect_keys(value, found):
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _collect_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_keys(item, found)


def _publish(ds):
    publish_workflow(
        ds, workflow_key=WF_KEY, name="S5 单据流",
        nodes=[{"node_id": "n1", "title": "建单", "step_number": 1,
                "executor_type": "system",
                "executor_config": {"action_id": "doc_flow.derive"}}],
        edges=[],
    )


class TestTraceDivision:

    def test_doc_flow_envelope_has_no_workflow_fields(self, env):
        _, platform_ds = env

        trace = RuleTraceService().build(
            SOURCE_BO,
            data={"id": 1, "order_no": "SO-S5-1", "status": "open"},
            scenarios=["doc_flow"], data_source=platform_ds)

        envelope = trace["scenarios"][0]
        assert envelope["decision"] == "declared"
        found = set()
        _collect_keys(envelope, found)
        assert found & _FORBIDDEN_KEYS == set()

    def test_task_outputs_edge_ids_match_edge_table(self, env):
        app_ds, platform_ds = env
        _publish(platform_ds)
        run = start_run(platform_ds, workflow_key=WF_KEY, doc_ref="SO-S5-1")
        task_id = run["task_ids"]["n1"]
        params = {"rule_id": RULE_ID, "sources": [1],
                  "target": {"mode": "create",
                             "data": {"delivery_no": "DN-S5"}}}
        platform_ds.update("tasks", task_id, {
            "status": "claimed", "inputs": json.dumps(params),
        })

        outcome = BOActionExecutor().start(platform_ds, task_id, run_as="tester")

        assert outcome["status"] == OUTCOME_COMPLETED
        assert outcome["task_status"] == "done"
        outputs = json.loads(platform_ds.execute(
            "SELECT outputs FROM tasks WHERE id = ?", (task_id,)).fetchall()[0][0])
        edge_ids = outputs["edge_ids"]
        edge_rows = app_ds.execute(
            "SELECT id FROM doc_flow_edges WHERE status = 'active'").fetchall()
        assert edge_ids
        assert set(edge_ids) == {row[0] for row in edge_rows}

    def test_tasks_queryable_by_doc_ref(self, env):
        _, platform_ds = env
        _publish(platform_ds)
        run = start_run(platform_ds, workflow_key=WF_KEY, doc_ref="SO-S5-1")

        rows = platform_ds.execute(
            "SELECT id FROM tasks WHERE doc_ref = ?", ("SO-S5-1",)).fetchall()

        assert run["task_ids"]["n1"] in {row[0] for row in rows}
