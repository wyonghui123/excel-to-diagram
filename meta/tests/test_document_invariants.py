# -*- coding: utf-8 -*-
"""[S7.4 2026-11-06] 事实单据生命周期默认推导测试（纯元数据层）。

覆盖：
  · derive_default_state_policy 由 posting_state + number_field + snapshot_fields 推导；
  · 未声明 posting_state ⇒ 空推导（零影响）；
  · derive_deletability 过账状态不可删；
  · FieldPolicyEngine 未显式声明矩阵时使用推导兜底。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core.models import (  # noqa: E402
    MetaDocumentProfile,
    MetaField,
    MetaObject,
    MetaStateDefinition,
    registry,
)
from meta.services.document_invariants import (  # noqa: E402
    derive_default_state_policy,
    derive_deletability,
)
from meta.services.field_policy_engine import (  # noqa: E402
    FieldPolicyEngine,
    PolicyContext,
)


def _f(field_id, name):
    return MetaField(id=field_id, name=name, field_type="string", db_column=field_id)


def _obj(object_id, profile):
    obj = MetaObject(
        id=object_id,
        name=object_id,
        table_name=object_id,
        fields=[_f("order_no", "单号"), _f("amount", "金额"), _f("remark", "备注")],
        states=[
            MetaStateDefinition(code="draft", label="草稿", category="initial", seq=1),
            MetaStateDefinition(code="confirmed", label="已确认", seq=2),
        ],
    )
    obj.document_profile = profile
    return obj


@pytest.fixture(autouse=True)
def temp_registry():
    """保存 / 恢复全局 registry，避免污染其他测试。"""
    saved = dict(registry._objects)
    try:
        yield
    finally:
        registry._objects = saved


def test_derive_default_state_policy():
    registry.register(_obj("inv_doc", MetaDocumentProfile(
        number_field="order_no",
        state_field="status",
        posting_state="confirmed",
        snapshot_fields=["amount"],
    )))
    derived = derive_default_state_policy("inv_doc")
    assert derived == {"confirmed": {"readonly": ["order_no", "amount"]}}


def test_derive_default_state_policy_without_posting_state():
    registry.register(_obj("inv_plain", MetaDocumentProfile(
        number_field="order_no",
        snapshot_fields=["amount"],
    )))
    assert derive_default_state_policy("inv_plain") == {}


def test_derive_default_state_policy_unknown_object():
    assert derive_default_state_policy("not_registered_at_all") == {}


def test_derive_deletability():
    registry.register(_obj("inv_del", MetaDocumentProfile(
        number_field="order_no", posting_state="confirmed",
    )))
    assert derive_deletability("inv_del", "draft") is True
    assert derive_deletability("inv_del", "confirmed") is False
    # 未声明对象恒可删（不猜业务）
    assert derive_deletability("not_registered_at_all", "confirmed") is True


def test_engine_uses_derived_policy_when_no_matrix():
    obj = _obj("inv_engine", MetaDocumentProfile(
        number_field="order_no",
        state_field="status",
        posting_state="confirmed",
        snapshot_fields=["amount"],
    ))
    registry.register(obj)
    engine = FieldPolicyEngine(obj)
    ctx = PolicyContext(row={"status": "confirmed"}, state="confirmed", action="update")
    assert engine.is_field_editable("order_no", ctx) is False
    assert engine.is_field_editable("amount", ctx) is False
    # 未在推导集合中的字段仍可编辑
    assert engine.is_field_editable("remark", ctx) is True


def test_engine_no_profile_keeps_legacy_behavior():
    obj = _obj("inv_legacy", None)
    registry.register(obj)
    engine = FieldPolicyEngine(obj)
    ctx = PolicyContext(row={"status": "confirmed"}, state="confirmed", action="update")
    assert engine.is_field_editable("order_no", ctx) is True
