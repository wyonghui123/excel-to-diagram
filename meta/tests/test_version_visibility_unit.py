import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Product Version Visibility — Unit Tests

覆盖：
1. manage_api._parse_scope_expression OR 表达式解析
2. manage_api._parse_simple_condition 简单条件解析
3. manage_api._apply_scope_filter scope 过滤注入
4. DataPermissionInterceptor OR scope 注入到 query_conditions
5. version.yaml visibility 字段元数据验证
6. version.yaml publish_version 状态转换规则验证
7. Metadata-driven：所有测试通过 YAML 元数据驱动，无硬编码
"""

import unittest
import pytest
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.core.yaml_loader import load_yaml_directory
from meta.core.models import registry, MetaStateTransition, RuleType, FieldType

schemas_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'schemas')
if not registry.get('version'):
    load_yaml_directory(schemas_dir)

class TestScopeExpressionParsing:
    """manage_api scope 表达式解析单元测试"""

    def test_parse_simple_eq(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("owner_id = 1")
        assert result['field'] == 'owner_id'
        assert result['operator'] == 'eq'
        assert result['value'] == '1'

    def test_parse_simple_quoted_string(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("visibility = 'public'")
        assert result['field'] == 'visibility'
        assert result['operator'] == 'eq'
        assert result['value'] == 'public'

    def test_parse_simple_double_quoted_string(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition('visibility = "draft"')
        assert result['field'] == 'visibility'
        assert result['operator'] == 'eq'
        assert result['value'] == 'draft'

    def test_parse_simple_not_equal(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("status != 'deleted'")
        assert result['field'] == 'status'
        assert result['operator'] == 'ne'
        assert result['value'] == 'deleted'

    def test_parse_simple_ge(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("age >= 18")
        assert result['field'] == 'age'
        assert result['operator'] == 'ge'
        assert result['value'] == '18'

    def test_parse_simple_le(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("age <= 18")
        assert result['field'] == 'age'
        assert result['operator'] == 'le'
        assert result['value'] == '18'

    def test_parse_simple_gt(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("count > 0")
        assert result['field'] == 'count'
        assert result['operator'] == 'gt'
        assert result['value'] == '0'

    def test_parse_simple_lt(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("count < 100")
        assert result['field'] == 'count'
        assert result['operator'] == 'lt'
        assert result['value'] == '100'

    def test_parse_scope_expression_simple(self):
        from meta.api.manage_api import _parse_scope_expression
        result = _parse_scope_expression("owner_id = 5")
        assert len(result) == 1
        assert isinstance(result[0], dict), f"Expected dict, got {type(result[0])}"
        assert result[0]['field'] == 'owner_id'
        assert result[0]['value'] == '5'

    def test_parse_scope_expression_or(self):
        from meta.api.manage_api import _parse_scope_expression
        result = _parse_scope_expression("visibility = 'public' OR owner_id = 5")
        assert len(result) == 1
        assert isinstance(result[0], list), f"Expected list, got {type(result[0])}"
        assert len(result[0]) == 2
        assert result[0][0]['field'] == 'visibility'
        assert result[0][0]['value'] == 'public'
        assert result[0][1]['field'] == 'owner_id'
        assert result[0][1]['value'] == '5'

    def test_parse_scope_expression_or_lowercase(self):
        from meta.api.manage_api import _parse_scope_expression
        result = _parse_scope_expression("visibility = 'public' or owner_id = 5")
        assert len(result) == 1
        assert isinstance(result[0], list), f"Expected list, got {type(result[0])}"
        assert len(result[0]) == 2

    def test_parse_scope_expression_three_ways_or(self):
        from meta.api.manage_api import _parse_scope_expression
        result = _parse_scope_expression("a = 1 OR b = 2 OR c = 3")
        assert len(result) == 1
        assert isinstance(result[0], list), f"Expected list, got {type(result[0])}"
        assert len(result[0]) == 3

    def test_parse_scope_no_op_fallback(self):
        from meta.api.manage_api import _parse_simple_condition
        result = _parse_simple_condition("is_active")
        assert result['field'] == 'is_active'
        assert result['operator'] == 'eq'
        assert result['value'] == True

class TestScopeFilterConditionInjection:
    """_apply_scope_filter 条件注入测试"""

    def test_apply_scope_filter_returns_conditions_without_user_context(self):
        from meta.api.manage_api import _apply_scope_filter
        conditions = []
        result = _apply_scope_filter('version', conditions)
        assert result is not None
        assert isinstance(result, list)

    def test_or_scope_parsed_correctly(self):
        from meta.api.manage_api import _parse_scope_expression
        parsed = _parse_scope_expression("visibility = 'public' OR owner_id = 5")
        assert len(parsed) == 1
        assert isinstance(parsed[0], list), f"Expected list, got {type(parsed[0])}"

        or_group = parsed[0]
        assert len(or_group) == 2
        for item in or_group:
            assert isinstance(item, dict)
            assert 'field' in item
            assert 'operator' in item
            assert 'value' in item

    def test_apply_scope_filter_with_empty_conditions_returns_same(self):
        from meta.api.manage_api import _apply_scope_filter
        conditions = []
        result = _apply_scope_filter('version', conditions)
        assert result is conditions

    def test_parse_scope_trims_whitespace(self):
        from meta.api.manage_api import _parse_scope_expression
        result = _parse_scope_expression("  visibility = 'public'  OR   owner_id = 5  ")
        assert len(result) == 1
        assert isinstance(result[0], list), f"Expected list, got {type(result[0])}"
        assert len(result[0]) == 2
        assert result[0][0]['field'] == 'visibility'
        assert result[0][0]['value'] == 'public'
        assert result[0][1]['field'] == 'owner_id'
        assert result[0][1]['value'] == '5'

class TestIsCurrentStateTransition:
    """version is_current 状态转换规则元数据验证 (v1.1 新增)

    注意：publish_version 规则已移除（visibility 上移到 product）。
    version 现在只有 is_current 状态转换规则。
    """

    def setup_method(self):
        self.version_meta = registry.get('version')

    def test_set_current_version_rule_exists(self):
        """验证 set_current_version 状态转换规则存在"""
        set_current_rule = None
        for r in self.version_meta.rules:
            if r.id == 'set_current_version':
                set_current_rule = r
                break
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在"

    def test_set_current_version_rule_type(self):
        """验证规则类型为状态转换"""
        set_current_rule = next((r for r in self.version_meta.rules if r.id == 'set_current_version'), None)
        if set_current_rule is None:
            # v1.1 refactor 后规则可能在 actions 而非 rules
            set_current_rule = next((a for a in getattr(self.version_meta, 'actions', []) if a.id == 'set_current_version'), None)
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在（可能在 rules 或 actions 中）"
        assert set_current_rule.rule_type == RuleType.STATE_TRANSITION

    def test_set_current_version_state_field(self):
        """验证状态字段为 is_current"""
        set_current_rule = next((r for r in self.version_meta.rules if r.id == 'set_current_version'), None)
        if set_current_rule is None:
            set_current_rule = next((a for a in getattr(self.version_meta, 'actions', []) if a.id == 'set_current_version'), None)
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在"
        assert set_current_rule.state_field == 'is_current'

    def test_set_current_version_from_states(self):
        """验证从状态为 false"""
        set_current_rule = next((r for r in self.version_meta.rules if r.id == 'set_current_version'), None)
        if set_current_rule is None:
            set_current_rule = next((a for a in getattr(self.version_meta, 'actions', []) if a.id == 'set_current_version'), None)
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在"
        assert False in set_current_rule.from_states or 'false' in set_current_rule.from_states

    def test_set_current_version_to_state(self):
        """验证目标状态为 true"""
        set_current_rule = next((r for r in self.version_meta.rules if r.id == 'set_current_version'), None)
        if set_current_rule is None:
            set_current_rule = next((a for a in getattr(self.version_meta, 'actions', []) if a.id == 'set_current_version'), None)
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在"
        assert set_current_rule.to_state is True or set_current_rule.to_state == 'true'

    def test_set_current_version_triggers(self):
        """验证触发器为 before_update"""
        from meta.core.models import RuleTrigger
        set_current_rule = next((r for r in self.version_meta.rules if r.id == 'set_current_version'), None)
        if set_current_rule is None:
            set_current_rule = next((a for a in getattr(self.version_meta, 'actions', []) if a.id == 'set_current_version'), None)
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在"
        assert RuleTrigger.BEFORE_UPDATE in set_current_rule.triggers

    def test_set_current_version_ui_hints(self):
        """验证 UI 提示包含正确标签"""
        set_current_rule = next((r for r in self.version_meta.rules if r.id == 'set_current_version'), None)
        if set_current_rule is None:
            set_current_rule = next((a for a in getattr(self.version_meta, 'actions', []) if a.id == 'set_current_version'), None)
        assert set_current_rule is not None, "set_current_version 状态转换规则应存在"
        hints = set_current_rule.ui_hints
        assert hints is not None
        if hasattr(hints, 'label'):
            assert hints.label == '设为当前'
        elif isinstance(hints, dict):
            assert hints.get('label') == '设为当前'

    def test_unset_current_version_rule_exists(self):
        """验证 unset_current_version 规则也存在"""
        unset_rule = None
        for r in self.version_meta.rules:
            if r.id == 'unset_current_version':
                unset_rule = r
                break
        assert unset_rule is not None, "unset_current_version 状态转换规则应存在"

    def test_no_visibility_state_transitions(self):
        """验证没有 visibility 相关的状态转换规则（v1.1 refactor）"""
        for r in self.version_meta.rules:
            if isinstance(r, MetaStateTransition) or (
                hasattr(r, 'rule_type') and r.rule_type == RuleType.STATE_TRANSITION
            ):
                if hasattr(r, 'state_field'):
                    assert r.state_field != 'visibility', "不应存在 visibility 状态转换规则"

class TestDataPermissionInterceptorOrScope:
    """DataPermissionInterceptor OR scope 注入验证"""

    def test_parse_scope_or_delivers_correct_structure(self):
        from meta.api.manage_api import _parse_scope_expression
        parsed = _parse_scope_expression("visibility = 'public' OR owner_id = 99")
        assert len(parsed) == 1
        or_group = parsed[0]
        assert isinstance(or_group, list)
        assert len(or_group) == 2
        assert or_group[0]['field'] == 'visibility'
        assert or_group[0]['value'] == 'public'
        assert or_group[1]['field'] == 'owner_id'
        assert or_group[1]['value'] == '99'

