# -*- coding: utf-8 -*-
import logging
from flask import Blueprint, request, jsonify

from meta.core.maintenance_scheduler import JOB_CODES

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


def _migrated_response(task_code):
    """[P1 2026-10-13] 已迁出作业码的调度**已内嵌进程内调度器代码**，`scheduled_tasks`
    表不再承载其调度 —— 改表改不动。此处必须显式报错（409），而非静默回
    success:true（假成功）。"""
    return jsonify({
        'success': False,
        'message': (
            f'Task {task_code} 的调度已迁到进程内调度器（配置内嵌代码，'
            f'scheduled_tasks 表不再承载）：请改用 '
            f'POST /api/v2/schedulers/{task_code}/run-now；'
            f'如需全局暂停 cron，设环境变量 CRON_JOBS_ENABLED=0'
        ),
    }), 409


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


@task_api_bp.route('/api/v2/tasks/<task_code>/trigger', methods=['POST'])
def trigger_task(task_code):
    try:
        scheduler = _get_scheduler()
        scheduler.trigger_task(task_code)
        return jsonify({
            'success': True,
            'message': f'Task {task_code} triggered'
        })
    except ValueError as e:
        # [P1 2026-10-13] 已迁出的作业码不在遗留调度器 _tasks 里 —— 触发它已无意义，
        # 改用新的进程内调度器端点（显式 409，不假成功）。
        if task_code in JOB_CODES:
            return _migrated_response(task_code)
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@task_api_bp.route('/api/v2/tasks/<task_code>/enable', methods=['POST'])
def enable_task(task_code):
    try:
        scheduler = _get_scheduler()
        ds = scheduler.data_source
        cursor = ds.execute(
            "UPDATE scheduled_tasks SET enabled = 1 WHERE code = ?",
            (task_code,)
        )
        # [P1 2026-10-13] 0 行 = 没改到任何东西：迁移码 → 409，未知码 → 404，
        # 不再静默回 success:true（假成功）。
        changed = getattr(cursor, 'rowcount', None)
        if changed == 0:
            if task_code in JOB_CODES:
                return _migrated_response(task_code)
            return jsonify(
                {'success': False, 'message': f'Task {task_code} not found'}
            ), 404
        ds.commit()
        scheduler.reload()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@task_api_bp.route('/api/v2/tasks/<task_code>/disable', methods=['POST'])
def disable_task(task_code):
    try:
        scheduler = _get_scheduler()
        ds = scheduler.data_source
        cursor = ds.execute(
            "UPDATE scheduled_tasks SET enabled = 0 WHERE code = ?",
            (task_code,)
        )
        # [P1 2026-10-13] 同上：0 行须显式报错，不假成功。
        changed = getattr(cursor, 'rowcount', None)
        if changed == 0:
            if task_code in JOB_CODES:
                return _migrated_response(task_code)
            return jsonify(
                {'success': False, 'message': f'Task {task_code} not found'}
            ), 404
        ds.commit()
        scheduler.reload()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@task_api_bp.route('/api/v2/task-executions/<int:execution_id>/retry', methods=['POST'])
def retry_execution(execution_id):
    try:
        scheduler = _get_scheduler()
        ds = scheduler.data_source
        
        exec_record = ds.query(
            "SELECT * FROM task_executions WHERE id = ?",
            (execution_id,)
        )
        if not exec_record:
            return jsonify(
                {'success': False, 'message': 'Execution not found'}
            ), 404
        
        from datetime import datetime
        ds.execute(
            "UPDATE task_executions SET status = 'pending', "
            "retry_count = 0, error_message = NULL "
            "WHERE id = ?",
            (execution_id,)
        )
        ds.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@task_api_bp.route('/api/v2/task-executions/<int:execution_id>/cancel', methods=['POST'])
def cancel_execution(execution_id):
    try:
        scheduler = _get_scheduler()
        ds = scheduler.data_source
        
        from datetime import datetime
        ds.execute(
            "UPDATE task_executions SET status = 'cancelled' "
            "WHERE id = ? AND status IN ('pending','queued')",
            (execution_id,)
        )
        ds.commit()
        return jsonify({'success': True})
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