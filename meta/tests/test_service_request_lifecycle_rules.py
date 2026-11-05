# -*- coding: utf-8 -*-
"""service_request 状态机声明回归。

schema 的 `rules: type=state_transition` 是服务请求生命周期的唯一真源；
本用例锁定规则形状与状态边，防止声明被悄悄改掉后服务层与前端动作失配。
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

SCHEMA = Path(__file__).resolve().parents[1] / 'schemas' / 'service_request.yaml'


def _rules():
    data = yaml.safe_load(SCHEMA.read_text(encoding='utf-8'))
    return [r for r in (data.get('rules') or [])
            if r.get('type') == 'state_transition']


def test_every_rule_has_state_field_and_triggers():
    rules = _rules()
    assert rules, 'service_request.yaml 未声明 state_transition 规则'
    assert len({r['id'] for r in rules}) == len(rules), '规则 id 重复'
    for rule in rules:
        assert rule['state_field'] == 'status', rule['id']
        assert rule['from_states'], rule['id']
        assert rule['to_state'] not in rule['from_states'], rule['id']
        assert rule.get('triggers') == ['before_update'], rule['id']


def test_lifecycle_edges_match_documented_machine():
    pairs = {(tuple(r['from_states']), r['to_state']) for r in _rules()}
    assert pairs == {
        (('draft',), 'submitted'),
        (('submitted',), 'approved'),
        (('submitted',), 'rejected'),
        (('approved',), 'completed'),
        (('completed',), 'closed'),
        (('draft', 'submitted', 'approved'), 'cancelled'),
    }


def test_reject_only_from_submitted_but_cancel_covers_pre_commit_states():
    pairs = {(tuple(r['from_states']), r['to_state']) for r in _rules()}
    assert (('submitted',), 'rejected') in pairs
    assert (('approved',), 'rejected') not in pairs
    assert (('draft', 'submitted', 'approved'), 'cancelled') in pairs
