# -*- coding: utf-8 -*-
"""判定规则化：``constraint`` 规则的多 key 判定与 explain（spec-rule-model M6b）

契约（§11.2.1）：

- 复用 ``constraint`` rule_type，不扩 ``RuleType`` 枚举；
- 规则显式声明 ``combine_mode=any|all``（默认 ``all``），聚合各 key 的判定；
- key 内限值由参数 resolver 按 ``specificity_rank`` 首命中，explain 直接引用；
- key 之间**全部求值**（不短路），severity 升级 ``error > warning > info``，
  处置动作取最高等级；
- explain 拆两节点：``limit`` 引用参数 explain，``verdict`` 只记度量值 /
  比较符 / 结论，不重复限值字段；
- ``hold`` 为独立结果（可存不可过），必须声明释放动作（加载期校验）。

本模块只做判定，不落库、不改单据状态；``holds`` 持久化与释放路径另行实施。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from meta.core.models_enums import ValidationSeverity
from meta.core.rule_action_matrix import BLOCK, HOLD, NOTIFY
from meta.core.rule_combine_mode import normalize_combine_mode
from meta.core.rule_metrics import MetricSession

#: key 级 severity 词表（复用字段校验的 severity 枚举，不另造一套）
KEY_SEVERITIES = tuple(item.value for item in ValidationSeverity)

#: 超限动作等级（M6b「动作取最高等级」）；只登记 constraint 矩阵允许的动作
ACTION_PRECEDENCE = {BLOCK: 3, HOLD: 2, NOTIFY: 1}

#: severity 升级顺序
SEVERITY_PRECEDENCE = {
    ValidationSeverity.INFO.value: 1,
    ValidationSeverity.WARNING.value: 2,
    ValidationSeverity.ERROR.value: 3,
}

#: 未声明容差方向 / 基准时的回退口径
DEFAULT_DIRECTION = 'both'
DEFAULT_BASIS = 'absolute'


class ConstraintEvaluationError(ValueError):
    """约束判定配置 / 求值错误（未声明 key、参数或度量不存在等）。"""


@dataclass(frozen=True)
class ConstraintKeyResult:
    """单个 key 的判定结果（limit + verdict 两节点）。"""

    parameter: str
    metric: str
    direction: str
    basis: str
    severity: str
    disposition: str
    limit: Dict[str, Any]
    verdict: Dict[str, Any]
    exceeded: bool

    def explain(self) -> List[Dict[str, Any]]:
        return [
            {'node': 'limit', 'parameter': self.parameter, **self.limit},
            {'node': 'verdict', **self.verdict},
        ]


@dataclass(frozen=True)
class ConstraintDecision:
    """一条 constraint 规则的整体判定结果。"""

    rule_key: str
    combine_mode: str
    matched: bool
    severity: str
    action: str
    release_action: str
    keys: Tuple[ConstraintKeyResult, ...]

    def explain(self) -> List[Dict[str, Any]]:
        """按 key 顺序展开两节点 explain，保证相同输入逐字节一致（NFR-001）。"""
        items: List[Dict[str, Any]] = []
        for key in self.keys:
            items.extend(key.explain())
        return items


def _severity_value(value: Any) -> str:
    raw = getattr(value, 'value', value)
    text = str(raw or '').strip().lower()
    return text or ValidationSeverity.ERROR.value


def _definition_of(resolver: Any, code: str, dims: Dict[str, Any]) -> Dict[str, Any]:
    detail = resolver.candidates(code, dims)
    definition = detail.get('definition') if detail.get('defined') else None
    return definition or {}


def _compare(value: Any, limit: Any, direction: str) -> Tuple[bool, str]:
    """按容差方向比较度量值与限值，返回（是否超限、比较符）。

    限值一律按正数量级解释：``under`` 方向下欠交为负偏差，比较 ``value < -limit``。
    """
    try:
        actual = float(value)
        bound = float(limit)
    except (TypeError, ValueError):
        raise ConstraintEvaluationError(
            '度量值或限值不是数字：value=%r limit=%r' % (value, limit))
    if direction == 'over':
        return actual > bound, 'gt'
    if direction == 'under':
        return actual < -bound, 'lt'
    return abs(actual) > bound, 'abs_gt'


def _evaluate_key(rule: Any, key: Mapping[str, Any], *,
                  metrics: MetricSession, resolver: Any,
                  dims: Dict[str, Any],
                  overrides: Mapping[str, Any]) -> ConstraintKeyResult:
    parameter = str(key.get('parameter') or '').strip()
    metric = str(key.get('metric') or '').strip()
    if not parameter or not metric:
        raise ConstraintEvaluationError(
            '约束规则 %s 的 key 必须同时声明 parameter 与 metric'
            % getattr(rule, 'id', ''))

    explain = resolver.explain(parameter, dims)
    definition = _definition_of(resolver, parameter, dims)
    override = overrides.get(parameter)
    if override is not None:
        limit_value = override
        source = {'type': 'instance'}
    else:
        limit_value = explain.get('value')
        source = explain.get('source') or {}
        if not definition and limit_value is None:
            raise ConstraintEvaluationError(
                '参数 %s 不存在（既无定义也无实例覆盖）' % parameter)
    if limit_value is None:
        raise ConstraintEvaluationError('参数 %s 未取到限值' % parameter)

    direction = str(definition.get('tolerance_direction') or
                    DEFAULT_DIRECTION).strip().lower()
    basis = str(definition.get('tolerance_basis') or
                DEFAULT_BASIS).strip().lower()

    try:
        actual = metrics.resolve(metric)
    except Exception as exc:  # MetricError 等统一收敛为判定错误
        raise ConstraintEvaluationError(
            '度量 %s 求值失败：%s' % (metric, exc)) from exc

    exceeded, op = _compare(actual, limit_value, direction)
    severity = _severity_value(
        key.get('severity') or getattr(rule, 'severity', ''))
    disposition = str(
        key.get('disposition') or getattr(rule, 'disposition', '') or ''
    ).strip().lower()

    return ConstraintKeyResult(
        parameter=parameter,
        metric=metric,
        direction=direction,
        basis=basis,
        severity=severity,
        disposition=disposition,
        # limit 节点直接引用参数 explain 候选链，并给出实际生效限值与来源
        limit={'value': limit_value, 'source': source, 'explain': explain},
        # verdict 只记度量值 / 比较符 / 结论，不重复限值字段
        verdict={'metric': metric, 'actual': actual, 'op': op, 'passed': not exceeded},
        exceeded=exceeded,
    )


def evaluate_constraint_rule(
        rule: Any,
        *,
        metrics: MetricSession,
        dims: Optional[Dict[str, Any]] = None,
        resolver: Any = None,
        overrides: Optional[Mapping[str, Any]] = None) -> ConstraintDecision:
    """对一条 ``constraint`` 规则执行多 key 判定。

    - ``metrics``：单据级 ``MetricSession``，保证同一度量只算一次；
    - ``dims``：参数解析维度（customer / supplier / material 等）；
    - ``resolver``：控制参数 resolver，缺省取全局单例；
    - ``overrides``：实例层限值（单据头容差等），按 parameter code 覆盖。
    """
    keys = list(getattr(rule, 'keys', None) or [])
    if not keys:
        raise ConstraintEvaluationError(
            '约束规则 %s 未声明 keys，不能执行多键判定' % getattr(rule, 'id', ''))

    if resolver is None:
        from meta.services.control_parameter_service import (
            get_control_parameter_resolver,
        )
        resolver = get_control_parameter_resolver()

    dims = dict(dims or {})
    overrides = dict(overrides or {})

    results = tuple(
        _evaluate_key(rule, key, metrics=metrics, resolver=resolver,
                      dims=dims, overrides=overrides)
        for key in keys
    )

    mode = normalize_combine_mode(getattr(rule, 'combine_mode', ''))
    exceeded = [item for item in results if item.exceeded]
    if mode == 'any':
        matched = bool(exceeded)
    elif mode == 'all':
        matched = len(exceeded) == len(results)
    else:  # 词表已在加载期校验；此处只防御未经过校验的直构规则
        raise ConstraintEvaluationError(
            'combine_mode %r 不在 %s' % (mode, list(('any', 'all'))))

    if not matched:
        return ConstraintDecision(
            rule_key=str(getattr(rule, 'id', '') or ''),
            combine_mode=mode,
            matched=False,
            severity='',
            action='',
            release_action=str(getattr(rule, 'release_action', '') or ''),
            keys=results,
        )

    severity = max(
        (item.severity for item in exceeded),
        key=lambda value: SEVERITY_PRECEDENCE.get(value, 0),
    )
    action = max(
        (item.disposition for item in exceeded if item.disposition),
        key=lambda value: ACTION_PRECEDENCE.get(value, 0),
        default='',
    )
    return ConstraintDecision(
        rule_key=str(getattr(rule, 'id', '') or ''),
        combine_mode=mode,
        matched=True,
        severity=severity,
        action=action,
        release_action=str(getattr(rule, 'release_action', '') or ''),
        keys=results,
    )