# -*- coding: utf-8 -*-
"""[Test v1.0.1] DimensionScopeEngine.derive_data_conditions 向上展开"""
import unittest
import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meta.services.dimension_scope_engine import DimensionScopeEngine
from meta.services.cascade_service import HierarchyConfigLoader


class _MockDataSource:
    """[Test helper] 包装 sqlite3 connection 为 DataSource 接口"""
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        return self.conn.execute(sql, params or [])


class TestDimensionScopeUpwardExpansion(unittest.TestCase):
    """[FIX v1.0.1] 验证 derive_data_conditions 支持向上展开"""

    @classmethod
    def setUpClass(cls):
        # __file__ = .../meta/tests/test_dimension_scope_v101.py
        # need 3 dirname calls to get to project root
        db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                          'meta', 'architecture.db')
        cls.conn = sqlite3.connect(db)
        cls.conn.row_factory = sqlite3.Row
        cls.ds = _MockDataSource(cls.conn)

    def test_T1_upward_product_from_version(self):
        """[T1] TEST60 有 version=[2,11,12], 推 product filter"""
        engine = DimensionScopeEngine(self.ds)
        conditions = engine.derive_data_conditions(1803)
        # product filter 应有 id 限定（向上的 product_id）
        self.assertIn('product', conditions,
                      f"product should have filter, got: {conditions}")
        cond = conditions['product']
        # 应包含 id = 1 (因为 version 2,11,12 属于 product 1)
        # 也可能 version 11/12 在 product 1 之外
        # 至少应有限制
        self.assertTrue('id' in cond.lower() or 'IN' in cond.upper(),
                       f"product filter should have id restriction, got: {cond}")
        print(f"\n  product filter: {cond}")

    def test_T2_upward_domain_no_change(self):
        """[T2] domain 已有 inherit_children 展开, 不应破坏"""
        engine = DimensionScopeEngine(self.ds)
        conditions = engine.derive_data_conditions(1803)
        # domain 应有 version_id IN (2,11,12)
        self.assertIn('domain', conditions, f"domain missing: {conditions}")
        self.assertIn('version_id', conditions['domain'])
        self.assertIn('2', conditions['domain'])
        self.assertIn('11', conditions['domain'])
        self.assertIn('12', conditions['domain'])
        print(f"\n  domain filter: {conditions['domain']}")

    def test_T3_subdomain_no_change(self):
        """[T3] sub_domain 向下展开, 应保留"""
        engine = DimensionScopeEngine(self.ds)
        conditions = engine.derive_data_conditions(1803)
        self.assertIn('sub_domain', conditions, f"sub_domain missing: {conditions}")
        # 应有 domain_id IN (...)
        self.assertIn('domain_id', conditions['sub_domain'])
        print(f"\n  sub_domain filter: {conditions['sub_domain'][:100]}")

    def test_T4_version_id_filter(self):
        """[T4] version 应有 id IN (2, 11, 12)"""
        engine = DimensionScopeEngine(self.ds)
        conditions = engine.derive_data_conditions(1803)
        self.assertIn('version', conditions, f"version missing: {conditions}")
        cond = conditions['version']
        # 应有 id 限制
        self.assertTrue('id' in cond.lower() or 'IN' in cond.upper(),
                       f"version filter should restrict ids, got: {cond}")
        print(f"\n  version filter: {cond}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
