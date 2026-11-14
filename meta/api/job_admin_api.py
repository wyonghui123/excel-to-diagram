# -*- coding: utf-8 -*-
"""后台作业管理端点（spec IF-002 / IF-003 / IF-007 ~ IF-012）。

依据:
  docs/specs/spec-unified-async-job-2026-11-14.md（v1.4）

边界:
  · 只写 `job_definitions` 白名单字段与 `task_runs` 生命周期字段；
  · `params_schema` / `handler` / `executor_type` 只读，禁止经 API 注册执行器；
  · 本模块**不执行作业**，执行只发生在 dispatcher；
  · 权限码 `job_admin`（管理员 '*' 通配放行）。
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from meta.core.cron_parser import CronParser
from meta.core.job_params import (
    job_default_params,
    job_params_schema,
    merge_job_params,
    redact_secrets,
    sanitize_params_detailed,
)
from meta.core.job_run_store import (
    RUN_SOURCES,
    RUN_STATUSES,
    TERMINAL_STATUSES,
    TRIGGER_TYPES,
)
from meta.services.auth_middleware import require_permission

logger = logging.getLogger(__name__)

job_admin_bp = Blueprint('job_admin_api', __name__)

_store = None
_registry = None
_dispatcher = None
_cron = CronParser()

#: 定义 PATCH 白名单（其余列只读）。
_JOB_EDITABLE = ('name', 'description', 'default_params', 'timeout_seconds',
                 'max_attempts', 'backoff_seconds', 'status')
_JOB_STATUSES = frozenset({'active', 'paused'})

#: 触发器 PATCH 白名单（`trigger_type` 不可变：换类型请删后重建）。
_TRIGGER_EDITABLE = ('cron_expr', 'interval_seconds', 'params_override',
                     'enabled', 'next_run_at')

#: 手动运行 `scheduled_for` 容差（±60s，防止形成影子调度器）。
SCHEDULE_TOLERANCE_SECONDS = 60

_TRIGGER_KEY_RE = re.compile(r'^(\d+):(\d+)$')


def set_job_store(store) -> None:
    """由 server.py 注入 `JobRunStore`（未注入时端点返回 503）。"""
    global _store
    _store = store


def set_job_registry(registry) -> None:
    """注入 `ExecutorRegistry`，用于派生 `available` / `can_run`。"""
    global _registry
    _registry = registry


def set_job_dispatcher(dispatcher) -> None:
    """注入 `JobDispatcher`，用于 `GET /jobs/dispatcher/status`。"""
    global _dispatcher
    _dispatcher = dispatcher


def get_job_store():
    """供其他蓝图（如 `/import/async`）复用同一账本实例。"""
    return _store


def _store_or_error():
    if _store is None:
        return None, (jsonify({
            'success': False,
            'message': 'job run store not initialized',
        }), 503)
    return _store, None


# ── 通用工具 ─────────────────────────────────────────────────────────────

def _load_json(raw):
    if not raw:
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _parse_ts(value):
    """epoch 秒 / ISO8601 → epoch 秒；空值返回 None，非法也返回 None。"""
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed.timestamp()


def _available(handler) -> bool:
    """执行器是否在注册表白名单（未注入 registry 时不阻断）。"""
    if _registry is None:
        return True
    try:
        return handler in set(_registry.names())
    except Exception:  # pragma: no cover - 防御性
        logger.warning('[job-admin] registry.names() 失败', exc_info=True)
        return True


def _can_run(job) -> bool:
    return bool(job) and _available(job.get('handler')) \
        and str(job.get('status')) == 'active'


def _derive_source(run, trigger):
    """run 来源派生（spec §2.1）：不落库、不猜测。"""
    key = str(run.get('run_key') or '')
    if key.startswith('import:'):
        return 'import'
    if key.startswith('manual:'):
        return 'manual'
    if _TRIGGER_KEY_RE.match(key):
        if trigger:
            return trigger.get('trigger_type') or 'scheduled'
        return 'scheduled'
    return 'scheduled' if run.get('trigger_id') else 'manual'


def _run_brief(run):
    if not run:
        return None
    return {
        'run_id': run.get('id'),
        'status': run.get('status'),
        'attempt': run.get('attempt'),
        'created_at': run.get('created_at'),
        'finished_at': run.get('finished_at'),
        'duration_ms': run.get('duration_ms'),
    }


def _trigger_brief(trigger):
    if not trigger:
        return None
    return {
        'trigger_id': trigger.get('id'),
        'trigger_type': trigger.get('trigger_type'),
        'cron_expr': trigger.get('cron_expr'),
        'interval_seconds': trigger.get('interval_seconds'),
        'enabled': bool(trigger.get('enabled')),
        'next_run_at': trigger.get('next_run_at'),
    }


def _run_timeline(run) -> list:
    entries = []
    for key, status in (('created_at', 'pending'), ('claimed_at', 'claimed'),
                        ('started_at', 'running'),
                        ('next_retry_at', 'retrying')):
        if run.get(key):
            entries.append({'at': run.get(key), 'status': status})
    if run.get('finished_at'):
        entries.append({'at': run.get('finished_at'),
                        'status': run.get('status')})
    return entries


def _run_capabilities(run, job) -> dict:
    """IF-002 能力位：唯一来源在后端，前端只读。"""
    status = run.get('status')
    return {
        'is_terminal': status in TERMINAL_STATUSES,
        'can_cancel': status in ('pending', 'claimed', 'running'),
        'can_retry': status in ('failed', 'dead', 'cancelled'),
        'can_run': _can_run(job),
    }


def _project_run(store, run, *, job=None, trigger=None, detail=False) -> dict:
    """`task_runs` 行 → 前端消费的只读投影（IF-002 / IF-011）。"""
    if job is None:
        job = store.job_by_id(run.get('job_id')) or {}
    if trigger is None and run.get('trigger_id'):
        trigger = store.trigger_by_id(run.get('trigger_id'))
    schema = job_params_schema(job)
    params = redact_secrets(run.get('params') or {}, schema)
    data = {
        'run_id': run.get('id'),
        'job_code': job.get('code'),
        'job_name': job.get('name'),
        'status': run.get('status'),
        'attempt': run.get('attempt'),
        'max_attempts': run.get('max_attempts'),
        'progress': run.get('progress'),
        'result': _load_json(run.get('result')),
        'error': run.get('error'),
        'duration_ms': run.get('duration_ms'),
        'created_at': run.get('created_at'),
        'started_at': run.get('started_at'),
        'finished_at': run.get('finished_at'),
        'scheduled_for': run.get('scheduled_for'),
        'source': _derive_source(run, trigger),
        'trigger_type': (trigger or {}).get('trigger_type'),
        'trigger_id': run.get('trigger_id'),
        'capabilities': _run_capabilities(run, job),
        'links': {
            'detail': '/system/task-runs?run=%s' % run.get('id'),
        },
    }
    if detail:
        data['params'] = params
        data['timeline'] = _run_timeline(run)
        data['worker_id'] = run.get('worker_id')
        data['next_retry_at'] = run.get('next_retry_at')
        if job.get('code'):
            data['links']['job'] = '/system/job-schedules?job=%s' % job['code']
    else:
        excerpt = json.dumps(params, ensure_ascii=False)
        data['params_excerpt'] = excerpt if len(excerpt) <= 200 \
            else excerpt[:200] + '...'
    return data


def _project_job(job, overview=None) -> dict:
    overview = overview or {}
    schema = job_params_schema(job)
    return {
        'code': job.get('code'),
        'name': job.get('name'),
        'description': job.get('description'),
        'handler': job.get('handler'),
        'executor_type': job.get('executor_type'),
        'status': job.get('status'),
        'available': _available(job.get('handler')),
        'params_schema': schema,
        'default_params': redact_secrets(job_default_params(job), schema),
        'timeout_seconds': job.get('timeout_seconds'),
        'max_attempts': job.get('max_attempts'),
        'backoff_seconds': job.get('backoff_seconds'),
        'concurrency_group': job.get('concurrency_group'),
        'record_mode': job.get('record_mode'),
        'trigger_count': int(overview.get('trigger_count') or 0),
        'last_run': _run_brief(overview.get('last_run')),
        'next_run': _trigger_brief(overview.get('next_run')),
        'capabilities': {'can_run': _can_run(job)},
        'links': {
            'runs': '/system/task-runs?job_code=%s' % (job.get('code') or ''),
            'triggers': '/api/v2/jobs/%s/triggers' % (job.get('code') or ''),
        },
    }


def _next_runs(trigger, count=5) -> list:
    """下一次运行时间预览（与调度同源：CronParser + 进程本地时区）。"""
    next_at = trigger.get('next_run_at')
    if next_at is None:
        return []
    kind = trigger.get('trigger_type')
    if kind == 'once':
        return [float(next_at)]
    if kind == 'interval':
        step = trigger.get('interval_seconds')
        if not step:
            return []
        return [float(next_at) + float(step) * i for i in range(int(count))]
    expr = (trigger.get('cron_expr') or '').strip()
    if not expr:
        return []
    stamps = []
    base = float(next_at)
    for _ in range(int(count)):
        try:
            following = _cron.get_next(expr, datetime.fromtimestamp(base))
        except Exception:  # pragma: no cover - 防御性
            break
        if following is None:
            break
        base = following.timestamp()
        stamps.append(base)
    return stamps


def _project_trigger(store, trigger) -> dict:
    job = store.job_by_id(trigger.get('job_id')) or {}
    schema = job_params_schema(job)
    return {
        'trigger_id': trigger.get('id'),
        'job_code': job.get('code'),
        'trigger_type': trigger.get('trigger_type'),
        'cron_expr': trigger.get('cron_expr'),
        'interval_seconds': trigger.get('interval_seconds'),
        'params_override': redact_secrets(
            trigger.get('params_override') or {}, schema),
        'timezone': trigger.get('timezone'),
        'enabled': bool(trigger.get('enabled')),
        'next_run_at': trigger.get('next_run_at'),
        'last_run_at': trigger.get('last_run_at'),
        'next_runs_preview': _next_runs(trigger),
        'last_run': _run_brief(store.last_run_by_trigger(trigger.get('id'))),
        'links': {'runs': '/system/task-runs?trigger_id=%s' % trigger.get('id')},
    }


def _clean_override(job, raw):
    """校验 params_override：同一实现（sanitize_params_detailed）。"""
    if raw is None:
        return {}, None, []
    if not isinstance(raw, dict):
        return None, 'params_override 必须是 object', []
    clean, error, details = sanitize_params_detailed(raw, job_params_schema(job))
    if error:
        return None, error, details
    if len(clean) != len(raw):
        return None, '存在未声明或非法参数键', details
    return clean, None, details


def _write_audit(action, object_type, object_id, data=None, old_data=None):
    """作业管理面审计（FR-020）：单条写入，失败不阻断业务。

    调用方负责先脱敏（`redact_secrets`），本函数只做落地。
    """
    try:
        from meta.api._audit_helper import write_permission_config_audit
        write_permission_config_audit(
            action, object_type, object_id,
            data=data or {}, old_data=old_data)
    except Exception:  # pragma: no cover - 审计失败不影响主流程
        logger.warning('[job-admin] audit write failed: %s %s/%s',
                       action, object_type, object_id, exc_info=True)


# ── 作业定义（IF-007）────────────────────────────────────────────────────

@job_admin_bp.route('/api/v2/jobs', methods=['GET'])
@require_permission('job_admin')
def job_list():
    store, error = _store_or_error()
    if error:
        return error
    overview = store.overview_by_job()
    items = [_project_job(job, overview.get(int(job['id'])))
             for job in store.list_jobs()]
    return jsonify({'success': True,
                    'data': {'items': items, 'total': len(items)}})


@job_admin_bp.route('/api/v2/jobs/<code>', methods=['GET'])
@require_permission('job_admin')
def job_detail(code):
    store, error = _store_or_error()
    if error:
        return error
    job = store.job_by_code(code)
    if not job:
        return jsonify({
            'success': False, 'message': 'Unknown job: %s' % code}), 404
    overview = store.overview_by_job().get(int(job['id']))
    data = _project_job(job, overview)
    data['triggers'] = [_project_trigger(store, trigger)
                        for trigger in store.list_triggers(job['id'])]
    return jsonify({'success': True, 'data': data})


@job_admin_bp.route('/api/v2/jobs/<code>', methods=['PATCH'])
@require_permission('job_admin')
def job_update(code):
    store, error = _store_or_error()
    if error:
        return error
    job = store.job_by_code(code)
    if not job:
        return jsonify({
            'success': False, 'message': 'Unknown job: %s' % code}), 404

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'success': False, 'message': 'body 必须是 object'}), 400
    fields = {key: body[key] for key in _JOB_EDITABLE if key in body}
    if not fields:
        return jsonify({'success': False, 'message': '没有可更新字段'}), 400

    if 'status' in fields and fields['status'] not in _JOB_STATUSES:
        return jsonify({
            'success': False,
            'message': 'status 只能是 active|paused'}), 400
    for key in ('timeout_seconds', 'max_attempts', 'backoff_seconds'):
        if key in fields and not isinstance(fields[key], int):
            return jsonify({
                'success': False, 'message': '%s 必须是整数' % key}), 400
    if 'max_attempts' in fields and int(fields['max_attempts']) < 1:
        return jsonify({
            'success': False, 'message': 'max_attempts 必须 >= 1'}), 400
    if 'default_params' in fields:
        clean, err, details = _clean_override(job, fields['default_params'])
        if err:
            return jsonify({
                'success': False, 'code': 'invalid_params',
                'message': err, 'details': details}), 400
        fields['default_params'] = clean

    schema = job_params_schema(job)
    before = {}
    for key in fields:
        value = job.get(key)
        if key == 'default_params':
            value = redact_secrets(_load_json(value) or {}, schema)
        before[key] = value
    after = dict(fields)
    if 'default_params' in after:
        after['default_params'] = redact_secrets(after['default_params'], schema)

    if not store.update_job(code, fields):
        return jsonify({
            'success': False, 'message': '作业定义更新失败'}), 409
    _write_audit('UPDATE', 'job_definition', code, data=after, old_data=before)
    updated = store.job_by_code(code)
    overview = store.overview_by_job().get(int(updated['id']))
    return jsonify({'success': True, 'data': _project_job(updated, overview)})


# ── 触发器（IF-009）─────────────────────────────────────────────────────

@job_admin_bp.route('/api/v2/jobs/<code>/triggers', methods=['GET'])
@require_permission('job_admin')
def job_trigger_list(code):
    store, error = _store_or_error()
    if error:
        return error
    job = store.job_by_code(code)
    if not job:
        return jsonify({
            'success': False, 'message': 'Unknown job: %s' % code}), 404
    triggers = [_project_trigger(store, trigger)
                for trigger in store.list_triggers(job['id'])]
    return jsonify({'success': True,
                    'data': {'items': triggers, 'total': len(triggers)}})


@job_admin_bp.route('/api/v2/jobs/<code>/triggers', methods=['POST'])
@require_permission('job_admin')
def job_trigger_create(code):
    store, error = _store_or_error()
    if error:
        return error
    job = store.job_by_code(code)
    if not job:
        return jsonify({
            'success': False, 'message': 'Unknown job: %s' % code}), 404

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'success': False, 'message': 'body 必须是 object'}), 400
    trigger_type = body.get('trigger_type') or 'cron'
    if trigger_type not in TRIGGER_TYPES:
        return jsonify({
            'success': False,
            'message': 'trigger_type 只能是 cron|interval|once'}), 400

    override, err, details = _clean_override(job, body.get('params_override'))
    if err:
        return jsonify({
            'success': False, 'code': 'invalid_params',
            'message': err, 'details': details}), 400

    now = time.time()
    cron_expr = None
    interval_seconds = None
    if trigger_type == 'cron':
        cron_expr = (body.get('cron_expr') or '').strip()
        if not cron_expr:
            return jsonify({
                'success': False, 'message': 'cron_expr 必填'}), 400
        try:
            next_dt = _cron.get_next(cron_expr, datetime.fromtimestamp(now))
        except Exception:
            next_dt = None
        if next_dt is None:
            return jsonify({
                'success': False, 'code': 'invalid_cron_expr',
                'message': 'cron 表达式非法'}), 400
        next_run_at = next_dt.timestamp()
    elif trigger_type == 'interval':
        try:
            interval_seconds = int(body.get('interval_seconds') or 0)
        except (TypeError, ValueError):
            interval_seconds = 0
        if interval_seconds <= 0:
            return jsonify({
                'success': False, 'code': 'invalid_interval',
                'message': 'interval_seconds 必须为正整数'}), 400
        next_run_at = now + interval_seconds
    else:
        next_run_at = _parse_ts(body.get('run_at') or body.get('next_run_at'))
        if next_run_at is None:
            return jsonify({
                'success': False, 'code': 'invalid_schedule',
                'message': 'run_at 必填（epoch 秒或 ISO8601）'}), 400
        if next_run_at <= now:
            return jsonify({
                'success': False, 'code': 'run_at_in_past',
                'message': 'run_at 必须晚于当前时间'}), 400

    trigger_id = store.create_trigger(
        int(job['id']), trigger_type, cron_expr=cron_expr,
        interval_seconds=interval_seconds, params_override=override,
        timezone=body.get('timezone') or 'Asia/Shanghai',
        enabled=1 if body.get('enabled', True) else 0,
        next_run_at=next_run_at, now=now)
    if trigger_id is None:
        return jsonify({
            'success': False, 'message': '触发器写入失败'}), 500
    logger.info('[job-admin] trigger created job=%s type=%s id=%s',
                code, trigger_type, trigger_id)
    _write_audit('CREATE', 'job_trigger', trigger_id, data={
        'job_code': code,
        'trigger_type': trigger_type,
        'cron_expr': cron_expr,
        'interval_seconds': interval_seconds,
        'next_run_at': next_run_at,
        'enabled': bool(body.get('enabled', True)),
        'params_override': redact_secrets(
            override, job_params_schema(job)),
    })
    return jsonify({'success': True, 'data': _project_trigger(
        store, store.trigger_by_id(trigger_id))}), 201


@job_admin_bp.route('/api/v2/jobs/triggers/<int:trigger_id>', methods=['PATCH'])
@require_permission('job_admin')
def job_trigger_update(trigger_id):
    store, error = _store_or_error()
    if error:
        return error
    trigger = store.trigger_by_id(trigger_id)
    if not trigger:
        return jsonify({
            'success': False, 'message': 'Unknown trigger: %s'
            % trigger_id}), 404
    job = store.job_by_id(trigger.get('job_id')) or {}

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'success': False, 'message': 'body 必须是 object'}), 400
    fields = {key: body[key] for key in _TRIGGER_EDITABLE if key in body}
    if not fields:
        return jsonify({'success': False, 'message': '没有可更新字段'}), 400

    if 'params_override' in fields:
        clean, err, details = _clean_override(job, fields['params_override'])
        if err:
            return jsonify({
                'success': False, 'code': 'invalid_params',
                'message': err, 'details': details}), 400
        fields['params_override'] = clean

    if 'cron_expr' in fields:
        expr = (fields['cron_expr'] or '').strip()
        if not expr:
            return jsonify({
                'success': False, 'message': 'cron_expr 必填'}), 400
        try:
            next_dt = _cron.get_next(expr, datetime.fromtimestamp(time.time()))
        except Exception:
            next_dt = None
        if next_dt is None:
            return jsonify({
                'success': False, 'code': 'invalid_schedule',
                'message': 'cron 表达式非法'}), 400
        fields['cron_expr'] = expr
        fields.setdefault('next_run_at', next_dt.timestamp())

    if 'interval_seconds' in fields:
        try:
            seconds = int(fields['interval_seconds'])
        except (TypeError, ValueError):
            seconds = 0
        if seconds <= 0:
            return jsonify({
                'success': False, 'code': 'invalid_schedule',
                'message': 'interval_seconds 必须为正整数'}), 400
        fields['interval_seconds'] = seconds

    if 'next_run_at' in fields and fields['next_run_at'] is not None:
        parsed = _parse_ts(fields['next_run_at'])
        if parsed is None:
            return jsonify({
                'success': False, 'code': 'invalid_schedule',
                'message': 'next_run_at 非法'}), 400
        fields['next_run_at'] = parsed

    # 重新启用但已无下次时间：按类型补算（once 必须显式给 run_at）。
    if fields.get('enabled') and trigger.get('next_run_at') is None \
            and 'next_run_at' not in fields:
        kind = trigger.get('trigger_type')
        if kind == 'cron':
            expr = fields.get('cron_expr') or trigger.get('cron_expr') or ''
            next_dt = _cron.get_next(expr, datetime.fromtimestamp(time.time())) \
                if expr else None
            if next_dt is None:
                return jsonify({
                    'success': False, 'code': 'invalid_schedule',
                    'message': 'cron 表达式无法推算下次运行'}), 400
            fields['next_run_at'] = next_dt.timestamp()
        elif kind == 'interval':
            seconds = fields.get('interval_seconds') \
                or trigger.get('interval_seconds')
            if not seconds:
                return jsonify({
                    'success': False, 'code': 'invalid_schedule',
                    'message': '缺少 interval_seconds'}), 400
            fields['next_run_at'] = time.time() + int(seconds)
        else:
            return jsonify({
                'success': False, 'code': 'invalid_schedule',
                'message': 'once 触发器重新启用必须提供 next_run_at'}), 400

    schema = job_params_schema(job)
    before = {}
    for key in fields:
        value = trigger.get(key)
        if key == 'params_override':
            value = redact_secrets(value or {}, schema)
        before[key] = value
    after = dict(fields)
    if 'params_override' in after:
        after['params_override'] = redact_secrets(after['params_override'], schema)

    if not store.update_trigger(trigger_id, fields):
        return jsonify({
            'success': False, 'message': '触发器更新失败'}), 409
    _write_audit('UPDATE', 'job_trigger', trigger_id,
                 data=after, old_data=before)
    return jsonify({'success': True, 'data': _project_trigger(
        store, store.trigger_by_id(trigger_id))})


@job_admin_bp.route('/api/v2/jobs/triggers/<int:trigger_id>', methods=['DELETE'])
@require_permission('job_admin')
def job_trigger_delete(trigger_id):
    store, error = _store_or_error()
    if error:
        return error
    trigger = store.trigger_by_id(trigger_id)
    if not trigger or not store.delete_trigger(trigger_id):
        return jsonify({
            'success': False, 'message': 'Unknown trigger: %s'
            % trigger_id}), 404
    logger.info('[job-admin] trigger deleted id=%s', trigger_id)
    job = store.job_by_id(trigger.get('job_id')) or {}
    _write_audit('DELETE', 'job_trigger', trigger_id, data={
        'job_code': job.get('code'),
        'trigger_type': trigger.get('trigger_type'),
        'cron_expr': trigger.get('cron_expr'),
        'interval_seconds': trigger.get('interval_seconds'),
        'next_run_at': trigger.get('next_run_at'),
        'params_override': redact_secrets(
            trigger.get('params_override') or {}, job_params_schema(job)),
    })
    return jsonify({'success': True, 'data': {'id': trigger_id}})


# ── 调度器状态（IF-010）──────────────────────────────────────────────────

@job_admin_bp.route('/api/v2/jobs/dispatcher/status', methods=['GET'])
@require_permission('job_admin')
def job_dispatcher_status():
    store, error = _store_or_error()
    if error:
        return error
    if _dispatcher is not None:
        data = _dispatcher.status_snapshot()
    else:
        data = {
            'enabled': False,
            'dry_run': False,
            'running': False,
            'tick_interval': None,
            'last_tick_at': None,
            'last_summary': None,
            'backlog': {
                'pending': store.count_runs('pending'),
                'due_triggers': store.count_due_triggers(),
            },
        }
    return jsonify({'success': True, 'data': data})


# ── 执行记录（IF-003 / IF-011 / IF-012）─────────────────────────────────

@job_admin_bp.route('/api/v2/jobs/runs', methods=['GET'])
@require_permission('job_admin')
def job_runs_list():
    """执行记录列表：job_code / status / source / trigger_type / from / to。"""
    store, error = _store_or_error()
    if error:
        return error

    job_code = (request.args.get('job_code') or '').strip() or None
    status = (request.args.get('status') or '').strip() or None
    source = (request.args.get('source') or '').strip() or None
    trigger_type = (request.args.get('trigger_type') or '').strip() or None
    if status and status not in RUN_STATUSES:
        return jsonify({
            'success': False, 'message': '非法 status: %s' % status}), 400
    if source and source not in RUN_SOURCES:
        return jsonify({
            'success': False, 'message': '非法 source: %s' % source}), 400
    if trigger_type and trigger_type not in TRIGGER_TYPES:
        return jsonify({
            'success': False, 'message': '非法 trigger_type: %s'
            % trigger_type}), 400

    from_ts = _parse_ts(request.args.get('from'))
    to_ts = _parse_ts(request.args.get('to'))
    if request.args.get('from') and from_ts is None:
        return jsonify({'success': False, 'message': 'from 非法'}), 400
    if request.args.get('to') and to_ts is None:
        return jsonify({'success': False, 'message': 'to 非法'}), 400

    try:
        page = max(int(request.args.get('page', 1)), 1)
        page_size = min(max(int(request.args.get('page_size', 20)), 1), 200)
    except (TypeError, ValueError):
        return jsonify({
            'success': False, 'message': 'page/page_size 必须为整数'}), 400

    runs = store.list_runs(
        job_code=job_code, status=status, trigger_type=trigger_type,
        source=source, from_ts=from_ts, to_ts=to_ts,
        limit=page_size, offset=(page - 1) * page_size)
    total = store.count_runs_filtered(
        job_code=job_code, status=status, trigger_type=trigger_type,
        source=source, from_ts=from_ts, to_ts=to_ts)

    job_ids = {run.get('job_id') for run in runs}
    trigger_ids = {run.get('trigger_id') for run in runs if run.get('trigger_id')}
    jobs = store.job_map(job_ids)
    triggers = store.trigger_map(trigger_ids)
    items = [
        _project_run(
            store, run,
            job=jobs.get(int(run['job_id'])),
            trigger=triggers.get(int(run['trigger_id']))
            if run.get('trigger_id') else None)
        for run in runs
    ]

    return jsonify({
        'success': True,
        'data': {
            'items': items,
            'total': total,
            'page': page,
            'page_size': page_size,
            'has_more': (page - 1) * page_size + len(runs) < total,
            'meta': {
                'filters': {
                    'statuses': sorted(RUN_STATUSES),
                    'sources': sorted(RUN_SOURCES),
                    'job_codes': [
                        {'code': job['code'], 'name': job.get('name')}
                        for job in store.list_jobs()
                    ],
                },
            },
        },
    })


@job_admin_bp.route('/api/v2/jobs/runs/<int:run_id>', methods=['GET'])
@require_permission('job_admin')
def job_run_detail(run_id):
    """单次执行详情（IF-012）：含 params / timeline / capabilities。"""
    store, error = _store_or_error()
    if error:
        return error
    run = store.get_run(run_id)
    if not run:
        return jsonify({
            'success': False, 'message': 'Unknown run: %s' % run_id}), 404
    return jsonify({'success': True,
                    'data': _project_run(store, run, detail=True)})


# ── 手动运行 / 重试 / 取消 ───────────────────────────────────────────────

@job_admin_bp.route('/api/v2/jobs/<code>/run-now', methods=['POST'])
@require_permission('job_admin')
def job_run_now(code):
    store, error = _store_or_error()
    if error:
        return error
    job = store.job_by_code(code)
    if not job:
        return jsonify({
            'success': False, 'code': 'job_not_found',
            'message': 'Unknown job: %s' % code}), 404
    if str(job.get('status')) != 'active':
        return jsonify({
            'success': False, 'code': 'job_paused',
            'message': '作业已暂停：%s' % code}), 409
    if not _available(job.get('handler')):
        return jsonify({
            'success': False, 'code': 'job_unavailable',
            'message': '执行器未注册：%s' % (job.get('handler') or '')}), 409

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'success': False, 'message': 'body 必须是 object'}), 400
    params = body.get('params')
    if params is not None and not isinstance(params, dict):
        return jsonify({'success': False, 'message': 'params 必须是 object'}), 400

    merged = merge_job_params(job, params)
    schema = job_params_schema(job)
    clean, err, details = sanitize_params_detailed(merged, schema)
    if err:
        return jsonify({
            'success': False, 'code': 'invalid_params',
            'message': err, 'details': details}), 400
    if len(clean) != len(merged):
        return jsonify({
            'success': False, 'code': 'invalid_params',
            'message': '存在未声明或非法参数键', 'details': details}), 400

    now = time.time()
    scheduled_for = now
    raw_schedule = body.get('scheduled_for')
    if raw_schedule not in (None, ''):
        parsed = _parse_ts(raw_schedule)
        if parsed is None or abs(parsed - now) > SCHEDULE_TOLERANCE_SECONDS:
            return jsonify({
                'success': False, 'code': 'invalid_schedule',
                'message': 'scheduled_for 必须在当前时间 ±%ds 内'
                           % SCHEDULE_TOLERANCE_SECONDS}), 400
        scheduled_for = parsed

    run_key = 'manual:%s' % uuid.uuid4().hex
    run_id = store.create_run(job_code=code, params=clean, run_key=run_key,
                              scheduled_for=scheduled_for)
    if run_id is None:
        return jsonify({
            'success': False, 'message': 'job definition disappeared: %s'
            % code}), 409
    logger.info('[job-admin] manual run-now job=%s run=%s', code, run_id)
    _write_audit('CREATE', 'job_run', run_id, data={
        'job_code': code,
        'run_key': run_key,
        'status': 'pending',
        'scheduled_for': scheduled_for,
        'params': redact_secrets(clean, schema),
    })
    return jsonify({
        'success': True,
        'data': {'run_id': run_id, 'run_key': run_key, 'job_code': code,
                 'status': 'pending', 'scheduled_for': scheduled_for},
    })


@job_admin_bp.route('/api/v2/jobs/runs/<int:run_id>/retry', methods=['POST'])
@require_permission('job_admin')
def job_retry(run_id):
    store, error = _store_or_error()
    if error:
        return error
    run = store.get_run(run_id)
    if not run:
        return jsonify({
            'success': False, 'message': 'Unknown run: %s' % run_id}), 404
    if not store.retry(run_id):
        return jsonify({
            'success': False, 'message': 'run %s 当前状态不可重试'
            % run_id}), 409
    job = store.job_by_code(run.get('job_code')) or {}
    updated = store.get_run(run_id) or {}
    _write_audit('UPDATE', 'job_run', run_id,
                 data={'status': updated.get('status'),
                       'attempt': updated.get('attempt'),
                       'action': 'retry'},
                 old_data={'status': run.get('status'),
                           'attempt': run.get('attempt'),
                           'params': redact_secrets(
                               run.get('params') or {}, job_params_schema(job))})
    return jsonify({'success': True, 'data': {'run_id': run_id,
                                              'status': 'pending'}})


@job_admin_bp.route('/api/v2/jobs/runs/<int:run_id>/cancel', methods=['POST'])
@require_permission('job_admin')
def job_cancel(run_id):
    store, error = _store_or_error()
    if error:
        return error
    run = store.get_run(run_id)
    if not run:
        return jsonify({
            'success': False, 'message': 'Unknown run: %s' % run_id}), 404
    if not store.cancel(run_id):
        return jsonify({
            'success': False, 'message': 'run %s 当前状态不可取消'
            % run_id}), 409
    job = store.job_by_code(run.get('job_code')) or {}
    updated = store.get_run(run_id) or {}
    _write_audit('UPDATE', 'job_run', run_id,
                 data={'status': updated.get('status'),
                       'action': 'cancel'},
                 old_data={'status': run.get('status'),
                           'params': redact_secrets(
                               run.get('params') or {}, job_params_schema(job))})
    return jsonify({'success': True, 'data': {'run_id': run_id,
                                              'status': 'cancelled'}})