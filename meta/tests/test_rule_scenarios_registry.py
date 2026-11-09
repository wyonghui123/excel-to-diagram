# -*- coding: utf-8 -*-
"""规则场景注册表契约测试（spec 2026-11-09 M1/P0）。

覆盖：注册表闭合、因子轴并集投影、sourcing 灰度登记、rule_key 唯一身份、
FR-010 扩展属性不得作为因子轴。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core import rule_keys, rule_scenarios  # noqa: E402
from meta.core.models_enums import RuleType  # noqa: E402
from meta.core.rule_scenarios import (  # noqa: E402
    NOT_INSTRUMENTED_SOURCES,
    SCENARIO_FACTOR_KEYS,
    SCENARIOS,
    SOURCE_CARRIERS,
    SOURCES,
    TRACE_SCENARIO_HANDLERS,
    TRACE_SCENARIOS,
    ScenarioRegistryError,
    get_scenario,
    validate_attribute_factor_namespace,
    validate_registry,
)

VIEW_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'meta', 'schemas', 'rule_center_view.yaml'))


# ----------------------------------------------------------------------
# FR-001：注册表闭合
# ----------------------------------------------------------------------

def test_registry_is_closed():
    validate_registry()

    names = [spec.scenario for spec in SCENARIOS]
    assert len(names) == len(set(names)), '场景名不得重复'

    covered = {spec.source for spec in SCENARIOS if spec.instrumented}
    covered |= set(SOURCE_CARRIERS)
    for source in SOURCES:
        assert source in covered or source in NOT_INSTRUMENTED_SOURCES, (
            f'来源 {source!r} 既未接入 trace，也未登记为未接入来源')

    for source, carrier in SOURCE_CARRIERS.items():
        assert source in SOURCES and carrier in SOURCES
        assert carrier in {spec.source for spec in SCENARIOS if spec.instrumented}

    for spec in SCENARIOS:
        if spec.instrumented:
            assert spec.stage, f'{spec.scenario} 已接入但缺少 stage'
            assert spec.handler, f'{spec.scenario} 已接入但缺少 handler'
        else:
            assert spec.handler is None, f'{spec.scenario} 未接入却声明了 handler'


def test_derived_views_match_registry():
    assert rule_keys.RULE_SOURCES == SOURCES
    assert rule_keys.NOT_INSTRUMENTED_SOURCES == NOT_INSTRUMENTED_SOURCES
    assert set(TRACE_SCENARIOS) == {
        spec.scenario for spec in SCENARIOS if spec.instrumented}
    assert set(TRACE_SCENARIO_HANDLERS) == set(TRACE_SCENARIOS)
    assert set(SCENARIO_FACTOR_KEYS) == {spec.scenario for spec in SCENARIOS}


# ----------------------------------------------------------------------
# FR-004：全局因子轴 = 兼容场景并集投影
# ----------------------------------------------------------------------

def test_dimension_fields_are_legacy_projection():
    legacy = ('org_id', 'document_type_id', 'line_type_id', 'item_group_id')
    assert rule_keys.DIMENSION_FIELDS == legacy
    assert rule_scenarios.DIMENSION_FIELDS == legacy

    projected = tuple(dict.fromkeys(
        key for spec in SCENARIOS if spec.global_projection
        for key in spec.factor_keys
    ))
    assert projected == legacy


def test_scenario_factor_keys_are_declared_individually():
    assert SCENARIO_FACTOR_KEYS['control_parameter'] == (
        'org_id', 'document_type_id', 'line_type_id', 'item_group_id')
    assert SCENARIO_FACTOR_KEYS['line_type'] == (
        'document_type_id', 'item_group_id')
    assert SCENARIO_FACTOR_KEYS['sourcing'] == (
        'dest_org_id', 'item_id', 'usage', 'eval_date')


# ----------------------------------------------------------------------
# FR-002：sourcing 登记与枚举边界
# ----------------------------------------------------------------------

def test_sourcing_registered_as_gray_scenario():
    spec = get_scenario('sourcing')
    assert spec is not None
    assert spec.source == 'sourcing'
    assert spec.semantic_class == 'decision'
    assert spec.semantic_type == 'determination'
    assert spec.legacy_rule_type == 'sourcing'
    assert spec.hit_policy == 'first'
    assert spec.instrumented is False
    assert spec.configurable is False
    assert spec.publishable is False
    assert spec.stage_map == {
        'assignment': 'scope', 'line_filter': 'filter', 'line_pick': 'select'}

    assert 'sourcing' in SOURCES
    assert 'sourcing' in NOT_INSTRUMENTED_SOURCES
    # 灰度期不进入 trace 白名单，避免"永远跳过"的假节点
    assert 'sourcing' not in TRACE_SCENARIOS


def test_sourcing_does_not_extend_rule_type_enum():
    enum_values = {item.value for item in RuleType}
    assert 'sourcing' not in enum_values
    assert 'sourcing' in rule_keys.DERIVED_RULE_TYPES
    assert 'sourcing' in rule_keys.RULE_TYPES


# ----------------------------------------------------------------------
# FR-003：唯一 rule_key
# ----------------------------------------------------------------------

def test_sourcing_rule_key_roundtrip():
    key = rule_keys.sourcing_key('SRC-001')
    assert key == 'sourcing:SRC-001'
    assert rule_keys.split_key(key) == ('sourcing', 'SRC-001')
    assert rule_keys.split_key('unknown:SRC-001') is None


def test_catalog_sourcing_uses_same_rule_key(monkeypatch, tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.services import rule_catalog_service as catalog
    from meta.tests.factories._raw_sql_bridge import insert

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / 'catalog.db'))
    adapter.execute(
        "CREATE TABLE sourcing_rules (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " code TEXT, name TEXT, rule_usage TEXT, effectivity_start TEXT,"
        " effectivity_end TEXT, status TEXT, description TEXT, updated_at TEXT)")
    adapter.execute(
        "CREATE TABLE sourcing_rule_assignments (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " rule_id INTEGER, scope_type TEXT, scope_ref_id INTEGER,"
        " dest_org_id INTEGER, dest_location_id INTEGER,"
        " specificity_rank INTEGER, seq INTEGER, effectivity_start TEXT,"
        " effectivity_end TEXT, status TEXT)")
    insert(
        adapter, 'sourcing_rules',
        code='SRC-001', name='默认来源', rule_usage='all',
        effectivity_start='2020-01-01', status='active')
    insert(
        adapter, 'sourcing_rule_assignments',
        rule_id=1, scope_type='item', scope_ref_id=9, dest_org_id=1,
        specificity_rank=30, seq=1, effectivity_start='2020-01-01', status='active')
    monkeypatch.setattr(catalog, '_meta_db', lambda: adapter)
    try:
        items = catalog._sourcing_descriptors()
    finally:
        adapter.disconnect()

    assert len(items) == 1
    item = items[0]
    assert item['rule_key'] == rule_keys.sourcing_key('SRC-001')
    assert item['source'] == 'sourcing'
    assert item['rule_type'] == 'sourcing'
    assert item['configurable'] is False
    assert item['publishable'] is False
    assert item['links']['edit']['target'] == 'sourcing_rule'
    assert item['factors']['scope_count'] == 1
    assert 'item:9@1' in item['factors']['scope_summary']


def test_catalog_sourcing_degrades_when_table_missing(monkeypatch, tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter
    from meta.services import rule_catalog_service as catalog

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / 'empty.db'))
    monkeypatch.setattr(catalog, '_meta_db', lambda: adapter)
    try:
        with pytest.raises(catalog.RuleCatalogError):
            catalog._sourcing_descriptors()
    finally:
        adapter.disconnect()


# ----------------------------------------------------------------------
# FR-010：扩展属性不得进入因子轴
# ----------------------------------------------------------------------

def test_attribute_codes_must_not_overlap_factor_keys():
    validate_attribute_factor_namespace(['warehouse_code', 'brand'])
    for factor_key in ('item_id', 'dest_org_id', 'org_id', 'document_type_id'):
        with pytest.raises(ScenarioRegistryError):
            validate_attribute_factor_namespace(['brand', factor_key])


# ----------------------------------------------------------------------
# IF-004：视图元数据由注册表派生
# ----------------------------------------------------------------------

def test_view_config_sources_and_scenarios_follow_registry():
    from meta.services.rule_catalog_service import RuleCatalogService

    config = RuleCatalogService(view_path=VIEW_PATH).get_view_config()
    assert [entry['id'] for entry in config['sources']] == list(SOURCES)
    assert config['trace']['scenarios'] == list(TRACE_SCENARIOS)
    assert set(config['filter_options']['source']) == set(SOURCES)
    assert 'sourcing' in config['filter_options']['source']
