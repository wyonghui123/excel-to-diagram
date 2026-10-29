# -*- coding: utf-8 -*-
"""变更申请服务（M3 / FR-007 / FR-008）

职责边界（spec D5）：
  · 本模块**不**做生效编排（`apply` 留在 `revision_service`，走 ActionExecutor 漏斗）；
  · 只负责两件事：
      1. `after_status_change(...)` —— `draft → submitted` 的提交钩子：
         校验变更明细 → 建审批任务（与状态写入同事务，失败整体回滚）；
      2. `transition(...)` —— 按 YAML 声明的合法边推进状态。

审批复用 `tasks` 模型（type=approval / status=waiting_approval），不新建审批引擎（D1/D2）。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

CR_TABLE = 'change_requests'
CRL_TABLE = 'change_request_lines'
TASKS_TABLE = 'tasks'

# 与 meta/schemas/change_request.yaml 的 6 条 state_transition 同源
_TRANSITIONS = {
    'submitted': ('draft',),
    'approved': ('submitted',),
    'rejected': ('submitted',),
    'applied': ('approved',),
    'failed': ('approved',),
    # G3：审批任务取消 / 超时 / 死信时由系统内部推进，消灭 submitted 悬挂态
    'cancelled': ('submitted',),
}

# G3：只有这些任务终态的审批任务会回写变更申请（正常通过/驳回时 CR 已先离开 submitted）
_TASK_TERMINAL_FOR_CR = ('cancelled', 'skipped', 'dead', 'failed')

_TABLES_READY = False


class ChangeRequestError(Exception):
    """带业务错误码的变更申请异常（API 层据此映射 HTTP 状态码）"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _actor_ref(actor: Any) -> Optional[str]:
    if not actor:
        return None
    if isinstance(actor, dict):
        return (actor.get('username') or actor.get('display_name')
                or actor.get('user_id') or actor.get('id'))
    return str(actor)


def _ensure_tables(ds) -> None:
    """幂等建任务表 + 登记三张非 BO 表名（沿用 M2 解决 `Invalid table name` 的机制）。"""
    global _TABLES_READY
    from meta.core.table_name_validator import register_table_name

    register_table_name(TASKS_TABLE)
    register_table_name(CR_TABLE)
    register_table_name(CRL_TABLE)
    if _TABLES_READY:
        return
    from meta.core.task_schema import ensure_task_tables

    ensure_task_tables(ds)
    _TABLES_READY = True


def _is_draft_to_submitted(before: Dict[str, Any], after: Dict[str, Any]) -> bool:
    return (before or {}).get('status') == 'draft' \
        and (after or {}).get('status') == 'submitted'


def _editable_db_columns(meta_object) -> set:
    """目标对象 revision_policy.fields 中 editable:true 且非派生的字段（db 列名集合）"""
    from meta.core.yaml_loader import _REVISION_DERIVED_FIELDS

    policy = getattr(meta_object, 'revision_policy', None)
    if policy is None or not policy.enabled:
        return set()
    editable_ids = {
        f.field for f in policy.fields
        if f.field and f.editable and f.field not in _REVISION_DERIVED_FIELDS
    }
    columns = set()
    for field in meta_object.get_persistent_fields():
        if field.id in editable_ids:
            columns.add(field.db_column or field.id)
    return columns


def after_status_change(ds, before: Dict[str, Any], after: Dict[str, Any],
                        ctx: Optional[Dict[str, Any]] = None) -> None:
    """`draft → submitted` 提交钩子：校验变更明细 + 创建审批任务。

    任一校验失败即 raise ChangeRequestError —— 调用方（`_do_update`）处于业务事务中，
    异常会让「状态推进 + 审批任务」整体回滚，不会出现「已提交但无审批任务」。
    """
    ctx = ctx or {}
    if not _is_draft_to_submitted(before, after):
        return

    from meta.core.models import registry

    cr_id = (after or {}).get('id', (before or {}).get('id'))
    target_type = (after or {}).get('target_object_type', '')
    target_id = (after or {}).get('target_object_id', '')
    target_revision_no = (after or {}).get('target_revision_no')

    _ensure_tables(ds)

    # ① 至少 1 行变更明细
    lines = ds.find(CRL_TABLE, {'change_request_id': cr_id}) or []
    if not lines:
        raise ChangeRequestError(
            'INVALID_CHANGE_REQUEST',
            '变更申请至少需要一行变更明细',
        )

    # ② 目标对象存在，且行字段命中 revision_policy 的 editable 且非派生白名单（FR-011）
    meta_object = registry.get(target_type) if target_type else None
    if meta_object is None:
        raise ChangeRequestError(
            'INVALID_TARGET_OBJECT',
            '目标对象不存在: %s' % (target_type or '(空)'),
        )
    editable_columns = _editable_db_columns(meta_object)
    # [M4] 行级申请：字段白名单按父 policy.lines 的行类型分档；line_key 必须属于该父单据
    lines_cfg = getattr(getattr(meta_object, 'revision_policy', None), 'lines', None)
    line_object = registry.get(lines_cfg.child_object) if lines_cfg is not None else None
    for line in lines:
        field_name = (line.get('field_name') or '').strip()
        line_key = line.get('line_key')
        if line_key in (None, ''):
            if not field_name or field_name not in editable_columns:
                raise ChangeRequestError(
                    'INVALID_CHANGE_FIELD',
                    '字段 %s 不在目标对象 %s 的可变更白名单（editable 且非派生字段）' % (
                        field_name or '(空)', meta_object.id),
                )
            continue

        if line_object is None:
            raise ChangeRequestError(
                'INVALID_CHANGE_FIELD',
                '目标对象 %s 未声明行级策略，不能提交行变更' % meta_object.id,
            )
        line_row = None
        try:
            line_row = ds.find_by_id(line_object.table_name, line_key)
        except Exception:  # noqa: BLE001 - 表不存在按行不存在处理
            line_row = None
        # 父字段在行表是 INTEGER、change_requests.target_object_id 是 TEXT，
        # 直接比较会 1 != '1' 而误拒合法行；统一转 str 比较
        if not line_row or str(line_row.get(lines_cfg.parent_field)) != str(target_id):
            raise ChangeRequestError(
                'INVALID_LINE_KEY',
                '变更行 %s#%s 不存在或不属于目标单据 %s' % (
                    line_object.id, line_key, target_id),
            )
        tier = lines_cfg.policy_for(line_row)
        allowed_columns = {field.id for field in line_object.get_persistent_fields()
                           if field.id in set(tier.editable or ())
                           or field.id in set(tier.via_change_request or ())}
        allowed_columns |= {field.db_column or field.id
                            for field in line_object.get_persistent_fields()
                            if field.id in set(tier.editable or ())
                            or field.id in set(tier.via_change_request or ())}
        if not field_name or field_name not in allowed_columns:
            raise ChangeRequestError(
                'INVALID_CHANGE_FIELD',
                '行字段 %s 不在行对象 %s 的可变更白名单（行类型分档未列出）' % (
                    field_name or '(空)', line_object.id),
            )

    # ③ 目标存在且版本仍是提交时冻结的版本（FR-010 乐观锁预检）
    target_row = ds.find_by_id(meta_object.table_name, target_id)
    if not target_row:
        raise ChangeRequestError(
            'TARGET_NOT_FOUND',
            '目标单据不存在: %s#%s' % (meta_object.id, target_id),
        )
    if target_row.get('revision_no') != target_revision_no:
        raise ChangeRequestError(
            'TARGET_REVISION_STALE',
            '目标已被修改（当前版本 %s，申请冻结版本 %s），请重新提交' % (
                target_row.get('revision_no'), target_revision_no),
        )

    # ③' 同目标仅一条在途申请（G2）：submitted / approved 都算在途
    #     idx_cr_target(target_object_type, target_object_id, status) 已覆盖本查询
    pending_rows = ds.execute(
        "SELECT id FROM change_requests "
        "WHERE target_object_type = ? AND target_object_id = ? "
        "AND status IN ('submitted', 'approved') AND id <> ?",
        (target_type, str(target_id), cr_id),
    ).fetchall()
    if pending_rows:
        raise ChangeRequestError(
            'TARGET_HAS_PENDING_REQUEST',
            '目标单据已有在途变更申请 #%s，请先完成或取消后再提交' % pending_rows[0][0],
            409,
        )

    # ④ 创建审批任务（平台无创建 API，直插 tasks）
    #    code 留 None：tasks.code 的唯一索引 + ^T-[0-9]+$ 人读编号约束不适用于审批类任务，
    #    与 workflow_engine 建任务时一致（NULL 不参与唯一冲突）。
    submitted_by = (after or {}).get('submitted_by') \
        or _actor_ref(ctx.get('actor') or ctx.get('user'))
    row = {
        'id': uuid.uuid4().hex,
        'code': None,
        'title': '变更申请审批 #%s' % cr_id,
        'type': 'approval',
        'status': 'waiting_approval',
        'priority': 'P1',
        'app_id': '',
        'executor_type': 'human',
        'assign_policy': 'claim',
        'executor_candidates': json.dumps([], ensure_ascii=False),
        'executor_config': json.dumps({
            'decision_actions': {
                'approve': 'change_request.approve',
                'reject': 'change_request.reject',
            }
        }, ensure_ascii=False),
        'inputs': json.dumps({
            'change_request_id': cr_id,
            'target_object_type': target_type,
            'target_object_id': target_id,
            'target_revision_no': target_revision_no,
        }, ensure_ascii=False),
        'doc_ref': str(cr_id),
        'created_by': submitted_by,
        'created_at': _now_iso(),
        'attempt': 1,
    }
    ds.insert(TASKS_TABLE, row)


def transition(ds, cr_row: Dict[str, Any], to_status: str,
               actor: Any = '', extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """按 YAML 声明的合法边推进变更申请状态，返回本次写入的列。

    非法边（from 不是当前状态 / to 未声明）→ ChangeRequestError('INVALID_TRANSITION', 409)。
    """
    if not cr_row or cr_row.get('id') is None:
        raise ChangeRequestError('CHANGE_REQUEST_NOT_FOUND', '变更申请不存在')
    current = cr_row.get('status')
    allowed_from = _TRANSITIONS.get(to_status)
    if not allowed_from or current not in allowed_from:
        raise ChangeRequestError(
            'INVALID_TRANSITION',
            '不允许的状态迁移: %s → %s' % (current, to_status),
            409,
        )

    updates: Dict[str, Any] = {'status': to_status}
    if to_status == 'submitted':
        updates['submitted_by'] = _actor_ref(actor) or cr_row.get('submitted_by')
        updates['submitted_at'] = _now_iso()
    elif to_status == 'approved':
        updates['approved_by'] = _actor_ref(actor)
        updates['approved_at'] = _now_iso()
    elif to_status == 'applied':
        updates['applied_at'] = _now_iso()
    elif to_status == 'cancelled':
        updates['fail_reason'] = (extra or {}).get('fail_reason') \
            or '审批任务终止，变更申请自动取消'
    if extra:
        updates.update(extra)

    _ensure_tables(ds)
    ds.update(CR_TABLE, cr_row['id'], updates)
    return updates


def on_approval_task_terminal(ds, task_id: str, to_status: str,
                              actor: Any = '', reason: str = '') -> Optional[Dict[str, Any]]:
    """审批类任务终止 → 回写仍停在 submitted 的变更申请为 cancelled（幂等 no-op）。

    由 A3 事件账统一入口 `task_event_schema.record_transition` 挂钩调用：
      - 决策链是「先 BO 生效（CR→approved/rejected），后任务归位」，正常通过/驳回时
        CR 已离开 submitted，本函数返回 None；
      - 只有「任务终止但 BO 未生效」（取消 / 超时 / 死信 / 执行失败）才会真正写 cancelled，
        消灭 `change_requests.status = submitted` 的悬挂态。

    纪律：本函数不建表、不吞业务异常以外的错误；调用方负责不阻断任务迁移。
    """
    if to_status not in _TASK_TERMINAL_FOR_CR:
        return None

    try:
        rows = ds.execute(
            "SELECT type, doc_ref, inputs FROM tasks WHERE id = ?",
            (str(task_id),),
        ).fetchall()
    except Exception:  # noqa: BLE001 - 库未启用 tasks 表 → 无审批任务可回写
        return None
    if not rows:
        return None

    task_type, doc_ref, inputs_raw = rows[0]
    if task_type not in ('approval', 'review'):
        return None

    cr_id = doc_ref
    if cr_id in (None, ''):
        try:
            inputs = json.loads(inputs_raw) if isinstance(inputs_raw, str) else (inputs_raw or {})
            cr_id = (inputs or {}).get('change_request_id')
        except (TypeError, ValueError):
            cr_id = None
    if cr_id in (None, ''):
        return None

    # change_requests.id 是 INTEGER，doc_ref / inputs 存的是字符串 → 数字串转回 int，
    # 否则 SQLite 的 1 != '1' 会让回写静默失效。
    cr_key = int(cr_id) if str(cr_id).isdigit() else cr_id
    try:
        cr_row = ds.find_by_id(CR_TABLE, cr_key)
    except Exception:  # noqa: BLE001 - 库未启用 change_requests 表 → no-op
        return None
    if not cr_row or cr_row.get('status') != 'submitted':
        return None

    fail_reason = (reason or '审批任务 %s，变更申请自动取消' % to_status)[:200]
    return transition(ds, cr_row, 'cancelled', actor, {'fail_reason': fail_reason})
