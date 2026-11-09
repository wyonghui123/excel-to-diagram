# -*- coding: utf-8 -*-
"""FR-013：单据节点组只读派生契约。"""

from types import SimpleNamespace

from meta.core.doc_flow_node_groups import (
    build_node_groups,
    group_for_bo,
    node_group_detail,
)


RULES = [
    {
        'rule_id': 'so_schedule_to_shipment_line',
        'source_bo': 'sales_order_schedule',
        'target_bo': 'shipment_line',
        'status': 'active',
    },
    {
        'rule_id': 'so_to_shipment',
        'source_bo': 'sales_order',
        'target_bo': 'shipment',
        'status': 'active',
    },
]


def _field(field_id: str, relation: str = '') -> SimpleNamespace:
    return SimpleNamespace(
        id=field_id,
        db_column=field_id,
        ui=SimpleNamespace(relation=relation),
    )


def _meta(children=(), fields=(), hierarchy=None) -> SimpleNamespace:
    return SimpleNamespace(
        ui_view_config=SimpleNamespace(
            child_sections=[{'child_object': child} for child in children],
        ),
        hierarchy=hierarchy,
        fields=list(fields),
    )


def test_sales_order_group_nodes_and_roles():
    groups = build_node_groups(RULES)

    group = groups['sales_order']
    assert [
        (node['bo'], node['role'], node['parent_fk'])
        for node in group['nodes']
    ] == [
        ('sales_order', 'header', ''),
        ('sales_order_line', 'line', 'order_id'),
        ('sales_order_schedule', 'schedule', 'order_id'),
    ]
    assert group['degraded'] is False
    assert group['reasons'] == []
    assert group['subflows'] == []


def test_shipment_parent_fk_prefers_hierarchy():
    group = build_node_groups(RULES)['shipment']

    node = next(item for item in group['nodes'] if item['bo'] == 'shipment_line')
    assert node['parent_fk'] == 'delivery_id'
    assert node['role'] == 'line'


def test_edges_are_grouped_on_both_sides():
    groups = build_node_groups(RULES)

    outbound = groups['sales_order']['outbound']
    assert [edge['rule_id'] for edge in outbound] == [
        'so_schedule_to_shipment_line', 'so_to_shipment']
    assert {edge['target_group'] for edge in outbound} == {'shipment'}

    inbound = groups['shipment']['inbound']
    assert [edge['rule_id'] for edge in inbound] == [
        'so_schedule_to_shipment_line', 'so_to_shipment']
    assert {edge['source_group'] for edge in inbound} == {'sales_order'}


def test_inactive_rules_do_not_form_groups():
    rules = RULES + [{
        'rule_id': 'legacy',
        'source_bo': 'sales_order',
        'target_bo': 'shipment',
        'status': 'inactive',
    }]

    groups = build_node_groups(rules)

    assert [edge['rule_id'] for edge in groups['sales_order']['outbound']] == [
        'so_schedule_to_shipment_line', 'so_to_shipment']


def test_unresolved_parent_fk_degrades_group():
    registry_all = {
        'orphan_header': _meta(['orphan_line']),
        'orphan_line': _meta(fields=[_field('note')]),
    }
    rules = [{
        'rule_id': 'orphan_rule',
        'source_bo': 'orphan_header',
        'target_bo': 'orphan_line',
        'status': 'active',
    }]

    group = build_node_groups(rules, registry_all)['orphan_header']

    assert group['degraded'] is True
    assert group['reasons'] == ['parent_fk_unresolved:orphan_line']
    assert [node['bo'] for node in group['nodes']] == ['orphan_header']


def test_header_child_becomes_subflow():
    registry_all = {
        'project': _meta(['sales_order']),
        'sales_order': _meta(['sales_order_line']),
        'sales_order_line': _meta(fields=[_field('order_id', 'sales_order')]),
    }
    rules = [
        {
            'rule_id': 'project_to_sales_order',
            'source_bo': 'project',
            'target_bo': 'sales_order',
            'status': 'active',
        },
        {
            'rule_id': 'so_line_to_project',
            'source_bo': 'sales_order_line',
            'target_bo': 'project',
            'status': 'active',
        },
    ]

    groups = build_node_groups(rules, registry_all)

    assert groups['project']['subflows'] == ['sales_order']
    assert [node['bo'] for node in groups['project']['nodes']] == ['project']
    assert group_for_bo(groups, 'sales_order') == ('sales_order', 'header')


def test_unmodeled_target_is_listed():
    registry_all = {
        'receipt': _meta(['receipt_line']),
        'receipt_line': _meta(
            fields=[_field('receipt_id')],
            hierarchy={'parent_field': 'receipt_id'},
        ),
    }
    rules = [{
        'rule_id': 'receipt_line_to_txn',
        'source_bo': 'receipt_line',
        'target_bo': 'inventory_transaction',
        'status': 'active',
    }]

    group = build_node_groups(rules, registry_all)['receipt']

    assert group['unmodeled_bo'] == ['inventory_transaction']
    assert [node['bo'] for node in group['nodes']] == ['receipt', 'receipt_line']


def test_node_group_detail_shape():
    groups = build_node_groups(RULES)

    header = node_group_detail(groups, 'sales_order')
    assert header['group_id'] == 'sales_order'
    assert header['node_role'] == 'header'
    assert header['header_bo'] == 'sales_order'

    line = node_group_detail(groups, 'sales_order_schedule')
    assert line['group_id'] == 'sales_order'
    assert line['node_role'] == 'schedule'

    assert node_group_detail(groups, 'inventory_transaction') is None
