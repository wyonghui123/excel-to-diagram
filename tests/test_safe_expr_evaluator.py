import pytest
from meta.core.safe_expr_evaluator import safe_evaluate


class TestSafeEvaluateBasic:
    def test_simple_eq_true(self):
        assert safe_evaluate("value == 1", {"value": 1}) is True

    def test_simple_eq_false(self):
        assert safe_evaluate("value == 2", {"value": 1}) is False

    def test_simple_ne(self):
        assert safe_evaluate("value != 1", {"value": 2}) is True

    def test_lt(self):
        assert safe_evaluate("x < 10", {"x": 5}) is True
        assert safe_evaluate("x < 5", {"x": 5}) is False

    def test_lte(self):
        assert safe_evaluate("x <= 5", {"x": 5}) is True
        assert safe_evaluate("x <= 3", {"x": 5}) is False

    def test_gt(self):
        assert safe_evaluate("x > 3", {"x": 5}) is True
        assert safe_evaluate("x > 5", {"x": 5}) is False

    def test_gte(self):
        assert safe_evaluate("x >= 5", {"x": 5}) is True
        assert safe_evaluate("x >= 6", {"x": 5}) is False

    def test_in_operator(self):
        assert safe_evaluate("x in [1, 2, 3]", {"x": 2}) is True
        assert safe_evaluate("x in [1, 2, 3]", {"x": 4}) is False

    def test_not_in_operator(self):
        assert safe_evaluate("x not in [1, 2, 3]", {"x": 4}) is True
        assert safe_evaluate("x not in [1, 2, 3]", {"x": 2}) is False

    def test_is_operator(self):
        assert safe_evaluate("x is None", {"x": None}) is True
        assert safe_evaluate("x is None", {"x": 1}) is False

    def test_is_not_operator(self):
        assert safe_evaluate("x is not None", {"x": 1}) is True
        assert safe_evaluate("x is not None", {"x": None}) is False


class TestSafeEvaluateBooleanLogic:
    def test_and_true(self):
        assert safe_evaluate("x > 0 and y > 0", {"x": 5, "y": 3}) is True

    def test_and_false(self):
        assert safe_evaluate("x > 0 and y > 10", {"x": 5, "y": 3}) is False

    def test_or(self):
        assert safe_evaluate("x == 1 or y == 2", {"x": 0, "y": 2}) is True
        assert safe_evaluate("x == 1 or y == 2", {"x": 0, "y": 0}) is False

    def test_not_unary(self):
        assert safe_evaluate("not x", {"x": False}) is True
        assert safe_evaluate("not x", {"x": True}) is False

    def test_complex_condition(self):
        assert safe_evaluate(
            "x > 0 and (y == 1 or y == 2) and z != None",
            {"x": 5, "y": 1, "z": "test"}
        ) is True

    def test_string_comparison(self):
        assert safe_evaluate("name == 'test'", {"name": "test"}) is True
        assert safe_evaluate("name == 'other'", {"name": "test"}) is False


class TestSafeEvaluateEdgeCases:
    def test_empty_expression(self):
        assert safe_evaluate("", {}) is True
        assert safe_evaluate(None, {}) is True
        assert safe_evaluate("  ", {}) is True

    def test_none_context(self):
        assert safe_evaluate("True", None) is True
        assert safe_evaluate("False", None) is False

    def test_literal_true_false_none(self):
        assert safe_evaluate("True", {}) is True
        assert safe_evaluate("False", {}) is False
        assert safe_evaluate("None is None", {}) is True

    def test_attribute_access(self):
        ctx = {"obj": type("Obj", (), {"status": "active"})()}
        assert safe_evaluate("obj.status == 'active'", ctx) is True
        assert safe_evaluate("obj.status == 'inactive'", ctx) is False

    def test_attribute_none_object(self):
        assert safe_evaluate("x.y == 'test'", {"x": None}) is False

    def test_dict_context_access(self):
        ctx = {"data": {"key": "value"}}
        assert safe_evaluate("data.key == 'value'", ctx) is True

    def test_unary_minus(self):
        assert safe_evaluate("-x == -5", {"x": 5}) is True

    def test_unary_plus(self):
        assert safe_evaluate("+x == 5", {"x": 5}) is True


class TestSafeEvaluateSecurity:
    """Verify eval() / exec() injection attempts are rejected"""

    def test_os_system_blocked(self):
        expr = "__import__('os').system('whoami')"
        assert safe_evaluate(expr, {}) is False

    def test_builtin_eval_blocked(self):
        expr = "eval('1+1')"
        assert safe_evaluate(expr, {}) is False

    def test_exec_blocked(self):
        expr = "exec('print(1)')"
        assert safe_evaluate(expr, {}) is False

    def test_open_blocked(self):
        expr = "open('/etc/passwd')"
        assert safe_evaluate(expr, {}) is False

    def test_compile_blocked(self):
        expr = "compile('', '', 'exec')"
        assert safe_evaluate(expr, {}) is False

    def test_function_call_blocked(self):
        expr = "abs(-5)"
        assert safe_evaluate(expr, {}) is False
        expr = "len('test')"
        assert safe_evaluate(expr, {}) is False
        expr = "int('123')"
        assert safe_evaluate(expr, {}) is False

    def test_import_blocked(self):
        expr = "import os"
        assert safe_evaluate(expr, {}) is False

    def test_dunder_attribute_blocked(self):
        expr = "x.__class__"
        assert safe_evaluate(expr, {"x": "test"}) is False
        expr = "x.__bases__"
        assert safe_evaluate(expr, {"x": "test"}) is False

    def test_subscript_blocked(self):
        expr = "x[0]"
        assert safe_evaluate(expr, {"x": [1, 2, 3]}) is False

    def test_arithmetic_blocked(self):
        expr = "1 + 1"
        assert safe_evaluate(expr, {}) is False
        expr = "x * 2"
        assert safe_evaluate(expr, {"x": 5}) is False

    def test_comprehension_blocked(self):
        expr = "[i for i in range(10)]"
        assert safe_evaluate(expr, {}) is False

    def test_lambda_blocked(self):
        expr = "lambda x: x"
        assert safe_evaluate(expr, {}) is False

    def test_getattr_blocked(self):
        expr = "getattr(x, 'secret')"
        assert safe_evaluate(expr, {"x": "test"}) is False

    def test_setattr_blocked(self):
        expr = "setattr(x, 'secret', 1)"
        assert safe_evaluate(expr, {"x": "test"}) is False


class TestSafeEvaluateRealWorld:
    """Test conditions matching actual usage patterns"""

    def test_deletability_condition(self):
        assert safe_evaluate("self.child_count == 0", {"self": type("Obj", (), {"child_count": 0})()}) is True
        assert safe_evaluate("self.child_count == 0", {"self": type("Obj", (), {"child_count": 3})()}) is False

    def test_constraint_condition(self):
        assert safe_evaluate("value > 0 and value < 100", {"value": 50}) is True
        assert safe_evaluate("value > 0 and value < 100", {"value": 0}) is False

    def test_scope_condition(self):
        ctx = {"domain_id": "D001", "type": "transactional"}
        assert safe_evaluate("type == 'transactional' and domain_id != None", ctx) is True

    def test_undefined_name_returns_false(self):
        assert safe_evaluate("undefined_var == 1", {}) is False
