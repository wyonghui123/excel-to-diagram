"""
telemetry/api.py - M14 v1.0.0 Telemetry Dashboard API

5 个端点：
- GET /api/v1/telemetry/stats          统计（p50/p95/p99 + 总数）
- GET /api/v1/telemetry/traces         最近 trace 列表
- GET /api/v1/telemetry/traces/slow    慢请求列表
- GET /api/v1/telemetry/traces/<id>    单个 trace 详情
- POST /api/v1/telemetry/configure     配置（threshold / max）
- POST /api/v1/telemetry/error         前端错误上报 (FR-003)
"""
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

telemetry_bp = Blueprint('telemetry', __name__, url_prefix='/api/v1/telemetry')


@telemetry_bp.route('/stats', methods=['GET'])
def get_stats():
    """统计信息（p50/p95/p99 + 总数）"""
    from .storage import get_storage
    stats = get_storage().get_stats()
    return jsonify(stats)


@telemetry_bp.route('/traces', methods=['GET'])
def get_traces():
    """最近 trace 列表"""
    from .storage import get_storage
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))
    traces = get_storage().get_recent(limit=limit, offset=offset)
    return jsonify({
        'count': len(traces),
        'limit': limit,
        'offset': offset,
        'traces': traces,
    })


@telemetry_bp.route('/traces/slow', methods=['GET'])
def get_slow_traces():
    """慢请求列表"""
    from .storage import get_storage
    limit = int(request.args.get('limit', 20))
    traces = get_storage().get_slow(limit=limit)
    return jsonify({
        'count': len(traces),
        'traces': traces,
    })


@telemetry_bp.route('/traces/<trace_id>', methods=['GET'])
def get_trace_detail(trace_id):
    """单个 trace 详情"""
    from .storage import get_storage
    trace = get_storage().get_by_trace_id(trace_id)
    if trace is None:
        return jsonify({'error': 'Trace not found'}), 404
    return jsonify(trace)


@telemetry_bp.route('/configure', methods=['POST'])
def configure():
    """配置（threshold / max）"""
    from .storage import get_storage
    data = request.get_json() or {}
    storage = get_storage()
    max_traces = data.get('max_traces')
    slow_threshold_ms = data.get('slow_threshold_ms')
    storage.configure(max_traces=max_traces, slow_threshold_ms=slow_threshold_ms)
    return jsonify({
        'max_traces': storage._traces.maxlen,
        'slow_threshold_ms': storage._slow_threshold_ms,
    })


# ---------------------------------------------------------------------------
# FR-003: 前端错误上报端点
# 接收 logger.js sendBeacon 上报的错误数据
# ---------------------------------------------------------------------------
import threading

# 内存存储: 最近 200 条前端错误 (线程安全)
_frontend_errors = []
_frontend_errors_lock = threading.Lock()
_MAX_FRONTEND_ERRORS = 200


@telemetry_bp.route('/error', methods=['POST'])
def report_error():
    """接收前端 sendBeacon 上报的错误 (FR-003)

    请求体 (JSON):
      level: 'error' | 'warn'
      message: string
      extra: { stack?, name? } | null
      traceId: string | null
      url: string | null
      userAgent: string | null
      ts: number (epoch ms)
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'success': False, 'message': 'Invalid JSON'}), 400

    # 基本校验
    level = data.get('level', 'error')
    message = data.get('message', '')
    if not message:
        return jsonify({'success': False, 'message': 'Missing message'}), 400

    error_record = {
        'level': level,
        'message': message[:2000],  # 截断防止超长
        'extra': data.get('extra'),
        'traceId': data.get('traceId'),
        'url': (data.get('url') or '')[:500],
        'userAgent': (data.get('userAgent') or '')[:500],
        'ts': data.get('ts'),
        'received_at': __import__('time').time(),
    }

    with _frontend_errors_lock:
        _frontend_errors.append(error_record)
        if len(_frontend_errors) > _MAX_FRONTEND_ERRORS:
            _frontend_errors.pop(0)

    # 同时写入 Python logger (便于后端日志聚合)
    logger.error('[FrontendError] %s (traceId=%s)', message[:200], data.get('traceId', '-'))

    return jsonify({'success': True}), 201


@telemetry_bp.route('/errors', methods=['GET'])
def get_errors():
    """查询前端错误列表 (FR-003)"""
    limit = min(int(request.args.get('limit', 50)), 200)
    with _frontend_errors_lock:
        errors = list(_frontend_errors[-limit:])
    return jsonify({
        'count': len(errors),
        'total': len(_frontend_errors),
        'errors': errors,
    })
