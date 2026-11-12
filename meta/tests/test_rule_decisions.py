# -*- coding: utf-8 -*-
"""typed 判定结果测试（M4 / FR-004 / R-A5）"""

import pytest

pytestmark = pytest.mark.unit

from meta.core.metadata_validator import ValidationLevel, ValidationResult
from meta.core.rule_decisions import (
    ApprovalRequirement,
    AssignmentDecision,
    DecisionError,
    DefaultDecision,
    StateGuardDecision,
    ValidationDecision,
    ValidationFinding,
)
from meta.services.document_approval_service import DocumentApprovalResolver


# ---------------- ValidationFinding ----------------

@pytest.mark.parametrize('severity', ['error', 'warning', 'info', 'tech_debt',
                                      'ERROR', ' Warning '])
def test_finding_accepts_validation_levels(severity):
    finding = ValidationFinding('R1', severity, '不成立')
    assert finding.severity == severity.strip().lower()


@pytest.mark.parametrize('severity', ['block', 'hold', 'route', 'warn_ack',
                                      'fatal', ''])
def test_finding_rejects_action_words_and_unknown_severity(severity):
    with pytest.raises(DecisionError):
        ValidationFinding('R1', severity, '不成立')


def test_finding_requires_code_and_message():
    with pytest.raises(DecisionError):
        ValidationFinding('', 'error', 'x')
    with pytest.raises(DecisionError):
        ValidationFinding('R1', 'error', '  ')


# ---------------- ValidationDecision ----------------

def test_decision_ok_only_when_no_error():
    warn = ValidationFinding('W1', 'warning', '缺省值提示')
    assert ValidationDecision([warn]).ok is True
    assert ValidationDecision([warn, ValidationFinding('E1', 'error', '阻断')]).ok is False


def test_decision_rejects_approval_requirement():
    approval = ApprovalRequirement(required=True, policy_code='PO')
    with pytest.raises(DecisionError):
        ValidationDecision([approval])
    with pytest.raises(DecisionError):
        ValidationDecision([approval.as_dict()])


def test_decision_from_metadata_results():
    results = [
        ValidationResult(ValidationLevel.ERROR, 'purchase_order', 'gross_amount',
                         '金额必填', {'code': 'REQUIRED',
                                      'explain': [{'field': 'gross_amount',
                                                   'passed': False}]}),
        ValidationResult(ValidationLevel.WARNING, 'purchase_order', 'remark',
                         '建议填写备注'),
    ]
    decision = ValidationDecision.from_results(results)
    assert decision.ok is False
    payload = decision.as_dict()
    assert payload['ok'] is False
    assert payload['findings'][0] == {
        'code': 'REQUIRED', 'severity': 'error', 'message': '金额必填',
        'field': 'gross_amount',
        'explain': [{'field': 'gross_amount', 'passed': False}],
    }
    assert payload['findings'][1]['code'] == 'warning'


# ---------------- ApprovalRequirement ----------------

def test_approval_requirement_round_trip():
    resolved = {
        'required': True, 'policy_id': 2, 'policy_code': 'PO_AMOUNT',
        'steps': [{'step_no': 1, 'approver_ref': 'manager'}],
        'amount': 12000, 'snapshot': {'policy_code': 'PO_AMOUNT'},
        'reason': 'matched',
    }
    requirement = ApprovalRequirement.from_resolve(resolved)
    assert requirement.as_dict() == dict(resolved, amount=12000.0)
    assert set(requirement.as_dict()) == set(resolved)


def test_approval_requirement_requires_required_key():
    with pytest.raises(DecisionError):
        ApprovalRequirement.from_resolve({'policy_code': 'X'})


class _EmptyDS:
    def query(self, sql, params=None):
        return []


def test_resolver_exposes_typed_requirement():
    requirement = DocumentApprovalResolver(_EmptyDS()).resolve_requirement(
        'purchase_order', 1)
    assert isinstance(requirement, ApprovalRequirement)
    assert requirement.required is False
    assert requirement.reason == 'record_not_found'
    assert requirement.as_dict()['required'] is False


# ---------------- 其余 typed 结果 ----------------

def test_assignment_and_default_decisions():
    assert AssignmentDecision('u1', 'ap_pool', '按组织').as_dict() == {
        'assignee': 'u1', 'pool': 'ap_pool', 'reason': '按组织'}
    assert DefaultDecision('currency', 'CNY', 'R-DEF-1').as_dict() == {
        'field': 'currency', 'value': 'CNY', 'source_rule': 'R-DEF-1'}


def test_state_guard_decision_serializes_from_to():
    decision = StateGuardDecision(False, 'draft', 'confirmed',
                                  ['R-PO-12'])
    assert decision.as_dict() == {
        'allowed': False, 'from': 'draft', 'to': 'confirmed',
        'blocking_rules': ['R-PO-12']}