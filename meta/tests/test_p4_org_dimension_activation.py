# -*- coding: utf-8 -*-
"""
P4-Org-01 组织维度激活测试 (F1 治理分域 §7.1「平台动作」item 1/2/3)

【背景】
org 维度激活是步 2 (party 建表) 的直接前置:
- item 1: dimension_object_mapping.yaml org 维度激活 (generic +
          filter_through_hierarchy) + loader.is_filter_through_hierarchy 解析
- item 2: PermissionDimensionEngine._apply_generic_dimension_auto_expand 实现
          (沿 orgs.parent_id 自引用树 BFS 展开, visited 防环;
           先例 OrgAdminScopeService.expand_org_scope)
- item 3: DimensionScopeEngine runtime 侧 generic 维度子树展开缺口补齐
          (_expand_down_chain generic 分支 / _get_all_dimension_ids 回落)

【覆盖】
1. loader: org 激活字段 + flag 语义 + priority
2. 原语: expand_generic_dimension_subtree (子树/中节点/防环/fail-closed)
3. 引擎: _apply_generic_dimension_auto_expand (org 展开 / 非 generic 透传)
4. runtime: DimensionScopeEngine (include 展开 / inherit_children=0 / all)
5. 数据条件: 模拟步 2 party_internal direct binding → org_id IN (子树)
6. 验收核对: org-only scope 不生成菜单/功能权限 (derivePermissions 对
   generic 维度仅推数据规则)

【测试数据】
DDL/DML 集中在 factories/ helper (conftest raw-SQL 白名单豁免):
- orgs 树: 见 seed_org_tree (干净树 1→2→3 / 1→4→5 + 防环环 101↔104)
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

from meta.tests.factories._dimension_scope_engine_helpers import (
    make_dim_scope_engine_ds,
    seed_org_tree,
)
from meta.tests.factories._spec20_bizkey_helpers import add_scope

pytestmark = pytest.mark.unit

ALL_ORG_IDS = {1, 2, 3, 4, 5, 101, 102, 103, 104}


def _loader():
    from meta.core.dimension_object_mapping_loader import (
        get_dimension_object_mapping_loader,
    )
    return get_dimension_object_mapping_loader()


@pytest.fixture
def mock_ds():
    """临时 SQLite (scope/menus/orgs 表) + org 树种子"""
    g = make_dim_scope_engine_ds()
    ds = next(g)
    seed_org_tree(ds)
    yield ds


@pytest.fixture
def loader_mutation():
    """临时改写 loader 单例缓存配置 (测试后还原)

    用途: 模拟步 2 的 org→BO binding 登记 / 构造 value_table 缺失场景。
    """
    loader = _loader()
    loader.is_loaded()  # 确保缓存已加载
    saved = {}

    def mutate(code, **changes):
        m = loader._config['mappings'][code]
        for k, v in changes.items():
            saved.setdefault((code, k), (k in m, m.get(k)))
            m[k] = v
        return m

    yield mutate

    for (code, k), (existed, old) in saved.items():
        m = loader._config['mappings'][code]
        if existed:
            m[k] = old
        else:
            m.pop(k, None)


# ────────────────────────────────────────
# 1. item 1: loader org 激活
# ────────────────────────────────────────
class TestLoaderOrgActivation:
    def test_org_mapping_activated(self):
        """YAML 中 org 维度已激活 (generic + value_table=orgs + 步 2 承载面登记)"""
        m = _loader().get_mapping('org')
        assert m is not None
        assert m.get('dimension_type') == 'generic'
        assert m.get('value_table') == 'orgs'
        assert m.get('value_field') == 'id'
        # 步 2 (2026-10-05): 内部面 party_internal 已真实登记为 org 承载面
        applies_to = m.get('applies_to') or []
        assert {'bo': 'party_internal', 'field': 'org_id',
                'filter_type': 'direct'} in applies_to
        # 仅内部面登记: 写锚 party / 对外面 party_archive 不得出现
        assert {e.get('bo') for e in applies_to} == {'party_internal'}

    def test_flag_true_for_org(self):
        """is_filter_through_hierarchy('org') → True (P4-Org-01)"""
        loader = _loader()
        assert loader.is_filter_through_hierarchy('org') is True
        assert loader.get_value_table('org') == 'orgs'
        assert loader.get_value_field('org') == 'id'

    def test_flag_false_for_business_and_unknown(self):
        """business 维度 / 未知维度 → False (不误开子树展开)"""
        loader = _loader()
        for dim in ('product', 'version', 'domain', 'sub_domain'):
            assert loader.is_filter_through_hierarchy(dim) is False
        assert loader.is_filter_through_hierarchy('unknown_dimension_xyz') is False

    def test_org_priority(self):
        """org 优先级 50, 低于 product (数值越大越低)"""
        loader = _loader()
        assert loader.get_priority('org') == 50
        assert loader.get_priority('product') < loader.get_priority('org')


# ────────────────────────────────────────
# 2. item 2 原语: expand_generic_dimension_subtree
# ────────────────────────────────────────
class TestExpandGenericSubtreePrimitive:
    def _expand(self, ds, ids):
        from meta.services.permission_dimension_engine import (
            expand_generic_dimension_subtree,
        )
        return expand_generic_dimension_subtree(ds, 'orgs', 'id', ids)

    def test_root_includes_whole_subtree(self, mock_ds):
        assert self._expand(mock_ds, [1]) == {1, 2, 3, 4, 5}

    def test_middle_node_only_descendants(self, mock_ds):
        """选中中间节点: 仅含子孙, 不含祖先/兄弟"""
        assert self._expand(mock_ds, [2]) == {2, 3}
        assert self._expand(mock_ds, [4]) == {4, 5}

    def test_cycle_terminates(self, mock_ds):
        """自引用环: BFS 必须终止且环上节点全覆盖"""
        assert self._expand(mock_ds, [101]) == {101, 102, 103, 104}

    def test_multiple_roots_union(self, mock_ds):
        assert self._expand(mock_ds, [2, 4]) == {2, 3, 4, 5}

    def test_missing_table_fail_closed(self, mock_ds):
        """表不存在 → 仅返回根集合 (不放大范围)"""
        from meta.services.permission_dimension_engine import (
            expand_generic_dimension_subtree,
        )
        assert expand_generic_dimension_subtree(
            mock_ds, 'no_such_table_xyz', 'id', [7]) == {7}

    def test_empty_input(self, mock_ds):
        assert self._expand(mock_ds, []) == set()


# ────────────────────────────────────────
# 3. item 2: 引擎入口 _apply_generic_dimension_auto_expand
# ────────────────────────────────────────
class TestApplyGenericDimensionAutoExpand:
    @pytest.fixture
    def engine(self, mock_ds):
        from meta.services.permission_dimension_engine import (
            PermissionDimensionEngine,
        )
        return PermissionDimensionEngine(mock_ds, ttl_seconds=300)

    def test_org_expands_subtree(self, engine):
        assert engine._apply_generic_dimension_auto_expand('org', [1]) == \
            [1, 2, 3, 4, 5]

    def test_business_dimension_passthrough(self, engine):
        assert engine._apply_generic_dimension_auto_expand('product', [1]) == [1]

    def test_unknown_dimension_passthrough(self, engine):
        assert engine._apply_generic_dimension_auto_expand('unknown_xyz', [9]) == [9]

    def test_empty_passthrough(self, engine):
        assert engine._apply_generic_dimension_auto_expand('org', []) == []

    def test_missing_value_table_fail_closed(self, engine, loader_mutation):
        """value_table 指向不存在表 → 透传原值 (fail-closed)"""
        loader_mutation('org', value_table='no_such_table_xyz')
        assert engine._apply_generic_dimension_auto_expand('org', [7]) == [7]


# ────────────────────────────────────────
# 3b. [P4-Org-02] 引擎三级合并映射公开入口 (org 等 generic 维度)
# ────────────────────────────────────────
class TestResourceTableMergedMap:
    """get_resource_table: /instances 与 /codes 支持 org 的支点"""

    @pytest.fixture
    def engine(self, mock_ds):
        from meta.services.permission_dimension_engine import (
            PermissionDimensionEngine,
        )
        return PermissionDimensionEngine(mock_ds, ttl_seconds=300)

    def test_org_resolves_to_orgs(self, engine):
        """静态 map 无 org, 靠 YAML value_table 合并解析"""
        assert engine.get_resource_table('org') == 'orgs'

    def test_business_dim_still_resolves(self, engine):
        assert engine.get_resource_table('product') == 'products'

    def test_unknown_dim_returns_none(self, engine):
        assert engine.get_resource_table('unknown_xyz') is None


# ────────────────────────────────────────
# 4. item 3: DimensionScopeEngine runtime 展开
# ────────────────────────────────────────
class TestRuntimeOrgSubtreeExpansion:
    @pytest.fixture
    def engine(self, mock_ds):
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        return DimensionScopeEngine(mock_ds)

    def test_include_expands_subtree(self, mock_ds, engine):
        add_scope(mock_ds, 1, 'org', [1])
        expanded, native, anchors, inherited, failed = \
            engine.expand_dimension_values_detail(1)
        assert expanded['org'] == {1, 2, 3, 4, 5}
        assert native['org'] == {1}  # 原生选中值保持 (子树进 expanded)
        assert anchors == {} and inherited == {} and failed == {}

    def test_include_middle_node(self, mock_ds, engine):
        add_scope(mock_ds, 1, 'org', [2])
        expanded, _, _, _, _ = engine.expand_dimension_values_detail(1)
        assert expanded['org'] == {2, 3}

    def test_inherit_children_off_no_expand(self, mock_ds, engine):
        """inherit_children=0 → 不展开子树 (仅原生选中值)"""
        add_scope(mock_ds, 1, 'org', [1], inherit=0)
        expanded = engine.expand_dimension_values(1)
        assert expanded['org'] == {1}

    def test_scope_mode_all(self, mock_ds, engine):
        """scope_mode='all' → 全量 org (generic 回落 value_table)"""
        add_scope(mock_ds, 1, 'org', [], mode='all')
        expanded = engine.expand_dimension_values(1)
        assert expanded['org'] == ALL_ORG_IDS

    def test_get_all_dimension_ids_org_fallback(self, mock_ds, engine):
        assert engine._get_all_dimension_ids('org') == ALL_ORG_IDS

    def test_get_all_dimension_ids_unknown_empty(self, mock_ds, engine):
        assert engine._get_all_dimension_ids('unknown_xyz') == set()


# ────────────────────────────────────────
# 5. 数据条件: 模拟步 2 party_internal direct binding
# ────────────────────────────────────────
class TestDeriveDataConditionsOrgBinding:
    def test_org_direct_binding_generates_subtree_sql(self, mock_ds):
        """步 2 登记 party_internal.org_id 承载 org 维度后:
        选中 org=1 → SQL 条件 org_id IN (1,2,3,4,5)"""
        import unittest.mock as mock
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'org', [1])

        with mock.patch.object(engine, '_get_all_resource_types',
                               return_value=['party_internal']):
            conditions = engine.derive_data_conditions(1)

        assert conditions.get('party_internal') == 'org_id IN (1,2,3,4,5)'

    def test_org_binding_absent_no_condition(self, mock_ds):
        """未登记 binding 的 BO 不受 org 维度影响 (写锚 party / 对外面 party_archive)"""
        import unittest.mock as mock
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'org', [1])

        with mock.patch.object(engine, '_get_all_resource_types',
                               return_value=['party', 'party_archive']):
            conditions = engine.derive_data_conditions(1)

        assert 'party' not in conditions
        assert 'party_archive' not in conditions


# ────────────────────────────────────────
# 6. P4-Org-01 验收核对: 无菜单/功能权限泄露
# ────────────────────────────────────────
class TestNoFunctionalPermissionLeak:
    def test_org_only_scope_no_menus_no_permissions(self, mock_ds):
        """org-only scope + 空菜单 → 推荐菜单/功能权限均为空"""
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'org', [1])

        assert engine.derive_recommended_menus(1) == []
        assert engine.derive_permissions(1) == []

    def test_org_subtree_expanded_but_no_permissions(self, mock_ds):
        """反向对照: org 子树确实展开 (数据范围生效), 但不派生功能权限"""
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'org', [1])

        expanded = engine.expand_dimension_values(1)
        assert expanded['org'] == {1, 2, 3, 4, 5}
        assert engine.derive_permissions(1) == []