# -*- coding: utf-8 -*-
"""生命周期单据的状态机覆盖回归。

shipment / receipt / work_order 的 `rules: type=state_transition` 是各自生命周期
的唯一真源（副作用由对应 guard/service 执行）。本用例锁定状态边，避免声明被
误删后服务层与前端动作静默失配。
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'

EXPECTED_EDGES = {
    'shipment.yaml': {
        (('draft',), 'released'),
        (('released',), 'staged'),
        (('staged',), 'shipped'),
        (('shipped',), 'delivered'),
        (('delivered',), 'closed'),
        (('draft', 'released'), 'cancelled'),
    },
    'receipt.yaml': {
        (('draft',), 'posted'),
        (('draft',), 'cancelled'),
        (('posted',), 'reversed'),
    },
    'work_order.yaml': {
        (('New',), 'In Progress'),
        (('In Progress',), 'Waiting'),
        (('Waiting',), 'In Progress'),
        (('In Progress', 'Waiting'), 'Resolved'),
        (('Resolved',), 'Closed'),
        (('New', 'In Progress', 'Waiting'), 'Cancelled'),
    },
}


def _rules(name):
    data = yaml.safe_load((SCHEMA_DIR / name).read_text(encoding='utf-8'))
    return [r for r in (data.get('rules') or [])
            if r.get('type') == 'state_transition']


@pytest.mark.parametrize('name', sorted(EXPECTED_EDGES))
def test_rules_are_well_formed(name):
    rules = _rules(name)
    assert rules, '{0} 未声明 state_transition 规则'.format(name)
    assert len({r['id'] for r in rules}) == len(rules), '规则 id 重复'
    for rule in rules:
        assert rule['state_field'] == 'status', rule['id']
        assert rule['from_states'], rule['id']
        assert rule['to_state'] not in rule['from_states'], rule['id']
        assert rule.get('triggers') == ['before_update'], rule['id']


@pytest.mark.parametrize('name', sorted(EXPECTED_EDGES))
def test_declared_edges_match_lifecycle(name):
    pairs = {(tuple(r['from_states']), r['to_state']) for r in _rules(name)}
    assert pairs == EXPECTED_EDGES[name]


def test_terminal_states_have_no_outgoing_edges():
    """终态只进不出：closed / cancelled / reversed 不得作为迁移起点。"""
    terminals = {'closed', 'cancelled', 'reversed', 'Closed', 'Cancelled'}
    for name in EXPECTED_EDGES:
        for rule in _rules(name):
            assert not (set(rule['from_states']) & terminals), rule['id']
