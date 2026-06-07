import pytest

pytestmark = pytest.mark.unit

import pytest
from meta.core.condition_evaluator import (
    ConditionEvaluator,
    _FieldAccessor,
)


class TestConditionEvaluatorBasic:
    """测试条件评估器基础功能"""

    def test_empty_condition_returns_true(self):
        """空条件返回 True"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("") is True
        assert evaluator.evaluate("   ") is True
        assert evaluator.evaluate(None) is True

    def test_simple_equality(self):
        """简单等式判断"""
        evaluator = ConditionEvaluator()
        result = evaluator.evaluate("status == 'active'", {"status": "active"})
        assert result is True

    def test_simple_inequality(self):
        """简单不等式判断"""
        evaluator = ConditionEvaluator()
        result = evaluator.evaluate("status != 'inactive'", {"status": "active"})
        assert result is True

    def test_numeric_comparison(self):
        """数值比较"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("count > 0", {"count": 5}) is True
        assert evaluator.evaluate("count > 10", {"count": 5}) is False
        assert evaluator.evaluate("age >= 18", {"age": 18}) is True
        assert evaluator.evaluate("age < 18", {"age": 17}) is True
        assert evaluator.evaluate("age <= 17", {"age": 17}) is True

    def test_logical_and(self):
        """逻辑 AND"""
        evaluator = ConditionEvaluator()
        context = {"is_active": True, "is_verified": True}
        assert evaluator.evaluate("is_active and is_verified", context) is True

        context["is_verified"] = False
        assert evaluator.evaluate("is_active and is_verified", context) is False

    def test_logical_or(self):
        """逻辑 OR"""
        evaluator = ConditionEvaluator()
        context = {"role": "admin"}
        assert evaluator.evaluate("role == 'admin' or role == 'superadmin'", context) is True

        context["role"] = "user"
        assert evaluator.evaluate("role == 'admin' or role == 'superadmin'", context) is False

    def test_logical_not(self):
        """逻辑 NOT"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("not is_deleted", {"is_deleted": False}) is True
        assert evaluator.evaluate("not is_deleted", {"is_deleted": True}) is False


class TestFieldAccessor:
    """测试字段访问器"""

    def test_dict_field_access(self):
        """字典字段访问"""
        accessor = _FieldAccessor({"name": "test", "value": 42})
        assert accessor.name == "test"
        assert accessor.value == 42

    def test_none_data_returns_empty_accessor(self):
        """None 数据返回空访问器"""
        accessor = _FieldAccessor(None)
        assert accessor.get("name") is None
        assert bool(accessor) is False

    def test_non_dict_data_wraps(self):
        """非字典数据包装为 value 字段"""
        accessor = _FieldAccessor("simple_value")
        assert accessor.value == "simple_value"

    def test_numeric_defaults_for_none_fields(self):
        """None 数值字段的默认值"""
        accessor = _FieldAccessor({"name": "test"})
        assert accessor.count == 0
        assert accessor.relation_count == 0
        assert accessor.child_count == 0

    def test_contains_check(self):
        """包含检查"""
        accessor = _FieldAccessor({"key1": "val1"})
        assert ("key1" in accessor) is True
        assert ("key2" in accessor) is False

    def test_equality_comparison(self):
        """相等性比较"""
        data = {"id": 1}
        accessor = _FieldAccessor(data)
        assert (accessor == data) is True
        assert (accessor != {"id": 2}) is True

    def test_get_with_default(self):
        """带默认值的 get 方法"""
        accessor = _FieldAccessor({"name": "test"})
        assert accessor.get("name") == "test"
        assert accessor.get("missing", "default") == "default"


class TestConditionEvaluatorWithSelf:
    """测试 self 对象访问"""

    def test_self_field_access(self):
        """通过 self 访问字段"""
        evaluator = ConditionEvaluator()
        context = {
            "self": {"can_delete": True, "relation_count": 5}
        }
        assert evaluator.evaluate("self.can_delete == True", context) is True
        assert evaluator.evaluate("self.relation_count > 0", context) is True

    def test_self_null_relation_count_default_zero(self):
        """relation_count 为 None 时默认为 0"""
        evaluator = ConditionEvaluator()
        context = {"self": {"relation_count": None}}
        assert evaluator.evaluate("self.relation_count == 0", context) is True

    def test_parent_field_access(self):
        """通过 parent 访问父对象字段"""
        evaluator = ConditionEvaluator()
        context = {
            "self": {"code": "CHILD"},
            "parent": {"code": "PARENT"}
        }
        assert evaluator.evaluate(
            "self.code != parent.code", context
        ) is True


class TestConditionEvaluatorEdgeCases:
    """测试边界情况和错误处理"""

    def test_invalid_expression_returns_false(self):
        """无效表达式返回 False（安全）"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("undefined_var == 123", {}) is False

    def test_malformed_syntax_returns_false(self):
        """语法错误返回 False"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("if x then y", {}) is False

    def test_safe_names_available(self):
        """安全名称可用"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("True") is True
        assert evaluator.evaluate("False") is False
        assert evaluator.evaluate("None == None") is True
        assert evaluator.evaluate("true") is True
        assert evaluator.evaluate("false") is False
        assert evaluator.evaluate("null == None") is True

    def test_no_builtin_access(self):
        """禁止访问内置函数"""
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate("__import__('os')", {}) is False

    def test_context_override(self):
        """上下文覆盖初始上下文"""
        evaluator = ConditionEvaluator(context={"x": 10})
        assert evaluator.evaluate("x == 10") is True
        assert evaluator.evaluate("x == 20", {"x": 20}) is True


class TestEvaluateWithMessage:
    """测试带消息的评估"""

    def test_success_returns_true_and_empty_message(self):
        """成功时返回 True 和空消息"""
        evaluator = ConditionEvaluator()
        result, message = evaluator.evaluate_with_message(
            "status == 'active'",
            "状态不正确",
            {"status": "active"}
        )
        assert result is True
        assert message == ""

    def test_failure_returns_false_and_message(self):
        """失败时返回 False 和错误消息"""
        evaluator = ConditionEvaluator()
        result, message = evaluator.evaluate_with_message(
            "status == 'active'",
            "状态必须为激活",
            {"status": "inactive"}
        )
        assert result is False
        assert message == "状态必须为激活"

    def test_empty_condition_always_success(self):
        """空条件总是成功"""
        evaluator = ConditionEvaluator()
        result, message = evaluator.evaluate_with_message("", "不应触发")
        assert result is True
        assert message == ""


class TestRealWorldConditions:
    """真实业务场景的条件评估"""

    def test_deletability_condition(self):
        """可删除性判断：无子对象且无关联关系"""
        evaluator = ConditionEvaluator()
        record = {
            "self": {
                "child_count": 0,
                "relation_count": 0,
            }
        }
        condition = "self.child_count == 0 and self.relation_count == 0"
        assert evaluator.evaluate(condition, record) is True

    def test_deletability_blocked_by_children(self):
        """有子对象时不可删除"""
        evaluator = ConditionEvaluator()
        record = {
            "self": {
                "child_count": 3,
                "relation_count": 0,
            }
        }
        condition = "self.child_count == 0 and self.relation_count == 0"
        assert evaluator.evaluate(condition, record) is False

    def test_deletability_blocked_by_relations(self):
        """有关联关系时不可删除"""
        evaluator = ConditionEvaluator()
        record = {
            "self": {
                "child_count": 0,
                "relation_count": 2,
            }
        }
        condition = "self.child_count == 0 and self.relation_count == 0"
        assert evaluator.evaluate(condition, record) is False

    def test_action_precondition_version_match(self):
        """操作前置条件：版本匹配"""
        evaluator = ConditionEvaluator()
        record = {
            "self": {"version": 5},
            "expected_version": 5,
        }
        assert evaluator.evaluate("self.version == expected_version", record) is True

    def test_action_precondition_version_mismatch(self):
        """操作前置条件：版本不匹配"""
        evaluator = ConditionEvaluator()
        record = {
            "self": {"version": 3},
            "expected_version": 5,
        }
        assert evaluator.evaluate("self.version == expected_version", record) is False

    def test_complex_business_rule(self):
        """复杂业务规则组合"""
        evaluator = ConditionEvaluator()
        record = {
            "self": {
                "status": "approved",
                "amount": 10000,
                "department": "finance",
            },
            "user_role": "manager",
        }
        condition = (
            "(self.status == 'approved' or user_role == 'admin') "
            "and self.amount < 50000 "
            "and self.department != 'hr'"
        )
        assert evaluator.evaluate(condition, record) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
