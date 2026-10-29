# -*- coding: utf-8 -*-
"""
TestStateSideEffects — 状态转换 side_effects 执行器（P1-1 C4-a）

覆盖点：
- 声明解析白名单：NOW() / <field> +/- 数字 / 字面量；非法表达式抛错
- flat 执行器（StateTransitionExecutor）与状态字段同批写入
- chain 执行器（ImplicitRuleChainExecutor）与 flat 共用同一实现
- 对象不存在的 target 字段跳过（不写坏 SQL）
- reload 前置校验：schema 目录内非法声明立即失败
"""

import os
import sys
from datetime import datetime

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import (
    MetaField, MetaObject, MetaStateTransition, StateTransitionSideEffect, FieldType,
)
from meta.core.rule_chain import ImplicitRuleChainExecutor, RuleChainContext
from meta.core.rule_executor import RuleContext, StateTransitionExecutor
from meta.core.state_side_effects import (
    SideEffectDeclarationError,
    apply_state_side_effects,
    evaluate_side_effect_value,
    validate_schema_dir_side_effects,
    validate_side_effects,
)


def _make_obj(with_delivered_at=True):
    fields = [
        MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
        MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        MetaField(id="retry_count", name="重试次数", field_type=FieldType.INTEGER,
                  db_column="retry_count"),
    ]
    if with_delivered_at:
        fields.append(MetaField(id="delivered_at", name="投递时间",
                                field_type=FieldType.DATETIME, db_column="delivered_at"))
    return MetaObject(id="se_events", name="事件（副作用测试）", table_name="se_events",
                      fields=fields)


def _deliver_rule(side_effects=None):
    return MetaStateTransition(
        id="deliver_event",
        name="投递成功",
        state_field="status",
        from_states=["processing"],
        to_state="delivered",
        side_effects=side_effects if side_effects is not None else [
            StateTransitionSideEffect(type="set_field", target="delivered_at", value="NOW()"),
        ],
    )


# ---- 表达式白名单 ----

class TestSideEffectExpressions:

    def test_now_expression_returns_datetime(self):
        value = evaluate_side_effect_value("NOW()", lambda field: None)
        assert isinstance(value, datetime)

    def test_arithmetic_uses_current_value(self):
        assert evaluate_side_effect_value("retry_count + 1",
                                          lambda field: 2) == 3
        assert evaluate_side_effect_value("retry_count - 1",
                                          lambda field: 2) == 1

    def test_arithmetic_none_treated_as_zero(self):
        assert evaluate_side_effect_value("retry_count + 1",
                                          lambda field: None) == 1

    def test_empty_string_is_literal(self):
        assert evaluate_side_effect_value("", lambda field: None) == ""

    def test_plain_text_is_literal(self):
        assert evaluate_side_effect_value("已完成", lambda field: None) == "已完成"

    def test_negative_number_literal(self):
        assert evaluate_side_effect_value("-5", lambda field: None) == -5

    def test_non_string_value_passthrough(self):
        assert evaluate_side_effect_value(5, lambda field: None) == 5
        assert evaluate_side_effect_value(None, lambda field: None) is None

    def test_call_expression_rejected(self):
        with pytest.raises(SideEffectDeclarationError):
            evaluate_side_effect_value("os.system('rm')", lambda field: None)

    def test_arithmetic_between_fields_rejected(self):
        with pytest.raises(SideEffectDeclarationError):
            evaluate_side_effect_value("retry_count + other", lambda field: None)

    def test_unsupported_type_rejected(self):
        with pytest.raises(SideEffectDeclarationError):
            validate_side_effects([{"type": "send_email", "target": "x", "value": "a"}])

    def test_missing_target_rejected(self):
        with pytest.raises(SideEffectDeclarationError):
            validate_side_effects([{"type": "set_field", "value": "NOW()"}])

    def test_non_numeric_base_raises(self):
        with pytest.raises(SideEffectDeclarationError):
            evaluate_side_effect_value("retry_count + 1", lambda field: "abc")


# ---- flat 执行器 ----

class TestFlatExecutorSideEffects:

    def test_delivered_at_written_in_same_batch(self):
        obj = _make_obj()
        ctx = RuleContext(obj, {"id": 1, "status": "delivered"},
                          {"id": 1, "status": "processing"})
        result = StateTransitionExecutor().execute(_deliver_rule(), ctx)

        assert result.success is True, result.message
        assert ctx.data["status"] == "delivered"
        assert isinstance(ctx.data["delivered_at"], datetime)
        assert "delivered_at" in ctx.changed_fields

    def test_retry_count_incremented(self):
        obj = _make_obj()
        rule = MetaStateTransition(
            id="retry_event", name="重试", state_field="status",
            from_states=["failed"], to_state="pending",
            side_effects=[StateTransitionSideEffect(
                type="set_field", target="retry_count", value="retry_count + 1")],
        )
        ctx = RuleContext(obj, {"id": 1, "status": "pending", "retry_count": 2},
                          {"id": 1, "status": "failed", "retry_count": 2})
        result = StateTransitionExecutor().execute(rule, ctx)

        assert result.success is True, result.message
        assert ctx.data["retry_count"] == 3

    def test_unknown_target_skipped(self):
        obj = _make_obj(with_delivered_at=False)
        ctx = RuleContext(obj, {"id": 1, "status": "delivered"},
                          {"id": 1, "status": "processing"})
        result = StateTransitionExecutor().execute(_deliver_rule(), ctx)

        assert result.success is True, result.message
        assert "delivered_at" not in ctx.data

    def test_no_side_effects_keeps_behavior(self):
        obj = _make_obj()
        ctx = RuleContext(obj, {"id": 1, "status": "delivered"},
                          {"id": 1, "status": "processing"})
        result = StateTransitionExecutor().execute(_deliver_rule(side_effects=[]), ctx)

        assert result.success is True
        assert "delivered_at" not in ctx.data


# ---- chain 执行器（与 flat 共用实现）----

class TestChainExecutorSideEffects:

    def _execute(self, obj, rule, data, original_data):
        obj.rules = [rule]
        executor = ImplicitRuleChainExecutor(obj)
        node = executor.graph.nodes[rule.id]
        ctx = RuleChainContext(data=dict(data), original_data=dict(original_data))
        return executor._execute_state_transition(node, ctx), ctx

    def test_delivered_at_written_and_recorded(self):
        obj = _make_obj()
        result, ctx = self._execute(
            obj, _deliver_rule(),
            {"id": 1, "status": "delivered"}, {"id": 1, "status": "processing"})

        assert result["success"] is True
        assert isinstance(ctx.data["delivered_at"], datetime)
        assert "delivered_at" in ctx.changed_fields
        changed = {c.field_id for c in result["changes"]}
        assert "delivered_at" in changed


# ---- chain 执行器：状态进入时间 ----

class TestChainExecutorStateEnteredAt:

    def _make_obj(self, with_entered_at=True):
        fields = [
            MetaField(id="id", name="ID", field_type=FieldType.INTEGER, db_column="id"),
            MetaField(id="status", name="状态", field_type=FieldType.STRING, db_column="status"),
        ]
        if with_entered_at:
            fields.append(MetaField(id="status_entered_at", name="状态进入时间",
                                    field_type=FieldType.DATETIME, db_column="status_entered_at"))
        return MetaObject(id="st_events", name="事件（进入时间测试）", table_name="st_events",
                          fields=fields)

    def _execute(self, obj, data, original_data):
        rule = MetaStateTransition(
            id="start_event", name="开始", state_field="status",
            from_states=["draft"], to_state="processing")
        obj.rules = [rule]
        executor = ImplicitRuleChainExecutor(obj)
        node = executor.graph.nodes[rule.id]
        ctx = RuleChainContext(data=dict(data), original_data=dict(original_data))
        return executor._execute_state_transition(node, ctx), ctx

    def test_written_when_field_declared(self):
        result, ctx = self._execute(
            self._make_obj(), {"id": 1, "status": "processing"}, {"id": 1, "status": "draft"})

        assert result["success"] is True
        assert isinstance(ctx.data["status_entered_at"], datetime)

    def test_skipped_when_field_not_declared(self):
        result, ctx = self._execute(
            self._make_obj(with_entered_at=False),
            {"id": 1, "status": "processing"}, {"id": 1, "status": "draft"})

        assert result["success"] is True
        assert "status_entered_at" not in ctx.data


# ---- reload 前置校验 ----

class TestReloadValidation:

    def test_valid_schema_passes(self, tmp_path):
        (tmp_path / "ok.yaml").write_text(
            "id: evt\nname: 事件\ntable_name: evt\n"
            "rules:\n"
            "  - id: deliver_event\n    type: state_transition\n"
            "    state_field: status\n    to_state: delivered\n"
            "    side_effects:\n"
            "      - type: set_field\n        target: delivered_at\n        value: \"NOW()\"\n",
            encoding="utf-8",
        )
        stats = validate_schema_dir_side_effects(str(tmp_path))
        assert stats == {"files": 1, "declarations": 1}

    def test_invalid_expression_fails(self, tmp_path):
        (tmp_path / "bad.yaml").write_text(
            "id: evt\nname: 事件\ntable_name: evt\n"
            "rules:\n"
            "  - id: bad_event\n    type: state_transition\n"
            "    state_field: status\n    to_state: delivered\n"
            "    side_effects:\n"
            "      - type: set_field\n        target: delivered_at\n"
            "        value: \"foo()\"\n",
            encoding="utf-8",
        )
        with pytest.raises(SideEffectDeclarationError):
            validate_schema_dir_side_effects(str(tmp_path))

    def test_real_schema_dir_is_valid(self):
        from meta.core.yaml_loader import get_yaml_schema_dir
        stats = validate_schema_dir_side_effects(get_yaml_schema_dir())
        assert stats["declarations"] >= 3  # change_event ×2 + audit_log ×1


# ---- 直接调用 apply_state_side_effects ----

class TestApplyHelper:

    def test_returns_applied_changes(self):
        rule = _deliver_rule()
        data = {"delivered_at": None}
        applied = apply_state_side_effects(
            rule,
            lambda field: data.get(field),
            lambda field, value: data.__setitem__(field, value),
            valid_fields={"delivered_at"},
        )
        assert len(applied) == 1
        target, old, new = applied[0]
        assert target == "delivered_at"
        assert old is None
        assert isinstance(new, datetime)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
