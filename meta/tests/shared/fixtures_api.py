# -*- coding: utf-8 -*-
"""
[MODULE] API 测试 Fixtures
[DESCRIPTION] 提供 API 测试所需的共享 fixtures

使用方式：
1. 在测试文件中导入：
   from meta.tests.shared.fixtures_api import api_client, admin_headers

2. 或直接在测试中使用：
   def test_something(api_client, admin_headers):
       response = api_client.get('/api/v2/bo/user', headers=admin_headers)
"""

import pytest
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


@pytest.fixture(scope="session")
def api_client():
    """
    [FIXTURE] API 测试客户端
    [DESCRIPTION] 共享 Flask 测试客户端
    [SCOPE] session - 整个测试会话复用
    """
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()
    return client


@pytest.fixture(scope="session")
def admin_headers(api_client):
    """
    [FIXTURE] 管理员认证头
    [DESCRIPTION] 包含管理员 JWT Token 的请求头
    [SCOPE] session - 整个测试会话复用
    """
    user = UserInfo(
        user_id='1',
        username='admin',
        display_name='Admin',
        email='admin@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)

    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'admin',
    }


@pytest.fixture(scope="session")
def regular_user_headers():
    """
    [FIXTURE] 普通用户认证头
    [DESCRIPTION] 普通用户 JWT Token 的请求头
    [SCOPE] session - 整个测试会话复用
    """
    user = UserInfo(
        user_id='9999',
        username='regular_user',
        display_name='Regular User',
        email='user@test.com',
        roles=['viewer'],
        permissions=['user:read']
    )
    token, _ = TokenService.create_token(user)

    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }


@pytest.fixture
def api_client_and_headers(api_client, admin_headers):
    """
    [FIXTURE] API 客户端和认证头元组
    [DESCRIPTION] 返回 (client, headers) 元组
    [USAGE]
        def test_something(api_client_and_headers):
            client, headers = api_client_and_headers
            response = client.get('/api/v2/bo/user', headers=headers)
    """
    return api_client, admin_headers


# ==================== 导出 ====================

__all__ = [
    'api_client',
    'admin_headers',
    'regular_user_headers',
    'api_client_and_headers',
]
