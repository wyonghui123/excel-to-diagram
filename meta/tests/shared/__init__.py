# -*- coding: utf-8 -*-
"""
[MODULE] 测试共享模块
[DESCRIPTION] 提供所有测试文件共享的 fixtures, Mock 类, 基类, 断言函数, 常量和 App 客户端

使用方式：
1. 导入 fixtures:
   from meta.tests.shared.fixtures import *

2. 导入 mocks:
   from meta.tests.shared.mocks import *

3. 导入测试基类:
   from meta.tests.shared.base import AuthenticatedTestCase, IntegrationTestCase

4. 导入断言函数:
   from meta.tests.shared.assertions import assert_success, HTTPStatus

5. 导入错误处理:
   from meta.tests.shared.error_handlers import safe_request, APIRequest

6. 导入 App Fixtures (支持并行测试):
   from meta.tests.shared.app_fixtures import app_client, get_shared_app

7. 在 conftest.py 中自动加载:
   from meta.tests.shared.fixtures import *
   from meta.tests.shared.mocks import *

v3.18 P1: 删除了 shared/constants.py (T200 彻底清理)
  之前从 constants 导入的 TestUser/TestConfig/APIEndpoints 改为各文件本地定义
  (或者直接使用字符串字面量)
"""

# 使用相对导入确保在 pytest 环境中正常工作
try:
    from meta.tests.shared.fixtures import *
    from meta.tests.shared.mocks import *
    from meta.tests.shared.base import *
    from meta.tests.shared.app_fixtures import *
    from meta.tests.shared.fixtures_v2 import *
    from meta.tests.shared.base_crud import *
    from meta.tests.shared.parametrize_crud import *
    from meta.tests.shared.parametrize_auth import *
except ImportError:
    # 回退到相对导入
    try:
        from .fixtures import *
        from .mocks import *
        from .base import *
        from .app_fixtures import *
        from .fixtures_v2 import *
        from .base_crud import *
        from .parametrize_crud import *
        from .parametrize_auth import *
    except ImportError:
        pass

__all__ = [
    # Fixtures (原有)
    'app_client',
    'admin_headers',
    'regular_user_headers',
    'no_auth_headers',
    'random_suffix',
    'cleanup_tracker',
    'admin_token',
    'regular_user_token',
    'db_session',
    'db_isolated',
    'db_transaction',
    # Fixtures_v2 (增强版)
    'cleanup_list',
    'bulk_cleanup',
    'timestamp',
    'unique_name',
    'test_data_factory',
    'create_object',
    'create_test_object',
    'read_object',
    'update_object',
    'delete_object',
    'list_objects',
    # App Fixtures (新增 - 支持并行)
    'app_client_func',
    'api_client',
    'api_client_session',
    'get_shared_app',
    'create_app_with_config',
    # Mocks
    'MockActionContext',
    'MockActionResult',
    'MockResult',
    'MockMetaObject',
    'MockMetaField',
    'MockDataSource',
    # Base Classes
    'IntegrationTestCase',
    'AuthenticatedTestCase',
    'AuthenticatedAsyncTestCase',
    'BaseCrudTest',
    # CRUD 参数化
    'CRUDTestCase',
    'STANDARD_BO_TEST_DATA',
    'generate_unique_data',
    'get_required_fields',
    'get_update_data',
    'create_object_and_cleanup',
    'assert_crud_operations',
    # Auth 参数化
    'STANDARD_ROLES',
    'STANDARD_PERMISSIONS',
    'ROLE_DEFAULT_PERMISSIONS',
    'create_token',
    'create_headers',
    'create_role_token',
    'AuthTestCases',
]
