import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
VersionContextInterceptor 单元测试

测试版本上下文拦截器的核心功能：
- before_action 注入 version_id
- should_execute 条件判断

迁移自 unittest.TestCase -> pytest
"""
import pytest
from unittest.mock import Mock

from meta.core.interceptors.version_context_interceptor import VersionContextInterceptor


class MockActionContext:
    """模拟 ActionContext"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', None)
        self.action = kwargs.get('action', 'crud_list')
        self.params = kwargs.get('params', {})
        self.user_id = kwargs.get('user_id', 1)
        self.meta_object = kwargs.get('meta_object', None)
        self.extra = kwargs.get('extra', {})


@pytest.fixture
def interceptor():
    """VersionContextInterceptor 实例"""
    return VersionContextInterceptor()


class TestVersionContextInterceptor:
    """VersionContextInterceptor 测试"""

    def test_priority_is_15(self, interceptor):
        """优先级为 15"""
        assert interceptor.priority == 15

    def test_should_execute_without_meta_object(self, interceptor):
        """无 meta_object 时不执行"""
        context = MockActionContext(
            action='crud_list',
            meta_object=None
        )
        assert not interceptor.should_execute(context)

    def test_should_execute_without_context_config(self, interceptor):
        """无 context 配置时不执行"""
        meta_obj = Mock()
        meta_obj.context = None

        context = MockActionContext(
            action='crud_list',
            meta_object=meta_obj
        )
        assert not interceptor.should_execute(context)

    def test_should_execute_for_list_action(self, interceptor):
        """list 动作执行"""
        meta_obj = Mock()
        meta_obj.context = {'field': 'version_id'}

        context = MockActionContext(
            action='crud_list',
            meta_object=meta_obj
        )
        assert interceptor.should_execute(context)

    def test_should_execute_for_read_action(self, interceptor):
        """read 动作执行"""
        meta_obj = Mock()
        meta_obj.context = {'field': 'version_id'}

        context = MockActionContext(
            action='crud_read',
            meta_object=meta_obj
        )
        assert interceptor.should_execute(context)

    def test_should_not_execute_for_create_action(self, interceptor):
        """create 动作不执行"""
        meta_obj = Mock()
        meta_obj.context = {'field': 'version_id'}

        context = MockActionContext(
            action='create',
            meta_object=meta_obj
        )
        assert not interceptor.should_execute(context)

    def test_before_action_without_context_field(self, interceptor):
        """无 context.field 时跳过"""
        meta_obj = Mock()
        meta_obj.context = {}

        context = MockActionContext(
            action='crud_list',
            meta_object=meta_obj,
            params={}
        )

        original_params = dict(context.params)
        interceptor.before_action(context)
        assert context.params == original_params

    def test_before_action_with_existing_version_id(self, interceptor):
        """已有 version_id 时不覆盖"""
        meta_obj = Mock()
        meta_obj.context = {'field': 'version_id'}

        context = MockActionContext(
            action='crud_list',
            meta_object=meta_obj,
            params={'version_id': 5}
        )

        interceptor.before_action(context)
        assert context.params['version_id'] == 5

    def test_after_action_does_nothing(self, interceptor):
        """after_action 不执行任何操作"""
        context = MockActionContext(action='crud_list')
        original_params = dict(context.params)
        interceptor.after_action(context)
        assert context.params == original_params

    def test_resolve_version_id_returns_none_by_default(self, interceptor):
        """_resolve_version_id 需要 Flask 应用上下文"""
        try:
            version_id = interceptor._resolve_version_id()
            assert version_id is None
        except RuntimeError:
            pass


class TestVersionContextInterceptorMethods:
    """VersionContextInterceptor 方法测试"""

    def test_has_should_execute(self, interceptor):
        """有 should_execute 方法"""
        assert hasattr(interceptor, 'should_execute')

    def test_has_before_action(self, interceptor):
        """有 before_action 方法"""
        assert hasattr(interceptor, 'before_action')

    def test_has_after_action(self, interceptor):
        """有 after_action 方法"""
        assert hasattr(interceptor, 'after_action')

    def test_has_resolve_version_id(self, interceptor):
        """有 _resolve_version_id 方法"""
        assert hasattr(interceptor, '_resolve_version_id')
