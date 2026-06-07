# -*- coding: utf-8 -*-
r"""
M1.5 集成测试 — Runtime Dimension Resolver 端到端

测试覆盖：
1. 数据库迁移正确性（bo_id 列已添加）
2. 公共维度数据持久化
3. 跨 BO 完整流程
4. 性能基准（动态展开 <50ms）
5. 与 BO schema 加载器集成

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\integration\test_data_permission_runtime.py
"""
import sys
import os
import time
import json
import sqlite3
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.core.runtime_dimension_resolver import get_runtime_dimension_resolver


class TestDataPermissionRuntime(unittest.TestCase):
    """数据权限运行时集成测试"""

    @classmethod
    def setUpClass(cls):
        cls.resolver = get_runtime_dimension_resolver()
        cls.db_path = cls.resolver._db_path
        cls.test_role_id = 998
        cls._setup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def _setup_test_data(cls):
        """注入集成测试数据"""
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()

        # 创建测试角色
        cursor.execute("SELECT id FROM roles WHERE id = 998 LIMIT 1")
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO roles (id, name, code, description, is_system)
                VALUES (998, 'Integration Test Role', 'integ_test', 'Integration test', 0)
            """)

        # 清理
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 998")

        # 注入：4 个维度的公共 scope
        scopes = [
            ('domain', json.dumps([1, 2, 3, 4, 5]), None),
            ('sub_domain', json.dumps([10, 20]), None),
            ('product', json.dumps([1]), None),
            ('version', json.dumps([100]), None),
        ]
        for dim, vals, bo_id in scopes:
            cursor.execute("""
                INSERT INTO role_dimension_scopes
                (role_id, dimension_code, dimension_values, inherit_children, scope_mode, bo_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (998, dim, vals, 1, 'include', bo_id))

        conn.commit()
        conn.close()

    @classmethod
    def _cleanup_test_data(cls):
        """清理"""
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM role_dimension_scopes WHERE role_id = 998")
        cursor.execute("DELETE FROM roles WHERE id = 998")
        conn.commit()
        conn.close()

    def setUp(self):
        clear_cache()
        get_bo_schema_loader().clear_cache()
        clear_cache.__self__ if hasattr(clear_cache, '__self__') else None

    def test_01_migration_applied(self):
        """测试：数据库迁移成功（bo_id 列已存在）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(role_dimension_scopes)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        self.assertIn('bo_id', columns, "bo_id 列必须已存在")

    def test_02_test_role_has_scopes(self):
        """测试：测试角色有 4 个公共维度 scope"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dimension_code, bo_id FROM role_dimension_scopes
            WHERE role_id = 998
        """)
        rows = cursor.fetchall()
        conn.close()
        self.assertEqual(len(rows), 4)
        # 全部是公共维度（bo_id=NULL）
        for _, bo_id in rows:
            self.assertIsNone(bo_id)

    def test_03_cross_bo_resolution_full_flow(self):
        """测试：跨 BO 完整 resolve 流程"""
        bo_ids = ['domain', 'sub_domain', 'business_object', 'service_module', 'version']
        for bo_id in bo_ids:
            conditions = self.resolver.resolve(
                user_id=1, bo_id=bo_id, role_ids=[998]
            )
            # 每个 BO 都应该至少有一些 condition
            # （取决于 BO 声明的 bindings）
            self.assertIsInstance(conditions, list)
            # 每个 condition 应有 field, operator, value, source, dimension
            for c in conditions:
                self.assertIn('field', c)
                self.assertIn('operator', c)
                self.assertIn('value', c)
                self.assertIn('source', c)
                self.assertIn('dimension', c)

    def test_04_sub_domain_scope_applied(self):
        """测试：sub_domain 维度的公共 scope 正确应用到相关 BO"""
        # sub_domain 维度应该应用到：sub_domain 自身 + business_object + service_module
        # （因为它们都声明了 sub_domain 绑定）
        for bo_id in ['sub_domain', 'business_object', 'service_module']:
            conditions = self.resolver.resolve(
                user_id=1, bo_id=bo_id, role_ids=[998]
            )
            sd_conds = [c for c in conditions if c['dimension'] == 'sub_domain']
            self.assertGreater(
                len(sd_conds), 0,
                f"BO {bo_id} 应该收到 sub_domain 维度的公共条件"
            )
            # 应该是 in 操作符（多值）
            self.assertEqual(sd_conds[0]['operator'], 'in')
            self.assertEqual(sorted(sd_conds[0]['value']), [10, 20])

    def test_05_version_dimension_isolation(self):
        """测试：version 维度的公共 scope 只应用于声明了 version 绑定的 BO

        通过多跳关联（sub_domain → domain → version），version 维度也会
        间接应用到 sub_domain、business_object、service_module（它们都声明了
        通过 domain 关联到 version 的 binding）。
        """
        # 显式或通过多跳声明了 version 绑定的 BO，应该收到 version 条件
        for bo_id in ['domain', 'sub_domain', 'business_object', 'service_module']:
            conditions = self.resolver.resolve(
                user_id=1, bo_id=bo_id, role_ids=[998]
            )
            v_conds = [c for c in conditions if c['dimension'] == 'version']
            self.assertGreater(
                len(v_conds), 0,
                f"BO {bo_id} 应该有 version 维度的条件（直接或通过多跳）"
            )

    def test_06_performance_benchmark(self):
        """测试：性能基准（动态展开 <50ms）"""
        iterations = 100
        start = time.time()
        for _ in range(iterations):
            self.resolver.resolve(
                user_id=1, bo_id='domain', role_ids=[998]
            )
        elapsed = time.time() - start
        avg_ms = (elapsed / iterations) * 1000
        print(f"\n  平均每次 resolve 耗时: {avg_ms:.2f}ms")
        self.assertLess(avg_ms, 50, f"性能不达标: {avg_ms:.2f}ms >= 50ms")

    def test_07_bo_schema_loader_integration(self):
        """测试：与 BO schema 加载器集成"""
        loader = get_bo_schema_loader()
        # 验证 dimension_bindings 加载正确
        for bo_id in ['domain', 'sub_domain', 'business_object', 'service_module', 'version']:
            bindings = loader.get_dimension_bindings(bo_id)
            self.assertIsInstance(bindings, list)
            # 每个 binding 应有 dimension 和 field
            for b in bindings:
                self.assertIn('dimension', b)
                self.assertIn('field', b)

    def test_08_feature_flag_disables_resolution(self):
        """测试：Feature flag 关闭时禁用运行时解析"""
        set_flag('ENABLE_RUNTIME_RESOLUTION', False)
        try:
            conditions = self.resolver.resolve(
                user_id=1, bo_id='domain', role_ids=[998]
            )
            self.assertEqual(conditions, [], "Feature flag 关闭时应返回空")
        finally:
            set_flag('ENABLE_RUNTIME_RESOLUTION', True)

    def test_09_resolution_consistency(self):
        """测试：相同输入应产生相同结果（确定性）"""
        results = []
        for _ in range(3):
            conditions = self.resolver.resolve(
                user_id=1, bo_id='domain', role_ids=[998]
            )
            results.append(json.dumps(conditions, sort_keys=True, ensure_ascii=False))
        self.assertEqual(
            results[0], results[1],
            "第 1 次和第 2 次结果不一致"
        )
        self.assertEqual(
            results[1], results[2],
            "第 2 次和第 3 次结果不一致"
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
