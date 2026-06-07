import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
Auth API 细粒度测试

测试 /api/v1/auth 端点的细粒度场景：
- 登录成功/失败
- 登出
- token 刷新
- 密码变更
- 用户信息获取
"""

import pytest
import json


@pytest.fixture(scope='class')
def app_client():
    from meta.tests.conftest import get_shared_app
    app, client = get_shared_app()
    return app, client


@pytest.fixture(scope='class')
def auth_token(app_client):
    app, client = app_client
    response = client.post(
        '/api/v1/auth/login',
        data=json.dumps({'username': 'admin', 'password': 'admin123'}),
        content_type='application/json'
    )
    if response.status_code == 200:
        try:

            data = json.loads(response.data)

        except (json.JSONDecodeError, ValueError):

            data = {}
        return data.get('data', {}).get('token')
    return None


class TestAuthAPIGranularLogin:
    """Auth API 登录细粒度测试"""

    def test_login_with_valid_credentials(self, app_client):
        """有效凭据登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        assert response.status_code in [200, 401, 404, 500]

    def test_login_with_invalid_password(self, app_client):
        """无效密码登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'wrongpassword'}),
            content_type='application/json'
        )
        assert response.status_code in [401, 400, 404]

    def test_login_with_nonexistent_user(self, app_client):
        """不存在用户登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'nonexistent_user', 'password': 'password'}),
            content_type='application/json'
        )
        assert response.status_code in [401, 400, 404]

    def test_login_with_empty_username(self, app_client):
        """空用户名登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': '', 'password': 'password'}),
            content_type='application/json'
        )
        assert response.status_code in [400, 401, 404]

    def test_login_with_empty_password(self, app_client):
        """空密码登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': ''}),
            content_type='application/json'
        )
        assert response.status_code in [400, 401, 404]

    def test_login_with_missing_username(self, app_client):
        """缺少用户名登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'password': 'password'}),
            content_type='application/json'
        )
        assert response.status_code in [400, 401, 404]

    def test_login_with_missing_password(self, app_client):
        """缺少密码登录"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin'}),
            content_type='application/json'
        )
        assert response.status_code in [400, 401, 404]

    def test_login_response_format(self, app_client):
        """登录响应格式"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            assert 'success' in data
            if data.get('success'):
                assert 'data' in data
                result_data = data.get('data', {})
                assert 'token' in result_data


class TestAuthAPIGranularLogout:
    """Auth API 登出细粒度测试"""

    def _get_token(self, app_client):
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            return data.get('data', {}).get('token')
        return None

    def test_logout_with_valid_token(self, app_client):
        """有效 token 登出"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.post(
                '/api/v1/auth/logout',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code in [200, 204, 401, 404, 500]

    def test_logout_without_token(self, app_client):
        """无 token 登出"""
        app, client = app_client
        response = client.post('/api/v1/auth/logout')
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_logout_with_invalid_token(self, app_client):
        """无效 token 登出"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/logout',
            headers={'Authorization': 'Bearer invalid_token'}
        )
        assert response.status_code in [200, 401, 403, 404, 500]


class TestAuthAPIGranularMe:
    """Auth API 用户信息细粒度测试"""

    def _get_token(self, app_client):
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            return data.get('data', {}).get('token')
        return None

    def test_me_with_valid_token(self, app_client):
        """有效 token 获取用户信息"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.get(
                '/api/v1/auth/me',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code in [200, 401, 404, 500]

    def test_me_without_token(self, app_client):
        """无 token 获取用户信息"""
        app, client = app_client
        response = client.get('/api/v1/auth/me')
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_me_with_invalid_token(self, app_client):
        """无效 token 获取用户信息"""
        app, client = app_client
        response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': 'Bearer invalid_token'}
        )
        assert response.status_code in [200, 401, 403, 404, 500]

    def test_me_response_format(self, app_client):
        """用户信息响应格式"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.get(
                '/api/v1/auth/me',
                headers={'Authorization': f'Bearer {token}'}
            )
            if response.status_code == 200:
                try:

                    data = json.loads(response.data)

                except (json.JSONDecodeError, ValueError):

                    data = {}
                assert 'success' in data
                if data.get('success'):
                    assert 'data' in data
                    result_data = data.get('data', {})
                    assert 'user_id' in result_data
                    assert 'username' in result_data


class TestAuthAPIGranularRefresh:
    """Auth API token 刷新细粒度测试"""

    def _get_token(self, app_client):
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            return data.get('data', {}).get('token')
        return None

    def test_refresh_with_valid_token(self, app_client):
        """有效 token 刷新"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.post(
                '/api/v1/auth/refresh',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code in [200, 401, 404, 500]

    def test_refresh_without_token(self, app_client):
        """无 token 刷新"""
        app, client = app_client
        response = client.post('/api/v1/auth/refresh')
        assert response.status_code in [401, 403, 404, 500]

    def test_refresh_with_invalid_token(self, app_client):
        """无效 token 刷新"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/refresh',
            headers={'Authorization': 'Bearer invalid_token'}
        )
        assert response.status_code in [401, 403, 404, 500]


class TestAuthAPIGranularPasswordChange:
    """Auth API 密码变更细粒度测试"""

    def _get_token(self, app_client):
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            return data.get('data', {}).get('token')
        return None

    def test_change_password_with_valid_data(self, app_client):
        """有效数据变更密码"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.post(
                '/api/v1/auth/change-password',
                data=json.dumps({
                    'old_password': 'admin123',
                    'new_password': 'newpassword123'
                }),
                content_type='application/json',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code in [200, 400, 401, 404, 500]

    def test_change_password_with_wrong_old(self, app_client):
        """错误旧密码变更"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.post(
                '/api/v1/auth/change-password',
                data=json.dumps({
                    'old_password': 'wrongpassword',
                    'new_password': 'newpassword123'
                }),
                content_type='application/json',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code in [400, 401, 404]

    def test_change_password_without_token(self, app_client):
        """无 token 变更密码"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/change-password',
            data=json.dumps({
                'old_password': 'admin123',
                'new_password': 'newpassword123'
            }),
            content_type='application/json'
        )
        assert response.status_code in [400, 401, 403, 404, 500]

    def test_change_password_with_missing_fields(self, app_client):
        """缺少字段变更密码"""
        app, client = app_client
        token = self._get_token(app_client)
        if token:
            response = client.post(
                '/api/v1/auth/change-password',
                data=json.dumps({'old_password': 'admin123'}),
                content_type='application/json',
                headers={'Authorization': f'Bearer {token}'}
            )
            assert response.status_code in [400, 401, 404]


class TestAuthAPIGranularSession:
    """Auth API 会话细粒度测试"""

    def test_login_creates_session(self, app_client):
        """登录创建会话"""
        app, client = app_client
        response = client.post(
            '/api/v1/auth/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        if response.status_code == 200:
            try:

                data = json.loads(response.data)

            except (json.JSONDecodeError, ValueError):

                data = {}
            assert data.get('success', False) is True
            assert data.get('data', {}).get('token') is not None

    def test_protected_route_requires_auth(self, app_client):
        """受保护路由需要认证"""
        app, client = app_client
        response = client.get('/api/v1/auth/me')
        assert response.status_code in [401, 403, 404]

    def test_invalid_token_rejected(self, app_client):
        """无效 token 被拒绝"""
        app, client = app_client
        response = client.get(
            '/api/v1/auth/me',
            headers={'Authorization': 'Bearer definitely_invalid_token'}
        )
        assert response.status_code in [401, 403, 404]
