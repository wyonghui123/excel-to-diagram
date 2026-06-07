# -*- coding: utf-8 -*-
r"""
M3.1 重叠加检测器测试

测试覆盖：
1. 检测 Section 1 dim_scope 与 Section 3 condition rules 重叠
2. 不同字段不重叠
3. 空配置不重叠
4. feature flag 控制
5. 多个 dim_scope 与 rule 组合

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\unit\test_overlap_detector.py
"""
import sys
import os
import json
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.dim_scope_overlap_detector import (
    DimScopeOverlapDetector,
    get_overlap_detector,
)


class TestOverlapDetector(unittest.TestCase):
    """重叠加检测器单元测试"""

    TEST_ROLE_ID = 996

    @classmethod
    def setUpClass(cls):
        cls.detector = get_overlap_detector()
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        """注入测试数据"""
        conn = sqlite3.connect(cls.detector._db_path)
        cursor = conn.cursor()

        # 创建测试角色
        cursor.execute("SELECT id FROM roles WHERE id = 996 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (996, 'Overlap Test', 'overlap_test', 'Test', 0)
            """)

        # 清理已有
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 996")
        cursor.execute("DELETE FROM permission_rules WHERE role_id = 996")

        # Section 1: 配 domain=[1, 2, 3, 4, 5]
        cursor.execute("""
            INSERT INTO role_dimension_scopes
            (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (996, 'domain', json.dumps([1, 2, 3, 4, 5]), 1, 'include', None))

        # Section 1: 配 product=[10]
        cursor.execute("""
            INSERT INTO role_dimension_scopes
            (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (996, 'product', json.dumps([10]), 1, 'include', None))

        # Section 3: 配 rule 1, domain in [3, 4, 5, 6] - 与 dim_scope 部分重叠
        cursor.execute("""
            INSERT INTO permission_rules
            (role_id, resource_type, condition, permission_level, is_denied,
             inherit_to_children, propagate_to_parents, analysis_mode,
             created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
        """, (
            996, 'domain',
            json.dumps({'field': 'domain', 'operator': 'in', 'value': [3, 4, 5, 6]}),
            'read', 0, 1, 0, 'value', 1,
        ))

        # Section 3: 配 rule 2, status = 'active' - 不同字段不重叠
        cursor.execute("""
            INSERT INTO permission_rules
            (role_id, resource_type, condition, permission_level, is_denied,
             inherit_to_children, propagate_to_parents, analysis_mode,
             created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
        """, (
            996, 'domain',
            json.dumps({'field': 'status', 'operator': 'eq', 'value': 'active'}),
            'read', 0, 1, 0, 'value', 1,
        ))

        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        conn = sqlite3.connect(cls.detector._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 996")
        cursor.execute("DELETE FROM permission_rules WHERE role_id = 996")
        cursor.execute("DELETE FROM roles WHERE id = 996")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        set_flag('ENABLE_DUP_CONFIG_WARNING', True)

    # ---- 重叠加检测 ----

    def test_01_detect_overlap_with_field_match(self):
        """测试：同字段值有交集，检测到重叠"""
        overlaps = self.detector.detect_overlaps(role_id=996)
        # domain 字段重叠（3, 4, 5）
        domain_overlaps = [o for o in overlaps if o['field'] == 'domain']
        self.assertEqual(len(domain_overlaps), 1)
        self.assertEqual(domain_overlaps[0]['field'], 'domain')
        self.assertEqual(domain_overlaps[0]['count'], 1)

    def test_02_detect_overlap_intersection_values(self):
        """测试：交集值正确"""
        overlaps = self.detector.detect_overlaps(role_id=996)
        domain_overlaps = [o for o in overlaps if o['field'] == 'domain']
        rule = domain_overlaps[0]['rules'][0]
        self.assertEqual(sorted(rule['intersection']), [3, 4, 5])

    def test_03_no_overlap_for_different_field(self):
        """测试：不同字段不重叠"""
        overlaps = self.detector.detect_overlaps(role_id=996)
        status_overlaps = [o for o in overlaps if o['field'] == 'status']
        self.assertEqual(len(status_overlaps), 0)

    def test_04_product_no_overlap(self):
        """测试：product dim_scope 没有匹配的 rule（不重叠）"""
        overlaps = self.detector.detect_overlaps(role_id=996)
        product_overlaps = [o for o in overlaps if o['field'] == 'product']
        self.assertEqual(len(product_overlaps), 0)

    def test_05_has_overlap_quick_check(self):
        """测试：has_overlap 快速检查"""
        self.assertTrue(self.detector.has_overlap(996, 'domain'))
        self.assertFalse(self.detector.has_overlap(996, 'status'))
        self.assertFalse(self.detector.has_overlap(996, 'nonexistent'))

    def test_06_get_overlap_count(self):
        """测试：get_overlap_count 计数"""
        count = self.detector.get_overlap_count(996)
        self.assertEqual(count, 1)  # 只有 domain 字段重叠

    def test_07_get_overlap_summary(self):
        """测试：get_overlap_summary 返回正确摘要"""
        summary = self.detector.get_overlap_summary(996)
        self.assertTrue(summary['has_overlap'])
        self.assertEqual(summary['count'], 1)
        self.assertIn('domain', summary['fields'])

    def test_08_no_overlap_when_no_dim_scopes(self):
        """测试：没有 dim_scope 时不重叠"""
        # 清理 dim_scope 但保留 rule
        conn = sqlite3.connect(self.detector._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 996")
        conn.commit()
        try:
            overlaps = self.detector.detect_overlaps(996)
            self.assertEqual(len(overlaps), 0)
        finally:
            # 恢复
            cursor.execute("""
                INSERT INTO role_dimension_scopes
                (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (996, 'domain', json.dumps([1, 2, 3, 4, 5]), 1, 'include', None))
            cursor.execute("""
                INSERT INTO role_dimension_scopes
                (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (996, 'product', json.dumps([10]), 1, 'include', None))
            conn.commit()
            conn.close()

    def test_09_no_overlap_when_no_rules(self):
        """测试：没有 rule 时不重叠"""
        # 清理 rules 但保留 dim_scope
        conn = sqlite3.connect(self.detector._db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM permission_rules WHERE role_id = 996")
        conn.commit()
        try:
            overlaps = self.detector.detect_overlaps(996)
            self.assertEqual(len(overlaps), 0)
        finally:
            # 恢复
            cursor.execute("""
                INSERT INTO permission_rules
                (role_id, resource_type, condition, permission_level, is_denied,
                 inherit_to_children, propagate_to_parents, analysis_mode,
                 created_at, created_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
            """, (
                996, 'domain',
                json.dumps({'field': 'domain', 'operator': 'in', 'value': [3, 4, 5, 6]}),
                'read', 0, 1, 0, 'value', 1,
            ))
            cursor.execute("""
                INSERT INTO permission_rules
                (role_id, resource_type, condition, permission_level, is_denied,
                 inherit_to_children, propagate_to_parents, analysis_mode,
                 created_at, created_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
            """, (
                996, 'domain',
                json.dumps({'field': 'status', 'operator': 'eq', 'value': 'active'}),
                'read', 0, 1, 0, 'value', 1,
            ))
            conn.commit()
            conn.close()

    def test_10_feature_flag_disable(self):
        """测试：Feature flag 关闭时不检测"""
        set_flag('ENABLE_DUP_CONFIG_WARNING', False)
        try:
            overlaps = self.detector.detect_overlaps(996)
            self.assertEqual(overlaps, [])
        finally:
            set_flag('ENABLE_DUP_CONFIG_WARNING', True)

    def test_11_empty_role_id(self):
        """测试：不存在的 role 返回空"""
        overlaps = self.detector.detect_overlaps(99999)
        self.assertEqual(overlaps, [])

    def test_12_resource_type_filter(self):
        """测试：按 resource_type 过滤"""
        overlaps = self.detector.detect_overlaps(996, resource_type='domain')
        self.assertGreater(len(overlaps), 0)

    def test_13_intersection_with_fully_overlap(self):
        """测试：完全重叠的情况"""
        # 添加一条 rule 1, 2, 3, 4, 5 - 与 dim_scope 完全重叠
        conn = sqlite3.connect(self.detector._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO permission_rules
            (role_id, resource_type, condition, permission_level, is_denied,
             inherit_to_children, propagate_to_parents, analysis_mode,
             created_at, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, datetime('now'))
        """, (
            996, 'domain',
            json.dumps({'field': 'domain', 'operator': 'in', 'value': [1, 2, 3, 4, 5]}),
            'read', 0, 1, 0, 'value', 1,
        ))
        conn.commit()
        try:
            overlaps = self.detector.detect_overlaps(996)
            domain = next(o for o in overlaps if o['field'] == 'domain')
            # 应该有 2 条 rule（之前 1 条 + 这次 1 条）
            self.assertEqual(domain['count'], 2)
        finally:
            cursor.execute(
                "DELETE FROM permission_rules WHERE role_id = 996 AND condition LIKE '%1, 2, 3, 4, 5%'"
            )
            conn.commit()
            conn.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
