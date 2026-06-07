# -*- coding: utf-8 -*-
"""
FR-017 Intent API 端到端测试（P1-2）

覆盖：
- GET /api/v1/roles/<id>/intents
- PUT /api/v1/roles/<id>/intents/<bo>/<action>
- DELETE /api/v1/roles/<id>/intents/<bo>/<action>
- POST /api/v1/permissions/check_intent
- GET /api/v1/bos
- GET /api/v1/bos/<id>/actions
- GET /api/v1/bos/<id>/actions/<name>
"""
import sys
import os
import json
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from flask import Flask
from meta.api.intent_api import intent_bp
from meta.core.feature_flags import set_flag, clear_cache
from meta.core.intent_resolver import get_role_intent_dao
from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.core.perm_cache import get_permission_cache


class TestIntentApis(unittest.TestCase):
    """FR-017 API 端到端测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.register_blueprint(intent_bp)
        cls.client = cls.app.test_client()

        dao = get_role_intent_dao()
        cls.db_path = dao._db_path
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = 9992 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (id, username, display_name, email, status)
                VALUES (9992, 'test_intent_api_user', 'Test', 'test@test.com', 'active')
            """)
        cursor.execute("SELECT id FROM roles WHERE id = 9992 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (9992, 'Test Intent API Role', 'test_intent_api', 'Test', 0)
            """)
        cursor.execute("""
            SELECT group_id FROM group_roles WHERE role_id = 9992 LIMIT 1
        """)
        if cursor.fetchone() is None:
            cursor.execute("SELECT id FROM user_groups WHERE id > 0 LIMIT 1")
            grp = cursor.fetchone()
            if grp:
                cursor.execute("""
                    INSERT INTO group_roles (group_id, role_id)
                    VALUES (?, 9992)
                """, (grp[0],))
                cursor.execute("""
                    INSERT INTO user_group_members (user_id, group_id)
                    VALUES (9992, ?)
                """, (grp[0],))
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_intents WHERE role_id = 9992")
        cursor.execute("DELETE FROM group_roles WHERE role_id = 9992")
        cursor.execute("DELETE FROM user_group_members WHERE user_id = 9992")
        cursor.execute("DELETE FROM roles WHERE id = 9992")
        cursor.execute("DELETE FROM users WHERE id = 9992")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        get_permission_cache().clear()
        set_flag('ENABLE_RUNTIME_RESOLUTION', True)
        set_flag('ENABLE_OWNER_FILTER', True)
        # 清理 role_intents
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM role_intents WHERE role_id = 9992")
        conn.commit()
        conn.close()

    def test_01_list_role_intents_empty(self):
        """GET /roles/<id>/intents 初始为空"""
        response = self.client.get('/api/v1/roles/9992/intents')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data'], [])

    def test_02_grant_intent(self):
        """PUT /roles/<id>/intents/<bo>/<action> 授予"""
        response = self.client.put(
            '/api/v1/roles/9992/intents/business_object/read',
            json={'granted': True, 'source': 'manual'},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['data']['granted'])

    def test_03_deny_intent(self):
        """PUT grant=False → deny"""
        response = self.client.put(
            '/api/v1/roles/9992/intents/business_object/delete',
            json={'granted': False},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertFalse(data['data']['granted'])

    def test_04_list_role_intents_after_grant(self):
        """grant 后 list 应有 1 条"""
        self.client.put(
            '/api/v1/roles/9992/intents/domain/read',
            json={'granted': True},
        )
        response = self.client.get('/api/v1/roles/9992/intents')
        data = response.get_json()
        self.assertEqual(len(data['data']), 1)
        self.assertEqual(data['data'][0]['bo_id'], 'domain')

    def test_05_revoke_intent(self):
        """DELETE 撤销"""
        self.client.put(
            '/api/v1/roles/9992/intents/business_object/read',
            json={'granted': True},
        )
        response = self.client.delete(
            '/api/v1/roles/9992/intents/business_object/read',
        )
        self.assertEqual(response.status_code, 200)
        # 验证已撤销
        response = self.client.get('/api/v1/roles/9992/intents')
        data = response.get_json()
        self.assertEqual(len(data['data']), 0)

    def test_06_check_intent_endpoint(self):
        """POST /permissions/check_intent 5 步检查"""
        self.client.put(
            '/api/v1/roles/9992/intents/business_object/read',
            json={'granted': True},
        )
        response = self.client.post(
            '/api/v1/permissions/check_intent',
            json={
                'user_id': 9992,
                'bo_id': 'business_object',
                'action_name': 'read',
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']['steps']), 5)
        self.assertTrue(data['data']['granted'])

    def test_07_check_intent_missing_params(self):
        """check_intent 缺 user_id 应 400"""
        response = self.client.post(
            '/api/v1/permissions/check_intent',
            json={'bo_id': 'business_object'},
        )
        self.assertEqual(response.status_code, 400)

    def test_08_list_bos(self):
        """GET /bos 应返回所有 BO 列表"""
        response = self.client.get('/api/v1/bos')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['data'], list)
        # 应包含 business_object
        bo_ids = [b['bo_id'] for b in data['data']]
        self.assertIn('business_object', bo_ids)
        # 默认 type='entity'
        bo = next(b for b in data['data'] if b['bo_id'] == 'business_object')
        self.assertEqual(bo['type'], 'entity')

    def test_09_list_bos_filter_type(self):
        """GET /bos?type=entity 过滤"""
        response = self.client.get('/api/v1/bos?type=entity')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        for bo in data['data']:
            self.assertEqual(bo['type'], 'entity')

    def test_10_list_bo_actions(self):
        """GET /bos/<id>/actions 列出 actions"""
        response = self.client.get('/api/v1/bos/business_object/actions')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIsInstance(data['data'], list)

    def test_11_get_bo_action_not_found(self):
        """GET 不存在的 action 应 404"""
        response = self.client.get(
            '/api/v1/bos/business_object/actions/non_existent_action',
        )
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
