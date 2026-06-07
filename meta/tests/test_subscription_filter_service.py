import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
订阅过滤条件解析器测试
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.services.subscription_filter_service import (
    FilterParser,
    SubscriptionFilter,
    FilterExpression,
    Condition,
    AndExpression,
    OrExpression,
    NotExpression,
    Operator
)


class TestFilterParser:
    """过滤条件解析器测试"""

    def test_parse_simple_eq_condition(self):
        """测试解析简单等于条件"""
        parser = FilterParser()
        
        result = parser.parse({"field": "status", "op": "eq", "value": "active"})
        
        assert result is not None
        assert isinstance(result, Condition)
        assert result.field == "status"
        assert result.operator == Operator.EQ
        assert result.value == "active"

    def test_parse_string_condition(self):
        """测试解析字符串条件"""
        parser = FilterParser()
        
        result = parser.parse("status = 'active'")
        
        assert result is not None
        assert result.field == "status"
        assert result.operator == Operator.EQ
        assert result.value == "active"

    def test_parse_gt_condition(self):
        """测试解析大于条件"""
        parser = FilterParser()
        
        result = parser.parse({"field": "count", "op": "gt", "value": 10})
        
        assert result is not None
        assert result.operator == Operator.GT
        assert result.value == 10

    def test_parse_contains_condition(self):
        """测试解析包含条件"""
        parser = FilterParser()
        
        result = parser.parse({"field": "name", "op": "contains", "value": "test"})
        
        assert result is not None
        assert result.operator == Operator.CONTAINS

    def test_parse_and_expression(self):
        """测试解析 AND 表达式"""
        parser = FilterParser()
        
        config = {
            "and": [
                {"field": "status", "op": "eq", "value": "active"},
                {"field": "type", "op": "eq", "value": "A"}
            ]
        }
        
        result = parser.parse(config)
        
        assert result is not None
        assert isinstance(result, AndExpression)
        assert len(result.conditions) == 2

    def test_parse_or_expression(self):
        """测试解析 OR 表达式"""
        parser = FilterParser()
        
        config = {
            "or": [
                {"field": "status", "op": "eq", "value": "active"},
                {"field": "status", "op": "eq", "value": "pending"}
            ]
        }
        
        result = parser.parse(config)
        
        assert result is not None
        assert isinstance(result, OrExpression)
        assert len(result.conditions) == 2

    def test_parse_not_expression(self):
        """测试解析 NOT 表达式"""
        parser = FilterParser()
        
        config = {
            "not": {"field": "deleted", "op": "eq", "value": True}
        }
        
        result = parser.parse(config)
        
        assert result is not None
        assert isinstance(result, NotExpression)

    def test_parse_list_conditions(self):
        """测试解析条件列表"""
        parser = FilterParser()
        
        config = [
            {"field": "status", "op": "eq", "value": "active"},
            {"field": "type", "op": "eq", "value": "A"}
        ]
        
        result = parser.parse(config)
        
        assert result is not None
        assert isinstance(result, AndExpression)

    def test_parse_nested_expression(self):
        """测试解析嵌套表达式"""
        parser = FilterParser()
        
        config = {
            "and": [
                {"field": "status", "op": "eq", "value": "active"},
                {
                    "or": [
                        {"field": "type", "op": "eq", "value": "A"},
                        {"field": "type", "op": "eq", "value": "B"}
                    ]
                }
            ]
        }
        
        result = parser.parse(config)
        
        assert result is not None
        assert isinstance(result, AndExpression)
        assert len(result.conditions) == 2
        assert isinstance(result.conditions[1], OrExpression)

    def test_parse_string_with_and(self):
        """测试解析带 AND 的字符串"""
        parser = FilterParser()
        
        result = parser.parse("status = 'active' AND type = 'A'")
        
        assert result is not None
        assert isinstance(result, AndExpression)

    def test_parse_string_with_or(self):
        """测试解析带 OR 的字符串"""
        parser = FilterParser()
        
        result = parser.parse("status = 'active' OR status = 'pending'")
        
        assert result is not None
        assert isinstance(result, OrExpression)

    def test_parse_exists_condition(self):
        """测试解析 EXISTS 条件"""
        parser = FilterParser()
        
        result = parser.parse("description exists")
        
        assert result is not None
        assert result.operator == Operator.EXISTS


class TestConditionEvaluation:
    """条件评估测试"""

    def test_eq_true(self):
        """测试等于为真"""
        condition = Condition(field="status", operator=Operator.EQ, value="active")
        data = {"status": "active"}
        
        assert condition.evaluate(data) is True

    def test_eq_false(self):
        """测试等于为假"""
        condition = Condition(field="status", operator=Operator.EQ, value="active")
        data = {"status": "inactive"}
        
        assert condition.evaluate(data) is False

    def test_ne_true(self):
        """测试不等于为真"""
        condition = Condition(field="status", operator=Operator.NE, value="deleted")
        data = {"status": "active"}
        
        assert condition.evaluate(data) is True

    def test_gt_true(self):
        """测试大于为真"""
        condition = Condition(field="count", operator=Operator.GT, value=10)
        data = {"count": 15}
        
        assert condition.evaluate(data) is True

    def test_gt_false(self):
        """测试大于为假"""
        condition = Condition(field="count", operator=Operator.GT, value=10)
        data = {"count": 5}
        
        assert condition.evaluate(data) is False

    def test_contains_true(self):
        """测试包含为真"""
        condition = Condition(field="name", operator=Operator.CONTAINS, value="test")
        data = {"name": "my test item"}
        
        assert condition.evaluate(data) is True

    def test_contains_case_insensitive(self):
        """测试包含不区分大小写"""
        condition = Condition(field="name", operator=Operator.CONTAINS, value="TEST")
        data = {"name": "my Test item"}
        
        assert condition.evaluate(data) is True

    def test_starts_with_true(self):
        """测试以...开始为真"""
        condition = Condition(field="name", operator=Operator.STARTS_WITH, value="test")
        data = {"name": "test_item"}
        
        assert condition.evaluate(data) is True

    def test_ends_with_true(self):
        """测试以...结束为真"""
        condition = Condition(field="name", operator=Operator.ENDS_WITH, value="_item")
        data = {"name": "test_item"}
        
        assert condition.evaluate(data) is True

    def test_in_true(self):
        """测试 IN 为真"""
        condition = Condition(field="status", operator=Operator.IN, value=["active", "pending"])
        data = {"status": "active"}
        
        assert condition.evaluate(data) is True

    def test_not_in_true(self):
        """测试 NOT IN 为真"""
        condition = Condition(field="status", operator=Operator.NOT_IN, value=["deleted", "archived"])
        data = {"status": "active"}
        
        assert condition.evaluate(data) is True

    def test_exists_true(self):
        """测试 EXISTS 为真"""
        condition = Condition(field="description", operator=Operator.EXISTS, value=None)
        data = {"description": "some text"}
        
        assert condition.evaluate(data) is True

    def test_exists_false(self):
        """测试 EXISTS 为假"""
        condition = Condition(field="description", operator=Operator.EXISTS, value=None)
        data = {}
        
        assert condition.evaluate(data) is False

    def test_not_exists_true(self):
        """测试 NOT EXISTS 为真"""
        condition = Condition(field="description", operator=Operator.NOT_EXISTS, value=None)
        data = {}
        
        assert condition.evaluate(data) is True


class TestAndExpression:
    """AND 表达式测试"""

    def test_and_all_true(self):
        """测试 AND 全部为真"""
        expr = AndExpression(conditions=[
            Condition(field="status", operator=Operator.EQ, value="active"),
            Condition(field="type", operator=Operator.EQ, value="A")
        ])
        data = {"status": "active", "type": "A"}
        
        assert expr.evaluate(data) is True

    def test_and_one_false(self):
        """测试 AND 一个为假"""
        expr = AndExpression(conditions=[
            Condition(field="status", operator=Operator.EQ, value="active"),
            Condition(field="type", operator=Operator.EQ, value="A")
        ])
        data = {"status": "inactive", "type": "A"}
        
        assert expr.evaluate(data) is False


class TestOrExpression:
    """OR 表达式测试"""

    def test_or_one_true(self):
        """测试 OR 一个为真"""
        expr = OrExpression(conditions=[
            Condition(field="status", operator=Operator.EQ, value="active"),
            Condition(field="status", operator=Operator.EQ, value="pending")
        ])
        data = {"status": "active"}
        
        assert expr.evaluate(data) is True

    def test_or_all_false(self):
        """测试 OR 全部为假"""
        expr = OrExpression(conditions=[
            Condition(field="status", operator=Operator.EQ, value="active"),
            Condition(field="status", operator=Operator.EQ, value="pending")
        ])
        data = {"status": "deleted"}
        
        assert expr.evaluate(data) is False


class TestNotExpression:
    """NOT 表达式测试"""

    def test_not_true(self):
        """测试 NOT 取反"""
        expr = NotExpression(condition=Condition(
            field="deleted", operator=Operator.EQ, value=True
        ))
        data = {"deleted": False}
        
        assert expr.evaluate(data) is True


class TestSubscriptionFilter:
    """订阅过滤器测试"""

    def test_matches_no_condition(self):
        """测试无过滤条件时匹配"""
        filter_service = SubscriptionFilter()
        event_data = {"object_type": "business_object", "event_type": "created"}
        
        assert filter_service.matches(None, event_data) is True

    def test_matches_simple_condition(self):
        """测试简单条件匹配"""
        filter_service = SubscriptionFilter()
        event_data = {
            "object_type": "business_object",
            "event_type": "created",
            "changed_fields": ["name"]
        }
        
        condition = {"field": "event_type", "op": "eq", "value": "created"}
        
        assert filter_service.matches(condition, event_data) is True

    def test_matches_complex_condition(self):
        """测试复杂条件匹配"""
        filter_service = SubscriptionFilter()
        event_data = {
            "object_type": "business_object",
            "event_type": "updated",
            "changed_fields": ["status"]
        }
        
        condition = {
            "and": [
                {"field": "object_type", "op": "eq", "value": "business_object"},
                {"field": "event_type", "op": "in", "value": ["created", "updated"]},
                {"field": "changed_fields", "op": "contains", "value": "status"}
            ]
        }
        
        assert filter_service.matches(condition, event_data) is True

    def test_matches_subscription(self):
        """测试订阅匹配"""
        filter_service = SubscriptionFilter()
        
        subscription = {
            "filter_condition": {"field": "event_type", "op": "eq", "value": "created"}
        }
        event_data = {"event_type": "created", "object_type": "business_object"}
        
        assert filter_service.matches_subscription(subscription, event_data) is True

    def test_matches_subscription_json_condition(self):
        """测试订阅匹配（JSON 格式过滤条件）"""
        filter_service = SubscriptionFilter()
        
        subscription = {
            "filter_condition": '{"field": "event_type", "op": "eq", "value": "created"}'
        }
        event_data = {"event_type": "created", "object_type": "business_object"}
        
        assert filter_service.matches_subscription(subscription, event_data) is True

    def test_matches_subscription_no_filter(self):
        """测试订阅无过滤条件时匹配"""
        filter_service = SubscriptionFilter()
        
        subscription = {}
        event_data = {"event_type": "created"}
        
        assert filter_service.matches_subscription(subscription, event_data) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
