# -*- coding: utf-8 -*-
"""S1/S3 接缝：`doc_flow.derive` / `doc_flow.reverse` Action handler 测试。

覆盖 spec §9.3.13:
- derive: 源 id 列表简化形态、target_ids / edge_ids 输出、重复执行 replay
- derive: 服务层错误码透传（success=False）
- reverse: A 档 cancel（含 replay）、C 档 update 红字、追加补偿、B 档 partial
- reverse: none 跳过、缺 ref_id / 未知 mode 的确定性错误
"""
import os

os.environ.setdefault("ALLOW_RAW_SQL", "1")

import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_derive_engine import derive
from meta.core.doc_flow_rule_store import ensure_doc_flow_rule_table, upsert_rules
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType, MetaField, MetaObject, registry
from meta.core.schema_generator import sync_schema_from_meta
from meta.core.table_name_validator import invalidate_cache
from meta.services.doc_flow_action import (
    doc_flow_derive_handler,
    doc_flow_reverse_handler,
)
from meta.services.doc_flow_service import DocFlowService, init_doc_flow_service

SOURCE_BO = "df_act_sales_line"
TARGET_BO = "df_act_delivery"
RULE_ID = "df-act-sales-to-delivery-v1"
RETURN_RULE_ID = "df-act-delivery-to-sales-v1"
_REGISTERED_BOS = (SOURCE_BO, TARGET_BO)


def _field(fid, ftype, **kw):
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _metas():
    source = MetaObject(
        id=SOURCE_BO, name="Action 测试销售行", table_name="df_act_sales_lines",
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
        id=TARGET_BO, name="Action 测试交货单", table_name="df_act_deliveries",
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
    upsert_rules(platform_ds, [
        {"rule_id": RULE_ID, "source_bo": SOURCE_BO, "target_bo": TARGET_BO},
        {"rule_id": RETURN_RULE_ID, "source_bo": TARGET_BO, "target_bo": SOURCE_BO},
    ])
    app_ds.insert("df_act_sales_lines", {
        "id": 1, "order_no": "SO-1", "item_name": "物料A",
        "quantity": 100.0, "unit": "PCS", "status": "open",
    })
    init_doc_flow_service(DocFlowService(app_ds, platform_ds))
    return app_ds, platform_ds


def _fresh_edge(app_ds, platform_ds, quantity=100.0):
    return derive(app_ds, platform_ds, RULE_ID, source_id=1,
                  quantity=quantity, target_data={"delivery_no": "DN-001"},
                  derived_by="tester")


class TestDeriveHandler:

    def test_source_id_list_creates(self, env):
        params = {"rule_id": RULE_ID, "sources": [1],
                  "target": {"mode": "create", "data": {"delivery_no": "DN-1"}}}
        result = doc_flow_derive_handler(params, {"run_as": "wf-run"})
        assert result["success"] is True
        assert len(result["data"]["created"]) == 1
        assert result["data"]["edge_ids"]
        assert result["data"]["target_ids"]

    def test_replayed_entries_are_passed_through(self, env, monkeypatch):
        from meta.services import doc_flow_action

        class _FakeService:
            app_ds = platform_ds = None

            def derive(self, payload, derived_by="", trace_id=""):
                assert payload["rule_id"] == RULE_ID
                assert derived_by == "wf-run"
                return {"target": {"bo": TARGET_BO, "ids": ["t1"]},
                        "created": [],
                        "replayed": [{"edge_id": "e1", "quantity": 10}],
                        "totals": {"requested": 10, "written": 0, "replayed": 1}}

        monkeypatch.setattr(doc_flow_action, "get_doc_flow_service",
                            lambda: _FakeService())
        result = doc_flow_action.doc_flow_derive_handler(
            {"rule_id": RULE_ID, "sources": [1]}, {"run_as": "wf-run"})
        assert result["success"] is True
        assert result["data"]["created"] == []
        assert result["data"]["edge_ids"] == ["e1"]
        assert result["data"]["target_ids"] == ["t1"]

    def test_service_error_is_returned_as_failure(self, env):
        result = doc_flow_derive_handler(
            {"rule_id": "not-exists", "sources": [1]}, {})
        assert result["success"] is False
        assert result["code"] == "DOC_FLOW_RULE_NOT_FOUND"


class TestReverseHandler:

    def test_cancel_reverses_once_and_replays(self, env):
        app_ds, platform_ds = env
        edge = _fresh_edge(app_ds, platform_ds)
        params = {"mode": "cancel", "edge_ids": [edge.edge_id]}

        first = doc_flow_reverse_handler(params, {"run_as": "wf-run"})
        assert first["success"] is True
        assert first["data"]["reversed_edge_ids"] == [edge.edge_id]
        assert first["data"]["replay"] is False

        second = doc_flow_reverse_handler(params, {"run_as": "wf-run"})
        assert second["success"] is True
        assert second["data"]["reversed_edge_ids"] == []
        assert second["data"]["replayed"] == [edge.edge_id]
        assert second["data"]["replay"] is True

    def test_update_creates_red_ink_edge(self, env):
        app_ds, platform_ds = env
        edge = _fresh_edge(app_ds, platform_ds)
        params = {"mode": "update", "edge_ids": [edge.edge_id],
                  "ref_id": "RED-1", "quantity": 30.0}

        result = doc_flow_reverse_handler(params, {})
        assert result["success"] is True
        assert len(result["data"]["created_edge_ids"]) == 1

        replay = doc_flow_reverse_handler(params, {})
        assert replay["success"] is True
        assert replay["data"]["created_edge_ids"] == []
        assert replay["data"]["replayed"]

    def test_partial_creates_counter_edge(self, env):
        app_ds, platform_ds = env
        edge = _fresh_edge(app_ds, platform_ds)
        params = {"mode": "partial", "edge_ids": [edge.edge_id],
                  "ref_id": "RET-1", "quantity": 30.0,
                  "return_rule_id": RETURN_RULE_ID,
                  "target_data": {"order_no": "RET-1", "item_name": "物料A"}}

        result = doc_flow_reverse_handler(params, {})
        assert result["success"] is True, result["message"]
        assert len(result["data"]["created_edge_ids"]) == 1

    def test_partial_requires_ref_id(self, env):
        app_ds, platform_ds = env
        edge = _fresh_edge(app_ds, platform_ds)
        result = doc_flow_reverse_handler(
            {"mode": "partial", "edge_ids": [edge.edge_id],
             "return_rule_id": RETURN_RULE_ID, "quantity": 10}, {})
        assert result["success"] is False
        assert result["code"] == "REF_ID_REQUIRED"

    def test_compensate_appends_reversal_edge(self, env):
        app_ds, platform_ds = env
        edge = _fresh_edge(app_ds, platform_ds)
        params = {"mode": "compensate", "edge_ids": [edge.edge_id],
                  "ref_id": "CMP-1"}

        result = doc_flow_reverse_handler(params, {})
        assert result["success"] is True
        assert len(result["data"]["created_edge_ids"]) == 1

        replay = doc_flow_reverse_handler(params, {})
        assert replay["data"]["created_edge_ids"] == []
        assert replay["data"]["replayed"]

    def test_none_mode_skips(self, env):
        result = doc_flow_reverse_handler({"mode": "none", "edge_ids": ["x"]}, {})
        assert result["success"] is True
        assert result["data"]["skipped"] is True

    def test_unknown_mode_returns_failure(self, env):
        result = doc_flow_reverse_handler({"mode": "explode"}, {})
        assert result["success"] is False
        assert result["code"] == "DOC_FLOW_ACTION_FAILED"