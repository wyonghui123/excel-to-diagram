# -*- coding: utf-8 -*-
"""规则试算（FR-017 / IF-008）。

对给定因子快照，返回某场景的候选集、命中规则、最终值与解释；可选 ``config_mode``
做 baseline（仅 active）与 draft（active + draft）对照。全程只读：不落库、不改变业务数据。

场景接入程度：
    control_parameter   完整（复用 ControlParameterResolver 的匹配，暴露完整候选集）
    line_type           完整（复用 LineTypeResolver）
    其余场景             需 record_id / data，委托 RuleTraceService 单场景推导；
                        缺上下文时如实返回 ``not_instrumented``，不伪造结果。

缓存：进程内 30 秒，发布流调用 ``invalidate_simulate_cache`` 立即失效。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from meta.core.rule_trace_service import (
    DIMENSION_FIELDS,
    TRACE_SCENARIOS,
    RuleTraceError,
    RuleTraceNotFound,
    RuleTraceService,
    get_rule_trace_service,
)

logger = logging.getLogger(__name__)

CONFIG_MODES = ('baseline', 'draft', 'both')
MAX_CODES = 20
MAX_CANDIDATES = 500
CACHE_TTL_SECONDS = 30.0

_COMPLETED_SCENARIOS = ('control_parameter', 'line_type')

_cache: Dict[Tuple[Any, ...], Tuple[float, Dict[str, Any]]] = {}
_generation = 0


class RuleSimulateError(ValueError):
    """试算入参非法（API 层转 400）。"""


def invalidate_simulate_cache() -> None:
    """配置变更后调用：清空试算缓存。"""
    global _generation
    _generation += 1
    _cache.clear()


class RuleSimulateService:
    """规则试算（只读）。"""

    def simulate(self, scenario: str, *,
                 factors: Optional[Dict[str, Any]] = None,
                 record_id: Any = None,
                 codes: Optional[Iterable[str]] = None,
                 config_mode: str = 'baseline',
                 object_type: Optional[str] = None,
                 data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        started = time.perf_counter()
        if not scenario:
            raise RuleSimulateError('scenario 不能为空')
        if scenario not in TRACE_SCENARIOS:
            raise RuleSimulateError(
                'scenario 非法: {0}；可选 {1}'.format(scenario, list(TRACE_SCENARIOS)))

        mode = str(config_mode or 'baseline').lower()
        if mode not in CONFIG_MODES:
            raise RuleSimulateError(
                'config_mode 非法: {0}；可选 {1}'.format(config_mode, list(CONFIG_MODES)))

        resolved = self._resolve_factors(factors, record_id, object_type, data)
        dims = {f: resolved[f] for f in DIMENSION_FIELDS if resolved.get(f) is not None}
        code_list = self._normalize_codes(codes)
        if scenario == 'control_parameter' and not code_list:
            raise RuleSimulateError('控制参数试算必须提供 codes')

        key = (scenario, mode, object_type, record_id,
               tuple(sorted((k, str(v)) for k, v in dims.items())),
               tuple(code_list or ()), _generation)
        cached = _cache.get(key)
        if cached and (time.time() - cached[0]) < CACHE_TTL_SECONDS:
            result = dict(cached[1])
            result['cached'] = True
            return result

        if scenario == 'control_parameter':
            payload = self._with_modes(
                lambda include_draft: self._control_parameter(code_list, dims, include_draft),
                mode)
        elif scenario == 'line_type':
            payload = self._with_modes(
                lambda include_draft: self._line_type(dims, include_draft),
                mode)
        else:
            payload = self._delegate(scenario, dims, record_id, object_type, data)

        elapsed = (time.perf_counter() - started) * 1000
        result = {
            'ok': True,
            'scenario': scenario,
            'config_mode': mode,
            'source': payload.get('source') or 'code',
            'rule_id': payload.get('rule_id'),
            'reason': payload.get('reason') or '',
            'factors': resolved,
            'candidates': payload.get('candidates') or [],
            'final': payload.get('final'),
            'results': payload.get('results') or [],
            'elapsed_ms': round(elapsed, 3),
            'trace_id': _trace_id(),
            'cached': False,
        }
        if 'baseline' in payload:
            result['decision'] = payload['draft']['decision']
            result['baseline'] = payload['baseline']
            result['draft'] = payload['draft']
            result['diff'] = payload['diff']
        else:
            result['decision'] = payload.get('decision') or 'unknown'
            result['baseline'] = payload if mode == 'baseline' else None
            result['draft'] = payload if mode == 'draft' else None
            result['diff'] = []

        _cache[key] = (time.time(), result)
        return result

    # ------------------------------------------------------------------
    # 场景实现
    # ------------------------------------------------------------------

    def _with_modes(self, runner, mode: str) -> Dict[str, Any]:
        if mode == 'baseline':
            return runner(False)
        if mode == 'draft':
            return runner(True)
        baseline = runner(False)
        draft = runner(True)
        return {
            'source': draft.get('source'),
            'rule_id': draft.get('rule_id'),
            'reason': draft.get('reason'),
            'candidates': draft.get('candidates') or [],
            'final': draft.get('final'),
            'results': draft.get('results') or [],
            'baseline': baseline,
            'draft': draft,
            'diff': _diff(baseline, draft),
        }

    def _control_parameter(self, codes: List[str], dims: Dict[str, Any],
                           include_draft: bool) -> Dict[str, Any]:
        from meta.services.control_parameter_service import (
            get_control_parameter_resolver,
        )

        resolver = get_control_parameter_resolver()
        results: List[Dict[str, Any]] = []
        candidates: List[Dict[str, Any]] = []

        for code in codes:
            info = resolver.candidates(code, dims, include_draft)
            rows = info.get('rows') or []
            hit = info.get('hit')
            if len(rows) > MAX_CANDIDATES:
                raise RuleSimulateError(
                    f'参数 {code} 候选过多（{len(rows)} > {MAX_CANDIDATES}），请收窄因子')

            annotated = []
            for row in rows:
                is_hit = hit is not None and row.get('id') == hit.get('id')
                if is_hit:
                    reason = '命中（首个匹配，specificity_rank 最小）'
                elif resolver._matches(row, dims):
                    reason = '维度匹配但被更具体规则覆盖'
                else:
                    reason = '维度不匹配'
                annotated.append({
                    'code': code,
                    'value_id': row.get('id'),
                    'specificity_rank': row.get('specificity_rank'),
                    'specificity': sum(1 for f in DIMENSION_FIELDS
                                       if row.get(f) is not None),
                    'dims': {f: row.get(f) for f in DIMENSION_FIELDS},
                    'value': row.get('value'),
                    'status': row.get('status') or 'active',
                    'hit': bool(is_hit),
                    'reason': reason,
                })
            candidates.extend(annotated)

            if not info.get('defined'):
                results.append({
                    'code': code, 'decision': 'not_instrumented',
                    'reason': f'参数 {code} 未定义', 'value': None,
                    'from': 'missing', 'fallback': False, 'value_id': None,
                    'candidates': annotated,
                })
                continue

            definition = info.get('definition') or {}
            if hit is not None:
                results.append({
                    'code': code, 'decision': 'hit',
                    'reason': '命中更具体取值',
                    'value': resolver._convert(definition, hit.get('value')),
                    'raw_value': hit.get('value'),
                    'from': 'specific', 'fallback': False,
                    'value_id': hit.get('id'),
                    'specificity_rank': hit.get('specificity_rank'),
                    'candidates': annotated,
                })
                continue

            default_raw = info.get('default_value')
            if default_raw is None:
                results.append({
                    'code': code, 'decision': 'missing',
                    'reason': '无匹配取值且未配置默认值', 'value': None,
                    'from': 'default', 'fallback': True, 'value_id': None,
                    'candidates': annotated,
                })
            else:
                results.append({
                    'code': code, 'decision': 'default',
                    'reason': '无匹配取值，回落默认值',
                    'value': resolver._convert(definition, default_raw),
                    'raw_value': default_raw,
                    'from': 'default', 'fallback': True, 'value_id': None,
                    'candidates': annotated,
                })

        decisions = {r['decision'] for r in results}
        if decisions == {'hit'}:
            decision = 'hit'
        elif 'hit' in decisions:
            decision = 'mixed'
        elif decisions == {'default'}:
            decision = 'default'
        elif decisions == {'missing'}:
            decision = 'missing'
        else:
            decision = 'not_instrumented'

        return {
            'decision': decision,
            'source': 'db:control_parameter_values',
            'rule_id': 'control_parameter:' + ','.join(codes),
            'reason': '' if decision == 'hit' else '部分或全部参数未命中具体取值',
            'candidates': candidates,
            'final': _final_of_control_parameter(results),
            'results': results,
        }

    def _line_type(self, dims: Dict[str, Any], include_draft: bool) -> Dict[str, Any]:
        from meta.services.line_type_service import get_line_type_resolver

        resolver = get_line_type_resolver()
        doc_type_id = dims.get('document_type_id')
        item_group_id = dims.get('item_group_id')
        info = resolver.candidates(doc_type_id, item_group_id, include_draft)
        rows = info.get('rows') or []
        hit = info.get('hit')
        if len(rows) > MAX_CANDIDATES:
            raise RuleSimulateError(
                f'行类型候选过多（{len(rows)} > {MAX_CANDIDATES}），请收窄因子')

        candidates = []
        for row in rows:
            is_hit = hit is not None and row.get('id') == hit.get('id')
            if is_hit:
                reason = '命中（首个匹配，specificity_rank 最小）'
            elif _line_type_matches(row, item_group_id):
                reason = '物料组匹配但被更具体规则覆盖'
            else:
                reason = '物料组不匹配'
            candidates.append({
                'assignment_id': row.get('id'),
                'document_type_id': row.get('document_type_id'),
                'item_group_id': row.get('item_group_id'),
                'specificity_rank': row.get('specificity_rank'),
                'specificity': 1 if row.get('item_group_id') is not None else 0,
                'line_type_id': row.get('line_type_id'),
                'status': row.get('status') or 'active',
                'hit': bool(is_hit),
                'reason': reason,
            })

        resolved = resolver.resolve(doc_type_id, item_group_id, include_draft)
        if not info.get('doc_type_exists'):
            decision = 'not_instrumented'
            reason = f'单据类型 {doc_type_id!r} 不存在或已停用'
        elif resolved.get('source') == 'assignment':
            decision = 'hit'
            reason = '命中行类型确定规则'
        elif resolved.get('source') == 'default':
            decision = 'default'
            reason = '未命中确定规则，回落单据类型默认行类型'
        else:
            decision = 'missing'
            reason = '未命中确定规则且单据类型未配置默认行类型'

        rule_key = 'line_type:{0}.{1}'.format(
            doc_type_id if doc_type_id is not None else '*',
            item_group_id if item_group_id is not None else '*')
        final = {
            'line_type_id': resolved.get('line_type_id'),
            'from': resolved.get('source'),
            'fallback': resolved.get('source') == 'default',
            'assignment_id': resolved.get('assignment_id'),
            'doc_type_id': doc_type_id,
            'item_group_id': item_group_id,
        }
        return {
            'decision': decision,
            'source': 'db:line_type_assignments',
            'rule_id': rule_key,
            'reason': reason,
            'candidates': candidates,
            'final': final,
            'results': [{'code': 'line_type_id', 'decision': decision,
                         'value': final['line_type_id'], 'from': final['from'],
                         'fallback': final['fallback'],
                         'assignment_id': final['assignment_id'],
                         'candidates': candidates}],
        }

    def _delegate(self, scenario: str, dims: Dict[str, Any], record_id: Any,
                  object_type: Optional[str],
                  data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not object_type:
            raise RuleSimulateError('该场景试算必须提供 object_type')
        try:
            trace = get_rule_trace_service().build(
                object_type, record_id=record_id, data=data,
                scenarios=[scenario], dims=dims)
        except RuleTraceNotFound:
            raise
        except RuleTraceError as e:
            raise RuleSimulateError(str(e)) from e

        step = (trace.get('scenarios') or [{}])[0]
        decision = step.get('decision') or 'not_instrumented'
        return {
            'decision': decision,
            'source': step.get('source') or 'code',
            'rule_id': step.get('rule_id'),
            'reason': step.get('reason') or '',
            'candidates': (step.get('detail') or {}).get('candidates') or [],
            'final': (step.get('detail') or {}).get('result'),
            'results': [],
        }

    # ------------------------------------------------------------------
    # 因子解析
    # ------------------------------------------------------------------

    def _resolve_factors(self, factors: Optional[Dict[str, Any]], record_id: Any,
                         object_type: Optional[str],
                         data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        resolved = {f: (factors or {}).get(f) for f in DIMENSION_FIELDS}
        record = dict(data) if data else None
        if record_id is not None:
            if not object_type:
                raise RuleSimulateError('使用 record_id 时必须提供 object_type')
            if record is None:
                record = RuleTraceService._load_record(object_type, record_id)
        if record:
            for field in DIMENSION_FIELDS:
                if resolved.get(field) is None and record.get(field) is not None:
                    resolved[field] = record.get(field)
        resolved['missing'] = [f for f in DIMENSION_FIELDS if resolved.get(f) is None]
        return resolved

    @staticmethod
    def _normalize_codes(codes: Optional[Iterable[str]]) -> List[str]:
        if not codes:
            return []
        if isinstance(codes, str):
            codes = [item.strip() for item in codes.split(',') if item.strip()]
        items: List[str] = []
        for code in codes:
            text = str(code or '').strip()
            if text and text not in items:
                items.append(text)
        if len(items) > MAX_CODES:
            raise RuleSimulateError(f'codes 数量超限（{len(items)} > {MAX_CODES}）')
        return items


def _line_type_matches(row: Dict[str, Any], item_group_id: Any) -> bool:
    expected = row.get('item_group_id')
    if expected is None:
        return True
    if item_group_id is None:
        return False
    return str(expected) == str(item_group_id)


def _final_of_control_parameter(results: List[Dict[str, Any]]) -> Any:
    simplified = {
        r['code']: {
            'value': r.get('value'),
            'from': r.get('from'),
            'fallback': r.get('fallback'),
            'value_id': r.get('value_id'),
        }
        for r in results
    }
    if len(results) == 1:
        item = dict(simplified[results[0]['code']])
        item['code'] = results[0]['code']
        return item
    return {'codes': simplified}


def _diff(baseline: Dict[str, Any], draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    """对照差异：仅返回取值发生变化的项。"""
    changes: List[Dict[str, Any]] = []
    base_results = {r.get('code'): r for r in baseline.get('results') or []}
    draft_results = {r.get('code'): r for r in draft.get('results') or []}
    for code in sorted(set(base_results) | set(draft_results)):
        before = (base_results.get(code) or {}).get('value')
        after = (draft_results.get(code) or {}).get('value')
        if before != after:
            changes.append({'code': code, 'baseline': before, 'draft': after})
    return changes


_trace_counter = 0


def _trace_id() -> str:
    """试算无副作用，trace_id 仅用于前端串联一次请求的展示。"""
    global _trace_counter
    _trace_counter += 1
    return 'sim-{0}-{1}'.format(int(time.time() * 1000), _trace_counter)


_simulator: Optional[RuleSimulateService] = None


def get_rule_simulate_service() -> RuleSimulateService:
    global _simulator
    if _simulator is None:
        _simulator = RuleSimulateService()
    return _simulator