# -*- coding: utf-8 -*-
"""M6b：constraint 多 key 判定、combine_mode 聚合、explain 两节点与声明校验。"""

import pytest

from meta.core.models import MetaConstraint
from meta.core.models_enums import RuleType
from meta.core.rule_constraint_evaluator import (
    ConstraintEvaluationError,
    evaluate_constraint_rule,
)
from meta.core.rule_declaration_validator import validate_constraint_keys
from meta.core.rule_metrics import MetricDefinition, MetricRegistry, MetricSession
from meta.core.yaml_loader import parse_constraint

OBJECT = 'inventory_count_line'
RECORD = {'counted_qty': 110, 'snapshot_qty': 100}


class FakeResolver:
    """最小参数 resolver：explain 候选链 + candidates 定义。"""

    def __init__(self, definitions):
        self.definitions = definitions

    def explain(self, code, dims=None):
        definition = self.definitions.get(code)
        if not definition:
            return {'parameter': code, 'value': None,
                    'source': {'type': 'missing'}, 'candidates': []}
        return {
            'parameter': code,
            'value': definition['value'],
            'source': {'type': 'definition',
                       'parameter_code': 'PM-%s' % code},
            'candidates': [{'value': definition['value'],
                            'specificity_rank': 0}],
        }

    def candidates(self, code, dims=None):
        definition = self.definitions.get(code)
        return {'defined': bool(definition), 'definition': definition}


def _registry():
    registry = MetricRegistry()
    registry.register(MetricDefinition(
        code='deviation_qty', formula='counted_qty - snapshot_qty',
        inputs=('counted_qty', 'snapshot_qty'), object_type=OBJECT))
    registry.register(MetricDefinition(
        code='deviation_rate', formula='deviation_qty / snapshot_qty',
        inputs=('deviation_qty', 'snapshot_qty'), object_type=OBJECT,
        precision=4))
    return registry


def _metrics(record=None):
    return MetricSession(OBJECT, 1, record or RECORD, registry=_registry())


def _resolver():
    return FakeResolver({
        'tol_abs': {'value': 5, 'tolerance_direction': 'both',
                    'tolerance_basis': 'absolute'},
        'tol_pct': {'value': 0.02, 'tolerance_direction': 'both',
                    'tolerance_basis': 'percent'},
        'tol_under': {'value': 3, 'tolerance_direction': 'under',
                      'tolerance_basis': 'absolute'},
    })


def _rule(**kwargs):
    defaults = {
        'id': 'inv_variance', 'name': '盘点差异容差',
        'rule_type': RuleType.CONSTRAINT,
        'combine_mode': 'any',
        'disposition': 'block',
        'keys': [
            {'parameter': 'tol_abs', 'metric': 'deviation_qty',
             'severity': 'warning', 'disposition': 'hold'},
            {'parameter': 'tol_pct', 'metric': 'deviation_rate',
             'severity': 'error', 'disposition': 'block'},
        ],
        'release_action': 'edit_and_resubmit',
    }
    defaults.update(kwargs)
    return MetaConstraint(**defaults)


def test_parse_constraint_reads_keys_and_release_action():
    rule = parse_constraint({
        'id': 'R1', 'name': 'R1', 'type': 'constraint',
        'combine_mode': 'any', 'disposition': 'hold',
        'release_action': 'edit_and_resubmit',
        'keys': [{'parameter': 'tol_abs', 'metric': 'deviation_qty'}],
    })
    assert rule.keys == [{'parameter': 'tol_abs', 'metric': 'deviation_qty'}]
    assert rule.release_action == 'edit_and_resubmit'
    assert rule.combine_mode == 'any'


def test_any_mode_triggers_on_single_key_and_escalates():
    decision = evaluate_constraint_rule(
        _rule(), metrics=_metrics(), resolver=_resolver())
    # 偏差 10：abs 键（限值 5）超限；pct 键（限值 0.02 对应 10%）也超限
    assert decision.matched is True
    assert decision.combine_mode == 'any'
    assert decision.severity == 'error'
    assert decision.action == 'block'
    assert decision.release_action == 'edit_and_resubmit'


def test_all_mode_requires_every_key_exceeded():
    decision = evaluate_constraint_rule(
        _rule(combine_mode='all'), metrics=_metrics(), resolver=_resolver())
    assert decision.matched is True
    # 只突破一个键时 all 不构成结论
    relaxed = _resolver()
    relaxed.definitions['tol_abs']['value'] = 50
    decision = evaluate_constraint_rule(
        _rule(combine_mode='all'), metrics=_metrics(), resolver=relaxed)
    assert decision.matched is False
    assert decision.action == '' and decision.severity == ''


def test_all_keys_are_evaluated_in_order_without_short_circuit():
    decision = evaluate_constraint_rule(
        _rule(), metrics=_metrics(), resolver=_resolver())
    assert [item.parameter for item in decision.keys] == ['tol_abs', 'tol_pct']
    # any 模式下即使首键已命中，后续键仍产出解释
    assert all(item.limit and item.verdict for item in decision.keys)


def test_explain_has_limit_and_verdict_nodes_only():
    decision = evaluate_constraint_rule(
        _rule(), metrics=_metrics(), resolver=_resolver())
    explain = decision.explain()
    assert [item['node'] for item in explain] == ['limit', 'verdict'] * 2
    limit = explain[0]
    assert limit['parameter'] == 'tol_abs'
    assert limit['value'] == 5
    assert limit['explain']['candidates']
    verdict = explain[1]
    # verdict 只记度量值 / 比较符 / 结论，不重复限值字段
    assert set(verdict) == {'node', 'metric', 'actual', 'op', 'passed'}
    assert verdict == {'node': 'verdict', 'metric': 'deviation_qty',
                       'actual': 10.0, 'op': 'abs_gt', 'passed': False}


def test_under_direction_compares_negative_deviation():
    rule = _rule(combine_mode='any', keys=[
        {'parameter': 'tol_under', 'metric': 'deviation_qty',
         'severity': 'error', 'disposition': 'block'},
    ])
    # 偏差 +10 不触发「仅下限」规则
    assert evaluate_constraint_rule(
        rule, metrics=_metrics(), resolver=_resolver()).matched is False
    under = _metrics({'counted_qty': 95, 'snapshot_qty': 100})
    decision = evaluate_constraint_rule(
        rule, metrics=under, resolver=_resolver())
    assert decision.matched is True
    assert decision.keys[0].verdict['op'] == 'lt'


def test_instance_override_takes_precedence_over_definition():
    decision = evaluate_constraint_rule(
        _rule(combine_mode='any'), metrics=_metrics(), resolver=_resolver(),
        overrides={'tol_abs': 50})
    first = decision.keys[0]
    assert first.limit['value'] == 50
    assert first.limit['source'] == {'type': 'instance'}
    assert first.exceeded is False  # abs 键在实例限值 50 下未超限
    assert decision.keys[1].exceeded is True  # pct 键仍超限
    assert decision.matched is True


def test_missing_parameter_fails_loud():
    with pytest.raises(ConstraintEvaluationError):
        evaluate_constraint_rule(
            _rule(combine_mode='any', keys=[
                {'parameter': 'nope', 'metric': 'deviation_qty'},
            ]),
            metrics=_metrics(), resolver=_resolver())


def test_rule_without_keys_is_rejected():
    with pytest.raises(ConstraintEvaluationError):
        evaluate_constraint_rule(
            _rule(keys=[]), metrics=_metrics(), resolver=_resolver())


def _object(rule):
    return type('MetaObject', (), {'id': OBJECT, 'rules': [rule]})()


def test_hold_requires_release_action():
    errors = validate_constraint_keys([_object(
        _rule(disposition='hold', release_action=''))])
    codes = [error.code for error in errors]
    assert codes.count('RULE_HOLD_RELEASE_MISSING') == 2  # 规则级 + key 级 hold


def test_key_disposition_outside_matrix_rejected():
    errors = validate_constraint_keys([_object(_rule(keys=[
        {'parameter': 'tol_abs', 'metric': 'deviation_qty',
         'disposition': 'route'},
    ]))])
    assert [error.code for error in errors] == ['RULE_ACTION_INVALID']


def test_invalid_key_structure_and_severity_reported():
    errors = validate_constraint_keys([_object(_rule(keys=[
        {'parameter': 'tol_abs'},
        {'parameter': 'tol_abs', 'metric': 'deviation_qty',
         'severity': 'fatal'},
    ]))])
    assert [error.code for error in errors] == ['RULE_KEY_INVALID'] * 2


def test_legal_declaration_passes():
    assert validate_constraint_keys([_object(_rule())]) == []