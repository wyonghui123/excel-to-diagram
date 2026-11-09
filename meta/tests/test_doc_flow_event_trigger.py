# -*- coding: utf-8 -*-
"""S4 接缝：`doc_flow.created` 事件 → Workflow Run 接线测试。

覆盖 spec §9.3.13 S4:
- 事件命中：payload 成为 Run inputs，`doc_ref` 取自 `target_id`
- when 不命中：不起 Run
- 幂等：同一 trace_id 重复事件不重复起 Run
- 触发异常不阻断 derive（业务事务已提交）
"""
import os

os.environ.setdefault("ALLOW_RAW_SQL", "1")

import json

import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_rule_store import ensure_doc_flow_rule_table, upsert_rules
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.table_name_validator import invalidate_cache
from meta.core.task_event_schema import ensure_task_event_tables
from meta.core.task_schema import ensure_task_tables
from meta.core.workflow_store import publish_workflow
from meta.services.doc_flow_service import DocFlowService, init_doc_flow_service

SOURCE_BO = "df_evt_sales_line"
TARGET_BO = "df_evt_delivery"
RULE_ID = "df-evt-sales-to-delivery-v1"
WORKFLOW_KEY = "wf-doc-flow-created"
_REGISTERED_BOS = (SOURCE_BO, TARGET_BO)


def _field(fid, ftype, **kw):
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _metas():
    source = MetaObject(
        id=SOURCE_BO, name="事件触发测试销售行", table_name="df_evt_sales_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING, required=True),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    target = MetaObject(
        id=TARGET_BO, name="事件触发测试交货单", table_name="df_evt_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING),
            _field("item_name", FieldType.STRING),
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
    with platform_ds.transaction():
        ensure_task_tables(platform_ds)
        ensure_task_event_tables(platform_ds)
    upsert_rules(platform_ds, [
        {"rule_id": RULE_ID, "source_bo": SOURCE_BO, "target_bo": TARGET_BO},
    ])
    app_ds.insert("df_evt_sales_lines", {
        "id": 1, "order_no": "SO-EVT-1", "item_name": "物料A",
        "quantity": 100.0, "unit": "PCS", "status": "open",
    })
    init_doc_flow_service(DocFlowService(app_ds, platform_ds))
    return app_ds, platform_ds


def _publish(platform_ds, when="target_bo == 'df_evt_delivery'"):
    return publish_workflow(
        platform_ds, workflow_key=WORKFLOW_KEY, name="单据流触发",
        nodes=[{"node_id": "n1", "title": "处理下游单据",
                "executor_type": "human", "step_number": 1}],
        trigger_kind="event",
        trigger_expr=json.dumps({
            "event": "doc_flow.created", "when": when, "doc_ref": "target_id",
        }),
    )


def _derive(trace_id, quantity=10.0):
    from meta.services.doc_flow_service import get_doc_flow_service
    return get_doc_flow_service().derive(
        {"rule_id": RULE_ID,
         "sources": [{"source_id": 1, "quantity": quantity}],
         "target": {"mode": "create", "data": {"delivery_no": "DN-EVT"}}},
        derived_by="tester", trace_id=trace_id)


def _runs(platform_ds):
    rows = platform_ds.execute(
        "SELECT id, trigger_kind, inputs, meta, idempotency_key"
        " FROM workflow_runs ORDER BY created_at").fetchall()
    return [{"run_id": row[0], "trigger_kind": row[1],
             "inputs": json.loads(row[2]) if row[2] else None,
             "meta": json.loads(row[3]) if row[3] else {},
             "idempotency_key": row[4]} for row in rows]


class TestDocFlowCreatedTrigger:

    def test_event_starts_run_with_inputs_and_doc_ref(self, env):
        _, platform_ds = env
        _publish(platform_ds)

        view = _derive("trace-evt-1")

        runs = _runs(platform_ds)
        assert len(runs) == 1
        run = runs[0]
        assert run["trigger_kind"] == "event"
        assert run["inputs"]["rule_id"] == RULE_ID
        assert run["inputs"]["source_bo"] == SOURCE_BO
        assert run["inputs"]["target_bo"] == TARGET_BO
        assert run["inputs"]["target_id"] == view["target"]["ids"][0]
        assert run["inputs"]["row_count"] == 1
        assert run["inputs"]["trace_id"] == "trace-evt-1"
        assert run["meta"]["doc_ref"] == str(view["target"]["ids"][0])
        assert run["idempotency_key"] == (
            "doc_flow.created:trace-evt-1:{0}".format(WORKFLOW_KEY))

    def test_when_not_matched_starts_nothing(self, env):
        _, platform_ds = env
        _publish(platform_ds, when="target_bo == 'other_bo'")

        _derive("trace-evt-2")

        assert _runs(platform_ds) == []

    def test_duplicate_event_does_not_start_second_run(self, env):
        _, platform_ds = env
        _publish(platform_ds)

        _derive("trace-evt-3", quantity=10.0)
        _derive("trace-evt-3", quantity=10.0)

        runs = _runs(platform_ds)
        assert len(runs) == 1
        assert runs[0]["inputs"]["trace_id"] == "trace-evt-3"

    def test_trigger_failure_does_not_block_derive(self, env, monkeypatch):
        from meta.core import workflow_trigger

        _, platform_ds = env
        _publish(platform_ds)

        def boom(*args, **kwargs):
            raise RuntimeError("trigger down")

        monkeypatch.setattr(workflow_trigger, "start_runs_for_event", boom)

        view = _derive("trace-evt-4")
        assert len(view["created"]) == 1
        assert _runs(platform_ds) == []
