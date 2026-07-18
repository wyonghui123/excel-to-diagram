"""
test_helpers - 共享测试基类与工具 (Phase 7 重构)

目的: 整合测试中重复的 setup/teardown 模式
- BaseAPITestCase: 通用 API 测试基类 (含 client, admin_headers, user_headers, assert_* helpers)
- BaseCRUDTestCase: CRUD 测试基类 (自动 create/read/update/delete 流程)
- BaseRegressionTestCase: 回归测试基类 (带 fixed_version 标记)

设计原则:
1. 100% 向后兼容 - 不修改现有测试, 新代码可选使用
2. 不破坏现有 fixture - conftest.py 的 shared_app/client 仍然有效
3. 减少 150+ 重复 fixture 定义
4. 提供可复用的断言助手

使用示例:
    from meta.tests.test_helpers import BaseAPITestCase

    class TestMyAPI(BaseAPITestCase):
        object_type = 'product'

        def test_create(self):
            response = self.client.post(self.list_url, json=self._make_payload())
            self.assert_api_success(response)
"""


# 导入所有基类 - 保持简洁导入路径
from .base_api import BaseAPITestCase
from .base_crud import BaseCRUDTestCase
from .base_regression import BaseRegressionTestCase
from .assert_helpers import (
    assert_api_success,
    assert_api_error,
    assert_data_field,
    assert_status_code,
)
from .cookie_helpers import (
    admin_cookie,
    user_cookie,
    make_test_user,
)


__all__ = [
    'BaseAPITestCase',
    'BaseCRUDTestCase',
    'BaseRegressionTestCase',
    'assert_api_success',
    'assert_api_error',
    'assert_data_field',
    'assert_status_code',
    'admin_cookie',
    'user_cookie',
    'make_test_user',
]


__version__ = '1.0.0'
__phase__ = 'Phase 7'