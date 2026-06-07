# -*- coding: utf-8 -*-
"""
FR-017 BO 统一模型核心测试覆盖
"""
import sys
import os
import json
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.intent_resolver import (
    RoleIntentDAO,
    IntentPermissionChecker,
    MenuIntentMigrationHelper,
    get_role_intent_dao,
    get_intent_permission_checker,
)
from meta.core.bo_schema_loader import get_bo_schema_loader


class TestRoleIntentDAO(unittest.TestCase):
    """RoleIntentDAO 单元测试"""

    @classmethod
    def setUpClass(cls):
        cls.dao = RoleIntentDAO()
        cls.db_path = cls.dao._db_path
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM roles WHERE id = 7777 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (7777, 'Test Intent Role', 'test_intent_role', 'Test', 0)
            """)
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_intents WHERE role_id = 7777")
        cursor.execute("DELETE FROM roles WHERE id = 7777")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()

    def test_01_grant_intent(self):
        """授予 Intent 权限"""
        success = self.dao.grant(
            role_id=7777, bo_id='business_object', action_name='read',
        )
        self.assertTrue(success)
        intents = self.dao.list_for_role(7777)
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]['bo_id'], 'business_object')
        self.assertEqual(intents[0]['action_name'], 'read')
        self.assertTrue(intents[0]['granted'])

    def test_02_deny_intent(self):
        """deny Intent 权限（granted=0）"""
        success = self.dao.deny(
            role_id=7777, bo_id='domain', action_name='delete',
        )
        self.assertTrue(success)
        has = self.dao.has_intent(
            role_ids=[7777], bo_id='domain', action_name='delete',
        )
        self.assertFalse(has)

    def test_03_revoke_intent(self):
        """撤销 Intent 权限"""
        self.dao.grant(
            role_id=7777, bo_id='version', action_name='read',
        )
        self.assertTrue(self.dao.has_intent(
            role_ids=[7777], bo_id='version', action_name='read',
        ))
        self.dao.revoke(
            role_id=7777, bo_id='version', action_name='read',
        )
        self.assertFalse(self.dao.has_intent(
            role_ids=[7777], bo_id='version', action_name='read',
        ))

    def test_04_has_intent_with_parameters(self):
        """参数化的 Intent 检查"""
        self.dao.grant(
            role_id=7777, bo_id='product', action_name='view',
            parameters={'chart_type': 'bar'},
        )
        # 相同参数应匹配
        self.assertTrue(self.dao.has_intent(
            role_ids=[7777], bo_id='product', action_name='view',
            parameters={'chart_type': 'bar'},
        ))
        # 不同参数不匹配
        self.assertFalse(self.dao.has_intent(
            role_ids=[7777], bo_id='product', action_name='view',
            parameters={'chart_type': 'line'},
        ))

    def test_05_parameters_hash_consistent(self):
        """参数 hash 一致性（顺序无关）"""
        h1 = RoleIntentDAO.make_parameters_hash({'a': 1, 'b': 2})
        h2 = RoleIntentDAO.make_parameters_hash({'b': 2, 'a': 1})
        self.assertEqual(h1, h2)


class TestIntentPermissionChecker(unittest.TestCase):
    """5 步权限检查器测试"""

    @classmethod
    def setUpClass(cls):
        cls.checker = IntentPermissionChecker()
        cls.dao = RoleIntentDAO()
        cls.db_path = cls.checker._db_path
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = 7777 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (id, username, display_name, email, status)
                VALUES (7777, 'test_intent_user', 'Test', 'test@test.com', 'active')
            """)
        cursor.execute("SELECT id FROM roles WHERE id = 7777 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (7777, 'Test Intent Role', 'test_intent_role', 'Test', 0)
            """)
        cursor.execute("""
            SELECT group_id FROM group_roles WHERE role_id = 7777 LIMIT 1
        """)
        if cursor.fetchone() is None:
            cursor.execute("SELECT id FROM user_groups WHERE id > 0 LIMIT 1")
            grp = cursor.fetchone()
            if grp:
                cursor.execute("""
                    INSERT INTO group_roles (group_id, role_id)
                    VALUES (?, 7777)
                """, (grp[0],))
                cursor.execute("""
                    INSERT INTO user_group_members (user_id, group_id)
                    VALUES (7777, ?)
                """, (grp[0],))
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_intents WHERE role_id = 7777")
        cursor.execute("DELETE FROM group_roles WHERE role_id = 7777")
        cursor.execute("DELETE FROM user_group_members WHERE user_id = 7777")
        cursor.execute("DELETE FROM roles WHERE id = 7777")
        cursor.execute("DELETE FROM users WHERE id = 7777")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        set_flag('ENABLE_RUNTIME_RESOLUTION', True)
        set_flag('ENABLE_OWNER_FILTER', True)

    def test_01_check_returns_5_steps(self):
        """返回 5 步检查结果"""
        result = self.checker.check(
            user_id=7777, bo_id='business_object', action_name='read',
        )
        self.assertIn('steps', result)
        self.assertEqual(len(result['steps']), 5)

    def test_02_check_granted_with_intent(self):
        """授予 Intent 后 granted=true"""
        self.dao.grant(
            role_id=7777, bo_id='business_object', action_name='read',
        )
        result = self.checker.check(
            user_id=7777, bo_id='business_object', action_name='read',
        )
        # Step 1 Intent 权限应通过
        self.assertTrue(result['steps'][0]['passed'])
        self.assertTrue(result['granted'])

    def test_03_check_denied_without_intent(self):
        """未授予 Intent 时 granted=false"""
        # 确保没有 grant
        self.dao.revoke(
            role_id=7777, bo_id='domain', action_name='delete',
        )
        result = self.checker.check(
            user_id=7777, bo_id='domain', action_name='delete',
        )
        self.assertFalse(result['granted'])
        # Step 1 应失败
        self.assertFalse(result['steps'][0]['passed'])

    def test_04_check_includes_data_conditions(self):
        """Step 4 包含数据权限"""
        self.dao.grant(
            role_id=7777, bo_id='domain', action_name='read',
        )
        result = self.checker.check(
            user_id=7777, bo_id='domain', action_name='read',
        )
        step4 = result['steps'][3]
        self.assertEqual(step4['name'], '数据权限')
        self.assertIn('conditions', step4)


class TestMenuIntentMigrationHelper(unittest.TestCase):
    """menu.yaml 兼容迁移测试"""

    def setUp(self):
        self.helper = MenuIntentMigrationHelper()

    def test_01_generate_default_intent(self):
        """从 bo_bindings 生成默认 Intent"""
        intents = self.helper.generate_default_intent_from_menu(
            menu_code='test_menu',
            bo_bindings=[
                {'bo_id': 'business_object'},
                {'bo_id': 'domain'},
            ],
        )
        # 应生成 2 个 Intent（每个 BO 一个 read）
        self.assertEqual(len(intents), 2)
        self.assertEqual(intents[0]['bo_id'], 'business_object')
        self.assertEqual(intents[0]['action_name'], 'read')


if __name__ == '__main__':
    unittest.main(verbosity=2)
