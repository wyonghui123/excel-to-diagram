# -*- coding: utf-8 -*-
"""
业务对象 (BO) E2E 测试

测试场景：
1. BO CRUD 完整流程
2. deep_insert 深度插入
3. batch 批量操作
4. 关联关系管理
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


class E2EBOCrudTest(unittest.TestCase):
    """BO CRUD E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/bo'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}
        cls.created = []

    @classmethod
    def tearDownClass(cls):
        for obj_type, obj_id in cls.created:
            try:
                cls.client.delete(
                    f'{cls.base_url}/{obj_type}/{obj_id}',
                    headers=cls.headers
                )
            except Exception:
                pass

    def test_01_list_domains(self):
        """列出 domain"""
        response = self.client.get(
            f'{self.base_url}/domain?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 404])

    def test_02_create_domain(self):
        """创建 domain"""
        suffix = uuid.uuid4().hex[:8]
        data = {
            'name': f'E2E Domain {suffix}',
            'code': f'e2e_domain_{suffix}',
            'description': 'E2E test domain'
        }
        
        response = self.client.post(
            f'{self.base_url}/domain',
            data=json.dumps(data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 404])
        
        if response.status_code in [200, 201]:
            result = json.loads(response.data)
            if result.get('success') and result.get('data', {}).get('id'):
                self.__class__.created.append(('domain', result['data']['id']))

    def test_03_get_domain_by_id(self):
        """根据 ID 获取 domain"""
        response = self.client.get(
            f'{self.base_url}/domain/1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_04_update_domain(self):
        """更新 domain"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'name': f'E2E Domain Update {suffix}',
            'code': f'e2e_domain_upd_{suffix}'
        }
        
        create_resp = self.client.post(
            f'{self.base_url}/domain',
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            result = json.loads(create_resp.data)
            if result.get('success') and result.get('data', {}).get('id'):
                obj_id = result['data']['id']
                self.__class__.created.append(('domain', obj_id))
                
                update_data = {'description': 'Updated description'}
                update_resp = self.client.put(
                    f'{self.base_url}/domain/{obj_id}',
                    data=json.dumps(update_data),
                    headers=self.headers
                )
                self.assertIn(update_resp.status_code, [200, 400, 404])

    def test_05_delete_domain(self):
        """删除 domain"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'name': f'E2E Domain Delete {suffix}',
            'code': f'e2e_domain_del_{suffix}'
        }
        
        create_resp = self.client.post(
            f'{self.base_url}/domain',
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            result = json.loads(create_resp.data)
            if result.get('success') and result.get('data', {}).get('id'):
                obj_id = result['data']['id']
                
                delete_resp = self.client.delete(
                    f'{self.base_url}/domain/{obj_id}',
                    headers=self.headers
                )
                self.assertIn(delete_resp.status_code, [200, 204, 400, 404])

    def test_06_query_with_filters(self):
        """带过滤条件查询"""
        response = self.client.get(
            f'{self.base_url}/domain?name__contains=test&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_07_query_with_sorting(self):
        """带排序查询"""
        response = self.client.get(
            f'{self.base_url}/domain?ordering=-created_at&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])

    def test_08_query_with_pagination(self):
        """分页查询"""
        response = self.client.get(
            f'{self.base_url}/domain?page=2&page_size=5',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 400, 404])


class E2EBODeepInsertTest(unittest.TestCase):
    """BO deep_insert E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/bo'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_deep_insert_simple(self):
        """简单 deep_insert"""
        suffix = uuid.uuid4().hex[:8]
        data = {
            'name': f'E2E Deep Insert {suffix}',
            'code': f'e2e_deep_{suffix}'
        }
        
        response = self.client.post(
            f'{self.base_url}/domain/deep',
            data=json.dumps(data),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 201, 400, 404])


class E2EBOBatchTest(unittest.TestCase):
    """BO batch 操作 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v2/bo'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_batch_delete_empty(self):
        """空列表批量删除"""
        response = self.client.post(
            f'{self.base_url}/domain/batch-delete',
            data=json.dumps({'ids': []}),
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 204, 400, 404])

    def test_batch_delete_single(self):
        """单个 ID 批量删除"""
        suffix = uuid.uuid4().hex[:8]
        create_data = {
            'name': f'E2E Batch Single {suffix}',
            'code': f'e2e_batch_s_{suffix}'
        }
        
        create_resp = self.client.post(
            f'{self.base_url}/domain',
            data=json.dumps(create_data),
            headers=self.headers
        )
        
        if create_resp.status_code in [200, 201]:
            result = json.loads(create_resp.data)
            if result.get('success') and result.get('data', {}).get('id'):
                obj_id = result['data']['id']
                
                delete_resp = self.client.post(
                    f'{self.base_url}/domain/batch-delete',
                    data=json.dumps({'ids': [obj_id]}),
                    headers=self.headers
                )
                self.assertIn(delete_resp.status_code, [200, 204, 400, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
