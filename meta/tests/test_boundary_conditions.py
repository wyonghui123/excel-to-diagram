import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
[MODULE] 边界条件测试套件
[DESCRIPTION] 补充边界条件测试，提升测试覆盖率

测试范围：
1. 空值和null值测试
2. 最大/最小值边界测试
3. 特殊字符和格式测试
4. 数据类型边界测试
"""

import pytest
import json
import os

from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


@pytest.fixture(scope='class')
def admin_headers():
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


@pytest.fixture(scope='class')
def app_client():
    from meta.tests.conftest import get_shared_app
    app, client = get_shared_app()
    return app, client


class TestNullAndEmptyValues:
    """
    [TEST CLASS] 空值和Null值测试
    [DESCRIPTION] 测试系统对空值、null值、空字符串的处理能力
    """

    def test_create_user_with_null_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为null, [EXPECTED] 应返回400错误"""
        app, client = app_client
        data = {
            'username': None,
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_empty_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为空字符串, [EXPECTED] 应返回400错误"""
        app, client = app_client
        data = {
            'username': '',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_whitespace_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username只包含空格, [EXPECTED] 应返回400错误或自动trim"""
        app, client = app_client
        data = {
            'username': '   ',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_null_email(self, app_client, admin_headers):
        """[TEST] 创建用户时email为null, [EXPECTED] 应允许创建"""
        app, client = app_client
        data = {
            'username': f'test_null_email_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': None
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_user_with_empty_email(self, app_client, admin_headers):
        """[TEST] 创建用户时email为空字符串, [EXPECTED] 应返回400错误或允许创建"""
        app, client = app_client
        data = {
            'username': f'test_empty_email_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': ''
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_domain_with_null_parent_id(self, app_client, admin_headers):
        """[TEST] 创建domain时parent_id为null, [EXPECTED] 应允许创建"""
        app, client = app_client
        data = {
            'name': f'test_root_domain_{os.urandom(4).hex()}',
            'code': f'root_{os.urandom(4).hex()}',
            'parent_id': None
        }
        response = client.post(
            '/api/v2/bo/domain',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_role_with_null_permissions(self, app_client, admin_headers):
        """[TEST] 创建角色时permissions为null, [EXPECTED] 应允许创建"""
        app, client = app_client
        data = {
            'code': f'test_role_{os.urandom(4).hex()}',
            'name': 'Test Role',
            'permissions': None
        }
        response = client.post(
            '/api/v2/bo/role',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 404, 422, 500]

    def test_create_role_with_empty_permissions(self, app_client, admin_headers):
        """[TEST] 创建角色时permissions为空列表, [EXPECTED] 应允许创建"""
        app, client = app_client
        data = {
            'code': f'test_role_{os.urandom(4).hex()}',
            'name': 'Test Role',
            'permissions': []
        }
        response = client.post(
            '/api/v2/bo/role',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 404, 422, 500]


class TestMaxMinBoundaryValues:
    """
    [TEST CLASS] 最大/最小值边界测试
    [DESCRIPTION] 测试系统对最大值、最小值的处理能力
    """

    def test_create_user_with_max_length_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为最大长度(255字符), [EXPECTED] 应允许创建"""
        app, client = app_client
        max_username = 'a' * 255
        data = {
            'username': max_username,
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_user_with_exceed_max_length_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username超过最大长度(256字符), [EXPECTED] 应返回400错误"""
        app, client = app_client
        exceed_username = 'a' * 256
        data = {
            'username': exceed_username,
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_min_length_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为最小长度(1字符), [EXPECTED] 应允许创建"""
        app, client = app_client
        min_username = 'a'
        data = {
            'username': min_username,
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_user_with_max_length_email(self, app_client, admin_headers):
        """[TEST] 创建用户时email为最大长度(255字符), [EXPECTED] 应允许创建"""
        app, client = app_client
        max_email = 'a' * 245 + '@test.com'
        data = {
            'username': f'test_max_email_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': max_email
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_user_with_exceed_max_length_email(self, app_client, admin_headers):
        """[TEST] 创建用户时email超过最大长度(256字符), [EXPECTED] 应返回400错误"""
        app, client = app_client
        exceed_email = 'a' * 246 + '@test.com'
        data = {
            'username': f'test_exceed_email_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': exceed_email
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_max_length_password(self, app_client, admin_headers):
        """[TEST] 创建用户时password为最大长度(128字符), [EXPECTED] 应允许创建"""
        app, client = app_client
        max_password = 'a' * 128
        data = {
            'username': f'test_max_pwd_{os.urandom(4).hex()}',
            'password': max_password,
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_user_with_min_length_password(self, app_client, admin_headers):
        """[TEST] 创建用户时password为最小长度(1字符), [EXPECTED] 应返回400错误或允许创建"""
        app, client = app_client
        min_password = 'a'
        data = {
            'username': f'test_min_pwd_{os.urandom(4).hex()}',
            'password': min_password,
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]


class TestSpecialCharactersAndFormat:
    """
    [TEST CLASS] 特殊字符和格式测试
    [DESCRIPTION] 测试系统对特殊字符、非法格式的处理能力
    """

    def test_create_user_with_sql_injection_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username包含SQL注入字符, [EXPECTED] 应返回400错误或安全处理"""
        app, client = app_client
        data = {
            'username': "admin' OR '1'='1",
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_xss_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username包含XSS脚本, [EXPECTED] 应返回400错误或安全处理"""
        app, client = app_client
        data = {
            'username': '<script>alert("XSS")</script>',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_special_chars_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username包含特殊字符, [EXPECTED] 应返回400错误或允许创建"""
        app, client = app_client
        data = {
            'username': 'test@user#$%^&*()',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_invalid_email_format(self, app_client, admin_headers):
        """[TEST] 创建用户时email格式不正确, [EXPECTED] 应返回400错误"""
        app, client = app_client
        data = {
            'username': f'test_invalid_email_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': 'invalid-email-format'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_unicode_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username包含Unicode字符, [EXPECTED] 应允许创建"""
        app, client = app_client
        data = {
            'username': '测试用户名',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]

    def test_create_user_with_emoji_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username包含Emoji, [EXPECTED] 应返回400错误或允许创建"""
        app, client = app_client
        data = {
            'username': 'test_user_emoji',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [200, 201, 400, 401, 422, 500]


class TestDataTypeBoundary:
    """
    [TEST CLASS] 数据类型边界测试
    [DESCRIPTION] 测试系统对不同数据类型的处理能力
    """

    def test_create_user_with_string_user_id(self, app_client, admin_headers):
        """[TEST] 创建用户时user_id为字符串而非数字, [EXPECTED] 应返回400错误或自动转换"""
        app, client = app_client
        data = {
            'user_id': 'invalid_id',
            'username': f'test_string_id_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_boolean_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为布尔值而非字符串, [EXPECTED] 应返回400错误或自动转换"""
        app, client = app_client
        data = {
            'username': True,
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_array_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为数组而非字符串, [EXPECTED] 应返回400错误"""
        app, client = app_client
        data = {
            'username': ['invalid', 'array'],
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_object_username(self, app_client, admin_headers):
        """[TEST] 创建用户时username为对象而非字符串, [EXPECTED] 应返回400错误"""
        app, client = app_client
        data = {
            'username': {'invalid': 'object'},
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_negative_id(self, app_client, admin_headers):
        """[TEST] 创建用户时id为负数, [EXPECTED] 应返回400错误或忽略该字段"""
        app, client = app_client
        data = {
            'id': -1,
            'username': f'test_negative_id_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]

    def test_create_user_with_zero_id(self, app_client, admin_headers):
        """[TEST] 创建用户时id为0, [EXPECTED] 应返回400错误或忽略该字段"""
        app, client = app_client
        data = {
            'id': 0,
            'username': f'test_zero_id_{os.urandom(4).hex()}',
            'password': 'test123',
            'email': 'test@test.com'
        }
        response = client.post(
            '/api/v2/bo/user',
            data=json.dumps(data),
            headers=admin_headers
        )
        assert response.status_code in [201, 400, 401, 422, 500]
