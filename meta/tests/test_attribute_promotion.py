# -*- coding: utf-8 -*-
"""属性提升与影响面测试（spec 2026-11-09 §9.5 P2 / FR-009 / FR-012 / TBD-003）。

[定位]
  - promotion 状态机：pending → column_created → backfilled → verified → active；
  - 建列 / 回填 / 校验 / 切换（cutover）与 AttributeProvider 读取口径；
  - 已提升属性的值表写入保护；
  - 每日一致性校验只报告差异、不自动回滚；
  - 影响面分析（attrs 引用扫描）与视图变量下发（IF-004）。
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
from meta.migrations import v232__attribute_promotion as v232  # noqa: E402
from meta.services.attribute_impact_service import AttributeImpactService  # noqa: E402
from meta.services.attribute_promotion_service import (  # noqa: E402
    AttributePromotionError,
    AttributePromotionService,
)
from meta.services.attribute_value_service import (  # noqa: E402
    AttributeValueError,
)
from meta.tests.factories._raw_sql_bridge import insert, update  # noqa: E402

DDL = [
    "CREATE TABLE attribute_definitions ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,"
    " code TEXT, name TEXT, data_type TEXT DEFAULT 'string',"
    " multi_value_flag INTEGER DEFAULT 0, status TEXT DEFAULT 'active',"
    " usage_class TEXT DEFAULT 'descriptive', revision INTEGER DEFAULT 1)",
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
    "CREATE TABLE items (id INTEGER PRIMARY KEY, item_code TEXT, potency_pct REAL)",
    "CREATE TABLE parties (id INTEGER PRIMARY KEY, party_code TEXT, credit_grade TEXT)",
    v232.PROMOTION_TABLE_DDL,
]


@pytest.fixture()
def ds(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / 'attribute_promotion.db'))
    for ddl in DDL:
        adapter.execute(ddl)
    yield adapter
    AttributeProvider.invalidate()
    adapter.disconnect()


def _definition(ds, code, *, tenant_id=0, data_type='number',
                multi_value_flag=0, status='active'):
    return insert(
        ds, 'attribute_definitions', tenant_id=tenant_id, code=code,
        name=code, data_type=data_type, multi_value_flag=multi_value_flag,
        status=status).lastrowid


def _item_value(ds, item_id, attribute_id, code, value, org_id=None):
    return insert(
        ds, 'item_attribute_values', item_id=item_id,
        attribute_id=attribute_id, attr_code=code, org_id=org_id,
        value_number=value if isinstance(value, (int, float)) else None,
        value_text=value if isinstance(value, str) else None).lastrowid


def _item(ds, item_id, code='I'):
    insert(ds, 'items', id=item_id, item_code=code, potency_pct=None)


def test_state_machine_and_duplicate(ds):
    attribute_id = _definition(ds, 'potency_pct')
    _item(ds, 1)
    service = AttributePromotionService(ds)

    record = service.create('item', 'potency_pct')
    assert record['status'] == 'pending'
    assert record['data_type'] == 'number'

    with pytest.raises(AttributePromotionError) as exc:
        service.transition(record['id'], 'active')
    assert exc.value.rule == 'promotion_transition_invalid'

    with pytest.raises(AttributePromotionError) as exc:
        service.create('item', 'potency_pct')
    assert exc.value.rule == 'promotion_exists'

    service.create_column(record['id'])
    service.backfill(record['id'])
    assert service.get(record['id'])['status'] == 'backfilled'
    service.verify(record['id'])
    assert service.get(record['id'])['status'] == 'verified'
    service.activate(record['id'])
    assert service.get(record['id'])['status'] == 'active'

    with pytest.raises(AttributePromotionError) as exc:
        service.transition(record['id'], 'verified')
    assert exc.value.rule == 'promotion_transition_invalid'


def test_create_rejects_unsafe_or_unsupported(ds):
    service = AttributePromotionService(ds)
    _definition(ds, 'tenant_attr', tenant_id=9)
    _definition(ds, 'multi_attr', multi_value_flag=1)
    _definition(ds, 'off_attr', status='inactive')

    cases = [
        (('item', 'bad code'), 'promotion_attribute_code_invalid'),
        (('unknown', 'x'), 'promotion_object_unknown'),
        (('item', 'tenant_attr'), 'promotion_platform_only'),
        (('item', 'multi_attr'), 'promotion_multi_value'),
        (('item', 'off_attr'), 'promotion_definition_inactive'),
        (('item', 'missing_attr'), 'promotion_definition_missing'),
    ]
    for args, rule in cases:
        with pytest.raises(AttributePromotionError) as exc:
            service.create(*args)
        assert exc.value.rule == rule

    _definition(ds, 'unsafe_target')
    with pytest.raises(AttributePromotionError) as exc:
        service.create('item', 'unsafe_target', target_table='items;drop')
    assert exc.value.rule == 'promotion_identifier_invalid'

    _definition(ds, 'bad_mode')
    with pytest.raises(AttributePromotionError) as exc:
        service.create('item', 'bad_mode', sync_mode='mirror')
    assert exc.value.rule == 'promotion_sync_mode_invalid'


def test_backfill_verify_activate_cutover_and_write_guard(ds):
    attribute_id = _definition(ds, 'potency_pct')
    _item_value(ds, 1, attribute_id, 'potency_pct', 98.5)
    _item_value(ds, 2, attribute_id, 'potency_pct', 12.0)
    _item(ds, 1, 'A')
    _item(ds, 2, 'B')

    service = AttributePromotionService(ds)
    record = service.create('item', 'potency_pct')
    service.create_column(record['id'])
    record = service.backfill(record['id'])
    assert record['backfilled_count'] == 2

    result = service.verify(record['id'])
    assert (result['status'], result['checked'], result['mismatched']) == (
        'verified', 2, 0)
    service.activate(record['id'])

    provider = AttributeProvider(ds)
    values = provider.resolve('item', [1, 2], ['potency_pct'])
    assert values['1']['potency_pct']['value'] == 98.5
    assert values['1']['potency_pct']['source'] == SOURCE_VALUE

    # 物理列成为唯一 owner：改物理列后 Provider 立即读新值
    update(ds, 'items', {'id': 1}, potency_pct=50.0)
    AttributeProvider.invalidate(object_type='item', codes=['potency_pct'])
    assert provider.resolve('item', [1], ['potency_pct'])['1'][
        'potency_pct']['value'] == 50.0

    # 物理列 NULL 不回落值表（值表仍有 12.0）
    update(ds, 'items', {'id': 2}, potency_pct=None)
    AttributeProvider.invalidate(object_type='item', codes=['potency_pct'])
    entry = provider.resolve('item', [2], ['potency_pct'])['2']['potency_pct']
    assert entry['value'] is None
    assert entry['source'] == SOURCE_MISSING

    # 值表写入被拒（rule = attribute_promoted）
    value_service = __import__(
        'meta.services.attribute_value_service',
        fromlist=['AttributeValueService']).AttributeValueService.for_object(
            'item', ds)
    with pytest.raises(AttributeValueError) as exc:
        value_service.validate_write({
            'attribute_id': attribute_id,
            'attr_code': 'potency_pct',
            'value_number': 1.0,
        })
    assert exc.value.rule == 'attribute_promoted'


def test_verify_detects_mismatch_and_consistency_only_reports(ds):
    attribute_id = _definition(ds, 'potency_pct')
    value_row = _item_value(ds, 1, attribute_id, 'potency_pct', 10.0)
    _item(ds, 1)

    service = AttributePromotionService(ds)
    record = service.create('item', 'potency_pct')
    service.create_column(record['id'])
    service.backfill(record['id'])

    update(ds, 'item_attribute_values', {'id': value_row}, value_number=20.0)
    result = service.verify(record['id'])
    assert result['mismatched'] == 1
    assert result['status'] == 'backfilled'
    assert result['diffs'][0]['expected'] == 20.0

    # 修正物理列后可继续前进
    update(ds, 'items', {'id': 1}, potency_pct=20.0)
    assert service.verify(record['id'])['status'] == 'verified'
    service.activate(record['id'])

    # 切换后值表再漂移：只报告，不回滚状态
    update(ds, 'item_attribute_values', {'id': value_row}, value_number=30.0)
    report = service.check_consistency()
    assert len(report) == 1
    assert report[0]['mismatched'] == 1
    assert service.get(record['id'])['status'] == 'active'
    AttributeProvider.invalidate()
    entry = AttributeProvider(ds).resolve(
        'item', [1], ['potency_pct'])['1']['potency_pct']
    assert entry['value'] == 20.0


def test_impact_service_scans_rule_expressions():
    class _Rule:
        def __init__(self, rule_id, **fields):
            self.id = rule_id
            self.name = rule_id
            for key, value in fields.items():
                setattr(self, key, value)

    class _Object:
        def __init__(self, object_id, rules):
            self.id = object_id
            self.rules = rules

    registry = type('Registry', (), {
        'all': lambda self: [
            _Object('item', [
                _Rule('r1', condition='attrs.potency_pct > 90'),
                _Rule('r2', action="item.attrs['potency_pct'] = 1"),
                _Rule('r3', formula='attrs.potency_pct_x + 1'),
            ]),
            _Object('party', [
                _Rule('r4', source_value='related.attrs.credit_grade'),
            ]),
        ],
    })()

    impacts = AttributeImpactService(
        registry=registry).find_rule_references('potency_pct')
    assert [(item['rule_id'], item['field']) for item in impacts] == [
        ('r1', 'condition'), ('r2', 'action')]
    assert impacts[0]['object_type'] == 'item'
    assert impacts[0]['attribute_code'] == 'potency_pct'

    assert AttributeImpactService(registry=registry).find_rule_references(
        'potency_pct', object_type='party') == []
    assert AttributeImpactService(registry=registry).find_many_rule_references(
        ['credit_grade'])['credit_grade'][0]['field'] == 'source_value'


def test_view_config_derives_scenario_factor_keys_and_variables():
    from meta.services.rule_catalog_service import (
        VIEW_CONFIG_PATH,
        RuleCatalogService,
    )

    class _FakeDataSource:
        def query(self, sql, params=None):
            if 'JOIN attribute_definitions' in sql:
                return [{
                    'attribute_id': 1, 'code': 'potency_pct',
                    'label': '含量', 'data_type': 'number',
                    'usage_class': 'descriptive', 'tenant_id': 0,
                    'scope_type': 'object',
                }]
            if 'FROM attribute_scopes' in sql:
                return [{'scope_ref': 'item'}]
            return []

    config = RuleCatalogService(
        view_path=VIEW_CONFIG_PATH).get_view_config(
            data_source=_FakeDataSource())

    factor_keys = config['trace']['scenario_factor_keys']
    assert factor_keys['sourcing'] == [
        'dest_org_id', 'item_id', 'usage', 'eval_date']
    assert factor_keys['control_parameter'] == [
        'org_id', 'document_type_id', 'line_type_id', 'item_group_id']
    assert config['trace']['factor_keys']
    assert config['attribute_variables'] == {
        'item': [{
            'attribute_id': 1, 'code': 'potency_pct', 'label': '含量',
            'data_type': 'number', 'scope_level': 'object', 'tenant_id': 0,
        }],
    }


def test_migration_is_idempotent(tmp_path):
    import sqlite3

    db_path = str(tmp_path / 'migration.db')
    sqlite3.connect(db_path).close()
    v232.migrate(db_path)
    v232.migrate(db_path)
    result = v232.verify(db_path)
    assert result['ok'] is True
    assert result['checks']['required_columns'] is True
