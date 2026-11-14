# -*- coding: utf-8 -*-
"""[FR-009/010/012] 运维可观测端点

在主服务内暴露 ``/ops/*``，避免运维依赖独立 ops_server 进程：

- ``GET  /ops/health``            健康汇总（DB / WAL / 告警 / 监控 / 调度器）
- ``GET  /ops/metrics``           指标快照（error_total / alert_total / 监控）
- ``GET  /ops/alerts``            告警列表（可按 status 过滤）
- ``POST /ops/alerts/<id>/replay`` 重放 dead_letter 告警
- ``POST /ops/alerts/<id>/resolve`` 手工恢复告警

认证：仅当环境变量 ``OPS_ADMIN_TOKEN`` 已配置时，写操作与告警列表要求
``Authorization: Bearer <token>`` 或 ``X-Ops-Token``；健康检查始终公开。
"""
from __future__ import annotations

import logging
import os
import time
from functools import wraps
from typing import Any, Dict

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

ops_bp = Blueprint('ops_api', __name__)


def _ops_token_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        expected = os.environ.get('OPS_ADMIN_TOKEN', '')
        if not expected:
            return fn(*args, **kwargs)
        auth = request.headers.get('Authorization', '')
        token = auth[7:] if auth.startswith('Bearer ') else request.headers.get('X-Ops-Token', '')
        if token != expected:
            return jsonify({'success': False, 'message': 'Unauthorized', 'error_code': 'unauthorized'}), 401
        return fn(*args, **kwargs)
    return wrapper


def _db_checks() -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    start = time.monotonic()
    try:
        from meta.core.datasource import get_platform_data_source
        ds = get_platform_data_source()
        cursor = ds.execute('SELECT 1')
        cursor.fetchone()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        checks['database'] = 'ok'
        checks['db_latency_ms'] = latency_ms
        if latency_ms > 3000:
            checks['db_latency'] = 'warning'
    except Exception as e:
        checks['database'] = 'error: {0}'.format(str(e)[:200])
    try:
        from meta.core.datasource import get_platform_data_source
        db_path = getattr(get_platform_data_source(), 'db_path', None) or ''
        wal_path = db_path + '-wal' if db_path else ''
        if wal_path and os.path.exists(wal_path):
            checks['wal_size_mb'] = round(os.path.getsize(wal_path) / (1024 * 1024), 2)
            if checks['wal_size_mb'] > 100:
                checks['wal_size'] = 'warning'
    except Exception as e:
        logger.debug('[Ops] WAL 大小读取失败', exc_info=True)
        checks['wal_size'] = 'unknown: {0}'.format(str(e)[:120])
    return checks


def _monitor_snapshot() -> Dict[str, Any]:
    try:
        from meta.core.monitor_runner import get_monitor_snapshot
        return get_monitor_snapshot()
    except Exception as e:
        return {'error': str(e)[:200]}


def _scheduler_snapshot() -> Dict[str, Any]:
    try:
        from meta.api.scheduler_api import get_inprocess_schedulers
        maintenance, platform = get_inprocess_schedulers()
        return {
            'maintenance': maintenance.status() if maintenance else None,
            'platform': platform.status() if platform else None,
        }
    except Exception as e:
        return {'error': str(e)[:200]}


def _health_status(checks: Dict[str, Any]) -> str:
    values = [str(v) for v in checks.values()]
    if any(v.startswith('error') for v in values):
        return 'unhealthy'
    if any('warning' in v for v in values):
        return 'warning'
    return 'healthy'


@ops_bp.route('/ops/health', methods=['GET'])
def ops_health():
    checks = _db_checks()
    try:
        from meta.core.alert_service import alert_stats
        stats = alert_stats()
        checks['alerts_open'] = stats.get('open', 0)
        checks['alert_channel'] = 'configured' if stats.get('channel_configured') else 'log_only'
        if stats.get('dead_letter'):
            checks['alerts_dead_letter'] = 'warning'
    except Exception as e:
        checks['alerts'] = 'error: {0}'.format(str(e)[:120])
    checks['monitors'] = _monitor_snapshot()
    return jsonify({
        'success': True,
        'status': _health_status(checks),
        'checks': checks,
        'schedulers': _scheduler_snapshot(),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
    })


@ops_bp.route('/ops/metrics', methods=['GET'])
def ops_metrics():
    data: Dict[str, Any] = {}
    try:
        from meta.core.observability import get_internal_metrics
        data['counters'] = get_internal_metrics()
    except Exception as e:
        data['counters'] = {'error': str(e)[:120]}
    try:
        from meta.core.alert_service import alert_stats
        data['alerts'] = alert_stats()
    except Exception as e:
        data['alerts'] = {'error': str(e)[:120]}
    data['monitors'] = _monitor_snapshot()
    return jsonify({'success': True, 'data': data})


@ops_bp.route('/ops/alerts', methods=['GET'])
@_ops_token_required
def ops_alerts():
    status = request.args.get('status')
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 500))
    except (TypeError, ValueError):
        limit = 50
    try:
        from meta.core.alert_service import list_alerts
        rows = list_alerts(status=status, limit=limit)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:200], 'error_code': 'db_error'}), 500
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@ops_bp.route('/ops/alerts/<int:alert_id>/replay', methods=['POST'])
@_ops_token_required
def ops_alert_replay(alert_id: int):
    try:
        from meta.core.alert_service import replay_alert
        ok = replay_alert(alert_id=alert_id)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:200]}), 500
    return jsonify({'success': ok, 'message': 'replayed' if ok else 'not found'})


@ops_bp.route('/ops/alerts/<int:alert_id>/resolve', methods=['POST'])
@_ops_token_required
def ops_alert_resolve(alert_id: int):
    try:
        from meta.core.alert_service import list_alerts, resolve_alert
        row = next((r for r in list_alerts(limit=1000) if r.get('id') == alert_id), None)
        ok = bool(row) and resolve_alert(fingerprint=row['fingerprint'])
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)[:200]}), 500
    return jsonify({'success': ok, 'message': 'resolved' if ok else 'not found'})