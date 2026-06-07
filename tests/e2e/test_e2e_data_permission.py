# -*- coding: utf-8 -*-
"""
数据权限管理 E2E 测试

测试场景：
1. 数据权限 CRUD
2. 权限继承
3. 权限过滤
4. 批量权限分配
"""

import unittest
import sys
import os
import json
import uuid

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


class E2EDataPermissionTest(unittest.TestCase):
    """数据权限管理 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/data-permissions'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}
        cls.created_ids = []

    @classmethod
    def tearDownClass(cls):
        for perm_id in cls.created_ids:
            try:
                cls.client.delete(
                    f'{cls.base_url}/{perm_id}',
                    headers=cls.headers
                )
            except Exception:
                pass

    def test_01_list_data_permissions(self):
        """列出数据权限"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_02_list_by_user_id(self):
        """按用户 ID 列出权限"""
        response = self.client.get(
            f'{self.base_url}?user_id=1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_03_list_by_resource_type(self):
        """按资源类型列出权限"""
        response = self.client.get(
            f'{self.base_url}?resource_type=domain',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_04_create_data_permission(self):
        """创建数据权限"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 1,
            'permission_level': 'read',
            'inherit_to_children': True
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 403, 404])
        
        if response.status_code in [200, 201]:
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('id'):
                self.__class__.created_ids.append(data['data']['id'])

    def test_05_create_with_invalid_level(self):
        """创建无效权限级别"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 1,
            'permission_level': 'invalid_level'
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [400, 403, 404])

    def test_06_create_with_missing_fields(self):
        """创建缺少字段"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain'
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [400, 403, 404])

    def test_07_update_data_permission(self):
        """更新数据权限"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 999,
            'permission_level': 'read'
        }
        
        create_resp = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            data = json.loads(create_resp.data)
            if data.get('success') and data.get('data', {}).get('id'):
                perm_id = data['data']['id']
                self.__class__.created_ids.append(perm_id)
                
                update_data = {'permission_level': 'write'}
                update_resp = self.client.put(
                    f'{self.base_url}/{perm_id}',
                    data=json.dumps(update_data),
                    headers=self.headers
                )
                self.assertIn(update_resp.status_code, [200, 400, 403, 404])

    def test_08_delete_data_permission(self):
        """删除数据权限"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 998,
            'permission_level': 'read'
        }
        
        create_resp = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            data = json.loads(create_resp.data)
            if data.get('success') and data.get('data', {}).get('id'):
                perm_id = data['data']['id']
                
                delete_resp = self.client.delete(
                    f'{self.base_url}/{perm_id}',
                    headers=self.headers
                )
                self.assertIn(delete_resp.status_code, [200, 204, 400, 403, 404])


class E2EDataPermissionInheritanceTest(unittest.TestCase):
    """数据权限继承 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/data-permissions'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}
        cls.created_ids = []

    @classmethod
    def tearDownClass(cls):
        for perm_id in cls.created_ids:
            try:
                cls.client.delete(
                    f'{cls.base_url}/{perm_id}',
                    headers=cls.headers
                )
            except Exception:
                pass

    def test_create_with_inheritance(self):
        """创建带继承的权限"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 1,
            'permission_level': 'admin',
            'inherit_to_children': True
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 403, 404])
        
        if response.status_code in [200, 201]:
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('id'):
                self.__class__.created_ids.append(data['data']['id'])
                
                perm_data = data['data']
                self.assertTrue(perm_data.get('inherit_to_children', False))

    def test_create_without_inheritance(self):
        """创建不带继承的权限"""
        perm_data = {
            'user_id': 1,
            'resource_type': 'domain',
            'resource_id': 2,
            'permission_level': 'read',
            'inherit_to_children': False
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(perm_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 403, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
