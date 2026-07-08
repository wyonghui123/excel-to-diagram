# -*- coding: utf-8 -*-
import logging
from flask import Blueprint, request, jsonify

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
        return jsonify({'success': False, 'error': str(e)}), 500


@task_api_bp.route('/api/v2/task-scheduler/reload', methods=['POST'])
def task_scheduler_reload():
    try:
        scheduler = _get_scheduler()
        scheduler.reload()
        return jsonify({'success': True, 'message': 'Reloaded'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@task_api_bp.route('/api/v2/tasks/<task_code>/enable', methods=['POST'])
def enable_task(task_code):
    try:
        scheduler = _get_scheduler()
        ds = scheduler.data_source
        ds.execute(
            "UPDATE scheduled_tasks SET enabled = 1 WHERE code = ?",
            (task_code,)
        )
        ds.commit()
        scheduler.reload()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@task_api_bp.route('/api/v2/tasks/<task_code>/disable', methods=['POST'])
def disable_task(task_code):
    try:
        scheduler = _get_scheduler()
        ds = scheduler.data_source
        ds.execute(
            "UPDATE scheduled_tasks SET enabled = 0 WHERE code = ?",
            (task_code,)
        )
        ds.commit()
        scheduler.reload()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
                {'success': False, 'error': 'Execution not found'}
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
        return jsonify({'success': False, 'error': str(e)}), 500


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
        return jsonify({'success': False, 'error': str(e)}), 500


@task_api_bp.route('/api/v2/task-queues/stats', methods=['GET'])
def queue_stats():
    try:
        scheduler = _get_scheduler()
        stats = scheduler.queue_manager.get_queue_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500