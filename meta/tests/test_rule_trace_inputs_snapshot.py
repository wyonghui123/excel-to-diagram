# -*- coding: utf-8 -*-
"""trace 输入快照测试（spec 2026-11-09 FR-008）。

[定位] 每个 trace 节点新增 ``inputs={factors, fields, attrs, relations}``：
factors 只含场景因子轴；fields/attrs/relations 来自同一次求值的访问采集。
旧字段（factors/detail/kind 等）保持不变，旧客户端忽略 inputs 不受影响。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from meta.core.rule_trace_service import RuleTraceService, _inputs_of  # noqa: E402


def _default_node():
    return {
        'scenario': 'default',
        'decision': 'applied',
        'kind': 'hit',
        'factors': {
            'target_field': 'payment_terms',
            'value': 'NT30',
            'logs': [
                {'rule_id': 'd1', 'inputs': {
                    'fields': [
                        {'path': 'order_type', 'value': 'ZOR', 'source': 'data'},
                    ],
                    'attrs': [
                        {'path': 'attrs.color', 'code': 'color', 'value': 'red',
                         'source': 'value', 'definition_version': 3},
                    ],
                    'relations': [],
                }},
                {'rule_id': 'd2', 'inputs': {
                    'fields': [
                        {'path': 'order_type', 'value': 'ZOR', 'source': 'data'},
                    ],
                    'attrs': [],
                    'relations': [
                        {'path': 'self.customer', 'value': {'id': 9}},
                    ],
                }},
            ],
        },
        'detail': {'rules': []},
    }


class TestInputsOf:
    def test_default_aggregates_and_dedupes(self):
        inputs = _inputs_of(_default_node())

        assert inputs['factors'] == {}
        assert [item['path'] for item in inputs['fields']] == ['order_type']
        assert [item['path'] for item in inputs['attrs']] == ['attrs.color']
        assert inputs['attrs'][0]['definition_version'] == 3
        assert [item['path'] for item in inputs['relations']] == ['self.customer']

    def test_factors_limited_to_scenario_axes(self):
        node = {
            'scenario': 'control_parameter',
            'factors': {
                'org_id': 1, 'document_type_id': 2, 'line_type_id': 3,
                'item_group_id': 4, 'noise': 'x',
            },
        }
        inputs = _inputs_of(node)
        assert inputs['factors'] == {
            'org_id': 1, 'document_type_id': 2,
            'line_type_id': 3, 'item_group_id': 4,
        }
        assert inputs['fields'] == []

    def test_sourcing_axes(self):
        node = {
            'scenario': 'sourcing',
            'factors': {
                'dest_org_id': 1, 'item_id': 100,
                'usage': 'fulfillment', 'eval_date': '2026-10-24',
            },
        }
        assert _inputs_of(node)['factors'] == {
            'dest_org_id': 1, 'item_id': 100,
            'usage': 'fulfillment', 'eval_date': '2026-10-24',
        }

    def test_unknown_scenario_factors_empty(self):
        node = {'scenario': 'approval', 'factors': {'x': 1}}
        assert _inputs_of(node)['factors'] == {}


class TestDecoratedNode:
    def test_inputs_added_without_changing_old_fields(self):
        node = _default_node()
        decorated = RuleTraceService._decorate_steps('tr-1', [node])[0]

        assert decorated['inputs']['attrs'][0]['path'] == 'attrs.color'
        # 旧字段原样保留
        assert decorated['factors'] is node['factors']
        assert decorated['kind'] == 'hit'
        assert decorated['stage'] == 'before_save'
        assert decorated['seq'] == 1
