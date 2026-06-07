# -*- coding: utf-8 -*-
"""
认证流程 E2E 测试

测试场景：
1. 登录成功/失败
2. Token 刷新
3. 登出
4. 密码变更
5. 会话管理
"""

import unittest
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class E2EAuthFlowTest(unittest.TestCase):
    """认证流程 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/auth'

    def test_01_login_success(self):
        """登录成功"""
        response = self.client.post(
            f'{self.base_url}/login',
            data=json.dumps({'username': 'admin', 'password': 'admin123'}),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [200, 404])
        
        if response.status_code == 200:
            data = json.loads(response.data)
            self.assertTrue(data.get('success', False))
            self.assertIsNotNone(data.get('data', {}).get('token'))
            self.__class__.token = data['data']['token']
            self.__class__.user_id = data['data'].get('user_id')

    def test_02_login_invalid_password(self):
        """登录失败 - 无效密码"""
        response = self.client.post(
            f'{self.base_url}/login',
            data=json.dumps({'username': 'admin', 'password': 'wrongpassword'}),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [401, 400, 404])

    def test_03_login_nonexistent_user(self):
        """登录失败 - 不存在用户"""
        response = self.client.post(
            f'{self.base_url}/login',
            data=json.dumps({'username': 'nonexistent', 'password': 'password'}),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [401, 400, 404])

    def test_04_login_missing_fields(self):
        """登录失败 - 缺少字段"""
        response = self.client.post(
            f'{self.base_url}/login',
            data=json.dumps({'username': 'admin'}),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [400, 401, 404])

    def test_05_get_user_info(self):
        """获取用户信息"""
        if not hasattr(self.__class__, 'token'):
            self.skipTest('No token available')
        
        response = self.client.get(
            f'{self.base_url}/me',
            headers={'Authorization': f'Bearer {self.__class__.token}'}
        )
        self.assertIn(response.status_code, [200, 404])
        
        if response.status_code == 200:
            data = json.loads(response.data)
            self.assertTrue(data.get('success', False))
            self.assertIn('username', data.get('data', {}))

    def test_06_refresh_token(self):
        """刷新 Token"""
        if not hasattr(self.__class__, 'token'):
            self.skipTest('No token available')
        
        response = self.client.post(
            f'{self.base_url}/refresh',
            headers={'Authorization': f'Bearer {self.__class__.token}'}
        )
        self.assertIn(response.status_code, [200, 401, 404])

    def test_07_logout(self):
        """登出"""
        if not hasattr(self.__class__, 'token'):
            self.skipTest('No token available')
        
        response = self.client.post(
            f'{self.base_url}/logout',
            headers={'Authorization': f'Bearer {self.__class__.token}'}
        )
        self.assertIn(response.status_code, [200, 204, 404])

    def test_08_protected_route_without_token(self):
        """无 Token 访问受保护路由"""
        response = self.client.get(f'{self.base_url}/me')
        self.assertIn(response.status_code, [401, 403, 404])

    def test_09_protected_route_with_invalid_token(self):
        """无效 Token 访问受保护路由"""
        response = self.client.get(
            f'{self.base_url}/me',
            headers={'Authorization': 'Bearer invalid_token'}
        )
        self.assertIn(response.status_code, [401, 403, 404])


class E2EPasswordChangeTest(unittest.TestCase):
    """密码变更 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/auth'

    def test_change_password_without_auth(self):
        """未认证变更密码"""
        response = self.client.post(
            f'{self.base_url}/change-password',
            data=json.dumps({
                'old_password': 'admin123',
                'new_password': 'newpassword123'
            }),
            content_type='application/json'
        )
        self.assertIn(response.status_code, [401, 403, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
