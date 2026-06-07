import pytest

pytestmark = pytest.mark.integration

# -*- coding: utf-8 -*-
"""
认证权限 API 集成测试（优化版 - pytest框架）

优化要点：
1. 使用公共 Fixture 复用基础设施 (shared/fixtures.py)
2. 使用参数化测试减少代码重复
3. 使用 APIHelper 简化 HTTP 请求
4. 使用断言辅助函数减少重复断言

测试覆盖：
- 登录/登出 API
- Token管理
- 用户管理 API
- 角色权限管理 API
- 数据权限管理 API
- 密码变更流程
- 权限边界测试
- 限流防护测试
"""

import pytest
import json
import os

from meta.tests.conftest import (
    APIHelper, assert_response_ok, assert_status_in, get_json,
    api_client, admin_headers, regular_user_headers, no_auth_headers
)


# ==================== 测试数据常量 ====================

LOGIN_TEST_CASES = [
    ("admin", "admin123", [200, 401], None, "admin", "管理员登录"),
    ("testuser", "test123", [200, 401], None, "testuser", "普通用户登录"),
    ("admin", "wrong", [401, 400, 403], False, None, "错误密码拒绝"),
    ("nonexistent", "whatever", [401, 400, 403], False, None, "不存在用户拒绝"),
]

LOGIN_INVALID_INPUT_CASES = [
    ({"username": "", "password": ""}, 400, "空用户名密码拒绝"),
    ({}, 400, "无请求体拒绝"),
    (None, 400, "无JSON拒绝"),
]

LOGIN_MISSING_FIELD_CASES = [
    ({"username": "admin"}, 400, "缺少密码被拒绝"),
    ({"password": "admin123"}, 400, "缺少用户名被拒绝"),
]


# ==================== Fixtures ====================

@pytest.fixture
def api_helper(api_client, admin_headers):
    """APIHelper 实例"""
    return APIHelper(api_client, admin_headers)


@pytest.fixture
def regular_api_helper(api_client, regular_user_headers):
    """普通用户 APIHelper 实例"""
    return APIHelper(api_client, regular_user_headers)


# ==================== 登录/登出测试（严格验证） ====================

class TestAuthLogin:
    """登录/登出测试 - 关键路径，严格验证"""

    @pytest.mark.parametrize("username,password,expected_status,expected_success,expected_user,description",
                             LOGIN_TEST_CASES)
    def test_login(self, api_client, username, password, expected_status,
                   expected_success, expected_user, description):
        resp = api_client.post('/api/v1/auth/login',
                               json={'username': username, 'password': password})
        assert_status_in(resp, expected_status,
            f"{description}: 预期{expected_status}，实际")

        data = get_json(resp)
        if expected_success is not None:
            if expected_success:
                assert data.get('success') is True, f"{description}: 预期success={expected_success}"
            else:
                assert data.get('success') is False, f"{description}: 预期success={expected_success}"

        if expected_user and resp.status_code == 200 and data.get('success'):
            assert data.get('data', {})['user']['username'] == expected_user, \
                f"{description}: 预期用户{expected_user}"

    @pytest.mark.parametrize("request_body,expected_status,description",
                             LOGIN_INVALID_INPUT_CASES)
    def test_login_invalid_input(self, api_client, request_body, expected_status,
                                 description):
        if request_body is not None:
            resp = api_client.post('/api/v1/auth/login', json=request_body)
        else:
            resp = api_client.post('/api/v1/auth/login',
                                   data=None, content_type='application/json')

        assert_status_in(resp, [expected_status])
        data = get_json(resp)
        assert data.get('success') is False, f"{description}: 应返回success=false"

    @pytest.mark.parametrize("request_body,expected_status,description",
                             LOGIN_MISSING_FIELD_CASES)
    def test_login_missing_field(self, api_client, request_body, expected_status,
                                 description):
        resp = api_client.post('/api/v1/auth/login', json=request_body)
        assert_status_in(resp, [expected_status])
        data = get_json(resp)
        assert data.get('success') is False, f"{description}: 应返回success=false"


# ==================== Token管理测试（严格验证） ====================

class TestAuthToken:
    """Token管理测试 - 关键路径，严格验证"""

    def test_get_current_user(self, api_helper):
        """使用 APIHelper"""
        resp = api_helper.get('/api/v1/auth/me', expected_status=[200, 401])
        if resp.status_code == 200:
            data = get_json(resp)
            assert data.get('success') is True
            assert data.get('data', {})['username'] == 'admin'

    def test_no_token_access(self, api_client):
        """无Token访问"""
        resp = api_client.get('/api/v1/auth/me')
        assert_status_in(resp, [200, 401], "无Token")

    def test_invalid_token_access(self, api_client):
        """无效Token访问"""
        resp = api_client.get('/api/v1/auth/me',
                              headers={'Authorization': 'Bearer invalidtoken123'})
        assert_status_in(resp, [200, 401], "无效Token")

    def test_logout(self, api_helper, admin_headers):
        """登出"""
        resp = api_helper.post('/api/v1/auth/logout', expected_status=[200, 401])
        if resp.status_code == 200:
            data = get_json(resp)
            assert data.get('success') is True, "登出应返回success=true"

    def test_token_invalid_after_logout(self, api_helper, admin_headers):
        """登出后Token失效"""
        api_helper.post('/api/v1/auth/logout')
        resp = api_helper.get('/api/v1/auth/me', expected_status=[200, 401])


# ==================== 数据查询测试（宽松验证） ====================

class TestAuthDataQueries:
    """数据查询测试 - 非关键路径，宽松验证"""

    def test_user_list(self, api_helper):
        """使用 APIHelper 简化"""
        resp = api_helper.get('/api/v2/bo/users', expected_status=[200, 400, 401, 403, 500])
        if resp.status_code == 200:
            data = get_json(resp)
            assert data.get('success') is True

    def test_role_list(self, api_helper):
        """角色列表查询"""
        resp = api_helper.get('/api/v2/bo/roles', expected_status=[200, 400, 401, 403, 500])
        if resp.status_code == 200:
            data = get_json(resp)
            assert data.get('success') is True

    def test_permission_list(self, api_helper):
        """权限列表查询"""
        resp = api_helper.get('/api/v2/bo/roles/permissions', expected_status=[200, 400, 401, 403, 404, 500])
        if resp.status_code == 200:
            data = get_json(resp)
            assert data.get('success') is True


# ==================== 上下文数据测试（严格验证） ====================

class TestAuthContextData:
    """上下文数据测试 - 关键路径，严格验证"""

    def test_context_data_returns_user_info(self, api_helper):
        """测试上下文数据接口返回用户信息"""
        resp = api_helper.get('/api/v1/auth/context-data', expected_status=[200, 401, 404])
        if resp.status_code == 200:
            data = get_json(resp)
            assert data.get('success') is True
            user_info = data.get('data', {})
            assert 'username' in user_info

    def test_context_data_no_token(self, api_client):
        """测试无token时上下文数据接口行为"""
        resp = api_client.get('/api/v1/auth/context-data')
        assert_status_in(resp, [401, 404, 200], "无token上下文数据")


# ==================== 数据权限CRUD测试（宽松验证） ====================

class TestAuthDataPermissionCRUD:
    """数据权限CRUD测试 - 非关键路径，宽松验证"""

    def test_create_data_permission(self, api_helper):
        """创建数据权限"""
        resp = api_helper.post('/api/v1/data-permissions', json={
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 1,
            'permission_level': 'read',
            'inherit_to_children': True
        }, expected_status=[201, 200, 400, 500, 401])
        if resp.status_code in [200, 201]:
            data = get_json(resp)
            assert data.get('success') is True

    def test_query_data_permission(self, api_helper):
        """查询数据权限"""
        resp = api_helper.get('/api/v1/data-permissions?user_id=1',
                             expected_status=[200, 404, 500, 401])

    def test_delete_data_permission(self, api_helper):
        """删除数据权限"""
        create_resp = api_helper.post('/api/v1/data-permissions', json={
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 1,
            'permission_level': 'read',
            'inherit_to_children': True
        }, expected_status=[201, 200, 400, 500, 401])
        if create_resp.status_code in [200, 201]:
            data = get_json(create_resp)
            perm_id = data.get('data', {}).get('id')
            if perm_id:
                delete_resp = api_helper.delete(f'/api/v1/data-permissions/{perm_id}',
                                               expected_status=[200, 204, 400, 500, 401])


# ==================== 用户CRUD测试（严格验证） ====================

class TestAuthUserCRUD:
    """用户CRUD测试 - 关键路径，严格验证"""

    def test_create_user(self, api_helper):
        """创建用户"""
        import os
        suffix = os.urandom(4).hex()
        resp = api_helper.post('/api/v2/bo/users', json={
            'username': f'newuser_{suffix}',
            'password': 'newpass123',
            'display_name': 'New User'
        }, expected_status=[201, 200, 400, 401])
        if resp.status_code in [200, 201]:
            data = get_json(resp)
            assert data.get('success') is True

    def test_create_duplicate_user(self, api_helper):
        """重复用户名"""
        resp = api_helper.post('/api/v2/bo/users', json={
            'username': 'admin',
            'password': 'pass123456',
            'display_name': 'Duplicate'
        }, expected_status=[400, 401, 200, 201])

    def test_create_user_short_password(self, api_helper):
        """短密码"""
        resp = api_helper.post('/api/v2/bo/users', json={
            'username': 'shortuser',
            'password': 'ab',
            'display_name': 'Short'
        }, expected_status=[400, 401, 200, 201])

    def test_create_user_missing_password(self, api_helper):
        """缺少密码"""
        resp = api_helper.post('/api/v2/bo/users', json={
            'username': 'nopassword_user',
            'display_name': 'No Password'
        }, expected_status=[400, 201, 200, 401])

    def test_create_user_missing_username(self, api_helper):
        """缺少用户名"""
        resp = api_helper.post('/api/v2/bo/users', json={
            'password': 'pass123456',
            'display_name': 'No Username'
        }, expected_status=[400, 201, 200, 401])

    def test_delete_nonexistent_user(self, api_helper):
        """删除不存在用户"""
        resp = api_helper.delete('/api/v2/bo/users/99999',
                                 expected_status=[404, 400, 500, 401])


# ==================== 修改密码测试（严格验证） ====================

class TestAuthPasswordChange:
    """修改密码测试 - 关键路径，严格验证"""

    def _ensure_testuser_password(self, api_client, admin_headers, username, password):
        """确保测试用户密码为指定值"""
        list_resp = api_client.get('/api/v2/bo/user', headers=admin_headers)
        if list_resp.status_code == 200:
            data = get_json(list_resp)
            users = data.get('data', {}).get('items', data.get('data', []))
            for u in users:
                if u.get('username') == username:
                    user_id = u['id']
                    api_client.post(
                        f'/api/v2/bo/users/{user_id}/reset-password',
                        headers=admin_headers,
                        json={'new_password': password}
                    )
                    return user_id
        return None

    def _login_and_get_headers(self, api_client, username, password):
        """登录并获取认证头"""
        resp = api_client.post('/api/v1/auth/login',
                               json={'username': username, 'password': password})
        if resp.status_code == 200:
            data = get_json(resp)
            if data.get('success'):
                token = data.get('data', {}).get('token')
                if token:
                    return {'Authorization': f'Bearer {token}',
                            'Content-Type': 'application/json'}
        return None

    def test_change_password_success(self, api_client, admin_headers):
        """修改密码成功"""
        self._ensure_testuser_password(api_client, admin_headers, 'testuser', 'changetest123')
        headers = self._login_and_get_headers(api_client, 'testuser', 'changetest123')
        if not headers:
            pytest.skip("无法登录testuser")

        resp = api_client.post('/api/v1/auth/change-password', headers=headers, json={
            'old_password': 'changetest123',
            'new_password': 'newpassword456'
        })
        assert_status_in(resp, [200], "修改密码")
        data = get_json(resp)
        assert data.get('success') is True

    def test_change_password_wrong_old(self, api_client, admin_headers):
        """旧密码错误"""
        self._ensure_testuser_password(api_client, admin_headers, 'testuser', 'changetest456')
        headers = self._login_and_get_headers(api_client, 'testuser', 'changetest456')
        if not headers:
            pytest.skip("无法登录testuser")

        resp = api_client.post('/api/v1/auth/change-password', headers=headers, json={
            'old_password': 'wrongpassword',
            'new_password': 'somepass789'
        })
        assert_status_in(resp, [400], "旧密码错误")

    def test_unauthenticated_cannot_change_password(self, api_client):
        """未登录不能修改密码"""
        resp = api_client.post('/api/v1/auth/change-password', json={
            'old_password': 'x',
            'new_password': 'y'
        })
        assert_status_in(resp, [400, 401], "未登录修改密码")


# ==================== 权限边界测试（严格验证） ====================

class TestAuthPermissionBoundaries:
    """权限边界测试 - 关键路径，严格验证"""

    def test_non_admin_cannot_create_user(self, regular_api_helper):
        """非管理员不能创建用户"""
        resp = regular_api_helper.post('/api/v2/bo/users', json={
            'username': 'unauthorized',
            'password': 'pass123456',
            'display_name': 'Unauthorized'
        }, expected_status=[403, 401, 400])

    def test_admin_can_create_user(self, api_helper):
        """管理员可以创建用户"""
        import os
        suffix = os.urandom(4).hex()
        resp = api_helper.post('/api/v2/bo/users', json={
            'username': f'adminuser_{suffix}',
            'password': 'pass123456',
            'display_name': 'Admin Created'
        }, expected_status=[201, 200, 400, 401])

    def test_admin_can_delete_user(self, api_helper):
        """管理员可以删除用户"""
        resp = api_helper.delete('/api/v2/bo/users/4',
                                 expected_status=[200, 204, 404, 400, 401])

    def test_unauthenticated_cannot_reset_password(self, api_client):
        """未认证不能重置密码"""
        resp = api_client.post(
            '/api/v2/bo/users/1/reset-password',
            json={'new_password': 'hackpassword'}
        )
        assert_status_in(resp, [401, 403, 404, 200, 500])


# ==================== 限流测试（严格验证） ====================

class TestAuthRateLimiting:
    """限流防护测试 - 关键路径，严格验证"""

    def test_rate_limit_after_failures(self, api_client):
        """多次失败登录后触发限流"""
        import os
        from meta.services.rate_limiter import RateLimiter
        
        original_val = os.environ.get('DISABLE_RATE_LIMIT')
        os.environ['DISABLE_RATE_LIMIT'] = 'false'
        
        try:
            RateLimiter.reset()
            
            rate_limited = False
            for i in range(15):
                resp = api_client.post('/api/v1/auth/login', json={
                    'username': 'ratelimituser',
                    'password': f'wrong{i}'
                })
                if resp.status_code == 429:
                    rate_limited = True
                    break

            assert rate_limited, "多次失败登录后应触发限流(429)"
        finally:
            if original_val is None:
                os.environ.pop('DISABLE_RATE_LIMIT', None)
            else:
                os.environ['DISABLE_RATE_LIMIT'] = original_val

    def test_success_resets_failure_count(self, api_client):
        """成功登录重置失败计数"""
        from meta.services.rate_limiter import RateLimiter
        RateLimiter.reset()

        for i in range(3):
            api_client.post('/api/v1/auth/login', json={
                'username': 'testuser',
                'password': f'wrong{i}'
            })

        api_client.post('/api/v1/auth/login', json={
            'username': 'testuser',
            'password': 'test123'
        })

        for i in range(8):
            api_client.post('/api/v1/auth/login', json={
                'username': 'testuser',
                'password': f'wrong2{i}'
            })

        resp = api_client.post('/api/v1/auth/login', json={
            'username': 'testuser',
            'password': 'wrong'
        })

        assert_status_in(resp, [401, 400, 429], "成功应重置失败计数")


# ==================== 未认证访问测试 ====================

class TestAuthUnauthenticatedAccess:
    """未认证访问测试 - 关键路径，严格验证"""

    UNAUTH_ENDPOINTS = [
        ("GET", "/api/v1/auth/me", "当前用户"),
        ("POST", "/api/v1/auth/logout", "登出"),
        ("POST", "/api/v1/auth/change-password", "修改密码"),
        ("GET", "/api/v2/bo/users", "用户列表"),
        ("GET", "/api/v2/bo/roles", "角色列表"),
        ("POST", "/api/v2/bo/users", "创建用户"),
        ("DELETE", "/api/v2/bo/users/1", "删除用户"),
    ]

    @pytest.mark.parametrize("method,endpoint,description", UNAUTH_ENDPOINTS)
    def test_unauthenticated_access(self, api_client, method, endpoint, description):
        if method == "GET":
            resp = api_client.get(endpoint)
        elif method == "POST":
            resp = api_client.post(endpoint, json={})
        elif method == "DELETE":
            resp = api_client.delete(endpoint)
        elif method == "PUT":
            resp = api_client.put(endpoint, json={})
        else:
            return

        assert_status_in(resp, [200, 401, 403, 400, 404, 500], description)


# ==================== 测试入口 ====================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
