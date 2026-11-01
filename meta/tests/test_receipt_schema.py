# -*- coding: utf-8 -*-
"""收货对象元数据测试（spec-receipt-object-model §3 / §4 / §12）

只校验 YAML 声明（不连 DB）：字段 / 枚举 / 父子关系 / 菜单三态配置。
"""

import pathlib

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA_DIR = pathlib.Path(__file__).resolve().parents[1] / 'schemas'

# document_type_id 由文档类型切面（document_type_aspect）提供，不在 fields 显式声明
RECEIPT_FIELDS = {
    'id', 'receipt_no', 'receipt_date',
    'actual_arrival_date', 'source_doc_type', 'source_doc_id', 'source_doc_no',
    'supplier_party_id', 'supplier_delivery_no', 'org_id', 'purchase_org_id',
    'deliver_to_location_id', 'project_id', 'received_by', 'status',
    'reversal_of_receipt_id', 'remark', 'created_at', 'updated_at',
}

RECEIPT_LINE_FIELDS = {
    'id', 'receipt_id', 'line_no', 'schedule_id', 'source_line_id', 'order_id',
    'order_line_id', 'item_id', 'uom_id', 'qty_received', 'qty_rejected',
    'rejection_reason_code', 'rejection_disposition', 'lot_no', 'serial_no',
    'putaway_location_id', 'status', 'reversal_of_line_id', 'created_at',
    'updated_at',
}

STATUS_VALUES = {'draft', 'posted', 'reversed', 'cancelled'}
DISPOSITIONS = {'return_to_supplier', 'concession', 'scrap', 'rework'}


def _load(name):
    return yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _fields(doc):
    return {f['id']: f for f in doc['fields']}


def _enum_values(field):
    return {item['value'] for item in field.get('enum_values') or []}


@pytest.fixture(scope='module')
def receipt_doc():
    return _load('receipt.yaml')


@pytest.fixture(scope='module')
def line_doc():
    return _load('receipt_line.yaml')


def test_receipt_header_fields_complete(receipt_doc):
    assert receipt_doc['table_name'] == 'receipts'
    assert RECEIPT_FIELDS <= set(_fields(receipt_doc))


def test_receipt_status_enum(receipt_doc):
    field = _fields(receipt_doc)['status']
    assert _enum_values(field) == STATUS_VALUES
    assert field['default'] == 'draft'


def test_receipt_source_doc_type_is_enum(receipt_doc):
    field = _fields(receipt_doc)['source_doc_type']
    values = _enum_values(field)
    assert 'purchase_order' in values
    assert len(values) == 5


def test_receipt_line_fields_complete(line_doc):
    assert line_doc['table_name'] == 'receipt_lines'
    assert line_doc['parent_object'] == 'receipt'
    assert RECEIPT_LINE_FIELDS <= set(_fields(line_doc))


def test_receipt_line_qty_constraints(line_doc):
    fields = _fields(line_doc)
    received = fields['qty_received']
    assert received['required'] is True
    assert received['constraints'][0]['gt'] == 0
    rejected = fields['qty_rejected']
    assert rejected['default'] == 0
    assert rejected['constraints'][0]['gte'] == 0


def test_receipt_line_rejection_disposition_enum(line_doc):
    field = _fields(line_doc)['rejection_disposition']
    assert _enum_values(field) == DISPOSITIONS


def test_receipt_line_has_dual_anchors(line_doc):
    fields = _fields(line_doc)
    assert fields['schedule_id'].get('nullable') is True
    assert fields['source_line_id'].get('nullable') is True


def test_receipt_has_child_section_for_lines(receipt_doc):
    children = receipt_doc['ui_view_config'].get('child_sections') or []
    assert [c['child_object'] for c in children] == ['receipt_line']


def test_line_skips_auto_menu(line_doc):
    assert line_doc['ui_view_config']['skip_auto_menu'] is True


def test_both_objects_declare_list_and_form(receipt_doc, line_doc):
    for doc in (receipt_doc, line_doc):
        view = doc['ui_view_config']
        assert view['list']['columns']
        assert view['form']['sections']
