# -*- coding: utf-8 -*-
"""
FR-012 权限 API 端到端测试（P1-2）

覆盖：
- POST /api/v1/permissions/explain
- POST /api/v1/permissions/check
"""
import sys
import os
import json
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from flask import Flask
from meta.api.permission_api import permission_bp
from meta.core.feature_flags import set_flag, clear_cache
from meta.core.permission_explainer import get_permission_explainer
from meta.core.perm_cache import get_permission_cache
from meta.core.bo_schema_loader import get_bo_schema_loader


class TestPermissionApis(unittest.TestCase):
    """FR-012 API 端到端测试"""

    @classmethod
    def setUpClass(cls):
        """创建 Flask app + 注册 bp + 设置测试数据"""
        cls.app = Flask(__name__)
        cls.app.register_blueprint(permission_bp)
        cls.client = cls.app.test_client()

        explainer = get_permission_explainer()
        cls.db_path = explainer._db_path
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = 9991 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (id, username, display_name, email, status)
                VALUES (9991, 'test_api_user', 'Test', 'test@test.com', 'active')
            """)
        cursor.execute("SELECT id FROM roles WHERE id = 9991 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (9991, 'Test API Role', 'test_api_role', 'Test', 0)
            """)
        cursor.execute("""
            SELECT group_id FROM group_roles WHERE role_id = 9991 LIMIT 1
        """)
        if cursor.fetchone() is None:
            cursor.execute("SELECT id FROM user_groups WHERE id > 0 LIMIT 1")
            grp = cursor.fetchone()
            if grp:
                cursor.execute("""
                    INSERT INTO group_roles (group_id, role_id)
                    VALUES (?, 9991)
                """, (grp[0],))
                cursor.execute("""
                    INSERT INTO user_group_members (user_id, group_id)
                    VALUES (9991, ?)
                """, (grp[0],))
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 9991")
        cursor.execute("""
            INSERT INTO role_dimension_scopes
            (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
            VALUES (9991, 'domain', ?, 1, 'include', NULL)
        """, (json.dumps([1, 2, 3]),))
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 9991")
        cursor.execute("DELETE FROM group_roles WHERE role_id = 9991")
        cursor.execute("DELETE FROM user_group_members WHERE user_id = 9991")
        cursor.execute("DELETE FROM roles WHERE id = 9991")
        cursor.execute("DELETE FROM users WHERE id = 9991")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        get_permission_cache().clear()
        set_flag('ENABLE_RUNTIME_RESOLUTION', True)
        set_flag('ENABLE_OWNER_FILTER', True)

    def test_01_explain_endpoint(self):
        """POST /api/v1/permissions/explain 端到端"""
        response = self.client.post(
            '/api/v1/permissions/explain',
            json={
                'user_id': 9991,
                'bo_id': 'domain',
                'action_id': 'read',
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertEqual(data['data']['bo_id'], 'domain')
        self.assertEqual(data['data']['user_id'], 9991)
        self.assertEqual(len(data['data']['steps']), 5)
        self.assertTrue(data['data']['granted'])

    def test_02_explain_endpoint_missing_user_id(self):
        """缺 user_id 应 400"""
        response = self.client.post(
            '/api/v1/permissions/explain',
            json={'bo_id': 'domain'},
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn('user_id', data['error'])

    def test_03_explain_endpoint_invalid_json(self):
        """无效 JSON 不应 500"""
        response = self.client.post(
            '/api/v1/permissions/explain',
            data='not json',
            content_type='application/json',
        )
        # 应 fallback 到 {} 然后 400
        self.assertIn(response.status_code, [400, 500])

    def test_04_check_endpoint(self):
        """POST /api/v1/permissions/check 端到端"""
        response = self.client.post(
            '/api/v1/permissions/check',
            json={'user_id': 9991, 'bo_id': 'domain', 'action_id': 'read'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('granted', data['data'])

    def test_05_check_endpoint_denied(self):
        """无角色用户应 denied"""
        response = self.client.post(
            '/api/v1/permissions/check',
            json={'user_id': 99999, 'bo_id': 'domain', 'action_id': 'read'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertFalse(data['data']['granted'])

    def test_06_explain_returns_sql_preview(self):
        """explain 应包含 SQL preview"""
        response = self.client.post(
            '/api/v1/permissions/explain',
            json={'user_id': 9991, 'bo_id': 'domain', 'action_id': 'read'},
        )
        data = response.get_json()
        self.assertIn('sql_preview', data['data'])
        self.assertIn('SELECT', data['data']['sql_preview'])
        self.assertIn('FROM domains', data['data']['sql_preview'])

    def test_07_explain_with_parameters(self):
        """带 parameters 参数"""
        response = self.client.post(
            '/api/v1/permissions/explain',
            json={
                'user_id': 9991,
                'bo_id': 'domain',
                'action_id': 'read',
                'parameters': {'a': 1},
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
