# -*- coding: utf-8 -*-
"""规则化收敛 M2：状态机 / 审批注册表 / 单据流 / 加载期校验等价性回归。

对应 Spec v1.3 FR-004 / FR-005 / FR-006 / FR-012。
断言「声明解析结果与迁移前常量逐项相等」，不是新行为。
"""

import os
import subprocess
import sys
from types import SimpleNamespace

from meta.core import approval_meta_loader, state_machine_loader
from meta.core.models import registry
from meta.core.models_enums import RuleType
from meta.core.rule_declaration_validator import (
    validate_approval,
    validate_doc_flow_rules,
    validate_numbering,
    validate_state_machines,
)
from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
from meta.migrations.v214__doc_flow_shipment_issue_rule import RULE as V214_RULE
from meta.migrations.v215__doc_flow_stage2_rules import RULES as V215_RULES
from meta.migrations.v222__doc_flow_return_shipment_rule import (
    RETURN_RULE as V222_RULE,
)
from meta.services.document_approval_service import DocumentApprovalResolver

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPECTED_SCHEDULE_STATES = ('planned', 'confirmed', 'completed', 'cancelled')
EXPECTED_SCHEDULE_TRANSITIONS = {
    'planned': ('confirmed', 'cancelled'),
    'confirmed': ('completed', 'cancelled'),
    'completed': (),
    'cancelled': (),
}
EXPECTED_SCHEDULE_TERMINAL = ('completed', 'cancelled')

EXPECTED_SERIAL_STATES = (
    'defined', 'in_stores', 'in_transit', 'issued',
    'shipped', 'consumed', 'returned', 'scrapped')
EXPECTED_SERIAL_TRANSITIONS = {
    'defined': ('in_stores', 'scrapped'),
    'in_stores': ('issued', 'in_transit', 'shipped', 'scrapped'),
    'in_transit': ('in_stores', 'scrapped'),
    'issued': ('shipped', 'consumed', 'returned', 'scrapped'),
    'shipped': ('scrapped',),
    'consumed': ('scrapped',),
    'returned': ('in_stores', 'scrapped'),
    'scrapped': (),
}
EXPECTED_SERIAL_TERMINAL = ('scrapped',)

EXPECTED_APPROVAL_TABLES = {
    'purchase_order': 'purchase_orders',
    'transfer_order': 'transfer_orders',
    'requisition': 'requisitions',
    'service_request': 'service_requests',
}


def _ensure_registry():
    if not registry.all():
        register_from_directory(get_yaml_schema_dir())


def _field(field_id):
    return SimpleNamespace(id=field_id, db_column=field_id)


def _state(code, category=''):
    return SimpleNamespace(code=code, category=category)


def _rule(from_states, to_state, state_field='status'):
    return SimpleNamespace(
        rule_type=RuleType.STATE_TRANSITION,
        state_field=state_field,
        from_states=from_states,
        to_state=to_state,
    )


# ---------------------------------------------------------------- 状态机

def test_schedule_machine_matches_legacy():
    machine = state_machine_loader.get_state_machine('sales_order_schedule')
    assert machine is not None, 'sales_order_schedule 未声明状态机'
    assert machine.states == EXPECTED_SCHEDULE_STATES
    assert machine.transitions == EXPECTED_SCHEDULE_TRANSITIONS
    assert machine.terminal == EXPECTED_SCHEDULE_TERMINAL


def test_schedule_terminal_cannot_move():
    machine = state_machine_loader.get_state_machine('sales_order_schedule')
    assert machine.can_transition('planned', 'confirmed')
    assert machine.can_transition('confirmed', 'completed')
    assert machine.can_transition('planned', 'cancelled')
    assert not machine.can_transition('completed', 'planned')
    assert not machine.can_transition('planned', 'completed')


def test_serial_machine_matches_legacy():
    machine = state_machine_loader.get_state_machine(
        'serial_number', 'usage_status')
    assert machine is not None, 'serial_number 未声明 usage_status 状态机'
    assert machine.states == EXPECTED_SERIAL_STATES
    assert machine.transitions == EXPECTED_SERIAL_TRANSITIONS
    assert machine.terminal == EXPECTED_SERIAL_TERMINAL


def test_serial_states_equal_service_constant():
    from meta.services.serial_number_service import USAGE_STATUSES

    machine = state_machine_loader.get_state_machine(
        'serial_number', 'usage_status')
    assert tuple(USAGE_STATUSES) == machine.states


def test_state_machines_are_hidden_and_not_triggered():
    """声明只作读取真源：hidden 保证 /state_transitions 输出不变，enabled=False 不接引擎。"""
    _ensure_registry()
    for object_id in ('sales_order_schedule', 'serial_number'):
        meta_object = registry.get(object_id)
        rules = [
            rule for rule in (meta_object.rules or [])
            if rule.rule_type == RuleType.STATE_TRANSITION
        ]
        assert rules, '%s 缺少 state_transition 声明' % object_id
        for rule in rules:
            assert rule.enabled is False
            assert rule.ui_hints is not None and rule.ui_hints.hidden is True


# ---------------------------------------------------------------- 审批

def test_approval_meta_matches_legacy():
    for object_type, table in EXPECTED_APPROVAL_TABLES.items():
        meta = approval_meta_loader.get_approval_meta(object_type)
        assert meta['table'] == table

    purchase = approval_meta_loader.get_approval_meta('purchase_order')
    assert purchase['amount_fields'] == (
        'gross_amount', 'net_amount', 'total_amount', 'amount')

    for object_type in ('transfer_order', 'requisition', 'service_request'):
        assert approval_meta_loader.get_approval_meta(
            object_type)['amount_fields'] == ()


def test_approval_amount_priority():
    fields = approval_meta_loader.get_approval_meta(
        'purchase_order')['amount_fields']
    assert DocumentApprovalResolver._amount_of(
        {'gross_amount': 10.0, 'net_amount': 20.0}, fields) == 10.0
    assert DocumentApprovalResolver._amount_of(
        {'net_amount': 20.0, 'total_amount': 30.0}, fields) == 20.0
    assert DocumentApprovalResolver._amount_of(
        {'total_amount': 30.0, 'amount': 40.0}, fields) == 30.0
    assert DocumentApprovalResolver._amount_of({'amount': 40.0}, fields) == 40.0
    assert DocumentApprovalResolver._amount_of({}, fields) == 0.0


def test_unknown_object_has_no_approval_table():
    assert approval_meta_loader.get_approval_meta(
        '__no_such_object__')['table'] == ''


# ---------------------------------------------------------------- 加载期校验

def test_declarations_of_migrated_objects_are_clean():
    _ensure_registry()
    state_objects = [
        registry.get(object_id)
        for object_id in ('sales_order_schedule', 'serial_number')]
    approval_objects = [
        registry.get(object_id) for object_id in (
            'purchase_order', 'transfer_order', 'requisition',
            'service_request')]
    numbering_objects = [
        registry.get(object_id) for object_id in (
            'sales_order', 'purchase_order', 'receipt', 'transfer_order',
            'transfer_shipment')]

    errors = validate_state_machines(state_objects)
    errors.extend(validate_approval(approval_objects))
    errors.extend(validate_numbering(numbering_objects))
    assert errors == [], '\n'.join(str(item) for item in errors)


def test_state_machine_validator_negative():
    objects = [
        SimpleNamespace(
            id='undeclared', fields=[_field('status')],
            rules=[_rule(['planned'], 'done')],
            states=[_state('planned', 'initial')]),
        SimpleNamespace(
            id='terminal_out', fields=[_field('status')],
            rules=[_rule(['done'], 'planned')],
            states=[_state('planned', 'initial'), _state('done', 'terminal')]),
        SimpleNamespace(
            id='orphan', fields=[_field('status')],
            rules=[_rule(['planned'], 'confirmed')],
            states=[_state('planned', 'initial'), _state('confirmed'),
                    _state('lonely')]),
        SimpleNamespace(
            id='field_missing', fields=[_field('other')],
            rules=[_rule(['planned'], 'confirmed')],
            states=[_state('planned', 'initial'), _state('confirmed')]),
    ]
    codes = {item.code for item in validate_state_machines(objects)}
    assert 'STATE_UNDECLARED' in codes
    assert 'STATE_TERMINAL_OUTGOING' in codes
    assert 'STATE_ORPHAN' in codes
    assert 'STATE_FIELD_MISSING' in codes


def test_approval_validator_negative():
    objects = [
        SimpleNamespace(
            id='bad_table', table_name='bad_tables',
            fields=[_field('gross_amount')],
            approval={'table': 'unknown_table',
                      'amount_fields': ['gross_amount']}),
        SimpleNamespace(
            id='bad_amount', table_name='bad_amounts', fields=[_field('id')],
            approval={'table': 'bad_amounts',
                      'amount_fields': ['gross_amount']}),
    ]
    codes = {item.code for item in validate_approval(objects)}
    assert 'APPROVAL_TABLE_UNKNOWN' in codes
    assert 'APPROVAL_AMOUNT_FIELD_MISSING' in codes


def test_numbering_validator_negative():
    objects = [
        SimpleNamespace(
            id='bad_numbering', fields=[_field('id')],
            numbering={'no_field': 'missing_no', 'date_field': 'missing_date'}),
    ]
    codes = {item.code for item in validate_numbering(objects)}
    assert codes == {'NUMBERING_FIELD_MISSING'}


# ---------------------------------------------------------------- 单据流

def test_doc_flow_baseline_unchanged():
    assert V214_RULE['rule_id'] == 'shipment_line_to_issue_txn'
    assert len(V215_RULES) == 6
    assert V222_RULE['rule_id'] == 'shipment_line_to_return_in_txn'

    _ensure_registry()
    rules = [dict(V214_RULE), dict(V222_RULE)] + [dict(item) for item in V215_RULES]
    errors = validate_doc_flow_rules(rules)
    assert errors == [], '\n'.join(str(item) for item in errors)


def test_doc_flow_validator_negative():
    _ensure_registry()
    rules = [{
        'rule_id': 'bad_rule',
        'source_bo': '__no_such_source__',
        'target_bo': '__no_such_target__',
        'source_qty_field': 'qty',
    }]
    codes = {item.code for item in validate_doc_flow_rules(rules)}
    assert 'DOC_FLOW_SOURCE_UNKNOWN' in codes

    duplicated = [
        {'rule_id': 'dup', 'source_bo': 'shipment_line', 'target_bo': 'inventory_transaction', 'source_qty_field': 'quantity'},
        {'rule_id': 'dup', 'source_bo': 'shipment_line', 'target_bo': 'inventory_transaction', 'source_qty_field': 'quantity'},
    ]
    codes = {item.code for item in validate_doc_flow_rules(duplicated)}
    assert 'DOC_FLOW_DUPLICATE' in codes


# ---------------------------------------------------------------- 静态守卫

def test_static_guard_passes():
    result = subprocess.run(
        [sys.executable,
         os.path.join(PROJECT_ROOT, 'scripts', 'check_rule_convergence.py')],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout
