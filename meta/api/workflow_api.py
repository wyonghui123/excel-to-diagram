# -*- coding: utf-8 -*-
"""[C 组编排完整] 编排只读聚合端点 —— 调度视图的数据源

为什么要有这个模块:
  任务管理页需要一个「调度」tab，把三段信息拼在一起：
    (1) 编排定义（哪些 workflow 声明了 schedule、几个节点）；
    (2) 触发规则（cron 表达式与可读描述、下次触发时间）；
    (3) 运行实例（该 workflow 最近的 Run 及其派生状态）。
  这三段分别来自 `workflows` 定义表、进程内调度器、`workflow_runs` 实例表 ——
  本模块把它们聚合为一条只读响应，供前端直接渲染。

  **只读**：本模块不做任何调度、不改任何状态；真正的调度归
  `meta/core/workflow_schedule_scheduler.py`。此处只如实反映调度器现状。

  为什么随 `tasks` 模块门控（而 `scheduler_api` 无条件）：本视图是任务/编排域的
  用户界面数据源（对齐 `task_api_bp` 的门控口径）；运维作业视图走 `scheduler_api`，
  两者互不重叠。

处置边界:
  - 调度器由 server.py 经 `set_workflow_scheduler` 注入；数据源取自其 `data_source`。
  - 未接线 → 503；暂停态（`CRON_JOBS_ENABLED=0`）→ 明确答 `paused=True`。
"""
from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify

from meta.core.cron_parser import CronParser
from meta.core.workflow_engine import run_progress
from meta.core.workflow_store import get_nodes, list_latest_workflows
from meta.core.workflow_trigger import TRIGGER_SCHEDULE

logger = logging.getLogger(__name__)

workflow_bp = Blueprint('workflow_api', __name__)

_workflow_scheduler = None
_paused = False

#: 每个 workflow 返回的最近运行条数（视图只展示「最近」，不做全量）
_RECENT_RUNS = 5

#: 视为「已完成」的任务终态（与 `workflow_engine._TERMINAL_OK` 同口径）
_DONE_STATUSES = ('done', 'skipped', 'cancelled')


def set_workflow_scheduler(scheduler, paused: bool = False) -> None:
    """由 server.py 在启动期注入 Workflow 调度器。

    - 正常运行：传调度器实例，`paused=False`；
    - cron 暂停（`CRON_JOBS_ENABLED=0`）：`set_workflow_scheduler(None, paused=True)`；
    - 未接线：保持默认 `(None, paused=False)` → schedules/status 返回 503。
    """
    global _workflow_scheduler, _paused
    _workflow_scheduler = scheduler
    _paused = bool(paused)


def _data_source():
    """只读查询用的数据源：取自注入的调度器（未接线则 None）。"""
    if _workflow_scheduler is None:
        return None
    return getattr(_workflow_scheduler, 'data_source', None)


# ─────────────────────────────────────────────────────────────────────────────
# 聚合辅助
# ─────────────────────────────────────────────────────────────────────────────

def _cron_of(workflow) -> str:
    """从定义行的 trigger_expr 取 cron；解析失败返回空串（不抛）。"""
    raw = workflow.get('trigger_expr')
    if not isinstance(raw, str) or not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    cron = data.get('cron') if isinstance(data, dict) else None
    return cron.strip() if isinstance(cron, str) else ""


def _cron_label(cron: str) -> str:
    """cron 可读描述；非法/空返回空串（CronParser.describe 会抛）。"""
    if not cron:
        return ""
    try:
        return CronParser().describe(cron)
    except Exception:       # noqa: BLE001 —— 描述失败不该影响聚合
        return ""


def _node_count(data_source, workflow) -> int:
    return len(get_nodes(data_source, workflow['id'], workflow['version']))


def _recent_runs(data_source, workflow_key: str, limit: int = _RECENT_RUNS):
    """最近若干 Run（`workflow_runs` 派生状态 + 进度；Run 无状态列）。"""
    rows = data_source.execute(
        "SELECT id, started_at, created_at FROM workflow_runs "
        "WHERE workflow_key = ? ORDER BY created_at DESC, id DESC LIMIT ?",
        (workflow_key, limit)).fetchall()
    runs = []
    for run_id, started_at, created_at in rows:
        progress = run_progress(data_source, run_id)
        counts = progress.get('counts', {})
        done = sum(counts.get(status, 0) for status in _DONE_STATUSES)
        runs.append({
            'run_id': run_id,
            'started_at': started_at or created_at,
            'status': progress.get('status'),
            'total': progress.get('total', 0),
            'done': done,
        })
    return runs


# ─────────────────────────────────────────────────────────────────────────────
# 只读端点
# ─────────────────────────────────────────────────────────────────────────────

@workflow_bp.route('/api/v2/workflows/schedules', methods=['GET'])
def workflow_schedules():
    """编排 + 触发规则 + 运行实例 的三段只读聚合。"""
    data_source = _data_source()
    if data_source is None:
        return jsonify({
            'success': False,
            'message': 'workflow scheduler not initialized',
        }), 503

    scheduler_status = _workflow_scheduler.status() if _workflow_scheduler else {}
    items = []
    for workflow in list_latest_workflows(data_source,
                                          trigger_kind=TRIGGER_SCHEDULE):
        key = workflow['workflow_key']
        cron = _cron_of(workflow)
        items.append({
            'workflow_key': key,
            'name': workflow.get('name') or '',
            'version': workflow.get('version'),
            'node_count': _node_count(data_source, workflow),
            'cron': cron,
            'cron_label': _cron_label(cron),
            'next_run_at': (scheduler_status.get(key) or {}).get('next_run_at'),
            'scheduler_registered': bool(_workflow_scheduler
                                         and _workflow_scheduler.is_registered(key)),
            'runs': _recent_runs(data_source, key),
        })
    return jsonify({'success': True, 'data': {'items': items}})


@workflow_bp.route('/api/v2/workflows/scheduler/status', methods=['GET'])
def workflow_scheduler_status():
    """Workflow 调度器作业状态（未接线 503 / 暂停 200+paused）。"""
    if _workflow_scheduler is None:
        if _paused:
            return jsonify({
                'success': True,
                'data': {'paused': True, 'jobs': None},
            })
        return jsonify({
            'success': False,
            'message': 'workflow scheduler not initialized',
        }), 503
    return jsonify({
        'success': True,
        'data': {'paused': False, 'jobs': _workflow_scheduler.status()},
    })
