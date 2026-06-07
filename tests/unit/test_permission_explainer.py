# -*- coding: utf-8 -*-
r"""
FR-012 Match Preview API 单元测试

测试覆盖：
1. 5 步检查完整返回
2. SQL preview 生成
3. granted 计算（无角色 -> denied）
4. 边界情况（无 BO、无 user_id）
5. 维度条件 + Owner 过滤组合
6. owner_aspect 自动应用

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\unit\test_permission_explainer.py
"""
import sys
import os
import json
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.permission_explainer import get_permission_explainer
from meta.core.bo_schema_loader import get_bo_schema_loader


class TestPermissionExplainer(unittest.TestCase):
    """Permission Explainer 单元测试"""

    @classmethod
    def setUpClass(cls):
        cls.explainer = get_permission_explainer()
        cls.db_path = cls.explainer._db_path
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        """注入测试数据"""
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        # 创建测试用户
        cursor.execute("SELECT id FROM users WHERE id = 8888 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO users (id, username, display_name, email, status)
                VALUES (8888, 'test_explain_user', 'Test User', 'test@test.com', 'active')
            """)
        # 创建测试角色
        cursor.execute("SELECT id FROM roles WHERE id = 8888 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (8888, 'Test Explain Role', 'test_explain_role', 'Test', 0)
            """)
        # 关联用户-角色
        cursor.execute("""
            SELECT group_id FROM group_roles WHERE role_id = 8888 LIMIT 1
        """)
        group_id = cursor.fetchone()
        if group_id is None:
            # 找一个组
            cursor.execute("SELECT id FROM user_groups WHERE id > 0 LIMIT 1")
            grp = cursor.fetchone()
            if grp:
                cursor.execute("""
                    INSERT INTO group_roles (group_id, role_id)
                    VALUES (?, ?)
                """, (grp[0], 8888))
                cursor.execute("""
                    INSERT INTO user_group_members (user_id, group_id)
                    VALUES (8888, ?)
                """, (grp[0],))
        # 清理已有
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 8888")
        # 插入 domain 维度公共条件
        cursor.execute("""
            INSERT INTO role_dimension_scopes
            (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (8888, 'domain', json.dumps([1, 2, 3]), 1, 'include', None))
        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        """清理测试数据"""
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 8888")
        cursor.execute("DELETE FROM group_roles WHERE role_id = 8888")
        cursor.execute("DELETE FROM user_group_members WHERE user_id = 8888")
        cursor.execute("DELETE FROM roles WHERE id = 8888")
        cursor.execute("DELETE FROM users WHERE id = 8888")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        # 确保 flag 开启
        set_flag('ENABLE_RUNTIME_RESOLUTION', True)
        set_flag('ENABLE_OWNER_FILTER', True)

    def test_01_explain_returns_5_steps(self):
        """FR-012: 返回 5 步检查结果"""
        result = self.explainer.explain(
            user_id=8888, bo_id='domain', action_id='read'
        )
        self.assertIn('steps', result)
        self.assertEqual(len(result['steps']), 5)
        for i, step in enumerate(result['steps'], 1):
            self.assertEqual(step['step'], i)
            self.assertIn('name', step)
            self.assertIn('passed', step)
            self.assertIn('details', step)

    def test_02_explain_step1_role_check(self):
        """FR-012: Step 1 角色检查"""
        result = self.explainer.explain(
            user_id=8888, bo_id='domain', action_id='read'
        )
        step1 = result['steps'][0]
        self.assertEqual(step1['name'], '角色检查')
        self.assertTrue(step1['passed'])
        self.assertIn('role_ids', step1)
        self.assertIn(8888, step1['role_ids'])

    def test_03_explain_step2_dimension_scope(self):
        """FR-012: Step 2 维度范围检查"""
        result = self.explainer.explain(
            user_id=8888, bo_id='domain', action_id='read'
        )
        step2 = result['steps'][1]
        self.assertEqual(step2['name'], '维度范围')
        self.assertIn('conditions', step2)
        # 应该有 domain 维度的条件
        domain_conds = [
            c for c in step2['conditions'] if c.get('dimension') == 'domain'
        ]
        self.assertEqual(len(domain_conds), 1)
        self.assertEqual(domain_conds[0]['value'], [1, 2, 3])

    def test_04_explain_step3_owner_filter(self):
        """FR-012: Step 3 Owner 过滤"""
        # business_object 有 owner_id 字段
        result = self.explainer.explain(
            user_id=8888, bo_id='business_object', action_id='read'
        )
        step3 = result['steps'][2]
        self.assertEqual(step3['name'], 'Owner 过滤')
        # business_object 有 owner_id，应有 owner 条件
        self.assertIsNotNone(step3['condition'])
        self.assertEqual(step3['condition']['field'], 'owner_id')
        self.assertEqual(step3['condition']['value'], 8888)

    def test_05_explain_step4_sql_preview(self):
        """FR-012: Step 4 SQL 预览生成"""
        result = self.explainer.explain(
            user_id=8888, bo_id='domain', action_id='read'
        )
        step4 = result['steps'][3]
        self.assertEqual(step4['name'], 'SQL 预览')
        sql = step4['sql_preview']
        # 应包含 SELECT FROM domains
        self.assertIn('SELECT', sql)
        self.assertIn('FROM', sql)
        # domain BO 有 [1, 2, 3] 维度的过滤
        self.assertIn('IN', sql)

    def test_06_explain_step5_final_decision(self):
        """FR-012: Step 5 最终决策"""
        result = self.explainer.explain(
            user_id=8888, bo_id='domain', action_id='read'
        )
        step5 = result['steps'][4]
        self.assertEqual(step5['name'], '最终决策')
        self.assertTrue(step5['passed'])

    def test_07_explain_granted_for_user_with_role(self):
        """FR-012: 有角色的用户 granted=true"""
        result = self.explainer.explain(
            user_id=8888, bo_id='domain', action_id='read'
        )
        self.assertTrue(result['granted'])

    def test_08_explain_denied_for_user_without_role(self):
        """FR-012: 无角色的用户 granted=false"""
        result = self.explainer.explain(
            user_id=99999, bo_id='domain', action_id='read'  # 不存在的用户
        )
        self.assertFalse(result['granted'])
        # Step 1 应失败
        self.assertFalse(result['steps'][0]['passed'])

    def test_09_explain_nonexistent_bo(self):
        """FR-012: 不存在的 BO 不影响 granted（只影响条件）"""
        result = self.explainer.explain(
            user_id=8888, bo_id='non_existent_bo_xyz', action_id='read'
        )
        # 用户有角色，granted 应为 true（没有匹配的绑定，没条件但不算 denied）
        self.assertTrue(result['granted'])
        # SQL 预览应该是简单 SELECT
        self.assertIn('non_existent_bo_xyzs', result['sql_preview'])

    def test_10_explain_owner_combine_with_dimension(self):
        """FR-012: Owner 过滤 + 维度范围组合"""
        result = self.explainer.explainer = self.explainer
        result = self.explainer.explain(
            user_id=8888, bo_id='business_object', action_id='read'
        )
        # business_object 有 owner_id 字段
        # 应该既显示维度条件（如果有）也显示 owner 条件
        step2 = result['steps'][1]
        step3 = result['steps'][2]
        # Owner 条件应存在
        self.assertIsNotNone(step3['condition'])
        # SQL preview 应同时包含维度过滤和 owner 过滤（用 AND 连接）
        sql = result['sql_preview']
        if step2['conditions'] and step3['condition']:
            self.assertIn('AND', sql)


if __name__ == '__main__':
    unittest.main(verbosity=2)
