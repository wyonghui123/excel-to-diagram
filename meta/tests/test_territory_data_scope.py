# -*- coding: utf-8 -*-
"""TER-M4 销售区域数据范围测试（维度激活 / 子树展开 / 数据条件 / v135 迁移）

依据: docs/superpowers/specs/2026-10-26-sales-territory-design.md
      §7 数据范围落地 / §9 M4 / §10 测试矩阵（数据范围行）

覆盖:
1. loader: territory 维度已激活（generic + value_table=territories +
   filter_through_hierarchy + 两个承载面 sales_order / territory_account_assignment）
2. 原语: expand_generic_dimension_subtree 沿 territories.parent_id 展开（含防环）
3. 引擎: _apply_generic_dimension_auto_expand('territory', ...) 子树展开
4. runtime: 角色配父区域 → include 展开含子孙 / inherit_children=0 不展开 / all
5. 数据条件: 角色配区域 → sales_order.territory_id IN 子树；未登记承载面的 BO 无条件
6. 迁移 v135: 菜单页形态 object_list → multi_object_hub / 幂等 / 缺表终止 / 回滚

【测试数据】
DDL/DML 集中在 factories/ helper（conftest raw-SQL 白名单豁免）:
- territories 树: seed_territory_tree
- menus 行: _pricing_w1_helpers.seed_row
"""
import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from meta.tests.factories._dimension_scope_engine_helpers import (
    make_dim_scope_engine_ds,
    seed_org_tree,
    seed_territory_tree,
)
from meta.tests.factories._spec20_bizkey_helpers import add_scope
from meta.tests.factories._pricing_w1_helpers import seed_row

ALL_TERRITORY_IDS = {1, 2, 3, 4, 201, 202, 203}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_hub_declaration_enables_left_tree_right_table():
    """territory.yaml 的 hub 声明：左树 = 区域自引用层级，右表 = 区域列表"""
    import yaml

    with open(_PROJECT_ROOT / 'meta' / 'schemas' / 'territory.yaml',
              encoding='utf-8') as f:
        cfg = yaml.safe_load(f)['ui_view_config']
    hub = cfg['hub']
    assert hub['object_types'] == ['territory']
    assert hub['default_tab'] == 'territory'
    scope = hub['scope']
    assert scope['type'] == 'hierarchy'
    assert scope['object'] == 'territory'
    assert scope['scope_key'] == 'territory'
    assert scope['parent_field'] == 'parent_id'
    # 勾选节点 → 右表按 id__in 过滤（effective = 勾选 ∪ 子孙）
    assert hub['filters']['territory']['field'] == 'id'


def _loader():
    from meta.core.dimension_object_mapping_loader import (
        get_dimension_object_mapping_loader,
    )
    return get_dimension_object_mapping_loader()


@pytest.fixture
def mock_ds():
    """临时 SQLite（scope / menus / territories 表）+ 区域树种子"""
    g = make_dim_scope_engine_ds()
    ds = next(g)
    seed_territory_tree(ds)
    yield ds


# ────────────────────────────────────────
# 1. 维度激活: loader 读到 territory 声明
# ────────────────────────────────────────
class TestLoaderTerritoryActivation:
    def test_territory_mapping_activated(self):
        """YAML 中 territory 维度已激活（generic + value_table + 两个承载面）"""
        m = _loader().get_mapping('territory')
        assert m is not None
        assert m.get('dimension_type') == 'generic'
        assert m.get('value_table') == 'territories'
        assert m.get('value_field') == 'id'
        assert m.get('filter_through_hierarchy') is True
        applies_to = m.get('applies_to') or []
        assert {'bo': 'sales_order', 'field': 'territory_id',
                'filter_type': 'fk'} in applies_to
        assert {'bo': 'territory_account_assignment', 'field': 'territory_id',
                'filter_type': 'fk'} in applies_to
        assert {e.get('bo') for e in applies_to} == {
            'sales_order', 'territory_account_assignment'}

    def test_flag_and_value_table(self):
        loader = _loader()
        assert loader.is_filter_through_hierarchy('territory') is True
        assert loader.get_value_table('territory') == 'territories'
        assert loader.get_value_field('territory') == 'id'

    def test_priority(self):
        """territory 优先级 60，低于 org（数值越大越低）"""
        loader = _loader()
        assert loader.get_priority('territory') == 60
        assert loader.get_priority('org') < loader.get_priority('territory')

    def test_binding_lookup(self):
        loader = _loader()
        assert loader.get_field_for_bo('territory', 'sales_order') == {
            'bo': 'sales_order', 'field': 'territory_id', 'filter_type': 'fk'}
        assert loader.get_field_for_bo('territory', 'customer_account') is None


# ────────────────────────────────────────
# 2. 原语: expand_generic_dimension_subtree
# ────────────────────────────────────────
class TestExpandGenericSubtreePrimitive:
    def _expand(self, ds, ids):
        from meta.services.permission_dimension_engine import (
            expand_generic_dimension_subtree,
        )
        return expand_generic_dimension_subtree(ds, 'territories', 'id', ids)

    def test_root_includes_whole_subtree(self, mock_ds):
        assert self._expand(mock_ds, [1]) == {1, 2, 3, 4}

    def test_middle_node_only_descendants(self, mock_ds):
        assert self._expand(mock_ds, [2]) == {2, 3}

    def test_cycle_terminates(self, mock_ds):
        assert self._expand(mock_ds, [201]) == {201, 202, 203}

    def test_multiple_roots_union(self, mock_ds):
        assert self._expand(mock_ds, [2, 4]) == {2, 3, 4}

    def test_missing_table_fail_closed(self, mock_ds):
        from meta.services.permission_dimension_engine import (
            expand_generic_dimension_subtree,
        )
        assert expand_generic_dimension_subtree(
            mock_ds, 'no_such_table_xyz', 'id', [7]) == {7}

    def test_empty_input(self, mock_ds):
        assert self._expand(mock_ds, []) == set()


# ────────────────────────────────────────
# 3. 引擎入口: 选中值自动含子孙
# ────────────────────────────────────────
class TestApplyGenericDimensionAutoExpand:
    @pytest.fixture
    def engine(self, mock_ds):
        from meta.services.permission_dimension_engine import (
            PermissionDimensionEngine,
        )
        return PermissionDimensionEngine(mock_ds, ttl_seconds=300)

    def test_territory_expands_subtree(self, engine):
        assert engine._apply_generic_dimension_auto_expand('territory', [1]) == \
            [1, 2, 3, 4]

    def test_business_dimension_passthrough(self, engine):
        assert engine._apply_generic_dimension_auto_expand('product', [1]) == [1]

    def test_empty_passthrough(self, engine):
        assert engine._apply_generic_dimension_auto_expand('territory', []) == []


# ────────────────────────────────────────
# 4. runtime: 角色区域范围展开
# ────────────────────────────────────────
class TestRuntimeTerritorySubtreeExpansion:
    @pytest.fixture
    def engine(self, mock_ds):
        from meta.services.dimension_scope_engine import DimensionScopeEngine
        return DimensionScopeEngine(mock_ds)

    def test_include_expands_subtree(self, mock_ds, engine):
        add_scope(mock_ds, 1, 'territory', [1])
        expanded, native, anchors, inherited, failed = \
            engine.expand_dimension_values_detail(1)
        assert expanded['territory'] == {1, 2, 3, 4}
        assert native['territory'] == {1}
        assert anchors == {} and inherited == {} and failed == {}

    def test_include_middle_node(self, mock_ds, engine):
        add_scope(mock_ds, 1, 'territory', [2])
        expanded, _, _, _, _ = engine.expand_dimension_values_detail(1)
        assert expanded['territory'] == {2, 3}

    def test_inherit_children_off_no_expand(self, mock_ds, engine):
        """inherit_children=0 → 不展开子树（仅原生选中值，不放大范围）"""
        add_scope(mock_ds, 1, 'territory', [1], inherit=0)
        assert engine.expand_dimension_values(1)['territory'] == {1}

    def test_scope_mode_all(self, mock_ds, engine):
        add_scope(mock_ds, 1, 'territory', [], mode='all')
        assert engine.expand_dimension_values(1)['territory'] == ALL_TERRITORY_IDS

    def test_get_all_dimension_ids_fallback(self, mock_ds, engine):
        assert engine._get_all_dimension_ids('territory') == ALL_TERRITORY_IDS


# ────────────────────────────────────────
# 5. 数据条件: 承载面登记后生成区域过滤 SQL
# ────────────────────────────────────────
class TestDeriveDataConditionsTerritoryBinding:
    def test_sales_order_condition_uses_subtree(self, mock_ds):
        """角色配区域=1 → 订单按快照列 territory_id 过滤到 1 的子树"""
        import unittest.mock as mock
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'territory', [1])

        with mock.patch.object(engine, '_get_all_resource_types',
                               return_value=['sales_order',
                                             'territory_account_assignment',
                                             'customer_account']):
            conditions = engine.derive_data_conditions(1)

        assert conditions.get('sales_order') == 'territory_id IN (1,2,3,4)'
        assert conditions.get('territory_account_assignment') == \
            'territory_id IN (1,2,3,4)'
        # 未登记承载面的 BO 不受区域维度影响
        assert 'customer_account' not in conditions

    def test_inherit_children_off_single_value(self, mock_ds):
        """inherit_children=0 → 单值等值条件，不含子孙"""
        import unittest.mock as mock
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'territory', [1], inherit=0)

        with mock.patch.object(engine, '_get_all_resource_types',
                               return_value=['sales_order']):
            conditions = engine.derive_data_conditions(1)

        assert conditions.get('sales_order') == 'territory_id = 1'

    def test_no_scope_no_condition(self, mock_ds):
        """角色未配区域 → 不注入区域条件（默认看全部）"""
        import unittest.mock as mock
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'product', [1])

        with mock.patch.object(engine, '_get_all_resource_types',
                               return_value=['sales_order']):
            conditions = engine.derive_data_conditions(1)

        assert 'sales_order' not in conditions

    def test_org_and_territory_same_role_and(self, mock_ds):
        """跨维度护栏（D-TER-3）：同角色内 org + territory 命中同一 BO 取 AND

        生产映射中 org 只绑 party_internal、territory 只绑 sales_order，两套承载面
        不相交；此处用测试桩给 org 注入 sales_order 绑定，锁定引擎的跨维度 AND
        语义，防止后续 org 纳入管理维度时被无意改成 OR。
        """
        import unittest.mock as mock
        from meta.core.dimension_object_mapping_loader import (
            get_dimension_object_mapping_loader,
        )
        from meta.services.dimension_scope_engine import DimensionScopeEngine

        seed_org_tree(mock_ds)
        engine = DimensionScopeEngine(mock_ds)
        add_scope(mock_ds, 1, 'org', [1])
        add_scope(mock_ds, 1, 'territory', [1])

        loader = get_dimension_object_mapping_loader()
        real_get_bindings = loader.get_bindings_for_bo

        def stub_bindings(dim_code, bo_id):
            if dim_code == 'org' and bo_id == 'sales_order':
                return [{'bo': 'sales_order', 'field': 'org_id',
                         'filter_type': 'fk'}]
            return real_get_bindings(dim_code, bo_id)

        with mock.patch.object(loader, 'get_bindings_for_bo',
                               side_effect=stub_bindings), \
                mock.patch.object(engine, '_get_all_resource_types',
                                  return_value=['sales_order']):
            conditions = engine.derive_data_conditions(1)

        parts = set(conditions.get('sales_order', '').split(' AND '))
        assert parts == {'org_id IN (1,2,3,4,5)',
                         'territory_id IN (1,2,3,4)'}


# ────────────────────────────────────────
# 6. 迁移 v135: 菜单页形态切换
# ────────────────────────────────────────
from meta.migrations.v135__territory_hub import (  # noqa: E402
    MENU_CODE,
    PAGE_TYPE_NEW,
    PAGE_TYPE_OLD,
    migrate,
    rollback,
    verify,
)


def _stub_db(tmp_path: Path, page_type: str = PAGE_TYPE_OLD) -> Path:
    """最小 menus 表 + 一行 territory-list 菜单。"""
    db = tmp_path / 'territory_hub.db'
    conn = sqlite3.connect(str(db))
    conn.execute(
        'CREATE TABLE menus (id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'menu_code TEXT, menu_name TEXT, page_type TEXT)')
    conn.commit()
    conn.close()
    seed_row(db, 'menus', menu_code=MENU_CODE, menu_name='销售区域',
             page_type=page_type)
    return db


def _scalar(path: Path, sql: str, params=()):
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


class TestMigrationV135:
    def test_switches_page_type(self, tmp_path):
        db = _stub_db(tmp_path)
        assert migrate(db) is True
        assert verify(db) is True
        assert _scalar(db, 'SELECT page_type FROM menus WHERE menu_code = ?',
                       (MENU_CODE,))[0] == PAGE_TYPE_NEW

    def test_rerun_is_idempotent(self, tmp_path):
        db = _stub_db(tmp_path)
        assert migrate(db) is True
        assert migrate(db) is True
        assert _scalar(db, 'SELECT COUNT(*) FROM menus WHERE menu_code = ?',
                       (MENU_CODE,))[0] == 1
        assert verify(db) is True

    def test_missing_menus_table_fails(self, tmp_path):
        db = tmp_path / 'empty.db'
        sqlite3.connect(str(db)).close()
        assert migrate(db) is False
        assert verify(db) is False

    def test_menu_row_missing_skips(self, tmp_path):
        """menus 表在但菜单行缺失（v132 未执行）→ 迁移跳过，verify 不通过"""
        db = tmp_path / 'no_row.db'
        conn = sqlite3.connect(str(db))
        conn.execute('CREATE TABLE menus (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                     'menu_code TEXT, menu_name TEXT, page_type TEXT)')
        conn.commit()
        conn.close()
        assert migrate(db) is True
        assert verify(db) is False

    def test_rollback_restores_object_list(self, tmp_path):
        db = _stub_db(tmp_path)
        assert migrate(db) is True
        assert rollback(db) is True
        assert _scalar(db, 'SELECT page_type FROM menus WHERE menu_code = ?',
                       (MENU_CODE,))[0] == PAGE_TYPE_OLD
        assert verify(db) is False
