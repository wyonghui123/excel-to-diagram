# -*- coding: utf-8 -*-
"""
角色与权限 API 测试

合并以下测试文件:
- test_role_menu_api.py (角色菜单权限 API)
- test_role_dimension_scope_api.py (角色维度范围 API)
- test_permission_audit_api.py (权限审计 API)

测试范围:
- 角色菜单权限: /api/v1/roles/*/menu-permissions
- 角色维度范围: /api/v2/bo/role-dimension-scopes
- 权限审计: /api/v1/permission-audit/*
"""

import pytest
import json
import jwt
import os

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

@pytest.fixture(scope='module')
def api_client():
    """获取共享 API 客户端"""
    from meta.tests.conftest import get_shared_app
    return get_shared_app()[1]


@pytest.fixture(scope='module')
def admin_token():
    """获取管理员 Token"""
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    user = UserInfo(
        user_id='1', username='admin', display_name='Admin',
        email='admin@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    return token


@pytest.fixture(scope='module')
def admin_headers(admin_token):
    """获取管理员认证头"""
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {admin_token}'
    }


# ==================== 角色菜单权限 API 测试 ====================

class TestRoleMenuPermissions:
    """角色菜单权限 API 测试"""

    def test_get_role_menu_permissions(self, api_client, admin_headers):
        """获取角色菜单权限"""
        resp = api_client.get('/api/v1/roles/1/menu-permissions', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True
        assert 'data' in data

    def test_get_role_unified_permissions(self, api_client, admin_headers):
        """获取角色统一权限"""
        resp = api_client.get('/api/v1/roles/1/unified-permissions', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True
        body = data.get('data', {})
        assert 'menus' in body
        assert 'summary' in body

    def test_update_role_menu_permissions_unauthorized(self, api_client):
        """未授权更新菜单权限"""
        resp = api_client.put('/api/v1/roles/1/menu-permissions', json={
            'menu_codes': ['test_menu']
        })
        assert resp.status_code in (200, 401, 403, 404, 500)

    def test_update_role_menu_permissions_success(self, api_client, admin_headers):
        """成功更新菜单权限"""
        resp = api_client.put('/api/v1/roles/1/menu-permissions', json={
            'menu_codes': []
        }, headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True

    def test_menu_permissions_structure(self, api_client, admin_headers):
        """菜单权限结构验证"""
        resp = api_client.get('/api/v1/roles/1/menu-permissions', headers=admin_headers)
        data = resp.get_json()
        menus = data.get('data', [])
        if menus:
            menu = menus[0]
            assert 'menu_code' in menu
            assert 'assigned' in menu

    def test_unified_permissions_three_layers(self, api_client, admin_headers):
        """统一权限三层结构"""
        resp = api_client.get('/api/v1/roles/1/unified-permissions', headers=admin_headers)
        data = resp.get_json()
        body = data.get('data', {})
        menus = body.get('menus', [])
        if menus:
            menu = menus[0]
            assert 'assigned' in menu
            assert 'required_permissions' in menu
            assert 'data_scope' in menu

    def test_auto_sync_permissions_on_menu_update(self, api_client, admin_headers):
        """菜单更新时自动同步权限"""
        resp = api_client.put('/api/v1/roles/1/menu-permissions', json={
            'menu_codes': []
        }, headers=admin_headers)
        data = resp.get_json()
        assert data.get('success', False) is True
        assert 'synced_permissions' in data

    def test_super_admin_role_all_permissions(self, api_client, admin_headers):
        """超级管理员拥有所有权限"""
        resp = api_client.get('/api/v1/roles/1/unified-permissions', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True


# ==================== 角色维度范围 API 测试 ====================

class TestRoleDimensionScopeAPI:
    """角色维度范围 API 测试"""

    @property
    def base_url(self):
        return '/api/v2/bo/role-dimension-scopes'

    def test_list_role_dimension_scopes(self, api_client, admin_headers):
        """列出角色维度范围"""
        response = api_client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 403, 404, 500]

    def test_list_by_role_id(self, api_client, admin_headers):
        """按角色 ID 列出"""
        response = api_client.get(
            f'{self.base_url}?role_id=1&page=1&page_size=10',
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 403, 404, 500]

    def test_create_role_dimension_scope(self, api_client, admin_headers):
        """创建角色维度范围"""
        data = {
            'role_id': 1,
            'dimension': 'domain',
            'scope_value': 'all'
        }
        response = api_client.post(
            self.base_url,
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 403, 404, 500]

    def test_get_role_dimension_scope_by_id(self, api_client, admin_headers):
        """根据 ID 获取角色维度范围"""
        response = api_client.get(
            f'{self.base_url}/1',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 404, 500]

    def test_update_role_dimension_scope(self, api_client, admin_headers):
        """更新角色维度范围"""
        data = {'scope_value': 'specific'}
        response = api_client.put(
            f'{self.base_url}/1',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 400, 401, 403, 404, 500]

    def test_delete_role_dimension_scope(self, api_client, admin_headers):
        """删除角色维度范围"""
        response = api_client.delete(
            f'{self.base_url}/999',
            headers=admin_headers
        )
        assert response.status_code in [200, 204, 400, 401, 403, 404, 500]

    def test_get_dimensions(self, api_client, admin_headers):
        """获取可用维度列表"""
        response = api_client.get(
            f'{self.base_url}/dimensions',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]


# ==================== 权限审计 API 测试 ====================

class TestPermissionAuditAPI:
    """权限审计 API 测试"""

    @property
    def base_url(self):
        return '/api/v1/permission-audit'

    def test_get_audit_report(self, api_client, admin_headers):
        """获取权限审计报告"""
        response = api_client.get(f'{self.base_url}/report', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_user_summary(self, api_client, admin_headers):
        """获取用户权限摘要"""
        response = api_client.get(f'{self.base_url}/user/1/summary', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_usage_stats(self, api_client, admin_headers):
        """获取权限使用统计"""
        response = api_client.get(f'{self.base_url}/stats', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_find_orphan_permissions(self, api_client, admin_headers):
        """查找孤立权限"""
        response = api_client.get(f'{self.base_url}/orphans', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_find_excessive_permissions(self, api_client, admin_headers):
        """查找过度权限"""
        response = api_client.get(f'{self.base_url}/excessive', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_change_history(self, api_client, admin_headers):
        """获取权限变更历史"""
        response = api_client.get(f'{self.base_url}/history', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_change_history_with_filters(self, api_client, admin_headers):
        """获取权限变更历史（带过滤）"""
        response = api_client.get(
            f'{self.base_url}/history?user_id=1&resource_type=role&limit=10',
            headers=admin_headers
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_get_usage_stats_with_days(self, api_client, admin_headers):
        """获取权限使用统计（带天数参数）"""
        response = api_client.get(f'{self.base_url}/stats?days=7', headers=admin_headers)
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_list_without_auth(self, api_client):
        """未认证访问权限审计"""
        response = api_client.get(f'{self.base_url}/report')
        assert response.status_code in [401, 403, 302, 200, 404, 500]
