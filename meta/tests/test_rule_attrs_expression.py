# -*- coding: utf-8 -*-
"""attrs 表达式与输入采集测试（spec 2026-11-09 FR-007 / FR-008）。

[定位] RuleContext 注入只读惰性 attrs / item.attrs；缺失与停用返回 None，
被引用的路径才进入 trace.inputs。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.models import MetaDefaultRule, MetaField, MetaObject  # noqa: E402
from meta.core.models_enums import FieldType, ObjectType  # noqa: E402
from meta.core.rule_executor import (  # noqa: E402
    ExpressionEvaluator,
    RuleContext,
    RuleEngine,
)
from meta.tests.factories._raw_sql_bridge import insert  # noqa: E402

DDL = [
    "CREATE TABLE attribute_definitions ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER DEFAULT 0,"
    " code TEXT, name TEXT, data_type TEXT, usage_class TEXT DEFAULT 'descriptive',"
    " status TEXT DEFAULT 'active', revision INTEGER DEFAULT 1)",
    "CREATE TABLE item_attribute_values ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, attribute_id INTEGER,"
    " attr_code TEXT, org_id INTEGER, value_text TEXT, value_number REAL,"
    " value_boolean INTEGER, value_date TEXT, value_datetime TEXT)",
]


@pytest.fixture()
def ds(tmp_path):
    from meta.core.sql_adapters import SQLiteAdapter

    adapter = SQLiteAdapter()
    adapter.connect(path=str(tmp_path / 'attrs_expr.db'))
    for ddl in DDL:
        adapter.execute(ddl)
    yield adapter
    adapter.disconnect()


def _definition(ds, code, *, status='active', revision=1):
    return insert(ds, 'attribute_definitions', tenant_id=0, code=code,
                  name=code, data_type='string', usage_class='descriptive',
                  status=status, revision=revision).lastrowid


def _item_value(ds, item_id, attribute_id, code, value):
    return insert(ds, 'item_attribute_values', item_id=item_id,
                  attribute_id=attribute_id, attr_code=code, org_id=None,
                  value_text=value, value_number=None,
                  value_boolean=None, value_date=None,
                  value_datetime=None).lastrowid


def _object(object_id, fields=()):
    obj = MetaObject(id=object_id, name=object_id, table_name='t_' + object_id,
                     object_type=ObjectType.ENTITY)
    obj.fields = list(fields)
    return obj


def _context(ds, object_id='item', data=None, fields=()):
    return RuleContext(_object(object_id, fields), dict(data or {}),
                       data_source=ds)


# ----------------------------------------------------------------------
# 根对象 attrs
# ----------------------------------------------------------------------
class TestRootAttrs:
    def test_reads_value_and_records_access(self, ds):
        definition_id = _definition(ds, 'color', revision=3)
        _item_value(ds, 100, definition_id, 'color', 'red')
        context = _context(ds, data={'id': 100})

        assert ExpressionEvaluator.evaluate("attrs.color == 'red'", context) is True

        inputs = context.inputs_snapshot()
        assert inputs['attrs'] == [{
            'path': 'attrs.color',
            'code': 'color',
            'value': 'red',
            'source': 'value',
            'status': 'active',
            'definition_id': definition_id,
            'definition_version': 3,
            'reason': None,
        }]

    def test_missing_attribute_is_none_and_recorded(self, ds):
        context = _context(ds, data={'id': 100})
        assert ExpressionEvaluator.evaluate('attrs.unknown is None', context) is True

        record = context.inputs_snapshot()['attrs'][0]
        assert record['code'] == 'unknown'
        assert record['value'] is None
        assert record['source'] == 'missing'
        assert record['reason'] == 'attribute_missing'

    def test_inactive_attribute_records_reason(self, ds):
        definition_id = _definition(ds, 'legacy', status='inactive')
        _item_value(ds, 100, definition_id, 'legacy', 'old')
        context = _context(ds, data={'id': 100})

        assert ExpressionEvaluator.evaluate('attrs.legacy is None', context) is True
        record = context.inputs_snapshot()['attrs'][0]
        assert record['reason'] == 'attribute_inactive'
        assert record['status'] == 'inactive'

    def test_unreferenced_attribute_not_recorded(self, ds):
        definition_id = _definition(ds, 'color')
        _item_value(ds, 100, definition_id, 'color', 'red')
        context = _context(ds, data={'id': 100})

        assert ExpressionEvaluator.evaluate('1 + 1', context) == 2
        assert context.inputs_snapshot()['attrs'] == []
        assert context.inputs_snapshot()['fields'] == []

    def test_subscript_access(self, ds):
        definition_id = _definition(ds, 'color')
        _item_value(ds, 100, definition_id, 'color', 'blue')
        context = _context(ds, data={'id': 100})

        assert ExpressionEvaluator.evaluate("attrs['color'] == 'blue'", context) is True


# ----------------------------------------------------------------------
# 单据行 item.attrs
# ----------------------------------------------------------------------
class TestItemAttrs:
    def test_item_namespace_reads_item_values(self, ds):
        definition_id = _definition(ds, 'brand', revision=2)
        _item_value(ds, 200, definition_id, 'brand', 'ACME')
        context = _context(ds, object_id='sales_order',
                           data={'id': 1, 'item_id': 200})

        assert ExpressionEvaluator.evaluate(
            "item.attrs.brand == 'ACME'", context) is True

        record = context.inputs_snapshot()['attrs'][0]
        assert record['path'] == 'item.attrs.brand'
        assert record['value'] == 'ACME'
        assert record['definition_version'] == 2

    def test_item_missing_still_returns_none(self, ds):
        context = _context(ds, object_id='sales_order', data={'id': 1})
        assert ExpressionEvaluator.evaluate(
            'item.attrs.brand is None', context) is True
        assert context.inputs_snapshot()['attrs'][0]['path'] == 'item.attrs.brand'


# ----------------------------------------------------------------------
# 字段采集
# ----------------------------------------------------------------------
class TestFieldInputs:
    def test_only_accessed_fields_recorded(self, ds):
        context = _context(ds, object_id='sales_order',
                           data={'order_type': 'ZOR', 'unused': 'x'})
        assert ExpressionEvaluator.evaluate(
            "order_type == 'ZOR'", context) is True

        fields = context.inputs_snapshot()['fields']
        assert [item['path'] for item in fields] == ['order_type']
        assert fields[0]['value'] == 'ZOR'
        assert fields[0]['source'] == 'data'

    def test_fields_and_attrs_share_one_snapshot(self, ds):
        definition_id = _definition(ds, 'color')
        _item_value(ds, 100, definition_id, 'color', 'red')
        context = _context(ds, data={'id': 100, 'order_type': 'ZOR'})

        assert ExpressionEvaluator.evaluate(
            "order_type == 'ZOR' and attrs.color == 'red'", context) is True

        inputs = context.inputs_snapshot()
        assert [item['path'] for item in inputs['fields']] == ['order_type']
        assert [item['path'] for item in inputs['attrs']] == ['attrs.color']


# ----------------------------------------------------------------------
# 默认值规则同一求值链路
# ----------------------------------------------------------------------
class TestDefaultRuleIntegration:
    def test_default_rule_log_carries_attr_inputs(self, ds):
        definition_id = _definition(ds, 'color')
        _item_value(ds, 100, definition_id, 'color', 'red')

        obj = _object('item', [MetaField(
            id='result', name='结果', field_type=FieldType.STRING,
            db_column='result')])
        obj.rules = [MetaDefaultRule(
            id='d1', name='d1', target_fields=['result'],
            condition="attrs.color == 'red'",
            source_type='constant', source_value='APPLIED',
        )]
        context = RuleContext(obj, {'id': 100, 'result': ''},
                              data_source=ds)

        logs = RuleEngine().default_by_priority(obj, context)

        assert context.data['result'] == 'APPLIED'
        assert logs[0].inputs['attrs'][0]['path'] == 'attrs.color'
        assert logs[0].inputs['attrs'][0]['value'] == 'red'
        assert logs[0].to_dict()['inputs']['attrs'][0]['code'] == 'color'
