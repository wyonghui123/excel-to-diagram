# -*- coding: utf-8 -*-
"""后台作业管理端点（spec §8.2：手动运行 / 重试 / 取消）。

依据:
  docs/specs/spec-background-job-infrastructure-2026-11-10.md §8.2 / §10.1 第 5 项

边界:
  · 只写 `task_runs` 的生命周期字段（由 `JobRunStore` 负责），不碰
    `status` 之外的 `attempt` / `run_key` / `worker_id`（spec §8.2）；
  · 本模块**不执行作业**，执行只发生在 dispatcher；
  · 权限码 `job_admin`（管理员 '*' 通配放行）。
"""
from __future__ import annotations

import logging
import uuid

from flask import Blueprint, jsonify, request

from meta.core.job_params import merge_job_params
from meta.services.auth_middleware import require_permission

logger = logging.getLogger(__name__)

job_admin_bp = Blueprint('job_admin_api', __name__)

_store = None


def set_job_store(store) -> None:
    """由 server.py 注入 `JobRunStore`（未注入时端点返回 503）。"""
    global _store
    _store = store


def _store_or_error():
    if _store is None:
        return None, (jsonify({
            'success': False,
            'message': 'job run store not initialized',
        }), 503)
    return _store, None


@job_admin_bp.route('/api/v2/jobs/<code>/run-now', methods=['POST'])
@require_permission('job_admin')
def job_run_now(code):
    store, error = _store_or_error()
    if error:
        return error
    job = store.job_by_code(code)
    if not job:
        return jsonify({
            'success': False,
            'message': 'Unknown job: %s' % code,
        }), 404

    body = request.get_json(silent=True) or {}
    params = body.get('params') if isinstance(body, dict) else None
    if params is not None and not isinstance(params, dict):
        return jsonify({'success': False, 'message': 'params 必须是 object'}), 400

    run_key = 'manual:%s' % uuid.uuid4().hex
    run_id = store.create_run(code, params=merge_job_params(job, params),
                              run_key=run_key)
    if run_id is None:
        return jsonify({
            'success': False,
            'message': 'job definition disappeared: %s' % code,
        }), 409
    logger.info('[job-admin] manual run-now job=%s run=%s', code, run_id)
    return jsonify({
        'success': True,
        'data': {'run_id': run_id, 'run_key': run_key, 'job_code': code},
    })


@job_admin_bp.route('/api/v2/jobs/runs/<int:run_id>/retry', methods=['POST'])
@require_permission('job_admin')
def job_retry(run_id):
    store, error = _store_or_error()
    if error:
        return error
    if not store.get_run(run_id):
        return jsonify({'success': False, 'message': 'Unknown run: %s' % run_id}), 404
    if not store.retry(run_id):
        return jsonify({
            'success': False,
            'message': 'run %s 当前状态不可重试' % run_id,
        }), 409
    return jsonify({'success': True, 'data': {'run_id': run_id,
                                              'status': 'pending'}})


@job_admin_bp.route('/api/v2/jobs/runs/<int:run_id>/cancel', methods=['POST'])
@require_permission('job_admin')
def job_cancel(run_id):
    store, error = _store_or_error()
    if error:
        return error
    if not store.get_run(run_id):
        return jsonify({'success': False, 'message': 'Unknown run: %s' % run_id}), 404
    if not store.cancel(run_id):
        return jsonify({
            'success': False,
            'message': 'run %s 当前状态不可取消' % run_id,
        }), 409
    return jsonify({'success': True, 'data': {'run_id': run_id,
                                              'status': 'cancelled'}})