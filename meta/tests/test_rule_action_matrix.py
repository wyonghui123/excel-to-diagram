# -*- coding: utf-8 -*-
"""规则模型 M1：`rule_type × action` 封闭矩阵与加载期校验（R-A1）。

对应 spec-rule-model-2026-11-10 §9.5 / §9.9。
"""

from types import SimpleNamespace

import pytest

from meta.core.models import registry
from meta.core.models_enums import RuleType
from meta.core.rule_action_matrix import (
    APPROVAL_RULE_TYPE,
    RULE_ACTION_MATRIX,
    RULE_ACTIONS,
    allowed_actions,
    validate_action,
)
from meta.core.rule_declaration_validator import validate_rule_actions
from meta.core.yaml_loader import (
    get_yaml_schema_dir,
    parse_rule,
    register_from_directory,
)


def _declaration(rule_type, disposition=''):
    return SimpleNamespace(id='R-TEST', rule_type=rule_type,
                           disposition=disposition)


# ---------------------------------------------------------------- 词表 / 矩阵

def test_action_vocabulary_is_closed_as_seven_words():
    assert RULE_ACTIONS == (
        'block', 'warn_ack', 'hold', 'route', 'notify', 'default', 'lock')


def test_matrix_covers_every_rule_type():
    assert set(RULE_ACTION_MATRIX) == {
        item.value for item in RuleType} | {APPROVAL_RULE_TYPE}


def test_derivation_allows_no_disposition_action():
    # derivation 是计算而非处置：矩阵全为 —。
    assert allowed_actions(RuleType.DERIVATION) == frozenset()


@pytest.mark.parametrize('rule_type, action', [
    (RuleType.VALIDATION, 'block'),
    (RuleType.VALIDATION, 'warn_ack'),
    (RuleType.VALIDATION, 'hold'),
    (RuleType.CONSTRAINT, 'hold'),
    (RuleType.STATE_TRANSITION, 'route'),
    (RuleType.PERMISSION, 'lock'),
    (RuleType.DEFAULT, 'default'),
    (RuleType.COMPUTATION, 'default'),
    (RuleType.TRIGGER, 'notify'),
    (APPROVAL_RULE_TYPE, 'route'),
])
def test_legal_combinations_pass(rule_type, action):
    assert validate_action(rule_type, action) is None


@pytest.mark.parametrize('rule_type, action', [
    (RuleType.VALIDATION, 'lock'),
    (RuleType.CONSTRAINT, 'warn_ack'),
    (RuleType.PERMISSION, 'route'),
    (RuleType.DEFAULT, 'block'),
    (RuleType.COMPUTATION, 'warn_ack'),
    (RuleType.DERIVATION, 'hold'),
    (RuleType.TRIGGER, 'block'),
    (APPROVAL_RULE_TYPE, 'default'),
    ('not_a_rule_type', 'block'),
])
def test_illegal_combinations_rejected(rule_type, action):
    reason = validate_action(rule_type, action)
    assert reason and action in reason


def test_unknown_action_word_rejected():
    reason = validate_action(RuleType.VALIDATION, 'reject')
    assert reason and 'reject' in reason


def test_undeclared_action_is_allowed():
    assert validate_action(RuleType.VALIDATION, '') is None


# ---------------------------------------------------------------- 加载期校验

def test_rule_action_error_carries_rule_key():
    meta_object = SimpleNamespace(
        id='sales_order',
        rules=[_declaration(RuleType.VALIDATION, 'lock')],
    )

    errors = validate_rule_actions([meta_object])

    assert len(errors) == 1
    assert errors[0].code == 'RULE_ACTION_INVALID'
    assert errors[0].object_type == 'sales_order'
    assert 'bo_yaml:sales_order.R-TEST' in errors[0].message


def test_registry_has_no_illegal_rule_actions():
    if not registry.all():
        register_from_directory(get_yaml_schema_dir())
    assert validate_rule_actions() == []


def test_parse_rule_reads_disposition():
    rule = parse_rule({
        'id': 'R-VAL-1',
        'name': '金额必须为正',
        'type': 'validation',
        'condition': 'amount > 0',
        'disposition': 'block',
    })

    assert rule.disposition == 'block'
    assert rule.action == ''