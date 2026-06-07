import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
FieldPolicyInterceptor 单元测试

测试字段策略拦截器的核心逻辑：
1. 仅在 crud_create/crud_update 时触发
2. 调用 FieldPolicyValidationInterceptor 进行校验
3. 校验失败抛出 FieldPolicyViolationError
4. 用户上下文正确传递
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from meta.core.interceptors.field_policy_interceptor import FieldPolicyInterceptor
from meta.core.action_context import ActionContext
from meta.core.exceptions import FieldPolicyViolationError


def _make_meta_object(object_id='user'):
    meta = Mock()
    meta.id = object_id
    return meta


def _make_context(object_type, action, params=None, data_source=None, user_id=None, user_name=None):
    meta = _make_meta_object(object_type)
    ctx = ActionContext(
        meta_object=meta,
        action=action,
        params=params or {},
        data_source=data_source or Mock(),
        user_id=user_id,
        user_name=user_name,
    )
    return ctx


class TestFieldPolicyInterceptorProperties:

    def test_name(self):
        interceptor = FieldPolicyInterceptor()
        assert interceptor.name == "field_policy"

    def test_priority(self):
        interceptor = FieldPolicyInterceptor()
        assert interceptor.priority == 40


class TestFieldPolicyInterceptorSkipsNonCreateUpdate:

    def test_skips_read_action(self):
        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'crud_read')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_delete_action(self):
        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'crud_delete', params={'id': 1})
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_query_action(self):
        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'crud_query')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_associate_action(self):
        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'associate')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_assign_action(self):
        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'assign')
        interceptor.before_action(ctx)
        assert ctx.result is None


class TestFieldPolicyInterceptorCreate:

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_calls_validate_create_on_crud_create(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = True
        mock_validator_instance.validate_create.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context(
            'user', 'crud_create',
            params={'username': 'test', 'email': 'test@example.com'},
            user_id=1,
            user_name='admin',
        )
        interceptor.before_action(ctx)

        mock_validator_instance.validate_create.assert_called_once()
        call_args = mock_validator_instance.validate_create.call_args
        assert call_args[0][0] == {'username': 'test', 'email': 'test@example.com'}
        user_context = call_args[0][1]
        assert user_context['user_id'] == 1
        assert user_context['user_name'] == 'admin'

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_raises_error_on_invalid_create(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = False
        mock_result.get_error_message.return_value = "Field 'status' is not editable"
        mock_validator_instance.validate_create.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'crud_create', params={'status': 'active'})

        with pytest.raises(FieldPolicyViolationError, match="not editable"):
            interceptor.before_action(ctx)

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_passes_user_context_on_create(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = True
        mock_validator_instance.validate_create.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context(
            'user', 'crud_create',
            params={'username': 'newuser'},
            user_id=42,
            user_name='operator',
        )
        interceptor.before_action(ctx)

        call_args = mock_validator_instance.validate_create.call_args
        user_context = call_args[0][1]
        assert user_context == {'user_id': 42, 'user_name': 'operator'}

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_handles_none_user_context_on_create(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = True
        mock_validator_instance.validate_create.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context(
            'user', 'crud_create',
            params={'username': 'newuser'},
        )
        interceptor.before_action(ctx)

        call_args = mock_validator_instance.validate_create.call_args
        user_context = call_args[0][1]
        assert user_context == {'user_id': None, 'user_name': None}


class TestFieldPolicyInterceptorUpdate:

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_calls_validate_update_on_crud_update(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = True
        mock_validator_instance.validate_update.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context(
            'user', 'crud_update',
            params={'id': 1, 'email': 'new@example.com'},
            user_id=1,
            user_name='admin',
        )
        interceptor.before_action(ctx)

        mock_validator_instance.validate_update.assert_called_once()
        call_args = mock_validator_instance.validate_update.call_args
        assert call_args[0][0] == 1
        assert call_args[0][1] == {'email': 'new@example.com'}

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_raises_error_on_invalid_update(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = False
        mock_result.get_error_message.return_value = "Field 'username' is immutable"
        mock_validator_instance.validate_update.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'crud_update', params={'id': 1, 'username': 'changed'})

        with pytest.raises(FieldPolicyViolationError, match="immutable"):
            interceptor.before_action(ctx)

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_passes_user_context_on_update(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = True
        mock_validator_instance.validate_update.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        ctx = _make_context(
            'user', 'crud_update',
            params={'id': 1, 'email': 'new@example.com'},
            user_id=5,
            user_name='editor',
        )
        interceptor.before_action(ctx)

        call_args = mock_validator_instance.validate_update.call_args
        user_context = call_args[0][2]
        assert user_context == {'user_id': 5, 'user_name': 'editor'}


class TestFieldPolicyInterceptorAfterAction:

    def test_after_action_does_nothing(self):
        interceptor = FieldPolicyInterceptor()
        ctx = _make_context('user', 'crud_create')
        result = interceptor.after_action(ctx)
        assert result is None


class TestFieldPolicyInterceptorValidatorConstruction:

    @patch('meta.core.interceptors.field_policy_interceptor.FieldPolicyValidationInterceptor')
    def test_constructs_validator_with_meta_object(self, MockValidator):
        mock_validator_instance = Mock()
        mock_result = Mock()
        mock_result.valid = True
        mock_validator_instance.validate_create.return_value = mock_result
        MockValidator.return_value = mock_validator_instance

        interceptor = FieldPolicyInterceptor()
        meta = _make_meta_object('role')
        ds = Mock()
        ctx = ActionContext(
            meta_object=meta,
            action='crud_create',
            params={'name': 'new_role'},
            data_source=ds,
        )
        interceptor.before_action(ctx)

        MockValidator.assert_called_once_with(
            meta_object=meta,
            data_source=ds,
        )
