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
            # [V007.46 BUG-FIX] 改用 safe_connect_for_read: 加 mmap_size=0
            # 背景: diagnostics_api 高频调, 跟连接池并发访问 108MB DB 触发 disk I/O
            from meta.core.safe_connect import safe_connect_for_read
            conn_cm = safe_connect_for_read(db_path)
            conn = conn_cm.__enter__()
            try:
                # audit_log 表可能不存在, 容错
                one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
                rows = conn.execute(
                    "SELECT log_id, object_type, action, message, created_at "
                    "FROM v_audit_all "
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
                # [V007.46] 配套: conn_cm 也要 close
                try:
                    conn_cm.__exit__(None, None, None)
                except Exception:
                    pass
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

    # [v2.1] 5. interceptor warnings (写 scope / 父读 / 链 read)
    # [FIX] 主动初始化 4 类 key, 即便为空数组 (便于前端探测)
    interceptor_warnings = {
        'write_scope_warnings': [],
        'parent_read_warnings': [],
        'chain_read_warnings': [],
        'chain_instance_out_of_scope': [],
    }
    try:
        from meta.core.diagnostics import get_diagnostics as _get_diag
        diag_state = _get_diag()
        for key in list(interceptor_warnings.keys()):
            if key in diag_state:
                interceptor_warnings[key] = diag_state[key]
    except Exception:
        pass

    # [Spec 08 FR-008] 6. dim scope 统计 (wildcard/exclude 配置 + 冲突用户 + feature flags)
    dim_scope_stats = _build_dim_scope_stats()

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
            # [v2.1] interceptor 警告 (WriteScope / parent read / chain read)
            'interceptor_warnings': interceptor_warnings,
            # [Spec 08 FR-008] dim scope 统计
            'dim_scope': dim_scope_stats,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'trace_id': trace_id,
        }
    }


def _build_dim_scope_stats() -> dict:
    """[Spec 08 FR-008] 构建 dim scope 配置统计

    Returns:
        {
            'wildcard_count': int,
            'exclude_count': int,
            'wildcard_roles': [{permission_set_id, role_code, dimension_code}, ...],
            'exclude_roles': [{permission_set_id, role_code, dimension_code, excluded_ids}, ...],
            'conflict_users': [user_id, ...],
            'feature_flags': {'wildcard_enabled': bool, 'exclude_enabled': bool}
        }
    """
    result = {
        'wildcard_count': 0,
        'exclude_count': 0,
        'wildcard_roles': [],
        'exclude_roles': [],
        'conflict_users': [],
        'feature_flags': {
            'wildcard_enabled': True,
            'exclude_enabled': True,
        },
    }

    # 1. feature flags
    try:
        from meta.services.dimension_scope_engine import is_wildcard_enabled, is_exclude_enabled
        result['feature_flags'] = {
            'wildcard_enabled': is_wildcard_enabled(),
            'exclude_enabled': is_exclude_enabled(),
        }
    except ImportError:
        pass

    # 2. 查询数据库统计
    try:
        import sqlite3
        import os
        import json
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db'
        )
        if not os.path.exists(db_path):
            return result

        from meta.core.safe_connect import safe_connect_for_read
        conn_cm = safe_connect_for_read(db_path)
        conn = conn_cm.__enter__()
        try:
            # wildcard 统计 (dimension_values 含 '"*"')
            wildcard_rows = conn.execute(
                "SELECT rds.permission_set_id, r.code, rds.dimension_code "
                "FROM permission_set_dimension_scopes rds "
                "LEFT JOIN roles r ON rds.permission_set_id = r.id "
                "WHERE rds.dimension_values LIKE '%\"*\"%' "
                "AND rds.scope_mode = 'include'"
            ).fetchall()
            result['wildcard_roles'] = [
                {'permission_set_id': r[0], 'role_code': r[1] or '', 'dimension_code': r[2]}
                for r in wildcard_rows
            ]
            result['wildcard_count'] = len(wildcard_rows)

            # exclude 统计
            exclude_rows = conn.execute(
                "SELECT rds.permission_set_id, r.code, rds.dimension_code, rds.dimension_values "
                "FROM permission_set_dimension_scopes rds "
                "LEFT JOIN roles r ON rds.permission_set_id = r.id "
                "WHERE rds.scope_mode = 'exclude'"
            ).fetchall()
            result['exclude_roles'] = []
            for r in exclude_rows:
                try:
                    excluded_ids = json.loads(r[3] or '[]')
                except (json.JSONDecodeError, TypeError):
                    excluded_ids = []
                result['exclude_roles'].append({
                    'permission_set_id': r[0], 'role_code': r[1] or '',
                    'dimension_code': r[2], 'excluded_ids': excluded_ids,
                })
            result['exclude_count'] = len(exclude_rows)

            # 3. 冲突用户检测 (FR-005: 同一用户的所有角色不允许同时有 wildcard + exclude)
            # 查询同时绑定 wildcard 角色和 exclude 角色的用户
            conflict_rows = conn.execute(
                "SELECT DISTINCT ugm.user_id "
                "FROM org_members ugm "
                "JOIN org_permission_sets gr1 ON ugm.org_id = gr1.org_id "
                "JOIN permission_set_dimension_scopes rds1 ON gr1.permission_set_id = rds1.permission_set_id "
                "WHERE rds1.dimension_values LIKE '%\"*\"%' AND rds1.scope_mode = 'include' "
                "AND EXISTS ("
                "  SELECT 1 FROM org_permission_sets gr2 "
                "  JOIN permission_set_dimension_scopes rds2 ON gr2.permission_set_id = rds2.permission_set_id "
                "  WHERE gr2.org_id = ugm.org_id "
                "  AND rds2.scope_mode = 'exclude'"
                ")"
            ).fetchall()
            result['conflict_users'] = [r[0] for r in conflict_rows]

        finally:
            try:
                conn_cm.__exit__(None, None, None)
            except Exception:
                pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'[FR-008] _build_dim_scope_stats failed: {e}')

    return result


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
            return jsonify({'success': False, 'message': 'db_admin_api not available'}), 500

        if not _ensure_current_user():
            return jsonify({'success': False, 'message': 'unauthorized'}), 401
        if not _require_admin():
            return jsonify({'success': False, 'message': 'admin_required'}), 403

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
        # [Spec 08 FR-006] feature flag 端点 (登录用户可访问, 用于前端探测功能开关)
        if request.path == '/api/v2/_feature_flags' and request.method == 'GET':
            return _feature_flags_handler()
        return None  # 继续走其他路由

    def _feature_flags_handler():
        """[FR-006] GET /api/v2/_feature_flags — 返回 feature flag 状态

        前端启动时调用此端点, 决定是否显示"全维度可见"复选框和"排除已选值"复选框。
        登录用户即可访问 (不需要 admin)。
        """
        from meta.api.user_api import login_required
        from flask import g

        # 复用登录鉴权
        try:
            from meta.api.db_admin_api import _ensure_current_user
        except ImportError:
            return jsonify({'success': False, 'message': 'auth unavailable'}), 500

        if not _ensure_current_user():
            return jsonify({'success': False, 'message': 'unauthorized'}), 401

        try:
            from meta.services.dimension_scope_engine import is_wildcard_enabled, is_exclude_enabled
            flags = {
                'dim_scope_wildcard_enabled': is_wildcard_enabled(),
                'dim_scope_exclude_enabled': is_exclude_enabled(),
            }
        except ImportError:
            flags = {
                'dim_scope_wildcard_enabled': True,
                'dim_scope_exclude_enabled': True,
            }

        trace_id = TraceId.get_or_generate()
        resp = jsonify({'success': True, 'data': flags})
        resp.headers['X-Trace-Id'] = trace_id
        return resp
