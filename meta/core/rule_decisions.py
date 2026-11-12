# -*- coding: utf-8 -*-
"""typed 判定结果（spec-rule-model M4 / FR-004）

判定结果按用途分型，不共用一个大而全的结构：
  · `ValidationDecision`   校验结论（findings 只放校验发现）
  · `ApprovalRequirement`  审批需求（是否需审批 / 命中策略 / 审批链）
  · `AssignmentDecision`   指派结论
  · `DefaultDecision`      默认值结论
  · `StateGuardDecision`   状态守卫结论

约束：
  · 不同类型不得互相塞入：`ValidationDecision.findings` 只接受
    `ValidationFinding`，审批结果不得进入校验发现（FR-004）；
  · `severity` 取值域与 `ValidationLevel` 对齐（error / warning / info /
    tech_debt），处置动作词（block / hold / route ...）不得出现在 severity（R-A5）。
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

VALID_SEVERITIES = frozenset({'error', 'warning', 'info', 'tech_debt'})
ACTION_WORDS = frozenset({
    'block', 'warn_ack', 'hold', 'route', 'notify', 'default', 'lock',
})


class DecisionError(Exception):
    """判定结果类型/取值不合法。"""


def _as_tuple(items: Optional[Iterable[Any]]) -> Tuple[Any, ...]:
    return tuple(items or ())


@dataclass(frozen=True)
class ValidationFinding:
    """一条校验发现。"""

    code: str
    severity: str
    message: str
    field: str = ''
    explain: Tuple[Dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        code = str(self.code or '').strip()
        severity = str(self.severity or '').strip().lower()
        message = str(self.message or '').strip()
        if not code:
            raise DecisionError('ValidationFinding.code 不能为空')
        if not message:
            raise DecisionError('ValidationFinding({0}).message 不能为空'.format(code))
        if severity in ACTION_WORDS:
            raise DecisionError(
                'severity 不得使用处置动作词：{0}'.format(severity))
        if severity not in VALID_SEVERITIES:
            raise DecisionError(
                'severity 必须是 {0} 之一，实际 {1}'.format(
                    '/'.join(sorted(VALID_SEVERITIES)), severity))
        object.__setattr__(self, 'code', code)
        object.__setattr__(self, 'severity', severity)
        object.__setattr__(self, 'message', message)
        object.__setattr__(self, 'field', str(self.field or '').strip())
        object.__setattr__(self, 'explain', _as_tuple(self.explain))

    def as_dict(self) -> Dict[str, Any]:
        result = {
            'code': self.code,
            'severity': self.severity,
            'message': self.message,
            'explain': [dict(item) for item in self.explain],
        }
        if self.field:
            result['field'] = self.field
        return result


@dataclass(frozen=True)
class ValidationDecision:
    """校验结论：ok = 没有 error 级发现（warning/info 不阻断）。"""

    findings: Tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        findings = _as_tuple(self.findings)
        for item in findings:
            if not isinstance(item, ValidationFinding):
                raise DecisionError(
                    'ValidationDecision.findings 只接受 ValidationFinding，'
                    '实际 {0}（审批结果不得进入校验发现）'.format(
                        type(item).__name__))
        object.__setattr__(self, 'findings', findings)

    @property
    def ok(self) -> bool:
        return not any(item.severity == 'error' for item in self.findings)

    def as_dict(self) -> Dict[str, Any]:
        return {'ok': self.ok, 'findings': [f.as_dict() for f in self.findings]}

    @classmethod
    def from_results(cls, results: Optional[Iterable[Any]]) -> 'ValidationDecision':
        """从 `metadata_validator.ValidationResult` 列表构造。"""
        findings: List[ValidationFinding] = []
        for item in results or ():
            level = getattr(item, 'level', None)
            details = getattr(item, 'details', None) or {}
            findings.append(ValidationFinding(
                code=str(details.get('code') or getattr(level, 'value', level)
                         or 'VALIDATION'),
                severity=str(getattr(level, 'value', level) or 'error'),
                message=str(getattr(item, 'message', '') or ''),
                field=str(getattr(item, 'field_id', '') or ''),
                explain=details.get('explain') or (),
            ))
        return cls(tuple(findings))


@dataclass(frozen=True)
class ApprovalRequirement:
    """审批需求（原 `DocumentApprovalResolver.resolve()` 的 typed 形态）。"""

    required: bool
    policy_id: Optional[int] = None
    policy_code: Optional[str] = None
    steps: Tuple[Dict[str, Any], ...] = ()
    amount: float = 0.0
    snapshot: Optional[Dict[str, Any]] = None
    reason: str = ''

    def __post_init__(self) -> None:
        object.__setattr__(self, 'steps', _as_tuple(self.steps))
        try:
            object.__setattr__(self, 'amount', float(self.amount or 0.0))
        except (TypeError, ValueError):
            raise DecisionError('ApprovalRequirement.amount 必须是数值')

    def as_dict(self) -> Dict[str, Any]:
        return {
            'required': self.required,
            'policy_id': self.policy_id,
            'policy_code': self.policy_code,
            'steps': [dict(step) for step in self.steps],
            'amount': self.amount,
            'snapshot': self.snapshot,
            'reason': self.reason,
        }

    @classmethod
    def from_resolve(cls, resolved: Dict[str, Any]) -> 'ApprovalRequirement':
        if not isinstance(resolved, dict) or 'required' not in resolved:
            raise DecisionError('ApprovalRequirement 需要审批解析结果（含 required）')
        return cls(
            required=bool(resolved.get('required')),
            policy_id=resolved.get('policy_id'),
            policy_code=resolved.get('policy_code'),
            steps=resolved.get('steps') or (),
            amount=resolved.get('amount') or 0.0,
            snapshot=resolved.get('snapshot'),
            reason=str(resolved.get('reason') or ''),
        )


@dataclass(frozen=True)
class AssignmentDecision:
    assignee: str = ''
    pool: str = ''
    reason: str = ''

    def as_dict(self) -> Dict[str, Any]:
        return {'assignee': self.assignee, 'pool': self.pool, 'reason': self.reason}


@dataclass(frozen=True)
class DefaultDecision:
    field: str
    value: Any
    source_rule: str = ''

    def as_dict(self) -> Dict[str, Any]:
        return {'field': self.field, 'value': self.value,
                'source_rule': self.source_rule}


@dataclass(frozen=True)
class StateGuardDecision:
    allowed: bool
    from_state: str
    to_state: str
    blocking_rules: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'blocking_rules', tuple(self.blocking_rules or ()))

    def as_dict(self) -> Dict[str, Any]:
        return {
            'allowed': self.allowed,
            'from': self.from_state,
            'to': self.to_state,
            'blocking_rules': list(self.blocking_rules),
        }