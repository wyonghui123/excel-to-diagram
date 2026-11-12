# -*- coding: utf-8 -*-
r"""
M1.4 单元测试 — Runtime Dimension Resolver

测试覆盖：
1. 用户角色查询
2. 角色维度范围查询
3. 完整 resolve 流程
4. 公共维度跨 BO 应用
5. dimension_values 解析
6. 多跳关联字段解析
7. Feature flag 控制
8. 空角色列表
9. 不存在的 BO
10. BO 级覆盖（bo_id != NULL）

通过 test.py 入口运行：
    python d:\filework\test.py --file d:\filework\excel-to-diagram\tests\unit\test_runtime_dimension_resolver.py
"""
import sys
import unittest

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.feature_flags import set_flag, clear_cache
from meta.core.perm_cache import get_permission_cache
from meta.core.runtime_dimension_resolver import RuntimeDimensionResolver
from meta.core.bo_schema_loader import get_bo_schema_loader
from meta.tests.factories._dimension_scope_engine_helpers import make_runtime_resolver_ds


class TestRuntimeDimensionResolver(unittest.TestCase):
    """Runtime Dimension Resolver 单元测试

    [FIX 2026-11-07] 原用例直连真实 meta/architecture.db 并写入 roles /
    role_dimension_scopes (v070 已重命名为 permission_sets /
    permission_set_dimension_scopes), 属迁移遗留 → 全部 error。
    改为自播种临时库, 表结构对齐当前模型 (含 bo_id), 断言逻辑不变。
    """

    @classmethod
    def setUpClass(cls):
        """测试前置：准备临时库 (permission_set 999 / user 1)"""
        cls._ds_gen = make_runtime_resolver_ds()
        cls._ds = next(cls._ds_gen)
        cls.resolver = RuntimeDimensionResolver(db_path=cls._ds.db_path)
        cls.db_path = cls._ds.db_path
        cls.test_role_id = 999

    @classmethod
    def tearDownClass(cls):
        """测试后置：关闭并删除临时库"""
        cls._ds_gen.close()
        get_permission_cache().clear()

    def setUp(self):
        """每个测试前清空缓存"""
        clear_cache()
        get_permission_cache().clear()
        get_bo_schema_loader().clear_cache()

    def test_01_get_user_roles(self):
        """测试：用户 → permission_set 查询"""
        roles = self.resolver._get_user_permission_sets(1)
        self.assertIsInstance(roles, list)
        self.assertIn(self.test_role_id, roles)

    def test_02_get_role_dim_scopes(self):
        """测试：角色维度范围查询"""
        scopes = self.resolver._get_role_dim_scopes([self.test_role_id])
        self.assertEqual(len(scopes), 3)
        # domain 是公共维度 (bo_id=NULL)
        domain_scopes = [s for s in scopes if s['dimension_code'] == 'domain']
        self.assertEqual(len(domain_scopes), 1)
        self.assertIsNone(domain_scopes[0]['bo_id'])
        # sub_domain 是 BO 级覆盖
        sd_scopes = [s for s in scopes if s['dimension_code'] == 'sub_domain']
        self.assertEqual(sd_scopes[0]['bo_id'], 'sub_domain')

    def test_03_resolve_basic(self):
        """测试：基本 resolve"""
        conditions = self.resolver.resolve(
            user_id=1, bo_id='domain', role_ids=[999]
        )
        # domain 公共维度 + product 公共维度
        # domain 的 bindings 包含: id(field), version_id(through version), version_id
        self.assertGreater(len(conditions), 0)

    def test_04_public_dimension_cross_bo(self):
        """测试：公共维度跨 BO 应用（核心）

        只有声明了 dimension_bindings 的 BO 才接收公共维度值。
        例如：domain/sub_domain/business_object/service_module 都有 domain 绑定，
        而 version 没有 domain 绑定（它属于 product 维度），所以不应有 domain condition。
        """
        # 声明了 domain 绑定的 BO（应该收到 domain 维度的公共条件）
        bo_with_domain_binding = ['domain', 'sub_domain', 'business_object', 'service_module']
        for bo_id in bo_with_domain_binding:
            conditions = self.resolver.resolve(
                user_id=1, bo_id=bo_id, role_ids=[999]
            )
            domain_conds = [c for c in conditions if c['dimension'] == 'domain']
            self.assertGreater(
                len(domain_conds), 0,
                f"BO {bo_id} 应该有 domain 维度的公共条件"
            )

        # 未声明 domain 绑定的 BO（不应该收到 domain 维度的公共条件）
        bo_without_domain_binding = ['version']  # version 属于 product 维度
        for bo_id in bo_without_domain_binding:
            conditions = self.resolver.resolve(
                user_id=1, bo_id=bo_id, role_ids=[999]
            )
            domain_conds = [c for c in conditions if c['dimension'] == 'domain']
            self.assertEqual(
                len(domain_conds), 0,
                f"BO {bo_id} 不应该有 domain 维度的公共条件（未声明绑定）"
            )

    def test_05_bo_level_override(self):
        """测试：BO 级覆盖（bo_id != NULL）"""
        # sub_domain 的 BO 级覆盖
        conditions = self.resolver.resolve(
            user_id=1, bo_id='sub_domain', role_ids=[999]
        )
        # 应该有 sub_domain 维度的 BO 级覆盖
        sd_conds = [c for c in conditions if c['dimension'] == 'sub_domain']
        self.assertGreater(len(sd_conds), 0)
        self.assertEqual(sd_conds[0]['value'], [100, 200])

    def test_06_dimension_values_parsing(self):
        """测试：dimension_values 解析"""
        # JSON 字符串
        self.assertEqual(self.resolver._parse_dim_values('[1, 2, 3]'), [1, 2, 3])
        # Python 列表
        self.assertEqual(self.resolver._parse_dim_values([1, 2, 3]), [1, 2, 3])
        # None
        self.assertEqual(self.resolver._parse_dim_values(None), [])
        # 空
        self.assertEqual(self.resolver._parse_dim_values(''), [])

    def test_07_multi_hop_field(self):
        """测试：多跳关联字段解析"""
        # 简单字段
        self.assertEqual(
            self.resolver._resolve_field({'field': 'id'}, 'domain'),
            'id'
        )
        # 单跳
        self.assertEqual(
            self.resolver._resolve_field(
                {'field': 'version_id', 'through': 'version'},
                'domain'
            ),
            'version_id'
        )
        # 多跳
        self.assertEqual(
            self.resolver._resolve_field(
                {'field': 'service_module_id', 'through': 'service_module->sub_domain->domain'},
                'business_object'
            ),
            'service_module_id'
        )

    def test_08_feature_flag_disable(self):
        """测试：Feature flag 关闭时 resolve 返回空"""
        set_flag('ENABLE_RUNTIME_RESOLUTION', False)
        try:
            conditions = self.resolver.resolve(
                user_id=1, bo_id='domain', role_ids=[999]
            )
            self.assertEqual(conditions, [])
        finally:
            set_flag('ENABLE_RUNTIME_RESOLUTION', True)

    def test_09_empty_role_ids(self):
        """测试：空角色列表"""
        conditions = self.resolver.resolve(
            user_id=1, bo_id='domain', role_ids=[]
        )
        self.assertEqual(conditions, [])

    def test_10_nonexistent_bo(self):
        """测试：不存在的 BO"""
        conditions = self.resolver.resolve(
            user_id=1, bo_id='non_existent_bo', role_ids=[999]
        )
        self.assertEqual(conditions, [])

    def test_11_dimension_value_in(self):
        """测试：多值用 in 操作符"""
        conditions = self.resolver.resolve(
            user_id=1, bo_id='domain', role_ids=[999]
        )
        # domain 维度有 3 个值，应该用 in
        domain_conds = [c for c in conditions if c['dimension'] == 'domain']
        self.assertEqual(domain_conds[0]['operator'], 'in')
        # product 维度有 1 个值，应该用 eq
        product_conds = [c for c in conditions if c['dimension'] == 'product']
        self.assertEqual(product_conds[0]['operator'], 'eq')

    # ----------------------------------------------------------------
    # FR-016 AC-1: 冗余字段优先（修复 v1.3 实施 Bug）
    # ----------------------------------------------------------------

    def test_12_find_redundant_field_business_object(self):
        """FR-016 AC-1: business_object 的 domain_id 是 stored + db_column，应视为冗余字段

        [FIX 2026-11-07] business_object.yaml 已把 domain_id 从 storage: virtual
        升级为 storage: stored（含 db_column，由 service_module_id 反向推导维护），
        断言随之改为返回 'domain_id'。
        """
        result = self.resolver._find_redundant_field('business_object', 'domain')
        self.assertEqual(
            result, 'domain_id',
            "business_object.domain_id 已落库（stored + db_column），应视为冗余字段"
        )

    def test_13_resolve_field_fallback_main_field(self):
        """FR-016 AC-1: 无冗余字段时使用主字段（向后兼容）

        验证：当 BO 没有目标维度的冗余字段时，_resolve_field 返回 binding 的
        field（主字段），保留 v1.3 行为。用 mock schema 隔离 YAML 演进。
        """
        from unittest.mock import patch, MagicMock

        mock_loader = MagicMock()
        mock_loader.get_bo_schema.return_value = {
            'id': 'test_bo_no_redundant',
            'fields': [
                {'id': 'service_module_id', 'db_column': 'service_module_id'},
            ],
        }
        with patch.object(self.resolver, '_schema_loader', mock_loader):
            result = self.resolver._resolve_field(
                {
                    'dimension': 'domain',
                    'field': 'service_module_id',
                    'through': 'service_module->sub_domain->domain',
                },
                'test_bo_no_redundant',
            )
        # 无 domain_id 冗余字段 → fallback 到主字段 service_module_id
        self.assertEqual(result, 'service_module_id')

    def test_14_find_redundant_field_nonexistent_bo(self):
        """FR-016 AC-1: 不存在的 BO 返回 None"""
        result = self.resolver._find_redundant_field('non_existent_bo', 'domain')
        self.assertIsNone(result)

    def test_15_resolve_field_uses_redundant_field(self):
        """FR-016 AC-1: 有冗余字段时优先用冗余字段

        验证：当 BO 有目标维度的冗余字段（实际 db_column），_resolve_field 应
        优先返回冗余字段名。
        """
        from unittest.mock import patch, MagicMock

        # 构造一个 mock BO schema，模拟"有冗余字段"场景
        mock_schema = {
            'id': 'test_bo_with_redundant',
            'fields': [
                {
                    'id': 'domain_id',
                    'db_column': 'domain_id',
                    'storage': 'persistent',  # 不是 virtual
                },
                {
                    'id': 'service_module_id',
                    'db_column': 'service_module_id',
                },
            ],
        }
        mock_loader = MagicMock()
        mock_loader.get_bo_schema.return_value = mock_schema

        with patch.object(self.resolver, '_schema_loader', mock_loader):
            result = self.resolver._resolve_field(
                {
                    'dimension': 'domain',
                    'field': 'service_module_id',
                    'through': 'service_module->sub_domain->domain',
                },
                'test_bo_with_redundant',
            )
            # 优先用冗余字段 domain_id
            self.assertEqual(result, 'domain_id')

    # ----------------------------------------------------------------
    # FR-016 AC-2: JOIN 路径生成（Q9 字符串语法）
    # ----------------------------------------------------------------

    def test_16_build_join_path_parent_child(self):
        """FR-016 AC-2: parent_child 路径（`->`）解析"""
        joins = self.resolver._build_join_path(
            'service_module->sub_domain->domain'
        )
        # 跳过第一个（bo_id 自身 service_module）
        self.assertEqual(len(joins), 2)
        self.assertEqual(joins[0]['target_bo'], 'sub_domain')
        self.assertEqual(joins[0]['target_table'], 'sub_domains')
        self.assertEqual(joins[0]['alias'], 'sd')
        self.assertEqual(joins[0]['path_type'], 'parent_child')
        self.assertEqual(joins[0]['level'], 1)
        self.assertEqual(joins[1]['target_bo'], 'domain')
        self.assertEqual(joins[1]['target_table'], 'domains')
        self.assertEqual(joins[1]['alias'], 'd')
        self.assertEqual(joins[1]['level'], 2)

    def test_17_build_join_path_association(self):
        """FR-016 AC-2: association 路径（`-->`）解析"""
        joins = self.resolver._build_join_path(
            'order-->customer-->region'
        )
        self.assertEqual(len(joins), 2)
        self.assertEqual(joins[0]['target_bo'], 'customer')
        self.assertEqual(joins[0]['path_type'], 'association')
        self.assertEqual(joins[1]['target_bo'], 'region')
        self.assertEqual(joins[1]['path_type'], 'association')

    def test_18_build_join_path_mixed(self):
        """FR-016 AC-2: 混合 parent_child + association 路径"""
        joins = self.resolver._build_join_path(
            'business_object->sub_domain-->manager'
        )
        self.assertEqual(len(joins), 2)
        self.assertEqual(joins[0]['target_bo'], 'sub_domain')
        self.assertEqual(joins[0]['path_type'], 'parent_child')
        self.assertEqual(joins[1]['target_bo'], 'manager')
        self.assertEqual(joins[1]['path_type'], 'association')

    def test_19_resolve_field_with_joins_no_redundant(self):
        """FR-016 AC-2: 无冗余字段时 _resolve_field_with_joins 返回 JOIN 路径"""
        from unittest.mock import patch, MagicMock

        mock_loader = MagicMock()
        mock_loader.get_bo_schema.return_value = {
            'id': 'test_bo_no_redundant',
            'fields': [
                {'id': 'service_module_id', 'db_column': 'service_module_id'},
            ],
        }
        with patch.object(self.resolver, '_schema_loader', mock_loader):
            result = self.resolver._resolve_field_with_joins(
                {
                    'dimension': 'domain',
                    'field': 'service_module_id',
                    'through': 'service_module->sub_domain->domain',
                },
                'test_bo_no_redundant',
            )
        self.assertIsNotNone(result)
        self.assertEqual(result['field'], 'service_module_id')
        # 无 domain_id db_column 冗余字段 → 返回 JOIN
        self.assertEqual(len(result['joins']), 2)
        self.assertEqual(result['joins'][0]['target_bo'], 'sub_domain')
        self.assertEqual(result['joins'][1]['target_bo'], 'domain')

    def test_20_resolve_field_with_joins_redundant(self):
        """FR-016 AC-2: 有冗余字段时 _resolve_field_with_joins 返回 joins=[]"""
        from unittest.mock import patch, MagicMock

        mock_schema = {
            'id': 'test_bo',
            'fields': [
                {
                    'id': 'domain_id',
                    'db_column': 'domain_id',
                    'storage': 'persistent',
                },
                {
                    'id': 'service_module_id',
                    'db_column': 'service_module_id',
                },
            ],
        }
        mock_loader = MagicMock()
        mock_loader.get_bo_schema.return_value = mock_schema

        with patch.object(self.resolver, '_schema_loader', mock_loader):
            result = self.resolver._resolve_field_with_joins(
                {
                    'dimension': 'domain',
                    'field': 'service_module_id',
                    'through': 'service_module->sub_domain->domain',
                },
                'test_bo',
            )
            self.assertEqual(result['field'], 'domain_id')  # 用了冗余字段
            self.assertEqual(result['joins'], [])  # 无需 JOIN

    def test_21_to_table_name(self):
        """辅助方法：BO 标识符 → 表名复数化"""
        self.assertEqual(
            self.resolver._to_table_name('sub_domain'),
            'sub_domains',
        )
        self.assertEqual(
            self.resolver._to_table_name('business_object'),
            'business_objects',
        )
        self.assertEqual(
            self.resolver._to_table_name('category'),
            'categories',  # y -> ies
        )
        self.assertEqual(
            self.resolver._to_table_name('users'),
            'users',  # 已 s 结尾不变
        )


if __name__ == '__main__':
    unittest.main(verbosity=2)
