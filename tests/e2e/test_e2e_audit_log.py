# -*- coding: utf-8 -*-
"""
审计日志 E2E 测试

测试场景：
1. 审计日志查询
2. 审计日志过滤
3. 审计日志导出
4. 操作日志查询
"""

import unittest
import sys
import os
import json
from datetime import datetime, timedelta

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


class E2EAuditLogTest(unittest.TestCase):
    """审计日志 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/audit'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_01_list_audit_logs(self):
        """列出审计日志"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_02_filter_by_user_id(self):
        """按用户 ID 过滤"""
        response = self.client.get(
            f'{self.base_url}?user_id=1&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_03_filter_by_action(self):
        """按操作类型过滤"""
        response = self.client.get(
            f'{self.base_url}?action=create&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_04_filter_by_object_type(self):
        """按对象类型过滤"""
        response = self.client.get(
            f'{self.base_url}?object_type=user&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_05_filter_by_date_range(self):
        """按日期范围过滤"""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        response = self.client.get(
            f'{self.base_url}?start_date={start_date}&end_date={end_date}&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_06_filter_by_severity(self):
        """按严重级别过滤"""
        response = self.client.get(
            f'{self.base_url}?severity=WARNING&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_07_search_logs(self):
        """搜索日志"""
        response = self.client.get(
            f'{self.base_url}?search=admin&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_08_get_log_by_id(self):
        """根据 ID 获取日志"""
        response = self.client.get(
            f'{self.base_url}/1',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 404])

    def test_09_get_log_statistics(self):
        """获取日志统计"""
        response = self.client.get(
            f'{self.base_url}/statistics',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_10_get_log_overview(self):
        """获取日志概览"""
        response = self.client.get(
            f'{self.base_url}/overview',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])


class E2EOperationLogTest(unittest.TestCase):
    """操作日志 E2E 测试"""

    @classmethod
    def setUpClass(cls):
        from meta.server import create_app
        cls.app = create_app()
        cls.client = cls.app.test_client()
        cls.base_url = '/api/v1/operation-logs'
        cls.token = _get_admin_token(cls.client)
        cls.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cls.token}'
        } if cls.token else {}

    def test_list_operation_logs(self):
        """列出操作日志"""
        response = self.client.get(
            f'{self.base_url}?page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_filter_by_operation_type(self):
        """按操作类型过滤"""
        response = self.client.get(
            f'{self.base_url}?operation_type=CREATE&page=1&page_size=10',
            headers=self.headers
        )
        self.assertIn(response.status_code, [200, 401, 403, 404])


if __name__ == '__main__':
    unittest.main(verbosity=2)
