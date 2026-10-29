# -*- coding: utf-8 -*-
"""test_revision_guard.py

M2 T4 / FR-006 修订闸门单测（纯逻辑，无 DB）。

闸门顺序（spec §5）：
  1. enabled              —— 未启用直接跳过
  2. editable_in_states   —— 命中当前 status 才允许
  3. editable_when        —— ConditionEvaluator 求值（fail-closed）
  4. fulfillment_status   —— partial 需变更申请；fulfilled/voided 拒绝

设计取舍：
  - 用 fake evaluator 注入，避免依赖 ConditionEvaluator 的表达式语法；
  - 顺序断言用「同时违反两个闸门」的用例，验证先抛哪个错误码。
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from meta.core.models import MetaObject, MetaRevisionPolicy
from meta.services.revision_guard import (
    NOT_ALLOWED,
    NOT_ALLOWED_FULFILLED,
    REQUIRES_CHANGE_REQUEST,
    STATUS_NOT_EDITABLE,
    RevisionGuard,
)
from meta.services.revision_service import RevisionError


class FakeEvaluator:
    """可控的 ConditionEvaluator 替身。"""

    def __init__(self, result=True):
        self.result = result
        self.calls = []

    def evaluate(self, condition, context):
        self.calls.append((condition, dict(context)))
        return self.result


def _obj(policy):
    obj = MetaObject(id='rev_order', name='订单', table_name='rev_order', fields=[])
    obj.revision_policy = policy
    return obj


def _policy(**kwargs):
    return MetaRevisionPolicy(**kwargs)


def _expect_error(obj, record, code, evaluator=None):
    with pytest.raises(RevisionError) as ei:
        RevisionGuard(evaluator=evaluator).check(obj, record)
    assert ei.value.code == code
    return ei.value


# ---------------------------------------------------------------- 闸门 1：enabled

class TestEnabledGate:
    def test_no_policy_passes(self):
        obj = _obj(None)
        RevisionGuard().check(obj, {'status': 'approved', 'fulfillment_status': 'fulfilled'})

    def test_disabled_skips_all_gates(self):
        """enabled=False ⇒ 状态白名单 / 条件 / 履约分档全部不生效。"""
        obj = _obj(_policy(
            enabled=False,
            editable_in_states=['draft'],
            editable_when='total_amount > 100',
            reason_required_fields=['total_amount'],
        ))
        evaluator = FakeEvaluator(result=False)
        RevisionGuard(evaluator=evaluator).check(
            obj, {'status': 'approved', 'fulfillment_status': 'fulfilled'})
        assert evaluator.calls == []


# ---------------------------------------------------------------- 闸门 2：editable_in_states

class TestStateGate:
    def test_status_not_in_whitelist(self):
        obj = _obj(_policy(enabled=True, editable_in_states=['draft']))
        err = _expect_error(obj, {'status': 'approved'}, STATUS_NOT_EDITABLE)
        assert 'approved' in err.message
        assert 'draft' in err.message

    def test_status_in_whitelist_passes(self):
        obj = _obj(_policy(enabled=True, editable_in_states=['draft', 'approved']))
        RevisionGuard().check(obj, {'status': 'approved'})

    def test_empty_whitelist_means_any_state(self):
        obj = _obj(_policy(enabled=True, editable_in_states=[]))
        RevisionGuard().check(obj, {'status': 'whatever'})

    def test_missing_status_blocked_when_whitelist_set(self):
        obj = _obj(_policy(enabled=True, editable_in_states=['draft']))
        _expect_error(obj, {}, STATUS_NOT_EDITABLE)


# ---------------------------------------------------------------- 闸门 3：editable_when

class TestConditionGate:
    def test_condition_false_blocked(self):
        obj = _obj(_policy(enabled=True, editable_when='total_amount > 100'))
        evaluator = FakeEvaluator(result=False)
        err = _expect_error(obj, {'total_amount': 50}, NOT_ALLOWED, evaluator)
        assert 'total_amount > 100' in err.message
        assert evaluator.calls and evaluator.calls[0][0] == 'total_amount > 100'

    def test_condition_true_passes(self):
        obj = _obj(_policy(enabled=True, editable_when='total_amount > 100'))
        evaluator = FakeEvaluator(result=True)
        RevisionGuard(evaluator=evaluator).check(obj, {'total_amount': 200})
        assert len(evaluator.calls) == 1

    def test_blank_condition_skipped(self):
        obj = _obj(_policy(enabled=True, editable_when='   '))
        evaluator = FakeEvaluator(result=False)
        RevisionGuard(evaluator=evaluator).check(obj, {})
        assert evaluator.calls == []


# ---------------------------------------------------------------- 闸门 4：履约分档

class TestFulfillmentGate:
    def test_partial_requires_change_request(self):
        obj = _obj(_policy(enabled=True))
        _expect_error(obj, {'fulfillment_status': 'partial'}, REQUIRES_CHANGE_REQUEST)

    @pytest.mark.parametrize('state', ['fulfilled', 'voided'])
    def test_fulfilled_and_voided_blocked(self, state):
        obj = _obj(_policy(enabled=True))
        err = _expect_error(obj, {'fulfillment_status': state}, NOT_ALLOWED_FULFILLED)
        assert state in err.message

    @pytest.mark.parametrize('state', [None, '', 'not_started', 'in_progress'])
    def test_other_states_pass(self, state):
        obj = _obj(_policy(enabled=True))
        RevisionGuard().check(obj, {'fulfillment_status': state})


# ---------------------------------------------------------------- 闸门顺序

class TestGateOrder:
    def test_state_gate_precedes_fulfillment(self):
        """status 不在白名单 + partial ⇒ 先报 STATUS_NOT_EDITABLE。"""
        obj = _obj(_policy(enabled=True, editable_in_states=['draft']))
        _expect_error(
            obj,
            {'status': 'approved', 'fulfillment_status': 'partial'},
            STATUS_NOT_EDITABLE,
        )

    def test_condition_gate_precedes_fulfillment(self):
        """条件不满足 + partial ⇒ 先报 NOT_ALLOWED。"""
        obj = _obj(_policy(enabled=True, editable_when='total_amount > 100'))
        _expect_error(
            obj,
            {'total_amount': 50, 'fulfillment_status': 'partial'},
            NOT_ALLOWED,
            FakeEvaluator(result=False),
        )

    def test_state_gate_precedes_condition(self):
        """status 不在白名单 + 条件不满足 ⇒ 先报 STATUS_NOT_EDITABLE。"""
        obj = _obj(_policy(
            enabled=True,
            editable_in_states=['draft'],
            editable_when='total_amount > 100',
        ))
        _expect_error(
            obj,
            {'status': 'approved', 'total_amount': 50},
            STATUS_NOT_EDITABLE,
            FakeEvaluator(result=False),
        )


# ---------------------------------------------------------------- record 为空

class TestEmptyRecord:
    def test_none_record_treated_as_empty_dict(self):
        obj = _obj(_policy(enabled=True))
        RevisionGuard().check(obj, None)
