# -*- coding: utf-8 -*-
"""阶段推进（M5-3 / spec §9.8）

任务在当前阶段通过后，**原地**推进到下一阶段：
`tasks.stage_no` + 1 → 重派生候选人 → 重置参与流水 → 重开 SLA。

通用能力（不限审批）：所有输入都来自任务自带的快照
（`inputs.policy_snapshot`），不查策略表；无下一阶段时返回 `None`，
调用方继续走原有终态逻辑（BO 效果 / 任务完成）。
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from meta.core import task_assignee_resolver as resolver
from meta.core.task_participation import (
    NOTIFY_ROLE,
    VOTING_ROLES,
    participation_tables_exist,
    seed_participants,
    skip_other_pending,
)
from meta.core.task_sla import (
    ACTIVE_STAGES,
    cancel_sla,
    open_sla,
    sla_tables_exist,
)

logger = logging.getLogger(__name__)


def _load_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return fallback


def _int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stage_of(step: Dict[str, Any]) -> int:
    return max(_int(step.get('stage_no'), 1), 1)


def _snapshot_of(task: Dict[str, Any]) -> Dict[str, Any]:
    inputs = _load_json(task.get('inputs'), {})
    if not isinstance(inputs, dict):
        return {}
    snapshot = inputs.get('policy_snapshot')
    if isinstance(snapshot, dict):
        return snapshot
    # 兼容：不带 policy_snapshot 包装的裸快照
    return inputs if inputs.get('steps') else {}


def next_stage(snapshot: Dict[str, Any], current: int) -> Optional[int]:
    """返回大于 `current` 的最小阶段号（无则 None）。"""
    stages = sorted({_stage_of(s) for s in (snapshot.get('steps') or [])})
    for stage in stages:
        if stage > current:
            return stage
    return None


def _stage_steps(snapshot: Dict[str, Any], stage: int) -> List[Dict[str, Any]]:
    return [s for s in (snapshot.get('steps') or []) if _stage_of(s) == stage]


def _stage_completion_mode(snapshot: Dict[str, Any], stage: int) -> str:
    """阶段会签口径：任一步 `all` 即 `all`，否则 `any`（spec §9.4）。"""
    modes = [str(s.get('approve_mode') or 'any').strip().lower()
             for s in _stage_steps(snapshot, stage)]
    return 'all' if 'all' in modes else 'any'


def _stage_sla_hours(snapshot: Dict[str, Any], stage: int) -> Optional[int]:
    """阶段 SLA：取该阶段各步骤 `sla_hours` 的最小值（先到先算）。"""
    hours = [_int(s.get('sla_hours'), 0) for s in _stage_steps(snapshot, stage)]
    hours = [value for value in hours if value > 0]
    return min(hours) if hours else None


def _stage_quorum(snapshot: Dict[str, Any], stage: int) -> Optional[int]:
    """阶段通过票数下限：`routing_json.quorum.required` 取最大值（spec §9.4）。"""
    required = []
    for step in _stage_steps(snapshot, stage):
        routing = _load_json(step.get('routing_json'), {})
        if not isinstance(routing, dict):
            continue
        quorum = routing.get('quorum')
        value = _int(quorum.get('required')) if isinstance(quorum, dict) else None
        if value and value > 0:
            required.append(value)
    return max(required) if required else None


def _sla_snapshot(hours: Optional[int]) -> Optional[Dict[str, Any]]:
    """任务 `sla` 快照（与审批建任务同构，spec §8.5）。"""
    if not hours or hours <= 0:
        return None
    return {'target_seconds': int(hours * 3600), 'warn_at_pct': 80,
            'alert_at_pct': 95, 'grace_seconds': 0, 'on_breach': None}


#: [M5-4] 步骤动作三态（定义层 approval_policy_steps.action_type）
ACTIONS = ('approve', 'auto', 'notify')

#: 不产生人工待办/不阻塞流转的动作（auto 自动通过、纯知会阶段）
PASSIVE_ACTIONS = ('auto', 'notify')


def step_action(step: Dict[str, Any]) -> str:
    action = str((step or {}).get('action_type') or 'approve').strip().lower()
    return action if action in ACTIONS else 'approve'


def stage_action(snapshot: Dict[str, Any], stage: int) -> str:
    """阶段动作聚合：全 auto → auto；无 approve → notify；否则 approve。"""
    actions = [step_action(s) for s in _stage_steps(snapshot, stage)]
    if not actions:
        return 'approve'
    if all(action == 'auto' for action in actions):
        return 'auto'
    if any(action == 'approve' for action in actions):
        return 'approve'
    return 'notify'


def resolve_stage(snapshot: Dict[str, Any], stage: int,
                  ctx: Dict[str, Any]) -> Dict[str, Any]:
    """按阶段聚合取人：投票候选 / 知会候选 / 合并解释（M5-4）。

    同一阶段的多个步骤在此合并：auto 步骤不取人（自动通过）；notify 步骤
    只读不投票；approve 步骤计入会签分母。既投票又被知会者只保留投票身份。
    """
    ctx = dict(ctx or {})
    ctx.setdefault('policy_snapshot', snapshot)
    voting: List[str] = []
    notify: List[str] = []
    explain: List[Dict[str, Any]] = []
    reason: Optional[str] = None
    source = ''
    steps = sorted(_stage_steps(snapshot, stage),
                   key=lambda s: _int(s.get('step_no'), 0))
    for step in steps:
        action = step_action(step)
        step_no = _int(step.get('step_no'), 0)
        if action == 'auto':
            explain.append({'step_no': step_no, 'action_type': 'auto',
                            'field': 'action_type', 'op': 'eq',
                            'expected': 'approve', 'actual': 'auto',
                            'passed': True, 'auto_passed': True})
            continue
        result = resolver.resolve(step, ctx)
        bucket = notify if action == 'notify' else voting
        for name in result.candidates:
            if name not in bucket:
                bucket.append(name)
        for item in result.explain:
            enriched = dict(item)
            enriched.setdefault('step_no', step_no)
            enriched.setdefault('action_type', action)
            explain.append(enriched)
        if result.reason and reason is None:
            reason = result.reason
        source = result.source or source
    notify = [name for name in notify if name not in voting]
    if not steps:
        reason = resolver.REASON_NO_MEMBER
    return {
        'action': stage_action(snapshot, stage),
        'candidates': voting,
        'notify': notify,
        'explain': explain,
        'reason': reason,
        'source': source,
    }


def _has_column(data_source, table: str, column: str) -> bool:
    try:
        rows = data_source.execute(
            'PRAGMA table_info(%s)' % table).fetchall()
    except Exception:  # noqa: BLE001
        return False
    return any(str(row[1]) == column for row in rows)


def _sla_key(stage: int) -> str:
    return 'stage-%d' % stage


def _close_open_slas(data_source, task_id: str, *, at: str) -> None:
    if not sla_tables_exist(data_source).get('task_slas'):
        return
    try:
        rows = data_source.execute(
            'SELECT id, stage FROM task_slas WHERE task_id = ?',
            (str(task_id),)).fetchall()
    except Exception:  # noqa: BLE001
        return
    for row in rows:
        if row[1] in ACTIVE_STAGES:
            try:
                cancel_sla(data_source, row[0], at=at)
            except Exception:  # noqa: BLE001
                logger.warning('[TaskStage] 关闭旧 SLA 失败：%s', row[0],
                               exc_info=True)


def _sla_exists(data_source, task_id: str, key: str) -> bool:
    if not sla_tables_exist(data_source).get('task_slas'):
        return False
    try:
        rows = data_source.execute(
            'SELECT id FROM task_slas WHERE task_id = ? AND sla_key = ? '
            'LIMIT 1', (str(task_id), key)).fetchall()
    except Exception:  # noqa: BLE001
        return False
    return bool(rows)


def _due_at(start: datetime, hours: Optional[int]) -> Optional[str]:
    if not hours or hours <= 0:
        return None
    return (start + timedelta(hours=hours)).isoformat()


def _reload_task(data_source, task_id: str) -> Dict[str, Any]:
    """全列重载任务（`_load_task` 只取部分列，阶段字段需单独读）。"""
    try:
        rows = data_source.query('SELECT * FROM tasks WHERE id = ?', [task_id])
    except Exception:  # noqa: BLE001
        return {}
    return dict(rows[0]) if rows else {}


def _stage_context(data_source, task: Dict[str, Any], snapshot: Dict[str, Any],
                   actor: str) -> Dict[str, Any]:
    return {
        'data_source': data_source,
        'task_type': snapshot.get('task_type') or 'approval',
        'object_type': task.get('doc_ref_type'),
        'record_id': _int(task.get('doc_ref_id'), 0),
        'initiator': task.get('created_by') or actor,
        'policy_snapshot': snapshot,
    }


def _advance_once(data_source, task: Dict[str, Any], *,
                  actor: str = '', now: Any = None) -> Optional[Dict[str, Any]]:
    """推进一阶段（不做 auto 兜底）；无下一阶段/无快照时返回 None。"""
    task_id = str(task.get('id') or '')
    task = _reload_task(data_source, task_id) or dict(task)
    snapshot = _snapshot_of(task)
    current = max(_int(task.get('stage_no'), 1), 1)
    target = next_stage(snapshot, current)
    if target is None:
        return None

    resolution = resolve_stage(snapshot, target,
                               _stage_context(data_source, task, snapshot, actor))

    ts = now or datetime.now().isoformat()
    start = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
    hours = _stage_sla_hours(snapshot, target)
    due = _due_at(start, hours)

    config = _load_json(task.get('executor_config'), {})
    if not isinstance(config, dict):
        config = {}
    config.update({
        'completion_mode': _stage_completion_mode(snapshot, target),
        'action_type': resolution['action'],
        'assign_source': resolution['source'],
        'assign_explain': resolution['explain'],
    })
    quorum = _stage_quorum(snapshot, target)
    if quorum:
        config['quorum_required'] = quorum
    else:
        config.pop('quorum_required', None)
    if resolution['notify']:
        config['notify_candidates'] = resolution['notify']
    else:
        config.pop('notify_candidates', None)
    if resolution['reason']:
        config['assign_reason'] = resolution['reason']
    else:
        config.pop('assign_reason', None)
    config['stage'] = target

    candidates = resolution['candidates']
    columns: Dict[str, Any] = {
        'executor_candidates': json.dumps(candidates, ensure_ascii=False),
        'executor_config': json.dumps(config, ensure_ascii=False),
        'updated_at': ts,
    }
    if _has_column(data_source, 'tasks', 'stage_no'):
        columns['stage_no'] = target
    if _has_column(data_source, 'tasks', 'executor_assignee'):
        columns['executor_assignee'] = candidates[0] if len(candidates) == 1 else None
    if _has_column(data_source, 'tasks', 'due_at'):
        columns['due_at'] = due
    if _has_column(data_source, 'tasks', 'sla'):
        columns['sla'] = (json.dumps(_sla_snapshot(hours), ensure_ascii=False)
                          if hours else None)

    assignments = ', '.join('%s = ?' % k for k in columns)
    sql = 'UPDATE tasks SET %s WHERE id = ?' % assignments
    params: List[Any] = list(columns.values()) + [task_id]
    # [P0] CAS：只推进仍停留在 current 阶段的任务，避免并发双签把阶段连跳
    if 'stage_no' in columns:
        sql += ' AND COALESCE(stage_no, 1) = ?'
        params.append(current)
    cursor = data_source.execute(sql, params)
    if getattr(cursor, 'rowcount', None) == 0:
        logger.info('[TaskStage] 阶段已被并发推进，跳过：%s', task_id)
        return None

    # 参与流水：旧阶段投票待办作废（知会行保留只读）→ 新阶段重新种人
    try:
        skip_other_pending(data_source, task_id, roles=VOTING_ROLES, now=ts)
    except Exception:  # noqa: BLE001
        logger.debug('[TaskStage] 清理旧阶段参与流水跳过', exc_info=True)
    try:
        if participation_tables_exist(data_source).get('task_participations'):
            seed_participants(data_source, task_id, candidates,
                              role='required', created_by=actor or 'system')
            if resolution['notify']:
                seed_participants(data_source, task_id, resolution['notify'],
                                  role=NOTIFY_ROLE, created_by=actor or 'system')
    except Exception:  # noqa: BLE001
        logger.warning('[TaskStage] 新阶段参与流水写入失败：%s', task_id,
                       exc_info=True)

    # SLA：旧阶段关单 → 新阶段按 (task_id, stage_no) 幂等开单
    key = _sla_key(target)
    _close_open_slas(data_source, task_id, at=ts)
    if hours and not _sla_exists(data_source, task_id, key):
        try:
            open_sla(data_source, task_id=task_id, sla_key=key,
                     name=snapshot.get('policy_code') or '',
                     target_seconds=hours * 3600, due_at=due, start_at=ts)
        except Exception:  # noqa: BLE001
            logger.warning('[TaskStage] 新阶段 SLA 开单失败：%s', task_id,
                           exc_info=True)

    return {
        'status': 'stage_advanced',
        'task_id': task_id,
        'task_status': 'waiting_approval',
        'stage_no': target,
        'action_type': resolution['action'],
        'candidates': candidates,
        'notify': resolution['notify'],
        'assign_explain': resolution['explain'],
        'assign_reason': resolution['reason'],
    }


def _complete(data_source, task: Dict[str, Any], *,
              actor: str = '', now: Any = None) -> Dict[str, Any]:
    """auto 兜底走完末阶段：效果型任务走 `decide_and_apply`，其余直接 done。"""
    from meta.core.decision_effect import EFFECT_TASK_TYPES, decide_and_apply

    task_id = str(task.get('id') or '')
    ts = now or datetime.now().isoformat()
    if str(task.get('type') or '') in EFFECT_TASK_TYPES:
        outcome = dict(decide_and_apply(
            data_source, task_id, decision='approve',
            comment='自动通过（action_type=auto）',
            actor=actor or 'system', actor_kind='system',
            reviewer_permission=True))
        outcome['effect_applied'] = True
    else:
        data_source.execute(
            'UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?',
            ('done', ts, task_id))
        outcome = {'status': 'completed', 'task_status': 'done',
                   'effect_applied': False}
    outcome.update({'task_id': task_id, 'auto_completed': True,
                    'stage_no': _int(task.get('stage_no'), 1)})
    return outcome


def _settle_from(data_source, task: Dict[str, Any], *, actor: str = '',
                 now: Any = None) -> Optional[Dict[str, Any]]:
    """从当前阶段起跨过连续的 auto / 纯知会阶段；末阶段则自动完成。"""
    result: Optional[Dict[str, Any]] = None
    for _ in range(20):                      # 防御：阶段数上限
        snapshot = _snapshot_of(task)
        current = max(_int(task.get('stage_no'), 1), 1)
        if stage_action(snapshot, current) not in PASSIVE_ACTIONS:
            return result
        if next_stage(snapshot, current) is None:
            return _complete(data_source, task, actor=actor, now=now)
        result = _advance_once(data_source, task, actor=actor, now=now)
        if result is None:
            return None
        task = _reload_task(data_source, str(task.get('id') or '')) or task
    return result


def settle_auto(data_source, task_id: str, *, actor: str = 'system',
                now: Any = None) -> Optional[Dict[str, Any]]:
    """建任务后调用：当前阶段为 auto / 纯知会时自动跨过。

    Returns: 推进或完成结果；当前阶段需要人工决策时返回 None。
    """
    task = _reload_task(data_source, str(task_id))
    if not task:
        return None
    snapshot = _snapshot_of(task)
    current = max(_int(task.get('stage_no'), 1), 1)
    if stage_action(snapshot, current) not in PASSIVE_ACTIONS:
        return None
    return _settle_from(data_source, task, actor=actor, now=now)


def advance_stage(data_source, task: Dict[str, Any], *,
                  actor: str = '', now: Any = None) -> Optional[Dict[str, Any]]:
    """推进一阶段并自动跨过后续 auto / 纯知会阶段（M5-3 / M5-4）。"""
    result = _advance_once(data_source, task, actor=actor, now=now)
    if result is None:
        return None
    reloaded = _reload_task(data_source, str(task.get('id') or '')) or task
    return _settle_from(data_source, reloaded, actor=actor, now=now) or result


