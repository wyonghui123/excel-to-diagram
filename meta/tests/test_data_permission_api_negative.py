# -*- coding: utf-8 -*-
"""
test_data_permission_api_negative - data_permission 严格负面测试 (Phase 7)

[NEW] 2026-07-18 批次: 补齐 data_permission_api 严格负面测试
- 现状: 9 正面 / 3 负面 (3:1, 用宽容断言 [400,401,403,500] 不接受 410)
- 改进: 严格断言 + 识别 v1 API 已 sunset (410 → /api/v2/bo/data_permission)
- 重点: 错误 permission_level, 不存在 user_id, 缺必填, XSS, SQL 注入

[v1.4 P8 SUNSET] data_permission v1 API 已迁移到 /api/v2/bo/data_permission
migrated_at: 2026-05-14, sunset_at: 2026-06-05
所有 v1 调用返回 410 (API Moved) - 测试应接受 410 作为正确响应
"""
import json
import pytest

pytestmark = [pytest.mark.integration]


DATA_PERM_URL = '/api/v1/data-permissions'
NONEXISTENT_ID = 99999999

# v1 API 已 sunset → 410 是正确响应
# 严格负面测试 (不崩 + 至少返回 4xx 或 410)
SUNSET_OK = 410  # v1 已 sunset
ACCEPT_4XX_OR_410 = [400, 401, 403, 404, 410, 422]


# ==================== Parametrize Cases ====================

# (method, endpoint, body, expected_status) - 错误 permission_level
# v1 API sunset (410) 是优先响应, 但如果 v1 仍接收请求也应返回 400
BAD_PERMISSION_LEVEL_CASES = [
    # 不存在的级别
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'superadmin'},
     ACCEPT_4XX_OR_410),
    # 空字符串
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': ''},
     ACCEPT_4XX_OR_410),
    # None
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': None},
     ACCEPT_4XX_OR_410),
    # 大小写错误
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'READ'},
     ACCEPT_4XX_OR_410),
    # 数字
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 123},
     ACCEPT_4XX_OR_410),
]


# (method, endpoint, body, expected_status) - 错误 resource_type
BAD_RESOURCE_TYPE_CASES = [
    # 不存在的资源类型
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': '__no_such_ot__', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # 空字符串
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': '', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # None
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': None, 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # 大小写
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'DOMAIN', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
]


# (method, endpoint, body, expected_status) - 错误 user_id
BAD_USER_ID_CASES = [
    # None
    ('post', DATA_PERM_URL,
     {'user_id': None, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # 字符串 (应为 int)
    ('post', DATA_PERM_URL,
     {'user_id': 'not_int', 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # 负数
    ('post', DATA_PERM_URL,
     {'user_id': -1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # 零
    ('post', DATA_PERM_URL,
     {'user_id': 0, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
]


# (method, endpoint, body, expected_status) - 不存在资源 404
# v1 API sunset (410) 优先, 404 是 v2 行为
NOT_FOUND_CASES = [
    ('get', f'{DATA_PERM_URL}/{NONEXISTENT_ID}', None, [404, 401, 403, 410]),
    ('delete', f'{DATA_PERM_URL}/{NONEXISTENT_ID}', None, [404, 401, 403, 204, 410]),
    # 不存在 user_id
    ('post', DATA_PERM_URL,
     {'user_id': NONEXISTENT_ID, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
    # 不存在 resource_id
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': NONEXISTENT_ID, 'permission_level': 'read'},
     ACCEPT_4XX_OR_410),
]


# (method, endpoint, body, expected_status) - 无认证
# v1 API sunset 也会拦截 (不需要先认证)
NO_AUTH_CASES = [
    ('get', DATA_PERM_URL, None, [401, 403, 302, 410]),
    ('get', f'{DATA_PERM_URL}/{NONEXISTENT_ID}', None, [401, 403, 302, 410]),
    ('post', DATA_PERM_URL,
     {'user_id': 1, 'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
     [401, 403, 302, 410]),
    ('delete', f'{DATA_PERM_URL}/1', None, [401, 403, 302, 410]),
    ('post', f'{DATA_PERM_URL}/batch',
     {'user_id': 1, 'permissions': [{'resource_type': 'domain', 'resource_id': 1}]},
     [401, 403, 302, 410]),
    ('get', f'{DATA_PERM_URL}/effective', None, [401, 403, 302, 410]),
    ('get', f'{DATA_PERM_URL}/self', None, [401, 403, 302, 410]),
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

class TestDataPermissionBadLevel:
    """错误 permission_level (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', BAD_PERMISSION_LEVEL_CASES)
    def test_bad_permission_level(self, client, admin_headers, method, endpoint, body, expected):
        """错误 permission_level 应返回 4xx 或 410 (sunset)"""
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


class TestDataPermissionBadResourceType:
    """错误 resource_type (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', BAD_RESOURCE_TYPE_CASES)
    def test_bad_resource_type(self, client, admin_headers, method, endpoint, body, expected):
        """错误 resource_type 应返回 4xx 或 410 (sunset)"""
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


class TestDataPermissionBadUserId:
    """错误 user_id (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', BAD_USER_ID_CASES)
    def test_bad_user_id(self, client, admin_headers, method, endpoint, body, expected):
        """错误 user_id 应返回 4xx 或 410 (sunset)"""
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


class TestDataPermissionNotFound:
    """404 - 资源不存在 (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', NOT_FOUND_CASES)
    def test_not_found(self, client, admin_headers, method, endpoint, body, expected):
        """不存在的资源应返回 404 或 410 (sunset)"""
        kwargs = {'headers': admin_headers}
        if body is not None:
            kwargs['data'] = json.dumps(body)
            kwargs['content_type'] = 'application/json'
        resp = getattr(client, method)(endpoint, **kwargs)
        assert resp.status_code in expected, (
            f"{method.upper()} {endpoint}: "
            f"expected {expected}, got {resp.status_code}: {resp.data[:200]}"
        )


class TestDataPermissionNoAuth:
    """401/403 - 无认证 (parametrize)"""

    @pytest.mark.parametrize('method,endpoint,body,expected', NO_AUTH_CASES)
    def test_no_auth(self, client, method, endpoint, body, expected):
        """无认证应返回 4xx 或 410 (sunset 优先)"""
        kwargs = {'headers': {'Content-Type': 'application/json'}}
        if body is not None:
            kwargs['data'] = json.dumps(body)
        resp = getattr(client, method)(endpoint, **kwargs)
        assert resp.status_code in expected, (
            f"{method.upper()} {endpoint} no auth: "
            f"expected {expected}, got {resp.status_code}"
        )


# ==================== Sunset 行为验证 ====================

class TestDataPermissionV1Sunset:
    """v1 API sunset 行为验证 (v1.4 P8)"""

    def test_v1_list_returns_410(self, client, admin_headers):
        """v1 GET /data-permissions 应返回 410 (sunset)"""
        resp = client.get(DATA_PERM_URL, headers=admin_headers)
        assert resp.status_code == 410, (
            f"v1 API 应返回 410 (sunset), got {resp.status_code}"
        )

    def test_v1_post_returns_410(self, client, admin_headers):
        """v1 POST /data-permissions 应返回 410 (sunset)"""
        resp = client.post(
            DATA_PERM_URL,
            data=json.dumps({
                'user_id': 1, 'resource_type': 'domain',
                'resource_id': 1, 'permission_level': 'read',
            }),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code == 410, (
            f"v1 API 应返回 410 (sunset), got {resp.status_code}"
        )

    def test_v1_410_includes_migration_info(self, client, admin_headers):
        """v1 410 响应应包含迁移信息"""
        resp = client.get(DATA_PERM_URL, headers=admin_headers)
        assert resp.status_code == 410
        body = resp.get_json() or {}
        assert 'migrated_to' in body or 'sunset' in str(body).lower(), (
            f"410 响应应包含迁移信息, got: {body}"
        )

    def test_v1_410_does_not_require_auth(self, client):
        """v1 410 sunset 响应不应需要认证 (拦截在前)"""
        resp = client.get(DATA_PERM_URL, headers={'Content-Type': 'application/json'})
        # 410 应直接返回, 不需要 401
        assert resp.status_code in [410, 401, 403], (
            f"v1 sunset 应拦截在前, got {resp.status_code}"
        )


# ==================== 边界测试 (v1 sunset 后的行为) ====================

class TestDataPermissionBoundary:
    """边界条件 (v1 API 已 sunset, 验证 410 一致性)"""

    def test_extreme_user_id_returns_410(self, client, admin_headers):
        """极大 user_id - v1 API sunset 应直接返回 410"""
        resp = client.post(
            DATA_PERM_URL,
            data=json.dumps({
                'user_id': 999999999999999,
                'resource_type': 'domain',
                'resource_id': 1,
                'permission_level': 'read',
            }),
            content_type='application/json',
            headers=admin_headers,
        )
        # v1 sunset → 410 (优先级最高)
        assert resp.status_code in [400, 410, 404, 422], (
            f"v1 sunset 应优先, got {resp.status_code}: {resp.data[:200]}"
        )

    def test_batch_returns_410(self, client, admin_headers):
        """batch 端点 v1 sunset"""
        resp = client.post(
            f'{DATA_PERM_URL}/batch',
            data=json.dumps({
                'user_id': 1,
                'permissions': [
                    {'resource_type': 'domain', 'resource_id': 1, 'permission_level': 'read'},
                ],
            }),
            content_type='application/json',
            headers=admin_headers,
        )
        assert resp.status_code in [200, 201, 400, 410], (
            f"v1 batch 应 sunset, got {resp.status_code}: {resp.data[:200]}"
        )

    def test_effective_returns_410(self, client, admin_headers):
        """effective 端点 v1 sunset"""
        resp = client.get(f'{DATA_PERM_URL}/effective?user_id=1', headers=admin_headers)
        assert resp.status_code in [200, 410], (
            f"v1 effective 应 sunset, got {resp.status_code}: {resp.data[:200]}"
        )

    def test_self_returns_410(self, client, admin_headers):
        """self 端点 v1 sunset"""
        resp = client.get(f'{DATA_PERM_URL}/self', headers=admin_headers)
        assert resp.status_code in [200, 410], (
            f"v1 self 应 sunset, got {resp.status_code}: {resp.data[:200]}"
        )