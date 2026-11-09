# -*- coding: utf-8 -*-
"""[Test v1.0.1] RuntimeDimensionResolver 向上展开

[FIX 2026-11-07] 原用例直连真实 meta/architecture.db 的 permission_set 1803 (TEST60),
该运行数据在当前库中已不存在 (permission_set_dimension_scopes 无 1803 记录,
org_members 也无 user 1223) → resolve() 恒得 [] → T2/T3 恒失败。
改为自播种临时 SQLite (factories/ 白名单惯例, 与 test_org_dimension_contracts.py 同拓扑),
使断言确定性可复现; 断言逻辑与原用例保持一致。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import pytest
from meta.core.perm_cache import get_permission_cache
from meta.core.runtime_dimension_resolver import RuntimeDimensionResolver
from meta.tests.factories._dimension_scope_engine_helpers import (
    make_dim_scope_engine_ds,
    seed_v101_upward_expansion,
)

PS_ID = 1803
USER_ID = 1223


class TestRuntimeResolverUpward(unittest.TestCase):
    """[FIX v1.0.1] 验证 RuntimeDimensionResolver 向上展开"""

    @classmethod
    def setUpClass(cls):
        cls._ds_gen = make_dim_scope_engine_ds()
        cls._ds = next(cls._ds_gen)
        seed_v101_upward_expansion(cls._ds)
        # helper 建库时开了 WAL; safe_connect_for_read 会做 DB 级
        # PRAGMA journal_mode=DELETE, WAL 持有时会 'database is locked' → 先切回 DELETE
        cls._ds.execute("PRAGMA journal_mode=DELETE")
        cls.resolver = RuntimeDimensionResolver(db_path=cls._ds.db_path)

    @classmethod
    def tearDownClass(cls):
        cls._ds_gen.close()  # 触发 finally: 关闭连接 + 删除临时库
        get_permission_cache().clear()

    def setUp(self):
        # 全局单例缓存: 避免测试间串味 (key 不含 db_path)
        get_permission_cache().clear()

    @pytest.mark.skip(
        reason="product.yaml 的 dimension_bindings 仅声明 product (无 version 绑定点), "
               "运行时 resolver 不会为 bo=product + dim=version 走到向上展开"
    )
    def test_T1_product_from_version(self):
        """[T1] TEST60 (user 1223) + bo=product + dim=version → 应有 id filter"""
        conditions = self.resolver.resolve(user_id=USER_ID, bo_id='product', role_ids=[PS_ID])
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
        conditions = self.resolver.resolve(user_id=USER_ID, bo_id='version', role_ids=[PS_ID])
        print(f"\n  version conditions: {conditions}")
        ver_cond = [c for c in conditions if c.get('dimension') == 'version']
        self.assertGreater(len(ver_cond), 0, f"no version condition: {conditions}")
        cond = ver_cond[0]
        # 期望 value 包含 2, 11, 12
        print(f"  version value: {cond.get('value')}")
        self.assertEqual(cond['field'], 'id', f"version binding should be id, got: {cond}")
        for v in [2, 11, 12]:
            self.assertIn(v, cond['value'], f"version {v} should be in result, got: {cond['value']}")

    def test_T3_subdomain_from_version(self):
        """[T3] TEST60 + bo=sub_domain + dim=version → 向上 2 跳"""
        conditions = self.resolver.resolve(user_id=USER_ID, bo_id='sub_domain', role_ids=[PS_ID])
        print(f"\n  sub_domain conditions: {conditions}")
        # version 是 sub_domain 的祖父, 应有 filter
        ver_cond = [c for c in conditions if c.get('dimension') == 'version']
        self.assertGreater(len(ver_cond), 0, f"no version condition: {conditions}")
        cond = ver_cond[0]
        self.assertEqual(cond['value'], [2, 11, 12], f"unexpected value: {cond}")
        # sub_domain 有冗余列 version_id → 直接用它, 无需 JOIN (FR-016 AC-1)
        self.assertEqual(cond['field'], 'version_id', f"expected redundant field version_id, got: {cond}")
        self.assertEqual(cond['joins'], [], f"redundant field should not need joins: {cond}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
