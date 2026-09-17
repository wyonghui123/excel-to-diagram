import pytest

pytestmark = pytest.mark.unit

from meta.services.dimension_scope_engine import DimensionScopeEngine, HIERARCHY_CHAIN
from meta.tests.factories._dimension_scope_engine_helpers import (
    make_dim_scope_engine_ds, seed_basic_scope, seed_menu_domain,
)


@pytest.fixture
def ds():
    """临时 SQLite DB + DS wrapper (DDL/DML 在 factories/ helper, 白名单)."""
    g = make_dim_scope_engine_ds()
    yield next(g)


def test_expand_dimension_values(ds):
    seed_basic_scope(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.expand_dimension_values(1)
    # [Plan B C3 fix 2026-08-29] engine 返回 Dict[str, Set[int]],
    # result[dim] 直接是 set, 不再有 ['include'] 子 dict
    assert isinstance(result, dict)
    assert 'product' in result
    assert 1 in result['product']


def test_derive_data_conditions(ds):
    seed_basic_scope(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.derive_data_conditions(1)
    assert isinstance(result, dict)


def test_derive_recommended_menus(ds):
    seed_basic_scope(ds)
    seed_menu_domain(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.derive_recommended_menus(1)
    assert isinstance(result, list)


def test_derive_permissions(ds):
    seed_basic_scope(ds)
    seed_menu_domain(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.derive_permissions(1)
    assert isinstance(result, list)


def test_auto_sync_all(ds):
    seed_basic_scope(ds)
    engine = DimensionScopeEngine(ds)
    result = engine.auto_sync_all(1)
    assert isinstance(result, dict)
    assert 'dimension_scopes' in result
    assert 'recommended_menus' in result
    assert 'derived_permissions' in result
    assert 'data_conditions' in result


def test_hierarchy_chain_constant():
    # [REMOVED] 2026-06-03: service_module 和 business_object 从管理维度移除
    # 新的层级链: product → version → domain → sub_domain (4层)
    assert HIERARCHY_CHAIN == ['product', 'version', 'domain', 'sub_domain']


def test_load_scopes_empty(ds):
    engine = DimensionScopeEngine(ds)
    scopes = engine._load_scopes(999)
    assert isinstance(scopes, list)
    assert len(scopes) == 0
