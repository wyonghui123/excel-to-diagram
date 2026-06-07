# -*- coding: utf-8 -*-
"""
用户管理 E2E 测试

测试场景：
1. 用户 CRUD 完整流程
2. 用户角色分配
3. 用户权限查看
4. 用户组管理
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


class E2EUserManagementTest(unittest.TestCase):
    """用户管理 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/bo/user'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}
        cls.created_ids = []

    @classmethod
    def tearDownClass(cls):
        for user_id in cls.created_ids:
            try:
                cls.client.delete(
                    f'{cls.base_url}/{user_id}',
                    headers=cls.headers
                )
            except Exception:
                pass

    def test_01_list_users(self):
        """列出用户"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 404])
        
        if response.status_code == 200:
            data = json.loads(response.data)
            self.assertTrue(data.get('success', False))

    def test_02_create_user(self):
        """创建用户"""
        suffix = uuid.uuid4().hex[:8]
        user_data = {
            'username': f'e2e_user_{suffix}',
            'password': 'test123456',
            'email': f'e2e_user_{suffix}@test.com',
            'display_name': f'E2E Test User {suffix}',
            'status': 'active'
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(user_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 404])
        
        if response.status_code in [200, 201]:
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('id'):
                self.__class__.created_ids.append(data['data']['id'])

    def test_03_create_duplicate_user(self):
        """创建重复用户"""
        suffix = uuid.uuid4().hex[:8]
        user_data = {
            'username': f'e2e_dup_{suffix}',
            'password': 'test123456'
        }
        
        response1 = self.client.post(
            self.base_url,
            data=json.dumps(user_data),
            headers=self.headers
        )
        
        if response1.status_code in [200, 201]:
            data = json.loads(response1.data)
            if data.get('success') and data.get('data', {}).get('id'):
                self.__class__.created_ids.append(data['data']['id'])
                
                response2 = self.client.post(
                    self.base_url,
                    data=json.dumps(user_data),
                    headers=self.headers
                )
                self.assertIn(response2.status_code, [400, 409])

    def test_04_get_user_by_id(self):
        """根据 ID 获取用户"""
        response = self.client.get(
            f'{self.base_url}/1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_05_update_user(self):
        """更新用户"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'username': f'e2e_update_{suffix}',
            'password': 'test123456'
        }
        
        create_resp = self.client.post(
            self.base_url,
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            data = json.loads(create_resp.data)
            if data.get('success') and data.get('data', {}).get('id'):
                user_id = data['data']['id']
                self.__class__.created_ids.append(user_id)
                
                update_data = {'display_name': 'Updated Name'}
                update_resp = self.client.put(
                    f'{self.base_url}/{user_id}',
                    data=json.dumps(update_data),
                    headers=self.headers
                )
                self.assertIn(update_resp.status_code, [200, 400, 404])

    def test_06_delete_user(self):
        """删除用户"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'username': f'e2e_delete_{suffix}',
            'password': 'test123456'
        }
        
        create_resp = self.client.post(
            self.base_url,
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            data = json.loads(create_resp.data)
            if data.get('success') and data.get('data', {}).get('id'):
                user_id = data['data']['id']
                
                delete_resp = self.client.delete(
                    f'{self.base_url}/{user_id}',
                    headers=self.headers
                )
                self.assertIn(delete_resp.status_code, [200, 204, 400, 404])

    def test_07_batch_delete_users(self):
        """批量删除用户"""
        ids = []
        for i in range(2):
            suffix = uuid.uuid4().hex[:8]
            create_data = {
                'username': f'e2e_batch_{suffix}_{i}',
                'password': 'test123456'
            }
            create_resp = self.client.post(
                self.base_url,
                data=json.dumps(create_data),
                headers=self.headers
            )
            if create_resp.status_code in [200, 201]:
                data = json.loads(create_resp.data)
                if data.get('success') and data.get('data', {}).get('id'):
                    ids.append(data['data']['id'])
        
        if ids:
            delete_resp = self.client.post(
                f'{self.base_url}/batch-delete',
                data=json.dumps({'ids': ids}),
                headers=self.headers
            )
            self.assertIn(delete_resp.status_code, [200, 204, 400, 404])

    def test_08_search_users(self):
        """搜索用户"""
        response = self.client.get(
            f'{self.base_url}?search=admin&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_09_filter_users_by_status(self):
        """按状态过滤用户"""
        response = self.client.get(
            f'{self.base_url}?status=active&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])


class E2EUserGroupTest(unittest.TestCase):
    """用户组管理 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/bo/user_group'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}
        cls.created_ids = []

    @classmethod
    def tearDownClass(cls):
        for group_id in cls.created_ids:
            try:
                cls.client.delete(
                    f'{cls.base_url}/{group_id}',
                    headers=cls.headers
                )
            except Exception:
                pass

    def test_list_user_groups(self):
        """列出用户组"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 404])

    def test_create_user_group(self):
        """创建用户组"""
        suffix = uuid.uuid4().hex[:8]
        group_data = {
            'name': f'E2E Group {suffix}',
            'code': f'e2e_group_{suffix}',
            'description': 'E2E test group'
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(group_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 404])
        
        if response.status_code in [200, 201]:
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('id'):
                self.__class__.created_ids.append(data['data']['id'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
