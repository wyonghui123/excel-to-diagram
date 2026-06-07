import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
SafeExpressionEvaluator 单元测试

测试 §7.13 (FR-P0-001, FR-P2-002) 安全表达式解析器。
基于 AST 的白名单表达式解析器，替代 Python `eval()` 和前端 `new Function()`。
覆盖：白名单操作符、注入攻击防御、上下文解析、错误处理。
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.safe_expr_evaluator import (
    safe_evaluate, _ALLOWED_COMPARE_OPS, _ALLOWED_BOOL_OPS,
    _ALLOWED_UNARY_OPS, _FORBIDDEN_NAMES
)


class TestSafeEvaluateBasicOperators:

    def test_eq_operator(self):
        result = safe_evaluate("a == 1", {"a": 1})
        assert result is True
        result = safe_evaluate("a == 1", {"a": 2})
        assert result is False

    def test_not_eq_operator(self):
        result = safe_evaluate("a != 1", {"a": 2})
        assert result is True
        result = safe_evaluate("a != 1", {"a": 1})
        assert result is False

    def test_less_than(self):
        result = safe_evaluate("a < 10", {"a": 5})
        assert result is True
        result = safe_evaluate("a < 10", {"a": 10})
        assert result is False

    def test_less_than_or_equal(self):
        result = safe_evaluate("a <= 10", {"a": 10})
        assert result is True
        result = safe_evaluate("a <= 10", {"a": 11})
        assert result is False

    def test_greater_than(self):
        result = safe_evaluate("a > 10", {"a": 11})
        assert result is True
        result = safe_evaluate("a > 10", {"a": 10})
        assert result is False

    def test_greater_than_or_equal(self):
        result = safe_evaluate("a >= 10", {"a": 10})
        assert result is True
        result = safe_evaluate("a >= 10", {"a": 9})
        assert result is False

    def test_in_operator(self):
        result = safe_evaluate("a in [1, 2, 3]", {"a": 2})
        assert result is True
        result = safe_evaluate("a in [1, 2, 3]", {"a": 4})
        assert result is False

    def test_not_in_operator(self):
        result = safe_evaluate("a not in [1, 2, 3]", {"a": 4})
        assert result is True
        result = safe_evaluate("a not in [1, 2, 3]", {"a": 1})
        assert result is False


class TestSafeEvaluateBooleanOperators:

    def test_and_operator(self):
        result = safe_evaluate("a > 0 and a < 10", {"a": 5})
        assert result is True
        result = safe_evaluate("a > 0 and a < 10", {"a": 11})
        assert result is False
        result = safe_evaluate("a > 0 and a < 10", {"a": -1})
        assert result is False

    def test_or_operator(self):
        result = safe_evaluate("a == 1 or a == 2", {"a": 2})
        assert result is True
        result = safe_evaluate("a == 1 or a == 2", {"a": 3})
        assert result is False

    def test_not_operator(self):
        result = safe_evaluate("not a", {"a": False})
        assert result is True
        result = safe_evaluate("not a", {"a": True})
        assert result is False

    def test_negation_operator(self):
        result = safe_evaluate("-a == -5", {"a": 5})
        assert result is True

    def test_positive_operator(self):
        result = safe_evaluate("+a == 5", {"a": 5})
        assert result is True

    def test_chained_comparison(self):
        result = safe_evaluate("0 < a < 10", {"a": 5})
        assert result is True
        result = safe_evaluate("0 < a < 10", {"a": 15})
        assert result is False


class TestSafeEvaluateInjectionPrevention:

    def test_rejects_import_statement(self):
        result = safe_evaluate("import os")
        assert result is False

    def test_rejects_eval_keyword(self):
        result = safe_evaluate("eval('os.system')")
        assert result is False

    def test_rejects_exec_keyword(self):
        result = safe_evaluate("exec('os.system')")
        assert result is False

    def test_rejects_open_function(self):
        result = safe_evaluate("open('/etc/passwd')")
        assert result is False

    def test_rejects_dunder_getattr(self):
        result = safe_evaluate("getattr(obj, '__class__')")
        assert result is False

    def test_rejects_setattr(self):
        result = safe_evaluate("setattr(obj, 'malicious', 'value')")
        assert result is False

    def test_rejects_builtins(self):
        result = safe_evaluate("__builtins__")
        assert result is False

    def test_rejects_dunder_name(self):
        result = safe_evaluate("__name__")
        assert result is False

    def test_rejects_function_call(self):
        result = safe_evaluate("len(items)")
        assert result is False

    def test_rejects_arithmetic_operator(self):
        result = safe_evaluate("a + b")
        assert result is False

    def test_rejects_lambda(self):
        result = safe_evaluate("lambda x: x")
        assert result is False

    def test_rejects_list_comprehension(self):
        result = safe_evaluate("[x for x in items]")
        assert result is False

    def test_rejects_subscript_access(self):
        result = safe_evaluate("items[0]")
        assert result is False


class TestSafeEvaluateEdgeCases:

    def test_empty_expression_returns_true(self):
        result = safe_evaluate("")
        assert result is True

    def test_whitespace_only_returns_true(self):
        result = safe_evaluate("   ")
        assert result is True

    def test_none_input_returns_true(self):
        result = safe_evaluate(None)
        assert result is True

    def test_syntax_error_returns_false(self):
        result = safe_evaluate("a == ")
        assert result is False

    def test_undefined_name_returns_false(self):
        result = safe_evaluate("a == 1", {})
        assert result is False

    def test_string_true_returns_true(self):
        result = safe_evaluate("True")
        assert result is True

    def test_string_false_returns_false(self):
        result = safe_evaluate("False")
        assert result is False

    def test_none_value(self):
        result = safe_evaluate("a is None", {"a": None})
        assert result is True
        result = safe_evaluate("a is None", {"a": 0})
        assert result is False

    def test_is_not_operator(self):
        result = safe_evaluate("a is not None", {"a": 0})
        assert result is True
        result = safe_evaluate("a is not None", {"a": None})
        assert result is False


class TestSafeEvaluateRealWorldScenarios:

    def test_deletability_condition(self):
        result = safe_evaluate("self.child_count == 0", {"self": type('R', (), {'child_count': 0})()})
        assert result is True

        result = safe_evaluate("self.child_count == 0", {"self": type('R', (), {'child_count': 3})()})
        assert result is False

    def test_enum_readonly_condition(self):
        result = safe_evaluate("old_value != new_value", {"old_value": "draft", "new_value": "published"})
        assert result is True

    def test_unique_scope_condition(self):
        result = safe_evaluate("count == 1", {"count": 1})
        assert result is True

    def test_field_policy_condition(self):
        result = safe_evaluate("user.role == 'admin' and user.active == True",
                               {"user": type('U', (), {'role': 'admin', 'active': True})()})
        assert result is True


class TestSafeEvaluateContextResolution:

    def test_nested_attribute_access(self):
        class Record:
            def __init__(self):
                self.status = 'active'
        result = safe_evaluate("record.status == 'active'", {"record": Record()})
        assert result is True

    def test_dict_context(self):
        class Data:
            status = 'active'
        result = safe_evaluate("record.status == 'active'", {"record": Data()})
        assert result is True

    def test_mixed_context(self):
        result = safe_evaluate("self.name != '' and count > 0", {
            "self": type('S', (), {'name': 'Test'})(),
            "count": 5
        })
        assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
