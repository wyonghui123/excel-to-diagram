from flask import Flask, jsonify
from flask import request, g
from flask_socketio import SocketIO
import sys
import os
import io
import logging
import secrets
import socket
import time
import atexit
import signal
import sqlite3
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def is_port_in_use(port):
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def get_process_by_port(port):
    """获取占用端口的进程PID列表（仅监听端口的进程）"""
    import subprocess
    try:
        # 使用netsh命令获取监听端口的进程
        result = subprocess.run(
            ['powershell', '-Command', 
             f'(Get-NetTCPConnection -LocalPort {port} -State Listen).OwningProcess'],
            capture_output=True, text=True
        )
        pids = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
        
        # 去重
        return list(set(pids))
    except Exception as e:
        logging.warning(f"Failed to get process by port: {e}")
        return []


def kill_processes_on_port(port):
    """强制终止占用端口的进程"""
    pids = get_process_by_port(port)
    if pids:
        logging.warning(f"Found processes using port {port}: {pids}")
        for pid in pids:
            try:
                import subprocess
                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
                logging.info(f"Terminated process {pid} on port {port}")
            except Exception as e:
                logging.error(f"Failed to kill process {pid}: {e}")
        time.sleep(1)  # 等待进程完全退出
        return True
    return False


def get_pid_file_path():
    """获取PID文件路径"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, 'server.pid')


def write_pid_file():
    """写入PID文件"""
    pid_file = get_pid_file_path()
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logging.info(f"PID file written: {pid_file} (PID: {os.getpid()})")
    except Exception as e:
        logging.warning(f"Failed to write PID file: {e}")


def cleanup_pid_file():
    """清理PID文件"""
    pid_file = get_pid_file_path()
    try:
        if os.path.exists(pid_file):
            os.remove(pid_file)
            logging.info(f"PID file removed: {pid_file}")
    except Exception as e:
        logging.warning(f"Failed to remove PID file: {e}")

try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    print(f"[SERVER_DEBUG] Loading .env from: {env_path}")
    print(f"[SERVER_DEBUG] .env file exists: {os.path.exists(env_path)}")
    load_dotenv(env_path, override=True)
    print(f"[SERVER_DEBUG] JWT_SECRET_KEY after load_dotenv: {os.environ.get('JWT_SECRET_KEY', 'NOT_SET')[:20] + '...' if os.environ.get('JWT_SECRET_KEY') else 'None'}")
except ImportError as e:
    print(f"[SERVER_DEBUG] Failed to import dotenv: {e}")
    pass

from meta.api.query_api import query_bp
from meta.api.manage_api import manage_bp, init_services as init_manage_services
from meta.api.meta_api import meta_bp
from meta.api.agent_api import agent_bp
from meta.api.export_import_api import export_import_bp
from meta.api.stats_api import stats_bp
from meta.api.schema_api import schema_bp
from meta.api.notification_api import notification_bp, init_socketio
from meta.api.database_api import database_bp, init_database_services
from meta.services.log_filter_service import setup_log_filter
from meta.services.trace_service import (
    setup_trace_log_filter, get_or_create_trace_id, get_trace_id,
    TRACE_ID_HEADER
)
from meta.api.auth_api import auth_bp, init_auth_services
from meta.api.user_api import user_bp, init_user_services
from meta.api.role_api import role_bp, init_role_services
from meta.api.data_permission_api import data_perm_bp, init_data_perm_services
# from meta.api.role_data_permission_api import role_data_permission_bp  # 模块不存在，已废弃
from meta.api.user_group_api import user_group_bp, init_user_group_services
from meta.api.enum_api import enum_bp, init_enum_services
from meta.api.menu_permission_api import menu_permission_bp
from meta.api.permission_bundle_api import permission_bundle_bp
from meta.api.permission_audit_api import permission_audit_bp
from meta.api.role_menu_api import role_menu_bp
from meta.api.role_dimension_scope_api import role_dim_bp
from meta.api.management_dimension_api import management_dimension_bp, roles_bp, meta_bp as mgmt_meta_bp
from meta.api.permission_rule_api import permission_rule_bp
from meta.api.permission_sync_api import permission_sync_bp
from meta.api.owner_transfer_api import owner_transfer_bp
from meta.api.filter_variant_api import filter_variant_bp
from meta.api.audit_api import audit_bp, init_audit_services
from meta.api.object_identity_api import identity_bp, init_services as init_identity_services
from meta.api.association_api import association_bp, init_association_services
from meta.api.bo_api import bo_bp, meta_v2_bp, role_v2_bp, permission_rule_v2_bp
from meta.api.value_help_api import value_help_bp
from meta.api.special_routes_api import special_bp, init_special_services
from meta.api.annotation_routes_api import annotation_bp, init_annotation_services
from meta.api.audit_management_api import audit_mgmt_bp, init_audit_mgmt_services
from meta.api.meta_utility_routes_api import meta_util_bp
from meta.core.datasource import get_data_source
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.migration_runner import init_change_notification_tables
from meta.services.view_config_service import view_config_service
from meta.services.menu_auto_generator import menu_auto_generator
from meta.core.task_scheduler import TaskScheduler
from meta.core.task_queue_manager import QueueConfig
from meta.handlers.system_handlers import (
    DBAnalyzeHandler, DBVacuumHandler,
    DBIntegrityCheckHandler, DBCheckpointHandler
)
from meta.handlers.audit_handlers import (
    AuditLogArchiveHandler, AuditLogCleanupHandler,
    AuditFailureRetryHandler
)
from meta.handlers.import_handlers import ImportQueueHandler
from meta.api.task_api import task_api_bp, set_scheduler as set_task_scheduler
from meta.api.key_template_api import key_template_bp, set_engine as set_kt_engine
from meta.api.test_api import test_bp
from meta.api.debug_api import debug_bp
from meta.scripts.init_task_menus import init_task_menus
from meta.scripts.init_task_seed import init_task_seed_data
from meta.scripts.init_menu_permissions import init_menu_permissions

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(trace_id)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
setup_log_filter()
setup_trace_log_filter()


def _preflight_db_check(db_path):
    file_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    if file_size < 1024:
        return
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if result == "ok":
            return
        logging.getLogger(__name__).error(
            "[PREFLIGHT] DB integrity_check FAILED: %s", result
        )
    except sqlite3.DatabaseError:
        logging.getLogger(__name__).error("[PREFLIGHT] DB is corrupt")
    except Exception as e:
        logging.getLogger(__name__).error("[PREFLIGHT] DB preflight error: %s", e)

    bak_path = db_path + '.bak'
    if os.path.exists(bak_path):
        shutil.copy2(bak_path, db_path)
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if result == "ok":
                logging.getLogger(__name__).warning(
                    "[PREFLIGHT] Recovered DB from backup"
                )
                return
        except Exception as e:
            logging.getLogger(__name__).error(
                "[PREFLIGHT] Backup recovery failed: %s", e
            )
    else:
        logging.getLogger(__name__).error("[PREFLIGHT] No backup available")

    sys.exit(1)


def _preflight_db_integrity_check(db_path):
    """
    DB 完整性预检 + 自动修复（Fix 2026-06-05）

    在 _preflight_db_check 通过后调用，专门处理：
    - 清理残留的 _bak_<table>_* 表（migration_remove_updated_at 中断的产物）
    - 这些表对 PRAGMA integrity_check 是 "ok" 的，但会导致 INSERT 操作触发 FK 失败

    Returns:
        bool: 成功（True）/ 失败（False）
    """
    if not os.path.exists(db_path):
        logging.getLogger(__name__).error(f'[DBIntegrity] DB not found: {db_path}')
        return False

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        cur = conn.cursor()

        # 1. 清理残留的 _bak_<table>_* 表
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_bak_%'"
        )
        residual_baks = cur.fetchall()
        for (bak_name,) in residual_baks:
            logging.getLogger(__name__).warning(
                f'[DBIntegrity] Cleaning residual _bak table: {bak_name}'
            )
            cur.execute(f'DROP TABLE IF EXISTS {bak_name}')
        conn.commit()
        conn.close()

        if residual_baks:
            logging.getLogger(__name__).info(
                f'[DBIntegrity] Cleaned {len(residual_baks)} residual _bak tables'
            )
        else:
            logging.getLogger(__name__).debug('[DBIntegrity] No residual _bak tables')
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f'[DBIntegrity] Check failed: {e}')
        return False


def _cleanup_resources(data_source):
    logger = logging.getLogger(__name__)

    # [DECORATIVE] v3.18: 关闭时强制 TRUNCATE checkpoint（防止 WAL 残留导致损坏）
    if data_source and hasattr(data_source, '_db_path'):
        try:
            conn = sqlite3.connect(data_source._db_path, timeout=10)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            logger.info("Final WAL checkpoint TRUNCATE completed")
        except Exception as e:
            logger.warning("Final WAL checkpoint TRUNCATE failed: %s", e)

    if data_source and hasattr(data_source, '_write_queue') and data_source._write_queue:
        try:
            data_source._write_queue.flush(timeout=30)
        except Exception:
            pass
        try:
            data_source._write_queue.stop(timeout=30)
        except Exception:
            pass
        logger.info("Write queue stopped")
    if data_source and hasattr(data_source, '_pool') and data_source._pool:
        try:
            data_source._pool.shutdown()
            logger.info("Connection pool shut down")
        except Exception:
            pass


def _signal_handler(signum, frame, data_source=None):
    logging.getLogger(__name__).info("Received signal %s, shutting down...", signum)
    _cleanup_resources(data_source)
    sys.exit(0)


def create_app(db_path=None):
    """
    [WARNING] LEGACY 入口 — 推荐使用 ApplicationBuilder（spec-pre-deployment-optimization.md v1.0.0 / FR-5.8）

    新代码请使用：
        app = (ApplicationBuilder()
            .with_data_source()
            .with_yaml_schemas()
            .with_services()
            .with_interceptors()
            .with_preflight_checks()  # [FR-5.3]
            .with_telemetry()         # [FR-5.4]
            .with_auth_init()         # [FR-5.5]
            .with_menu_init()         # [FR-5.6]
            .with_bo_actions()        # [FR-5.7]
            .with_menu_auto_gen()
            .with_blueprints()
            .build())

    本函数将在 v4.0 移除。
    """
    import warnings
    warnings.warn(
        "create_app() is deprecated, use ApplicationBuilder.build() instead",
        DeprecationWarning,
        stacklevel=2
    )
    schema_dir = get_yaml_schema_dir()
    register_from_directory(schema_dir)
    view_config_service.invalidate_cache()

    if db_path is None:
        db_path = os.environ.get('SQLITE_DB_PATH')
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'architecture.db')

    _preflight_db_check(db_path)
    _preflight_db_integrity_check(db_path)  # Fix 2026-06-05: 清理 _bak_* 残留

    # [DECORATIVE] v3.18: 启动时强制 TRUNCATE checkpoint（清理残留 WAL，防止损坏）
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        logging.getLogger(__name__).info("[PREFLIGHT] WAL checkpoint TRUNCATE completed")
    except Exception as e:
        logging.getLogger(__name__).warning("[PREFLIGHT] WAL checkpoint TRUNCATE failed: %s", e)

    data_source = get_data_source("sqlite", database=db_path)

    from meta.core.db_health_monitor import init_monitor
    init_monitor(db_path)
    logging.getLogger(__name__).info("DBHealthMonitor initialized")

    init_manage_services(data_source)
    init_auth_services(data_source)
    from meta.scripts.init_auth import init_auth_system
    init_auth_system()
    from meta.scripts.migrate_system_admin import run_migration
    run_migration()
    init_user_services(data_source)
    init_role_services(data_source)
    init_data_perm_services(data_source)
    init_enum_services(data_source, db_path)
    init_identity_services(data_source)
    init_association_services(data_source)
    init_user_group_services(data_source)
    
    init_change_notification_tables(data_source)

    init_database_services(data_source=data_source)
    init_audit_services(data_source=data_source)

    from meta.migrations.enhance_audit_log_v2 import enhance_audit_log
    enhance_audit_log(db_path)

    from meta.services.async_audit_writer import async_audit_writer
    async_audit_writer.set_data_source(data_source)

    from meta.core.bo_framework import bo_framework
    from meta.core.interceptors.context_interceptor import ContextInterceptor
    from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
    from meta.core.interceptors.audit_interceptor import AuditInterceptor
    from meta.core.interceptors.lock_interceptor import LockInterceptor
    from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
    from meta.core.interceptors.query_interceptor import QueryInterceptor
    from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
    from meta.core.interceptors.permission_interceptor import PermissionInterceptor
    from meta.core.interceptors.owner_chain_interceptor import OwnerChainInterceptor
    from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor
    from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
    from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
    from meta.core.interceptors.enum_protection_interceptor import EnumProtectionInterceptor
    from meta.core.interceptors.field_policy_interceptor import FieldPolicyInterceptor
    from meta.core.interceptors.version_context_interceptor import VersionContextInterceptor
    from meta.core.interceptors.association_interceptor import AssociationInterceptor
    from meta.core.interceptors.business_log_interceptor import BusinessLogInterceptor
    from meta.core.interceptors.security_log_interceptor import SecurityLogInterceptor
    from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor

    from meta.core.interceptors.key_template_interceptor import KeyTemplateInterceptor
    from meta.core.key_template_engine import KeyTemplateEngine

    bo_framework._data_source = data_source

    from meta.services.token_version_service import token_version_service
    token_version_service.set_data_source(data_source)
    bo_framework.register_interceptor(ContextInterceptor())
    bo_framework.register_interceptor(VersionContextInterceptor())
    # [V1.1.8] OwnerChainInterceptor (P25) 在 PermissionInterceptor (P30) 之前
    #   owner chain 命中 -> 跳过 functional perm 检查
    bo_framework.register_interceptor(OwnerChainInterceptor())
    bo_framework.register_interceptor(PermissionInterceptor())
    bo_framework.register_interceptor(DataPermissionInterceptor())
    bo_framework.register_interceptor(FieldPolicyInterceptor())
    from meta.core.interceptors.constraint_validation_interceptor import ConstraintValidationInterceptor
    bo_framework.register_interceptor(ConstraintValidationInterceptor())
    bo_framework.register_interceptor(EnumProtectionInterceptor())
    bo_framework.register_interceptor(AssociationInterceptor())

    # [注册顺序修复 2026-06-07]
    # HierarchyValidationInterceptor(P45) 必须先于 KeyTemplateInterceptor(P45) 执行：
    # 先校验父级存在性 → 再生成 code，避免生成孤儿 code。
    bo_framework.register_interceptor(LockInterceptor())
    bo_framework.register_interceptor(HierarchyValidationInterceptor())

    _kt_engine = KeyTemplateEngine(data_source)
    _kt_interceptor = KeyTemplateInterceptor(engine=_kt_engine)
    bo_framework.register_interceptor(_kt_interceptor)
    set_kt_engine(_kt_engine)
    bo_framework.register_interceptor(CascadeInterceptor())
    bo_framework.register_interceptor(QueryInterceptor())
    bo_framework.register_interceptor(AuditInterceptor())
    bo_framework.register_interceptor(BusinessLogInterceptor())
    bo_framework.register_interceptor(PersistenceInterceptor())
    bo_framework.register_interceptor(SecurityLogInterceptor())
    bo_framework.register_interceptor(OwnerAutoPermissionInterceptor())
    # [H13 2026-06-15] WriteScopeInterceptor 写权限数据范围检查
    #   在 OwnerAutoPermissionInterceptor 注入 owner_id 之后执行, 用注入的 owner 判定
    #   必须在 PermissionInterceptor 之后 (functional perm 先通过才进 data scope check)
    from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor
    bo_framework.register_interceptor(WriteScopeInterceptor())
    bo_framework.register_interceptor(OperationLogInterceptor())

    # M14 v1.0.0: Install telemetry tracer on all registered interceptors
    from telemetry import install_global_tracer
    install_global_tracer(bo_framework.interceptors)

    menu_auto_generator.persist_to_db(data_source)

    db_path = os.environ.get('ARCH_DB_PATH', os.path.join(os.path.dirname(__file__), 'architecture.db'))
    init_menu_permissions(db_path)

    init_task_menus(data_source)

    init_task_seed_data(data_source)

    from meta.services.audit_service import AuditService
    _audit_svc = AuditService(data_source)
    _failed_count = len(_audit_svc.get_failed_audit_logs(page=1, page_size=1).get('data', []))
    _failed_total = _audit_svc.get_failed_audit_logs(page=1, page_size=1).get('total', 0)
    if _failed_total > 0:
        logging.getLogger(__name__).warning(
            "Found %d failed audit log records. Use GET /api/v1/audit/failed to review.",
            _failed_total
        )

    # [FR-010] 启动 audit retry worker (后台 thread, 扫 AUDIT_WRITE_FAILED 重试)
    try:
        from meta.services.audit_retry_worker import init_audit_retry_worker
        logging.getLogger(__name__).info(f"[SERVER] Initializing AuditRetryWorker with data_source: {data_source}")
        init_audit_retry_worker(data_source)
        logging.getLogger(__name__).info("[SERVER] AuditRetryWorker started successfully")
    except Exception as e:
        import traceback
        logging.getLogger(__name__).error(f"[SERVER] AuditRetryWorker init failed: {e}")
        logging.getLogger(__name__).error(traceback.format_exc())

    task_scheduler = TaskScheduler(
        data_source=data_source,
        config={'check_interval': 60}
    )

    task_scheduler.register_queue(QueueConfig(
        name='critical', priority=10, max_workers=2, timeout=600, enabled=True
    ))
    task_scheduler.register_queue(QueueConfig(
        name='ai_high', priority=20, max_workers=3, timeout=1200, enabled=True
    ))
    task_scheduler.register_queue(QueueConfig(
        name='ai_normal', priority=30, max_workers=5, timeout=1800, enabled=True
    ))
    task_scheduler.register_queue(QueueConfig(
        name='business', priority=50, max_workers=3, timeout=300, enabled=True
    ))
    task_scheduler.register_queue(QueueConfig(
        name='background', priority=100, max_workers=2, timeout=600, enabled=True
    ))

    task_scheduler.register_handler('db_analyze', DBAnalyzeHandler())
    task_scheduler.register_handler('db_vacuum', DBVacuumHandler())
    task_scheduler.register_handler('db_integrity_check', DBIntegrityCheckHandler())
    task_scheduler.register_handler('db_checkpoint', DBCheckpointHandler())
    task_scheduler.register_handler('audit_failure_retry', AuditFailureRetryHandler())
    task_scheduler.register_handler('audit_log_cleanup', AuditLogCleanupHandler())
    task_scheduler.register_handler('audit_log_archive', AuditLogArchiveHandler())
    task_scheduler.register_handler('import_queue_processor', ImportQueueHandler())

    task_scheduler.start()
    set_task_scheduler(task_scheduler)

    atexit.register(task_scheduler.stop)

    app = Flask(__name__)
    # P2 修复：Flask session 需要 secret_key（dev-login 写 session 用）
    app.secret_key = os.environ.get(
        'FLASK_SECRET_KEY',
        os.environ.get('JWT_SECRET_KEY', 'dev-secret-key-change-in-prod'),
    )

    from meta.core.startup_checks import run_startup_checks
    run_startup_checks(app)

    @app.before_request
    def _cache_request_body():
        """在最早期缓存 body, 避免 flask_socketio 包裹后无法 get_json()"""
        from flask import g
        import json as _json
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
                raw = request.get_data(cache=True, as_text=True)
                _log.info(f"[_cache_body] raw[:200]={repr(raw[:200])} ct={request.content_type}")
                if raw:
                    try:
                        g.cached_body = _json.loads(raw)
                    except Exception as e:
                        _log.warning(f"[_cache_body] json parse failed: {e}, raw={repr(raw[:200])}")
                        g.cached_body = None
                else:
                    g.cached_body = None
            else:
                g.cached_body = None
        except Exception as e:
            _log.warning(f"[_cache_body] exception: {e}")
            g.cached_body = None

    @app.before_request
    def setup_trace():
        try:
            print(f"[BEFORE_REQUEST] {request.method} {request.path}", flush=True)
        except (OSError, ValueError):
            # [FIX 2026-06-29] Windows 下后台进程 stdout 可能已关闭/管道断开,
            # 静默吞掉 print 错误, 不影响业务
            pass
        g.trace_id = get_or_create_trace_id()
        g.transaction_id = str(secrets.token_hex(16))
        g.agent_id = request.headers.get('X-Agent-Id')
        g.agent_session_id = request.headers.get('X-Agent-Session-Id')
        g.tool_call_id = request.headers.get('X-Tool-Call-Id')
        g.agent_reasoning = request.headers.get('X-Agent-Reasoning')

    @app.after_request
    def add_trace_header(response):
        trace_id = get_trace_id()
        if trace_id:
            response.headers[TRACE_ID_HEADER] = trace_id
        return response

    @app.after_request
    def add_cors_headers(response):
        allowed_origins_str = os.environ.get('CORS_ALLOWED_ORIGINS', '')
        allowed_origins = [o.strip() for o in allowed_origins_str.split(',') if o.strip()]
        request_origin = request.headers.get('Origin', '')
        is_debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

        if allowed_origins and request_origin in allowed_origins:
            response.headers['Access-Control-Allow-Origin'] = request_origin
        elif not allowed_origins and is_debug:
            response.headers['Access-Control-Allow-Origin'] = request_origin or '*'
        elif not allowed_origins and not is_debug:
            pass
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

    @app.errorhandler(500)
    def handle_500(error):
        error_msg = str(error)
        app_debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
        if app_debug:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[500 ERROR] {error_msg}")
            print(error_trace)
            return jsonify({
                'success': False,
                'error': 'INTERNAL_SERVER_ERROR',
                'message': error_msg,
                'detail': error_trace
            }), 500
        else:
            print(f"[500 ERROR] {error_msg}")
            return jsonify({
                'success': False,
                'error': 'INTERNAL_SERVER_ERROR',
                'message': 'An internal error occurred. Please contact support.'
            }), 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        error_msg = str(error)
        app_debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
        if app_debug:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[UNHANDLED ERROR] {error_msg}")
            print(error_trace)
            return jsonify({
                'success': False,
                'error': type(error).__name__,
                'message': error_msg,
                'detail': error_trace
            }), 500
        else:
            print(f"[UNHANDLED ERROR] {error_msg}")
            return jsonify({
                'success': False,
                'error': type(error).__name__,
                'message': 'An internal error occurred. Please contact support.'
            }), 500

    app.register_blueprint(query_bp)
    app.register_blueprint(annotation_bp)
    app.register_blueprint(special_bp)
    app.register_blueprint(manage_bp)
    app.register_blueprint(meta_bp)
    app.register_blueprint(agent_bp)
    app.register_blueprint(export_import_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(schema_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(role_bp)
    app.register_blueprint(data_perm_bp)
    # app.register_blueprint(role_data_permission_bp)  # 模块不存在，已废弃
    app.register_blueprint(role_menu_bp)
    app.register_blueprint(role_dim_bp)
    app.register_blueprint(management_dimension_bp)
    app.register_blueprint(roles_bp)  # /api/v1/roles/<id>/permission-rules
    app.register_blueprint(mgmt_meta_bp)  # /api/v1/meta/*
    app.register_blueprint(user_group_bp)
    app.register_blueprint(enum_bp)
    app.register_blueprint(menu_permission_bp)
    app.register_blueprint(permission_bundle_bp)
    app.register_blueprint(permission_audit_bp)
    app.register_blueprint(permission_sync_bp)
    app.register_blueprint(owner_transfer_bp)
    app.register_blueprint(permission_rule_bp)
    from meta.api.overlap_api import overlap_bp  # M3.1 FR-005
    app.register_blueprint(overlap_bp)
    from meta.api.permission_api import permission_bp  # M4.1 FR-012
    app.register_blueprint(permission_bp)
    from meta.api.intent_api import intent_bp  # M10.3.3 FR-017
    app.register_blueprint(intent_bp)
    app.register_blueprint(audit_bp, url_prefix='/api/v1/audit')
    app.register_blueprint(notification_bp)
    app.register_blueprint(database_bp)
    app.register_blueprint(filter_variant_bp)
    app.register_blueprint(identity_bp)
    app.register_blueprint(association_bp)
    app.register_blueprint(bo_bp)
    app.register_blueprint(meta_v2_bp)
    app.register_blueprint(role_v2_bp)
    app.register_blueprint(permission_rule_v2_bp)
    app.register_blueprint(value_help_bp)
    app.register_blueprint(audit_mgmt_bp)
    app.register_blueprint(meta_util_bp)
    app.register_blueprint(task_api_bp)
    app.register_blueprint(key_template_bp)
    app.register_blueprint(test_bp)
    app.register_blueprint(debug_bp)
    # v3 BO Action 统一端点
    from meta.api.bo_action_api import bo_action_bp
    app.register_blueprint(bo_action_bp)

    # [DECORATIVE] v3.16: DB 损坏预防 3 大方案端点
    from meta.api.db_admin_api import db_admin_bp
    app.register_blueprint(db_admin_bp)

    # [DECORATIVE] v3.18: /_diagnostics 端点 (M.5)
    from meta.api.diagnostics_api import register_diagnostics_route
    register_diagnostics_route(app)

    # [DECORATIVE] v3.18: /_metrics Prometheus 端点 (M.3)
    from meta.api.metrics_api import register_metrics_route
    register_metrics_route(app)

    # M10 v1.1.0: MCP Server Blueprint (JSON-RPC 2.0, 20 tools from ENTITY_SCHEMAS)
    from mcp import mcp_bp
    app.register_blueprint(mcp_bp)

    # M13 v1.4.0: Schema Dashboard Blueprint (entity summary + drift detection)
    from meta.api.schema_api import schema_dashboard_bp
    app.register_blueprint(schema_dashboard_bp)

    # M14 v1.0.0: Telemetry Dashboard Blueprint (p50/p95/p99 stats + slow traces)
    from telemetry import telemetry_bp
    app.register_blueprint(telemetry_bp)

    # v3 BO Action: 注册业务 Action 处理器
    # [FR-5.2] 提取到 meta/services/bo_action_registrations.py
    # 19 个 register 调用 → 单行 register_all_bo_actions()
    from meta.services.bo_action_registrations import register_all_bo_actions
    register_all_bo_actions()


    init_socketio(app)

    # Phase 3: 标准 CRUD 路由废弃中间件
    # 仍然有效的 v1 路径前缀 (放行) - 包括业务关系、认证、系统、特殊路由
    V1_SPECIAL_PREFIXES = {
        'relationships', 'business_object', 'annotations', 'audit', 'meta',
        'analytics', 'enums', 'enum-types', 'enum-values', 'auth',
        'import', 'export', 'import-export',
        'role-menus', 'role-dimension-scopes',
        'permission-audit', 'bo',
        'meta-actions',
        'query', 'agent', 'schema', 'system', 'stats', 'manage', 'test',
        # v1.4 P2 修复：保留这些 v1 路径（与 v2 bo object_type 冲突时不迁）
        'permissions',  # /api/v1/permissions/* (FR-012 explain/check/check_intent)
        'roles',        # /api/v1/roles/*/intents (FR-017)
        'bos',          # /api/v1/bos (FR-017 BO list)
        'overlaps',     # /api/v1/roles/*/overlaps (FR-005)
        'telemetry',    # M14: /api/v1/telemetry/* (stats/traces/configure)
    }

    # v1.4 P8 Sunset (2026-06-05): 应当 sunset 到 v2 的主表 CRUD 资源
    # 顶层 5 CRUD (GET/POST/PUT/DELETE /api/v1/<resource> 和 /<id>) 会被 410 拦截
    # 子路径 (/api/v1/<resource>/<id>/<sub> 等) 继续工作 (200)
    V1_CRUD_MIGRATION = {
        # v1_path_segment: v2_singular_object_type
        'users': 'user',
        'roles': 'role',
        'user-groups': 'user_group',
        'permission-bundles': 'permission_bundle',
        'permission-rules': 'permission_rule',
        'data-permissions': 'data_permission',
        'management-dimensions': 'management_dimension',
        'filter-variants': 'filter_variant',
        'menu-permission': 'menu_permission',
        'identity': 'identity',
        'associations': 'association',
        'notifications': 'notification',
    }

    @app.before_request
    def deprecate_v1_crud():
        """v1.4 P8 Sunset (2026-06-05): v1 主表 CRUD 路径 410, 子路径继续工作

        - V1_SPECIAL_PREFIXES 中的路径: 放行
        - V1_CRUD_MIGRATION 中的主表:
          - 顶层 CRUD (≤2 段): 410 拦截
          - 子路径 (>2 段): 放行
        - 其他 v1 路径: 410 (按 v2 名称映射)
        """
        if not request.path.startswith('/api/v1/'):
            return None

        path_parts = request.path[len('/api/v1/'):].split('/')
        if not path_parts or not path_parts[0]:
            return None

        first_segment = path_parts[0]

        # 1) 在 V1_SPECIAL_PREFIXES 中的路径: 放行
        if first_segment in V1_SPECIAL_PREFIXES:
            return None

        # 2) 在 V1_CRUD_MIGRATION 中的主表资源
        if first_segment in V1_CRUD_MIGRATION:
            # 精细化拦截: 仅顶层 CRUD 拦截
            # - 1 段: /<resource>  -> 410 (CRUD list)
            # - 2 段 + 第二段是整数: /<resource>/<id>  -> 410 (CRUD by id)
            # - 2 段 + 第二段非整数: /<resource>/<sub>  -> 200 (子路径, e.g. /users/me)
            # - >2 段: /<resource>/<id>/<sub>  -> 200 (子路径)
            non_empty_parts = [p for p in path_parts if p]
            if len(non_empty_parts) == 1:
                # 1 段: 顶层 CRUD list
                pass  # 走 410
            elif len(non_empty_parts) == 2 and non_empty_parts[1].isdigit():
                # 2 段 + 第二段是整数: 顶层 CRUD by id
                pass  # 走 410
            else:
                # 子路径: 放行让 Blueprint 处理
                return None
            v2_target = V1_CRUD_MIGRATION[first_segment]
        else:
            # 3) 其他 v1 路径: 410 拦截 (按 v2 名称映射)
            v2_target = first_segment

        # 构造 v2 路径
        v2_path = f'/api/v2/bo/{v2_target}'
        if len(path_parts) > 1 and path_parts[1]:
            v2_path += '/' + '/'.join(path_parts[1:])

        return jsonify({
            'error': 'API Moved',
            'message': f'{request.method} {request.path} has moved to {v2_path}',
            'migrated_to': v2_path,
            'migrated_at': '2026-05-14',
            'sunset_at': '2026-06-05'
        }), 410

    # v1.4 P8 Sunset: 已移除 add_v1_deprecation_headers 中间件
    # v1 豁免路径不再加 Deprecation/Sunset 响应头

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'arch-data-manage-api'})

    # M9 v3.5 P3: GraphQL 协议层 (Phase D1 POC) - 0 mutation / 0 subscription
    # 复用 bo_framework，0 业务逻辑改动，v1+v2 API 继续工作
    from meta.graphql import graphql_bp
    app.register_blueprint(graphql_bp)
    logging.getLogger(__name__).info("[M9] GraphQL endpoint registered at /graphql (POC: 1 entity, 2 queries)")

    atexit.register(lambda: _cleanup_resources(data_source))
    signal.signal(signal.SIGTERM, lambda s, f, ds=data_source: _signal_handler(s, f, ds))
    signal.signal(signal.SIGINT, lambda s, f, ds=data_source: _signal_handler(s, f, ds))

    return app


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3010))
    
    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    if not is_reloader:
        print(f"[SERVER] Checking port {port}...")
        if is_port_in_use(port):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            status_file = os.path.join(project_root, '.service_status.json')
            existing_info = ''
            if os.path.exists(status_file):
                try:
                    import json
                    with open(status_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    for svc_name, svc in data.items():
                        if svc.get('port') == port:
                            existing_info = (
                                "\n  已知信息: %s (PID=%s, since=%s)"
                                % (svc_name, svc.get('pid', '?'), svc.get('started_at', '?'))
                            )
                            break
                except Exception:
                    pass

            print("""
============================================================
[SERVER] 端口 %d 已被占用%s

多Agent并行环境下，请使用统一服务管理器:
  查看状态:  powershell -File scripts/service_manager.ps1 status
  重启服务:  powershell -File scripts/service_manager.ps1 restart

当前服务已在运行，无需重复启动。如确需重启请用上面命令。
============================================================
""" % (port, existing_info), file=sys.stderr)
            sys.exit(1)
        else:
            print(f"[SERVER] Port {port} is available")
    
    # 写入PID文件
    write_pid_file()
    
    # 注册清理函数
    atexit.register(cleanup_pid_file)
    
    # 创建Flask应用
    app = create_app()
    
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    print(f"[SERVER] Debug mode: {debug_mode}")
    print(f"[SERVER] Auto-reload: {'enabled' if debug_mode else 'disabled'}")
    print(f"[SERVER] Starting server on port {port}...")
    
    try:
        # [DECORATIVE] v3.7: 关闭 use_debugger 以支持 SSE streaming (否则 dev server streaming 会 hang)
        # debug=True 仍保留, 仅禁用 debugger 守护线程
        app.run(
            host='0.0.0.0',
            port=port,
            debug=debug_mode,
            use_reloader=False,  # FR-001: SQLite WAL并发保护 - reloader fork子进程导致DB损坏
            use_debugger=False,  # [DECORATIVE] v3.7: 关闭 Werkzeug debugger (与 send_file / SSE 冲突)
            extra_files=[],
            reloader_interval=1
        )
    finally:
        cleanup_pid_file()
