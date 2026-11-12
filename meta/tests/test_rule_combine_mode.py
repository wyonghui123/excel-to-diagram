# -*- coding: utf-8 -*-
"""M6b：判定聚合方式（combine_mode）封闭词表、默认值与加载期校验。"""

import dataclasses

import pytest

from meta.core.models import MetaRule
from meta.core.rule_combine_mode import (
    COMBINE_MODES,
    DEFAULT_COMBINE_MODE,
    normalize_combine_mode,
    validate_combine_mode,
)
from meta.core.rule_declaration_validator import validate_combine_modes
from meta.core.yaml_loader import parse_rule


def test_contract_constants():
    assert COMBINE_MODES == ('any', 'all')
    assert DEFAULT_COMBINE_MODE == 'all'


def test_meta_rule_declares_combine_mode():
    assert 'combine_mode' in {f.name for f in dataclasses.fields(MetaRule)}


@pytest.mark.parametrize('value', ['', None, '   '])
def test_undeclared_combine_mode_defaults_to_all(value):
    assert normalize_combine_mode(value) == 'all'
    assert validate_combine_mode(value) is None


@pytest.mark.parametrize('value', ['any', 'ALL', ' all '])
def test_declared_combine_mode_normalized(value):
    assert validate_combine_mode(value) is None
    assert normalize_combine_mode(value) in COMBINE_MODES


def test_unknown_combine_mode_rejected():
    reason = validate_combine_mode('first')
    assert reason is not None and 'first' in reason


def test_parse_rule_reads_combine_mode():
    rule = parse_rule({
        'id': 'R1', 'name': 'R1', 'type': 'constraint',
        'combine_mode': 'ANY', 'condition': 'deviation_qty > 0',
    })
    assert rule.combine_mode == 'any'


def test_parse_rule_defaults_combine_mode_to_empty():
    rule = parse_rule({
        'id': 'R1', 'name': 'R1', 'type': 'constraint',
        'condition': 'deviation_qty > 0',
    })
    assert rule.combine_mode == ''


def _rule(rule_id, combine_mode=''):
    return type('Rule', (), {
        'id': rule_id,
        'combine_mode': combine_mode,
    })()


def _object(rules):
    return type('MetaObject', (), {'id': 'inventory_count_line', 'rules': rules})()


def test_invalid_declared_combine_mode_reported():
    errors = validate_combine_modes([_object([_rule('R1', 'first')])])
    assert [error.code for error in errors] == ['RULE_COMBINE_MODE_INVALID']
    assert 'R1' in errors[0].message


def test_undeclared_combine_mode_is_default_not_error():
    assert validate_combine_modes([_object([_rule('R1')])]) == []


def test_legal_combine_modes_pass():
    assert validate_combine_modes([
        _object([_rule('R1', 'any'), _rule('R2', 'all')]),
    ]) == []