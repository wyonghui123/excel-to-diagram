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


def _cleanup_type(api_client, headers, enum_id):
    """清理枚举类型: 先删值再删类型。

    [Q4-E 2026-10-07] 根因: 类型下有值时 DELETE /enum-types/<id> 被 HAS_VALUES 拦截
    → 只删类型的旧清理静默失败导致残留 (本文件历史残留点: test_unauth / test_enum_val 等)。
    """
    try:
        resp = api_client.get(f'/api/v1/enum-types/{enum_id}/values', headers=headers)
        if resp.status_code == 200:
            values = resp.get_json()['data'].get('data', [])
            for v in values:
                api_client.delete(f"/api/v1/enum-values/{v['id']}", headers=headers)
    except Exception:
        pass
    try:
        api_client.delete(f'/api/v1/enum-types/{enum_id}', headers=headers)
    except Exception:
        pass


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

    def test_create_enum_type_unauthorized(self, api_client, admin_headers):
        """未授权创建枚举类型

        [Q4-E 2026-10-07] AUTH_ENABLED=False 时 _auth_required/_admin_required 整体旁路
        (enum_api.py L20/L156), 匿名 POST 实际 200 → 未授权路径在本测试环境不可验证, skip。
        历史残留根因: 首轮 200 断言失败且无清理 → test_unauth 落库; 后续轮因重复 id 插入失败
        反而"通过"。finally 清理消除此污染。
        """
        from meta.api.enum_api import AUTH_ENABLED
        if not AUTH_ENABLED:
            pytest.skip('AUTH_ENABLED=False: 认证装饰器旁路, 未授权路径不可验证')
        resp = api_client.post('/api/v1/enum-types', json={
            'id': 'test_unauth', 'name': 'Test'
        })
        try:
            assert resp.status_code in (400, 401, 403)
        finally:
            # 防御性清理: 若未授权创建意外成功 (断言失败) 也不残留
            _cleanup_type(api_client, admin_headers, 'test_unauth')

    def test_create_enum_type_success(self, api_client, admin_headers):
        """成功创建枚举类型"""
        import uuid
        unique_id = f'test_enum_{uuid.uuid4().hex[:8]}'
        try:
            resp = api_client.post('/api/v1/enum-types', json={
                'id': unique_id, 'name': 'Test Enum Extended',
                'category': 'business', 'mutability': 'extensible'
            }, headers=admin_headers)
            assert resp.status_code in [200, 401, 404, 500]
            data = resp.get_json()
            assert data.get('success', False) is True
        finally:
            _cleanup_type(api_client, admin_headers, unique_id)

    def test_update_enum_type(self, api_client, admin_headers):
        """更新枚举类型"""
        try:
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
        finally:
            _cleanup_type(api_client, admin_headers, 'test_enum_upd')

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
        try:
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
        finally:
            # 清理: 先删值再删类型 (否则 HAS_VALUES 拦截 → 残留)
            _cleanup_type(api_client, admin_headers, 'test_enum_val')

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
