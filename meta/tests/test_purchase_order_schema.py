# -*- coding: utf-8 -*-
"""采购订单对象模型 schema 断言（M3 / spec §14 步骤 14）

依据 `docs/specs/spec-purchase-order-object-model-2026-11-01.md` §3 / §4 / §5 / §9 / §10 / §15
口径：只读真实 YAML，字段 / 状态机 / 索引 / 关系漂移立即失败。
"""

import os
from pathlib import Path

os.environ.setdefault('ALLOW_RAW_SQL', '1')

import pytest
import yaml

pytestmark = pytest.mark.unit

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'


def _load(name):
    return yaml.safe_load((_SCHEMA_DIR / name).read_text(encoding='utf-8'))


def _fields(schema):
    return {f['id']: f for f in schema['fields']}


def _rules(schema):
    return {r['id']: r for r in schema['rules']}


def test_schema_files_exist():
    for name in ('purchase_order.yaml', 'purchase_order_line.yaml',
                 'purchase_order_schedule.yaml', 'demand_allocation.yaml'):
        assert (_SCHEMA_DIR / name).exists(), name


def test_header_uses_document_type_aspect():
    schema = _load('purchase_order.yaml')
    fields = _fields(schema)
    assert 'document_type_aspect' in schema['aspects']
    assert 'document_type_id' not in fields  # 切面注入，单据 YAML 不重复声明
    assert schema['table_name'] == 'purchase_orders'


def test_header_business_key_and_required_fields():
    fields = _fields(_load('purchase_order.yaml'))
    order_no = fields['order_no']
    assert order_no['required'] is True and order_no['unique'] is True
    assert order_no['semantics'].get('immutable') is True
    for name in ('order_date', 'supplier_party_id', 'org_id',
                 'purchase_org_id', 'currency_id'):
        assert fields[name]['required'] is True, name


def test_header_status_enum():
    fields = _fields(_load('purchase_order.yaml'))
    status = {v['value']: v for v in fields['status']['enum_values']}
    assert set(status) == {'draft', 'submitted', 'confirmed', 'closed', 'cancelled'}
    assert status['draft'].get('is_initial') is True


def test_approval_status_is_orthogonal_cache():
    fields = _fields(_load('purchase_order.yaml'))
    approval = {v['value']: v for v in fields['approval_status']['enum_values']}
    assert set(approval) == {'not_required', 'pending', 'approved', 'rejected'}
    assert approval['not_required'].get('is_initial') is True
    assert fields['approval_status'].get('ui', {}).get('readonly') is True


def test_header_state_machine_rules():
    schema = _load('purchase_order.yaml')
    rules = _rules(schema)
    assert rules['submit_purchase_order']['from_states'] == ['draft']
    assert rules['submit_purchase_order']['to_state'] == 'submitted'
    assert rules['approve_purchase_order']['from_states'] == ['submitted']
    assert rules['approve_purchase_order']['to_state'] == 'confirmed'
    assert rules['reject_purchase_order']['from_states'] == ['submitted']
    assert rules['reject_purchase_order']['to_state'] == 'draft'
    assert rules['confirm_purchase_order']['to_state'] == 'confirmed'
    assert rules['close_purchase_order']['from_states'] == ['confirmed']
    assert set(rules['cancel_purchase_order']['from_states']) == {
        'draft', 'submitted', 'confirmed'}
    for rule in rules.values():
        if rule['type'] == 'state_transition':
            assert rule.get('triggers') == ['before_update']


def test_header_indexes_and_relations():
    schema = _load('purchase_order.yaml')
    index_names = {i['name'] for i in schema['indexes']}
    assert 'uidx_purchase_order_no' in index_names
    assert 'idx_purchase_order_purchase_org_date' in index_names
    relations = {r['id']: r for r in schema['relations']}
    assert relations['purchase_order_to_supplier']['target'] == 'party'
    assert relations['purchase_order_to_purchase_org']['target'] == 'org'


def test_header_ui_config_has_child_sections():
    ui = _load('purchase_order.yaml')['ui_view_config']
    assert ui['list']['columns']
    assert ui['form']['sections']
    children = {c['child_object'] for c in ui['child_sections']}
    assert children == {'purchase_order_line', 'purchase_order_schedule'}


def test_line_fields_and_pricing_mode():
    fields = _fields(_load('purchase_order_line.yaml'))
    for name in ('order_id', 'line_no', 'line_type_id', 'qty', 'pricing_mode'):
        assert fields[name]['required'] is True, name
    modes = {v['value'] for v in fields['pricing_mode']['enum_values']}
    assert 'standalone' in modes and 'bundle_price' in modes
    sources = {v['value'] for v in fields['price_source']['enum_values']}
    assert sources == {'manual', 'agreement', 'quotation', 'rate_table',
                       'last_po', 'standard_cost'}


def test_line_has_no_single_demand_reference():
    """E5：需求 / 项目任务只落在分配行，PO 行不做单值引用。"""
    fields = _fields(_load('purchase_order_line.yaml'))
    assert 'requisition_line_id' not in fields
    assert 'project_task_id' not in fields
    assert 'parent_line_id' in fields
    assert 'source_structure_line_id' in fields


def test_schedule_fields_and_index():
    schema = _load('purchase_order_schedule.yaml')
    fields = _fields(schema)
    for name in ('order_id', 'line_id', 'schedule_no', 'promised_date',
                 'promised_qty', 'status', 'received_qty'):
        assert name in fields, name
    assert fields['received_qty'].get('ui', {}).get('editable') is False
    assert {'line_id', 'schedule_kind', 'schedule_no'} <= set(
        schema['indexes'][0]['fields'])
    assert schema['indexes'][0]['unique'] is True


def test_allocation_target_bo_domain():
    fields = _fields(_load('demand_allocation.yaml'))
    targets = {v['value'] for v in fields['target_bo']['enum_values']}
    assert {'purchase_order', 'transfer_order', 'work_order'} <= targets
    assert fields['project_task_id']['nullable'] is True
    indexes = _load('demand_allocation.yaml')['indexes']
    unique_names = {i['name'] for i in indexes if i.get('unique')}
    assert 'uidx_demand_alloc_target' in unique_names
    assert 'uidx_demand_alloc_target_schedule' in unique_names
