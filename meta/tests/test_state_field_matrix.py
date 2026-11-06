# -*- coding: utf-8 -*-
"""S1 状态 × 字段矩阵测试（纯元数据层，不依赖 DB）。"""

import pytest

from meta.core.models import (
    MetaField,
    MetaObject,
    MetaStateDefinition,
    MetaStateFieldPolicy,
    MetaStateTransition,
)
from meta.core.yaml_loader import parse_meta_object
from meta.services.field_policy_engine import FieldPolicyEngine, PolicyContext


def _f(field_id, name):
    return MetaField(id=field_id, name=name, field_type="string", db_column=field_id)


def _build_object():
    return MetaObject(
        id="purchase_order_test",
        name="采购订单测试",
        table_name="purchase_order_test",
        fields=[_f("code", "编码"), _f("remark", "备注"), _f("reason", "取消原因")],
        rules=[
            MetaStateTransition(
                id="po_submit", name="提交", state_field="status",
                from_states=["draft"], to_state="submitted",
            ),
        ],
        states=[
            MetaStateDefinition(code="draft", label="草稿", category="initial", seq=1),
            MetaStateDefinition(code="submitted", label="已提交", seq=2),
        ],
        state_field_policies={
            "submitted": MetaStateFieldPolicy(
                readonly=["code"], required=["reason"], hidden=["remark"],
            ),
        },
    )


def _ctx(state):
    return PolicyContext(row={"status": state}, state=state, action="update")


def test_matrix_readonly_wins_over_field_default():
    """矩阵 readonly 优先于字段默认可编辑。"""
    engine = FieldPolicyEngine(_build_object())
    assert engine.is_field_editable("code", _ctx("submitted")) is False
    assert engine.is_field_editable("code", _ctx("draft")) is True


def test_matrix_required():
    engine = FieldPolicyEngine(_build_object())
    assert engine.is_field_required("reason", _ctx("submitted")) is True
    assert engine.is_field_required("reason", _ctx("draft")) is False


def test_matrix_hidden_blocks_visible_and_required():
    engine = FieldPolicyEngine(_build_object())
    assert engine.is_field_visible("remark", _ctx("submitted")) is False
    assert engine.is_field_required("remark", _ctx("submitted")) is False
    assert engine.is_field_editable("remark", _ctx("submitted")) is False


def test_no_state_declaration_keeps_legacy_behavior():
    """未声明矩阵的对象行为不变。"""
    engine = FieldPolicyEngine(MetaObject(
        id="plain_test", name="普通对象", table_name="plain_test",
        fields=[_f("code", "编码")],
    ))
    assert engine.is_field_editable("code", _ctx("anything")) is True


def test_parse_states_and_policies():
    obj = parse_meta_object({
        "id": "po_parse",
        "name": "解析测试",
        "table_name": "po_parse",
        "fields": [{"id": "code", "name": "编码", "type": "string"}],
        "rules": [{
            "id": "po_submit", "name": "提交", "type": "state_transition",
            "state_field": "status", "from_states": ["draft"], "to_state": "submitted",
        }],
        "states": [{"code": "draft", "label": "草稿", "category": "initial"}],
        "state_field_policies": {"submitted": {"readonly": ["code"]}},
    })
    assert [s.code for s in obj.states] == ["draft"]
    assert obj.states[0].category == "initial"
    assert obj.state_field_policies["submitted"].readonly == ["code"]


def test_invalid_state_ref_fails_fast():
    with pytest.raises(ValueError, match="未声明的状态"):
        parse_meta_object({
            "id": "po_bad_state",
            "name": "坏状态",
            "table_name": "po_bad_state",
            "fields": [{"id": "code", "name": "编码", "type": "string"}],
            "state_field_policies": {"ghost_state": {"readonly": ["code"]}},
        })


def test_invalid_field_ref_fails_fast():
    with pytest.raises(ValueError, match="不存在的字段"):
        parse_meta_object({
            "id": "po_bad_field",
            "name": "坏字段",
            "table_name": "po_bad_field",
            "fields": [{"id": "code", "name": "编码", "type": "string"}],
            "rules": [{
                "id": "po_submit", "name": "提交", "type": "state_transition",
                "state_field": "status", "from_states": ["draft"], "to_state": "submitted",
            }],
            "state_field_policies": {"submitted": {"readonly": ["ghost_field"]}},
        })


def test_purchase_order_pilot_declared():
    """试点对象 purchase_order 的真实声明可解析，且矩阵字段全部存在。"""
    import yaml
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "schemas" / "purchase_order.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    obj = parse_meta_object(data, "purchase_order.yaml")

    assert [s.code for s in obj.states] == [
        "draft", "submitted", "confirmed", "closed", "cancelled",
    ]
    assert obj.states[0].category == "initial"
    confirmed = obj.state_field_policies["confirmed"]
    assert "exchange_rate" in confirmed.readonly
    assert "supplier_party_id" in confirmed.readonly
    assert "payment_term_id" in obj.state_field_policies["closed"].readonly
    # 草稿未声明矩阵 ⇒ 行为不变
    assert "draft" not in obj.state_field_policies
