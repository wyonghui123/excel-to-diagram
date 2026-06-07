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

class TestVersionVisibilityMetadata:
    """version.yaml visibility 字段元数据验证"""

    def setup_method(self):
        self.version_meta = registry.get('version')
        assert self.version_meta, "version 对象未在 registry 中注册" is not None

    def test_visibility_field_exists(self):
        vis_field = None
        for f in self.version_meta.fields:
            if f.id == 'visibility':
                vis_field = f
                break
        assert vis_field, "visibility 字段不存在" is not None
        assert vis_field.name == '可见性'

    def test_visibility_field_type(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        assert vis_field.field_type == FieldType.STRING

    def test_visibility_field_default(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        assert vis_field.default == 'draft'

    def test_visibility_field_required(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        assert vis_field.required

    def test_visibility_field_db_column(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        assert vis_field.db_column == 'visibility'

    def test_visibility_enum_values(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        assert vis_field.enum_values, "visibility 缺少 enum_values" is not None
        enum_vals = [ev.get('value') for ev in vis_field.enum_values]
        assert 'public' in enum_vals
        assert 'draft' in enum_vals
        assert len(enum_vals) == 2

    def test_visibility_public_enum_label(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        public_ev = next(ev for ev in vis_field.enum_values if ev.get('value') == 'public')
        assert public_ev.get('label') == '公开'

    def test_visibility_draft_enum_label(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        draft_ev = next(ev for ev in vis_field.enum_values if ev.get('value') == 'draft')
        assert draft_ev.get('label') == '草稿'

    def test_visibility_not_immutable(self):
        vis_field = next(f for f in self.version_meta.fields if f.id == 'visibility')
        semantics = getattr(vis_field, 'semantics', {})
        if isinstance(semantics, dict):
            self.assertNotEqual(semantics.get('immutable'), True)

    def test_visibility_entered_at_field_removed(self):
        vis_fields = [f for f in self.version_meta.fields if f.id == 'visibility_entered_at']
        assert len(vis_fields) == 0, "visibility_entered_at 应已删除，改用 Audit Log 推导"

class TestAuthorizationScope:
    """authorization.scope 元数据验证"""

    def setup_method(self):
        self.version_meta = registry.get('version')

    def test_authorization_enabled(self):
        auth = self.version_meta.authorization
        assert auth is not None
        if isinstance(auth, dict):
            assert auth.get('check', False)
        else:
            assert auth.check

    def test_authorization_scope_is_or_expression(self):
        auth = self.version_meta.authorization
        scope = auth.get('scope') if isinstance(auth, dict) else auth.scope
        assert 'OR' in scope.upper()
        assert 'visibility' in scope
        assert 'owner_id' in scope
        assert '$user.id' in scope

    def test_authorization_scope_parses_correctly(self):
        from meta.api.manage_api import _parse_scope_expression
        auth = self.version_meta.authorization
        scope = auth.get('scope') if isinstance(auth, dict) else auth.scope

        resolved = scope.replace('$user.id', '42')
        parsed = _parse_scope_expression(resolved)

        assert len(parsed) == 1
        assert isinstance(parsed[0], list), f"Expected list, got {type(parsed[0])}"
        or_group = parsed[0]
        assert len(or_group) == 2

        public_cond = or_group[0]
        owner_cond = or_group[1]

        assert public_cond['field'] == 'visibility'
        assert public_cond['value'] == 'public'

        assert owner_cond['field'] == 'owner_id'
        assert owner_cond['value'] == '42'

class TestPublishStateTransition:
    """draft → public 状态转换规则元数据验证"""

    def setup_method(self):
        self.version_meta = registry.get('version')

    def test_publish_transition_rule_exists(self):
        publish_rule = None
        for r in self.version_meta.rules:
            if r.id == 'publish_version':
                publish_rule = r
                break
        assert publish_rule, "publish_version 状态转换规则不存在" is not None

    def test_publish_transition_rule_type(self):
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        assert publish_rule.rule_type == RuleType.STATE_TRANSITION

    def test_publish_transition_state_field(self):
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        assert publish_rule.state_field == 'visibility'

    def test_publish_transition_from_states(self):
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        assert 'draft' in publish_rule.from_states
        assert 'public' not in publish_rule.from_states

    def test_publish_transition_to_state(self):
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        assert publish_rule.to_state == 'public'

    def test_publish_transition_triggers(self):
        from meta.core.models import RuleTrigger
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        assert RuleTrigger.BEFORE_UPDATE in publish_rule.triggers

    def test_publish_transition_ui_hints(self):
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        hints = publish_rule.ui_hints
        assert hints is not None
        if hasattr(hints, 'label'):
            assert hints.label == '发布'
        elif isinstance(hints, dict):
            assert hints.get('label') == '发布'

    def test_publish_transition_confirm_message(self):
        publish_rule = next(r for r in self.version_meta.rules if r.id == 'publish_version')
        hints = publish_rule.ui_hints
        if hasattr(hints, 'confirm_message'):
            msg = hints.confirm_message
        elif isinstance(hints, dict):
            msg = hints.get('confirm_message', '')
        assert '不可撤销' in msg

    def test_no_reverse_transition(self):
        for r in self.version_meta.rules:
            if isinstance(r, MetaStateTransition) or (
                hasattr(r, 'rule_type') and r.rule_type == RuleType.STATE_TRANSITION
            ):
                if hasattr(r, 'state_field') and r.state_field == 'visibility':
                    assert 'public' not in r.from_states, "不应存在 public → draft 的状态转换规则"

    def test_state_transition_rules_count(self):
        visibility_rules = []
        for r in self.version_meta.rules:
            if isinstance(r, MetaStateTransition) or (
                hasattr(r, 'rule_type') and r.rule_type == RuleType.STATE_TRANSITION
            ):
                if hasattr(r, 'state_field') and r.state_field == 'visibility':
                    visibility_rules.append(r)
        assert len(visibility_rules) == 1, "visibility 状态转换规则应只有 1 条（draft → public）"

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

