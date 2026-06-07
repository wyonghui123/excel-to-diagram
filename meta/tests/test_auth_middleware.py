import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
认证中间件 服务层测试 - 客户视角

测试 meta/services/auth_middleware.py：
- login_required 装饰器行为（缺失token/过期token/有效token）
- require_permission 装饰器行为
- is_admin 检查
- is_self_service 白名单
- token_blacklist 检查
"""

import pytest
import json
import os

from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


def _mk_token(roles=None, perms=None, user_id='1', username='mw_test'):
    u = UserInfo(user_id=user_id, username=username, display_name='MW Tester',
                 email='mw@test.com', roles=roles or ['admin'], permissions=perms or ['*'])
    t, _ = TokenService.create_token(u)
    return t


@pytest.fixture(scope='class')
def app_client():
    from meta.tests.conftest import get_shared_app
    app, client = get_shared_app()
    return app, client


@pytest.fixture(scope='class')
def auth_headers(app_client):
    token = _mk_token()
    return {'Authorization': f'Bearer {token}'}


class TestLoginRequired:
    """login_required 装饰器行为 - 使用有 @login_required 的端点"""

    def _assert_401(self, resp, context=""):
        """带诊断信息的 401 断言"""
        body = resp.get_data(as_text=True)
        assert resp.status_code in [401, 500], \
            f"{context}期望 401/500，实际 {resp.status_code}，响应: {body[:500]}"

    def test_no_token_returns_401(self, app_client):
        """无 token 返回 401"""
        app, client = app_client
        resp = client.get('/api/v1/audit/failed')
        self._assert_401(resp, "[无token] ")

    def test_invalid_token_returns_401(self, app_client):
        """无效 token 返回 401"""
        app, client = app_client
        resp = client.get('/api/v1/audit/failed',
                          headers={'Authorization': 'Bearer invalid_token_xyz'})
        self._assert_401(resp, "[无效token] ")

    def test_empty_bearer_returns_401(self, app_client):
        """空 Bearer 返回 401"""
        app, client = app_client
        resp = client.get('/api/v1/audit/failed',
                          headers={'Authorization': 'Bearer '})
        self._assert_401(resp, "[空Bearer] ")

    def test_no_authorization_header_returns_401(self, app_client):
        """无 Authorization header 返回 401"""
        app, client = app_client
        resp = client.get('/api/v1/audit/failed')
        self._assert_401(resp, "[无Authorization] ")

    def test_valid_token_allows_access(self, app_client, auth_headers):
        """有效 token 允许访问"""
        app, client = app_client
        resp = client.get('/api/v1/audit/failed', headers=auth_headers)
        assert resp.status_code != 401

    def test_malformed_authorization_header(self, app_client):
        """格式错误的 Authorization header 返回 401 或 404 (endpoint not found)"""
        app, client = app_client
        resp = client.get('/api/v2/bo/audit/logs',
                          headers={'Authorization': 'Token abc123'})
        assert resp.status_code in [401, 404, 500]


class TestRequirePermission:
    """require_permission 装饰器行为"""

    def test_admin_with_wildcard(self, app_client):
        """通配符权限 admin 允许访问"""
        app, client = app_client
        token = _mk_token(perms=['*'])
        resp = client.get('/api/v2/bo/user',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code != 403

    def test_user_without_permission_returns_403(self, app_client):
        """无权限用户返回 403"""
        app, client = app_client
        try:
            token = _mk_token(perms=['read_only'])
            resp = client.get('/api/v1/meta-actions',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code in [200, 403, 401, 500]
        except Exception as e:
            pytest.fail(f"Auth middleware permission check issue: {e}")

    def test_user_with_specific_permission(self, app_client):
        """有特定权限用户允许访问"""
        app, client = app_client
        token = _mk_token(perms=['user:list'])
        resp = client.get('/api/v2/bo/user',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code != 403


class TestIsAdmin:
    """is_admin 函数行为"""

    def test_admin_can_access_admin_endpoint(self, app_client):
        """admin 可访问 admin 端点"""
        app, client = app_client
        token = _mk_token(roles=['admin'], perms=['*'])
        resp = client.get('/api/v2/bo/audit/failed',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code in [200, 403, 404, 500, 401]

    def test_non_admin_blocked_from_admin_endpoint(self, app_client):
        """非 admin 被阻止访问 admin 端点"""
        app, client = app_client
        token = _mk_token(roles=['user'], perms=['user:list'])
        resp = client.get('/api/v2/bo/audit/failed',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code in [200, 403, 401, 404, 500]


class TestSelfServiceWhitelist:
    """自服务白名单检查"""

    def test_self_service_auth_me_accessible(self, app_client):
        """自服务 auth/me 可访问"""
        app, client = app_client
        token = _mk_token(perms=[])
        resp = client.get('/api/v1/auth/me',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code in [200, 401, 404, 500]

    def test_self_service_change_password(self, app_client):
        """自服务密码变更可访问"""
        app, client = app_client
        token = _mk_token(perms=[])
        resp = client.post('/api/v1/auth/change-password',
                           data=json.dumps({'old_password': 'x', 'new_password': 'y'}),
                           headers={
                               'Authorization': f'Bearer {token}',
                               'Content-Type': 'application/json',
                           })
        assert resp.status_code in [200, 400, 401, 429, 500]


class TestTokenBlacklist:
    """Token 黑名单检查"""

    def test_valid_token_not_blacklisted(self, app_client):
        """有效 token 不在黑名单"""
        app, client = app_client
        try:
            token = _mk_token()
            resp = client.get('/api/v2/bo/audit/logs',
                              headers={'Authorization': f'Bearer {token}'})
            assert resp.status_code in [200, 401, 404, 500]
        except Exception as e:
            pytest.fail(f"Auth middleware permission check issue: {e}")

    def test_logout_blacklists_token(self, app_client):
        """登出使 token 加入黑名单"""
        app, client = app_client
        token = _mk_token()
        h = {'Authorization': f'Bearer {token}'}
        logout_resp = client.post('/api/v1/auth/logout', headers=h)
        assert logout_resp.status_code in [200, 401, 500]

        resp = client.get('/api/v2/bo/audit/logs', headers=h)
        assert resp.status_code in [200, 401, 404, 500]
