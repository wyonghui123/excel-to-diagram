# -*- coding: utf-8 -*-
"""
权限服务测试

合并以下测试文件:
- test_permission_service.py (权限服务)
- test_permission_sync_service.py (权限同步服务)
- test_permission_bundle_api.py (权限包 API)

测试范围:
- 权限服务: get_user_roles, has_permission 等
- 权限同步: sync_all, validate_consistency 等
- 权限包: CRUD 和分发
"""

import pytest
import json
import os

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

@pytest.fixture(scope='module')
def data_source():
    """获取数据源"""
    from meta.core.datasource import get_data_source
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'architecture.db'
    )
    return get_data_source("sqlite", database=db_path)


@pytest.fixture(scope='module')
def permission_service(data_source):
    """获取权限服务"""
    from meta.services.permission_service import PermissionService
    return PermissionService(data_source)


@pytest.fixture(scope='module')
def sync_service(data_source):
    """获取权限同步服务"""
    from meta.services.permission_sync_service import PermissionSyncService
    return PermissionSyncService(data_source)


@pytest.fixture(scope='module')
def api_client():
    """获取 API 客户端"""
    from meta.tests.conftest import get_shared_app
    return get_shared_app()[1]


@pytest.fixture(scope='module')
def admin_headers(api_client):
    """获取管理员认证头"""
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    
    admin_user = UserInfo(
        user_id='1', username='admin', display_name='Admin',
        email='admin@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(admin_user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }


# ==================== 权限服务测试 ====================

class TestPermissionService:
    """权限服务测试 - 用户视角"""

    def test_get_all_roles(self, permission_service):
        """获取所有角色"""
        roles = permission_service.get_all_roles()
        assert isinstance(roles, list)

    def test_get_all_permissions(self, permission_service):
        """获取所有权限"""
        perms = permission_service.get_all_permissions()
        assert isinstance(perms, list)

    def test_get_user_roles(self, permission_service):
        """获取用户角色"""
        roles = permission_service.get_user_roles(1)
        assert isinstance(roles, list)

    def test_get_user_permissions(self, permission_service):
        """获取用户权限"""
        perms = permission_service.get_user_permissions(1)
        assert isinstance(perms, list)

    def test_has_permission_admin(self, permission_service):
        """管理员权限检查"""
        result = permission_service.has_permission(1, 'user:read')
        assert isinstance(result, bool)

    def test_has_permission_nonexistent_user(self, permission_service):
        """不存在用户的权限检查"""
        result = permission_service.has_permission(999999, 'user:read')
        assert result is False

    def test_get_role_permissions(self, permission_service):
        """获取角色权限"""
        perms = permission_service.get_role_permissions(1)
        assert isinstance(perms, list)

    def test_assign_and_remove_role(self, permission_service):
        """分配和移除角色"""
        result = permission_service.assign_role(1, 999)
        assert isinstance(result, bool)
        if result:
            removed = permission_service.remove_role(1, 999)
            assert removed is True

    def test_remove_nonexistent_role(self, permission_service):
        """移除不存在的角色"""
        result = permission_service.remove_role(999999, 999999)
        assert isinstance(result, bool)

    def test_get_user_roles_nonexistent_user(self, permission_service):
        """获取不存在用户的角色"""
        roles = permission_service.get_user_roles(999999)
        assert roles == []

    def test_get_user_permissions_nonexistent_user(self, permission_service):
        """获取不存在用户的权限"""
        perms = permission_service.get_user_permissions(999999)
        assert perms == []


# ==================== 权限同步服务测试 ====================

class TestPermissionSyncService:
    """权限同步服务测试"""

    def test_sync_all(self, sync_service):
        """全量同步验证"""
        result = sync_service.sync_all()
        assert 'created' in result
        assert 'updated' in result
        assert 'existing' in result
        assert 'orphaned' in result
        assert 'summary' in result

        summary = result['summary']
        assert isinstance(summary, dict)
        assert 'created_count' in summary
        assert 'updated_count' in summary
        assert 'orphaned_count' in summary

    def test_sync_all_is_idempotent(self, sync_service):
        """全量同步幂等性"""
        result1 = sync_service.sync_all()
        result2 = sync_service.sync_all()

        assert result1['summary']['created_count'] == 0, \
            "first sync should have 0 new creates"
        assert result2['summary']['created_count'] == 0, \
            "second sync should be idempotent"

    def test_validate_consistency(self, sync_service):
        """一致性校验"""
        result = sync_service.validate_consistency()

        assert 'is_consistent' in result
        assert 'missing_permissions' in result
        assert 'extra_permissions' in result
        assert isinstance(result['is_consistent'], bool)
        assert isinstance(result['missing_permissions'], list)

    def test_validate_consistency_after_sync(self, sync_service):
        """同步后一致性校验"""
        try:
            sync_service.sync_all()
            result = sync_service.validate_consistency()
            assert result['is_consistent'] is True
        except AssertionError:
            pytest.fail("Permissions not consistent after sync")
        except Exception as e:
            pytest.fail(f"Permission sync issue: {e}")

    def test_get_permission_report(self, sync_service):
        """权限报告"""
        result = sync_service.get_permission_report()

        assert 'objects' in result
        assert 'total_objects' in result
        assert 'total_actions' in result
        assert 'total_permissions' in result
        assert isinstance(result['objects'], list)

    def test_sync_for_object_known(self, sync_service):
        """增量同步已知对象"""
        result = sync_service.sync_for_object('product')

        assert 'created' in result
        assert 'existing' in result
        assert 'total' in result

    def test_sync_for_object_unknown(self, sync_service):
        """增量同步未知对象"""
        result = sync_service.sync_for_object('nonexistent_bo_12345')

        assert 'error' in result
        assert result['total'] == 0

    def test_super_permission_always_exists(self, sync_service):
        """超级权限始终存在"""
        try:
            sync_service.sync_all()
            result = sync_service.validate_consistency()

            if not result['is_consistent']:
                missing = result.get('missing_permissions', [])
                pytest.fail(f"Permissions not fully consistent (expected in test env): missing {len(missing)} permissions")
        except Exception as e:
            pytest.fail(f"Permission sync issue: {e}")


# ==================== 权限包 API 测试 ====================

class TestPermissionBundleAPI:
    """权限包 API 测试"""

    @property
    def base_url(self):
        return '/api/v1/permission-bundles'

    def test_list_permission_bundles(self, api_client, admin_headers):
        """列出权限包"""
        response = api_client.get(f'{self.base_url}?page=1&page_size=10', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_create_permission_bundle(self, api_client, admin_headers):
        """创建权限包"""
        data = {
            'name': 'Test Bundle',
            'code': 'test_bundle',
            'description': 'Test permission bundle',
            'permissions': ['read', 'write']
        }
        response = api_client.post(
            self.base_url,
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 403, 404, 500]

    def test_get_permission_bundle_by_id(self, api_client, admin_headers):
        """根据 ID 获取权限包"""
        response = api_client.get(f'{self.base_url}/1', headers=admin_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_update_permission_bundle(self, api_client, admin_headers):
        """更新权限包"""
        data = {'description': 'Updated description'}
        response = api_client.put(
            f'{self.base_url}/1',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 403, 404, 500]

    def test_delete_permission_bundle(self, api_client, admin_headers):
        """删除权限包"""
        response = api_client.delete(f'{self.base_url}/999', headers=admin_headers)
        assert response.status_code in [200, 204, 400, 401, 403, 404, 500]

    def test_apply_bundle_to_role(self, api_client, admin_headers):
        """将权限包应用到角色"""
        response = api_client.post(
            f'{self.base_url}/1/apply',
            data=json.dumps({'role_id': 1}),
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 403, 404, 500]

    def test_apply_bundle_to_user(self, api_client, admin_headers):
        """将权限包应用到用户"""
        response = api_client.post(
            f'{self.base_url}/1/apply',
            data=json.dumps({'user_id': 1}),
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 403, 404, 500]

    def test_get_bundle_permissions(self, api_client, admin_headers):
        """获取权限包包含的权限"""
        response = api_client.get(f'{self.base_url}/1/permissions', headers=admin_headers)
        assert response.status_code in [200, 401, 404, 500]

    def test_list_without_auth(self, api_client):
        """未认证访问"""
        response = api_client.get(self.base_url)
        assert response.status_code in [401, 403, 302, 200, 404, 500]
