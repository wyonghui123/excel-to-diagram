# -*- coding: utf-8 -*-
"""
ENG-001: condition_evaluator (22 测试) - 核心条件评估引擎

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] ConditionEvaluator 条件求值 / _FieldAccessor 字段访问
"""
import pytest
from meta.core.condition_evaluator import ConditionEvaluator, _FieldAccessor

pytestmark = [pytest.mark.unit]


class TestConditionEvaluator:
    """ConditionEvaluator 条件求值测试"""
    def test_empty_condition_returns_true(self):
        ev = ConditionEvaluator()
        assert ev.evaluate("") is True
        assert ev.evaluate("   ") is True
        assert ev.evaluate(None) is True

    def test_simple_true_literal(self):
        ev = ConditionEvaluator()
        assert ev.evaluate("True") is True
        assert ev.evaluate("true") is True
        assert ev.evaluate("False") is False
        assert ev.evaluate("false") is False

    def test_simple_comparison(self):
        ev = ConditionEvaluator({'count': 5})
        assert ev.evaluate("count == 5") is True
        assert ev.evaluate("count == 3") is False
        assert ev.evaluate("count > 3") is True
        assert ev.evaluate("count < 3") is False

    def test_logical_not(self):
        ev = ConditionEvaluator({'a': 1})
        assert ev.evaluate("not (a == 5)") is True
        assert ev.evaluate("not (a == 1)") is False

    # ---------- 逻辑运算符 合并 (2 → 1, 4 cases) ----------
    @pytest.mark.parametrize('op,true_expr,false_expr,context', [
        pytest.param('and', 'a == 1 and b == 2', 'a == 1 and b == 3',
                    {'a': 1, 'b': 2}, id='and'),
        pytest.param('or', 'a == 1 or b == 3', 'a == 5 or b == 3',
                    {'a': 1, 'b': 2}, id='or'),
    ])
    def test_logical_op(self, op, true_expr, false_expr, context):
        ev = ConditionEvaluator(context)
        assert ev.evaluate(true_expr) is True
        assert ev.evaluate(false_expr) is False

    def test_membership_in(self):
        ev = ConditionEvaluator({'status': 'active'})
        assert ev.evaluate("status in ['active', 'pending']") is True
        assert ev.evaluate("status in ['closed', 'archived']") is False

    # ---------- self/parent 字段访问 合并 (2 → 1, 4 cases) ----------
    @pytest.mark.parametrize('context,expr,expected', [
        pytest.param({'self': {'name': 'test', 'value': 10}}, "self.name == 'test'", True, id='self_name'),
        pytest.param({'self': {'name': 'test', 'value': 10}}, "self.value > 5", True, id='self_value'),
        pytest.param({'self': {'status': 'draft'}, 'parent': {'status': 'active'}},
                    "self.status == 'draft'", True, id='self_status'),
        pytest.param({'self': {'status': 'draft'}, 'parent': {'status': 'active'}},
                    "parent.status == 'active'", True, id='parent_status'),
    ])
    def test_field_access(self, context, expr, expected):
        ev = ConditionEvaluator(context)
        assert ev.evaluate(expr) is expected

    def test_evaluate_with_message_pass(self):
        ev = ConditionEvaluator({'x': 1})
        result, msg = ev.evaluate_with_message("x == 1", "should not see this")
        assert result is True
        assert msg == ""

    def test_evaluate_with_message_fail(self):
        ev = ConditionEvaluator({'x': 1})
        result, msg = ev.evaluate_with_message("x == 2", "x must equal 2")
        assert result is False
        assert msg == "x must equal 2"

    def test_evaluation_failure_returns_false(self):
        ev = ConditionEvaluator()
        # 不合法表达式 → safe_evaluate 抛异常 → return False
        assert ev.evaluate("__import__('os').system('echo')") is False
        assert ev.evaluate("invalid syntax +++") is False

    def test_runtime_context_override(self):
        ev = ConditionEvaluator({'x': 1})
        # runtime context 覆盖 self.x
        assert ev.evaluate("x == 99", {'x': 99}) is True
        assert ev.evaluate("x == 1", {'x': 99}) is False

    def test_numeric_defaults_for_count(self):
        ev = ConditionEvaluator({'self': {}})  # 无 count 字段
        # self.count 走 FieldAccessor._NUMERIC_DEFAULTS → 0
        assert ev.evaluate("self.count == 0") is True
        assert ev.evaluate("self.count > 0") is False
        # self.relation_count 同理
        assert ev.evaluate("self.relation_count == 0") is True


class TestFieldAccessor:
    def test_dict_access(self):
        acc = _FieldAccessor({'name': 'foo', 'value': 10})
        assert acc.name == 'foo'
        assert acc.value == 10

    def test_missing_field_returns_none(self):
        acc = _FieldAccessor({'name': 'foo'})
        assert acc.missing is None

    def test_numeric_default_for_count(self):
        acc = _FieldAccessor({})
        assert acc.count == 0
        assert acc.relation_count == 0

    def test_get_method(self):
        acc = _FieldAccessor({'a': 1})
        assert acc.get('a') == 1
        assert acc.get('b', 'default') == 'default'

    def test_equality(self):
        acc1 = _FieldAccessor({'a': 1})
        acc2 = _FieldAccessor({'a': 1})
        assert acc1 == acc2

    def test_contains(self):
        acc = _FieldAccessor({'a': 1, 'b': 2})
        assert 'a' in acc
        assert 'c' not in acc

    # ---------- bool() 合并 (2 → 1, 2 cases) ----------
    @pytest.mark.parametrize('data,expected', [
        pytest.param({}, False, id='empty'),
        pytest.param({'a': 1}, True, id='nonempty'),
    ])
    def test_bool(self, data, expected):
        acc = _FieldAccessor(data)
        assert bool(acc) is expected

    def test_repr(self):
        acc = _FieldAccessor({'a': 1})
        assert repr(acc) == "{'a': 1}"
