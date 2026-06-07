# -*- coding: utf-8 -*-
"""
跨模块集成验证（P1-4）

验证完整链路：
DAO → Cache → Resolver → Explainer → Checker

测试场景：
1. Grant Intent → Cache miss → Resolver → Explainer → Checker all pass
2. 重复请求 → Cache hit
3. Revoke → Checker denied
4. 数据权限叠加
5. 多角色 OR
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
    get_role_intent_dao,
    get_intent_permission_checker,
)
from meta.core.permission_explainer import get_permission_explainer
from meta.core.perm_cache import get_permission_cache, PermissionCache
from meta.core.bo_schema_loader import get_bo_schema_loader


class TestFullChainIntegration(unittest.TestCase):
    """P1-4 跨模块集成测试"""

    @classmethod
    def setUpClass(cls):
        cls.dao = get_role_intent_dao()
        cls.checker = get_intent_permission_checker()
        cls.explainer = get_permission_explainer()
        cls.cache = get_permission_cache()
        cls.db_path = cls.dao._db_path
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        # 用户
        cursor.execute("SELECT id FROM users WHERE id = 9993 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (id, username, display_name, email, status)
                VALUES (9993, 'test_full_chain_user', 'Test', 'test@test.com', 'active')
            """)
        # 角色
        cursor.execute("SELECT id FROM roles WHERE id = 9993 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (9993, 'Test Full Chain Role', 'test_full_chain', 'Test', 0)
            """)
        cursor.execute("""
            SELECT group_id FROM group_roles WHERE role_id = 9993 LIMIT 1
        """)
        if cursor.fetchone() is None:
            cursor.execute("SELECT id FROM user_groups WHERE id > 0 LIMIT 1")
            grp = cursor.fetchone()
            if grp:
                cursor.execute("""
                    INSERT INTO group_roles (group_id, role_id)
                    VALUES (?, 9993)
                """, (grp[0],))
                cursor.execute("""
                    INSERT INTO user_group_members (user_id, group_id)
                    VALUES (9993, ?)
                """, (grp[0],))
        # 维度范围
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 9993")
        cursor.execute("""
            INSERT INTO role_dimension_scopes
            (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
            VALUES (9993, 'domain', ?, 1, 'include', NULL)
        """, (json.dumps([1, 2, 3]),))
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_intents WHERE role_id = 9993")
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 9993")
        cursor.execute("DELETE FROM group_roles WHERE role_id = 9993")
        cursor.execute("DELETE FROM user_group_members WHERE user_id = 9993")
        cursor.execute("DELETE FROM roles WHERE id = 9993")
        cursor.execute("DELETE FROM users WHERE id = 9993")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        self.cache.clear()
        set_flag('ENABLE_RUNTIME_RESOLUTION', True)
        set_flag('ENABLE_OWNER_FILTER', True)
        # 清理 role_intents
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM role_intents WHERE role_id = 9993")
        conn.commit()
        conn.close()

    def test_01_full_chain_grant_pass(self):
        """完整链路：Grant → Explainer → Checker all pass"""
        # 1. Grant Intent
        self.dao.grant(
            role_id=9993, bo_id='business_object', action_name='read',
        )
        # 2. Explainer
        explain_result = self.explainer.explain(
            user_id=9993, bo_id='business_object', action_id='read',
        )
        self.assertTrue(explain_result['granted'])
        # 3. Checker
        check_result = self.checker.check(
            user_id=9993, bo_id='business_object', action_name='read',
        )
        self.assertTrue(check_result['granted'])

    def test_02_cache_hit_after_repeat(self):
        """重复请求应走缓存"""
        self.dao.grant(
            role_id=9993, bo_id='domain', action_name='read',
        )
        # 第 1 次（miss）
        self.explainer.explain(user_id=9993, bo_id='domain', action_id='read')
        # 第 2 次（hit）
        self.explainer.explain(user_id=9993, bo_id='domain', action_id='read')
        stats = self.cache.stats()
        # 至少有 1 次 hit
        self.assertGreaterEqual(stats['hits'], 1)

    def test_03_revoke_blocks_checker(self):
        """Revoke 后 Checker 应 denied"""
        self.dao.grant(
            role_id=9993, bo_id='product', action_name='read',
        )
        result1 = self.checker.check(
            user_id=9993, bo_id='product', action_name='read',
        )
        self.assertTrue(result1['granted'])
        # Revoke
        self.dao.revoke(
            role_id=9993, bo_id='product', action_name='read',
        )
        result2 = self.checker.check(
            user_id=9993, bo_id='product', action_name='read',
        )
        self.assertFalse(result2['granted'])

    def test_04_data_conditions_in_explainer(self):
        """Explainer 应包含数据权限条件"""
        # 用户已有 role_dim_scopes (domain [1,2,3])
        # 不需要 grant Intent（explainer 不严格检查 Intent）
        result = self.explainer.explain(
            user_id=9993, bo_id='business_object', action_id='read',
        )
        step2 = result['steps'][1]
        # 应有维度条件
        self.assertIn('conditions', step2)
        # business_object 应有 domain 维度的条件
        domain_conds = [
            c for c in step2['conditions']
            if c.get('dimension') == 'domain'
        ]
        self.assertGreater(len(domain_conds), 0)

    def test_05_sql_preview_uses_redundant_field(self):
        """business_object 维度 binding 应在 SQL preview 中体现

        business_object 有 domain 维度的 binding 走 service_module 路径。
        SQL preview 应包含 binding 字段 + 维度值。
        """
        result = self.explainer.explain(
            user_id=9993, bo_id='business_object', action_id='read',
        )
        sql = result['sql_preview']
        # 应包含 binding 字段（service_module_id 路径）和维度值 (1,2,3)
        self.assertTrue(
            'service_module_id' in sql or 'domain_id' in sql,
            f"SQL preview 缺字段: {sql}",
        )
        # 应包含维度值
        self.assertIn('1,2,3', sql)

    def test_06_explainer_and_checker_consistency(self):
        """Explainer 和 Checker 的 granted 应一致"""
        # Case A: grant Intent
        self.dao.grant(
            role_id=9993, bo_id='version', action_name='read',
        )
        exp_a = self.explainer.explain(
            user_id=9993, bo_id='version', action_id='read',
        )
        chk_a = self.checker.check(
            user_id=9993, bo_id='version', action_name='read',
        )
        # Explainer 偏宽松，Checker 严格
        # 但有 Intent 时应一致
        self.assertTrue(exp_a['granted'])
        self.assertTrue(chk_a['granted'])

    def test_07_owner_filter_combined(self):
        """Owner 过滤与维度范围组合"""
        self.dao.grant(
            role_id=9993, bo_id='business_object', action_name='read',
        )
        result = self.explainer.explain(
            user_id=9993, bo_id='business_object', action_id='read',
        )
        # business_object 有 owner_id 字段
        owner_step = result['steps'][2]
        self.assertIsNotNone(owner_step['condition'])
        # SQL preview 应包含 owner_id
        self.assertIn('owner_id', result['sql_preview'])

    def test_08_dao_parameters_hash_distinct(self):
        """不同参数生成不同 hash"""
        h1 = RoleIntentDAO.make_parameters_hash({'a': 1})
        h2 = RoleIntentDAO.make_parameters_hash({'a': 2})
        self.assertNotEqual(h1, h2)

    def test_09_cache_key_for_resolver(self):
        """Cache key 一致性"""
        k1 = PermissionCache.make_key(
            user_id=9993, bo_id='domain', role_ids=[9993],
        )
        k2 = PermissionCache.make_key(
            user_id=9993, bo_id='domain', role_ids=[9993],
        )
        self.assertEqual(k1, k2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
