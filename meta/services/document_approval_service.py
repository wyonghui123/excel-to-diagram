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

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

APPROVAL_ENABLED_PARAM = 'approval_enabled'

#: 对象 → 表名（M3 只有 PO 接入；requisition / service_request 保持 M1 旧口径）
APPROVAL_TABLES = {
    'purchase_order': 'purchase_orders',
    'requisition': 'requisitions',
    'service_request': 'service_requests',
}

#: 金额取值优先级（步骤金额分段的比较基准）
_AMOUNT_FIELDS = ('gross_amount', 'net_amount', 'total_amount', 'amount')


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _num(value: Any) -> Optional[float]:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


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

    def __init__(self, data_source):
        self._ds = data_source

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def resolve(self, object_type: str, record_id: Any,
                trigger_action: str = 'submit') -> Dict[str, Any]:
        table = APPROVAL_TABLES.get(object_type)
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

        amount = self._amount_of(record)
        empty['amount'] = amount

        if self._approval_disabled(record):
            return dict(empty, reason='disabled')

        policies = self._matched_policies(object_type, record, trigger_action)
        if not policies:
            return dict(empty, reason='no_policy')

        policy_id, policy, matched_conditions = policies[0]
        steps = self._load_steps(policy_id, amount)
        snapshot = {
            'object_type': object_type,
            'trigger_action': trigger_action,
            'policy_id': policy_id,
            'policy_code': policy.get('code'),
            'policy_name': policy.get('name'),
            'priority': policy.get('priority'),
            'amount': amount,
            'steps': steps,
            'conditions': matched_conditions,
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
        return rows[0] if rows else None

    @staticmethod
    def _amount_of(record: Dict[str, Any]) -> float:
        for field in _AMOUNT_FIELDS:
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
                          trigger_action: str) -> List[Tuple[int, Dict[str, Any], List[Dict[str, Any]]]]:
        rows = self._ds.query(
            'SELECT * FROM approval_policies '
            "WHERE scope_bo = ? AND trigger_action = ? AND status = 'active' "
            'ORDER BY priority DESC, effective_from DESC, id DESC',
            [object_type, trigger_action])

        now = datetime.now()
        hits: List[Tuple[int, Dict[str, Any], List[Dict[str, Any]]]] = []
        for policy in rows:
            if not self._within_effective(policy, now):
                continue
            conditions = self._load_conditions(policy.get('id'))
            if not self._conditions_hold(record, conditions):
                continue
            hits.append((policy.get('id'), policy, conditions))

        if not hits:
            return []
        # R3：priority 最大；同优先级取 effective_from 最新（无值时视为最早）
        hits.sort(key=lambda item: (
            int(_num(item[1].get('priority')) or 0),
            _parse_dt(item[1].get('effective_from')) or datetime.min,
        ), reverse=True)
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
        # R2：M3 只做单层 AND，group_no / logic 的 OR 语义留后续波次
        for condition in conditions:
            if not self._condition_matches(record, condition):
                return False
        return True

    def _condition_matches(self, record: Dict[str, Any],
                           condition: Dict[str, Any]) -> bool:
        field_id = _text(condition.get('field_id'))
        if not field_id:
            return False
        actual = record.get(field_id)
        operator = _text(condition.get('operator')) or '='
        if operator == '=':
            return self._eq(actual, condition)
        if operator == 'in':
            return self._in(actual, condition)
        if operator == 'between':
            return self._between(actual, condition)
        if operator == '>=':
            return self._compare(actual, condition.get('value_number')
                                 if condition.get('value_number') is not None
                                 else condition.get('value_text'), '>=')
        if operator == '<=':
            return self._compare(actual, condition.get('value_number')
                                 if condition.get('value_number') is not None
                                 else condition.get('value_text'), '<=')
        if operator == 'is_null':
            return _blank(actual) or _text(actual).lower() == 'null'
        logger.warning('[approval] 未知条件操作符 %s（policy=%s field=%s），按不命中处理',
                       operator, condition.get('policy_id'), field_id)
        return False

    @staticmethod
    def _target(condition: Dict[str, Any]) -> Any:
        if condition.get('value_number') is not None:
            return condition.get('value_number')
        if condition.get('value_json') not in (None, ''):
            try:
                return json.loads(condition.get('value_json'))
            except (TypeError, ValueError):
                return condition.get('value_json')
        return condition.get('value_text')

    def _eq(self, actual: Any, condition: Dict[str, Any]) -> bool:
        target = self._target(condition)
        left_num, right_num = _num(actual), _num(target)
        if left_num is not None and right_num is not None:
            return abs(left_num - right_num) < 1e-9
        left_text, right_text = _text(actual).lower(), _text(target).lower()
        if left_text in ('true', 'false') and right_text in ('1', '0'):
            return left_text == ('true' if right_text == '1' else 'false')
        return left_text == right_text

    def _in(self, actual: Any, condition: Dict[str, Any]) -> bool:
        values = self._target(condition)
        if not isinstance(values, (list, tuple)):
            values = [v for v in _text(values).split(',') if v.strip()]
        actual_num = _num(actual)
        for candidate in values:
            if actual_num is not None and _num(candidate) is not None:
                if abs(actual_num - float(candidate)) < 1e-9:
                    return True
            elif _text(candidate).lower() == _text(actual).lower():
                return True
        return False

    def _between(self, actual: Any, condition: Dict[str, Any]) -> bool:
        value = self._target(condition)
        if isinstance(value, (list, tuple)):
            bounds = list(value)
        else:
            bounds = [v for v in _text(value).split(',') if v.strip()]
        if len(bounds) < 2:
            return False
        low, high = _num(bounds[0]), _num(bounds[1])
        actual_num = _num(actual)
        if None in (low, high) or actual_num is None:
            return False
        return low <= actual_num <= high

    @staticmethod
    def _compare(actual: Any, target: Any, operator: str) -> bool:
        left_num, right_num = _num(actual), _num(target)
        if left_num is not None and right_num is not None:
            return left_num >= right_num if operator == '>=' else left_num <= right_num
        left, right = _text(actual), _text(target)
        if not left or not right:
            return False
        return left >= right if operator == '>=' else left <= right

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
