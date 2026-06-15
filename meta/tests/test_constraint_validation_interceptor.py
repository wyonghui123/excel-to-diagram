import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
ConstraintValidationInterceptor 单元测试

测试 §7.10.4 ConstraintValidationInterceptor 拦截器链集成：
1. priority = 42
2. before_action 调用 ConstraintEngine.validate()
3. 校验失败时抛出 ValidationFailedError
4. 错误详情包含 field_id / rule / message
"""

import pytest
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.interceptors.constraint_validation_interceptor import ConstraintValidationInterceptor
from meta.core.interceptors.base import Interceptor
from meta.core.action_context import ActionContext
from meta.core.exceptions import ValidationFailedError
from unittest.mock import Mock, MagicMock, patch


def _make_context(object_type='test_user', action='crud_create', params=None, data_source=None, user_id=None):
    meta = Mock()
    meta.id = object_type
    ctx = ActionContext(
        meta_object=meta,
        action=action,
        params=params or {},
        data_source=data_source or Mock(),
        user_id=user_id,
    )
    return ctx


class TestConstraintValidationInterceptorProperties:

    def test_name(self):
        interceptor = ConstraintValidationInterceptor()
        assert interceptor.name == 'ConstraintValidationInterceptor'

    def test_priority_is_42(self):
        interceptor = ConstraintValidationInterceptor()
        assert interceptor.priority == 42

    def test_is_subclass_of_interceptor(self):
        interceptor = ConstraintValidationInterceptor()
        assert isinstance(interceptor, Interceptor)


class TestConstraintValidationInterceptorBeforeAction:

    @patch('meta.core.interceptors.constraint_validation_interceptor.ConstraintEngine')
    def test_validation_success_passes_through(self, mock_engine_cls):
        mock_engine = MagicMock()
        mock_engine.validate.return_value = []
        mock_engine_cls.return_value = mock_engine

        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()

        interceptor.before_action(ctx)
        assert ctx.result is None

    @patch('meta.core.interceptors.constraint_validation_interceptor.ConstraintEngine')
    def test_validation_failed_raises_error(self, mock_engine_cls):
        from meta.core.constraint_engine import ConstraintViolation

        mock_engine = MagicMock()
        violation = ConstraintViolation(
            field_id='username',
            message='用户名 创建后不可修改',
            constraint_type='immutable'
        )
        mock_engine.validate.return_value = [violation]
        mock_engine_cls.return_value = mock_engine

        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()

        with pytest.raises(ValidationFailedError) as exc_info:
            interceptor.before_action(ctx)

        assert '创建后不可修改' in str(exc_info.value)

    @patch('meta.core.interceptors.constraint_validation_interceptor.ConstraintEngine')
    def test_error_contains_field_details(self, mock_engine_cls):
        from meta.core.constraint_engine import ConstraintViolation

        mock_engine = MagicMock()
        violation = ConstraintViolation(
            field_id='email',
            message='邮箱格式不正确',
            constraint_type='pattern'
        )
        mock_engine.validate.return_value = [violation]
        mock_engine_cls.return_value = mock_engine

        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()

        with pytest.raises(ValidationFailedError) as exc_info:
            interceptor.before_action(ctx)

        details = exc_info.value.details
        assert isinstance(details, list)
        assert len(details) == 1
        assert 'field_id' not in details[0]  # field_id 不暴露给前端
        assert details[0]['rule'] == 'pattern'

    @patch('meta.core.interceptors.constraint_validation_interceptor.ConstraintEngine')
    def test_multiple_violations_all_reported(self, mock_engine_cls):
        from meta.core.constraint_engine import ConstraintViolation

        mock_engine = MagicMock()
        mock_engine.validate.return_value = [
            ConstraintViolation('field1', '错误1', 'type1'),
            ConstraintViolation('field2', '错误2', 'type2'),
        ]
        mock_engine_cls.return_value = mock_engine

        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()

        with pytest.raises(ValidationFailedError) as exc_info:
            interceptor.before_action(ctx)

        details = exc_info.value.details
        assert len(details) == 2

    @patch('meta.core.interceptors.constraint_validation_interceptor.ConstraintEngine')
    def test_error_message_joined_by_semicolon(self, mock_engine_cls):
        from meta.core.constraint_engine import ConstraintViolation

        mock_engine = MagicMock()
        mock_engine.validate.return_value = [
            ConstraintViolation('field1', '错误一', 'type1'),
            ConstraintViolation('field2', '错误二', 'type2'),
        ]
        mock_engine_cls.return_value = mock_engine

        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()

        with pytest.raises(ValidationFailedError) as exc_info:
            interceptor.before_action(ctx)

        assert '错误一' in str(exc_info.value)
        assert '错误二' in str(exc_info.value)

    @patch('meta.core.interceptors.constraint_validation_interceptor.ConstraintEngine')
    def test_calls_engine_with_context(self, mock_engine_cls):
        mock_engine = MagicMock()
        mock_engine.validate.return_value = []
        mock_engine_cls.return_value = mock_engine

        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()

        interceptor.before_action(ctx)

        mock_engine.validate.assert_called_once_with(ctx)


class TestConstraintValidationInterceptorAfterAction:

    def test_after_action_does_nothing(self):
        interceptor = ConstraintValidationInterceptor()
        ctx = _make_context()
        result = interceptor.after_action(ctx)
        assert result is None


class TestInterceptorChainPosition:

    def test_priority_after_field_policy(self):
        from meta.core.interceptors.field_policy_interceptor import FieldPolicyInterceptor
        field_policy = FieldPolicyInterceptor()
        constraint = ConstraintValidationInterceptor()
        assert constraint.priority > field_policy.priority

    def test_priority_after_association(self):
        from meta.core.interceptors.association_interceptor import AssociationInterceptor
        constraint = ConstraintValidationInterceptor()
        assoc = AssociationInterceptor()
        assert constraint.priority > assoc.priority


class TestConditionalRequired:
    """[NEW] COV-005: _check_conditional_required 专项测试 (12 用例)

    FR-4.1: 条件必填校验 — 当 condition 求值为 True 时，字段变必填
    """

    def _make_engine(self):
        from meta.core.constraint_engine import ConstraintEngine
        return ConstraintEngine()

    def _make_field(self, fid, name=None):
        f = Mock()
        f.id = fid
        f.name = name or fid
        return f

    def _make_ctx(self, action='crud_create', params=None, old_data=None):
        meta = Mock()
        meta.id = 'test'
        return ActionContext(
            meta_object=meta,
            action=action,
            params=params or {},
            old_data=old_data or {},
            data_source=Mock(),
        )

    def test_read_action_skips_check(self):
        """read action 不触发条件必填"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",  # 永远 True
        }
        ctx = self._make_ctx(action='crud_query', params={})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is None

    def test_update_action_triggers_check(self):
        """update action 同样触发条件必填"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",
        }
        ctx = self._make_ctx(action='crud_update', params={'sub_id': None})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is not None

    def test_delete_action_skips_check(self):
        """delete action 不触发条件必填"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",
        }
        ctx = self._make_ctx(action='crud_delete', params={})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is None

    def test_empty_condition_string_returns_none(self):
        """condition 字符串为空 → 不校验"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {'type': 'conditional_required', 'condition': ''}
        ctx = self._make_ctx(params={})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is None

    def test_condition_eval_exception_returns_none(self):
        """condition 表达式异常 → 静默返回 None（不阻断）"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "params['nonexistent_key'].foo.bar",  # 抛出 KeyError
        }
        ctx = self._make_ctx(params={})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is None

    def test_custom_message_in_violation(self):
        """自定义 message 出现在 violation 中"""
        engine = self._make_engine()
        field = self._make_field('sub_id', name='子ID')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",
            'message': '自定义错误消息',
        }
        ctx = self._make_ctx(params={'sub_id': None})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is not None
        assert v.message == '自定义错误消息'

    def test_default_message_uses_field_name(self):
        """未提供 message 时使用字段名 + '为条件必填字段'"""
        engine = self._make_engine()
        field = self._make_field('sub_id', name='子ID')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",
        }
        ctx = self._make_ctx(params={'sub_id': None})
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is not None
        assert '子ID' in v.message
        assert '条件必填' in v.message

    def test_value_comparison_in_condition(self):
        """condition 中可访问 value（当前字段值）"""
        engine = self._make_engine()
        field = self._make_field('type')
        constraint = {
            'type': 'conditional_required',
            'condition': "value == 'special'",
        }
        ctx = self._make_ctx(params={'type': 'special'})
        # 字段已填（'special'），不应违反
        v = engine._check_conditional_required(ctx, field, constraint)
        assert v is None

    def test_constraint_routes_conditional_required_to_handler(self):
        """_check_constraint 路由 conditional_required 类型到 _check_conditional_required"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",  # 永远 True
        }
        ctx = self._make_ctx(params={'sub_id': None})
        v = engine._check_constraint(ctx, field, constraint)
        # 应路由到 _check_conditional_required 并返回 violation
        assert v is not None
        assert v.constraint_type == 'conditional_required'

    def test_constraint_returns_none_when_no_value_and_no_condition(self):
        """_check_constraint 无 condition 时直接跳过校验"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            # 无 condition
        }
        ctx = self._make_ctx(params={'sub_id': None})
        v = engine._check_constraint(ctx, field, constraint)
        assert v is None

    def test_constraint_with_field_value_skips_check(self):
        """_check_constraint 字段已填 → 不违规"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",
        }
        ctx = self._make_ctx(params={'sub_id': 'filled'})
        v = engine._check_constraint(ctx, field, constraint)
        assert v is None

    def test_constraint_for_read_action_returns_none(self):
        """_check_constraint 对 read action 跳过"""
        engine = self._make_engine()
        field = self._make_field('sub_id')
        constraint = {
            'type': 'conditional_required',
            'condition': "True",
        }
        ctx = self._make_ctx(action='crud_query', params={})
        v = engine._check_constraint(ctx, field, constraint)
        assert v is None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
