import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
DataPermissionInterceptor 单元测试

测试数据权限拦截器的核心功能：
- 拦截器名称和优先级
- before_action 行为
- _is_admin 判断逻辑
- scope 过滤应用
- 数据权限过滤应用
"""

import pytest
from unittest.mock import Mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor


class MockActionContext:
    """模拟 ActionContext 用于测试"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', None)
        self.action = kwargs.get('action', 'crud_query')
        self.params = kwargs.get('params', {})
        self.user_id = kwargs.get('user_id', 1)
        self.user_name = kwargs.get('user_name', 'test_user')
        self.data_source = kwargs.get('data_source', None)
        self.meta_object = kwargs.get('meta_object', None)
        self.result = kwargs.get('result', None)
        self.old_data = kwargs.get('old_data', None)
        self.extra = kwargs.get('extra', {})

    @property
    def is_query_action(self):
        return self.action in ('crud_query', 'query', 'list')

    @property
    def is_create_action(self):
        return self.action in ('create', 'crud_create')

    @property
    def is_update_action(self):
        return self.action in ('update', 'crud_update')

    @property
    def is_delete_action(self):
        return self.action in ('delete', 'crud_delete')


@pytest.fixture
def interceptor():
    return DataPermissionInterceptor()


@pytest.fixture(autouse=True)
def cleanup_interceptor():
    yield
    DataPermissionInterceptor._perm_filter = None


class TestDataPermissionInterceptor:
    """DataPermissionInterceptor 单元测试"""

    def test_name_and_priority(self, interceptor):
        """测试拦截器名称和优先级"""
        assert interceptor.name == "data_permission"
        assert interceptor.priority == 30

    def test_interceptor_exists(self, interceptor):
        """测试拦截器存在"""
        assert interceptor is not None


class TestDataPermissionInterceptorExtended:
    """DataPermissionInterceptor 扩展测试"""

    def test_priority_is_30(self, interceptor):
        """优先级为 30"""
        assert interceptor.priority == 30

    def test_name_is_data_permission(self, interceptor):
        """名称为 data_permission"""
        assert interceptor.name == "data_permission"

    def test_before_action_skips_non_query(self, interceptor):
        """非查询动作跳过权限过滤"""
        context = MockActionContext(action='create', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_create_action(self, interceptor):
        """创建动作跳过权限过滤"""
        context = MockActionContext(action='crud_create', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_update_action(self, interceptor):
        """更新动作跳过权限过滤"""
        context = MockActionContext(action='update', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_delete_action(self, interceptor):
        """删除动作跳过权限过滤"""
        context = MockActionContext(action='delete', user_id=1)
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_before_action_skips_when_admin_flag_true(self, interceptor):
        """is_admin=True 时跳过权限过滤"""
        context = MockActionContext(
            action='crud_query',
            user_id=1,
            extra={'is_admin': True}
        )
        original_extra = dict(context.extra)
        interceptor.before_action(context)
        assert context.extra == original_extra

    def test_apply_scope_filter_without_meta_object(self, interceptor):
        """无 meta_object 时跳过 scope 过滤"""
        context = MockActionContext(
            action='crud_query',
            user_id=1,
            meta_object=None,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' not in context.extra

    def test_apply_scope_filter_skips_without_auth(self, interceptor):
        """无 authorization 配置时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = None

        context = MockActionContext(
            action='crud_query',
            user_id=1,
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' not in context.extra

    def test_apply_scope_filter_skips_without_scope(self, interceptor):
        """无 scope 表达式时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = {'other_config': 'value'}

        context = MockActionContext(
            action='crud_query',
            user_id=1,
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' not in context.extra

    def test_after_action_does_nothing(self, interceptor):
        """after_action 不执行任何操作"""
        context = MockActionContext(action='crud_query', user_id=1)
        original_extra = dict(context.extra)
        interceptor.after_action(context)
        assert context.extra == original_extra

    def test_parse_scope_expression_simple(self, interceptor):
        """解析简单 scope 表达式"""
        result = DataPermissionInterceptor._parse_scope_expression("owner_id = 1")
        assert len(result) == 1
        assert result[0]['field'] == 'owner_id'
        assert result[0]['operator'] == 'eq'
        assert result[0]['value'] == '1'

    def test_parse_scope_expression_or(self, interceptor):
        """解析 OR scope 表达式"""
        result = DataPermissionInterceptor._parse_scope_expression(
            "visibility = 'public' OR owner_id = 1"
        )
        assert len(result) == 1
        assert isinstance(result[0], list)
        or_group = result[0]
        assert len(or_group) == 2
        assert or_group[0]['field'] == 'visibility'
        assert or_group[0]['value'] == 'public'
        assert or_group[1]['field'] == 'owner_id'
        assert or_group[1]['value'] == '1'

    def test_parse_scope_expression_or_lowercase(self, interceptor):
        """解析小写 or 表达式"""
        result = DataPermissionInterceptor._parse_scope_expression(
            "visibility = 'public' or owner_id = 1"
        )
        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) == 2

    def test_apply_scope_filter_with_or_expression(self, interceptor):
        """OR scope 表达式注入 query_conditions"""
        meta_obj = Mock()
        meta_obj.authorization = {
            'scope': "visibility = 'public' OR owner_id = $user.id"
        }

        context = MockActionContext(
            action='crud_query',
            user_id=42,
            meta_object=meta_obj,
            extra={}
        )

        interceptor._apply_scope_filter(context)
        assert 'query_conditions' in context.extra
        assert len(context.extra['query_conditions']) == 1
        cond = context.extra['query_conditions'][0]
        assert cond['type'] == 'or'
        assert len(cond['conditions']) == 2
        assert cond['conditions'][0]['field'] == 'visibility'
        assert cond['conditions'][0]['value'] == 'public'
        assert cond['conditions'][1]['field'] == 'owner_id'
        assert cond['conditions'][1]['value'] == '42'

    def test_parse_simple_condition_with_quotes(self, interceptor):
        """解析带引号的简单条件"""
        result = DataPermissionInterceptor._parse_simple_condition("name = 'hello'")
        assert result['field'] == 'name'
        assert result['operator'] == 'eq'
        assert result['value'] == 'hello'

    def test_parse_simple_condition_with_double_quotes(self, interceptor):
        """解析带双引号的简单条件"""
        result = DataPermissionInterceptor._parse_simple_condition('name = "world"')
        assert result['field'] == 'name'
        assert result['operator'] == 'eq'
        assert result['value'] == 'world'

    def test_parse_simple_condition_not_equal(self, interceptor):
        """解析 != 操作符"""
        result = DataPermissionInterceptor._parse_simple_condition("count != 0")
        assert result['field'] == 'count'
        assert result['operator'] == 'ne'
        assert result['value'] == '0'
