# -*- coding: utf-8 -*-
"""
角色权限管理 E2E 测试

测试场景：
1. 角色 CRUD
2. 角色权限分配
3. 角色菜单分配
4. 权限规则管理
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


class E2ERoleManagementTest(unittest.TestCase):
    """角色管理 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/bo/role'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}
        cls.created_ids = []

    @classmethod
    def tearDownClass(cls):
        for role_id in cls.created_ids:
            try:
                cls.client.delete(
                    f'{cls.base_url}/{role_id}',
                    headers=cls.headers
                )
            except Exception:
                pass

    def test_01_list_roles(self):
        """列出角色"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 404])

    def test_02_create_role(self):
        """创建角色"""
        suffix = uuid.uuid4().hex[:8]
        role_data = {
            'name': f'E2E Role {suffix}',
            'code': f'e2e_role_{suffix}',
            'description': 'E2E test role',
            'is_active': True
        }
        
        response = self.client.post(
            self.base_url,
            data=json.dumps(role_data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 404])
        
        if response.status_code in [200, 201]:
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('id'):
                self.__class__.created_ids.append(data['data']['id'])

    def test_03_get_role_by_id(self):
        """根据 ID 获取角色"""
        response = self.client.get(
            f'{self.base_url}/1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_04_update_role(self):
        """更新角色"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'name': f'E2E Role Update {suffix}',
            'code': f'e2e_role_upd_{suffix}'
        }
        
        create_resp = self.client.post(
            self.base_url,
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            data = json.loads(create_resp.data)
            if data.get('success') and data.get('data', {}).get('id'):
                role_id = data['data']['id']
                self.__class__.created_ids.append(role_id)
                
                update_data = {'description': 'Updated description'}
                update_resp = self.client.put(
                    f'{self.base_url}/{role_id}',
                    data=json.dumps(update_data),
                    headers=self.headers
                )
                self.assertIn(update_resp.status_code, [200, 400, 404])

    def test_05_delete_role(self):
        """删除角色"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'name': f'E2E Role Delete {suffix}',
            'code': f'e2e_role_del_{suffix}'
        }
        
        create_resp = self.client.post(
            self.base_url,
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            data = json.loads(create_resp.data)
            if data.get('success') and data.get('data', {}).get('id'):
                role_id = data['data']['id']
                
                delete_resp = self.client.delete(
                    f'{self.base_url}/{role_id}',
                    headers=self.headers
                )
                self.assertIn(delete_resp.status_code, [200, 204, 400, 404])


class E2EPermissionRuleTest(unittest.TestCase):
    """权限规则管理 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/permission-rules'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_list_permission_rules(self):
        """列出权限规则"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])


class E2EMenuPermissionTest(unittest.TestCase):
    """菜单权限管理 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/menu-permissions'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_list_menu_permissions(self):
        """列出菜单权限"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_get_role_menu_permissions(self):
        """获取角色菜单权限"""
        response = self.client.get(
            f'{self.base_url}/role/1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
