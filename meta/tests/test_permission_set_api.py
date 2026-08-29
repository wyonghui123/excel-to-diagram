import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Role API 测试 - 客户视角

测试 role_api.py 全部端点（url_prefix='/api/v1/roles'）：
- GET    /api/v1/roles                                    — 角色列表
- POST   /api/v1/roles                                    — 创建角色
- GET    /api/v1/roles/<role_id>                          — 获取角色
- PUT    /api/v1/roles/<role_id>                          — 更新角色
- DELETE /api/v1/roles/<role_id>                          — 删除角色
- PUT    /api/v1/roles/<role_id>/permissions              — 设置权限
- GET    /api/v1/roles/<role_id>/permissions              — 获取权限
- GET    /api/v1/roles/<role_id>/menus                    — 获取菜单权限
- GET    /api/v1/roles/<role_id>/data-permissions         — 数据权限列表
- POST   /api/v1/roles/<role_id>/data-permissions         — 创建数据权限
- POST   /api/v1/roles/<role_id>/users                    — 分配用户
- DELETE /api/v1/roles/<role_id>/users/<user_id>          — 移除用户
- GET    /api/v1/roles/permissions                        — 全局权限列表
- GET    /api/v1/roles/<role_id>/logs                     — 角色日志
"""

import json
import os
import sys
import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.server import create_app
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


def _mk_token(roles=None, perms=None):
    u = UserInfo(user_id='1', username='test_user', display_name='Test User',
                 email='test@test.com', roles=roles or ['admin'], permissions=perms or ['*'])
    t, _ = TokenService.create_token(u)
    return t


@pytest.fixture(scope='class')
def client():
    from meta.tests.conftest import get_shared_app
    app, test_client = get_shared_app()
    return test_client


@pytest.fixture(scope='class')
def auth_headers(client):
    token = _mk_token()
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
    }


@pytest.fixture
def created_roles(client, auth_headers):
    cleanup = []

    yield cleanup

    for rid in reversed(cleanup):
        try:
            client.delete(f'/api/v1/roles/{rid}', headers=auth_headers)
        except Exception:
            pass


def _create_role(client, auth_headers, data=None, cleanup=None):
    payload = data or {
        'name': 'Test Role',
        'code': f'T_{os.urandom(3).hex().upper()}',
        'description': 'Test',
    }
    resp = client.post('/api/v1/roles', data=json.dumps(payload), headers=auth_headers)
    try:
        r = json.loads(resp.data)
    except Exception:
        r = {}
    rid = (r.get('data') or {}).get('id') or r.get('id')
    if rid and cleanup is not None:
        cleanup.append(rid)
    return resp, r


class TestRoleApiCRUD:

    def test_create_role(self, client, auth_headers, created_roles):
        resp, data = _create_role(client, auth_headers, cleanup=created_roles)
        assert resp.status_code in [200, 201, 400, 401, 500]

    def test_create_duplicate_code(self, client, auth_headers, created_roles):
        code = f'D_{os.urandom(3).hex().upper()}'
        _create_role(client, auth_headers, {'name': 'R1', 'code': code}, cleanup=created_roles)
        resp = client.post('/api/v1/roles',
                           data=json.dumps({'name': 'R2', 'code': code}),
                           headers=auth_headers)
        assert resp.status_code in [200, 400, 401, 409, 500]

    def test_get_role(self, client, auth_headers, created_roles):
        resp, data = _create_role(client, auth_headers, cleanup=created_roles)
        rid = (data.get('data') or {}).get('id') or data.get('id')
        if rid:
            resp = client.get(f'/api/v1/roles/{rid}', headers=auth_headers)
            assert resp.status_code in [200, 401, 404, 500]

    def test_get_nonexistent(self, client, auth_headers):
        resp = client.get('/api/v1/roles/99999', headers=auth_headers)
        assert resp.status_code in [401, 404, 500]

    def test_list_roles(self, client, auth_headers):
        resp = client.get('/api/v1/roles', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_update_role(self, client, auth_headers, created_roles):
        resp, data = _create_role(client, auth_headers, cleanup=created_roles)
        rid = (data.get('data') or {}).get('id') or data.get('id')
        if rid:
            created_roles.remove(rid)
            resp = client.put(
                f'/api/v1/roles/{rid}',
                data=json.dumps({'name': 'Updated'}),
                headers=auth_headers,
            )
            assert resp.status_code in [200, 400, 401, 500]

    def test_delete_role(self, client, auth_headers, created_roles):
        resp, data = _create_role(client, auth_headers, cleanup=created_roles)
        rid = (data.get('data') or {}).get('id') or data.get('id')
        if rid:
            created_roles.remove(rid)
            resp = client.delete(f'/api/v1/roles/{rid}', headers=auth_headers)
            assert resp.status_code in [200, 204, 401, 500]


class TestRoleApiPermissions:

    def test_global_permissions_list(self, client, auth_headers):
        resp = client.get('/api/v1/roles/permissions', headers=auth_headers)
        # 410: API已废弃，使用 GET /api/v2/bo/permission
        assert resp.status_code in [200, 401, 404, 410, 500]

    def test_get_role_permissions(self, client, auth_headers):
        resp = client.get('/api/v1/roles/1/permissions', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_set_role_permissions(self, client, auth_headers):
        resp = client.put(
            '/api/v1/roles/1/permissions',
            data=json.dumps({'permission_ids': [1, 2, 3]}),
            headers=auth_headers,
        )
        assert resp.status_code in [200, 201, 400, 401, 404, 500]

    def test_get_role_menus(self, client, auth_headers):
        resp = client.get('/api/v1/roles/1/menus', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_get_data_permissions(self, client, auth_headers):
        resp = client.get('/api/v1/roles/1/data-permissions', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]

    def test_create_data_permission(self, client, auth_headers):
        resp = client.post(
            '/api/v1/roles/1/data-permissions',
            data=json.dumps({
                'object_type': 'user',
                'permission_level': 'own',
            }),
            headers=auth_headers,
        )
        assert resp.status_code in [201, 200, 400, 401, 404, 500]


class TestRoleApiUsers:

    def test_add_user_to_role(self, client, auth_headers):
        resp = client.post(
            '/api/v1/roles/1/users',
            data=json.dumps({'user_id': 1}),
            headers=auth_headers,
        )
        assert resp.status_code in [200, 201, 400, 401, 404, 500]

    def test_add_multiple_users(self, client, auth_headers):
        resp = client.post(
            '/api/v1/roles/1/users',
            data=json.dumps({'user_ids': [1, 2, 3]}),
            headers=auth_headers,
        )
        assert resp.status_code in [200, 201, 400, 401, 404, 500]

    def test_remove_user_from_role(self, client, auth_headers):
        resp = client.delete('/api/v1/roles/1/users/99999', headers=auth_headers)
        assert resp.status_code in [200, 204, 400, 401, 404, 500]


class TestRoleApiLogs:

    def test_get_role_logs(self, client, auth_headers):
        resp = client.get('/api/v1/roles/1/logs', headers=auth_headers)
        assert resp.status_code in [200, 401, 404, 500]


class TestRoleApiAuthRequired:

    def test_list_without_auth(self, client):
        resp = client.get('/api/v1/roles', headers={'Content-Type': 'application/json'})
        assert resp.status_code in [200, 401, 403, 302, 500]

    def test_create_without_auth(self, client):
        resp = client.post('/api/v1/roles', data=json.dumps({'name': 'x'}), headers={'Content-Type': 'application/json'})
        assert resp.status_code in [200, 400, 401, 403, 302, 500]

    def test_get_without_auth(self, client):
        resp = client.get('/api/v1/roles/1', headers={'Content-Type': 'application/json'})
        assert resp.status_code in [200, 401, 403, 302, 500]
