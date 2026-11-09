# -*- coding: utf-8 -*-
"""生命周期声明契约测试（state_transition 规则 / 冲销档位）。

[TEST-EFF P2-1] 由三个同域（读取 meta/schemas YAML + meta.core 纯配置）的
<=5 用例小文件合并而来：
- test_lifecycle_rule_coverage.py (shipment / receipt / work_order 状态边)
- test_shipment_schema_rules.py   (shipment.yaml 规则与列表动作, M1-6)
- test_reversal_profiles.py       (冲销档位策略表)
注：test_reversal_profiles.py 原缺 marker，合并后统一为 unit（纯静态配置校验）。
"""

from pathlib import Path

import pytest
import yaml

from meta.core.reversal_profiles import (
    REVERSAL_PROFILES,
    VALID_COMMITMENTS,
    VALID_MODES,
    get_profile,
)

pytestmark = pytest.mark.unit

SCHEMA_DIR = Path(__file__).resolve().parents[1] / 'schemas'


# ---------------------------------------------------------------------------
# test_lifecycle_rule_coverage.py
# ---------------------------------------------------------------------------
# shipment / receipt / work_order 的 `rules: type=state_transition` 是各自生命周期
# 的唯一真源（副作用由对应 guard/service 执行）。本用例锁定状态边，避免声明被
# 误删后服务层与前端动作静默失配。

EXPECTED_EDGES = {
    'shipment.yaml': {
        (('draft',), 'released'),
        (('released',), 'staged'),
        (('staged',), 'shipped'),
        (('shipped',), 'delivered'),
        (('delivered',), 'closed'),
        (('draft', 'released'), 'cancelled'),
        (('shipped', 'delivered'), 'reversed'),
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


# ---------------------------------------------------------------------------
# test_shipment_schema_rules.py
# ---------------------------------------------------------------------------
# 依据: docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.3 / §10.4

_SCHEMA_PATH = SCHEMA_DIR / 'shipment.yaml'
_LINE_SCHEMA_PATH = SCHEMA_DIR / 'shipment_line.yaml'

_RULE_IDS = {
    'release_shipment',
    'stage_shipment',
    'ship_shipment',
    'receive_shipment',
    'close_shipment',
    'cancel_shipment',
    'reverse_shipment',
}

#: 规则 id → (from_states, to_state)
_TRANSITIONS = {
    'release_shipment': (['draft'], 'released'),
    'stage_shipment': (['released'], 'staged'),
    'ship_shipment': (['staged'], 'shipped'),
    'receive_shipment': (['shipped'], 'delivered'),
    'close_shipment': (['delivered'], 'closed'),
    'cancel_shipment': (['draft', 'released'], 'cancelled'),
    'reverse_shipment': (['shipped', 'delivered'], 'reversed'),
}

_ACTION_IDS = {'create', 'export', 'print'}


@pytest.fixture(scope='module')
def schema():
    return yaml.safe_load(_SCHEMA_PATH.read_text(encoding='utf-8'))


def test_rules_have_seven_state_transitions(schema):
    rules = schema['rules']
    assert len(rules) == 7
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


def test_status_enum_contains_staged(schema):
    """批次 4a T4.4：拣货确认态 `staged` 必须在状态枚举内（否则规则空转）。"""
    status_field = next(f for f in schema['fields'] if f['id'] == 'status')
    values = {item['value']: item for item in status_field['enum_values']}
    assert 'staged' in values
    assert values['staged']['label'] == '待发运'
    assert values['staged']['category'] == 'active'


def test_list_actions(schema):
    actions = schema['ui_view_config']['list']['actions']
    assert {action['id'] for action in actions} == _ACTION_IDS
    create = next(action for action in actions if action['id'] == 'create')
    assert create['permission'] == 'shipment:create'


@pytest.fixture(scope='module')
def line_schema():
    return yaml.safe_load(_LINE_SCHEMA_PATH.read_text(encoding='utf-8'))


def test_line_serial_no_is_quick_entry_only(line_schema):
    """D7：行内 serial_no 仅 qty=1 快捷录入，宽度对齐 generated_schema 200。"""
    field = next(f for f in line_schema['fields'] if f['id'] == 'serial_no')
    assert field['max_length'] == 200
    assert 'qty=1' in field['description']
    assert 'qty>1' in field['description']


# ---------------------------------------------------------------------------
# test_reversal_profiles.py
# ---------------------------------------------------------------------------
# 冲销档位策略表回归：声明形状 + 关键单据口径。


def test_receipt_keeps_commitment_and_uses_red_reverse():
    profile = get_profile('receipt')
    assert profile['mode'] == 'red_reverse'
    assert profile['commitment'] == 'no_revert'  # 已发生投料不回退
    assert profile['close_guard'] is True
    assert profile['reason_required'] is True
    assert profile['edges'] == ({
        'rule_id': 'receipt_line_to_inventory_txn',
        'source_bo': 'receipt_line',
    },)


def test_shipment_uses_counter_and_releases_remaining():
    for name in ('shipment', 'transfer_shipment'):
        profile = get_profile(name)
        assert profile['mode'] == 'counter'
        assert profile['commitment'] == 'release_remaining'


def test_unknown_document_raises():
    with pytest.raises(KeyError):
        get_profile('no_such_doc')


def test_all_profiles_are_well_formed():
    assert REVERSAL_PROFILES
    for name, profile in REVERSAL_PROFILES.items():
        assert profile['mode'] in VALID_MODES, name
        assert profile['commitment'] in VALID_COMMITMENTS, name
        assert isinstance(profile['edges'], tuple), name
        assert isinstance(profile['reason_required'], bool), name
