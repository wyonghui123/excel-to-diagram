"""
BaseAPITestCase - API 测试基类 (Phase 7 重构)

提供:
- self.client: Flask test client (来自 conftest 的 shared_client)
- self.admin_headers: 管理员认证头
- self.user_headers: 普通用户认证头
- self._make_payload(): 生成测试数据 (需子类 override)
- self.assert_api_success(response): 断言 2xx
- self.assert_api_error(response, code=None): 断言 4xx/5xx
- self.list_url: /api/v2/{object_type}
- self.detail_url(id): /api/v2/{object_type}/{id}

注意: 不强制使用, 现有测试不受影响
"""
import pytest


class BaseAPITestCase:
    """
    API 测试基类

    子类必须设置:
        object_type = 'product'  # 业务对象类型

    子类可覆盖:
        api_prefix = '/api/v2'  # API 前缀
        _base_payload()  # 生成基础 payload
    """

    object_type: str = None
    api_prefix: str = '/api/v2'

    @pytest.fixture(autouse=True)
    def _setup_base_api(self, shared_client, admin_headers):
        """每个测试自动 setup (替代 150+ fixture 定义)"""
        self.client = shared_client
        self._admin_headers = admin_headers
        self._user_headers = self._make_user_headers()

    @property
    def admin_headers(self):
        return self._admin_headers

    @property
    def user_headers(self):
        return self._user_headers

    @property
    def list_url(self):
        """GET/POST 列表 URL"""
        return f"{self.api_prefix}/bo/{self.object_type}"

    def detail_url(self, obj_id, suffix=''):
        """GET/PUT/DELETE 详情 URL"""
        base = f"{self.api_prefix}/bo/{self.object_type}/{obj_id}"
        return f"{base}{suffix}" if suffix else base

    def _make_user_headers(self):
        """生成普通用户认证头 (子类可覆盖)"""
        from meta.services.token_service import TokenService
        from meta.services.auth_provider import UserInfo

        user = UserInfo(
            user_id='2',
            username='test_user',
            display_name='Test User',
            email='test@test.com',
            roles=['user'],
            permissions=['read'],
        )
        token, _ = TokenService.create_token(user)
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'X-User-Id': '2',
            'X-User-Name': 'test_user',
        }

    def _make_payload(self, **overrides):
        """生成基础 payload (子类应 override 添加必填字段)"""
        payload = {}
        payload.update(overrides)
        return payload

    # ==================== 断言助手 ====================

    def assert_api_success(self, response, expected_status=None):
        """断言 API 成功 (2xx)"""
        if expected_status is None:
            assert 200 <= response.status_code < 300, (
                f"Expected 2xx, got {response.status_code}: {response.data[:200]}"
            )
        else:
            assert response.status_code == expected_status, (
                f"Expected {expected_status}, got {response.status_code}: {response.data[:200]}"
            )
        return response

    def assert_api_error(self, response, expected_status=None, expected_code=None):
        """断言 API 错误 (4xx/5xx)"""
        if expected_status is not None:
            assert response.status_code == expected_status, (
                f"Expected {expected_status}, got {response.status_code}: {response.data[:200]}"
            )
        else:
            assert response.status_code >= 400, (
                f"Expected 4xx/5xx, got {response.status_code}: {response.data[:200]}"
            )
        if expected_code is not None:
            data = response.get_json() or {}
            actual_code = data.get('code') or data.get('error_code')
            assert actual_code == expected_code, (
                f"Expected error code {expected_code}, got {actual_code}"
            )
        return response

    def assert_data_field(self, response, field, expected):
        """断言返回 data 中指定字段"""
        data = response.get_json() or {}
        actual = data.get('data', {}).get(field) if 'data' in data else data.get(field)
        assert actual == expected, (
            f"Field '{field}': expected {expected!r}, got {actual!r}"
        )
        return actual