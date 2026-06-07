# -*- coding: utf-8 -*-
"""
[MODULE] 共享测试基类
[DESCRIPTION] 提供所有测试文件共享的测试基类

使用方式：
1. 继承 pytest 风格的基类（推荐）：
   from meta.tests.shared.base import IntegrationTestCase

   class TestMyFeature(IntegrationTestCase):
       def test_something(self):
           ...

2. 继承 unittest 风格的基类：
   from meta.tests.shared.base import AuthenticatedTestCase

   class TestMyFeature(AuthenticatedTestCase):
       def test_something(self):
           ...

优化说明：
- AuthenticatedTestCase 使用 session-scoped 缓存
- 避免每个测试类都重新创建 app/client/token
- 减少约 20+ 次重复初始化开销
"""

import unittest
import pytest
import sqlite3
import os

from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo


_SESSION_CACHE = {
    'app': None,
    'client': None,
    'token': None,
    'headers': None,
    'initialized': False,
}


def _get_cached_app_client():
    """获取缓存的 app 和 client（session级别只创建一次）"""
    if _SESSION_CACHE['initialized']:
        return _SESSION_CACHE['app'], _SESSION_CACHE['client']
    
    from meta.tests.conftest import get_shared_app
    _SESSION_CACHE['app'], _SESSION_CACHE['client'] = get_shared_app()
    _SESSION_CACHE['initialized'] = True
    
    return _SESSION_CACHE['app'], _SESSION_CACHE['client']


def _get_cached_token_headers():
    """获取缓存的 token 和 headers（session级别只创建一次）"""
    if _SESSION_CACHE['token'] is not None:
        return _SESSION_CACHE['token'], _SESSION_CACHE['headers']
    
    test_user = UserInfo(
        user_id='1',
        username='test_user',
        display_name='Test User',
        email='test@test.com',
        roles=['admin'],
        permissions=['*']
    )
    _SESSION_CACHE['token'], _ = TokenService.create_token(test_user)
    _SESSION_CACHE['headers'] = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {_SESSION_CACHE["token"]}',
        'X-User-Id': '1',
        'X-User-Name': 'test_user',
        'X-IP-Address': '127.0.0.1'
    }
    
    return _SESSION_CACHE['token'], _SESSION_CACHE['headers']


def reset_session_cache():
    """重置 session 缓存（用于测试隔离）"""
    _SESSION_CACHE['initialized'] = False
    _SESSION_CACHE['app'] = None
    _SESSION_CACHE['client'] = None
    _SESSION_CACHE['token'] = None
    _SESSION_CACHE['headers'] = None


# ==================== Pytest 风格基类 ====================

class IntegrationTestCase:
    """
    [BASE CLASS] Pytest 风格集成测试基类
    [DESCRIPTION] 提供通用的集成测试基础设施

    使用方式：
        class TestMyFeature(IntegrationTestCase):
            @pytest.fixture(autouse=True)
            def setup_method(self):
                # 每个测试方法前执行

            def test_something(self):
                ...
    """

    @pytest.fixture(scope="class", autouse=True)
    def setup_test_environment(self):
        """设置测试环境（每个测试类执行一次）"""
        self._init_test_data()
        yield
        self._cleanup_test_data()

    def _init_test_data(self):
        """初始化测试数据"""
        pass

    def _cleanup_test_data(self):
        """清理测试数据"""
        pass

    def _get_admin_headers(self):
        """获取管理员认证头"""
        from meta.tests.conftest import get_shared_app

        if not hasattr(self, '_app_client'):
            self._app_client = get_shared_app()

        _, client = self._app_client

        test_user = UserInfo(
            user_id='1',
            username='test_user',
            display_name='Test User',
            email='test@test.com',
            roles=['admin'],
            permissions=['*']
        )
        token, _ = TokenService.create_token(test_user)

        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'X-User-Id': '1',
            'X-User-Name': 'test_user',
            'X-IP-Address': '127.0.0.1'
        }


# ==================== Unittest 风格基类 ====================

class AuthenticatedTestCase(unittest.TestCase):
    """
    [BASE CLASS] 带认证的 unittest 风格测试基类
    [DESCRIPTION] 提供 JWT Token 认证的测试基础设施

    使用方式：
        class TestMyFeature(AuthenticatedTestCase):
            def test_something(self):
                response = self.client.get('/api/v2/bo/user', headers=self.headers)
                assert response.status_code in [200, 401, 404, 500]

    属性：
        - app: Flask 应用实例
        - client: Flask 测试客户端
        - token: JWT Token
        - headers: 认证请求头
    """

    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 使用缓存的 app/client/token
        
        优化: 使用 session-scoped 缓存，避免每个测试类都重新创建
        """
        cls.app, cls.client = _get_cached_app_client()
        cls.token, cls.headers = _get_cached_token_headers()

        if not _SESSION_CACHE.get('test_data_initialized'):
            cls._ensure_test_data()
            _SESSION_CACHE['test_data_initialized'] = True

    @classmethod
    def _ensure_test_data(cls):
        """
        [METHOD] 确保测试数据存在
        [DESCRIPTION] 初始化测试所需的数据库数据
        """
        try:
            from meta.tests.test_utils import get_test_db_path
        except ImportError:
            return

        db_path = get_test_db_path()
        if not db_path or not os.path.exists(db_path):
            return

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        try:
            cls._ensure_products(cur)
            cls._ensure_versions(cur)
            cls._ensure_domains(cur)
            cls._ensure_sub_domains(cur)
            cls._ensure_service_modules(cur)
            cls._ensure_business_objects(cur)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def _ensure_products(cls, cur):
        """确保产品数据存在"""
        cur.execute('SELECT COUNT(*) FROM products')
        if cur.fetchone()[0] == 0:
            cur.execute(
                'INSERT INTO products (name, code, is_active) VALUES (?, ?, ?)',
                ('Test Product', 'TEST_PROD', 1)
            )

    @classmethod
    def _ensure_versions(cls, cur):
        """确保版本数据存在"""
        cur.execute('SELECT COUNT(*) FROM versions WHERE id = 1')
        if cur.fetchone()[0] == 0:
            cur.execute('SELECT COUNT(*) FROM versions')
            if cur.fetchone()[0] == 0:
                cur.execute(
                    'INSERT INTO versions (name, code, product_id) VALUES (?, ?, ?)',
                    ('v1.0', 'V1', 1)
                )
            else:
                cur.execute(
                    'INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)',
                    (1, 'v1.0', 'V1', 1)
                )

        cur.execute('SELECT COUNT(*) FROM versions WHERE id = 2')
        if cur.fetchone()[0] == 0:
            cur.execute(
                'INSERT INTO versions (id, name, code, product_id) VALUES (?, ?, ?, ?)',
                (2, 'v2.0', 'V2', 1)
            )

    @classmethod
    def _ensure_domains(cls, cur):
        """确保领域数据存在"""
        cur.execute('SELECT COUNT(*) FROM domains')
        if cur.fetchone()[0] == 0:
            cur.execute(
                'INSERT INTO domains (name, code, version_id) VALUES (?, ?, ?)',
                ('Test Domain', 'TEST_DOM', 1)
            )

    @classmethod
    def _ensure_sub_domains(cls, cur):
        """确保子领域数据存在"""
        cur.execute('SELECT COUNT(*) FROM sub_domains')
        if cur.fetchone()[0] == 0:
            cur.execute(
                'INSERT INTO sub_domains (name, code, version_id, domain_id) VALUES (?, ?, ?, ?)',
                ('Test SubDomain', 'TEST_SUB', 1, 1)
            )

    @classmethod
    def _ensure_service_modules(cls, cur):
        """确保服务模块数据存在"""
        cur.execute('SELECT COUNT(*) FROM service_modules')
        if cur.fetchone()[0] == 0:
            cur.execute(
                'INSERT INTO service_modules (name, code, version_id, sub_domain_id) VALUES (?, ?, ?, ?)',
                ('Test ServiceModule', 'TEST_SM', 1, 1)
            )

    @classmethod
    def _ensure_business_objects(cls, cur):
        """确保业务对象数据存在"""
        cur.execute('SELECT COUNT(*) FROM business_objects')
        if cur.fetchone()[0] == 0:
            cur.execute(
                'INSERT INTO business_objects (name, code, version_id, service_module_id) VALUES (?, ?, ?, ?)',
                ('Test BO 1', 'BO01', 1, 1)
            )
            cur.execute(
                'INSERT INTO business_objects (name, code, version_id, service_module_id) VALUES (?, ?, ?, ?)',
                ('Test BO 2', 'BO02', 1, 1)
            )


class AuthenticatedAsyncTestCase(AuthenticatedTestCase):
    """
    [BASE CLASS] 带认证的异步测试基类
    [DESCRIPTION] 用于测试异步功能的基类
    """

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        super().setUpClass()
        cls._event_loop = None

    def get_event_loop(self):
        """获取事件循环"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop


# ==================== 导出 ====================

__all__ = [
    'IntegrationTestCase',
    'AuthenticatedTestCase',
    'AuthenticatedAsyncTestCase',
]
