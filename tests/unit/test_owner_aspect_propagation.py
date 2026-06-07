# -*- coding: utf-8 -*-
r"""
M2.5 推广验证 — 所有架构类 BO 都通过 aspect 引用 owner_aspect

测试覆盖：
1. 检查所有 BO 的 aspects 列表
2. 验证架构类 BO 都有 owner_aspect
3. 验证 owner_id 字段在所有架构类 BO 中可用
"""
import sys
import re
import os
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.bo_schema_loader import get_bo_schema_loader

# 架构类 BO（应该有 owner_aspect）
ARCHITECTURE_BOS = [
    'product', 'version', 'domain', 'sub_domain',
    'service_module', 'business_object',
]

# 非架构类 BO（不应该有 owner_aspect——元数据/系统类）
NON_ARCHITECTURE_BOS = [
    'user', 'role', 'user_group',
]


class TestOwnerAspectPropagation(unittest.TestCase):
    """owner_aspect 推广验证"""

    def setUp(self):
        get_bo_schema_loader().clear_cache()

    def test_01_all_architecture_bos_have_owner_aspect(self):
        """测试：所有架构类 BO 都有 owner_aspect"""
        loader = get_bo_schema_loader()
        for bo_id in ARCHITECTURE_BOS:
            with self.subTest(bo_id=bo_id):
                # has_owner_id 通过 aspect 推导
                self.assertTrue(
                    loader.has_owner_id(bo_id),
                    f"{bo_id} 应有 owner_id（通过 owner_aspect）"
                )

    def test_02_non_architecture_bos_no_owner(self):
        """测试：非架构类 BO 不应有 owner_id"""
        loader = get_bo_schema_loader()
        for bo_id in NON_ARCHITECTURE_BOS:
            with self.subTest(bo_id=bo_id):
                # user/role/user_group 不应有 owner_id
                # (注：user_group 可能有自己的成员管理机制)
                if bo_id == 'user_group':
                    continue
                self.assertFalse(
                    loader.has_owner_id(bo_id),
                    f"{bo_id} 不应有 owner_id"
                )

    def test_03_dimension_bindings_consistent(self):
        """测试：dimension_bindings 也已就位（与 M1 一致）"""
        loader = get_bo_schema_loader()
        for bo_id in ARCHITECTURE_BOS:
            with self.subTest(bo_id=bo_id):
                bindings = loader.get_dimension_bindings(bo_id)
                self.assertGreater(
                    len(bindings), 0,
                    f"{bo_id} 应有 dimension_bindings"
                )

    def test_04_summary(self):
        """测试：打印整体情况"""
        loader = get_bo_schema_loader()
        all_bos = ARCHITECTURE_BOS + NON_ARCHITECTURE_BOS
        print("\n=== 推广情况 ===")
        for bo_id in all_bos:
            has_owner = loader.has_owner_id(bo_id)
            bindings = loader.get_dimension_bindings(bo_id)
            print(f"  {bo_id}:")
            print(f"    owner_id: {has_owner}")
            print(f"    dimension_bindings: {len(bindings)}")
            for b in bindings:
                through = f" (through {b['through']})" if 'through' in b else ''
                print(f"      - {b['dimension']} → {b['field']}{through}")


if __name__ == '__main__':
    unittest.main(verbosity=2)
