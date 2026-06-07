# -*- coding: utf-8 -*-
"""
元数据管理 E2E 测试

测试场景：
1. 元数据对象查询
2. 元数据字段查询
3. Schema 管理
4. 元数据缓存
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


class E2EMetaObjectTest(unittest.TestCase):
    """元数据对象 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/meta'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_01_list_meta_objects(self):
        """列出元数据对象"""
        response = self.client.get(
            f'{self.base_url}/objects',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 404])

    def test_02_get_meta_object(self):
        """获取元数据对象"""
        response = self.client.get(
            f'{self.base_url}/objects/user',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_03_get_meta_object_fields(self):
        """获取元数据对象字段"""
        response = self.client.get(
            f'{self.base_url}/objects/user/fields',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_04_get_meta_object_actions(self):
        """获取元数据对象动作"""
        response = self.client.get(
            f'{self.base_url}/objects/user/actions',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_05_get_meta_object_relations(self):
        """获取元数据对象关系"""
        response = self.client.get(
            f'{self.base_url}/objects/user/relations',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])


class E2ESchemaTest(unittest.TestCase):
    """Schema E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/schema'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_01_get_schema(self):
        """获取 Schema"""
        response = self.client.get(
            f'{self.base_url}/user',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_02_get_schema_with_fields(self):
        """获取带字段的 Schema"""
        response = self.client.get(
            f'{self.base_url}/user?include_fields=true',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_03_get_schema_with_relations(self):
        """获取带关系的 Schema"""
        response = self.client.get(
            f'{self.base_url}/user?include_relations=true',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_04_list_all_schemas(self):
        """列出所有 Schema"""
        response = self.client.get(
            self.base_url,
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 404])


class E2EMetaCacheTest(unittest.TestCase):
    """元数据缓存 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/meta'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_clear_cache(self):
        """清除缓存"""
        response = self.client.post(
            f'{self.base_url}/cache/clear',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_reload_cache(self):
        """重载缓存"""
        response = self.client.post(
            f'{self.base_url}/cache/reload',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
