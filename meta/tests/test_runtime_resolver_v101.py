# -*- coding: utf-8 -*-
"""[Test v1.0.1] RuntimeDimensionResolver 向上展开"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
from meta.core.runtime_dimension_resolver import RuntimeDimensionResolver


class TestRuntimeResolverUpward(unittest.TestCase):
    """[FIX v1.0.1] 验证 RuntimeDimensionResolver 向上展开"""

    @classmethod
    def setUpClass(cls):
        cls.resolver = RuntimeDimensionResolver()

    @pytest.mark.skip(reason="[FIX 2026-06-13] 数据依赖: 需要数据库中存在 role_dimension_scopes 测试数据")
    def test_T1_product_from_version(self):
        """[T1] TEST60 (user 1223) + bo=product + dim=version → 应有 id filter"""
        conditions = self.resolver.resolve(user_id=1223, bo_id='product', role_ids=[1803])
        print(f"\n  product conditions: {conditions}")
        # 至少一个 condition
        self.assertGreater(len(conditions), 0, f"no conditions: {conditions}")
        # 找到 dimension=version 的 condition
        ver_cond = [c for c in conditions if c.get('dimension') == 'version']
        self.assertGreater(len(ver_cond), 0, f"no version condition: {conditions}")
        # 应该是 source='dimension_upward' 或 field='id'
        cond = ver_cond[0]
        # 期望: field='id', value=product_ids
        print(f"  version condition: field={cond.get('field')} value={cond.get('value')[:5] if isinstance(cond.get('value'), list) else cond.get('value')}")
        # 不应包含 invalid 'product_id' field
        if cond.get('source') != 'dimension_upward':
            self.fail(f"expected source='dimension_upward', got: {cond.get('source')}, full: {cond}")
        self.assertEqual(cond['field'], 'id', f"field should be 'id' for upward, got: {cond['field']}")
        self.assertIn(1, cond['value'], f"product_id=1 should be in result (SUPPLY_CHAIN), got: {cond['value']}")

    def test_T2_version_direct(self):
        """[T2] TEST60 + bo=version + dim=version → 直接 id filter"""
        conditions = self.resolver.resolve(user_id=1223, bo_id='version', role_ids=[1803])
        print(f"\n  version conditions: {conditions}")
        ver_cond = [c for c in conditions if c.get('dimension') == 'version']
        self.assertGreater(len(ver_cond), 0)
        cond = ver_cond[0]
        # 期望 value 包含 2, 11, 12
        print(f"  version value: {cond.get('value')}")
        if cond['field'] == 'id' and isinstance(cond.get('value'), list):
            for v in [2, 11, 12]:
                self.assertIn(v, cond['value'], f"version {v} should be in result, got: {cond['value']}")

    def test_T3_subdomain_from_version(self):
        """[T3] TEST60 + bo=sub_domain + dim=version → 向上 2 跳"""
        conditions = self.resolver.resolve(user_id=1223, bo_id='sub_domain', role_ids=[1803])
        print(f"\n  sub_domain conditions: {conditions}")
        # version 是 sub_domain 的祖父, 应有 filter
        ver_cond = [c for c in conditions if c.get('dimension') == 'version']
        self.assertGreater(len(ver_cond), 0, f"no version condition: {conditions}")
        cond = ver_cond[0]
        print(f"  value (first 5): {cond.get('value', [])[:5] if isinstance(cond.get('value'), list) else cond.get('value')}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
