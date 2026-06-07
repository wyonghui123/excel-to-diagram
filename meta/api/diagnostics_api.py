# -*- coding: utf-8 -*-
"""
[MODULE] /_diagnostics 端点 (v3.18 M.5)
[DESCRIPTION] 给 AI Production Diagnostician 用

返回:
- health (简化 _db_health)
- recent_errors (1h 内)
- error_codes (E001-E045 + fix_hint)
- recovery_suggestions (基于 health 自动建议)

合规:
- [OK] admin 权限
- [OK] 含 trace_id
- [OK] 走 db_admin_bp (跟 _db_health 类似)
"""
import time
import json
from datetime import datetime, timedelta
from typing import Optional


# 简易实现 (不依赖 Flask app, 给 agent_test/直接调用测试用)
def build_diagnostics() -> dict:
    """
    构建 diagnostics 数据 (供 /_diagnostics 端点用)

    返回:
      {
        'success': True,
        'data': {
          'health': {...},
          'recent_errors': [...],
          'error_codes': [{code, message, fix_hint, see_also}, ...],
          'recovery_suggestions': [...],
          'generated_at': '2026-06-06T...',
        }
      }
    """
    from meta.core.trace_id import TraceId
    from meta.core.error_fix_hints import FIX_HINTS, get_codes_count
    from meta.core.db_health_monitor import get_monitor

    trace_id = TraceId.get_or_generate()

    # 1. health (简化)
    try:
        monitor = get_monitor()
        # 调 snapshot 或 status 方法
        if hasattr(monitor, 'get_status'):
            full_health = monitor.get_status()
        elif hasattr(monitor, 'snapshot'):
            snap = monitor.snapshot()
            full_health = snap.to_dict() if hasattr(snap, 'to_dict') else {'status': 'ok'}
        else:
            full_health = {'status': 'unknown', 'integrity': 'unknown'}

        # 简化: 6 关键字段
        health_simple = {
            'status': full_health.get('status', 'unknown'),
            'integrity': full_health.get('integrity', 'unknown'),
            'db_size': full_health.get('db_size', 'unknown'),
            'wal_size': full_health.get('wal_info', {}).get('wal_size', 'unknown'),
            'pool_active': full_health.get('pool_stats', {}).get('active', 0),
            'backup_count': full_health.get('backup_count', 0),
        }
    except Exception as e:
        health_simple = {'status': 'error', 'message': str(e)}

    # 2. recent_errors (1h 内, 从 audit_log 查)
    recent_errors = []
    try:
        import sqlite3
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path, timeout=5)
            try:
                # audit_log 表可能不存在, 容错
                one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
                rows = conn.execute(
                    "SELECT log_id, object_type, action, message, created_at "
                    "FROM audit_logs "
                    "WHERE created_at > ? AND (log_level = 'ERROR' OR log_level = 'WARN') "
                    "ORDER BY created_at DESC LIMIT 20",
                    (one_hour_ago,)
                ).fetchall()
                for r in rows:
                    recent_errors.append({
                        'log_id': r[0],
                        'object_type': r[1],
                        'action': r[2],
                        'message': r[3],
                        'ts': r[4],
                        'trace_id': trace_id,
                    })
            except Exception:
                # audit_logs 表可能字段不同, 静默
                pass
            finally:
                conn.close()
    except Exception:
        pass

    # 3. error_codes (跟 fix_hint 合并)
    error_codes_list = []
    for code, info in FIX_HINTS.items():
        error_codes_list.append({
            'code': code,
            'fix_hint': info['fix_hint'],
            'see_also': info['see_also'],
        })

    # 4. recovery_suggestions (基于 health)
    suggestions = []
    if health_simple.get('wal_size', '0') and 'MB' in str(health_simple['wal_size']):
        wal_mb = float(str(health_simple['wal_size']).replace('MB', '').strip() or 0)
        if wal_mb > 1.0:
            suggestions.append({
                'level': 'warn',
                'action': 'WAL > 1MB, run: python scripts/backup_db.py --check',
                'auto_fix': False,
            })
    if health_simple.get('integrity') != 'ok':
        suggestions.append({
            'level': 'critical',
            'action': 'DB integrity != ok, run: python scripts/recover_db.py',
            'auto_fix': False,
        })
    if health_simple.get('backup_count', 0) == 0:
        suggestions.append({
            'level': 'info',
            'action': 'No backup found, run: python scripts/backup_db.py',
            'auto_fix': False,
        })

    return {
        'success': True,
        'data': {
            'health': health_simple,
            'recent_errors': recent_errors,
            'error_codes': error_codes_list,
            'error_codes_count': len(error_codes_list),
            'recovery_suggestions': suggestions,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'trace_id': trace_id,
        }
    }


# Flask 路由注册
def register_diagnostics_route(app):
    """注册 GET /_diagnostics 端点 (用 before_request 拦截, 优先级最高)"""
    from meta.core.trace_id import TraceId
    from functools import wraps
    from flask import request, jsonify, g

    def _diagnostics_handler():
        # [DECORATIVE] v3.18: 跟 db_admin_bp 一致, 走 _ensure_current_user + is_admin
        # 复用现成鉴权 (v3.16 已实施, 修过 execute_action middleware 旁路)
        try:
            from meta.api.db_admin_api import _ensure_current_user, _require_admin
        except ImportError:
            return jsonify({'success': False, 'error': 'db_admin_api not available'}), 500

        if not _ensure_current_user():
            return jsonify({'success': False, 'error': 'unauthorized'}), 401
        if not _require_admin():
            return jsonify({'success': False, 'error': 'admin_required'}), 403

        # 调 build_diagnostics (返回 dict)
        trace_id = TraceId.get_or_generate()
        result = build_diagnostics()
        resp = jsonify(result)
        resp.headers['X-Trace-Id'] = trace_id
        return resp

    # [DECORATIVE] v3.18: 用 before_request 拦截 (避免被 bo_action_bp 的 /<path:action_id> wildcard 截胡)
    @app.before_request
    def _diagnostics_intercept():
        if request.path == '/api/v2/action/_diagnostics' and request.method == 'GET':
            return _diagnostics_handler()
        return None  # 继续走其他路由
