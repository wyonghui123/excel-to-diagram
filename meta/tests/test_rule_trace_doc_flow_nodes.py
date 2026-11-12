# -*- coding: utf-8 -*-
"""FR-013：doc_flow trace 的节点组增量契约。"""

import time

import meta.core.rule_provider as provider
from meta.core.rule_trace_service import RuleTraceService


RULES = [
    {
        'rule_id': 'so_schedule_to_shipment_line',
        'source_bo': 'sales_order_schedule',
        'target_bo': 'shipment_line',
        'pool': 'unshipped_qty',
        'status': 'active',
    },
    {
        'rule_id': 'so_to_shipment',
        'source_bo': 'sales_order',
        'target_bo': 'shipment',
        'pool': 'unshipped_qty',
        'status': 'active',
    },
]

SCHEDULE_ONLY = [RULES[0]]


def _trace(monkeypatch, rules, object_type):
    monkeypatch.setattr(provider, 'list_doc_flow_rules',
                        lambda data_source: list(rules))
    return RuleTraceService()._doc_flow(
        object_type, object(), time.perf_counter())


def test_header_trace_adds_node_group(monkeypatch):
    node = _trace(monkeypatch, RULES, 'sales_order')

    assert node['decision'] == 'declared'
    assert [rule['rule_id'] for rule in node['detail']['rules']] == [
        'so_to_shipment']

    group = node['detail']['node_group']
    assert group['group_id'] == 'sales_order'
    assert group['node_role'] == 'header'
    assert [item['bo'] for item in group['nodes']] == [
        'sales_order', 'sales_order_line', 'sales_order_schedule']
    assert group['outbound'][0]['target_group'] == 'shipment'


def test_header_without_direct_rule_keeps_decision(monkeypatch):
    node = _trace(monkeypatch, SCHEDULE_ONLY, 'sales_order')

    assert node['decision'] == 'not_declared'
    assert node['detail']['rules'] == []
    assert node['detail']['node_group']['group_id'] == 'sales_order'


def test_schedule_trace_keeps_rules_and_adds_group(monkeypatch):
    node = _trace(monkeypatch, RULES, 'sales_order_schedule')

    assert node['decision'] == 'declared'
    assert [rule['rule_id'] for rule in node['detail']['rules']] == [
        'so_schedule_to_shipment_line']
    assert node['detail']['node_group']['node_role'] == 'schedule'


def test_unmodeled_object_has_no_node_group(monkeypatch):
    node = _trace(monkeypatch, RULES, 'inventory_transaction')

    assert node['decision'] == 'not_declared'
    assert 'node_group' not in node['detail']
