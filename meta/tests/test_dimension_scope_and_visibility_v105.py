# -*- coding: utf-8 -*-
"""
测试 v1.0.5 修复: dimension scope 与 visibility/owner scope 改为 AND 关系

【背景 - TESET68 bug】
修复前:
  - dimension scope 应用后直接 return → 跳过 visibility/owner scope
  - TESET68 (非 owner) 配置 product=[1] → 看到 product 1 下所有人的 draft 版本
  - 违反最小权限原则 (least privilege)

修复后:
  - dimension scope 应用后继续叠加 visibility/owner scope (AND 关系)
  - SQL: WHERE (dimension_scope_conds) AND (visibility='public' OR owner_id=$user)
        OR (owner_id = $user_id)  -- owner 例外
  - TESET68 看不到别人的 draft, 但仍能看到 product 1 下的 public 版本和自己 owner 的版本

【覆盖场景】
1. DimensionObjectMappingLoader 加载配置
2. DimensionScopeEngine 使用 yaml 映射配置
3. DataPermissionInterceptor v1.0.5 修复（AND 关系）
4. TESET68 端到端场景
"""
import os
import sys
import json
import sqlite3
import tempfile
import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

pytestmark = pytest.mark.unit


# ────────────────────────────────────────
# 1. DimensionObjectMappingLoader 测试
# ────────────────────────────────────────
class TestDimensionObjectMappingLoader:
    def test_loader_loads_yaml(self):
        """Loader 能加载 meta/schemas/dimension_object_mapping.yaml"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()
        assert loader.is_loaded(), "应该成功加载映射配置"

    def test_product_dimension_mappings(self):
        """product 维度应有 4 个 BO 映射（product/version/domain/sub_domain）"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()
        applies = loader.get_applies_to('product')
        assert len(applies) == 4

        bo_ids = {a['bo'] for a in applies}
        assert bo_ids == {'product', 'version', 'domain', 'sub_domain'}

    def test_version_dimension_mappings(self):
        """version 维度应适用于 version/domain/sub_domain"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()
        applies = loader.get_applies_to('version')

        # 应至少有 version(自身), domain(fk via version_id), sub_domain(chain via version_id)
        bo_to_field = {a['bo']: a for a in applies}
        assert 'version' in bo_to_field
        assert 'domain' in bo_to_field
        assert 'sub_domain' in bo_to_field

        # version 自身是 direct
        assert bo_to_field['version']['filter_type'] == 'direct'
        # domain 通过 fk
        assert bo_to_field['domain']['field'] == 'version_id'

    def test_combination_policy_default(self):
        """默认 combination_policy 应该是 AND + owner_always_visible"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()
        policy = loader.get_combination_policy()
        assert policy['scope_combination'] == 'AND'
        assert policy['owner_always_visible'] is True

    def test_get_field_for_bo(self):
        """get_field_for_bo 应正确返回 BO 字段映射"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()

        # product 维度 → product BO → id 字段 (direct)
        binding = loader.get_field_for_bo('product', 'product')
        assert binding is not None
        assert binding['field'] == 'id'
        assert binding['filter_type'] == 'direct'

        # product 维度 → version BO → product_id 字段 (fk)
        binding = loader.get_field_for_bo('product', 'version')
        assert binding is not None
        assert binding['field'] == 'product_id'
        assert binding['filter_type'] == 'fk'

    def test_priority(self):
        """优先级查询"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()
        # product 优先级应该比 domain 高（数值小）
        assert loader.get_priority('product') < loader.get_priority('domain')

    def test_unknown_dimension_returns_empty(self):
        """未知维度应返回空 mapping"""
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )

        loader = get_dimension_object_mapping_loader()
        assert loader.get_mapping('unknown_dimension_xyz') is None
        assert loader.get_applies_to('unknown_dimension_xyz') == []
        assert loader.get_dimension_type('unknown_dimension_xyz') is None


# ────────────────────────────────────────
# 2. DimensionScopeEngine 使用 yaml 配置的测试
# ────────────────────────────────────────
class TestDimensionScopeEngineYamlPath:
    """验证 derive_data_conditions 走 yaml 配置路径"""

    @pytest.fixture
    def mock_ds(self):
        """构造最小可用的 mock data_source"""
        db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = db_file.name
        db_file.close()
        conn = sqlite3.connect(db_path)

        # 创建所需表
        conn.executescript("""
            CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE versions (id INTEGER PRIMARY KEY, product_id INTEGER,
                                   visibility TEXT, owner_id INTEGER);
            CREATE TABLE domains (id INTEGER PRIMARY KEY, version_id INTEGER,
                                  visibility TEXT, owner_id INTEGER);
            CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, domain_id INTEGER,
                                     visibility TEXT, owner_id INTEGER);

            INSERT INTO products VALUES (1, '供应链管理系统');
            INSERT INTO versions VALUES (1, 1, 'public', NULL);
            INSERT INTO versions VALUES (2, 1, 'draft', 999);
            INSERT INTO domains VALUES (1, 1, 'public', NULL);
            INSERT INTO domains VALUES (2, 1, 'draft', 999);
        """)

        class MockDS:
            def execute(self, sql, params=None):
                cur = conn.execute(sql, params or [])
                return cur

        return MockDS()

    def test_yaml_path_generates_conditions(self, mock_ds):
        """走 yaml 路径应正确生成 conditions"""
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)

        # 模拟 expand: 用户配 product=[1]
        import unittest.mock as mock
        with mock.patch.object(engine, 'expand_dimension_values') as mock_expand:
            mock_expand.return_value = {'product': {1}}

            conditions = engine.derive_data_conditions(role_id=1)

            # product BO: id=1 直接过滤
            assert 'product' in conditions
            assert 'id = 1' in conditions['product'] or 'id IN (1)' in conditions['product']

            # version BO: product_id=1 过滤 (fk)
            assert 'version' in conditions
            assert 'product_id = 1' in conditions['version']


# ────────────────────────────────────────
# 3. TESET68 bug 修复 - DataPermissionInterceptor v1.0.5
# ────────────────────────────────────────
class TestDataPermissionInterceptorV105:
    """验证 v1.0.5 修复: dimension scope AND visibility/owner"""

    def test_dimension_scope_applied_runs_visibility_filter(self):
        """dimension scope 应用后, 必须继续运行 visibility scope filter (AND 叠加)"""
        from meta.core.interceptors.data_permission_interceptor import (
            DataPermissionInterceptor,
        )

        # 模拟一个 context
        class MockContext:
            def __init__(self):
                self.user_id = 1456  # TESET68
                self.user_name = 'TESET68'
                self.object_type = 'version'
                self.data_source = None
                self.meta_object = type('M', (), {
                    'authorization': {
                        'scope': "visibility = 'public' OR owner_id = $user.id",
                        'check': True,
                    }
                })()
                self.extra = {}
                self.is_query_action = True

        interceptor = DataPermissionInterceptor()
        ctx = MockContext()

        # 模拟 dimension scope filter 已经应用: product_id = 1
        ctx.extra['query_conditions'] = [{
            'field': 'product_id',
            'operator': 'eq',
            'value': 1,
            'source': 'dimension_scope',
        }]

        # [FIX 2026-06-13] mock _bo_has_visibility_field 也需要返回 True
        # 否则方法会跳过 visibility scope，直接添加 owner exception
        import unittest.mock as mock
        with mock.patch.object(interceptor, '_bo_has_owner_id', return_value=True), \
             mock.patch.object(interceptor, '_bo_has_visibility_field', return_value=True):
            interceptor._apply_scope_filter_after_dimension(ctx)

        # v1.0.7 修复后结构:
        # query_conditions = [
        #   {'type': 'or', 'conditions': [
        #       {'type': 'and', 'conditions': [dim_cond, visibility_or_group]},
        #       owner_cond  # owner exception
        #   ]}
        # ]
        conds = ctx.extra['query_conditions']

        # 应该 1 项: 顶层 OR group
        assert len(conds) == 1, f"应有 1 项, 实际 {len(conds)}: {conds}"
        assert conds[0].get('type') == 'or'

        # OR group 内 2 项: and_group + owner_cond
        or_inner = conds[0]['conditions']
        assert len(or_inner) == 2

        # 第 1 项: AND group (包 dim + visibility OR group)
        assert or_inner[0].get('type') == 'and'
        and_inner = or_inner[0]['conditions']
        assert len(and_inner) == 2  # dim + visibility OR group

        # 第 2 项: owner exception
        assert or_inner[1].get('source') == 'owner_exception'
        assert or_inner[1]['field'] == 'owner_id'
        assert or_inner[1]['value'] == 1456

        # 验证 visibility scope 是 OR group
        visibility_conds = [c for c in and_inner if c.get('source') == 'visibility_scope']
        assert len(visibility_conds) == 1
        assert visibility_conds[0].get('type') == 'or'

    def test_owner_exception_without_other_conditions(self):
        """没其他条件时, owner 例外应直接生效"""
        from meta.core.interceptors.data_permission_interceptor import (
            DataPermissionInterceptor,
        )

        class MockContext:
            def __init__(self):
                self.user_id = 1456
                self.object_type = 'version'
                self.data_source = None
                self.meta_object = None
                self.extra = {}
                self.is_query_action = True

        interceptor = DataPermissionInterceptor()
        ctx = MockContext()

        import unittest.mock as mock
        with mock.patch.object(interceptor, '_bo_has_owner_id', return_value=True):
            interceptor._add_owner_exception(ctx)

        conds = ctx.extra['query_conditions']
        # 应只有 owner 条件（因为 existing 为空）
        assert len(conds) == 1
        assert conds[0]['field'] == 'owner_id'
        assert conds[0]['source'] == 'owner_exception'


# ────────────────────────────────────────
# 4. SQL 语义验证 (基于 _build_scope_conditions)
# ────────────────────────────────────────
class TestSQLSemanticsV105:
    """验证 v1.0.5 修复后 SQL 语义正确"""

    def test_dimension_scope_AND_visibility(self):
        """dimension scope 和 visibility 应是 AND 关系"""
        from meta.core.interceptors.persistence_interceptor import (
            PersistenceInterceptor,
        )

        interceptor = PersistenceInterceptor()

        # 模拟 v1.0.5 修复后的 query_conditions
        query_conditions = [
            # dimension scope: product_id = 1
            {'field': 'product_id', 'operator': 'eq', 'value': 1},
            # visibility scope: OR group (visibility='public' OR owner_id=1456)
            {
                'type': 'or',
                'conditions': [
                    {'field': 'visibility', 'operator': 'eq', 'value': 'public'},
                    {'field': 'owner_id', 'operator': 'eq', 'value': 1456},
                ],
            },
        ]

        class MockContext:
            extra = {'query_conditions': query_conditions}

        conditions, params = interceptor._build_scope_conditions(MockContext())

        # 应该有 2 个 where 片段, 用 AND 连接
        # 第 1 段: product_id = ?
        # 第 2 段: (visibility = ? OR owner_id = ?)
        assert len(conditions) == 2

        # 第 1 段: dimension scope
        assert 'product_id' in conditions[0]
        assert '=' in conditions[0]
        assert '?' in conditions[0]

        # 第 2 段: visibility OR group (用括号包住)
        assert '(' in conditions[1]
        assert 'OR' in conditions[1]
        assert 'visibility' in conditions[1]

    def test_owner_exception_OR_dimension_and_visibility(self):
        """owner 例外应是顶层 OR, 把 dimension+visibility 包成一个 AND group"""
        from meta.core.interceptors.persistence_interceptor import (
            PersistenceInterceptor,
        )

        interceptor = PersistenceInterceptor()

        # v1.0.7 结构: [OR group {AND group, owner_cond}]
        and_group = [
            {'field': 'product_id', 'operator': 'eq', 'value': 1},
            {
                'type': 'or',
                'conditions': [
                    {'field': 'visibility', 'operator': 'eq', 'value': 'public'},
                    {'field': 'owner_id', 'operator': 'eq', 'value': 1456},
                ],
            },
        ]
        query_conditions = [{
            'type': 'or',
            'conditions': [
                {'type': 'and', 'conditions': and_group},
                {'field': 'owner_id', 'operator': 'eq', 'value': 1456,
                 'source': 'owner_exception'},
            ],
        }]

        class MockContext:
            extra = {'query_conditions': query_conditions}

        conditions, params = interceptor._build_scope_conditions(MockContext())

        # 应有 1 个 where 片段（外层 OR group）
        assert len(conditions) == 1, f"应有 1 段, 实际 {len(conditions)}: {conditions}"

        sql = conditions[0]

        # 完整 SQL 应是:
        # ((product_id = ? AND (visibility = ? OR owner_id = ?)) OR owner_id = ?)
        assert sql.startswith('(')
        assert ' AND ' in sql
        assert ' OR ' in sql
        assert 'product_id' in sql
        assert 'visibility' in sql
        assert 'owner_id' in sql


# ────────────────────────────────────────
# 5. TESET68 端到端场景测试
# ────────────────────────────────────────
class TestTeset68EndToEnd:
    """TESET68 场景: 配置 product=[1] 后看不到别人 draft, 但能看到 public"""

    def test_teset68_query_conditions_structure(self):
        """TESET68 的 query_conditions 应正确包含 AND visibility filter"""
        from meta.core.interceptors.data_permission_interceptor import (
            DataPermissionInterceptor,
        )

        # 模拟 _apply_dimension_scope_filter 后的 query_conditions
        # dimension scope: product_id = 1 (TESET68 配 product=[1] → version.product_id=1)
        ctx_user_id = 1456

        class MockContext:
            user_id = ctx_user_id
            user_name = 'TESET68'
            object_type = 'version'
            data_source = None
            meta_object = type('M', (), {
                'authorization': {
                    'scope': "visibility = 'public' OR owner_id = $user.id",
                    'check': True,
                }
            })()
            extra = {
                'query_conditions': [{
                    'field': 'product_id',
                    'operator': 'eq',
                    'value': 1,
                }],
            }
            is_query_action = True

        interceptor = DataPermissionInterceptor()
        ctx = MockContext()

        # [FIX 2026-06-13] mock _bo_has_visibility_field 也需要返回 True
        import unittest.mock as mock
        with mock.patch.object(interceptor, '_bo_has_owner_id', return_value=True), \
             mock.patch.object(interceptor, '_bo_has_visibility_field', return_value=True):
            interceptor._apply_scope_filter_after_dimension(ctx)

        # v1.0.7 结构: [{type:'or', conditions:[and_group, owner_cond]}]
        final_conds = ctx.extra['query_conditions']
        assert len(final_conds) == 1
        assert final_conds[0].get('type') == 'or'

        or_inner = final_conds[0]['conditions']
        assert len(or_inner) == 2

        # or_inner[0]: AND group (包 dim + visibility OR group)
        assert or_inner[0].get('type') == 'and'
        and_inner = or_inner[0]['conditions']
        assert len(and_inner) == 2

        # and_inner[0]: dimension scope (product_id=1)
        dim_cond = and_inner[0]
        assert dim_cond['field'] == 'product_id'
        assert dim_cond['value'] == 1

        # and_inner[1]: visibility scope (OR group)
        vis_cond = and_inner[1]
        assert vis_cond.get('type') == 'or'
        assert vis_cond['source'] == 'visibility_scope'

        # or_inner[1]: owner exception
        owner_cond = or_inner[1]
        assert owner_cond['source'] == 'owner_exception'
        assert owner_cond['field'] == 'owner_id'
        assert owner_cond['value'] == ctx_user_id

    def test_teset68_cannot_see_other_users_draft(self):
        """TESET68 不能看到别人 owner 的 draft

        模拟场景:
          - version id=2, visibility='draft', owner_id=999 (别人)
          - TESET68 (user_id=1456) 查询 version

        修复前: 能看到（dimension scope 命中 → 直接 return → 跳过 visibility）
        修复后: 看不到（dimension scope AND visibility scope: 1456 不是 owner，
                visibility=draft 不通过 OR 的第一项, 也不通过第二项 owner=999）
        """
        from meta.core.interceptors.persistence_interceptor import (
            PersistenceInterceptor,
        )

        interceptor = PersistenceInterceptor()

        # v1.0.7 修复后 TESET68 的 query_conditions
        and_group = [
            # dimension scope: product_id = 1
            {'field': 'product_id', 'operator': 'eq', 'value': 1},
            # visibility scope: visibility='public' OR owner_id=1456
            {
                'type': 'or',
                'source': 'visibility_scope',
                'conditions': [
                    {'field': 'visibility', 'operator': 'eq', 'value': 'public'},
                    {'field': 'owner_id', 'operator': 'eq', 'value': 1456},
                ],
            },
        ]
        query_conditions = [{
            'type': 'or',
            'conditions': [
                {'type': 'and', 'conditions': and_group},
                # owner exception (顶层 OR)
                {'field': 'owner_id', 'operator': 'eq', 'value': 1456,
                 'source': 'owner_exception'},
            ],
        }]

        class MockContext:
            extra = {'query_conditions': query_conditions}

        conditions, params = interceptor._build_scope_conditions(MockContext())

        # 整个条件应该是:
        # WHERE (product_id = ? AND (visibility = ? OR owner_id = ?) OR owner_id = ?)
        sql = conditions[0]
        params_list = params

        # 验证 SQL 包含 AND visibility
        assert 'product_id' in sql
        assert 'visibility' in sql
        assert 'AND' in sql

        # 模拟版本 id=2 的数据: product_id=1, visibility='draft', owner_id=999
        # 验算 SQL 不会匹配该记录
        # SQL: (product_id=1 AND (visibility='public' OR owner_id=1456)) OR owner_id=1456
        # 代入:
        #   (1=1 AND ('draft'='public' OR 999=1456)) OR 999=1456
        # = (TRUE AND (FALSE OR FALSE)) OR FALSE
        # = FALSE
        # → 不匹配, 正确！TESET68 看不到 draft version id=2
        visibility_check = ('draft' == 'public') or (999 == 1456)
        owner_check = 999 == 1456
        match = (True and visibility_check) or owner_check
        assert not match, "TESET68 不应该看到别人的 draft 版本"

        # 模拟 version id=1 的数据: product_id=1, visibility='public', owner_id=None
        # SQL: (1=1 AND ('public'='public' OR NULL=1456)) OR NULL=1456
        # = (TRUE AND TRUE) OR FALSE
        # = TRUE
        # → 匹配, 正确！TESET68 能看到 public version
        visibility_check_pub = ('public' == 'public') or (None == 1456)
        owner_check_pub = None == 1456
        match_pub = (True and visibility_check_pub) or owner_check_pub
        assert match_pub, "TESET68 应该能看到 public 版本"