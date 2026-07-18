# -*- coding: utf-8 -*-
"""
test_base_api_demo - 演示新 BaseAPITestCase 用法 (Phase 7)

目的:
- 验证 meta.tests.test_helpers.BaseAPITestCase 可用
- 作为新测试的模板
- 推广到未来的测试中

本测试:
- 用 BaseAPITestCase 简化 30+ 行 fixture
- 用 assert_api_success/assert_api_error 替代散落的 assert
- 演示 _make_payload / list_url / detail_url 助手
"""
import pytest

from meta.tests.test_helpers import (
    BaseAPITestCase,
    BaseCRUDTestCase,
    BaseRegressionTestCase,
    assert_api_success,
    assert_api_error,
    assert_data_field,
    admin_cookie,
    user_cookie,
    make_test_user,
)


class TestBaseAPIHelpersWork(BaseAPITestCase):
    """测试 BaseAPITestCase 本身可用"""

    object_type = 'product'

    def test_list_url_format(self):
        """list_url 应为 /api/v2/bo/{object_type}"""
        assert self.list_url == '/api/v2/bo/product'

    def test_detail_url_format(self):
        """detail_url 应为 /api/v2/bo/{object_type}/{id}"""
        assert self.detail_url(123) == '/api/v2/bo/product/123'

    def test_admin_headers_present(self):
        """admin_headers 应包含必要字段"""
        h = self.admin_headers
        assert 'Authorization' in h
        assert h['Authorization'].startswith('Bearer ')
        assert h['X-User-Name'] == 'admin'

    def test_user_headers_present(self):
        """user_headers 应为普通用户"""
        h = self.user_headers
        assert 'Authorization' in h
        assert h['X-User-Name'] == 'test_user'

    def test_make_payload_with_overrides(self):
        """_make_payload 应支持 overrides"""
        payload = self._make_payload(name='test', code='p1')
        assert payload == {'name': 'test', 'code': 'p1'}


class TestHelperFunctionsWork:
    """测试独立 helper 函数"""

    def test_admin_cookie_works(self):
        """admin_cookie 应返回完整 headers"""
        h = admin_cookie()
        assert 'Authorization' in h
        assert h['X-User-Name'] == 'admin'
        assert h['X-User-Id'] == '1'

    def test_user_cookie_works(self):
        """user_cookie 应返回普通用户 headers"""
        h = user_cookie(user_id='5', username='alice')
        assert h['X-User-Id'] == '5'
        assert h['X-User-Name'] == 'alice'

    def test_make_test_user_defaults(self):
        """make_test_user 默认 user 角色"""
        user = make_test_user()
        assert user.user_id == '1'
        assert user.username == 'test_user'
        assert 'user' in user.roles

    def test_make_test_user_admin(self):
        """make_test_user 配 admin 角色"""
        user = make_test_user(roles=['admin'], permissions=['*'])
        assert 'admin' in user.roles
        assert '*' in user.permissions


class TestCRUDBaseClassWorks(BaseCRUDTestCase):
    """测试 BaseCRUDTestCase 自动生成的测试方法"""

    object_type = 'product'

    # 跳过不需要的方法以减少测试开销
    skip_list = True  # 列表已测
    skip_update = True  # product.code 是 immutable, 不能 update

    def make_payload(self):
        """唯一性 payload - 用 uuid 避免冲突"""
        import uuid
        suffix = uuid.uuid4().hex[:8].upper()
        return {
            'name': f'crud_test_{suffix}',
            'code': f'C{suffix}',  # 需匹配 ^[A-Z][A-Z0-9_]*$
        }

    def mutate_payload(self, payload):
        """修改用于 update"""
        payload['name'] = f"{payload['name']}_updated"
        return payload

    # 继承自动获得 7 个测试方法
    # - test_create_success
    # - test_read_success
    # - test_update_success
    # - test_delete_success
    # - test_read_404_not_found
    # - test_create_401_no_auth
    # - test_list_success (skipped)


class TestRegressionBaseClassWorks(BaseRegressionTestCase):
    """测试 BaseRegressionTestCase 标记功能"""

    bug_id = 'TEST_DEMO'
    bug_title = 'BaseRegressionTestCase 演示'
    fixed_in_version = '3.18.0'

    def test_demo_regression_works(self):
        """演示 fix verification"""
        self.verify_fix(lambda: True, '演示通过')


class TestAssertHelpersWork:
    """测试 assert_helpers 独立函数"""

    def test_assert_api_success_runs(self):
        """assert_api_success 不应抛错 (无 response 无法测试, 仅 import check)"""
        # 导入即可
        from meta.tests.test_helpers import assert_api_success
        assert callable(assert_api_success)

    def test_assert_api_error_runs(self):
        from meta.tests.test_helpers import assert_api_error
        assert callable(assert_api_error)

    def test_assert_data_field_runs(self):
        from meta.tests.test_helpers import assert_data_field
        assert callable(assert_data_field)