"""
telemetry/api.py - M14 v1.0.0 Telemetry Dashboard API

4 个端点：
- GET /api/v1/telemetry/stats          统计（p50/p95/p99 + 总数）
- GET /api/v1/telemetry/traces         最近 trace 列表
- GET /api/v1/telemetry/traces/slow    慢请求列表
- GET /api/v1/telemetry/traces/<id>    单个 trace 详情
- POST /api/v1/telemetry/configure     配置（threshold / max）
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
