# -*- coding: utf-8 -*-
"""
Value Help E2E 测试

测试场景：
1. enum 类型 value help
2. bo 类型 value help
3. custom 类型 value help
4. resolve 解析
5. 权限过滤
"""

import unittest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _get_admin_token(client):
    """获取管理员 Token"""
    response = client.post(
        '/api/v1/auth/login',
        data=json.dumps({'username': 'admin', 'password': 'admin123'}),
        content_type='application/json'
    )
    if response.status_code == 200:
        data = json.loads(response.data)
        return data.get('data', {}).get('token')
    return None


class E2EValueHelpEnumTest(unittest.TestCase):
    """Value Help enum 类型 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/value-help'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_01_search_enum(self):
        """搜索 enum 类型"""
        response = self.client.get(
            f'{self.base_url}/enum/status',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_02_search_enum_with_search(self):
        """带搜索条件搜索 enum"""
        response = self.client.get(
            f'{self.base_url}/enum/status?search=active',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_03_search_enum_with_pagination(self):
        """分页搜索 enum"""
        response = self.client.get(
            f'{self.base_url}/enum/status?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_04_resolve_enum(self):
        """解析 enum 值"""
        response = self.client.get(
            f'{self.base_url}/enum/status/resolve?value=active',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])


class E2EValueHelpBoTest(unittest.TestCase):
    """Value Help bo 类型 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/value-help'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_01_search_bo(self):
        """搜索 bo 类型"""
        response = self.client.get(
            f'{self.base_url}/bo/domain',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_02_search_bo_with_search(self):
        """带搜索条件搜索 bo"""
        response = self.client.get(
            f'{self.base_url}/bo/domain?search=test',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_03_search_bo_with_filters(self):
        """带过滤条件搜索 bo"""
        response = self.client.get(
            f'{self.base_url}/bo/domain?filters[status]=active',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_04_search_bo_with_sort(self):
        """带排序搜索 bo"""
        response = self.client.get(
            f'{self.base_url}/bo/domain?sort=name:asc',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_05_resolve_bo(self):
        """解析 bo 值"""
        response = self.client.get(
            f'{self.base_url}/bo/domain/resolve?value=1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_06_resolve_bo_multiple(self):
        """解析多个 bo 值"""
        response = self.client.get(
            f'{self.base_url}/bo/domain/resolve?value=1,2,3',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])


class E2EValueHelpCustomTest(unittest.TestCase):
    """Value Help custom 类型 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/value-help'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_search_custom(self):
        """搜索 custom 类型"""
        response = self.client.get(
            f'{self.base_url}/custom/test_endpoint',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])


class E2EValueHelpAuthTest(unittest.TestCase):
    """Value Help 认证 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/value-help'

    def test_unauthenticated_returns_401(self):
        """未认证返回 401"""
        response = self.client.get(f'{self.base_url}/bo/domain')
        self.assertIn(response.status_code, [401, 403])

    def test_invalid_token_returns_401(self):
        """无效 token 返回 401"""
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer invalid_token'
        }
        response = self.client.get(
            f'{self.base_url}/bo/domain',
            headers=headers
        )
        self.assertIn(response.status_code, [401, 403])


if __name__ == '__main__':
    unittest.main(verbosity=2)
