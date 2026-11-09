# -*- coding: utf-8 -*-
"""TBD-007 P0：单据头契约只读派生契约。"""

from meta.core.doc_flow_header_contract import (
    MODE_FLAT,
    MODE_RULE_HEADED,
    MODE_SERVICE_HEADED,
    REASON_HEADER_FIELD_UNCOVERED,
    build_header_contract,
)
from meta.core.doc_flow_node_groups import REASON_MISSING_BO, owner_header

# shipment 头：required 且无 default 的存储字段（id/审计/status/source 不计）。
SHIPMENT_REQUIRED = [
    'delivery_no', 'order_id', 'ship_from_location_id', 'ship_to_address_text',
]


def _rule(**overrides):
    base = {
        'rule_id': 'r1',
        'source_bo': 'sales_order_schedule',
        'target_bo': 'shipment_line',
        'status': 'active',
    }
    base.update(overrides)
    return base


def test_owner_header_from_yaml():
    assert owner_header('shipment_line') == 'shipment'
    assert owner_header('inventory_transaction') == ''
    assert owner_header('shipment') == ''


def test_service_headed_contract():
    contract = build_header_contract(_rule())

    assert contract['mode'] == MODE_SERVICE_HEADED
    assert contract['head_bo'] == 'shipment'
    assert contract['split_key'] == []
    assert contract['required_missing'] == SHIPMENT_REQUIRED
    assert contract['service_owned_fields'] == SHIPMENT_REQUIRED
    assert contract['degraded'] is False
    assert contract['reasons'] == []


def test_defaulted_required_fields_are_not_missing():
    contract = build_header_contract(_rule())

    assert 'status' not in contract['required_missing']
    assert 'source' not in contract['required_missing']
    assert 'id' not in contract['required_missing']


def test_flat_contract():
    contract = build_header_contract(_rule(
        source_bo='receipt_line', target_bo='inventory_transaction'))

    assert contract['mode'] == MODE_FLAT
    assert contract['head_bo'] == ''
    assert contract['required_missing'] == []
    assert contract['service_owned_fields'] == []
    assert contract['degraded'] is False


def test_rule_headed_uncovered_degrades():
    contract = build_header_contract(_rule(
        source_bo='sales_order', target_bo='shipment',
        target_line_bo='shipment_line', split_key=['order_id']))

    assert contract['mode'] == MODE_RULE_HEADED
    assert contract['head_bo'] == 'shipment'
    assert 'order_id' not in contract['required_missing']
    assert contract['required_missing'] == [
        'delivery_no', 'ship_from_location_id', 'ship_to_address_text']
    assert contract['service_owned_fields'] == []
    assert contract['degraded'] is True
    assert contract['reasons'] == [REASON_HEADER_FIELD_UNCOVERED]


def test_rule_headed_covered_and_field_map_rename():
    contract = build_header_contract(_rule(
        source_bo='sales_order', target_bo='shipment',
        target_line_bo='shipment_line',
        split_key=['so_no', 'order_id', 'from_loc', 'addr'],
        field_map={
            'so_no': 'delivery_no',
            'from_loc': 'ship_from_location_id',
            'addr': 'ship_to_address_text',
        }))

    assert contract['mode'] == MODE_RULE_HEADED
    assert contract['required_missing'] == []
    assert contract['degraded'] is False
    assert contract['reasons'] == []


def test_missing_target_bo_degrades():
    contract = build_header_contract(_rule(target_bo='not_a_bo'))

    assert contract['mode'] == MODE_FLAT
    assert contract['degraded'] is True
    assert contract['reasons'] == [REASON_MISSING_BO]
