import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Formula 集成测试

测试 formula 函数的完整集成：
- SafeExpressionEvaluator
- ExpressionEvaluator 包装器
- FormulaFunctionRegistry
- 安全函数限制
"""

import pytest
import sys
import os
from datetime import date, datetime

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def meta_obj():
    from meta.core.models import MetaObject, MetaField, FieldType, ObjectType
    return MetaObject(
        id='test_obj',
        name='Test Object',
        table_name='test_objects',
        object_type=ObjectType.ENTITY,
        fields=[
            MetaField(id='name', name='Name', field_type=FieldType.STRING, db_column='name'),
            MetaField(id='amount', name='Amount', field_type=FieldType.INTEGER, db_column='amount'),
            MetaField(id='status', name='Status', field_type=FieldType.STRING, db_column='status'),
            MetaField(id='created_at', name='Created At', field_type=FieldType.DATETIME, db_column='created_at'),
        ]
    )


@pytest.fixture
def data():
    return {
        'name': 'Test Record',
        'amount': 100,
        'status': 'active',
        'created_at': '2026-01-15',
    }


@pytest.fixture
def context(meta_obj, data):
    from meta.core.rule_executor import RuleContext
    return RuleContext(meta_obj, data)


@pytest.fixture
def evaluator(context):
    from meta.core.rule_executor import SafeExpressionEvaluator
    return SafeExpressionEvaluator(context)


class TestFormulaIntegration:
    """Formula 集成测试"""

    def test_basic_expressions(self, evaluator):
        """测试基本表达式"""
        assert evaluator.evaluate('amount > 50') is True
        assert evaluator.evaluate('status == "active"') is True

    def test_string_functions(self, evaluator):
        """测试字符串函数"""
        assert evaluator.evaluate('UPPER(name)') == 'TEST RECORD'
        assert evaluator.evaluate('CONCAT(name, " - ", status)') == 'Test Record - active'

    def test_math_functions(self, evaluator):
        """测试数学函数"""
        assert evaluator.evaluate('ROUND(amount * 1.1, 2)') == 110.0

    def test_conditional_functions(self, evaluator):
        """测试条件函数"""
        assert evaluator.evaluate('IF(amount > 50, "high", "low")') == 'high'

    def test_coalesce_function(self, evaluator):
        """测试 COALESCE 函数"""
        assert evaluator.evaluate('COALESCE(None, None, "default")') == "default"

    def test_isnull_function(self, evaluator):
        """测试 ISNULL 函数"""
        assert evaluator.evaluate('ISNULL(None)') is True

    def test_isblank_function(self, evaluator):
        """测试 ISBLANK 函数"""
        assert evaluator.evaluate('ISBLANK("")') is True

    def test_length_function(self, evaluator):
        """测试 LENGTH 函数"""
        assert evaluator.evaluate('LENGTH(name)') == 11

    def test_contains_function(self, evaluator):
        """测试 CONTAINS 函数"""
        assert evaluator.evaluate('CONTAINS(name, "Test")') is True

    def test_starts_with_function(self, evaluator):
        """测试 STARTS_WITH 函数"""
        assert evaluator.evaluate('STARTS_WITH(name, "Test")') is True

    def test_ends_with_function(self, evaluator):
        """测试 ENDS_WITH 函数"""
        assert evaluator.evaluate('ENDS_WITH(name, "Record")') is True

    def test_date_functions(self, evaluator):
        """测试日期函数"""
        assert evaluator.evaluate('YEAR(created_at)') == 2026
        assert evaluator.evaluate('MONTH(created_at)') == 1
        assert evaluator.evaluate('DAY(created_at)') == 15

    def test_complex_formula_bo_density(self, evaluator):
        """测试复杂公式 - BO density"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        data2 = {'child_count': 5, 'relation_count': 12}
        context2 = RuleContext(evaluator.context.meta_object, data2)
        evaluator2 = SafeExpressionEvaluator(context2)
        result = evaluator2.evaluate('IF(child_count > 0, ROUND(relation_count / child_count, 2), 0)')
        assert result == 2.4

    def test_expression_evaluator_wrapper(self, context):
        """测试 ExpressionEvaluator 包装器"""
        from meta.core.rule_executor import ExpressionEvaluator
        result = ExpressionEvaluator.evaluate('UPPER(status)', context)
        assert result == 'ACTIVE'

    def test_security_forbidden_functions_blocked(self, evaluator):
        """测试安全 - 禁用函数被阻止"""
        result = evaluator.evaluate('open("test.txt")')
        assert result is None

    def test_cross_object_context(self, meta_obj):
        """测试跨对象上下文"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {'customer_id': 42, 'name': 'Order1'}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        result = evaluator.evaluate('IF(ISNULL(customer_id), "no customer", "has customer")')
        assert result == "has customer"

    def test_dynamic_function_registration(self, evaluator):
        """测试动态函数注册"""
        from meta.core.formula_functions import FormulaFunctionRegistry
        
        FormulaFunctionRegistry.register('DOUBLE', lambda x: x * 2)
        try:
            assert evaluator.evaluate('DOUBLE(amount)') == 200
        finally:
            FormulaFunctionRegistry.unregister('DOUBLE')


class TestFormulaExpressionEvaluator:
    """ExpressionEvaluator 包装器测试"""

    def test_evaluate_with_rule_context(self, meta_obj):
        """测试字符串表达式求值"""
        from meta.core.rule_executor import ExpressionEvaluator, RuleContext
        
        data = {'x': 10}
        context = RuleContext(meta_obj, data)
        
        result = ExpressionEvaluator.evaluate('x * 2', context)
        assert result == 20

    def test_evaluate_with_context_data(self, meta_obj):
        """测试从 context 读取数据"""
        from meta.core.rule_executor import ExpressionEvaluator, RuleContext
        
        data = {'value': 42}
        context = RuleContext(meta_obj, data)
        
        result = ExpressionEvaluator.evaluate('value + 8', context)
        assert result == 50
