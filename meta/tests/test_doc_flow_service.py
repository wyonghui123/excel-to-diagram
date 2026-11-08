# -*- coding: utf-8 -*-
"""[单据流 Phase 3] 服务层测试（spec 2026-11-08-doc-flow-service-spec.md §6/§8）。

覆盖：规则元数据下发 / 未结量查询 / 派生校验 / 追溯查询 / 幂等状态过滤。
测试入口：python d:\filework\test.py --file meta/tests/test_doc_flow_service.py
"""
import pytest

from meta.core.datasource import (
    _clear_data_source_cache_for_testing, get_data_source,
)
from meta.core.doc_flow_rule_store import (
    ensure_doc_flow_rule_table, get_rule, set_rule_status, upsert_rules,
)
from meta.core.doc_flow_schema import ensure_doc_flow_edge_tables
from meta.core.models import FieldType
from meta.core.models_annotations import SemanticAnnotation

SOURCE_BO = "dfs_order_line"
HEAD_BO = "dfs_delivery"
LINE_BO = "dfs_delivery_line"

_REGISTERED_BOS = (SOURCE_BO, HEAD_BO, LINE_BO)


def _field(fid, ftype, **kw):
    from meta.core.models import MetaField
    return MetaField(id=fid, name=fid, field_type=ftype, db_column=fid, **kw)


def _demo_metas():
    from meta.core.models import MetaObject

    source = MetaObject(
        id=SOURCE_BO, name="测试订单行", table_name="dfs_order_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("order_no", FieldType.STRING),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT, required=True),
            _field("unit", FieldType.STRING),
            _field("status", FieldType.STRING, default="open"),
        ],
    )
    head = MetaObject(
        id=HEAD_BO, name="测试交货单头", table_name="dfs_deliveries",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_no", FieldType.STRING),
            _field("order_no", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
            _field("created_at", FieldType.DATETIME),
        ],
    )
    line = MetaObject(
        id=LINE_BO, name="测试交货行", table_name="dfs_delivery_lines",
        fields=[
            _field("id", FieldType.INTEGER, required=True, unique=True),
            _field("delivery_id", FieldType.INTEGER,
                   semantics=SemanticAnnotation(parent_key=True)),
            _field("item_name", FieldType.STRING),
            _field("quantity", FieldType.FLOAT),
            _field("unit", FieldType.STRING),
        ],
    )
    return source, head, line


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DB_DIR", str(tmp_path / "db"))
    monkeypatch.delenv("APP_DB_ROUTING", raising=False)
    monkeypatch.delenv("ENABLED_APPS", raising=False)
    _clear_data_source_cache_for_testing()
    yield
    from meta.core.models import registry
    for bo_id in _REGISTERED_BOS:
        registry._objects.pop(bo_id, None)
    _clear_data_source_cache_for_testing()


@pytest.fixture
def dbs(tmp_path):
    app_ds = get_data_source("sqlite", database=str(tmp_path / "biz.db"))
    platform_ds = get_data_source("sqlite", database=str(tmp_path / "platform.db"))
    return app_ds, platform_ds


@pytest.fixture
def ready_env(dbs):
    app_ds, platform_ds = dbs
    from meta.core.models import registry
    from meta.core.schema_generator import sync_schema_from_meta
    from meta.core.table_name_validator import invalidate_cache

    metas = _demo_metas()
    for m in metas:
        registry.register(m)
    invalidate_cache()
    sync_schema_from_meta(app_ds, list(metas))
    ensure_doc_flow_edge_tables(app_ds)
    ensure_doc_flow_rule_table(platform_ds)
    return app_ds, platform_ds


def _make_rule(platform_ds, rule_id="dfs-rule", **overrides):
    rule = {
        "rule_id": rule_id,
        "source_bo": SOURCE_BO,
        "target_bo": HEAD_BO,
        "source_qty_field": "quantity",
    }
    rule.update(overrides)
    upsert_rules(platform_ds, [rule])
    return rule_id


def _insert_source(app_ds, row_id, quantity=100):
    app_ds.insert("dfs_order_lines", {
        "id": row_id, "order_no": "SO-{0}".format(row_id),
        "item_name": "物料A", "quantity": quantity,
        "unit": "PCS", "status": "open",
    })


def test_rule_declares_display_fields(ready_env):
    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, display_fields=["order_no", "item_name"])

    rule = get_rule(platform_ds, "dfs-rule")

    assert rule["display_fields"] == ["order_no", "item_name"]


def test_reversed_edge_does_not_block_rederive(ready_env):
    from meta.core.doc_flow_batch_engine import derive_batch
    from meta.core.doc_flow_reversal import reverse_edge

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    head_id = app_ds.insert("dfs_deliveries", {"delivery_no": "DN-1"})

    first = derive_batch(app_ds, platform_ds, "dfs-rule",
                         [{"source_id": 1, "source_item": "", "quantity": 100}],
                         head_overrides={"id": head_id})
    assert first.total_edges == 1
    reverse_edge(app_ds, first.results[0].edge_id, reversed_by="test")

    second = derive_batch(app_ds, platform_ds, "dfs-rule",
                          [{"source_id": 1, "source_item": "", "quantity": 100}],
                          head_overrides={"id": head_id})

    assert second.total_edges == 1
    assert second.skipped_replays == 0


def test_derive_result_carries_source_identity(ready_env):
    from meta.core.doc_flow_batch_engine import derive_batch

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 30)

    batch = derive_batch(app_ds, platform_ds, "dfs-rule",
                         [{"source_id": 1, "source_item": "", "quantity": 30}])

    result = batch.results[0]
    assert result.source_id == 1
    assert result.source_item == ""
    assert result.quantity == 30.0
    assert result.target_item


def test_list_rules_returns_ui_metadata(ready_env):
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, display_fields=["order_no", "item_name"])
    _make_rule(platform_ds, rule_id="dfs-deprecated")
    set_rule_status(platform_ds, "dfs-deprecated", "deprecated")

    service = DocFlowService(app_ds, platform_ds)
    data = service.list_rules(source_bo=SOURCE_BO)

    assert data["total"] == 1
    rule = data["rules"][0]
    assert rule["rule_id"] == "dfs-rule"
    assert rule["source_columns"] == [
        {"field": "order_no", "label": "order_no"},
        {"field": "item_name", "label": "item_name"},
    ]
    assert rule["allow_append"] is False
    assert rule["append_label"] == ""


def test_list_sources_computes_open_qty(ready_env):
    from meta.core.doc_flow_batch_engine import derive_batch
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO,
               display_fields=["order_no", "item_name"])
    _insert_source(app_ds, 1, 100)
    _insert_source(app_ds, 2, 50)
    derive_batch(app_ds, platform_ds, "dfs-rule",
                 [{"source_id": 1, "source_item": "", "quantity": 60}])

    service = DocFlowService(app_ds, platform_ds)
    data = service.list_sources("dfs-rule")

    assert data["total"] == 2
    row = [r for r in data["items"] if r["source_id"] == 1][0]
    assert row["quantity"] == 100.0
    assert row["consumed_qty"] == 60.0
    assert row["open_qty"] == 40.0
    assert row["display"] == "SO-1 / 物料A"


def _edge_count(app_ds):
    rows = app_ds.execute("SELECT COUNT(*) FROM doc_flow_edges").fetchall()
    return int(rows[0][0])


def test_derive_create_returns_target_and_totals(ready_env):
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    data = service.derive({
        "rule_id": "dfs-rule",
        "sources": [{"source_id": 1, "quantity": 30}],
        "target": {"mode": "create", "bo": HEAD_BO},
    }, derived_by="tester")

    assert len(data["target"]["ids"]) == 1
    assert data["totals"] == {"requested": 1, "written": 1, "replayed": 0}
    assert data["created"][0]["source_id"] == 1
    assert data["created"][0]["quantity"] == 30.0
    assert _edge_count(app_ds) == 1


def test_derive_quantity_exceeded(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({
            "rule_id": "dfs-rule",
            "sources": [{"source_id": 1, "quantity": 120}],
            "target": {"mode": "create"},
        })

    assert exc.value.code == "DOC_FLOW_QTY_EXCEEDED"
    assert exc.value.status == 409
    assert exc.value.details["open_qty"] == 100.0
    assert _edge_count(app_ds) == 0


def test_derive_invalid_quantity_and_duplicate_source(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({"rule_id": "dfs-rule",
                        "sources": [{"source_id": 1, "quantity": 0}],
                        "target": {"mode": "create"}})
    assert exc.value.code == "DOC_FLOW_QTY_INVALID"

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({"rule_id": "dfs-rule",
                        "sources": [{"source_id": 1}, {"source_id": 1}],
                        "target": {"mode": "create"}})
    assert exc.value.code == "DOC_FLOW_DUPLICATE_SOURCE"


def test_derive_single_table_append_rejected(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds)  # 单表模式：无 target_line_bo
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.derive({"rule_id": "dfs-rule",
                        "sources": [{"source_id": 1, "quantity": 10}],
                        "target": {"mode": "append", "id": 99}})
    assert exc.value.code == "DOC_FLOW_TARGET_MODE_INVALID"


def test_list_edges_both_directions(ready_env):
    from meta.services.doc_flow_service import DocFlowService

    app_ds, platform_ds = ready_env
    _make_rule(platform_ds, target_line_bo=LINE_BO)
    _insert_source(app_ds, 1, 100)
    service = DocFlowService(app_ds, platform_ds)

    head_id = service.derive({
        "rule_id": "dfs-rule",
        "sources": [{"source_id": 1, "quantity": 20}],
        "target": {"mode": "create"},
    })["target"]["ids"][0]

    by_source = service.list_edges(source_bo=SOURCE_BO, source_id=1)
    by_target = service.list_edges(target_bo=HEAD_BO, target_id=head_id)

    assert by_source["total"] == 1
    assert by_target["total"] == 1
    assert by_source["items"][0]["status"] == "active"
    assert by_source["items"][0]["quantity"] == 20.0


def test_list_edges_requires_filter(ready_env):
    from meta.services.doc_flow_service import DocFlowService, DocFlowServiceError

    app_ds, platform_ds = ready_env
    service = DocFlowService(app_ds, platform_ds)

    with pytest.raises(DocFlowServiceError) as exc:
        service.list_edges()

    assert exc.value.code == "DOC_FLOW_EDGE_FILTER_REQUIRED"