# -*- coding: utf-8 -*-
"""通用审批待办创建（M3 / SSOT v0.3 D-AP-02）

依据 `docs/specs/spec-purchase-order-object-model-2026-11-01.md` §6.2.2 R7 / §6.4：
  · 审批统一复用 `tasks(type='approval')`，不新建审批引擎；
  · 提交时按解析结果落一条待办；在途判重（未到终态的任务不回退）；
  · `executor_config.decision_actions` 指向 BO Action，`inputs.policy_snapshot`
    记录提交时命中的策略与步骤（R9：策略变更不回溯在途单据）。

建任务元数据唯一真源 = BO YAML ``approval:``（经 `approval_meta_loader` 读取），
本模块不再持有对象 → 表名 / 标题 / 域 / 决策动作的第二份副本。
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from meta.core import task_assignee_resolver as resolver
from meta.core.approval_meta_loader import get_approval_meta
from meta.services.task_stage import resolve_stage, settle_auto

logger = logging.getLogger(__name__)

PURCHASE_ORDER_OBJECT = 'purchase_order'

#: 审批任务的终止态（这些状态不再算在途，可重新建任务）
TASK_TERMINAL_STATUSES = ('done', 'failed', 'cancelled', 'skipped', 'dead')


class ApprovalTaskService:
    """按对象建审批待办（幂等：已有在途任务则不重复建）。"""

    def __init__(self, data_source):
        self._ds = data_source

    def create_task(self, object_type: str, record_id: Any, *,
                    policy_snapshot: Optional[Dict[str, Any]] = None,
                    actor: str = '',
                    approver_selection: Optional[Any] = None) -> Optional[str]:
        """返回任务 id；不适用（未知对象 / 缺 id / 已有在途任务）返回 None。"""
        meta = get_approval_meta(object_type)
        actions = meta.get('decision_actions') or {}
        if not meta.get('table') or record_id in (None, '') or not actions:
            return None

        placeholders = ', '.join('?' * len(TASK_TERMINAL_STATUSES))
        active = self._ds.query(
            "SELECT id FROM tasks WHERE type = 'approval' "
            'AND doc_ref_type = ? AND doc_ref_id = ? '
            'AND status NOT IN ({0})'.format(placeholders),
            [object_type, str(record_id)] + list(TASK_TERMINAL_STATUSES),
        )
        if active:
            return None

        task_id = uuid.uuid4().hex
        id_key = meta['id_key']
        title = '{0} #{1}'.format(
            meta['title_prefix'], self._title_suffix(meta, record_id))
        inputs = {'id': record_id, id_key: record_id}
        if policy_snapshot:
            inputs['policy_snapshot'] = policy_snapshot
        # [P2] initiator_choice 输入通道：发起人自选名单随任务冻结（spec §9.5）
        if approver_selection:
            inputs['approver_selection'] = approver_selection

        # [M5-2/M5-4 2026-11-15] 候选池 = 取人器按当前阶段聚合解析（spec §9.5 / §9.4）：
        # 同阶段多步骤合并；auto 步骤自动通过、notify 步骤只读知会、approve 计入会签。
        stage_no = _stage_no(policy_snapshot)
        stage = resolve_stage(
            policy_snapshot or {}, stage_no,
            {'data_source': self._ds, 'task_type': _task_type_of(policy_snapshot),
             'object_type': object_type, 'record_id': record_id,
             'initiator': actor or 'system', 'policy_snapshot': policy_snapshot,
             'approver_selection': approver_selection})
        candidates = stage['candidates']
        notify = stage['notify']
        assignee = candidates[0] if len(candidates) == 1 else None
        if assignee and _has_task_column(self._ds, 'executor_assignee'):
            row_assignee = {'executor_assignee': assignee}
        else:
            row_assignee = {}
        stage_row = {'stage_no': stage_no} \
            if _has_task_column(self._ds, 'stage_no') else {}

        # [M4-4 2026-11-15] 步骤 sla_hours 非空才开 SLA 单（默认关闭，spec §8.5）
        created_dt = datetime.now()
        sla_cfg, due_at = _resolve_sla(policy_snapshot, created_dt)
        quorum_required = _resolve_quorum(policy_snapshot)
        sla_row = {}
        if sla_cfg:
            sla_row = {'sla': json.dumps(sla_cfg, ensure_ascii=False),
                       'due_at': due_at}

        row = {
            'id': task_id,
            'code': None,
            'title': title,
            'type': 'approval',
            'status': 'waiting_approval',
            'priority': 'P1',
            'app_id': meta['app_id'],
            'executor_type': 'human',
            'assign_policy': 'claim',
            'executor_candidates': json.dumps(candidates, ensure_ascii=False),
            **row_assignee,
            **stage_row,
            **sla_row,
            'executor_config': json.dumps(
                {'decision_actions': actions,
                 'completion_mode': _resolve_completion_mode(policy_snapshot),
                 # [M5-4] auto 自动通过 / notify 只读知会 / approve 人工决策
                 'action_type': stage['action'],
                 **({'quorum_required': quorum_required}
                    if quorum_required else {}),
                 **({'notify_candidates': notify} if notify else {}),
                 # [M5-2] 取人解释：为什么是这批人 / 为什么空池
                 'assign_source': stage['source'],
                 'assign_explain': stage['explain'],
                 **({'assign_reason': stage['reason']}
                    if stage['reason'] else {})},
                ensure_ascii=False),
            'inputs': json.dumps(inputs, ensure_ascii=False, default=str),
            'doc_ref': str(record_id),
            'doc_ref_type': object_type,
            'doc_ref_id': str(record_id),
            'created_by': actor or 'system',
            'created_at': created_dt.isoformat(timespec='seconds'),
            'attempt': 1,
        }
        columns = ', '.join(row.keys())
        values = ', '.join('?' * len(row))
        self._ds.execute(
            'INSERT INTO tasks ({0}) VALUES ({1})'.format(columns, values),
            list(row.values()),
        )
        # [M4-1] 参与流水与候选池双写（同一事务由调用方迁移/提交保证；表缺失跳过）
        _seed_participations(self._ds, task_id, candidates, actor or 'system',
                             notify=notify)
        # [M4-4] 按任务快照开 SLA 单（表缺失 / 无 sla_hours 跳过；不阻断建任务）
        if sla_cfg:
            _open_sla(self._ds, task_id, created_dt)
        # [M5-4] auto / 纯知会阶段不产生人工待办：建完即自动跨过（末阶段则走完）
        if stage['action'] in ('auto', 'notify'):
            settle_auto(self._ds, task_id, actor='system',
                        now=created_dt.isoformat(timespec='seconds'))
        logger.info('[ApprovalTask] %s id=%s 建审批任务 %s',
                    object_type, record_id, task_id)
        return task_id

    def _title_suffix(self, meta: Dict[str, Any], record_id: Any) -> str:
        field = meta.get('title_field')
        if not field:
            return str(record_id)
        rows = self._ds.query(
            'SELECT {0} AS doc_no FROM {1} WHERE id = ?'.format(
                field, meta['table']), [record_id])
        doc_no = rows[0].get('doc_no') if rows else None
        return str(doc_no or record_id)


# ─────────────────────────────────────────────────────────────────────────────
# [M4 2026-11-15] 候选池 / 参与流水双写（spec §8.1）
# ─────────────────────────────────────────────────────────────────────────────

def _first_step(policy_snapshot: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """当前阶段的首个步骤（排序键 = (stage_no, step_no)，spec §9.4）。"""
    steps = (policy_snapshot or {}).get('steps') or []
    if not steps:
        return None
    try:
        return sorted(steps, key=lambda s: (_int_of(s.get('stage_no'), 1),
                                            _int_of(s.get('step_no'), 0)))[0]
    except (TypeError, ValueError):
        return None


def _int_of(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _task_type_of(policy_snapshot: Optional[Dict[str, Any]]) -> str:
    """策略任务类型（spec D-GT-01：表名不动，通用性用 task_type 表达）。"""
    return str((policy_snapshot or {}).get('task_type') or 'approval')


def _stage_no(policy_snapshot: Optional[Dict[str, Any]]) -> int:
    step = _first_step(policy_snapshot)
    return max(_int_of((step or {}).get('stage_no'), 1), 1)


def _resolve_candidates(policy_snapshot: Optional[Dict[str, Any]]) -> list:
    """兼容入口：无 DataSource 时退化为字面名单（仅 `user` 型）。"""
    step = _first_step(policy_snapshot)
    if not step:
        return []
    return resolver.resolve(step, {}).candidates


def _first_stage_steps(policy_snapshot: Optional[Dict[str, Any]]) -> list:
    """首个阶段的全部步骤（同阶段多步骤需聚合，spec §9.4）。"""
    step = _first_step(policy_snapshot)
    if not step:
        return []
    stage = max(_int_of(step.get('stage_no'), 1), 1)
    return [s for s in (policy_snapshot or {}).get('steps') or []
            if max(_int_of(s.get('stage_no'), 1), 1) == stage]


def _resolve_completion_mode(policy_snapshot: Optional[Dict[str, Any]]) -> str:
    """首阶段会签口径：任一步 `all` 即 `all`，否则 `any`（spec §8.1/§9.4）。"""
    modes = [str(s.get('approve_mode') or 'any').strip().lower()
             for s in _first_stage_steps(policy_snapshot)]
    return 'all' if 'all' in modes else 'any'


def _resolve_quorum(policy_snapshot: Optional[Dict[str, Any]]) -> Optional[int]:
    """首阶段通过票数下限：`routing_json.quorum.required` 取最大值（spec §9.4）。"""
    required = []
    for step in _first_stage_steps(policy_snapshot):
        routing = step.get('routing_json')
        if isinstance(routing, str):
            try:
                routing = json.loads(routing)
            except (TypeError, ValueError):
                continue
        quorum = routing.get('quorum') if isinstance(routing, dict) else None
        value = _int_of(quorum.get('required'), 0) if isinstance(quorum, dict) else 0
        if value > 0:
            required.append(value)
    return max(required) if required else None


def _resolve_sla(policy_snapshot: Optional[Dict[str, Any]],
                 created_at: datetime) -> tuple:
    """首阶段各步骤 `sla_hours` 最小值 → (任务 sla 快照, due_at)；未声明 (None, None)。

    [M4-4 2026-11-15] 阈值属业务域、随任务冻结（spec §8.5）；`on_breach=None`
    即「只记录不动作」——超时改派由 `executor_config.sla_on_breach` 另行开关。
    同阶段多步骤时取最小值，保证先到期的步骤先触发。
    """
    hours_list = []
    for step in _first_stage_steps(policy_snapshot):
        try:
            hours = float(step.get('sla_hours'))
        except (TypeError, ValueError):
            continue
        if hours > 0:
            hours_list.append(hours)
    if not hours_list:
        return None, None
    seconds = int(min(hours_list) * 3600)
    return ({'target_seconds': seconds, 'warn_at_pct': 80, 'alert_at_pct': 95,
             'grace_seconds': 0, 'on_breach': None},
            (created_at + timedelta(seconds=seconds)).isoformat(timespec='seconds'))


def _open_sla(data_source, task_id: str, start_at: datetime) -> None:
    """开 SLA 单（表缺失 / 配置缺失跳过，不阻断建任务）。"""
    try:
        from meta.core.task_sla import open_sla_for_task
        open_sla_for_task(data_source, task_id, start_at=start_at)
    except Exception:  # noqa: BLE001
        logger.warning('[M4-4] 审批任务 SLA 开单失败（任务已建）：%s',
                       task_id, exc_info=True)


def _has_task_column(data_source, column: str) -> bool:
    try:
        rows = data_source.execute(
            'PRAGMA table_info(tasks)').fetchall()
    except Exception:  # noqa: BLE001
        return False
    return any(len(r) > 1 and r[1] == column for r in rows)


def _seed_participations(data_source, task_id: str, candidates: list,
                         actor: str, *, notify: Optional[list] = None) -> None:
    """参与流水与候选池双写；表缺失（迁移未执行）跳过，不阻断建任务。"""
    if not candidates and not notify:
        return
    try:
        from meta.core.task_participation import (
            NOTIFY_ROLE, participation_tables_exist, seed_participants,
        )
        if not participation_tables_exist(data_source).get('task_participations'):
            return
        seed_participants(data_source, task_id, candidates or [],
                          role='required', created_by=actor)
        if notify:
            seed_participants(data_source, task_id, notify,
                              role=NOTIFY_ROLE, created_by=actor)
    except Exception:  # noqa: BLE001
        logger.warning('[ApprovalTask] 参与流水双写失败（任务已建）：%s',
                       task_id, exc_info=True)