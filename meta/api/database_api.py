# -*- coding: utf-8 -*-
"""
数据库系统管理 API

提供数据库健康检查、监控指标、维护操作等端点：
- GET  /api/v1/system/database/health          健康检查
- GET  /api/v1/system/database/metrics          监控指标
- GET  /api/v1/system/database/metrics/prometheus  Prometheus 格式
- GET  /api/v1/system/database/slow-queries     慢查询列表
- POST /api/v1/system/database/vacuum           VACUUM 回收空间
- POST /api/v1/system/database/analyze          ANALYZE 更新统计
- POST /api/v1/system/database/integrity-check  完整性检查
- POST /api/v1/system/database/wal-checkpoint   手动 checkpoint
- POST /api/v1/system/database/reindex          重建索引
"""

from flask import Blueprint, request, jsonify
from meta.services.auth_middleware import login_required, is_admin
import os
import logging

logger = logging.getLogger(__name__)

database_bp = Blueprint('database', __name__, url_prefix='/api/v1/system/database')

_data_source = None
_monitor = None
_slow_query_logger = None
_prometheus_exporter = None
_checkpoint_manager = None


def init_database_services(data_source=None, monitor=None, slow_query_logger=None,
                           prometheus_exporter=None, checkpoint_manager=None):
    global _data_source, _monitor, _slow_query_logger, _prometheus_exporter, _checkpoint_manager
    _data_source = data_source
    _monitor = monitor
    _slow_query_logger = slow_query_logger
    _prometheus_exporter = prometheus_exporter
    _checkpoint_manager = checkpoint_manager


def _get_data_source():
    global _data_source
    if _data_source is None:
        from meta.core.datasource import get_data_source
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'architecture.db'
        )
        _data_source = get_data_source("sqlite", database=db_path)
    return _data_source


@database_bp.route('/health', methods=['GET'])
@login_required
def database_health():
    ds = _get_data_source()
    health = ds.health_check()
    return jsonify({"data": health})


@database_bp.route('/metrics', methods=['GET'])
@login_required
def database_metrics():
    if _monitor:
        metrics = _monitor.collect_metrics()
    else:
        ds = _get_data_source()
        # [FIX BUG-003] 兼容 sqlite ds 没有 get_pool_stats / get_write_queue_stats
        # 用 getattr 提供默认值, 避免 AttributeError → 500
        metrics = {
            "pool": getattr(ds, 'get_pool_stats', lambda: {"active": 0, "idle": 0, "max": 0})(),
            "write_queue": getattr(ds, 'get_write_queue_stats', lambda: {"depth": 0, "pending": 0})(),
            "health": ds.health_check(),
        }
    return jsonify({"data": metrics})


@database_bp.route('/metrics/prometheus', methods=['GET'])
def database_metrics_prometheus():
    if _prometheus_exporter:
        output = _prometheus_exporter.generate_latest()
    else:
        output = "# Prometheus exporter not configured\n"
    return output, 200, {'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}


@database_bp.route('/slow-queries', methods=['GET'])
@login_required
def database_slow_queries():
    if _slow_query_logger:
        limit = request.args.get('limit', 20, type=int)
        queries = _slow_query_logger.get_recent(limit=limit)
        stats = _slow_query_logger.get_stats()
        return jsonify({"data": {"queries": queries, "stats": stats}})
    return jsonify({"data": {"queries": [], "stats": {"enabled": False}}})


@database_bp.route('/vacuum', methods=['POST'])
@login_required
def database_vacuum():
    if not is_admin():
        return jsonify({"error": "您没有执行此操作的权限，需要管理员权限"}), 403
    ds = _get_data_source()
    mode = request.args.get('mode', 'dry-run')
    if mode == 'dry-run':
        db_size = 0
        if hasattr(ds, '_db_path') and ds._db_path and os.path.exists(ds._db_path):
            db_size = os.path.getsize(ds._db_path)
        try:
            freelist = ds.query("PRAGMA freelist_count")
            page_count = ds.query("PRAGMA page_count")
            free_count = freelist[0]['freelist_count'] if freelist else 0
            total_pages = page_count[0]['page_count'] if page_count else 0
            free_ratio = round(free_count / total_pages * 100, 1) if total_pages > 0 else 0
        except Exception:
            free_count = 0
            total_pages = 0
            free_ratio = 0
        return jsonify({"data": {
            "action": "VACUUM", "dry_run": True,
            "current_size_bytes": db_size,
            "page_count": total_pages,
            "freelist_count": free_count,
            "free_ratio_pct": free_ratio,
            "recommendation": "VACUUM recommended" if free_ratio > 30 else "No action needed"
        }})
    if mode == 'force':
        try:
            ds.execute("PRAGMA incremental_vacuum")
            return jsonify({"data": {"action": "INCREMENTAL_VACUUM", "status": "completed"}})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Invalid mode. Use 'dry-run' (default) or 'force'"}), 400


@database_bp.route('/analyze', methods=['POST'])
@login_required
def database_analyze():
    if not is_admin():
        return jsonify({"error": "您没有执行此操作的权限，需要管理员权限"}), 403
    ds = _get_data_source()
    try:
        ds.execute("ANALYZE")
        return jsonify({"data": {"action": "ANALYZE", "status": "completed"}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route('/integrity-check', methods=['POST'])
@login_required
def database_integrity_check():
    if not is_admin():
        return jsonify({"error": "您没有执行此操作的权限，需要管理员权限"}), 403
    ds = _get_data_source()
    try:
        result = ds.query("PRAGMA integrity_check")
        return jsonify({"data": {"action": "integrity_check", "result": result}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route('/wal-checkpoint', methods=['POST'])
@login_required
def database_wal_checkpoint():
    if not is_admin():
        return jsonify({"error": "您没有执行此操作的权限，需要管理员权限"}), 403
    mode = request.args.get('mode', 'TRUNCATE')
    if mode not in ('PASSIVE', 'TRUNCATE', 'RESTART', 'FULL'):
        return jsonify({"error": "Invalid checkpoint mode: {0}".format(mode)}), 400
    ds = _get_data_source()
    try:
        if _checkpoint_manager:
            result = _checkpoint_manager.execute_checkpoint(mode)
        else:
            ds.checkpoint(mode)
            result = {"action": "wal_checkpoint", "mode": mode, "status": "completed"}
        return jsonify({"data": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route('/reindex', methods=['POST'])
@login_required
def database_reindex():
    if not is_admin():
        return jsonify({"error": "您没有执行此操作的权限，需要管理员权限"}), 403
    ds = _get_data_source()
    try:
        tables = ds.list_tables()
        for table in tables:
            ds.execute("REINDEX {0}".format(table))
        return jsonify({"data": {"action": "REINDEX", "tables": tables, "status": "completed"}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
