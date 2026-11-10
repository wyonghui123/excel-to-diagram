# -*- coding: utf-8 -*-
"""M5 / FR-006：命中策略封闭词表、排序契约与 unique 静态重叠检查。"""

import dataclasses

import pytest

from meta.core.models import MetaRule
from meta.core.rule_declaration_validator import validate_hit_policies
from meta.core.rule_hit_policy import (
    DEFAULT_HIT_POLICY,
    HIT_POLICIES,
    ORDER_BY,
    normalize_hit_policy,
    order_by_sql,
    select,
    sort_key,
    sort_rules,
    validate_hit_policy,
)


def test_contract_constants():
    assert HIT_POLICIES == ('first', 'all', 'unique')
    assert DEFAULT_HIT_POLICY == 'first'
    assert ORDER_BY == ('priority DESC', 'effective_from DESC', 'id DESC')


def test_meta_rule_declares_hit_policy():
    assert 'hit_policy' in {f.name for f in dataclasses.fields(MetaRule)}


def test_meta_rule_declares_governance_fields():
    names = {f.name for f in dataclasses.fields(MetaRule)}
    assert {'version', 'effective_from', 'priority'} <= names


@pytest.mark.parametrize('value', ['', None, '   '])
def test_undeclared_hit_policy_defaults_to_first(value):
    assert normalize_hit_policy(value) == 'first'
    assert validate_hit_policy(value) is None


@pytest.mark.parametrize('value', ['first', 'ALL', ' unique '])
def test_declared_hit_policy_normalized(value):
    assert validate_hit_policy(value) is None
    assert normalize_hit_policy(value) in HIT_POLICIES


def test_unknown_hit_policy_rejected():
    reason = validate_hit_policy('priority_first')
    assert reason is not None and 'priority_first' in reason


def test_order_by_sql_renders_shared_constant():
    assert order_by_sql() == 'priority DESC, effective_from DESC, id DESC'
    assert order_by_sql('p') == (
        'p.priority DESC, p.effective_from DESC, p.id DESC')


def test_sort_rules_priority_desc_then_effective_then_id():
    rules = [
        {'id': 1, 'priority': 100, 'effective_from': '2026-01-01'},
        {'id': 3, 'priority': 200, 'effective_from': '2026-01-01'},
        {'id': 4, 'priority': 200, 'effective_from': '2026-06-01'},
        {'id': 5, 'priority': 200, 'effective_from': '2026-06-01'},
        {'id': 2, 'priority': 200},
    ]
    assert [rule['id'] for rule in sort_rules(rules)] == [5, 4, 3, 2, 1]


def test_sort_key_blank_effective_from_is_earliest():
    blank = sort_key({'id': 1, 'priority': 10})
    dated = sort_key(
        {'id': 1, 'priority': 10, 'effective_from': '2020-01-01'})
    assert blank[1] < dated[1]


def test_select_first_returns_single_hit():
    hits = [1, 2, 3]
    assert select(hits) == [1]
    assert select(hits, 'first') == [1]


def test_select_all_returns_every_hit():
    assert select([1, 2, 3], 'all') == [1, 2, 3]


def test_select_unique_is_model_time_only():
    with pytest.raises(ValueError):
        select([1], 'unique')


def _rule(rule_id, hit_policy='', condition='amount > 100',
          rule_type='validation'):
    return type('Rule', (), {
        'id': rule_id,
        'hit_policy': hit_policy,
        'condition': condition,
        'rule_type': rule_type,
    })()


def _object(rules):
    return type('MetaObject', (), {'id': 'purchase_order', 'rules': rules})()


def test_invalid_declared_hit_policy_reported():
    errors = validate_hit_policies([_object([_rule('R1', 'priority_first')])])
    assert [error.code for error in errors] == ['RULE_HIT_POLICY_INVALID']
    assert 'R1' in errors[0].message


def test_undeclared_hit_policy_is_default_not_error():
    assert validate_hit_policies([_object([_rule('R1')])]) == []


def test_unique_overlap_detected_by_normalized_condition():
    errors = validate_hit_policies([_object([
        _rule('R1', 'unique'),
        _rule('R2', 'unique', condition=' amount >  100 '),
    ])])
    assert [error.code for error in errors] == ['RULE_OVERLAP']
    assert 'R1' in errors[0].message and 'R2' in errors[0].message


def test_unique_different_rule_type_or_condition_not_overlap():
    errors = validate_hit_policies([_object([
        _rule('R1', 'unique'),
        _rule('R2', 'unique', condition='amount > 200'),
        _rule('R3', 'unique', rule_type='state_transition'),
    ])])
    assert errors == []