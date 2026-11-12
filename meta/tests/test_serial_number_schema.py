# -*- coding: utf-8 -*-
"""P6a 序列号三对象 schema 声明测试（spec §3 / §4）。

只校验 YAML（不连 DB）：字段 / 索引 / 只读动作 / 菜单承载 / 单据行快捷录入长度。
"""

import pathlib

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

SERIAL_FIELDS = {
    'id', 'item_id', 'org_id', 'serial_no', 'uii', 'batch_id', 'revision',
    'usage_status', 'quality_status', 'current_location_id', 'parent_serial_id',
    'relation_type', 'parent_item_id', 'source_type', 'source_doc_type',
    'source_doc_id', 'received_at', 'produced_at', 'shipped_at', 'scrapped_at',
    'remark', 'created_at', 'updated_at',
}

TX_FIELDS = {
    'id', 'serial_id', 'inventory_transaction_id', 'txn_type', 'txn_date',
    'org_from_id', 'org_to_id', 'location_from_id', 'location_to_id',
    'batch_from_id', 'batch_to_id', 'usage_from', 'usage_to', 'quality_from',
    'quality_to', 'doc_type', 'doc_id', 'line_id', 'remark', 'created_at',
}

LINK_FIELDS = {
    'id', 'doc_type', 'doc_id', 'line_id', 'serial_id', 'direction',
    'created_at',
}


def _load(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _fields(doc):
    return {f['id']: f for f in doc['fields']}


def _index_names(doc):
    return {index['name'] for index in doc.get('indexes') or []}


@pytest.fixture(scope='module')
def serial_doc():
    return _load('serial_number.yaml')


@pytest.fixture(scope='module')
def tx_doc():
    return _load('serial_transaction.yaml')


@pytest.fixture(scope='module')
def link_doc():
    return _load('document_serial_link.yaml')


# ---------------- serial_numbers 主档 ----------------

def test_serial_number_fields_complete(serial_doc):
    assert serial_doc['table_name'] == 'serial_numbers'
    assert serial_doc['display_name_field'] == 'serial_no'
    assert 'audit_aspect' in serial_doc['aspects']
    assert SERIAL_FIELDS <= set(_fields(serial_doc))


def test_serial_number_unique_key_and_partial_uii(serial_doc):
    fields = _fields(serial_doc)
    assert fields['serial_no']['max_length'] == 64
    assert fields['serial_no']['semantics']['business_key'] is True
    assert serial_doc['indexes'][0] == {
        'fields': ['item_id', 'org_id', 'serial_no'],
        'unique': True,
        'name': 'uq_serial_number',
        'description': '同一物料同一组织内序列号唯一',
    }
    uii_index = next(i for i in serial_doc['indexes']
                     if i['name'] == 'uq_serial_uii')
    assert uii_index['unique'] is True
    assert uii_index['type'] == 'partial'
    assert uii_index['condition'] == 'uii IS NOT NULL'


def test_serial_number_indexes_and_three_axis_status(serial_doc):
    assert _index_names(serial_doc) == {
        'uq_serial_number', 'uq_serial_uii', 'idx_serial_org_item',
        'idx_serial_parent', 'idx_serial_status',
    }
    fields = _fields(serial_doc)
    assert fields['usage_status']['default'] == 'defined'
    assert fields['quality_status']['default'] == 'unrestricted'
    assert {i['value'] for i in fields['usage_status']['enum_values']} == {
        'defined', 'in_stores', 'in_transit', 'issued', 'shipped',
        'consumed', 'returned', 'scrapped',
    }
    assert {i['value'] for i in fields['quality_status']['enum_values']} == {
        'unrestricted', 'inspection', 'blocked',
    }
    assert {i['value'] for i in fields['source_type']['enum_values']} == {
        'received', 'produced', 'opening', 'issue_created',
    }


def test_serial_number_three_state_ui(serial_doc):
    view = serial_doc['ui_view_config']
    assert view['skip_auto_menu'] is True
    assert [c['field'] for c in view['list']['columns']] == [
        'serial_no', 'item_id', 'org_id', 'batch_id', 'usage_status',
        'quality_status', 'current_location_id',
    ]
    assert [s['title'] for s in view['form']['sections']] == [
        '身份', '归属', '状态', '谱系', '来源',
    ]
    assert [t['id'] for t in view['detail']['tabs']] == [
        'basic', 'lineage', 'source',
    ]


def test_serial_number_four_permissions(serial_doc):
    actions = serial_doc['ui_view_config']['list']['actions']
    assert [a['permission'] for a in actions] == [
        'serial_number:create',
    ]
    category = serial_doc['category_config']
    assert category['create_permission'] == 'serial_number:create'
    assert category['update_permission'] == 'serial_number:update'
    assert category['delete_permission'] == 'serial_number:delete'


# ---------------- 事件账 / 对象清单（只读面） ----------------

@pytest.mark.parametrize('doc_name,fields,permission_prefix', [
    ('serial_transaction.yaml', TX_FIELDS, 'serial_transaction'),
    ('document_serial_link.yaml', LINK_FIELDS, 'document_serial_link'),
])
def test_readonly_objects(doc_name, fields, permission_prefix):
    doc = _load(doc_name)
    assert fields <= set(_fields(doc))
    assert doc['import_export']['auto_crud'] is False
    assert doc['ui_view_config']['skip_auto_menu'] is True
    assert {a['id'] for a in doc['actions']} == {
        '%s_read' % permission_prefix, '%s_list' % permission_prefix,
    }
    assert doc['authorization']['permissions']['read'] == \
        '%s:read' % permission_prefix
    assert doc['authorization']['permissions']['list'] == \
        '%s:read' % permission_prefix


def test_transaction_indexes(tx_doc):
    assert _index_names(tx_doc) == {
        'idx_serial_tx_serial_date', 'idx_serial_tx_inv_tx', 'idx_serial_tx_doc',
    }


def test_document_link_unique_and_indexes(link_doc):
    assert _index_names(link_doc) == {
        'uq_document_serial_link', 'idx_document_serial_doc',
        'idx_document_serial_serial',
    }
    unique = next(i for i in link_doc['indexes']
                  if i['name'] == 'uq_document_serial_link')
    assert unique['fields'] == ['doc_type', 'line_id', 'serial_id']
    assert unique['unique'] is True


# ---------------- 单据行快捷录入（D7） ----------------

@pytest.mark.parametrize('doc_name', ['receipt_line.yaml', 'shipment_line.yaml'])
def test_line_serial_no_is_quick_entry_only(doc_name):
    field = _fields(_load(doc_name))['serial_no']
    assert field['max_length'] == 200
    assert 'qty=1' in field['description']
    assert 'qty>1' in field['description']


def test_items_serial_switches():
    fields = _fields(_load('items.yaml'))
    for column in ('serial_tracked', 'require_on_receipt', 'require_on_issue'):
        assert fields[column]['type'] == 'boolean'
        assert fields[column]['default'] is False
        assert fields[column]['ui']['fieldGroup'] == '序列号'
