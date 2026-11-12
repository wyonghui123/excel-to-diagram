# -*- coding: utf-8 -*-
"""[2026-11-12] 聚合根派生 + 头→行追溯服务测试。

覆盖 spec-doc-flow-header-trace-2026-11-12 §3.4（聚合根判定边界）
与 §4.2~§4.3（头→行展开、聚合键、正数减红字、撤销边不计数量）。
测试入口：python d:\filework\test.py --file meta/tests/test_doc_flow_trace.py
"""
import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing,
    get_data_source,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType, MetaObject
from meta.core.models_annotations import SemanticAnnotation
from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

HEAD_BO = "tft_invoice"
LINE_BO = "tft_invoice_line"
ORPHAN_LINE_BO = "tft_link"
CORE_BO = "tft_core_org"
CUSTOMER_BO = "tft_customer"
ARCH_BO = "tft_arch_node"
CYCLE_A_BO = "tft_cycle_a"
CYCLE_B_BO = "tft_cycle_b"

_REGISTERED_BOS = (
    HEAD_BO, LINE_BO, ORPHAN_LINE_BO, CORE_BO, CUSTOMER_BO,
    ARCH_BO, CYCLE_A_BO, CYCLE_B_BO,
)


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    head = MetaObject(
        id=HEAD_BO, name="追溯单据头", table_name="tft_invoices",
        semantics=SemanticAnnotation(category="business_document"),
        fields=[
            _field("id", FieldType.STRING, required=True, unique=True),
            _field("invoice_no", FieldType.STRING),
        ],
    )
    line = MetaObject(
        id=LINE_BO, name="追溯单据行", table_name="tft_invoice_lines",
        parent_object=HEAD_BO,
        hierarchy={"parent_field": "invoice_id"},
        semantics=SemanticAnnotation(category="business_document_line"),
        fields=[
            _field("id", FieldType.STRING, required=True, unique=True),
            _field("invoice_id", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
        ],
    )
    orphan_line = MetaObject(
        id=ORPHAN_LINE_BO, name="无父行级对象", table_name="tft_links",
        semantics=SemanticAnnotation(category="business_document_line"),
        fields=[_field("id", FieldType.STRING, required=True, unique=True)],
    )
    core = MetaObject(
        id=CORE_BO, name="主数据父", table_name="tft_core_orgs",
        semantics=SemanticAnnotation(category="core_entity"),
        fields=[_field("id", FieldType.STRING, required=True, unique=True)],
    )
    customer = MetaObject(
        id=CUSTOMER_BO, name="主数据子", table_name="tft_customers",
        parent_object=CORE_BO,
        semantics=SemanticAnnotation(category="core_entity"),
        fields=[_field("id", FieldType.STRING, required=True, unique=True)],
    )
    arch = MetaObject(
        id=ARCH_BO, name="架构节点", table_name="tft_arch_nodes",
        parent_object="tft_service_module",
        semantics=SemanticAnnotation(category="architecture"),
        fields=[_field("id", FieldType.STRING, required=True, unique=True)],
    )
    cycle_a = MetaObject(
        id=CYCLE_A_BO, name="环A", table_name="tft_cycle_a",
        parent_object=CYCLE_B_BO,
        semantics=SemanticAnnotation(category="business_document"),
        fields=[_field("id", FieldType.STRING, required=True, unique=True)],
    )
    cycle_b = MetaObject(
        id=CYCLE_B_BO, name="环B", table_name="tft_cycle_b",
        parent_object=CYCLE_A_BO,
        semantics=SemanticAnnotation(category="business_document"),
        fields=[_field("id", FieldType.STRING, required=True, unique=True)],
    )
    return [head, line, orphan_line, core, customer, arch, cycle_a, cycle_b]


@pytest.fixture()
def metas(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "db"))
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    monkeypatch.delenv("ENABLED_APPS", raising=False)
    _clear_data_source_cache_for_testing()
    from meta.core.models import registry
    demo = _demo_metas()
    for obj in demo:
        registry.register(obj)
    yield demo
    for bo_id in _REGISTERED_BOS:
        registry._objects.pop(bo_id, None)
    _clear_data_source_cache_for_testing()


@pytest.fixture()
def service(metas, tmp_path):
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import invalidate_cache

    app_ds = get_data_source("sqlite", database=str(tmp_path / "biz.db"))
    platform_ds = get_data_source("sqlite", database=str(tmp_path / "platform.db"))
    invalidate_cache()
    sync_schema_from_meta(app_ds, [metas[0], metas[1], metas[2]])
    ensure_doc_flow_edge_tables(app_ds)
    return DocFlowService(app_ds, platform_ds)


# ---------------------------------------------------------------- 聚合根边界

def test_line_resolves_to_head(metas):
    line = metas[1]
    assert line.get_aggregate_root().id == HEAD_BO
    assert line.get_aggregate_parent_field() == "invoice_id"


def test_head_is_its_own_root(metas):
    head = metas[0]
    assert head.get_aggregate_root().id == HEAD_BO
    assert [child.id for child in head.get_aggregate_children()] == [LINE_BO]


def test_orphan_line_has_no_root(metas):
    assert metas[2].get_aggregate_root() is None


def test_core_entity_has_no_root(metas):
    assert metas[4].get_aggregate_root() is None


def test_architecture_node_has_no_root(metas):
    assert metas[5].get_aggregate_root() is None


def test_cycle_returns_none(metas):
    assert metas[6].get_aggregate_root() is None


def test_parent_field_falls_back_to_parent_id():
    obj = MetaObject(
        id="tft_fallback", name="回落", table_name="tft_fallback",
        parent_object="tft_some_head",
    )
    assert obj.get_aggregate_parent_field() == "tft_some_head_id"


# ---------------------------------------------------------------- 头→行追溯

def _seed_invoice(app_ds):
    app_ds.insert("tft_invoices", {"id": "VI-1", "invoice_no": "INV-1"})
    for line_id in ("L1", "L2", "L3"):
        app_ds.insert("tft_invoice_lines", {
            "id": line_id, "invoice_id": "VI-1", "quantity": 10,
        })


def _edge(edge_id, source_bo, source_id, target_bo, target_id,
          quantity, rule_id="r1", sign="normal", status="active"):
    return {
        "id": edge_id,
        "source_bo": source_bo, "source_id": source_id, "source_item": "",
        "target_bo": target_bo, "target_id": target_id, "target_item": "",
        "quantity": quantity, "quantity_sign": sign, "status": status,
        "rule_id": rule_id, "pool": "default", "edge_kind": "normal",
        "unit": "EA", "derived_at": "2026-11-12T10:00:00",
    }


def test_trace_expands_head_to_lines(service):
    app_ds = service.app_ds
    _seed_invoice(app_ds)
    # 上游：同一对端两行正常 + 一条红字
    app_ds.insert("doc_flow_edges", _edge("e1", "po_line", "PO-1", LINE_BO, "L1", 5))
    app_ds.insert("doc_flow_edges", _edge("e2", "po_line", "PO-1", LINE_BO, "L2", 7))
    app_ds.insert("doc_flow_edges", _edge(
        "e3", "po_line", "PO-1", LINE_BO, "L3", 2, sign="red"))
    # 下游：一条正常 + 一条已撤销
    app_ds.insert("doc_flow_edges", _edge("e4", LINE_BO, "L1", "so_line", "SO-1", 10))
    app_ds.insert("doc_flow_edges", _edge(
        "e5", LINE_BO, "L2", "so_line", "SO-1", 10, status="reversed"))

    data = service.trace_records(HEAD_BO, "VI-1")

    assert data["expanded"] is True
    assert data["line_scope"]["count"] == 3
    assert data["root_object"] == HEAD_BO
    assert data["root_id"] == "VI-1"

    upstream = data["upstream"]["items"]
    assert len(upstream) == 1
    assert upstream[0]["peer_id"] == "PO-1"
    assert upstream[0]["quantity"] == 10.0
    assert upstream[0]["edge_count"] == 3
    assert upstream[0]["raw_count"] == 3

    downstream = data["downstream"]["items"]
    assert len(downstream) == 1
    assert downstream[0]["peer_id"] == "SO-1"
    assert downstream[0]["quantity"] == 10.0
    assert downstream[0]["edge_count"] == 1
    assert downstream[0]["raw_count"] == 2


def test_trace_line_id_normalizes_to_head(service):
    _seed_invoice(service.app_ds)
    service.app_ds.insert("doc_flow_edges", _edge(
        "e1", "po_line", "PO-1", LINE_BO, "L1", 5))

    by_head = service.trace_records(HEAD_BO, "VI-1")
    by_line = service.trace_records(LINE_BO, "L1")

    assert by_line["root_id"] == by_head["root_id"] == "VI-1"
    assert by_line["upstream"] == by_head["upstream"]
    assert by_line["downstream"] == by_head["downstream"]


def test_trace_without_lines_is_not_error(service):
    service.app_ds.insert("tft_invoices", {"id": "VI-2", "invoice_no": "INV-2"})
    data = service.trace_records(HEAD_BO, "VI-2")
    assert data["expanded"] is False
    assert data["upstream"]["items"] == []
    assert data["line_scope"]["count"] == 0


def test_trace_unknown_bo_raises(service):
    with pytest.raises(DocFlowServiceError) as exc:
        service.trace_records("tft_not_exists", "X")
    assert exc.value.code == "DOC_FLOW_BO_NOT_FOUND"


# ---------------------------------------------------------------- 真实 schema

def test_real_vendor_invoice_line_resolves_to_head():
    from meta.core.models import registry
    line = registry.get("vendor_invoice_line")
    if line is None:
        pytest.skip("registry 未加载真实 schema")
    assert line.get_aggregate_root().id == "vendor_invoice"
    assert line.get_aggregate_parent_field() == "invoice_id"