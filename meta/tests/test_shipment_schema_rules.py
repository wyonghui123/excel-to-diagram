# -*- coding: utf-8 -*-
"""交货单 schema 规则测试（M1-6）—— 校验 shipment.yaml 的状态机与列表动作。

依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.3 / §10.4
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / 'schemas' / 'shipment.yaml'

_RULE_IDS = {
    'release_shipment',
    'stage_shipment',
    'ship_shipment',
    'receive_shipment',
    'close_shipment',
    'cancel_shipment',
}

#: 规则 id → (from_states, to_state)
_TRANSITIONS = {
    'release_shipment': (['draft'], 'released'),
    'stage_shipment': (['released'], 'staged'),
    'ship_shipment': (['staged'], 'shipped'),
    'receive_shipment': (['shipped'], 'delivered'),
    'close_shipment': (['delivered'], 'closed'),
    'cancel_shipment': (['draft', 'released'], 'cancelled'),
}

_ACTION_IDS = {'create', 'export', 'print'}


@pytest.fixture(scope='module')
def schema():
    return yaml.safe_load(_SCHEMA_PATH.read_text(encoding='utf-8'))


def test_rules_have_six_state_transitions(schema):
    rules = schema['rules']
    assert len(rules) == 6
    assert {rule['id'] for rule in rules} == _RULE_IDS
    for rule in rules:
        assert rule['type'] == 'state_transition'
        assert rule['state_field'] == 'status'
        assert rule['triggers'] == ['before_update']


def test_rule_transitions_match_state_machine(schema):
    by_id = {rule['id']: rule for rule in schema['rules']}
    for rule_id, (from_states, to_state) in _TRANSITIONS.items():
        rule = by_id[rule_id]
        assert rule['from_states'] == from_states
        assert rule['to_state'] == to_state


def test_list_actions(schema):
    actions = schema['ui_view_config']['list']['actions']
    assert {action['id'] for action in actions} == _ACTION_IDS
    create = next(action for action in actions if action['id'] == 'create')
    assert create['permission'] == 'shipment:create'
