# -*- coding: utf-8 -*-
"""
[FILE] test_visibility_condition_mapper.py
[DESCRIPTION] Phase 3 P3-T5 — Visibility → 条件表达式自动映射 TDD 测试
[SPEC] spec-permission-system-unification-2026-07-19 §3.18.6 / §8.3 P3-T5
[FR] FR-034

测试覆盖:
  T1: 5 种 visibility 级别正确映射
  T2: Fallback 机制 (未知值)
  T3: User 参数灵活性 (dict + object)
  T4: 安全性 (SQL 注入防护)
  T5: 边界条件 (空 user / 缺字段)
  T6: 可解析性 (生成的表达式可被 ConditionEvaluator 评估)
  T7: 批量映射辅助函数

实现状态: [TDD RED] — 模块未实现前应全部 FAIL
           visibility_condition_mapper.py 实现后应全部 PASS
"""
import pytest

pytestmark = pytest.mark.unit

import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


# ============================================================================
# T1: 5 种 visibility 级别正确映射
# ============================================================================

class TestVisibilityLevelMapping:
    """P3-T5: 5 种 visibility 级别 → 条件表达式"""

    def test_public_returns_always_true(self):
        """public → 1=1 (所有人可见)"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('public', {'id': 1})
        assert result == '1=1'

    def test_private_returns_owner_filter(self):
        """private → owner_id = {user_id}"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('private', {'id': 42})
        assert result == 'owner_id = 42'

    def test_team_returns_team_filter(self):
        """team → team_id IN ({user_team_ids})"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('team', {'id': 1, 'team_ids': [10, 20, 30]})
        assert result == 'team_id IN (10,20,30)'

    def test_department_returns_department_filter(self):
        """department → department_id = {user_department_id}"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('department', {'id': 1, 'department_id': 99})
        assert result == 'department_id = 99'

    def test_parent_returns_parent_owner_filter(self):
        """parent → parent.owner_id = {user_id} (Controlled by Parent)"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('parent', {'id': 7})
        assert result == 'parent.owner_id = 7'


# ============================================================================
# T2: Fallback 机制 (未知 visibility 值)
# ============================================================================

class TestVisibilityFallback:
    """P3-T5: 未知 visibility 值 → fallback 表达式"""

    def test_unknown_visibility_value_fallback(self):
        """未知值 → visibility = '{value}' (Spec §3.18.6 fallback)"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('custom_level', {'id': 1})
        assert result == "visibility = 'custom_level'"

    def test_empty_visibility_value(self):
        """空字符串 → 安全 fallback (1=0 deny all)"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('', {'id': 1})
        # 空值是异常输入, 安全默认为 deny all (1=0)
        # Spec §3.18.6 未明确, 但 secure-by-default 原则要求拒绝
        assert result == '1=0'

    def test_none_visibility_value(self):
        """None → fallback (不抛异常)"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition(None, {'id': 1})
        # None 应该有合理 fallback, 不抛异常
        assert isinstance(result, str)


# ============================================================================
# T3: User 参数灵活性 (dict + object)
# ============================================================================

class TestUserParameterFlexibility:
    """P3-T5: user 同时支持 dict 和 object"""

    def test_user_as_dict(self):
        """user 是 dict → 正常工作"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('private', {'id': 100, 'team_ids': [1], 'department_id': 5})
        assert result == 'owner_id = 100'

    def test_user_as_object(self):
        """user 是 object (有 .id 属性) → 正常工作"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition

        class MockUser:
            def __init__(self, user_id, team_ids=None, department_id=None):
                self.id = user_id
                self.team_ids = team_ids or []
                self.department_id = department_id

        user = MockUser(user_id=200, team_ids=[1, 2], department_id=3)
        result = generate_visibility_condition('private', user)
        assert result == 'owner_id = 200'

    def test_user_as_object_team_ids(self):
        """user 是 object + team_ids → 正常工作"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition

        class MockUser:
            def __init__(self, user_id, team_ids):
                self.id = user_id
                self.team_ids = team_ids

        user = MockUser(user_id=1, team_ids=[10, 20])
        result = generate_visibility_condition('team', user)
        assert result == 'team_id IN (10,20)'


# ============================================================================
# T4: 安全性 (SQL 注入防护)
# ============================================================================

class TestSecuritySQLInjection:
    """P3-T5: SQL 注入防护 — 强制 int 类型"""

    def test_string_user_id_rejected(self):
        """user_id 是字符串 → 类型错误或强制转换"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        # 字符串 '42' 应被拒绝 (防 SQL 注入) 或强制 int 转换
        # 不能直接拼到 SQL 里
        result = generate_visibility_condition('private', {'id': '42'})
        # 期望: 要么抛 TypeError, 要么强制转换为 int (owner_id = 42)
        assert result == 'owner_id = 42' or '42' not in result or result == '1=1'

    def test_malicious_user_id_rejected(self):
        """user_id 含 SQL 注入 → 拒绝"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        malicious = "1; DROP TABLE users"
        # 不能让恶意字符串进入 SQL
        try:
            result = generate_visibility_condition('private', {'id': malicious})
            # 如果没抛异常, 结果不能含原字符串
            assert 'DROP' not in result.upper()
            assert ';' not in result
        except (TypeError, ValueError):
            pass  # 抛异常也是合理的

    def test_team_ids_non_int_rejected(self):
        """team_ids 含非 int → 拒绝"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        try:
            result = generate_visibility_condition('team', {'id': 1, 'team_ids': [1, 'malicious', 3]})
            # 如果没抛异常, 不能含恶意字符串
            assert 'malicious' not in result
        except (TypeError, ValueError):
            pass

    def test_unknown_visibility_not_injected(self):
        """未知 visibility 值不能注入 SQL"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        malicious = "x'; DROP TABLE--"
        result = generate_visibility_condition(malicious, {'id': 1})
        # fallback 应转义或拒绝特殊字符
        assert 'DROP' not in result.upper()
        assert '--' not in result
        assert ';' not in result


# ============================================================================
# T5: 边界条件
# ============================================================================

class TestEdgeCases:
    """P3-T5: 边界条件"""

    def test_user_none_safe(self):
        """user=None → 不抛异常 (返回模板或 fallback)"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        # user=None 时, private 等级无法填充 user_id
        # 期望: 不抛异常, 返回某种安全表达式
        result = generate_visibility_condition('private', None)
        assert isinstance(result, str)

    def test_user_empty_dict(self):
        """user={} → 不抛异常"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('private', {})
        assert isinstance(result, str)

    def test_user_no_team_ids_for_team_level(self):
        """team 级别但 user 无 team_ids → team_id IN () 或 fallback"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('team', {'id': 1})
        # 无 team_ids 时应返回空 IN 或 fallback
        assert isinstance(result, str)
        # 不能让模板占位符 {user_team_ids} 残留
        assert '{' not in result

    def test_user_no_department_id_for_department_level(self):
        """department 级别但 user 无 department_id → fallback"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        result = generate_visibility_condition('department', {'id': 1})
        assert isinstance(result, str)
        assert '{' not in result


# ============================================================================
# T6: 可解析性 (生成的表达式可被 ConditionEvaluator 评估)
# ============================================================================

class TestConditionParseable:
    """P3-T5: 生成的表达式可被 ConditionEvaluator 解析"""

    def test_public_1eq1_evaluates_true(self):
        """public → 1=1 → ConditionEvaluator 评估为 True"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        from meta.services.condition_evaluator import ConditionEvaluator
        cond = generate_visibility_condition('public', {'id': 1})
        evaluator = ConditionEvaluator()
        # 1=1 应该被识别为"总是真"
        assert evaluator.evaluate(cond, {'id': 999}) is True

    def test_private_evaluates_correctly(self):
        """private → owner_id = N → ConditionEvaluator 正确判定"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        from meta.services.condition_evaluator import ConditionEvaluator
        cond = generate_visibility_condition('private', {'id': 42})
        evaluator = ConditionEvaluator()
        # owner_id=42 的资源 → True
        assert evaluator.evaluate(cond, {'owner_id': 42}) is True
        # owner_id=99 的资源 → False
        assert evaluator.evaluate(cond, {'owner_id': 99}) is False

    def test_team_evaluates_correctly(self):
        """team → team_id IN (...) → ConditionEvaluator 正确判定"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        from meta.services.condition_evaluator import ConditionEvaluator
        cond = generate_visibility_condition('team', {'id': 1, 'team_ids': [10, 20]})
        evaluator = ConditionEvaluator()
        # team_id=10 的资源 → True
        assert evaluator.evaluate(cond, {'team_id': 10}) is True
        # team_id=99 的资源 → False
        assert evaluator.evaluate(cond, {'team_id': 99}) is False

    def test_department_evaluates_correctly(self):
        """department → department_id = N → ConditionEvaluator 正确判定"""
        from meta.services.visibility_condition_mapper import generate_visibility_condition
        from meta.services.condition_evaluator import ConditionEvaluator
        cond = generate_visibility_condition('department', {'id': 1, 'department_id': 99})
        evaluator = ConditionEvaluator()
        assert evaluator.evaluate(cond, {'department_id': 99}) is True
        assert evaluator.evaluate(cond, {'department_id': 100}) is False


# ============================================================================
# T7: 批量映射辅助函数
# ============================================================================

class TestBatchMapping:
    """P3-T5: 批量映射辅助函数"""

    def test_map_all_visibility_levels(self):
        """map_all_visibility_levels(user) 返回所有 5 种级别的映射 dict"""
        from meta.services.visibility_condition_mapper import (
            generate_visibility_condition,
            map_all_visibility_levels,
        )
        user = {'id': 1, 'team_ids': [10, 20], 'department_id': 5}
        result = map_all_visibility_levels(user)
        assert isinstance(result, dict)
        assert 'public' in result
        assert 'private' in result
        assert 'team' in result
        assert 'department' in result
        assert 'parent' in result
        # 验证每个值都是字符串
        for level, cond in result.items():
            assert isinstance(cond, str), f"{level} should be str"

    def test_supported_visibility_levels_constant(self):
        """SUPPORTED_VISIBILITY_LEVELS 常量包含 5 种级别"""
        from meta.services.visibility_condition_mapper import SUPPORTED_VISIBILITY_LEVELS
        assert set(SUPPORTED_VISIBILITY_LEVELS) == {'public', 'private', 'team', 'department', 'parent'}

    def test_visibility_condition_map_template_constant(self):
        """VISIBILITY_CONDITION_MAP 模板字典存在"""
        from meta.services.visibility_condition_mapper import VISIBILITY_CONDITION_MAP
        assert 'public' in VISIBILITY_CONDITION_MAP
        assert 'private' in VISIBILITY_CONDITION_MAP
        assert 'team' in VISIBILITY_CONDITION_MAP
        assert 'department' in VISIBILITY_CONDITION_MAP
        assert 'parent' in VISIBILITY_CONDITION_MAP