# -*- coding: utf-8 -*-
"""遗留任务执行基础设施 API（队列）

[docs/specs/task-two-generation-convergence] 2026-10-30 收口：
  Gen1 的定时配置层 `scheduled_tasks` 已退役（v155），对应的
  `trigger` / `enable` / `disable` 三条路由一并删除。cron 调度的唯一入口是
  进程内调度器：
    - 运维作业 → POST /api/v2/schedulers/<job_code>/run-now
    - 全局暂停 cron → 环境变量 CRON_JOBS_ENABLED=0

[账本统一 Phase 2c 2026-10-31] Gen1 执行账本 `task_executions` 已由
v165/v166 退役：`retry` / `cancel` 两条写路由一并删除（历史事件改由平台库
`task_events` 承载）。本 blueprint 只保留调度器状态 / 重载 / 队列统计。
"""
import logging
from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)

task_api_bp = Blueprint('task_api', __name__)

_scheduler = None


def set_scheduler(scheduler):
    global _scheduler
    _scheduler = scheduler


def _get_scheduler():
    if _scheduler is None:
        raise RuntimeError("TaskScheduler not initialized")
    return _scheduler


@task_api_bp.route('/api/v2/task-scheduler/status', methods=['GET'])
def task_scheduler_status():
    try:
        scheduler = _get_scheduler()
        status = scheduler.get_status()
        return jsonify({'success': True, 'data': status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@task_api_bp.route('/api/v2/task-scheduler/reload', methods=['POST'])
def task_scheduler_reload():
    try:
        scheduler = _get_scheduler()
        scheduler.reload()
        return jsonify({'success': True, 'message': 'Reloaded'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@task_api_bp.route('/api/v2/task-queues/stats', methods=['GET'])
def queue_stats():
    try:
        scheduler = _get_scheduler()
        stats = scheduler.queue_manager.get_queue_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
