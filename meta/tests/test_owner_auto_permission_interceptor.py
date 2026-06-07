import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
OwnerAutoPermissionInterceptor 单元测试

测试所有者自动权限拦截器的核心功能：
- 拦截器名称和优先级
- before_action 注入 owner_id
- after_action 添加数据权限
- authorization 配置解析
"""

import pytest
from unittest.mock import Mock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor


class MockActionResult:
    """模拟 ActionResult"""

    def __init__(self, success=True, data=None, message=''):
        self.success = success
        self.data = data
        self.message = message


class MockActionContext:
    """模拟 ActionContext 用于测试"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', None)
        self.action = kwargs.get('action', 'create')
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
    return OwnerAutoPermissionInterceptor()


class TestOwnerAutoPermissionInterceptor:
    """OwnerAutoPermissionInterceptor 单元测试"""

    def test_name_and_priority(self, interceptor):
        """测试拦截器名称和优先级"""
        assert interceptor.name == "owner_permission"
        assert interceptor.priority == 96

    def test_interceptor_exists(self, interceptor):
        """测试拦截器存在"""
        assert interceptor is not None


class TestOwnerAutoPermissionInterceptorExtended:
    """OwnerAutoPermissionInterceptor 扩展测试"""

    def test_priority_is_96(self, interceptor):
        """优先级为 96"""
        assert interceptor.priority == 96

    def test_name_is_owner_permission(self, interceptor):
        """名称为 owner_permission"""
        assert interceptor.name == "owner_permission"

    def test_before_action_injects_owner_id(self, interceptor):
        """创建时自动注入 owner_id"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_owner': True}

        context = MockActionContext(
            action='create',
            user_id=123,
            meta_object=meta_obj,
            params={}
        )

        interceptor.before_action(context)

        assert 'owner_id' in context.params
        assert context.params['owner_id'] == 123

    def test_before_action_injects_owner_id_with_crud_create(self, interceptor):
        """crud_create 动作也注入 owner_id"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_owner': True}

        context = MockActionContext(
            action='crud_create',
            user_id=456,
            meta_object=meta_obj,
            params={}
        )

        interceptor.before_action(context)

        assert 'owner_id' in context.params
        assert context.params['owner_id'] == 456

    def test_before_action_skips_non_create(self, interceptor):
        """非创建动作跳过"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_owner': True}

        context = MockActionContext(
            action='update',
            user_id=123,
            meta_object=meta_obj,
            params={}
        )

        interceptor.before_action(context)

        assert 'owner_id' not in context.params

    def test_before_action_respects_auto_owner_false(self, interceptor):
        """auto_owner=False 时不注入"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_owner': False}

        context = MockActionContext(
            action='create',
            user_id=123,
            meta_object=meta_obj,
            params={}
        )

        interceptor.before_action(context)

        assert 'owner_id' not in context.params

    def test_before_action_skips_without_auth_config(self, interceptor):
        """无 authorization 配置时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = None

        context = MockActionContext(
            action='create',
            user_id=123,
            meta_object=meta_obj,
            params={}
        )

        interceptor.before_action(context)

        assert 'owner_id' not in context.params

    def test_before_action_skips_without_meta_object(self, interceptor):
        """无 meta_object 时跳过"""
        context = MockActionContext(
            action='create',
            user_id=123,
            meta_object=None,
            params={}
        )

        interceptor.before_action(context)

        assert 'owner_id' not in context.params

    def test_after_action_skips_non_create(self, interceptor):
        """非创建动作跳过 after_action"""
        context = MockActionContext(
            action='update',
            user_id=123,
            result=MockActionResult(success=True, data={'id': 1})
        )

        original_result = context.result
        interceptor.after_action(context)

        assert context.result == original_result

    def test_after_action_skips_failed_create(self, interceptor):
        """创建失败时跳过权限添加"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_permission': 'admin'}

        context = MockActionContext(
            action='create',
            user_id=123,
            meta_object=meta_obj,
            result=MockActionResult(success=False, data=None)
        )

        interceptor.after_action(context)
        assert context.result.success is False

    def test_after_action_skips_none_result(self, interceptor):
        """result 为 None 时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_permission': 'admin'}

        context = MockActionContext(
            action='create',
            user_id=123,
            meta_object=meta_obj,
            result=None
        )

        interceptor.after_action(context)
        assert context.result is None

    def test_get_auth_config_from_dict(self, interceptor):
        """从 dict 获取 authorization 配置"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_owner': True, 'auto_permission': 'admin'}

        context = MockActionContext(meta_object=meta_obj)

        config = interceptor._get_auth_config(context)
        assert isinstance(config, dict)
        assert config.get('auto_owner') is True

    def test_get_auth_config_from_object(self, interceptor):
        """从对象获取 authorization 配置"""
        auth_config = Mock()
        auth_config.auto_owner = True
        auth_config.auto_permission = 'admin'

        meta_obj = Mock()
        meta_obj.authorization = auth_config

        context = MockActionContext(meta_object=meta_obj)

        config = interceptor._get_auth_config(context)
        assert config == auth_config

    def test_get_auth_config_returns_none_without_meta(self, interceptor):
        """无 meta_object 时返回 None"""
        context = MockActionContext(meta_object=None)
        config = interceptor._get_auth_config(context)
        assert config is None

    def test_get_auth_config_auto_permission_empty(self, interceptor):
        """auto_permission 为空时跳过"""
        meta_obj = Mock()
        meta_obj.authorization = {'auto_owner': True}

        context = MockActionContext(
            action='create',
            meta_object=meta_obj,
            result=MockActionResult(success=True, data={'id': 1})
        )

        interceptor.after_action(context)
        assert context.result.success is True
