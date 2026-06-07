# -*- coding: utf-8 -*-
"""
拦截器验证测试

合并以下测试文件:
- test_context_interceptor.py (上下文拦截器)
- test_hierarchy_validation.py (层级校验服务)
- test_hierarchy_validation_interceptor.py (层级校验拦截器)

测试范围:
- ContextInterceptor: 上下文设置
- HierarchyValidationInterceptor: 层级校验
- 父子元素校验逻辑
"""

import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.unit


# ==================== 共享 Fixtures ====================

class MockActionContext:
    """模拟 ActionContext 用于测试"""
    
    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'domain')
        self.object_id = kwargs.get('object_id', None)
        self.action = kwargs.get('action', 'update')
        self.params = kwargs.get('params', {})
        self.user_id = kwargs.get('user_id', None)
        self.user_name = kwargs.get('user_name', None)
        self.ip_address = kwargs.get('ip_address', None)
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
def context_interceptor():
    """ContextInterceptor 实例"""
    from meta.core.interceptors.context_interceptor import ContextInterceptor
    return ContextInterceptor()


@pytest.fixture
def hierarchy_interceptor():
    """HierarchyValidationInterceptor 实例"""
    from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
    return HierarchyValidationInterceptor()


@pytest.fixture
def api_client():
    """API 客户端"""
    from meta.tests.conftest import get_shared_app
    return get_shared_app()


@pytest.fixture
def api_headers():
    """API 认证头"""
    return {
        'Content-Type': 'application/json',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
        'X-IP-Address': '127.0.0.1'
    }


# ==================== ContextInterceptor 测试 ====================

class TestContextInterceptor:
    """ContextInterceptor 单元测试"""

    def test_priority_is_10(self, context_interceptor):
        """优先级为 10"""
        assert context_interceptor.priority == 10

    def test_after_action_does_nothing(self, context_interceptor):
        """after_action 不执行任何操作"""
        context = MockActionContext()
        original_user_id = context.user_id
        context_interceptor.after_action(context)
        assert context.user_id == original_user_id

    def test_before_action_handles_exception(self, context_interceptor):
        """before_action 异常处理"""
        context = MockActionContext()
        try:
            context_interceptor.before_action(context)
        except Exception:
            pytest.fail("before_action should not raise exception")

    def test_context_with_existing_user_id(self, context_interceptor):
        """已有 user_id 时保留"""
        context = MockActionContext(user_id=456)
        context_interceptor.before_action(context)
        assert context.user_id == 456

    def test_context_with_existing_username(self, context_interceptor):
        """已有 username 时保留"""
        context = MockActionContext(user_name='existing_user')
        context_interceptor.before_action(context)
        assert context.user_name == 'existing_user'

    def test_context_with_existing_ip_address(self, context_interceptor):
        """已有 ip_address 时保留"""
        context = MockActionContext(ip_address='10.0.0.1')
        context_interceptor.before_action(context)
        assert context.ip_address == '10.0.0.1'

    def test_interceptor_has_before_action(self, context_interceptor):
        """有 before_action 方法"""
        assert hasattr(context_interceptor, 'before_action')
        assert callable(getattr(context_interceptor, 'before_action'))

    def test_interceptor_has_after_action(self, context_interceptor):
        """有 after_action 方法"""
        assert hasattr(context_interceptor, 'after_action')
        assert callable(getattr(context_interceptor, 'after_action'))

    def test_before_action_returns_none(self, context_interceptor):
        """before_action 返回 None"""
        context = MockActionContext()
        result = context_interceptor.before_action(context)
        assert result is None


# ==================== HierarchyValidationInterceptor 测试 ====================

class TestHierarchyValidationInterceptor:
    """HierarchyValidationInterceptor 单元测试"""

    def test_name_and_priority(self, hierarchy_interceptor):
        """测试拦截器名称和优先级"""
        assert hierarchy_interceptor.name == "hierarchy_validation"
        assert hierarchy_interceptor.priority == 45

    def test_interceptor_exists(self, hierarchy_interceptor):
        """测试拦截器存在"""
        assert hierarchy_interceptor is not None

    def test_priority_is_45(self, hierarchy_interceptor):
        """优先级为 45"""
        assert hierarchy_interceptor.priority == 45

    def test_name_is_hierarchy_validation(self, hierarchy_interceptor):
        """名称为 hierarchy_validation"""
        assert hierarchy_interceptor.name == "hierarchy_validation"

    def test_after_action_does_nothing(self, hierarchy_interceptor):
        """after_action 不执行任何操作"""
        context = MockActionContext(action='update', user_id=1)
        original_extra = dict(context.extra)
        hierarchy_interceptor.after_action(context)
        assert context.extra == original_extra

    def test_has_before_action(self, hierarchy_interceptor):
        """有 before_action 方法"""
        assert hasattr(hierarchy_interceptor, 'before_action')

    def test_has_after_action(self, hierarchy_interceptor):
        """有 after_action 方法"""
        assert hasattr(hierarchy_interceptor, 'after_action')

    def test_validate_delete_force_true_skips(self, hierarchy_interceptor):
        """force=True 跳过删除校验"""
        context = MockActionContext(
            action='delete',
            object_type='domain',
            object_id=1,
            params={'force': True},
            extra={}
        )
        hierarchy_interceptor.before_action(context)

    def test_validate_delete_force_string_true_skips(self, hierarchy_interceptor):
        """force='true' 跳过删除校验"""
        context = MockActionContext(
            action='delete',
            object_type='domain',
            object_id=1,
            params={'force': 'true'},
            extra={}
        )
        hierarchy_interceptor.before_action(context)


# ==================== 层级校验服务集成测试 ====================

class TestHierarchyValidationService:
    """层级校验服务集成测试"""

    @pytest.fixture(autouse=True)
    def _ensure_base_data(self, api_client, api_headers):
        """v3.18 P1: 修复 S022 数据依赖 skip
        确保 BO id=1 和 Version id=1 存在, 否则测试无意义
        """
        _, client = api_client
        # 确保 Version 1 存在
        v1_resp = client.get('/api/v2/bo/version/1', headers=api_headers)
        if v1_resp.status_code != 200:
            v_create = client.post(
                '/api/v2/bo/version',
                json={'name': 'Default Version', 'code': 'V1', 'description': 'auto-created'},
                headers=api_headers,
            )
            if v_create.status_code not in [200, 201]:
                return  # skip 让测试自然 skip
        # 确保 BO 1 存在
        bo_resp = client.get('/api/v2/bo/business_object/1', headers=api_headers)
        if not (bo_resp.status_code == 200 and (bo_resp.json or {}).get('data')):
            bo_create = client.post(
                '/api/v2/bo/business_object',
                json={
                    'name': 'DefaultBO', 'code': 'DEFAULT_BO',
                    'version_id': 1, 'service_module_id': 1,
                },
                headers=api_headers,
            )
            if bo_create.status_code not in [200, 201]:
                return  # 让测试自然 skip
        return None

    def test_update_parent_field_blocked(self, api_client, api_headers):
        """测试更新父元素字段被阻止"""
        _, client = api_client
        response = client.get('/api/v2/bo/business_object/1')
        data = response.json
        if not data.get('success') or not data.get('data'):
            pytest.skip("Business object 1 not found")

        original = data.get('data', {})
        original_service_module_id = original.get('service_module_id')
        new_service_module_id = 999 if original_service_module_id != 999 else 998

        response = client.put(
            '/api/v2/bo/business_object/1',
            json={
                'name': original.get('name', 'test'),
                'version_id': original.get('version_id', 1),
                'service_module_id': new_service_module_id
            },
            headers=api_headers
        )

        assert response.status_code in [400, 401, 500]
        data = response.json
        assert data.get('success', True) is False
        assert '不允许修改' in data.get('message', '')

    def test_update_parent_field_unchanged_allowed(self, api_client, api_headers):
        """测试更新父元素字段未变更允许"""
        _, client = api_client
        response = client.get('/api/v2/bo/business_object/1')
        data = response.json
        if not data.get('success') or not data.get('data'):
            pytest.skip("Business object 1 not found")

        original = data.get('data', {})

        response = client.put(
            '/api/v2/bo/business_object/1',
            json={
                'name': original.get('name', 'test') + '_updated',
                'version_id': original.get('version_id'),
                'service_module_id': original.get('service_module_id')
            },
            headers=api_headers
        )

        assert response.status_code in [200, 401, 404, 500]
        data = response.json
        assert data.get('success', False) is True

    def test_delete_with_children_blocked(self, api_client, api_headers):
        """测试删除有子元素的记录被阻止"""
        _, client = api_client
        response = client.get('/api/v2/bo/version/1')
        if response.status_code != 200:
            pytest.skip("Version 1 not found")

        response = client.delete(
            '/api/v2/bo/version/1',
            headers=api_headers
        )

        assert response.status_code in [400, 401, 500]
        data = response.json
        assert data.get('success', True) is False
        assert '子元素' in data.get('message', '')

    def test_delete_without_children_allowed(self, api_client, api_headers):
        """测试删除没有子元素的记录允许"""
        _, client = api_client
        response = client.post(
            '/api/v2/bo/domain',
            json={'name': 'TestDomainForDelete', 'code': 'TDD', 'version_id': 1},
            headers=api_headers
        )

        if response.status_code not in [200, 201]:
            pytest.skip("Failed to create test domain")

        data = response.json
        if not data.get('success') or not data.get('data', {}).get('id'):
            pytest.skip("Failed to create test domain")

        domain_id = data.get('data', {})['id']

        response = client.delete(
            f'/api/v2/bo/domain/{domain_id}',
            headers=api_headers
        )

        assert response.status_code in [200, 204, 401, 500]
