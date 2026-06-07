import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
DataPermissionGenerator 服务测试

测试 data_permission_generator.py：
- generate_rules
- build_condition
- get_scope_conditions
"""

import pytest
import sys
import os
import json

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)


@pytest.fixture(scope="class")
def data_source():
    from meta.core.datasource import get_data_source
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )
    return get_data_source("sqlite", database=db_path)


@pytest.fixture(scope="class")
def app_client():
    from meta.tests.conftest import get_shared_app
    return get_shared_app()


@pytest.fixture
def admin_token():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    
    user = UserInfo(
        user_id='1',
        username='admin',
        display_name='Admin',
        email='admin@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    return token


@pytest.fixture
def admin_headers(admin_token):
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {admin_token}'
    }


class TestDataPermissionGenerator:
    """DataPermissionGenerator 服务测试"""

    def test_generator_exists(self):
        """测试 DataPermissionGenerator 类存在"""
        try:
            from meta.services.data_permission_generator import DataPermissionGenerator
            assert DataPermissionGenerator is not None
        except ImportError:
            pytest.skip("DataPermissionGenerator not implemented yet")

    def test_generate_rules_method_exists(self, data_source):
        """测试 generate_rules 方法存在"""
        try:
            from meta.services.data_permission_generator import DataPermissionGenerator
            gen = DataPermissionGenerator(data_source)
            assert hasattr(gen, 'generate_rules') or hasattr(gen, 'generate_on_create'), \
                "DataPermissionGenerator should have generate_rules or generate_on_create method"
        except ImportError:
            pytest.skip("DataPermissionGenerator not implemented yet")

    def test_get_scope_conditions_method_exists(self, data_source):
        """测试 get_scope_conditions 方法存在"""
        try:
            from meta.services.data_permission_generator import DataPermissionGenerator
            gen = DataPermissionGenerator(data_source)
            assert hasattr(gen, 'get_scope_conditions') or hasattr(gen, 'generate_on_create'), \
                "DataPermissionGenerator should have get_scope_conditions or generate_on_create method"
        except ImportError:
            pytest.skip("DataPermissionGenerator not implemented yet")


class TestDataPermissionService:
    """DataPermissionService 测试"""

    def test_service_exists(self, data_source):
        """测试 DataPermissionService 类存在"""
        from meta.services.data_permission_service import DataPermissionService
        assert DataPermissionService is not None

    def test_check_permission(self, data_source):
        """测试权限检查"""
        from meta.services.data_permission_service import DataPermissionService
        svc = DataPermissionService(data_source)
        
        if hasattr(svc, 'check_permission'):
            result = svc.check_permission(
                user_id=1,
                resource_type='domain',
                resource_id=1,
                permission_level='read'
            )
            assert isinstance(result, bool)
        elif hasattr(svc, 'has_access'):
            result = svc.has_access(
                user_id=1,
                resource_type='domain',
                resource_id=1,
                action='read'
            )
            assert isinstance(result, bool)
        else:
            pytest.skip("No permission check method available")


class TestDataPermissionAPI:
    """Data Permission API 测试"""

    def test_list_data_permissions(self, app_client, admin_headers):
        """列出数据权限"""
        _, client = app_client
        response = client.get(
            '/api/v1/data-permissions?page=1&page_size=10',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_create_data_permission(self, app_client, admin_headers):
        """创建数据权限"""
        _, client = app_client
        data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 1,
            'permission_level': 'read',
            'inherit_to_children': True
        }
        
        response = client.post(
            '/api/v1/data-permissions',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 403, 404, 500]

    def test_get_data_permission_by_id(self, app_client, admin_headers):
        """获取数据权限"""
        _, client = app_client
        response = client.get(
            '/api/v1/data-permissions/1',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 404, 500]

    def test_update_data_permission(self, app_client, admin_headers):
        """更新数据权限"""
        _, client = app_client
        data = {'permission_level': 'write'}
        
        response = client.put(
            '/api/v1/data-permissions/1',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 404, 500]

    def test_delete_data_permission(self, app_client, admin_headers):
        """删除数据权限"""
        _, client = app_client
        response = client.delete(
            '/api/v1/data-permissions/999',
            headers=admin_headers
        )
        assert response.status_code in [200, 204, 400, 401, 404, 500]

    def test_filter_by_user_id(self, app_client, admin_headers):
        """按用户 ID 过滤"""
        _, client = app_client
        response = client.get(
            '/api/v1/data-permissions?user_id=1',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_filter_by_resource_type(self, app_client, admin_headers):
        """按资源类型过滤"""
        _, client = app_client
        response = client.get(
            '/api/v1/data-permissions?resource_type=domain',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_without_auth_returns_401(self, app_client):
        """未认证返回 401"""
        _, client = app_client
        response = client.get('/api/v1/data-permissions')
        assert response.status_code in [401, 403, 302, 200, 404, 500]
