import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
EnumProtectionInterceptor 单元测试

测试枚举保护拦截器的核心逻辑：
1. 系统枚举保护（category = 'system'）：不可修改/删除
2. 锁定枚举保护（mutability = 'locked'）：不可增删改
3. 系统预置值保护（is_system = 1）：不可删除
4. 非 enum 对象应被跳过
"""

import pytest
from unittest.mock import MagicMock, Mock, patch

from meta.core.interceptors.enum_protection_interceptor import EnumProtectionInterceptor
from meta.core.action_context import ActionContext, ActionResult


def _make_meta_object(object_id):
    meta = Mock()
    meta.id = object_id
    return meta


def _make_context(object_type, action, params=None, old_data=None, data_source=None):
    meta = _make_meta_object(object_type)
    ctx = ActionContext(
        meta_object=meta,
        action=action,
        params=params or {},
        data_source=data_source or Mock(),
        old_data=old_data,
    )
    return ctx


def _make_data_source_with_enum_type(enum_type_data):
    ds = Mock()
    cursor = Mock()
    if enum_type_data:
        cols = list(enum_type_data.keys())
        row = tuple(enum_type_data.values())
        cursor.fetchone.return_value = row
        cursor.description = [(c, None, None, None, None, None, None) for c in cols]
    else:
        cursor.fetchone.return_value = None
    ds.execute.return_value = cursor
    return ds


def _make_data_source_with_enum_values(count):
    ds = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = (count,)
    ds.execute.return_value = cursor
    return ds


class TestEnumProtectionInterceptorProperties:

    def test_name(self):
        interceptor = EnumProtectionInterceptor()
        assert interceptor.name == "enum_protection"

    def test_priority(self):
        interceptor = EnumProtectionInterceptor()
        assert interceptor.priority == 35


class TestEnumProtectionInterceptorSkipsNonEnum:

    def test_skips_user_object(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context('user', 'crud_create', params={'username': 'test'})
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_role_object(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context('role', 'crud_update', params={'name': 'admin'})
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_non_crud_action(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context('enum_type', 'crud_read')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_query_action(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context('enum_value', 'crud_query')
        interceptor.before_action(ctx)
        assert ctx.result is None


class TestEnumProtectionInterceptorCreate:

    def test_blocks_create_value_for_locked_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'name': 'status', 'code': 'status',
            'mutability': 'locked', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'value': 'new_val'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'ENUM_LOCKED' in ctx.result.errors

    def test_allows_create_value_for_extensible_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'name': 'status', 'code': 'status',
            'mutability': 'extensible', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'value': 'new_val'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_allows_create_value_for_fully_editable_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'name': 'status', 'code': 'status',
            'mutability': 'fully_editable', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1, 'value': 'new_val'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_create_without_enum_type_id(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'value': 'new_val'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_create_for_enum_type_object(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_create',
            params={'name': 'new_type'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_create_when_enum_type_not_found(self):
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = None
        ds.execute.return_value = cursor
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 999},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None


class TestEnumProtectionInterceptorUpdate:

    def test_blocks_update_system_enum_type(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 1, 'name': 'modified'},
            old_data={'id': 1, 'category': 'system', 'name': 'status'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'SYSTEM_ENUM_IMMUTABLE' in ctx.result.errors

    def test_allows_update_business_enum_type(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 1, 'name': 'modified'},
            old_data={'id': 1, 'category': 'business', 'name': 'status'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_blocks_update_value_for_locked_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'mutability': 'locked', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 10, 'enum_type_id': 1, 'value': 'modified'},
            old_data={'id': 10, 'enum_type_id': 1, 'value': 'original'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'ENUM_LOCKED' in ctx.result.errors

    def test_allows_update_value_for_extensible_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'mutability': 'extensible', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 10, 'enum_type_id': 1, 'value': 'modified'},
            old_data={'id': 10, 'enum_type_id': 1, 'value': 'original'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_update_without_old_data(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_update',
            params={'id': 1},
            old_data=None,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_update_value_without_enum_type_id(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 10, 'value': 'modified'},
            old_data={'id': 10, 'value': 'original'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is None


class TestEnumProtectionInterceptorDelete:

    def test_blocks_delete_system_enum_type(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_delete',
            params={'id': 1},
            old_data={'id': 1, 'category': 'system'},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'SYSTEM_ENUM_IMMUTABLE' in ctx.result.errors

    def test_blocks_delete_enum_type_with_values(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_values(3)
        ctx = _make_context(
            'enum_type', 'crud_delete',
            params={'id': 2},
            old_data={'id': 2, 'category': 'business'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'HAS_VALUES' in ctx.result.errors

    def test_allows_delete_empty_business_enum_type(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_values(0)
        ctx = _make_context(
            'enum_type', 'crud_delete',
            params={'id': 2},
            old_data={'id': 2, 'category': 'business'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_blocks_delete_system_enum_value(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 10},
            old_data={'id': 10, 'enum_type_id': 1, 'is_system': 1},
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'SYSTEM_VALUE_IMMUTABLE' in ctx.result.errors

    def test_blocks_delete_value_for_locked_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'mutability': 'locked', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 10},
            old_data={'id': 10, 'enum_type_id': 1, 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
        assert 'ENUM_LOCKED' in ctx.result.errors

    def test_allows_delete_non_system_value_for_extensible_enum(self):
        interceptor = EnumProtectionInterceptor()
        ds = _make_data_source_with_enum_type({
            'id': 1, 'mutability': 'extensible', 'category': 'business'
        })
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 10},
            old_data={'id': 10, 'enum_type_id': 1, 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_delete_without_old_data(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_type', 'crud_delete',
            params={'id': 1},
            old_data=None,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_delete_value_without_enum_type_id(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 10},
            old_data={'id': 10, 'is_system': 0},
        )
        interceptor.before_action(ctx)
        assert ctx.result is None


class TestEnumProtectionInterceptorAfterAction:

    def test_after_action_does_nothing(self):
        interceptor = EnumProtectionInterceptor()
        ctx = _make_context('enum_type', 'crud_create')
        result = interceptor.after_action(ctx)
        assert result is None


class TestEnumProtectionInterceptorErrorHandling:

    def test_create_handles_data_source_exception(self):
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception("DB error")
        ctx = _make_context(
            'enum_value', 'crud_create',
            params={'enum_type_id': 1},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_update_value_handles_data_source_exception(self):
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception("DB error")
        ctx = _make_context(
            'enum_value', 'crud_update',
            params={'id': 10, 'enum_type_id': 1},
            old_data={'id': 10, 'enum_type_id': 1},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_delete_value_handles_data_source_exception(self):
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception("DB error")
        ctx = _make_context(
            'enum_value', 'crud_delete',
            params={'id': 10},
            old_data={'id': 10, 'enum_type_id': 1, 'is_system': 0},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_delete_type_handles_has_values_exception(self):
        interceptor = EnumProtectionInterceptor()
        ds = Mock()
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("DB error")
            cursor = Mock()
            cursor.fetchone.return_value = None
            return cursor
        ds.execute.side_effect = side_effect
        ctx = _make_context(
            'enum_type', 'crud_delete',
            params={'id': 2},
            old_data={'id': 2, 'category': 'business'},
            data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None
