# -*- coding: utf-8 -*-
"""AttributeProvider 契约测试（spec 2026-11-09 FR-006 / FR-009 / FR-011）。

[定位] 扩展属性唯一读取入口：两套物理表形状、定义层级、缺失/停用语义、
缓存与失效、可配置变量清单。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.attribute_provider import (  # noqa: E402
    AttributeProvider,
    SOURCE_MISSING,
    SOURCE_VALUE,
)
from meta.tests.factories._raw_sql_bridge import insert  # noqa: E402

DDL = [
    "CREATE TABLE attribute_definitions ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,"
    " code TEXT, name TEXT, data_type TEXT, usage_class TEXT DEFAULT 'descriptive',"
    " status TEXT DEFAULT 'active', revision INTEGER DEFAULT 1)",
    "CREATE TABLE attribute_scopes ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,"
    " attribute_id INTEGER, scope_type TEXT DEFAULT 'object', scope_ref TEXT,"
    " required_flag INTEGER DEFAULT 0, seq INTEGER DEFAULT 10,"
    " status TEXT DEFAULT 'active')",
    "CREATE TABLE item_attribute_values ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, attribute_id INTEGER,"
    " attr_code TEXT, org_id INTEGER, value_text TEXT, value_number REAL,"
    " value_boolean INTEGER, value_date TEXT, value_datetime TEXT)",
    "CREATE TABLE party_attribute_values ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,"
    " party_id INTEGER, attribute_id INTEGER, seq INTEGER DEFAULT 1,"
    " value_text TEXT, value_number REAL, value_boolean INTEGER,"
    " value_date TEXT, value_datetime TEXT)",
]


@pytest.fixture()
def ds(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / 'attribute_provider.db'))
    for ddl in DDL:
        adapter.execute(ddl)
    yield adapter
    adapter.disconnect()


def _definition(ds, code, *, tenant_id=0, data_type='string', status='active',
                revision=1, usage_class='descriptive'):
    return insert(
        ds, 'attribute_definitions', tenant_id=tenant_id, code=code,
        name=code, data_type=data_type, usage_class=usage_class,
        status=status, revision=revision).lastrowid


def _item_value(ds, item_id, attribute_id, code, value, org_id=None):
    column = 'value_number' if isinstance(value, (int, float)) else 'value_text'
    payload = {'value_text': None, 'value_number': None}
    payload[column] = value
    return insert(
        ds, 'item_attribute_values', item_id=item_id,
        attribute_id=attribute_id, attr_code=code, org_id=org_id,
        **payload).lastrowid


def _party_value(ds, party_id, attribute_id, value, *, tenant_id=0, seq=1):
    column = 'value_number' if isinstance(value, (int, float)) else 'value_text'
    payload = {'value_text': None, 'value_number': None}
    payload[column] = value
    return insert(
        ds, 'party_attribute_values', tenant_id=tenant_id, party_id=party_id,
        attribute_id=attribute_id, seq=seq, **payload).lastrowid


# ----------------------------------------------------------------------
# 读取：两套表形状
# ----------------------------------------------------------------------
class TestResolveShapes:
    def test_item_shape_reads_attr_code(self, ds):
        definition_id = _definition(ds, 'color', revision=3)
        _item_value(ds, 100, definition_id, 'color', 'red')

        result = AttributeProvider(ds).resolve('item', [100], ['color'])
        entry = result['100']['color']

        assert entry['value'] == 'red'
        assert entry['source'] == SOURCE_VALUE
        assert entry['status'] == 'active'
        assert entry['definition_id'] == definition_id
        assert entry['definition_version'] == 3

    def test_party_shape_joins_definition(self, ds):
        definition_id = _definition(ds, 'size', data_type='number')
        _party_value(ds, 7, definition_id, 42)

        entry = AttributeProvider(ds).resolve(
            'party', [7], ['size'])['7']['size']

        assert entry['value'] == 42
        assert entry['source'] == SOURCE_VALUE
        assert entry['definition_version'] == 1

    def test_multi_value_takes_first_seq(self, ds):
        definition_id = _definition(ds, 'tag')
        _party_value(ds, 7, definition_id, 'second', seq=2)
        _party_value(ds, 7, definition_id, 'first', seq=1)

        entry = AttributeProvider(ds).resolve(
            'party', [7], ['tag'])['7']['tag']
        assert entry['value'] == 'first'

    def test_org_specific_value_preferred(self, ds):
        definition_id = _definition(ds, 'color')
        _item_value(ds, 100, definition_id, 'color', 'global')
        _item_value(ds, 100, definition_id, 'color', 'org-red', org_id=9)

        default_entry = AttributeProvider(ds).resolve(
            'item', [100], ['color'])['100']['color']
        org_entry = AttributeProvider(ds).resolve(
            'item', [100], ['color'], org_id=9)['100']['color']

        assert default_entry['value'] == 'global'
        assert org_entry['value'] == 'org-red'


# ----------------------------------------------------------------------
# 定义层级与缺失语义
# ----------------------------------------------------------------------
class TestDefinitions:
    def test_tenant_definition_overrides_platform(self, ds):
        _definition(ds, 'size', tenant_id=0, revision=1)
        tenant_definition_id = _definition(
            ds, 'size', tenant_id=5, revision=2)
        _party_value(ds, 7, tenant_definition_id, 88, tenant_id=5)

        entry = AttributeProvider(ds, tenant_id=5).resolve(
            'party', [7], ['size'])['7']['size']

        assert entry['value'] == 88
        assert entry['definition_id'] == tenant_definition_id
        assert entry['definition_version'] == 2

    def test_disabled_definition_is_missing_with_status(self, ds):
        definition_id = _definition(ds, 'legacy', status='inactive')
        _item_value(ds, 100, definition_id, 'legacy', 'old')

        entry = AttributeProvider(ds).resolve(
            'item', [100], ['legacy'])['100']['legacy']

        assert entry['value'] is None
        assert entry['source'] == SOURCE_MISSING
        assert entry['status'] == 'inactive'

    def test_unknown_code_is_missing(self, ds):
        entry = AttributeProvider(ds).resolve(
            'item', [100], ['nope'])['100']['nope']
        assert entry['value'] is None
        assert entry['source'] == SOURCE_MISSING
        assert entry['definition_id'] is None

    def test_unknown_object_type_returns_missing(self, ds):
        result = AttributeProvider(ds).resolve('account', [1], ['x'])
        assert result['1']['x']['source'] == SOURCE_MISSING

    def test_missing_table_returns_missing(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        adapter = SQLiteAdapter()
        adapter.connect(path=str(tmp_path / 'empty.db'))
        try:
            entry = AttributeProvider(adapter).resolve(
                'item', [100], ['color'])['100']['color']
            assert entry['source'] == SOURCE_MISSING
        finally:
            adapter.disconnect()

    def test_missing_value_row_is_missing(self, ds):
        definition_id = _definition(ds, 'color', revision=2)
        entry = AttributeProvider(ds).resolve(
            'item', [100], ['color'])['100']['color']
        assert entry['value'] is None
        assert entry['source'] == SOURCE_MISSING
        assert entry['definition_id'] == definition_id
        assert entry['definition_version'] == 2


# ----------------------------------------------------------------------
# 缓存与失效（FR-011）
# ----------------------------------------------------------------------
class TestCache:
    def test_cache_then_invalidate(self, ds):
        definition_id = _definition(ds, 'color')
        provider = AttributeProvider(ds)

        assert provider.resolve('item', [100], ['color'])[
            '100']['color']['source'] == SOURCE_MISSING

        # 写入（模拟值表新增）后未失效：命中旧缓存
        _item_value(ds, 100, definition_id, 'color', 'red')
        assert provider.resolve('item', [100], ['color'])[
            '100']['color']['source'] == SOURCE_MISSING

        removed = AttributeProvider.invalidate(object_type='item')
        assert removed >= 1
        entry = provider.resolve('item', [100], ['color'])['100']['color']
        assert entry['value'] == 'red'

    def test_invalidate_by_code(self, ds):
        definition_id = _definition(ds, 'color')
        provider = AttributeProvider(ds)
        provider.resolve('item', [100], ['color'])
        provider.resolve('item', [100], ['size'])

        assert AttributeProvider.invalidate(codes=['color']) >= 1
        _item_value(ds, 100, definition_id, 'color', 'blue')
        assert provider.resolve('item', [100], ['color'])[
            '100']['color']['value'] == 'blue'

    def test_cache_is_isolated_per_data_source(self, ds, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        definition_id = _definition(ds, 'color')
        _item_value(ds, 100, definition_id, 'color', 'red')

        other = SQLiteAdapter()
        other.connect(path=str(tmp_path / 'other.db'))
        for ddl in DDL:
            other.execute(ddl)
        try:
            assert AttributeProvider(ds).resolve(
                'item', [100], ['color'])['100']['color']['value'] == 'red'
            assert AttributeProvider(other).resolve(
                'item', [100], ['color'])['100']['color']['source'] == SOURCE_MISSING
        finally:
            other.disconnect()


# ----------------------------------------------------------------------
# 可配置变量清单
# ----------------------------------------------------------------------
class TestAvailableVariables:
    def test_filters_scope_usage_and_status(self, ds):
        descriptive = _definition(ds, 'color')
        analytic = _definition(ds, 'weight', usage_class='analytic')
        computed = _definition(ds, 'margin', usage_class='computed')
        inactive = _definition(ds, 'legacy', status='inactive')

        for attribute_id in (descriptive, analytic, computed, inactive):
            insert(ds, 'attribute_scopes', attribute_id=attribute_id,
                   scope_type='object', scope_ref='item', status='active')
        insert(ds, 'attribute_scopes', attribute_id=analytic,
               scope_type='item_group', scope_ref='G1', status='active')

        variables = AttributeProvider(ds).available_variables('item')
        codes = [item['code'] for item in variables]

        assert 'color' in codes
        assert 'weight' in codes
        assert 'margin' not in codes
        assert 'legacy' not in codes

        color = next(item for item in variables if item['code'] == 'color')
        assert color['label'] == 'color'
        assert color['data_type'] == 'string'
        assert color['scope_level'] == 'object'

    def test_tenant_variable_wins(self, ds):
        platform_id = _definition(ds, 'size', data_type='string')
        tenant_id = _definition(ds, 'size', tenant_id=5, data_type='number')
        insert(ds, 'attribute_scopes', attribute_id=platform_id,
               scope_type='object', scope_ref='party', tenant_id=0)
        insert(ds, 'attribute_scopes', attribute_id=tenant_id,
               scope_type='object', scope_ref='party', tenant_id=5)

        variables = AttributeProvider(ds, tenant_id=5).available_variables('party')
        assert len([item for item in variables if item['code'] == 'size']) == 1
        assert variables[0]['data_type'] == 'number'
        assert variables[0]['tenant_id'] == 5

    def test_missing_tables_return_empty(self, tmp_path):
        from meta.core.sql_adapters import SQLiteAdapter

        adapter = SQLiteAdapter()
        adapter.connect(path=str(tmp_path / 'no_scopes.db'))
        try:
            assert AttributeProvider(adapter).available_variables('item') == []
        finally:
            adapter.disconnect()
