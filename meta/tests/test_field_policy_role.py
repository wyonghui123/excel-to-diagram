# -*- coding: utf-8 -*-
"""[S7.2 2026-11-06] 角色维度字段策略测试（纯元数据层，不依赖 DB）。

覆盖：
  · YAML field_policies 声明的角色规则命中 ⇒ 只读 / 必填；
  · 角色规则未命中 ⇒ 回落既有状态矩阵；
  · when_expr 需要 user_context.roles，无上下文时不得误命中；
  · 未声明 field_policies 的对象行为不变。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from meta.core.models import (  # noqa: E402
    MetaField,
    MetaObject,
    MetaStateDefinition,
    MetaStateFieldPolicy,
    MetaStateTransition,
)
from meta.services.field_policy_engine import (  # noqa: E402
    FieldPolicyEngine,
    PolicyContext,
    UserContext,
)


def _f(field_id, name):
    return MetaField(id=field_id, name=name, field_type="string", db_column=field_id)


def _build_object(field_policies=None, with_matrix=True):
    return MetaObject(
        id="po_role_test",
        name="角色策略测试",
        table_name="po_role_test",
        fields=[_f("amount", "金额"), _f("remark", "备注")],
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
        state_field_policies=(
            {"submitted": MetaStateFieldPolicy(readonly=["amount"])}
            if with_matrix else {}
        ),
        field_policies=field_policies or {},
    )


def _ctx(state="draft", roles=None):
    return PolicyContext(
        row={"status": state},
        state=state,
        action="update",
        user_context=UserContext(roles=roles or []),
    )


def test_role_rule_hit_marks_readonly():
    obj = _build_object(field_policies={
        "remark": {"editable": [{"when": "'auditor' in user.roles", "value": False}]},
    })
    engine = FieldPolicyEngine(obj)
    assert engine.is_field_editable("remark", _ctx(roles=["auditor"])) is False


def test_role_rule_miss_falls_back_to_matrix():
    obj = _build_object(field_policies={
        "remark": {"editable": [{"when": "'auditor' in user.roles", "value": False}]},
    })
    engine = FieldPolicyEngine(obj)
    # 角色未命中 ⇒ 无意见；remark 未在矩阵 readonly 中 ⇒ 可编辑
    assert engine.is_field_editable("remark", _ctx(state="submitted", roles=["clerk"])) is True
    # amount 仍受状态矩阵约束
    assert engine.is_field_editable("amount", _ctx(state="submitted", roles=["clerk"])) is False


def test_role_rule_overrides_matrix_when_hit():
    obj = _build_object(field_policies={
        "amount": {"editable": [{"when": "'admin' in user.roles", "value": True}]},
    })
    engine = FieldPolicyEngine(obj)
    assert engine.is_field_editable("amount", _ctx(state="submitted", roles=["admin"])) is True


def test_no_user_context_keeps_legacy_behavior():
    obj = _build_object(field_policies={
        "remark": {"editable": [{"when": "'auditor' in user.roles", "value": False}]},
    })
    engine = FieldPolicyEngine(obj)
    plain = PolicyContext(row={"status": "draft"}, state="draft", action="update")
    assert engine.is_field_editable("remark", plain) is True


def test_required_role_rule():
    obj = _build_object(field_policies={
        "remark": {"required": [{"when": "'clerk' in user.roles", "value": True}]},
    })
    engine = FieldPolicyEngine(obj)
    assert engine.is_field_required("remark", _ctx(roles=["clerk"])) is True
    assert engine.is_field_required("remark", _ctx(roles=["viewer"])) is False


def test_visible_role_rule():
    obj = _build_object(field_policies={
        "remark": {"visible": [{"when": "'external' in user.roles", "value": False}]},
    })
    engine = FieldPolicyEngine(obj)
    assert engine.is_field_visible("remark", _ctx(roles=["external"])) is False
    assert engine.is_field_visible("remark", _ctx(roles=["internal"])) is True


def test_no_field_policies_behavior_unchanged():
    engine = FieldPolicyEngine(_build_object())
    assert engine.is_field_editable("remark", _ctx(roles=["auditor"])) is True
    assert engine.is_field_editable("amount", _ctx(state="submitted")) is False
