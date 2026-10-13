# -*- coding: utf-8 -*-
"""[P1 2026-10-13] 进程内调度器运维端点 —— 只读状态 + 按需触发

为什么要有这个模块:
  替换路径第 3 项收口后，`scheduled_tasks` 历史行已清理、进程内调度器成为唯一
  cron 路径。运维侧因此失去两个原入口，需在无 DB 依赖的前提下补回：
    (1) 只读视图：两个进程内调度器各挂了哪些作业、下次何时跑、handler 是否就绪；
    (2) 按需跑一次：cron 到点之外的手工触发（原走遗留调度器的 trigger）。

  为什么不复用 `task_api`：`task_api_bp` 被 `tasks` 模块开关门控（server.py 仅在
  `is_module_enabled('tasks')` 时注册），而运维作业是平台基础设施、与任务模块开关
  无关 —— 故本蓝图独立、**无条件注册**。

处置边界:
  - 调度状态由 server.py 通过 `set_inprocess_schedulers` 注入；本模块不做调度。
  - 两条路径都只操作进程内调度器，不读写任何数据表。
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

scheduler_bp = Blueprint('scheduler_api', __name__)

_maintenance = None
_platform = None
_paused = False


def set_inprocess_schedulers(maintenance, platform, paused: bool = False) -> None:
    """由 server.py 在启动期注入两个进程内调度器。

    - 正常运行：传两个调度器实例，`paused=False`；
    - cron 暂停（`CRON_JOBS_ENABLED=0`）：传 `(None, None, paused=True)`；
    - 从未接线：保持默认 `(None, None, paused=False)` → status 返回 503。
    """
    global _maintenance, _platform, _paused
    _maintenance = maintenance
    _platform = platform
    _paused = bool(paused)


def _find_scheduler(code: str):
    """按作业码定位其归属调度器（`status()` 的键即该调度器的作业集）。"""
    for sched in (_maintenance, _platform):
        if sched is not None and code in sched.status():
            return sched
    return None


@scheduler_bp.route('/api/v2/schedulers/status', methods=['GET'])
def schedulers_status():
    if _maintenance is None and _platform is None:
        # 暂停态：两个调度器都没启动，但这是**有意**的（CRON_JOBS_ENABLED=0）
        if _paused:
            return jsonify({
                'success': True,
                'data': {'paused': True, 'maintenance': None, 'platform': None},
            })
        # 未接线：既非暂停也非运行 → 服务不可用
        return jsonify({
            'success': False,
            'message': 'in-process schedulers not initialized',
        }), 503
    return jsonify({
        'success': True,
        'data': {
            'paused': _paused,
            'maintenance': _maintenance.status() if _maintenance else None,
            'platform': _platform.status() if _platform else None,
        },
    })


@scheduler_bp.route('/api/v2/schedulers/<code>/run-now', methods=['POST'])
def scheduler_run_now(code):
    sched = _find_scheduler(code)
    if sched is None:
        return jsonify({
            'success': False,
            'message': f'Unknown scheduler job: {code}',
        }), 404
    if not sched.is_registered(code):
        return jsonify({
            'success': False,
            'message': f'Job {code} has no registered handler',
        }), 409
    if not sched.run_now(code):
        return jsonify({
            'success': False,
            'message': f'Job {code} not dispatched',
        }), 409
    return jsonify({'success': True, 'message': f'Job {code} triggered'})
