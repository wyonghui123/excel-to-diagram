# -*- coding: utf-8 -*-
"""[S7.1 2026-11-06] 事实单据六件套声明（document: 段）解析与校验测试。

纯元数据层，不依赖 DB：
  · 合法声明可解析为 MetaDocumentProfile；
  · 未声明 ⇒ None（零影响）；
  · number_field / posting_state / snapshot_fields 校验 fail-fast；
  · 跨对象 line_object 校验；
  · purchase_order.yaml 试点声明可解析。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core.yaml_loader import (  # noqa: E402
    load_yaml_file,
    parse_aspects_yaml,
    parse_meta_object,
    parse_shared_properties,
    validate_document_profiles,
)


def _base(**overrides):
    data = {
        "id": "doc_po_test",
        "name": "单据测试",
        "table_name": "doc_po_test",
        "fields": [
            {"id": "order_no", "name": "单号", "type": "string"},
            {"id": "order_date", "name": "单据日期", "type": "date"},
            {"id": "status", "name": "状态", "type": "string"},
            {"id": "document_type_id", "name": "单据类型", "type": "integer"},
            {"id": "amount", "name": "金额", "type": "number"},
        ],
        "rules": [{
            "id": "doc_confirm", "name": "确认", "type": "state_transition",
            "state_field": "status", "from_states": ["draft"], "to_state": "confirmed",
        }],
        "states": [
            {"code": "draft", "label": "草稿", "category": "initial"},
            {"code": "confirmed", "label": "已确认"},
        ],
    }
    data.update(overrides)
    return data


def test_parse_valid_document_profile():
    obj = parse_meta_object(_base(document={
        "number_field": "order_no",
        "business_date_field": "order_date",
        "state_field": "status",
        "posting_state": "confirmed",
        "document_type_field": "document_type_id",
        "snapshot_fields": ["order_no", "amount"],
    }))
    profile = obj.document_profile
    assert profile is not None
    assert profile.number_field == "order_no"
    assert profile.business_date_field == "order_date"
    assert profile.state_field == "status"
    assert profile.posting_state == "confirmed"
    assert profile.document_type_field == "document_type_id"
    assert profile.snapshot_fields == ["order_no", "amount"]


def test_no_document_section_returns_none():
    obj = parse_meta_object(_base())
    assert obj.document_profile is None


def test_unknown_number_field_fails_fast():
    with pytest.raises(ValueError, match=r"\[S7\].*number_field"):
        parse_meta_object(_base(document={"number_field": "ghost_no"}))


def test_posting_state_without_states_fails_fast():
    data = _base(document={"posting_state": "confirmed"})
    data.pop("states")
    data["rules"] = []
    with pytest.raises(ValueError, match=r"\[S7\].*未声明 states"):
        parse_meta_object(data)


def test_posting_state_outside_catalog_fails_fast():
    with pytest.raises(ValueError, match=r"\[S7\].*不在 states 中"):
        parse_meta_object(_base(document={"posting_state": "ghost_state"}))


def test_unknown_snapshot_field_fails_fast():
    obj = parse_meta_object(_base(document={"snapshot_fields": ["ghost_field"]}))
    with pytest.raises(ValueError, match=r"\[S7\].*snapshot_fields"):
        validate_document_profiles([obj])


def test_line_object_must_exist():
    parent = parse_meta_object(_base(document={
        "line_object": "ghost_line",
        "line_parent_field": "order_id",
    }))
    with pytest.raises(ValueError, match=r"\[S7\].*line_object"):
        validate_document_profiles([parent])


def test_line_parent_field_must_exist_on_child():
    parent = parse_meta_object(_base(document={
        "line_object": "doc_po_line",
        "line_parent_field": "ghost_parent",
    }))
    child = parse_meta_object({
        "id": "doc_po_line",
        "name": "单据行",
        "table_name": "doc_po_line",
        "fields": [
            {"id": "order_id", "name": "父单", "type": "integer"},
            {"id": "line_no", "name": "行号", "type": "integer"},
        ],
    })
    with pytest.raises(ValueError, match=r"\[S7\].*line_parent_field"):
        validate_document_profiles([parent, child])


def test_line_object_resolves_when_loaded():
    parent = parse_meta_object(_base(document={
        "line_object": "doc_po_line",
        "line_parent_field": "order_id",
        "line_sequence_field": "line_no",
    }))
    child = parse_meta_object({
        "id": "doc_po_line",
        "name": "单据行",
        "table_name": "doc_po_line",
        "fields": [
            {"id": "order_id", "name": "父单", "type": "integer"},
            {"id": "line_no", "name": "行号", "type": "integer"},
        ],
    })
    validate_document_profiles([parent, child])


def test_purchase_order_pilot_declared():
    """试点对象 purchase_order 的真实 document: 声明可解析。

    document_type_id 由 document_type_aspect 提供，故走 load_yaml_file（含切面合并）。
    """
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    path = schema_dir / "purchase_order.yaml"
    obj = load_yaml_file(
        str(path),
        shared_props=parse_shared_properties(str(schema_dir)),
        aspects_defs=parse_aspects_yaml(str(schema_dir)),
    )

    profile = obj.document_profile
    assert profile is not None
    assert profile.number_field == "order_no"
    assert profile.business_date_field == "order_date"
    assert profile.state_field == "status"
    assert profile.posting_state == "confirmed"
    assert profile.document_type_field == "document_type_id"
    assert profile.line_object == "purchase_order_line"
    assert profile.line_parent_field == "order_id"
    assert profile.line_sequence_field == "line_no"
    assert "exchange_rate" in profile.snapshot_fields


@pytest.mark.parametrize("object_file, expected_number", [
    ("sales_order.yaml", "order_no"),
    ("receipt.yaml", "receipt_no"),
    ("work_order.yaml", "work_order_no"),
])
def test_other_documents_declared(object_file, expected_number):
    """T8.5 抽查：其余事实单据的 document: 声明可正常加载。"""
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    obj = load_yaml_file(
        str(schema_dir / object_file),
        shared_props=parse_shared_properties(str(schema_dir)),
        aspects_defs=parse_aspects_yaml(str(schema_dir)),
    )
    assert obj.document_profile is not None
    assert obj.document_profile.number_field == expected_number
    assert obj.document_profile.state_field == "status"


# ── [P1 2026-11-06] 取号绑定元数据化（document.numbering） ──────────────

def test_numbering_block_parsed():
    obj = parse_meta_object(_base(document={
        "number_field": "order_no",
        "business_date_field": "order_date",
        "numbering": {"scope_bo": "doc_po_test", "fallback_sequence_code": "TST"},
    }))
    assert obj.document_profile.numbering == {
        "scope_bo": "doc_po_test", "fallback_sequence_code": "TST"}


def test_numbering_must_be_mapping():
    with pytest.raises(ValueError) as exc:
        parse_meta_object(_base(document={
            "number_field": "order_no",
            "business_date_field": "order_date",
            "numbering": "TST",
        }))
    assert "numbering 必须是映射" in str(exc.value)


def test_transfer_shipment_declares_scope_numbering():
    """调拨发货单无 document_type 维度，靠 scope_bo + 序列 code 兜底。"""
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    obj = load_yaml_file(
        str(schema_dir / "transfer_shipment.yaml"),
        shared_props=parse_shared_properties(str(schema_dir)),
        aspects_defs=parse_aspects_yaml(str(schema_dir)),
    )
    profile = obj.document_profile
    assert profile.number_field == "shipment_no"
    assert profile.numbering.get("scope_bo") == "transfer_shipment"
    assert profile.numbering.get("fallback_sequence_code") == "TRS"


def _register(meta_object):
    from meta.core.models import registry
    registry.register(meta_object)
    return meta_object


def test_resolve_numbering_prefers_metadata():
    from meta.core.models import MetaDocumentProfile, MetaObject
    from meta.services.document_number_service import resolve_document_numbering

    obj = _register(MetaObject(
        id="p1_doc_scope", name="P1单据", table_name="p1_doc_scope",
        document_profile=MetaDocumentProfile(
            number_field="biz_no", business_date_field="biz_date",
            numbering={"scope_bo": "p1_doc_scope",
                       "fallback_sequence_code": "P1S"}),
    ))
    try:
        config = resolve_document_numbering("p1_doc_scope")
    finally:
        from meta.core.models import registry
        registry.unregister(obj.id)

    assert config == {
        "no_field": "biz_no", "date_field": "biz_date",
        "scope_bo": "p1_doc_scope", "fallback_sequence_code": "P1S"}


def test_resolve_numbering_defaults_type_table():
    from meta.core.models import MetaDocumentProfile, MetaObject, registry
    from meta.services.document_number_service import resolve_document_numbering

    obj = _register(MetaObject(
        id="p1_doc_type", name="P1单据", table_name="p1_doc_type",
        document_profile=MetaDocumentProfile(
            number_field="doc_no", business_date_field="doc_date"),
    ))
    try:
        config = resolve_document_numbering("p1_doc_type")
    finally:
        registry.unregister(obj.id)

    assert config["no_field"] == "doc_no"
    assert config["date_field"] == "doc_date"
    assert config["type_table"] == "type_definitions"
    assert "scope_bo" not in config


def test_resolve_numbering_falls_back_to_legacy_table():
    """未声明 document: 的对象回落 NUMBERING（存量兼容）。"""
    from meta.services.document_number_service import resolve_document_numbering

    assert resolve_document_numbering("transfer_order")["no_field"] == \
        "transfer_order_no"
    assert resolve_document_numbering("no_such_object") is None
