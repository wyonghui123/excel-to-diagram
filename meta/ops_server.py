# -*- coding: utf-8 -*-
"""
独立运维管理服务器

双进程架构：与业务 server.py 隔离，确保业务系统故障时运维仍可用。

最小化依赖原则：
  - 仅使用 sqlite3 标准库直连数据库，不经过 DataSource/ActionExecutor
  - 独立 admin_token 认证，不依赖 JWT/用户表
  - 不依赖 meta.core.*, meta.services.*, meta.schemas.*
  - 直接查 sqlite_master 获取表结构，不依赖元模型

启动方式：
  python -m meta.ops_server

环境变量：
  OPS_ADMIN_TOKEN  - 运维管理员令牌（必须设置）
  OPS_PORT         - 端口号（默认 5001）
  OPS_DB_PATH      - 数据库路径（默认自动检测）
  OPS_DEBUG        - 调试模式（默认 False）
"""

import os
import sys
import sqlite3
import json
import time
import hashlib
import secrets
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Any, List, Optional

from flask import Flask, request, jsonify, g

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(trace_id)s] - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ops_server')


def _get_db_path() -> str:
    db_path = os.environ.get('OPS_DB_PATH')
    if db_path and os.path.exists(db_path):
        return db_path

    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'architecture.db'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db'),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    return candidates[0] if candidates else 'architecture.db'


def _get_admin_token() -> str:
    token = os.environ.get('OPS_ADMIN_TOKEN', '')
    if not token:
        token = secrets.token_hex(32)
        logger.warning("OPS_ADMIN_TOKEN not set, generated temporary token: %s", token)
    return token


def _get_db() -> sqlite3.Connection:
    db_path = _get_db_path()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ops_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        token = auth.replace('Bearer ', '') if auth.startswith('Bearer ') else ''
        if not token or token != _get_admin_token():
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def create_ops_app() -> Flask:
    app = Flask(__name__)

    @app.before_request
    def setup_trace():
        g.trace_id = request.headers.get('X-Request-Id') or str(secrets.token_hex(8))

    @app.after_request
    def add_trace_header(response):
        trace_id = getattr(g, 'trace_id', '-')
        response.headers['X-Request-Id'] = trace_id
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '')
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    @app.route('/ops/health', methods=['GET'])
    def health():
        checks = {}
        overall = 'healthy'

        try:
            conn = _get_db()
            cursor = conn.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            checks['database'] = 'ok'
        except Exception as e:
            checks['database'] = f'error: {str(e)}'
            overall = 'unhealthy'

        try:
            db_path = _get_db_path()
            db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            checks['db_size_mb'] = round(db_size / (1024 * 1024), 2)
        except:
            checks['db_size_mb'] = 'unknown'

        try:
            import psutil
            mem = psutil.virtual_memory()
            checks['memory_percent'] = mem.percent
            checks['memory_available_mb'] = round(mem.available / (1024 * 1024), 2)
            disk = psutil.disk_usage(os.path.dirname(_get_db_path()) or '.')
            checks['disk_percent'] = disk.percent
            checks['disk_free_gb'] = round(disk.free / (1024 * 1024 * 1024), 2)
            if mem.percent > 90 or disk.percent > 95:
                overall = 'warning'
        except ImportError:
            checks['system_metrics'] = 'psutil not installed'

        checks['uptime_seconds'] = int(time.time() - _start_time)
        checks['db_path'] = _get_db_path()

        return jsonify({
            'success': True,
            'status': overall,
            'checks': checks,
            'timestamp': datetime.now().isoformat(),
        })

    @app.route('/ops/api/v1/db/tables', methods=['GET'])
    @ops_auth_required
    def db_tables():
        try:
            conn = _get_db()
            cursor = conn.execute(
                "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            tables = []
            for row in cursor.fetchall():
                table_name = row['name']
                table_type = row['type']

                col_cursor = conn.execute(f"PRAGMA table_info([{table_name}])")
                columns = [{'name': c['name'], 'type': c['type'], 'notnull': bool(c['notnull']),
                            'default': c['dflt_value'], 'pk': bool(c['pk'])}
                           for c in col_cursor.fetchall()]

                idx_cursor = conn.execute(f"PRAGMA index_list([{table_name}])")
                indexes = []
                for idx in idx_cursor.fetchall():
                    idx_detail = conn.execute(f"PRAGMA index_info([{idx['name']}])")
                    idx_cols = [ic['name'] for ic in idx_detail.fetchall()]
                    indexes.append({'name': idx['name'], 'unique': bool(idx['unique']), 'columns': idx_cols})

                try:
                    count_cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM [{table_name}]")
                    row_count = count_cursor.fetchone()['cnt']
                except:
                    row_count = -1

                tables.append({
                    'name': table_name,
                    'type': table_type,
                    'columns': columns,
                    'column_count': len(columns),
                    'indexes': indexes,
                    'index_count': len(indexes),
                    'row_count': row_count,
                })

            conn.close()
            return jsonify({'success': True, 'data': tables, 'total': len(tables)})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/db/tables/<table_name>', methods=['GET'])
    @ops_auth_required
    def db_table_detail(table_name):
        try:
            conn = _get_db()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
            )
            if not cursor.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': 'Table not found'}), 404

            col_cursor = conn.execute(f"PRAGMA table_info([{table_name}])")
            columns = [{'name': c['name'], 'type': c['type'], 'notnull': bool(c['notnull']),
                        'default': c['dflt_value'], 'pk': bool(c['pk'])}
                       for c in col_cursor.fetchall()]

            idx_cursor = conn.execute(f"PRAGMA index_list([{table_name}])")
            indexes = []
            for idx in idx_cursor.fetchall():
                idx_detail = conn.execute(f"PRAGMA index_info([{idx['name']}])")
                idx_cols = [ic['name'] for ic in idx_detail.fetchall()]
                indexes.append({'name': idx['name'], 'unique': bool(idx['unique']), 'columns': idx_cols})

            fk_cursor = conn.execute(f"PRAGMA foreign_key_list([{table_name}])")
            foreign_keys = [{'from': fk['from'], 'table': fk['table'], 'to': fk['to']}
                            for fk in fk_cursor.fetchall()]

            try:
                count_cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM [{table_name}]")
                row_count = count_cursor.fetchone()['cnt']
            except:
                row_count = -1

            conn.close()
            return jsonify({
                'success': True,
                'data': {
                    'name': table_name,
                    'columns': columns,
                    'indexes': indexes,
                    'foreign_keys': foreign_keys,
                    'row_count': row_count,
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/db/status', methods=['GET'])
    @ops_auth_required
    def db_status():
        try:
            conn = _get_db()

            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]

            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

            table_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()['cnt']

            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

            conn.close()

            db_path = _get_db_path()
            db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            wal_path = db_path + '-wal'
            wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
            shm_path = db_path + '-shm'
            shm_size = os.path.getsize(shm_path) if os.path.exists(shm_path) else 0

            return jsonify({
                'success': True,
                'data': {
                    'db_path': db_path,
                    'db_size_bytes': db_size,
                    'db_size_mb': round(db_size / (1024 * 1024), 2),
                    'wal_size_bytes': wal_size,
                    'wal_size_mb': round(wal_size / (1024 * 1024), 2),
                    'shm_size_bytes': shm_size,
                    'journal_mode': journal_mode,
                    'foreign_keys_enabled': bool(foreign_keys),
                    'table_count': table_count,
                    'integrity_check': integrity,
                    'last_modified': datetime.fromtimestamp(
                        os.path.getmtime(db_path)
                    ).isoformat() if os.path.exists(db_path) else None,
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/db/migrations', methods=['GET'])
    @ops_auth_required
    def db_migrations():
        try:
            conn = _get_db()
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            )
            if not cursor.fetchone():
                conn.close()
                return jsonify({'success': True, 'data': [], 'total': 0,
                                'message': 'schema_migrations table not found'})

            cursor = conn.execute(
                "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
            )
            migrations = [{'version': row['version'], 'name': row['name'],
                           'applied_at': row['applied_at']} for row in cursor.fetchall()]
            conn.close()
            return jsonify({'success': True, 'data': migrations, 'total': len(migrations)})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/security/dashboard', methods=['GET'])
    @ops_auth_required
    def security_dashboard():
        try:
            conn = _get_db()

            login_attempts = 0
            locked_ips = 0
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) as cnt FROM audit_logs WHERE action='LOGIN_FAILED' AND created_at > ?",
                    ((datetime.now() - timedelta(hours=24)).isoformat(),)
                )
                login_attempts = cursor.fetchone()['cnt']
            except:
                pass

            active_tokens = 0
            try:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM token_blacklist")
                active_tokens = cursor.fetchone()['cnt']
            except:
                pass

            failed_audits = 0
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) as cnt FROM audit_logs WHERE status='failed'"
                )
                failed_audits = cursor.fetchone()['cnt']
            except:
                pass

            user_count = 0
            try:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM users")
                user_count = cursor.fetchone()['cnt']
            except:
                pass

            admin_count = 0
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) as cnt FROM users WHERE roles LIKE '%admin%'"
                )
                admin_count = cursor.fetchone()['cnt']
            except:
                pass

            conn.close()

            return jsonify({
                'success': True,
                'data': {
                    'login_attempts_24h': login_attempts,
                    'locked_ips': locked_ips,
                    'blacklisted_tokens': active_tokens,
                    'failed_audit_records': failed_audits,
                    'total_users': user_count,
                    'admin_users': admin_count,
                    'pbkdf2_enabled': True,
                    'jwt_expire_hours': 4,
                    'cors_whitelist_configured': bool(os.environ.get('CORS_ALLOWED_ORIGINS')),
                    'flask_debug': os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/audit/failed', methods=['GET'])
    @ops_auth_required
    def audit_failed():
        try:
            page = request.args.get('page', 1, type=int)
            page_size = request.args.get('page_size', 20, type=int)

            conn = _get_db()
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM audit_logs WHERE status='failed'"
            ).fetchone()['cnt']

            offset = (page - 1) * page_size
            cursor = conn.execute(
                "SELECT * FROM audit_logs WHERE status='failed' ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page_size, offset)
            )
            records = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return jsonify({
                'success': True,
                'data': records,
                'total': total,
                'page': page,
                'page_size': page_size,
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/audit/stats', methods=['GET'])
    @ops_auth_required
    def audit_stats():
        try:
            conn = _get_db()

            total = conn.execute("SELECT COUNT(*) as cnt FROM audit_logs").fetchone()['cnt']
            by_action = {}
            try:
                cursor = conn.execute(
                    "SELECT action, COUNT(*) as cnt FROM audit_logs GROUP BY action"
                )
                by_action = {row['action']: row['cnt'] for row in cursor.fetchall()}
            except:
                pass

            by_status = {}
            try:
                cursor = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM audit_logs GROUP BY status"
                )
                by_status = {row['status']: row['cnt'] for row in cursor.fetchall()}
            except:
                pass

            by_agent = {}
            try:
                cursor = conn.execute(
                    "SELECT agent_id, COUNT(*) as cnt FROM audit_logs WHERE agent_id IS NOT NULL GROUP BY agent_id"
                )
                by_agent = {row['agent_id']: row['cnt'] for row in cursor.fetchall()}
            except:
                pass

            conn.close()

            writer_stats = {}
            try:
                writer_db = os.environ.get('TOKEN_BLACKLIST_DB', '')
                if writer_db and os.path.exists(writer_db):
                    wconn = sqlite3.connect(writer_db)
                    wconn.row_factory = sqlite3.Row
                    wtotal = wconn.execute("SELECT COUNT(*) as cnt FROM token_blacklist").fetchone()['cnt']
                    writer_stats = {'blacklisted_tokens': wtotal}
                    wconn.close()
            except:
                pass

            return jsonify({
                'success': True,
                'data': {
                    'total_records': total,
                    'by_action': by_action,
                    'by_status': by_status,
                    'by_agent': by_agent,
                    'writer_stats': writer_stats,
                }
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/ops/api/v1/audit/query', methods=['GET'])
    @ops_auth_required
    def audit_query():
        try:
            page = request.args.get('page', 1, type=int)
            page_size = request.args.get('page_size', 20, type=int)
            object_type = request.args.get('object_type')
            action = request.args.get('action')
            trace_id = request.args.get('trace_id')
            agent_id = request.args.get('agent_id')
            start_time = request.args.get('start_time')
            end_time = request.args.get('end_time')

            conn = _get_db()
            conditions = []
            params = []

            if object_type:
                conditions.append("object_type = ?")
                params.append(object_type)
            if action:
                conditions.append("action = ?")
                params.append(action)
            if trace_id:
                conditions.append("trace_id = ?")
                params.append(trace_id)
            if agent_id:
                conditions.append("agent_id = ?")
                params.append(agent_id)
            if start_time:
                conditions.append("created_at >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("created_at <= ?")
                params.append(end_time)

            where = " AND ".join(conditions) if conditions else "1=1"

            total = conn.execute(
                f"SELECT COUNT(*) as cnt FROM audit_logs WHERE {where}", params
            ).fetchone()['cnt']

            offset = (page - 1) * page_size
            cursor = conn.execute(
                f"SELECT * FROM audit_logs WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [page_size, offset]
            )
            records = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return jsonify({
                'success': True,
                'data': records,
                'total': total,
                'page': page,
                'page_size': page_size,
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    return app


_start_time = time.time()

if __name__ == '__main__':
    app = create_ops_app()
    port = int(os.environ.get('OPS_PORT', '5001'))
    debug = os.environ.get('OPS_DEBUG', 'False').lower() == 'true'
    logger.info("Ops server starting on port %d (db=%s)", port, _get_db_path())
    logger.info("Admin token: %s...%s", _get_admin_token()[:8], _get_admin_token()[-4:])
    app.run(host='0.0.0.0', port=port, debug=debug)
