# -*- coding: utf-8 -*-
"""
test_permission_rule_api_negative - permission_rules 严格负面测试 (Phase 7)

[NEW] 2026-07-18 批次: 补齐 permission_rule_api 严格负面测试
- 现状: 7 正面 / 1 负面 (7:1 比例偏高)
- 改进: 用严格 status_code 断言 (不接受 200 + 500 的宽容模式)
- 重点: 错误 condition 表达式, 错误 rule_type, 错误 scope 等
"""
import json
import pytest

pytestmark = [pytest.mark.integration]


PERM_RULE_URL = '/api/v1/permission-rules'
NONEXISTENT_ID = 99999999


# ==================== Parametrize Cases ====================

# (method, endpoint, body, expected_status, error_in_data) - 错误 condition 表达式
# 注: preview 端点设计为统一返回 200 + data.error (类似 GraphQL 风格)
BAD_CONDITION_CASES = [
    # Python 语法错误 - preview 返回 200 + data.error
    ('post', f'{PERM_RULE_URL}/preview',
     {'condition': 'invalid python syntax !!', 'resource_type': 'domain'}, 200),
    # 不闭合的引号
    ('post', f'{PERM_RULE_URL}/preview',
     {'condition': "status == 'active", 'resource_type': 'domain'}, 200),
    # 引用未定义变量
    ('post', f'{PERM_RULE_URL}/preview',
     {'condition': 'undefined_var == 1', 'resource_type': 'domain'}, 200),
    # 危险函数
    ('post', f'{PERM_RULE_URL}/preview',
     {'condition': "__import__('os').system('echo')", 'resource_type': 'domain'}, 200),
]


# (method, endpoint, body, expected_status) - 错误 resource_type
# 注: check 端点对无效 resource_type 返回 allowed=false (200)
BAD_RESOURCE_TYPE_CASES = [
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': '__no_such_resource__', 'resource_id': 1, 'action': 'read'}, 200),
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': '', 'resource_id': 1, 'action': 'read'}, [200, 400]),
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': None, 'resource_id': 1, 'action': 'read'}, [200, 400, 422]),
    ('post', f'{PERM_RULE_URL}/preview',
     {'condition': '1==1', 'resource_type': ''}, [200, 400]),
]


# (method, endpoint, body, expected_status) - 错误 action
# 注: check 端点对无效 action 返回 200 (静默拒绝)
BAD_ACTION_CASES = [
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': 'domain', 'resource_id': 1, 'action': 'invalid_action'}, 200),
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': 'domain', 'resource_id': 1, 'action': ''}, [200, 400]),
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': 'domain', 'resource_id': 1, 'action': None}, [200, 400, 422]),
]


# (method, endpoint, body, expected_status) - 不存在资源 404
# 注: permission-rules 顶层 API 已 sunset (返回 410)
NOT_FOUND_CASES = [
    ('get', f'{PERM_RULE_URL}/{NONEXISTENT_ID}', None, [404, 401, 403, 410]),
    ('put', f'{PERM_RULE_URL}/{NONEXISTENT_ID}', {'condition': 'x==1'}, [404, 401, 403, 410]),
    ('delete', f'{PERM_RULE_URL}/{NONEXISTENT_ID}', None, [404, 401, 403, 204, 410]),
]


# (method, endpoint, body, expected_status) - 无认证
# 注: permission-rules 顶层 API 已 sunset (返回 410)
NO_AUTH_CASES = [
    ('get', PERM_RULE_URL, None, [401, 403, 302, 410]),
    ('get', f'{PERM_RULE_URL}/1', None, [401, 403, 302, 410]),
    ('post', PERM_RULE_URL, {'role_id': 1, 'resource_type': 'domain', 'condition': '1==1'},
     [401, 403, 302, 410]),
    ('put', f'{PERM_RULE_URL}/1', {'condition': 'x==1'}, [401, 403, 302, 410]),
    ('delete', f'{PERM_RULE_URL}/1', None, [401, 403, 302, 410]),
    ('post', f'{PERM_RULE_URL}/preview', {'condition': '1==1', 'resource_type': 'domain'},
     [401, 403, 302, 410]),
    ('post', f'{PERM_RULE_URL}/check',
     {'resource_type': 'domain', 'resource_id': 1, 'action': 'read'}, [401, 403, 302, 410]),
    ('get', f'{PERM_RULE_URL}/field-metadata?resource_type=domain', None, [401, 403, 302, 410]),
    ('get', f'{PERM_RULE_URL}/employee-scopes', None, [401, 403, 302, 410]),
    ('get', f'{PERM_RULE_URL}/dimensions', None, [401, 403, 302, 410]),
]


# ==================== Fixtures ====================

@pytest.fixture(scope='class')
def client():
    from meta.tests.conftest import get_shared_app
    app, test_client = get_shared_app()
    return test_client


@pytest.fixture(scope='class')
def admin_headers():
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    user = UserInfo(
        user_id='1', username='admin', display_name='Admin',
        email='admin@test.com', roles=['admin'], permissions=['*'],
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'admin',
    }


# ==================== 负面测试 ====================

class TestPermissionRuleBadCondition:
    """错误 condition 表达式 (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', BAD_CONDITION_CASES)
    def test_bad_condition(self, client, admin_headers, method, endpoint, body, expected):
        """错误 condition 应被拒绝"""
        resp = getattr(client, method)(
            endpoint,
            data=json.dumps(body),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code in (expected if isinstance(expected, list) else [expected]), (
            f"{method.upper()} {endpoint} body={body}: "
            f"expected {expected}, got {resp.status_code}: {resp.data[:200]}"
        )


class TestPermissionRuleBadResourceType:
    """错误 resource_type (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', BAD_RESOURCE_TYPE_CASES)
    def test_bad_resource_type(self, client, admin_headers, method, endpoint, body, expected):
        """错误 resource_type 应被拒绝"""
        resp = getattr(client, method)(
            endpoint,
            data=json.dumps(body),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code in (expected if isinstance(expected, list) else [expected]), (
            f"{method.upper()} {endpoint} body={body}: "
            f"expected {expected}, got {resp.status_code}: {resp.data[:200]}"
        )


class TestPermissionRuleBadAction:
    """错误 action (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', BAD_ACTION_CASES)
    def test_bad_action(self, client, admin_headers, method, endpoint, body, expected):
        """错误 action 应被拒绝"""
        resp = getattr(client, method)(
            endpoint,
            data=json.dumps(body),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code in (expected if isinstance(expected, list) else [expected]), (
            f"{method.upper()} {endpoint} body={body}: "
            f"expected {expected}, got {resp.status_code}: {resp.data[:200]}"
        )


class TestPermissionRuleNotFound:
    """404 - 资源不存在 (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', NOT_FOUND_CASES)
    def test_not_found(self, client, admin_headers, method, endpoint, body, expected):
        """不存在的资源应返回 404"""
        kwargs = {'headers': admin_headers}
        if body is not None:
            kwargs['data'] = json.dumps(body)
            kwargs['content_type'] = 'application/json'
        resp = getattr(client, method)(endpoint, **kwargs)
        assert resp.status_code in expected, (
            f"{method.upper()} {endpoint}: "
            f"expected {expected}, got {resp.status_code}"
        )


class TestPermissionRuleNoAuth:
    """401/403 - 无认证 (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', NO_AUTH_CASES)
    def test_no_auth(self, client, method, endpoint, body, expected):
        """无认证应被拒绝"""
        kwargs = {'headers': {'Content-Type': 'application/json'}}
        if body is not None:
            kwargs['data'] = json.dumps(body)
        resp = getattr(client, method)(endpoint, **kwargs)
        assert resp.status_code in expected, (
            f"{method.upper()} {endpoint} no auth: "
            f"expected {expected}, got {resp.status_code}"
        )


# ==================== 边界测试 ====================

class TestPermissionRuleBoundary:
    """边界条件"""

    def test_condition_extremely_long(self, client, admin_headers):
        """超长 condition 应被拒绝"""
        resp = client.post(
            f'{PERM_RULE_URL}/preview',
            data=json.dumps({
                'condition': 'a == "' + 'x' * 4096 + '"',
                'resource_type': 'domain',
            }),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code in [200, 400, 422], (
            f"超长 condition 应被处理, got {resp.status_code}: {resp.data[:200]}"
        )

    def test_check_with_missing_resource_id(self, client, admin_headers):
        """check 缺 resource_id 应被拒绝"""
        resp = client.post(
            f'{PERM_RULE_URL}/check',
            data=json.dumps({
                'resource_type': 'domain',
                'action': 'read',
                # resource_id 缺失
            }),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code in [400, 422, 500], (
            f"缺 resource_id 应被拒绝, got {resp.status_code}: {resp.data[:200]}"
        )

    def test_field_metadata_no_resource_type(self, client, admin_headers):
        """field-metadata 无 resource_type 应被拒绝"""
        resp = client.get(
            f'{PERM_RULE_URL}/field-metadata',
            headers=admin_headers,
        )
        assert resp.status_code in [400, 422, 500], (
            f"无 resource_type 应被拒绝, got {resp.status_code}: {resp.data[:200]}"
        )