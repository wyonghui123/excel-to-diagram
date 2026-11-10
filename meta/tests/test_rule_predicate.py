# -*- coding: utf-8 -*-
"""规则模型 M2：统一谓词求值器与 explain（FR-001 / FR-002）。"""

import pytest

from meta.core.rule_predicate import (
    evaluate,
    evaluate_conditions,
    normalize_operator,
)


def _atom(field, operator, **values):
    condition = {'field_id': field, 'operator': operator}
    condition.update(values)
    return condition


@pytest.mark.parametrize('raw, canonical', [
    ('=', 'eq'), ('==', 'eq'), ('!=', 'ne'), ('<>', 'ne'),
    ('>', 'gt'), ('>=', 'ge'), ('<', 'lt'), ('<=', 'le'),
    ('IN', 'in'), ('not in', 'not_in'), ('is null', 'is_null'),
    ('is not null', 'is_not_null'), ('like', 'like'), ('between', 'between'),
])
def test_operator_aliases(raw, canonical):
    assert normalize_operator(raw) == canonical


@pytest.mark.parametrize('actual, operator, target, expected', [
    (12000, '=', 12000, True),
    (12000, '=', 12001, False),
    ('Draft', '=', 'draft', True),
    ('true', '=', 1, True),
    (10, '!=', 11, True),
    (10, '>', 9, True),
    (10, '>=', 10, True),
    (10, '<', 10, False),
    (10, '<=', 10, True),
    ('2026-01-02', '>', '2026-01-01', True),
    (2, 'in', [1, 2, 3], True),
    (2, 'in', '1,2,3', True),
    (4, 'in', '1,2,3', False),
    (4, 'not_in', '1,2,3', True),
    (5, 'between', [1, 10], True),
    (10, 'between', '1,10', True),
    (11, 'between', [1, 10], False),
    (None, 'is_null', None, True),
    ('', 'is_null', None, True),
    ('null', 'is_null', None, True),
    ('x', 'is_null', None, False),
    ('x', 'is not null', None, True),
    ('PO-202611-000001', 'like', 'PO-%', True),
    ('PO-202611-000001', 'like', 'PO-202611-______', True),
    ('PO-202611-000001', 'like', 'SO-%', False),
])
def test_atom_operators(actual, operator, target, expected):
    record = {'amount': actual, 'code': actual, 'status': actual}
    condition = _atom('amount', operator, value_number=target)

    result = evaluate(record, condition)

    assert result.passed is expected
    assert len(result.explain) == 1
    assert result.explain[0]['op'] == normalize_operator(operator)
    assert result.explain[0]['actual'] == actual
    assert result.explain[0]['passed'] is expected


def test_explain_contains_field_operator_expected_actual():
    result = evaluate(
        {'approval_status': 'pending'},
        _atom('approval_status', 'in', value_text='not_required,approved'))

    assert result.passed is False
    assert result.explain == [{
        'field': 'approval_status',
        'op': 'in',
        'expected': 'not_required,approved',
        'actual': 'pending',
        'passed': False,
    }]


def test_unknown_operator_does_not_match():
    result = evaluate({'amount': 10}, _atom('amount', 'reject', value_number=10))

    assert result.passed is False
    assert result.explain[0]['op'] == 'reject'


def test_conditions_are_and_joined_and_explain_lists_all():
    record = {'amount': 12000, 'status': 'active', 'org_id': 7}
    conditions = [
        _atom('amount', '>=', value_number=10000),
        _atom('status', '=', value_text='frozen'),
    ]

    result = evaluate_conditions(record, conditions)

    assert result.passed is False
    assert [item['field'] for item in result.explain] == ['amount', 'status']
    assert [item['passed'] for item in result.explain] == [True, False]


def test_nested_and_or_not():
    record = {'amount': 12000, 'status': 'active'}
    node = {
        'logic': 'and',
        'children': [
            _atom('amount', '>=', value_number=10000),
            {'logic': 'or', 'children': [
                _atom('status', '=', value_text='frozen'),
                _atom('status', 'is null', value_text=''),
            ]},
        ],
    }

    result = evaluate(record, node)

    assert result.passed is False
    assert len(result.explain) == 3


def test_not_inverts_subtree():
    node = {'logic': 'not', 'children': [_atom('status', '=', value_text='frozen')]}

    assert evaluate({'status': 'active'}, node).passed is True
    assert evaluate({'status': 'frozen'}, node).passed is False


def test_empty_condition_list_passes():
    assert evaluate_conditions({'amount': 1}, []).passed is True