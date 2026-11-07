# -*- coding: utf-8 -*-
"""单据规则推导服务（FR-015 / IF-003 / IF-007）。

职责：给定业务对象 + 单据实例，按场景组合现有 Resolver / Explainer，
返回统一信封列表（spec §9.6.2）。只读，不落库、不改变数据。

场景分工：
    - default            -> meta.core.rule_explainer（属性确定）
    - permission         -> meta.core.rule_explainer（权限拒绝 / 放行）
    - state_transition   -> meta.core.rule_explainer（状态流转）
    - approval           -> meta.core.rule_explainer（审批命中）
    - control_parameter  -> ControlParameterResolver.explain（控制参数命中链）
    - line_type          -> LineTypeResolver.explain（行类型命中链）
    - doc_flow           -> doc_flow_rule_store（单据流声明）
"""

import logging
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from meta.core.models import registry

logger = logging.getLogger(__name__)

TRACE_SCENARIOS = (
    'default', 'control_parameter', 'line_type',
    'approval', 'state_transition', 'doc_flow',
)
_CORE_SCENARIOS = ('default', 'permission', 'state_transition', 'approval')
DIMENSION_FIELDS = ('org_id', 'document_type_id', 'line_type_id', 'item_group_id')


class RuleTraceError(ValueError):
    """推导入参非法（API 层转 400）。"""


class RuleTraceNotFound(RuleTraceError):
    """业务对象或单据实例不存在（API 层转 404）。"""


def _envelope(scenario: str, decision: str, *, rule_id: Optional[str] = None,
              source: str = 'code', reason: str = '',
              factors: Optional[Dict[str, Any]] = None,
              detail: Optional[Dict[str, Any]] = None,
              elapsed_ms: float = 0.0, ok: bool = True) -> Dict[str, Any]:
    envelope = {
        'ok': ok,
        'scenario': scenario,
        'decision': decision,
        'rule_id': rule_id,
        'source': source,
        'reason': reason,
        'factors': factors or {},
        'elapsed_ms': round(elapsed_ms, 3),
    }
    if detail is not None:
        envelope['detail'] = detail
    return envelope


def _default_data_source():
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=str(get_meta_db_path()))


class RuleTraceService:
    """单据规则推导（只读）。"""

    def build(self, object_type: str, *, record_id: Any = None,
              data: Optional[Dict[str, Any]] = None,
              scenarios: Optional[Iterable[str]] = None,
              user_id: Optional[int] = None, action_id: str = 'read',
              dims: Optional[Dict[str, Any]] = None,
              codes: Optional[Iterable[str]] = None,
              from_state: Any = None, to_state: Any = None,
              data_source: Any = None) -> Dict[str, Any]:
        if registry.get(object_type) is None:
            raise RuleTraceNotFound(f'object_type 未注册: {object_type!r}')

        record = dict(data) if data else None
        if record is None and record_id is not None:
            record = self._load_record(object_type, record_id)
        if record is None:
            raise RuleTraceError('data 或 record_id 必须提供其一')

        factors = dict(dims or {})
        for field in DIMENSION_FIELDS:
            if factors.get(field) is None and record.get(field) is not None:
                factors[field] = record.get(field)

        selected = self._normalize_scenarios(scenarios)
        ds = data_source or _default_data_source()

        steps: List[Dict[str, Any]] = []
        for scenario in selected:
            steps.append(self._run_scenario(
                scenario, object_type=object_type, record=record,
                record_id=record_id, factors=factors,
                user_id=user_id, action_id=action_id,
                codes=codes, from_state=from_state, to_state=to_state,
                data_source=ds,
            ))

        return {
            'trace_id': uuid.uuid4().hex,
            'object_type': object_type,
            'record_id': record_id,
            'factors': factors,
            'scenarios': steps,
        }

    # ------------------------------------------------------------------
    # 场景分发
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_scenarios(scenarios: Optional[Iterable[str]]) -> List[str]:
        if scenarios is None:
            return list(TRACE_SCENARIOS)
        if isinstance(scenarios, str):
            scenarios = [item.strip() for item in scenarios.split(',') if item.strip()]
        selected = list(scenarios)
        invalid = [item for item in selected if item not in TRACE_SCENARIOS]
        if invalid:
            raise RuleTraceError(
                'scenario 非法: {0}；可选 {1}'.format(invalid, list(TRACE_SCENARIOS)))
        return selected or list(TRACE_SCENARIOS)

    def _run_scenario(self, scenario: str, *, object_type: str,
                      record: Dict[str, Any], record_id: Any,
                      factors: Dict[str, Any], user_id: Optional[int],
                      action_id: str, codes: Optional[Iterable[str]],
                      from_state: Any, to_state: Any,
                      data_source: Any) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            if scenario in _CORE_SCENARIOS:
                return self._core_scenario(
                    scenario, object_type=object_type, record=record,
                    record_id=record_id, user_id=user_id, action_id=action_id,
                    from_state=from_state, to_state=to_state,
                    data_source=data_source,
                )
            if scenario == 'control_parameter':
                return self._control_parameter(record, factors, codes, started)
            if scenario == 'line_type':
                return self._line_type(factors, started)
            return self._doc_flow(object_type, data_source, started)
        except RuleTraceError:
            raise
        except Exception as e:  # noqa: BLE001 - 推导失败不影响其它场景
            logger.warning('[rule_trace] scenario %s 推导失败: %s', scenario, e)
            return _envelope(
                scenario, 'skipped', reason='trace_failed',
                factors={'error': str(e)},
                elapsed_ms=(time.perf_counter() - started) * 1000, ok=False,
            )

    def _core_scenario(self, scenario: str, *, object_type: str,
                       record: Dict[str, Any], record_id: Any,
                       user_id: Optional[int], action_id: str,
                       from_state: Any, to_state: Any,
                       data_source: Any) -> Dict[str, Any]:
        from meta.core.rule_explainer import explain

        if scenario == 'default':
            return explain(object_type, 'default', data=record,
                           data_source=data_source)
        if scenario == 'permission':
            return explain(object_type, 'permission', user_id=user_id,
                           action_id=action_id)
        if scenario == 'state_transition':
            state_field = factors_state_field(record)
            return explain(
                object_type, 'state_transition',
                state_field=state_field,
                from_state=from_state if from_state is not None
                else record.get(state_field),
                to_state=to_state,
            )
        return explain(object_type, 'approval', record_id=record_id,
                       data_source=data_source)

    def _control_parameter(self, record: Dict[str, Any],
                           factors: Dict[str, Any],
                           codes: Optional[Iterable[str]],
                           started: float) -> Dict[str, Any]:
        from meta.services.control_parameter_service import (
            get_control_parameter_resolver,
        )

        requested = list(codes or [])
        if not requested:
            return _envelope(
                'control_parameter', 'skipped', source='db',
                reason='no_codes_requested', factors=dict(factors),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

        resolver = get_control_parameter_resolver()
        chain = [resolver.explain(code, factors) for code in requested]
        missing = [entry['code'] for entry in chain
                   if entry.get('source', {}).get('type') == 'missing']
        return _envelope(
            'control_parameter', 'resolved' if chain else 'skipped',
            rule_id='control_parameter:' + ','.join(requested),
            source='db', reason='resolved' if chain else 'no_codes_requested',
            factors=dict(factors),
            detail={'codes': requested, 'missing': missing, 'chain': chain},
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def _line_type(self, factors: Dict[str, Any], started: float) -> Dict[str, Any]:
        from meta.services.line_type_service import get_line_type_resolver

        doc_type_id = factors.get('document_type_id')
        if doc_type_id is None:
            return _envelope(
                'line_type', 'skipped', source='db',
                reason='document_type_id_missing', factors=dict(factors),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )

        result = get_line_type_resolver().explain(
            doc_type_id, factors.get('item_group_id'))
        return _envelope(
            'line_type', 'resolved' if result.get('line_type_id') is not None
            else 'missing',
            rule_id=('line_type:{0}.{1}'.format(
                doc_type_id, factors.get('item_group_id') or '*')),
            source='db', reason=str(result.get('source') or 'missing'),
            factors=dict(factors),
            detail=result,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def _doc_flow(self, object_type: str, data_source: Any,
                  started: float) -> Dict[str, Any]:
        from meta.core.doc_flow_rule_store import list_rules

        rules = [
            rule for rule in list_rules(data_source)
            if rule.get('source_bo') == object_type and rule.get('status') == 'active'
        ]
        return _envelope(
            'doc_flow', 'declared' if rules else 'not_declared', source='db',
            reason='doc_flow_declared' if rules else 'no_doc_flow_rule',
            factors={'source_bo': object_type},
            detail={
                'rules': [
                    {
                        'rule_id': rule.get('rule_id'),
                        'target_bo': rule.get('target_bo'),
                        'pool': rule.get('pool'),
                        'status': rule.get('status'),
                    }
                    for rule in rules
                ],
            },
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    # ------------------------------------------------------------------
    # 记录装载
    # ------------------------------------------------------------------

    @staticmethod
    def _load_record(object_type: str, record_id: Any) -> Dict[str, Any]:
        from meta.core.bo_framework import bo_framework

        result = bo_framework.read(object_type, record_id)
        if not getattr(result, 'success', False):
            raise RuleTraceNotFound(
                getattr(result, 'message', None) or '记录不存在')
        data = getattr(result, 'data', None)
        if not isinstance(data, dict):
            raise RuleTraceNotFound('记录不存在')
        return data


def factors_state_field(record: Dict[str, Any]) -> str:
    """单据状态字段名（缺省 status，兼容 state / doc_status）。"""
    for candidate in ('status', 'state', 'doc_status'):
        if candidate in record:
            return candidate
    return 'status'


_default_service: Optional[RuleTraceService] = None


def get_rule_trace_service() -> RuleTraceService:
    global _default_service
    if _default_service is None:
        _default_service = RuleTraceService()
    return _default_service