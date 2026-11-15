# -*- coding: utf-8 -*-
"""审批策略配置服务（M3 / spec-approval-workflow §6）

真源 = ``approval_policies`` 三表（v178 建表 / v276 增 version）。
本模块只做配置期读写（校验 + 版本递增 + 子表整体替换），**不实现命中判定**：
试算一律委托 ``DocumentApprovalResolver``（D-AP-08，薄适配，零新逻辑）。

版本口径（D-AP-07）：
  · 新建 version = 1；
  · 每次保存 version + 1，并随任务快照冻结；策略变更不回溯在途任务。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from meta.core.approval_meta_loader import get_approval_meta
from meta.core.models import registry
from meta.core.rule_predicate import OPERATOR_ALIASES, normalize_operator

logger = logging.getLogger(__name__)

POLICY_TABLE = 'approval_policies'
CONDITION_TABLE = 'approval_policy_conditions'
STEP_TABLE = 'approval_policy_steps'

VALID_STATUSES: Tuple[str, ...] = ('active', 'inactive', 'draft')
VALID_APPROVE_MODES: Tuple[str, ...] = ('any', 'all')
#: 与 rule_predicate.OPERATOR_ALIASES 同源，避免第二份运算符清单
OPERATORS: Tuple[str, ...] = tuple(sorted(set(OPERATOR_ALIASES.values())))


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def _int(value: Any, default: Optional[int] = None, label: str = '') -> Optional[int]:
    if _blank(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError('%s 必须是整数' % (label or '取值'))


def _float(value: Any, label: str = '') -> Optional[float]:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError('%s 必须是数字' % (label or '取值'))


def _dt(value: Any, label: str = '') -> Optional[str]:
    if _blank(value):
        return None
    text = str(value).strip().replace('T', ' ')
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    raise ValueError('%s 不是合法日期（YYYY-MM-DD[ HH:MM:SS]）' % (label or '时间'))


def _require_approvable(scope_bo: str) -> Dict[str, Any]:
    """策略只能挂在「已声明 approval.table」的对象上（D-AP-01 唯一接入判据）。"""
    meta = get_approval_meta(scope_bo)
    if not meta.get('table'):
        raise ValueError('对象 %s 未声明 approval.table，不能配置审批策略' % scope_bo)
    return meta


# ----------------------------------------------------------------------
# 条件 / 步骤归一
# ----------------------------------------------------------------------
def _condition_row(raw: Any, index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('条件 #%d 必须是对象' % (index + 1))
    field_id = str(raw.get('field_id') or '').strip()
    if not field_id:
        raise ValueError('条件 #%d 缺少 field_id' % (index + 1))

    operator = normalize_operator(raw.get('operator') or '=')
    if operator not in OPERATORS:
        raise ValueError('条件 #%d 运算符 %s 不受支持' % (index + 1, raw.get('operator')))

    logic = str(raw.get('logic') or 'and').strip().lower()
    if logic != 'and':
        # R2：M3 只做单层 AND，OR / NOT 不在本期范围
        raise ValueError('条件 #%d 仅支持 and（R2 单层 AND）' % (index + 1))

    value_text = raw.get('value_text')
    value_number = raw.get('value_number')
    value_json = raw.get('value_json')
    if 'value' in raw and all(_blank(v) for v in
                              (value_text, value_number, value_json)):
        source = raw.get('value')
        if isinstance(source, bool):
            value_text = 'true' if source else 'false'
        elif isinstance(source, (int, float)):
            value_number = float(source)
        elif isinstance(source, (list, dict)):
            value_json = json.dumps(source, ensure_ascii=False)
        elif source is not None:
            value_text = str(source)

    if isinstance(value_json, (list, dict)):
        value_json = json.dumps(value_json, ensure_ascii=False)
    if isinstance(value_json, str) and value_json.strip():
        try:
            json.loads(value_json)
        except ValueError:
            raise ValueError('条件 #%d value_json 不是合法 JSON' % (index + 1))
    else:
        value_json = None

    return {
        'group_no': _int(raw.get('group_no'), 1, '条件 group_no'),
        'logic': logic,
        'field_id': field_id,
        'operator': operator,
        'value_text': None if _blank(value_text) else str(value_text),
        'value_number': _float(value_number, '条件 value_number'),
        'value_json': value_json,
    }


def _step_row(raw: Any, index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError('步骤 #%d 必须是对象' % (index + 1))
    step_no = _int(raw.get('step_no'), index + 1, '步骤 step_no')
    approver_type = str(raw.get('approver_type') or 'role').strip()
    approver_ref = str(raw.get('approver_ref') or '').strip()
    if not approver_ref:
        raise ValueError('步骤 #%d 缺少 approver_ref' % (index + 1))
    approve_mode = str(raw.get('approve_mode') or 'any').strip().lower()
    if approve_mode not in VALID_APPROVE_MODES:
        raise ValueError('步骤 #%d approve_mode 必须是 %s'
                         % (index + 1, '/'.join(VALID_APPROVE_MODES)))
    return {
        'step_no': step_no,
        'approver_type': approver_type,
        'approver_ref': approver_ref,
        'approve_mode': approve_mode,
        'sla_hours': _int(raw.get('sla_hours'), None, '步骤 sla_hours'),
        'min_amount': _float(raw.get('min_amount'), '步骤 min_amount'),
        'max_amount': _float(raw.get('max_amount'), '步骤 max_amount'),
    }


# ----------------------------------------------------------------------
# 读写
# ----------------------------------------------------------------------
def _condition_summary(conditions: List[Dict[str, Any]]) -> str:
    parts = []
    for row in conditions[:3]:
        value = row.get('value_number')
        if value is None:
            value = row.get('value_text')
        if value is None:
            value = row.get('value_json')
        parts.append('%s %s %s' % (row.get('field_id'), row.get('operator'),
                                   '' if value is None else value))
    if len(conditions) > 3:
        parts.append('…')
    return ' AND '.join(parts)


def list_policies(ds, *, scope_bo: Optional[str] = None,
                  status: Optional[str] = None, keyword: Optional[str] = None,
                  limit: int = 200, offset: int = 0) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if not _blank(scope_bo):
        where.append('scope_bo = ?')
        params.append(scope_bo)
    if not _blank(status):
        where.append('status = ?')
        params.append(status)
    if not _blank(keyword):
        where.append('(code LIKE ? OR name LIKE ?)')
        like = '%%%s%%' % keyword
        params.extend([like, like])
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''

    total_rows = ds.query(
        'SELECT COUNT(*) AS n FROM %s%s' % (POLICY_TABLE, clause), params)
    total = int((total_rows[0].get('n') if total_rows else 0) or 0)

    rows = ds.query(
        'SELECT id, code, name, scope_bo, trigger_action, priority, status, '
        '       version, effective_from, effective_to, description, updated_at '
        'FROM %s%s ORDER BY priority DESC, id DESC LIMIT ? OFFSET ?'
        % (POLICY_TABLE, clause),
        params + [int(limit), int(offset)])

    ids = [row.get('id') for row in rows]
    conditions: Dict[Any, List[Dict[str, Any]]] = {}
    step_counts: Dict[Any, int] = {}
    if ids:
        marks = ','.join(['?'] * len(ids))
        for row in ds.query(
                'SELECT policy_id, group_no, field_id, operator, value_text, '
                '       value_number, value_json FROM %s WHERE policy_id IN (%s) '
                'ORDER BY group_no ASC, id ASC' % (CONDITION_TABLE, marks), ids):
            conditions.setdefault(row.get('policy_id'), []).append(row)
        for row in ds.query(
                'SELECT policy_id, COUNT(*) AS n FROM %s WHERE policy_id IN (%s) '
                'GROUP BY policy_id' % (STEP_TABLE, marks), ids):
            step_counts[row.get('policy_id')] = int(row.get('n') or 0)

    items = []
    for row in rows:
        item = dict(row)
        own = conditions.get(row.get('id'), [])
        item['condition_count'] = len(own)
        item['step_count'] = step_counts.get(row.get('id'), 0)
        item['condition_summary'] = _condition_summary(own)
        items.append(item)
    return {'items': items, 'total': total}


def get_policy(ds, policy_id: int) -> Optional[Dict[str, Any]]:
    rows = ds.query('SELECT * FROM %s WHERE id = ?' % POLICY_TABLE, [policy_id])
    if not rows:
        return None
    policy = dict(rows[0])
    policy['conditions'] = ds.query(
        'SELECT * FROM %s WHERE policy_id = ? ORDER BY group_no ASC, id ASC'
        % CONDITION_TABLE, [policy_id])
    policy['steps'] = ds.query(
        'SELECT * FROM %s WHERE policy_id = ? ORDER BY step_no ASC'
        % STEP_TABLE, [policy_id])
    return policy


def _validate_header(payload: Dict[str, Any], base: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = base or {}

    def pick(key, default=None):
        return payload[key] if key in payload else base.get(key, default)

    code = str(pick('code') or '').strip()
    name = str(pick('name') or '').strip()
    scope_bo = str(pick('scope_bo') or '').strip()
    if not code:
        raise ValueError('code 不能为空')
    if not name:
        raise ValueError('name 不能为空')
    if not scope_bo:
        raise ValueError('scope_bo 不能为空')
    _require_approvable(scope_bo)

    status = str(pick('status') or 'active').strip().lower()
    if status not in VALID_STATUSES:
        raise ValueError('status 必须是 %s' % '/'.join(VALID_STATUSES))

    return {
        'code': code,
        'name': name,
        'scope_bo': scope_bo,
        'trigger_action': str(pick('trigger_action') or 'submit').strip(),
        'priority': _int(pick('priority'), 100, 'priority'),
        'status': status,
        'description': pick('description'),
        'effective_from': _dt(pick('effective_from'), 'effective_from'),
        'effective_to': _dt(pick('effective_to'), 'effective_to'),
    }


def _validate_children(payload: Dict[str, Any],
                       base: Optional[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]],
                                                                  List[Dict[str, Any]]]:
    raw_conditions = payload.get('conditions')
    if raw_conditions is None:
        raw_conditions = (base or {}).get('conditions') or []
    if not isinstance(raw_conditions, list):
        raise ValueError('conditions 必须是数组')
    conditions = [_condition_row(item, idx) for idx, item in enumerate(raw_conditions)]

    raw_steps = payload.get('steps')
    if raw_steps is None:
        raw_steps = (base or {}).get('steps') or []
    if not isinstance(raw_steps, list):
        raise ValueError('steps 必须是数组')
    steps = [_step_row(item, idx) for idx, item in enumerate(raw_steps)]
    step_nos = [row['step_no'] for row in steps]
    if len(set(step_nos)) != len(step_nos):
        raise ValueError('步骤 step_no 不能重复')
    return conditions, steps


def save_policy(ds, payload: Dict[str, Any], *, policy_id: Optional[int] = None,
                actor: str = '') -> Dict[str, Any]:
    """新建或保存策略；返回保存后的完整策略（含子表）。"""
    base = None
    if policy_id is not None:
        base = get_policy(ds, policy_id)
        if base is None:
            raise LookupError('审批策略不存在')

    header = _validate_header(payload, base)
    conditions, steps = _validate_children(payload, base)

    dup = ds.query('SELECT id FROM %s WHERE code = ?%s'
                   % (POLICY_TABLE, ' AND id <> ?' if policy_id is not None else ''),
                   [header['code']] + ([policy_id] if policy_id is not None else []))
    if dup:
        raise ValueError('策略编码 %s 已存在' % header['code'])

    now = _now()
    ds.begin_transaction()
    try:
        if policy_id is None:
            cursor = ds.execute(
                'INSERT INTO %s (code, name, scope_bo, trigger_action, priority, '
                'status, description, effective_from, effective_to, version, '
                'created_by, updated_by, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)' % POLICY_TABLE,
                [header['code'], header['name'], header['scope_bo'],
                 header['trigger_action'], header['priority'], header['status'],
                 header['description'], header['effective_from'],
                 header['effective_to'], actor, actor, now, now])
            policy_id = cursor.lastrowid
        else:
            version = int((base or {}).get('version') or 1) + 1
            ds.execute(
                'UPDATE %s SET code = ?, name = ?, scope_bo = ?, trigger_action = ?, '
                'priority = ?, status = ?, description = ?, effective_from = ?, '
                'effective_to = ?, version = ?, updated_by = ?, updated_at = ? '
                'WHERE id = ?' % POLICY_TABLE,
                [header['code'], header['name'], header['scope_bo'],
                 header['trigger_action'], header['priority'], header['status'],
                 header['description'], header['effective_from'],
                 header['effective_to'], version, actor, now, policy_id])

        # 子表整体替换（保存即全量语义，避免差量合并引入第二套口径）
        ds.execute('DELETE FROM %s WHERE policy_id = ?' % CONDITION_TABLE, [policy_id])
        ds.execute('DELETE FROM %s WHERE policy_id = ?' % STEP_TABLE, [policy_id])
        for row in conditions:
            ds.execute(
                'INSERT INTO %s (policy_id, group_no, logic, field_id, operator, '
                'value_text, value_number, value_json, created_by, updated_by, '
                'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
                % CONDITION_TABLE,
                [policy_id, row['group_no'], row['logic'], row['field_id'],
                 row['operator'], row['value_text'], row['value_number'],
                 row['value_json'], actor, actor, now, now])
        for row in steps:
            ds.execute(
                'INSERT INTO %s (policy_id, step_no, approver_type, approver_ref, '
                'min_amount, max_amount, approve_mode, sla_hours, created_by, '
                'updated_by, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)' % STEP_TABLE,
                [policy_id, row['step_no'], row['approver_type'],
                 row['approver_ref'], row['min_amount'], row['max_amount'],
                 row['approve_mode'], row['sla_hours'], actor, actor, now, now])
        ds.commit()
    except Exception:
        ds.rollback()
        raise

    return get_policy(ds, policy_id)


def preview(ds, object_type: str, record_id: Any,
            trigger_action: str = 'submit') -> Dict[str, Any]:
    """命中试算：薄适配 DocumentApprovalResolver，不做任何判定逻辑。"""
    _require_approvable(object_type)
    from meta.services.document_approval_service import DocumentApprovalResolver

    return DocumentApprovalResolver(ds).resolve(
        object_type, record_id, trigger_action or 'submit')


def options() -> Dict[str, Any]:
    """编辑器下拉项：可审批对象 + 运算符 + 审批人类型 + 状态（元数据派生）。"""
    objects = []
    for object_type in registry.list_types():
        meta = get_approval_meta(object_type)
        if not meta.get('table'):
            continue
        obj = registry.get(object_type)
        fields = []
        for field in (getattr(obj, 'fields', None) or [])[:100]:
            fields.append({'id': getattr(field, 'id', ''),
                           'name': getattr(field, 'name', '')})
        objects.append({
            'object_type': object_type,
            'name': getattr(obj, 'name', object_type) or object_type,
            'table': meta.get('table'),
            'amount_fields': list(meta.get('amount_fields') or ()),
            'fields': fields,
        })
    objects.sort(key=lambda item: item['object_type'])
    return {
        'objects': objects,
        'operators': list(OPERATORS),
        'approver_types': ['role', 'user', 'position', 'org'],
        'statuses': list(VALID_STATUSES),
        'approve_modes': list(VALID_APPROVE_MODES),
    }