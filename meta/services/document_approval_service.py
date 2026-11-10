# -*- coding: utf-8 -*-
"""通用单据审批规则解析（M3）

依据 `docs/specs/spec-purchase-order-object-model-2026-11-01.md` §6.2.2（R1-R9）：
  R1  只有 scope_bo = 当前对象的策略参与求值；
  R2  同一策略内多条件 AND（M3 不做 OR 分组）；
  R3  多策略命中取 priority 最大，同优先级取 effective_from 最新；
  R4  无命中策略 = 免审批（approval_status='not_required'）；
  R5  min_amount / max_amount 挂在步骤上（按金额分段给不同审批人）；
  R6  resolve(object_type, record_id) → {required, policy_code, steps, snapshot}；
  R9  提交时把命中策略与步骤快照进任务，策略变更不回溯在途单据。

口径：
  · `approval_enabled` 控制参数（v178 种子，默认 true）是组织级紧急旁路，
    解析前先判，false 直接免审批；
  · 条件 field_id 引用对象字段 id，运行时从记录行取值；
  · 条件值载体：value_number（数值）/ value_text（文本或逗号分隔）/ value_json（数组）；
  · 未识别的 operator 视为该条件不命中（并打日志），不静默放宽整条策略。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.approval_meta_loader import get_approval_meta
from meta.core.rule_decisions import ApprovalRequirement
from meta.core.rule_hit_policy import (
    DEFAULT_HIT_POLICY, order_by_sql, select, sort_key)
from meta.core.rule_metrics import DEFAULT_METRIC_REGISTRY, MetricSession
from meta.core.rule_predicate import evaluate_conditions

logger = logging.getLogger(__name__)

APPROVAL_ENABLED_PARAM = 'approval_enabled'


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _num(value: Any) -> Optional[float]:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> Optional[datetime]:
    if _blank(value):
        return None
    text = str(value).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


class DocumentApprovalResolver:
    """按被审批对象的字段求值审批策略，输出审批链与快照。"""

    def __init__(self, data_source, metric_registry=None):
        self._ds = data_source
        self._metrics = metric_registry or DEFAULT_METRIC_REGISTRY

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def resolve_requirement(self, object_type: str, record_id: Any,
                            trigger_action: str = 'submit') -> ApprovalRequirement:
        """M4/FR-004：typed 审批需求；dict 形态走 `resolve()`。"""
        return ApprovalRequirement.from_resolve(
            self.resolve(object_type, record_id, trigger_action))

    def resolve(self, object_type: str, record_id: Any,
                trigger_action: str = 'submit') -> Dict[str, Any]:
        # 审批对象注册唯一真源 = BO YAML approval:（M2 FR-005）
        approval_meta = get_approval_meta(object_type)
        table = approval_meta['table']
        empty = {
            'required': False, 'policy_id': None, 'policy_code': None,
            'steps': [], 'amount': 0.0, 'snapshot': None,
        }
        if not table or _blank(record_id):
            return dict(empty, reason='invalid_object')

        record = self._load_record(table, record_id)
        if not record:
            logger.warning('[approval] %s id=%s 不存在，按免审批处理',
                           object_type, record_id)
            return dict(empty, reason='record_not_found')

        amount = self._amount_of(record, approval_meta['amount_fields'])
        empty['amount'] = amount

        if self._approval_disabled(record):
            return dict(empty, reason='disabled')

        # M3/FR-003：同一单据一张单一次会话，度量只算一次，多策略引用结果一致
        metrics = MetricSession(object_type, record_id, record, self._metrics)
        policies = self._matched_policies(object_type, record, trigger_action, metrics)
        if not policies:
            return dict(empty, reason='no_policy')

        policy_id, policy, matched_conditions = select(
            policies, DEFAULT_HIT_POLICY)[0]
        steps = self._load_steps(policy_id, amount)
        eval_record = metrics.enrich(
            record, [c.get('field_id') for c in matched_conditions])
        snapshot = {
            'object_type': object_type,
            'trigger_action': trigger_action,
            'policy_id': policy_id,
            'policy_code': policy.get('code'),
            'policy_name': policy.get('name'),
            'priority': policy.get('priority'),
            # FR-006：命中策略显式化（审批策略集默认 first）
            'hit_policy': DEFAULT_HIT_POLICY,
            'amount': amount,
            'steps': steps,
            'conditions': matched_conditions,
            # FR-002：命中策略的逐条解释（field / op / expected / actual / passed）
            'conditions_explain': evaluate_conditions(
                eval_record, matched_conditions).explain,
            # FR-003：本次求值用到的派生度量（derived_cache=True，非事实源）
            'metrics': metrics.snapshot(),
            'resolved_at': datetime.now().isoformat(timespec='seconds'),
        }
        return {
            'required': True,
            'policy_id': policy_id,
            'policy_code': policy.get('code'),
            'steps': steps,
            'amount': amount,
            'snapshot': snapshot,
            'reason': 'matched',
        }

    # ------------------------------------------------------------------
    # 记录 / 开关
    # ------------------------------------------------------------------
    def _load_record(self, table: str, record_id: Any) -> Optional[Dict[str, Any]]:
        rows = self._ds.query(
            'SELECT * FROM {0} WHERE id = ?'.format(table), [record_id])
        if not rows:
            return None
        record = dict(rows[0])
        # D6：审批条件可直接引用单据类别（standard / return / red）
        type_id = record.get('document_type_id')
        if not _blank(type_id):
            try:
                type_rows = self._ds.query(
                    'SELECT document_category FROM type_definitions WHERE id = ?',
                    [type_id])
            except Exception:  # noqa: BLE001 - 极简测试替身无类型表
                type_rows = []
            if type_rows:
                record['document_category'] = type_rows[0].get('document_category')
        return record

    @staticmethod
    def _amount_of(record: Dict[str, Any],
                   amount_fields: Tuple[str, ...] = ()) -> float:
        for field in (amount_fields or ()):
            value = _num(record.get(field))
            if value is not None:
                return value
        return 0.0

    def _approval_disabled(self, record: Dict[str, Any]) -> bool:
        from meta.services.control_parameter_service import ControlParameterResolver

        dims = {}
        if not _blank(record.get('org_id')):
            dims['org_id'] = record.get('org_id')
        if not _blank(record.get('document_type_id')):
            dims['document_type_id'] = record.get('document_type_id')
        enabled = ControlParameterResolver(self._ds).resolve(
            APPROVAL_ENABLED_PARAM, dims)
        return enabled is False

    # ------------------------------------------------------------------
    # 策略 / 条件（R1-R3）
    # ------------------------------------------------------------------
    def _matched_policies(self, object_type: str, record: Dict[str, Any],
                          trigger_action: str,
                          metrics: Optional[MetricSession] = None
                          ) -> List[Tuple[int, Dict[str, Any], List[Dict[str, Any]]]]:
        rows = self._ds.query(
            'SELECT * FROM approval_policies '
            "WHERE scope_bo = ? AND trigger_action = ? AND status = 'active' "
            'ORDER BY ' + order_by_sql(),
            [object_type, trigger_action])

        now = datetime.now()
        hits: List[Tuple[int, Dict[str, Any], List[Dict[str, Any]]]] = []
        for policy in rows:
            if not self._within_effective(policy, now):
                continue
            conditions = self._load_conditions(policy.get('id'))
            eval_record = record
            if metrics is not None:
                # 条件 field_id 可以直接是注册表中的度量 code（FR-003）
                eval_record = metrics.enrich(
                    record, [c.get('field_id') for c in conditions])
            if not self._conditions_hold(eval_record, conditions):
                continue
            hits.append((policy.get('id'), policy, conditions))

        if not hits:
            return []
        # FR-006：排序口径唯一真源 rule_hit_policy.ORDER_BY
        # （priority DESC, effective_from DESC, id DESC），与 SQL 侧一致。
        hits.sort(key=lambda item: sort_key(item[1]), reverse=True)
        return hits

    @staticmethod
    def _within_effective(policy: Dict[str, Any], now: datetime) -> bool:
        start = _parse_dt(policy.get('effective_from'))
        end = _parse_dt(policy.get('effective_to'))
        if start and now < start:
            return False
        if end and now > end:
            return False
        return True

    def _load_conditions(self, policy_id: Any) -> List[Dict[str, Any]]:
        return self._ds.query(
            'SELECT * FROM approval_policy_conditions WHERE policy_id = ? '
            'ORDER BY group_no ASC, id ASC', [policy_id])

    def _conditions_hold(self, record: Dict[str, Any],
                         conditions: List[Dict[str, Any]]) -> bool:
        # R2：M3 只做单层 AND；求值统一走 rule_predicate（FR-001/FR-002）
        return evaluate_conditions(record, conditions).passed

    # 条件求值已统一到 meta.core.rule_predicate（FR-001/FR-002），此处不再重复实现。

    # ------------------------------------------------------------------
    # 步骤（R5）
    # ------------------------------------------------------------------
    def _load_steps(self, policy_id: Any, amount: float) -> List[Dict[str, Any]]:
        rows = self._ds.query(
            'SELECT step_no, approver_type, approver_ref, min_amount, max_amount, '
            '       approve_mode, sla_hours FROM approval_policy_steps '
            'WHERE policy_id = ? ORDER BY step_no ASC', [policy_id])
        steps = [{
            'step_no': int(_num(row.get('step_no')) or 0),
            'approver_type': row.get('approver_type'),
            'approver_ref': row.get('approver_ref'),
            'approve_mode': row.get('approve_mode') or 'any',
            'sla_hours': row.get('sla_hours'),
            'min_amount': _num(row.get('min_amount')),
            'max_amount': _num(row.get('max_amount')),
        } for row in rows]

        if not steps:
            return []
        matched = [s for s in steps if self._step_in_band(s, amount)]
        if matched:
            return matched
        # 金额分段未覆盖时回退整条链，避免策略命中却无审批人
        logger.warning('[approval] policy=%s 金额 %s 未落在任何步骤分段，回退全部步骤',
                       policy_id, amount)
        return steps

    @staticmethod
    def _step_in_band(step: Dict[str, Any], amount: float) -> bool:
        low, high = step.get('min_amount'), step.get('max_amount')
        if low is not None and amount < low:
            return False
        if high is not None and amount > high:
            return False
        return True
