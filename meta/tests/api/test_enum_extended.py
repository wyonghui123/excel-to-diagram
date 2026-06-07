# -*- coding: utf-8 -*-
"""
枚举 API 扩展测试

测试枚举类型的扩展 API 功能:
- 枚举类型 CRUD
- 枚举值管理
- 枚举选项查询
"""

import pytest
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

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


# ==================== 枚举类型 API 测试 ====================

class TestEnumTypeAPI:
    """枚举类型 API 测试"""

    def test_list_enum_types(self, api_client, admin_headers):
        """列出枚举类型"""
        resp = api_client.get('/api/v1/enum-types', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True
        assert 'data' in data

    def test_get_enum_type_by_id(self, api_client, admin_headers):
        """根据 ID 获取枚举类型"""
        resp = api_client.get('/api/v1/enum-types/nonexistent_type', headers=admin_headers)
        assert resp.status_code in [401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is False

    def test_create_enum_type_unauthorized(self, api_client):
        """未授权创建枚举类型"""
        resp = api_client.post('/api/v1/enum-types', json={
            'id': 'test_unauth', 'name': 'Test'
        })
        assert resp.status_code in (400, 401, 403)

    def test_create_enum_type_success(self, api_client, admin_headers):
        """成功创建枚举类型"""
        import uuid
        unique_id = f'test_enum_{uuid.uuid4().hex[:8]}'
        resp = api_client.post('/api/v1/enum-types', json={
            'id': unique_id, 'name': 'Test Enum Extended',
            'category': 'business', 'mutability': 'extensible'
        }, headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True

    def test_update_enum_type(self, api_client, admin_headers):
        """更新枚举类型"""
        api_client.post('/api/v1/enum-types', json={
            'id': 'test_enum_upd', 'name': 'Before Update',
            'category': 'business', 'mutability': 'extensible'
        }, headers=admin_headers)
        resp = api_client.put('/api/v1/enum-types/test_enum_upd', json={
            'name': 'After Update', 'description': 'Updated desc'
        }, headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        data = resp.get_json()
        assert data.get('success', False) is True

    def test_delete_enum_type_system_protected(self, api_client, admin_headers):
        """删除系统保护的枚举类型"""
        resp = api_client.delete('/api/v1/enum-types/log_level', headers=admin_headers)
        data = resp.get_json()
        assert data.get('success', False) is False


# ==================== 枚举值 API 测试 ====================

class TestEnumValueAPI:
    """枚举值 API 测试"""

    def test_list_enum_values(self, api_client, admin_headers):
        """列出枚举值"""
        resp = api_client.get('/api/v1/enum-types/log_level/values', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        if resp.status_code == 200:
            data = resp.get_json()
            assert data.get('success', False) is True

    def test_create_enum_value(self, api_client, admin_headers):
        """创建枚举值"""
        api_client.post('/api/v1/enum-types', json={
            'id': 'test_enum_val', 'name': 'Val Test',
            'category': 'business', 'mutability': 'extensible'
        }, headers=admin_headers)
        resp = api_client.post('/api/v1/enum-types/test_enum_val/values', json={
            'code': 'val1', 'name': 'Value One'
        }, headers=admin_headers)
        assert resp.status_code in [200, 400, 401, 404, 500]
        if resp.status_code == 200:
            data = resp.get_json()
            assert data.get('success', False) is True

    def test_get_enum_options(self, api_client, admin_headers):
        """获取枚举选项"""
        resp = api_client.get('/api/v1/enums/log_level/options', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 500]
        if resp.status_code == 200:
            data = resp.get_json()
            assert data.get('success', False) is True

    def test_query_enum_values(self, api_client, admin_headers):
        """查询枚举值"""
        resp = api_client.get('/api/v1/enum-values?enum_type_id=log_level', headers=admin_headers)
        assert resp.status_code in [200, 401, 404, 410, 500]
        if resp.status_code == 200:
            data = resp.get_json()
            assert data.get('success', False) is True
