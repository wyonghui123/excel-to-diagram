import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Formula 计算验证测试

测试 formula 计算引擎的正确性：
- DATEDIFF 计算
- DIVIDE 安全除法
- IF 条件表达式
- ISNULL/ISBLANK 空值处理
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture
def meta_obj():
    from meta.core.models import MetaObject, ObjectType
    return MetaObject(
        id='_test',
        name='Test',
        table_name='_test',
        object_type=ObjectType.ENTITY,
        fields=[]
    )


@pytest.fixture
def rule_context(meta_obj):
    from meta.core.rule_executor import RuleContext
    return RuleContext(meta_obj, {})


class TestFormulaCalculation:
    """Formula 计算测试"""

    def test_change_event_delivery_latency_seconds_with_delivery(self, rule_context):
        """测试 change_event.delivery_latency_seconds 有交付时间的情况"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {
            'created_at': '2026-05-22 10:00:00',
            'delivered_at': '2026-05-22 10:00:45',
        }
        context = RuleContext(rule_context.meta_object, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'IF(ISNULL(delivered_at), DATEDIFF(created_at, NOW(), "seconds"), DATEDIFF(created_at, delivered_at, "seconds"))'
        result = evaluator.evaluate(formula)
        assert result == 45, f"Expected 45 seconds, got {result}"

    def test_user_inactive_days_with_last_login(self, meta_obj):
        """测试 user.inactive_days 有最后登录时间的情况"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        now = datetime.now()
        last_login = now - timedelta(days=30)
        data = {
            'created_at': '2026-01-01',
            'last_login_at': last_login.strftime('%Y-%m-%d'),
        }
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'IF(ISNULL(last_login_at), DATEDIFF(created_at, NOW(), "days"), DATEDIFF(last_login_at, NOW(), "days"))'
        result = evaluator.evaluate(formula)
        assert 29 <= result <= 31, f"Expected ~30 days, got {result}"

    def test_user_account_age_days(self, meta_obj):
        """测试 user.account_age_days 计算"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {
            'created_at': '2026-01-01',
        }
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'DATEDIFF(created_at, NOW(), "days")'
        result = evaluator.evaluate(formula)
        assert result > 100, f"Expected >100 days, got {result}"

    def test_domain_bo_density_normal(self, meta_obj):
        """测试 domain.bo_density 正常计算"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {
            'child_count': 5,
            'relation_count': 12,
        }
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'ROUND(DIVIDE(relation_count, child_count, 0), 2)'
        result = evaluator.evaluate(formula)
        assert result == 2.4, f"Expected 2.4, got {result}"

    def test_domain_bo_density_zero_child_count(self, meta_obj):
        """测试 domain.bo_density 零 child_count 情况"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {
            'child_count': 0,
            'relation_count': 0,
        }
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'IF(child_count > 0, DIVIDE(relation_count, child_count, 0), 0)'
        result = evaluator.evaluate(formula)
        assert result == 0, f"Expected 0, got {result}"

    def test_relationship_activity_label_stale(self, meta_obj):
        """测试 relationship.activity_label 超过90天为 stale"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        old_date = (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d')
        data = {'created_at': old_date}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'IF(DATEDIFF(created_at, NOW(), "days") > 90, "stale", "active")'
        result = evaluator.evaluate(formula)
        assert result == "stale", f"Expected 'stale', got {result}"

    def test_relationship_activity_label_active(self, meta_obj):
        """测试 relationship.activity_label 90天内为 active"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {'created_at': datetime.now().strftime('%Y-%m-%d')}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'IF(DATEDIFF(created_at, NOW(), "days") > 90, "stale", "active")'
        result = evaluator.evaluate(formula)
        assert result == "active", f"Expected 'active', got {result}"

    def test_safe_divide_by_zero(self, meta_obj):
        """测试 DIVIDE 函数除零保护"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {'a': 10, 'b': 0}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        formula = 'DIVIDE(a, b, -1)'
        result = evaluator.evaluate(formula)
        assert result == -1, f"Expected -1 (fallback), got {result}"

    def test_isnull_function(self, meta_obj):
        """测试 ISNULL 函数"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {'field': None}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        result = evaluator.evaluate('ISNULL(field)')
        assert result is True, f"Expected True, got {result}"

    def test_isblank_function(self, meta_obj):
        """测试 ISBLANK 函数"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {'field': ''}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        result = evaluator.evaluate('ISBLANK(field)')
        assert result is True, f"Expected True, got {result}"

    def test_coalesce_function(self, meta_obj):
        """测试 COALESCE 函数"""
        from meta.core.rule_executor import RuleContext, SafeExpressionEvaluator
        
        data = {'a': None, 'b': None}
        context = RuleContext(meta_obj, data)
        evaluator = SafeExpressionEvaluator(context)
        
        result = evaluator.evaluate('COALESCE(a, b, "default")')
        assert result == "default", f"Expected 'default', got {result}"
