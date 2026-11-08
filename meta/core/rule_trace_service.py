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
from meta.core.rule_keys import (
    DIMENSION_FIELDS,
    control_parameter_codes_key,
    line_type_key,
)

logger = logging.getLogger(__name__)

TRACE_SCENARIOS = (
    'default', 'control_parameter', 'line_type',
    'approval', 'state_transition', 'doc_flow',
)
# [v1.8 2026-11-07] permission 场景依赖 user_id，单据推导接口不传该入参，
# 纳入白名单只会产生"永远跳过"的假场景，故从核心场景集移除。
_CORE_SCENARIOS = ('default', 'state_transition', 'approval')
# 因子轴由 meta.core.rule_keys.DIMENSION_FIELDS 唯一声明（spec §13.1 / F-13-12）
# 控制参数命中链的取值来源（视图元数据 trace.source_types 同源，spec §13.4）
SOURCE_TYPES = ('value', 'default', 'missing')

# [v1.8 2026-11-07] 决策归一：decision 保留场景细分词（applied/allowed/...），
# kind 统一为 hit / miss / skip / info，供前端着色与汇总，避免每个场景各自造词。
DECISION_KINDS = {
    'applied': 'hit',
    'granted': 'hit',
    'allowed': 'hit',
    'matched': 'hit',
    'resolved': 'hit',
    'declared': 'hit',
    'rejected': 'miss',
    'denied': 'miss',
    'not_matched': 'miss',
    'missing': 'miss',
    'not_declared': 'miss',
    'skipped': 'skip',
    'not_instrumented': 'skip',
}

# [L1 2026-11-08] 运行期节点上限（spec §11.4）：超出只截断返回体积，不影响求值；
# 截断标记与 kind 计数挂在返回体侧（`truncated` / `kind_counts`）。
MAX_TRACE_NODES = 200

# 场景 → 执行阶段（spec §11.3 stage 枚举）：只用于展示分组，不参与求值。
STAGE_MAP = {
    'default': 'before_save',
    'control_parameter': 'calc',
    'line_type': 'calc',
    'approval': 'approve',
    'state_transition': 'status_transition',
    'doc_flow': 'validate',
}


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
        'kind': DECISION_KINDS.get(decision, 'info'),
        'rule_id': rule_id,
        'source': source,
        'reason': reason,
        'factors': factors or {},
        'elapsed_ms': round(elapsed_ms, 3),
    }
    if detail is not None:
        envelope['detail'] = detail
    return envelope


def _same_value(left: Any, right: Any) -> bool:
    """与 ControlParameterResolver._matches 同口径的宽松比较。"""
    if left is None or right is None:
        return left is None and right is None
    return str(left) == str(right)


def _output_of(step: Dict[str, Any]) -> Dict[str, Any]:
    """节点写出的字段与值（spec §11.3）；无写入时返回空字典。

    只收录已确认写入的值：`default` 取 winner 赋值、`control_parameter`
    取已解析的编码值、`line_type` 取行类型、`state_transition` 取目标状态；
    `approval` / `doc_flow` 只做判定不写字段，保持空字典。
    """
    scenario = step.get('scenario')
    decision = step.get('decision')
    factors = step.get('factors') or {}
    detail = step.get('detail') or {}

    if scenario == 'default':
        target = factors.get('target_field')
        if decision == 'applied' and target and factors.get('value') is not None:
            return {str(target): factors.get('value')}
    elif scenario == 'control_parameter':
        output = {}
        for entry in detail.get('chain') or []:
            if isinstance(entry, dict) and entry.get('value') is not None:
                output[str(entry.get('code'))] = entry.get('value')
        return output
    elif scenario == 'line_type':
        line_type_id = detail.get('line_type_id')
        if line_type_id is not None:
            return {'line_type_id': line_type_id}
    elif scenario == 'state_transition':
        if decision == 'allowed':
            state_field = factors.get('state_field') or 'status'
            return {str(state_field): factors.get('to_state')}
    return {}


def _match_of(step: Dict[str, Any]) -> Dict[str, Any]:
    """判定条件与结果（spec §11.3）。

    只回填可核对的字段对比：状态流转的 from/to、控制参数的维度匹配、
    行类型的 item_group_id。其余场景（default 条件表达式、审批阈值、
    单据流声明）平台侧拿不到期望值，conditions 留空，不臆造比对项。
    """
    scenario = step.get('scenario')
    factors = step.get('factors') or {}
    detail = step.get('detail') or {}
    conditions: List[Dict[str, Any]] = []

    if scenario == 'state_transition':
        states = [str(item) for item in (factors.get('states') or [])]
        from_state = factors.get('from_state')
        if from_state is not None and states:
            conditions.append({
                'field': 'from_state', 'op': 'in',
                'expected': states, 'actual': from_state,
                'passed': str(from_state) in states,
            })
        allowed = [str(item) for item in (factors.get('allowed_to_states') or [])]
        to_state = factors.get('to_state')
        if to_state is not None:
            conditions.append({
                'field': 'to_state', 'op': 'in',
                'expected': allowed, 'actual': to_state,
                'passed': str(to_state) in allowed,
            })
    elif scenario == 'control_parameter':
        for entry in detail.get('chain') or []:
            if not isinstance(entry, dict):
                continue
            candidates = entry.get('candidates') or []
            dims = candidates[0].get('dims') if candidates else {}
            for field in DIMENSION_FIELDS:
                expected = (dims or {}).get(field)
                if expected is None:  # 通配维度不构成条件
                    continue
                actual = factors.get(field)
                conditions.append({
                    'field': field, 'op': '=',
                    'expected': expected, 'actual': actual,
                    'passed': _same_value(actual, expected),
                })
    elif scenario == 'line_type':
        candidates = detail.get('candidates') or []
        expected = candidates[0].get('item_group_id') if candidates else None
        if expected is not None:
            conditions.append({
                'field': 'item_group_id', 'op': '=',
                'expected': expected,
                'actual': factors.get('item_group_id'),
                'passed': _same_value(factors.get('item_group_id'), expected),
            })

    return {'matched': step.get('kind') == 'hit', 'conditions': conditions}


def _kind_counts(steps: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for step in steps:
        kind = step.get('kind') or 'info'
        counts[kind] = counts.get(kind, 0) + 1
    return counts


# 规则全集归属（spec §11.4）：下游声明 / 条件未命中 / 本次已评估
SCOPE_EVALUATED = 'evaluated'
SCOPE_NOT_TRIGGERED = 'not_triggered'
SCOPE_DOWNSTREAM = 'downstream'


def scope_of(scenario: str, status: Any) -> str:
    """归属判定的唯一真源；渲染层不得再按场景名/状态自行推导。"""
    if scenario == 'doc_flow':
        return SCOPE_DOWNSTREAM
    if status == 'not_matched':
        return SCOPE_NOT_TRIGGERED
    return SCOPE_EVALUATED


def _scope_rules(node: Dict[str, Any]) -> Any:
    """为 detail.rules 每行补 scope，保持节点自身结构不变。"""
    detail = node.get('detail')
    if not isinstance(detail, dict):
        return detail
    rules = detail.get('rules')
    if not isinstance(rules, list):
        return detail
    scenario = node.get('scenario') or ''
    decorated = dict(detail)
    decorated['rules'] = [
        dict(rule, scope=scope_of(scenario, rule.get('status')))
        if isinstance(rule, dict) else rule
        for rule in rules
    ]
    return decorated


def _default_data_source():
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return get_data_source('sqlite', database=str(get_meta_db_path()))


class RuleTraceService:
    """单据规则推导（只读）。"""

    def build(self, object_type: str, *, record_id: Any = None,
              data: Optional[Dict[str, Any]] = None,
              scenarios: Optional[Iterable[str]] = None,
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
        factor_sources: Dict[str, str] = {}
        for field in DIMENSION_FIELDS:
            if (dims or {}).get(field) is not None:
                # 请求显式传入的因子优先，快照需标注来源，避免与单据取值混淆
                factor_sources[field] = 'override'
            elif record.get(field) is not None:
                factors[field] = record.get(field)
                factor_sources[field] = 'record'
            else:
                factor_sources[field] = 'missing'

        selected = self._normalize_scenarios(scenarios)
        ds = data_source or _default_data_source()

        steps: List[Dict[str, Any]] = []
        for scenario in selected:
            steps.append(self._run_scenario(
                scenario, object_type=object_type, record=record,
                record_id=record_id, factors=factors,
                codes=codes, from_state=from_state, to_state=to_state,
                data_source=ds,
            ))

        trace_id = uuid.uuid4().hex
        # 截断只影响返回体积，不影响求值：kind_counts 按完整结果统计
        kind_counts = _kind_counts(steps)
        nodes = self._decorate_steps(trace_id, steps)
        return {
            'trace_id': trace_id,
            'object_type': object_type,
            'record_id': record_id,
            'factors': factors,
            'factor_sources': factor_sources,
            'scenarios': nodes,
            'truncated': len(steps) > MAX_TRACE_NODES,
            'node_count': len(nodes),
            'kind_counts': kind_counts,
        }

    @staticmethod
    def _decorate_steps(trace_id: str,
                        steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """补齐运行期节点字段（spec §11.3）。

        L1 不跨对象递归，`parent_id` 恒为 null；`seq` 在同一 trace 内从 1 递增。
        """
        decorated: List[Dict[str, Any]] = []
        for index, step in enumerate(steps[:MAX_TRACE_NODES], start=1):
            node = dict(step)
            node['seq'] = index
            node['node_id'] = f'{trace_id}:{index}'
            node['parent_id'] = None
            node['stage'] = STAGE_MAP.get(node.get('scenario'), 'validate')
            node['scope'] = scope_of(node.get('scenario') or '', node.get('decision'))
            node['match'] = _match_of(node)
            node['output'] = _output_of(node)
            node['detail'] = _scope_rules(node)
            decorated.append(node)
        return decorated

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
                      factors: Dict[str, Any], codes: Optional[Iterable[str]],
                      from_state: Any, to_state: Any,
                      data_source: Any) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            if scenario in _CORE_SCENARIOS:
                result = self._core_scenario(
                    scenario, object_type=object_type, record=record,
                    record_id=record_id, from_state=from_state,
                    to_state=to_state, data_source=data_source,
                )
            elif scenario == 'control_parameter':
                result = self._control_parameter(record, factors, codes, started)
            elif scenario == 'line_type':
                result = self._line_type(factors, started)
            else:
                result = self._doc_flow(object_type, data_source, started)
        except RuleTraceError:
            raise
        except Exception as e:  # noqa: BLE001 - 推导失败不影响其它场景
            logger.warning('[rule_trace] scenario %s 推导失败: %s', scenario, e)
            return _envelope(
                scenario, 'skipped', reason='trace_failed',
                factors={'error': str(e)},
                elapsed_ms=(time.perf_counter() - started) * 1000, ok=False,
            )
        # explainer 返回的信封不含 kind，此处统一补齐归一类别
        result['kind'] = DECISION_KINDS.get(result.get('decision'), 'info')
        return result

    def _core_scenario(self, scenario: str, *, object_type: str,
                       record: Dict[str, Any], record_id: Any,
                       from_state: Any, to_state: Any,
                       data_source: Any) -> Dict[str, Any]:
        from meta.core.rule_explainer import explain

        if scenario == 'default':
            return explain(object_type, 'default', data=record,
                           data_source=data_source)
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
        # [v1.8 2026-11-07] chain 恒非空，原实现「有请求即 resolved」会误报；
        # 全部编码都没取到值时必须如实报告 missing。
        if missing and len(missing) == len(requested):
            decision, reason = 'missing', 'all_codes_missing'
        elif missing:
            decision, reason = 'resolved', 'partially_resolved'
        else:
            decision, reason = 'resolved', 'resolved'
        return _envelope(
            'control_parameter', decision,
            rule_id=control_parameter_codes_key(requested),
            source='db', reason=reason,
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
            rule_id=line_type_key(doc_type_id, factors.get('item_group_id')),
            source='db', reason=str(result.get('source') or 'missing'),
            factors=dict(factors),
            detail=result,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    def _doc_flow(self, object_type: str, data_source: Any,
                  started: float) -> Dict[str, Any]:
        from meta.core.rule_provider import list_doc_flow_rules

        rules = [
            rule for rule in list_doc_flow_rules(data_source)
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