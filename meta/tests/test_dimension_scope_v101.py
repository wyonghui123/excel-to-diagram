# -*- coding: utf-8 -*-
"""[Test v1.0.1] DimensionScopeEngine.derive_data_conditions 向上展开

[FIX 2026-10-05] 原用例直连真实 meta/architecture.db 的 permission_set 1803 (TEST60),
该运行数据在当前库中已不存在 → _load_scopes 返回空 → 恒得 {} → 4 项恒失败。
改为自播种临时 SQLite (factories/ 白名单惯例), 复刻同一拓扑 (version=[2,11,12]),
使断言确定性可复现; 断言逻辑与原用例保持一致。
"""
import pytest

pytestmark = pytest.mark.unit

from meta.services.dimension_scope_engine import DimensionScopeEngine
from meta.tests.factories._dimension_scope_engine_helpers import (
    make_dim_scope_engine_ds, seed_v101_upward_expansion,
)

PS_ID = 1803
_CHAIN_DIMS = ['product', 'version', 'domain', 'sub_domain']


@pytest.fixture
def engine(monkeypatch):
    g = make_dim_scope_engine_ds()
    ds = next(g)
    seed_v101_upward_expansion(ds)
    eng = DimensionScopeEngine(ds)
    # 限定资源类型为 4 个业务维度, 避免无关 BO 的 chain 条件访问临时库中不存在的表
    monkeypatch.setattr(eng, '_get_all_resource_types', lambda: list(_CHAIN_DIMS))
    yield eng


def test_T1_upward_product_from_version(engine):
    """[T1] version=[2,11,12] 应向上反查 product 并生成 product 过滤"""
    conditions = engine.derive_data_conditions(PS_ID)
    # product filter 应有 id 限定 (向上的 product_id 反查)
    assert 'product' in conditions, f"product should have filter, got: {conditions}"
    cond = conditions['product']
    assert 'id' in cond.lower() or 'IN' in cond.upper(), \
        f"product filter should have id restriction, got: {cond}"


def test_T2_upward_domain_no_change(engine):
    """[T2] domain 已有向下展开, 不应破坏"""
    conditions = engine.derive_data_conditions(PS_ID)
    assert 'domain' in conditions, f"domain missing: {conditions}"
    cond = conditions['domain']
    assert 'version_id' in cond
    assert '2' in cond
    assert '11' in cond
    assert '12' in cond


def test_T3_subdomain_no_change(engine):
    """[T3] sub_domain 向下展开, 应保留"""
    conditions = engine.derive_data_conditions(PS_ID)
    assert 'sub_domain' in conditions, f"sub_domain missing: {conditions}"
    assert 'domain_id' in conditions['sub_domain']


def test_T4_version_id_filter(engine):
    """[T4] version 应有 id IN (2, 11, 12)"""
    conditions = engine.derive_data_conditions(PS_ID)
    assert 'version' in conditions, f"version missing: {conditions}"
    cond = conditions['version']
    assert 'id' in cond.lower() or 'IN' in cond.upper(), \
        f"version filter should restrict ids, got: {cond}"