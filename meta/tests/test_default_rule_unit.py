# -*- coding: utf-8 -*-
"""
属性确定（默认值）规则单元测试

[规则模型 T-05 ~ T-09 / T-12  2026-10-03]

覆盖：
- RuleType.DEFAULT 枚举 + yaml 映射 + parse_rule 分发（T-05）
- MetaDefaultRule 字段默认值 / target_field 属性 / MetaObject.get_defaults（T-06）
- RuleProvider.get_default_rules（T-06）
- DefaultExecutor 取值四类 / 覆盖语义 / apply_on（T-07）
- RuleEngine.default_by_priority 分组 + 首个命中 + tie-break + 再判定（T-08/T-09）
- DefaultLogEntry 日志结构（T-12）
"""

import pytest

from meta.core.models import (
    MetaObject, MetaField, MetaDefaultRule, MetaRule,
)
from meta.core.models_enums import RuleType, RuleTrigger, FieldType, ObjectType
from meta.core.rule_provider import RuleProvider, get_rule_provider, set_rule_provider
from meta.core.rule_executor import RuleEngine, RuleContext, DefaultLogEntry
from meta.core.yaml_loader import parse_rule, RULE_TYPE_MAP


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make_object(rules=None, object_type=ObjectType.ENTITY):
    obj = MetaObject(id="so", name="销售订单", table_name="t_so",
                     object_type=object_type)
    obj.fields = [
        MetaField(id="order_type", name="订单类型", field_type=FieldType.STRING,
                  db_column="order_type"),
        MetaField(id="customer_id", name="客户", field_type=FieldType.STRING,
                  db_column="customer_id"),
        MetaField(id="payment_terms", name="付款条件", field_type=FieldType.STRING,
                  db_column="payment_terms"),
        MetaField(id="price_list", name="价格表", field_type=FieldType.STRING,
                  db_column="price_list"),
    ]
    obj.rules = list(rules or [])
    return obj


def _rule(rid, target, shape, value, priority=100, condition="", **kw):
    r = MetaDefaultRule(id=rid, name=rid, target_fields=[target],
                        source_type=shape, source_value=value,
                        priority=priority, condition=condition)
    for k, v in kw.items():
        setattr(r, k, v)
    return r


# ---------------------------------------------------------------------------
# T-05 枚举 / yaml 映射
# ---------------------------------------------------------------------------

class TestRuleTypeDefaultEnum:
    def test_enum_value(self):
        assert RuleType.DEFAULT.value == "default"

    def test_yaml_map_contains_default(self):
        assert RULE_TYPE_MAP.get("default") == RuleType.DEFAULT

    def test_parse_rule_dispatches_to_meta_default_rule(self):
        rule = parse_rule({
            "id": "d1", "type": "default",
            "target_fields": ["payment_terms"],
            "condition": "order_type == 'ZOR'",
            "source_type": "constant", "source_value": "NT30",
            "priority": 10,
        })
        assert isinstance(rule, MetaDefaultRule)
        assert rule.rule_type == RuleType.DEFAULT
        assert rule.target_fields == ["payment_terms"]
        assert rule.source_type == "constant"
        assert rule.source_value == "NT30"

    def test_parse_rule_accepts_rule_type_key(self):
        rule = parse_rule({"id": "d2", "rule_type": "default",
                           "target_field": "price_list", "source_value": "PL1"})
        assert isinstance(rule, MetaDefaultRule)
        assert rule.target_field == "price_list"

    def test_parse_rule_default_trigger_is_before_save(self):
        rule = parse_rule({"id": "d3", "type": "default",
                           "target_fields": ["payment_terms"]})
        assert rule.triggers == [RuleTrigger.BEFORE_SAVE]


# ---------------------------------------------------------------------------
# T-06 模型 / 访问器 / Provider
# ---------------------------------------------------------------------------

class TestMetaDefaultRuleModel:
    def test_field_defaults(self):
        rule = MetaDefaultRule(id="d1", name="d1")
        assert rule.rule_type == RuleType.DEFAULT
        assert rule.apply_mode == "fill_if_empty"
        assert rule.apply_on == "both"
        assert rule.recompute == "keep"
        assert rule.triggers == [RuleTrigger.BEFORE_SAVE]

    def test_explicit_triggers_preserved(self):
        rule = MetaDefaultRule(id="d1", name="d1",
                               triggers=[RuleTrigger.ON_CHANGE])
        assert rule.triggers == [RuleTrigger.ON_CHANGE]

    def test_target_field_property(self):
        assert _rule("d1", "payment_terms", "constant", "X").target_field == "payment_terms"
        assert MetaDefaultRule(id="d2", name="d2").target_field == ""

    def test_object_get_defaults(self):
        obj = _make_object([
            _rule("d1", "payment_terms", "constant", "NT30"),
            MetaRule(id="c1", name="c1", rule_type=RuleType.COMPUTATION),
        ])
        defaults = obj.get_defaults()
        assert [r.id for r in defaults] == ["d1"]


class TestRuleProviderGetDefaultRules:
    def test_filters_by_rule_type_and_keeps_order(self):
        obj = _make_object([
            _rule("d2", "payment_terms", "constant", "B"),
            MetaRule(id="c1", name="c1", rule_type=RuleType.COMPUTATION),
            _rule("d1", "price_list", "constant", "A"),
        ])
        ids = [r.id for r in RuleProvider().get_default_rules(obj)]
        assert ids == ["d2", "d1"]

    def test_none_object_returns_empty(self):
        assert RuleProvider().get_default_rules(None) == []


# ---------------------------------------------------------------------------
# T-07 DefaultExecutor
# ---------------------------------------------------------------------------

class TestDefaultExecutor:
    def _engine_and_context(self, rules, data, **kw):
        obj = _make_object(rules)
        engine = RuleEngine()
        ctx = RuleContext(obj, data, kw.get("original_data"))
        ctx.change_source = kw.get("change_source", "both")
        if kw.get("auto_filled"):
            ctx.auto_filled_fields.update(kw["auto_filled"])
        return engine, obj, ctx

    def test_constant_source_fills_empty(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "constant", "NT30")],
            {"order_type": "ZOR", "payment_terms": ""})
        logs = engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == "NT30"
        assert logs[0].hit and logs[0].value == "NT30"
        assert logs[0].skip_reason == ""

    def test_constant_literal_type_restored(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "constant", "30")],
            {"payment_terms": ""})
        engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == 30

    def test_fill_if_empty_skips_non_empty(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "constant", "NT30")],
            {"payment_terms": "NT60"})
        logs = engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == "NT60"
        assert logs[0].hit is True
        assert logs[0].skip_reason == "target_not_empty"

    def test_override_overwrites_non_empty(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "constant", "NT30", apply_mode="override")],
            {"payment_terms": "NT60"})
        logs = engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == "NT30"
        assert logs[0].overwritten is True

    def test_condition_false_skips(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "constant", "NT30",
                   condition="order_type == 'ZCB1'")],
            {"order_type": "ZOR", "payment_terms": ""})
        logs = engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == ""
        assert logs[0].hit is False
        assert logs[0].skip_reason == "condition_false"

    def test_field_source_reads_sibling_field(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "field", "price_list")],
            {"price_list": "PL_STD", "payment_terms": ""})
        engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == "PL_STD"

    def test_expression_source(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "expression", "order_type + '_TERMS'")],
            {"order_type": "ZOR", "payment_terms": ""})
        engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == "ZOR_TERMS"

    def test_apply_on_mismatch_skips(self):
        engine, obj, ctx = self._engine_and_context(
            [_rule("d1", "payment_terms", "constant", "NT30", apply_on="user_input")],
            {"payment_terms": ""}, change_source="system")
        logs = engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == ""
        assert logs[0].skip_reason == "apply_on_mismatch"

    def test_disabled_rule_excluded(self):
        rule = _rule("d1", "payment_terms", "constant", "NT30")
        rule.enabled = False
        engine, obj, ctx = self._engine_and_context([rule], {"payment_terms": ""})
        logs = engine.default_by_priority(obj, ctx)
        assert logs == []
        assert ctx.data["payment_terms"] == ""

    def test_non_default_rule_type_not_executed(self):
        engine, obj, ctx = self._engine_and_context(
            [MetaRule(id="c1", name="c1", rule_type=RuleType.COMPUTATION)],
            {"payment_terms": ""})
        assert engine.default_by_priority(obj, ctx) == []


# ---------------------------------------------------------------------------
# T-08 分组 / 首个命中 / tie-break
# ---------------------------------------------------------------------------

class TestDefaultByPriority:
    def _run(self, rules, data, **kw):
        obj = _make_object(rules)
        engine = RuleEngine()
        ctx = RuleContext(obj, data, kw.get("original_data"))
        ctx.change_source = kw.get("change_source", "both")
        logs = engine.default_by_priority(obj, ctx)
        return ctx, logs

    def test_first_match_wins_lower_priority(self):
        ctx, logs = self._run([
            _rule("late", "payment_terms", "constant", "LATE", priority=20,
                  condition="order_type == 'ZOR'"),
            _rule("early", "payment_terms", "constant", "EARLY", priority=10,
                  condition="order_type == 'ZOR'"),
        ], {"order_type": "ZOR", "payment_terms": ""})
        assert ctx.data["payment_terms"] == "EARLY"
        reasons = {e.rule_id: e.skip_reason for e in logs}
        assert reasons["early"] == ""
        assert reasons["late"] == "not_first_match"

    def test_tie_break_by_rule_id(self):
        ctx, _ = self._run([
            _rule("b_rule", "payment_terms", "constant", "B", priority=10),
            _rule("a_rule", "payment_terms", "constant", "A", priority=10),
        ], {"payment_terms": ""})
        assert ctx.data["payment_terms"] == "A"

    def test_condition_match_but_blocked_then_next_rule_wins(self):
        ctx, logs = self._run([
            _rule("fill", "payment_terms", "constant", "FILL", priority=10),
            _rule("ovr", "payment_terms", "constant", "OVR", priority=20,
                  apply_mode="override"),
        ], {"payment_terms": "USER"})
        assert ctx.data["payment_terms"] == "OVR"
        reasons = {e.rule_id: e.skip_reason for e in logs}
        assert reasons["fill"] == "target_not_empty"
        assert reasons["ovr"] == ""

    def test_groups_are_independent(self):
        ctx, _ = self._run([
            _rule("d1", "payment_terms", "constant", "NT30", priority=10),
            _rule("d2", "price_list", "constant", "PL1", priority=10),
        ], {"payment_terms": "", "price_list": ""})
        assert ctx.data["payment_terms"] == "NT30"
        assert ctx.data["price_list"] == "PL1"

    def test_log_seq_and_factor_snapshot(self):
        ctx, logs = self._run([
            _rule("d1", "payment_terms", "constant", "NT30",
                  condition="order_type == 'ZOR'"),
        ], {"order_type": "ZOR", "payment_terms": ""})
        entry = logs[0]
        assert entry.seq == 1
        assert entry.factor_snapshot.get("order_type") == "ZOR"
        assert entry.target_field == "payment_terms"
        assert entry.elapsed_ms >= 0

    def test_log_to_dict_keys(self):
        entry = DefaultLogEntry(rule_id="d1")
        keys = set(entry.to_dict().keys())
        assert {"rule_id", "seq", "hit", "skip_reason", "value",
                "source_type", "overwritten", "factor_snapshot"} <= keys

    def test_trigger_filter_excludes_other_trigger(self):
        rule = _rule("d1", "payment_terms", "constant", "NT30")
        rule.triggers = [RuleTrigger.ON_CHANGE]
        obj = _make_object([rule])
        engine = RuleEngine()
        ctx = RuleContext(obj, {"payment_terms": ""})
        assert engine.default_by_priority(obj, ctx,
                                          trigger=RuleTrigger.BEFORE_SAVE) == []


# ---------------------------------------------------------------------------
# T-09 再判定（RECOMPUTE_KEEP / RECOMPUTE_CLEAR）
# ---------------------------------------------------------------------------

class TestRecomputePolicy:
    def _run(self, rules, data, auto_filled):
        obj = _make_object(rules)
        engine = RuleEngine()
        ctx = RuleContext(obj, data)
        ctx.auto_filled_fields.update(auto_filled)
        engine.default_by_priority(obj, ctx)
        return ctx

    def test_recompute_keep_preserves_old_auto_value(self):
        ctx = self._run(
            [_rule("d1", "payment_terms", "constant", "NT30",
                   condition="order_type == 'ZCB1'", recompute="keep")],
            {"order_type": "ZOR", "payment_terms": "NT30"},
            auto_filled={"payment_terms"})
        assert ctx.data["payment_terms"] == "NT30"

    def test_recompute_clear_wipes_old_auto_value(self):
        ctx = self._run(
            [_rule("d1", "payment_terms", "constant", "NT30",
                   condition="order_type == 'ZCB1'", recompute="clear")],
            {"order_type": "ZOR", "payment_terms": "NT30"},
            auto_filled={"payment_terms"})
        assert ctx.data["payment_terms"] is None

    def test_recompute_does_not_touch_user_value(self):
        ctx = self._run(
            [_rule("d1", "payment_terms", "constant", "NT30",
                   condition="order_type == 'ZCB1'", recompute="clear")],
            {"order_type": "ZOR", "payment_terms": "USER_INPUT"},
            auto_filled=set())
        assert ctx.data["payment_terms"] == "USER_INPUT"


# ---------------------------------------------------------------------------
# apply_defaults 入口
# ---------------------------------------------------------------------------

class TestApplyDefaultsEntry:
    def test_returns_data_and_logs(self):
        obj = _make_object([_rule("d1", "payment_terms", "constant", "NT30")])
        engine = RuleEngine()
        data, logs = engine.apply_defaults(obj, {"payment_terms": ""})
        assert data["payment_terms"] == "NT30"
        assert len(logs) == 1 and logs[0].value == "NT30"

    def test_previously_auto_filled_seed_enables_clear(self):
        obj = _make_object([
            _rule("d1", "payment_terms", "constant", "NT30",
                  condition="order_type == 'ZCB1'", recompute="clear")])
        engine = RuleEngine()
        data, _ = engine.apply_defaults(
            obj, {"order_type": "ZOR", "payment_terms": "NT30"},
            previously_auto_filled={"payment_terms"})
        assert data["payment_terms"] is None


# ---------------------------------------------------------------------------
# 视图对象不支持
# ---------------------------------------------------------------------------

class TestObjectTypeCompatibility:
    def test_view_object_rejects_default_rule(self):
        obj = _make_object([_rule("d1", "payment_terms", "constant", "NT30")],
                           object_type=ObjectType.VIEW)
        engine = RuleEngine()
        ctx = RuleContext(obj, {"payment_terms": ""})
        logs = engine.default_by_priority(obj, ctx)
        assert ctx.data["payment_terms"] == ""
        assert logs == []


# ---------------------------------------------------------------------------
# Provider 可替换性（一期入口收口回归）
# ---------------------------------------------------------------------------

class TestProviderInjection:
    def teardown_method(self):
        set_rule_provider(None)

    def test_custom_provider_is_used_by_default_by_priority(self):
        class _Empty(RuleProvider):
            def get_default_rules(self, meta_object):
                return []

        obj = _make_object([_rule("d1", "payment_terms", "constant", "NT30")])
        set_rule_provider(_Empty())
        try:
            engine = RuleEngine()
            ctx = RuleContext(obj, {"payment_terms": ""})
            assert engine.default_by_priority(obj, ctx) == []
            assert ctx.data["payment_terms"] == ""
        finally:
            set_rule_provider(None)
        assert isinstance(get_rule_provider(), RuleProvider)
