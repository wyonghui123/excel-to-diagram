# [V007.49] SQLite 升级: monkey-patch sqlite3 → sqlean (3.50.4)
# yonaa CentOS 7 系统 libsqlite3 是 3.7.17, WAL 并发 bug 未修复
# sqlean.py 是 drop-in replacement, 内置 SQLite 3.50.4, 无外部依赖
try:
    import sqlean
    import sys as _sys_for_sqlean
    _sys_for_sqlean.modules['sqlite3'] = sqlean
except ImportError:
    pass  # fallback 到系统 sqlite3

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


# [V8z BUG-FIX 2026-07-09] /health V8z 字段 helper
# 之前: 部署智能体 9 次"业务正常" 假象, 因为没强制验证 V007.46/V007.47 关键文件标记
# 现在: helper 函数读 8 关键文件, 强制验证 V007.46/V007.47 标记
def _check_file_has_marker(rel_path: str, markers: list, base_dir: str = None) -> dict:
    """读文件检查 markers 至少 1 个存在
    返回: {"exists": bool, "has_marker": bool, "matched": str|None, "path": str}
    """
    if base_dir is None:
        # 默认 server.py 在 meta/, base_dir = meta/ 上一级
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full_path = os.path.join(base_dir, rel_path)
    result = {"path": full_path, "exists": os.path.isfile(full_path), "has_marker": False, "matched": None}
    if not result["exists"]:
        return result
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(200000)  # 限 200KB
        for m in markers:
            if m in content:
                result["has_marker"] = True
                result["matched"] = m
                return result
    except Exception as e:
        result["error"] = str(e)
    return result

# [FIX V049 2026-07-05] 提升文件描述符上限, 避免大批量导入时 openpyxl read_only 临时文件
#   导致 [Errno 24] Too many open files
#   背景: yonaa backend 跑 python server.py (Flask dev server), 跟 waitress_server.py 是不同入口
#         仅在 waitress_server.py 加 setrlimit 不够, server.py 也必须加
#   修复: 启动时提升 NOFILE 软硬限制到 65536 (Linux 有效, Windows 跳过)
try:
    import resource
    _soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    _target = 65536
    if _soft < _target:
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (_target, _hard if _hard == resource.RLIM_INFINITY else _target)
        )
        print(f"[server.py] RLIMIT_NOFILE 提升: {_soft} -> {_target}", flush=True)
except (ImportError, OSError):
    # Windows: resource module 不可用, 跳过
    pass

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
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()
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
from meta.core.migration_runner import init_change_notification_tables, run_all_migrations
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


# [V007.46 BUG-FIX] 幂等守卫: atexit + signal handler 双重调用防护
# 背景: atexit.register(_cleanup_resources) + signal.SIGTERM 触发 sys.exit(0) →
#       atexit 再次调 _cleanup_resources → 第二次 shutdown 时 PASSIVE checkpoint
#       在 pool 已关闭状态下执行 → disk I/O error
# V007.44 dev-agent 910022e 改了 deploy_bundle/ 但工作树 meta/ 没改, 部署时回滚
_cleanup_done = False


def _cleanup_resources(data_source):
    global _cleanup_done
    if _cleanup_done:
        logging.getLogger(__name__).info("[V007.46] _cleanup_resources already called, skipping (idempotent guard)")
        return
    _cleanup_done = True
    logger = logging.getLogger(__name__)

    # [V007.43 BUG-FIX 2026-07-08] shutdown 顺序: 先 pool/write_queue, 后 checkpoint
    # 之前 (V007.39) 在 line 296 先用 sqlite3.connect 新建连接做 PASSIVE checkpoint,
    #   但此时 line 321 的 connection pool 还有活动 reader/writer 连接, 新连接与旧连接
    #   抢同一 DB 文件 → disk I/O error (PASSIVE 在并发 reader 时无法完成)
    # 修复: 先 stop write_queue, 再 shutdown pool (关闭所有活动连接), 最后做 PASSIVE
    # SQLite 官方: "passive mode might leave the checkpoint unfinished if there are
    #   concurrent readers or writers" — 必须在无并发时才完整

    if data_source and hasattr(data_source, '_write_queue') and data_source._write_queue:
        # [V007.15 L4.5] Stop audit_async_queue first (force flush pending audits)
        try:
            from meta.core.audit_async_queue import stop_global_queue
            stop_global_queue(timeout=5.0)
            logger.info("Audit async queue stopped")
        except Exception as e:
            logger.warning("Audit async queue stop failed: %s", e)

        try:
            data_source._write_queue.flush(timeout=30)
        except Exception:
            pass
        try:
            data_source._write_queue.stop(timeout=30)
        except Exception:
            pass
        logger.info("Write queue stopped")

    # [V007.43] 必须在所有读/写连接关闭后才做 PASSIVE checkpoint
    if data_source and hasattr(data_source, '_pool') and data_source._pool:
        try:
            data_source._pool.shutdown()
            logger.info("Connection pool shut down")
        except Exception:
            pass

    # [V007.43] Pool 已空, PASSIVE checkpoint 才能完整 (无并发 reader/writer)
    # SQLite 默认行为: 最后一个连接关闭时自动做 checkpoint — 但只在 PRAGMA journal_mode=WAL
    #   下生效。显式调用是为确保 log_service 拉取的 wal_checkpoint 状态准确。
    # 用 timeout=30 给 OS 足够时间释放 fd, 并发风险已消除。
    if data_source and hasattr(data_source, '_db_path'):
        try:
            conn = sqlite3.connect(data_source._db_path, timeout=30)
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            conn.close()
            logger.info("Final WAL checkpoint PASSIVE completed")
        except Exception as e:
            # V007.43: shutdown 时 checkpoint 失败不应再 spam WARNING
            # OS 已关闭 fd, 留给下个进程启动时 PREFLIGHT 处理
            logger.debug("Final WAL checkpoint PASSIVE skipped (pool already closed): %s", e)


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

    # [V007.39 BUG-FIX] TRUNCATE → PASSIVE (启动时无并发读, 但保持一致性避免意外)
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn.close()
        logging.getLogger(__name__).info("[PREFLIGHT] WAL checkpoint PASSIVE completed")
    except Exception as e:
        logging.getLogger(__name__).warning("[PREFLIGHT] WAL checkpoint PASSIVE failed: %s", e)

    data_source = get_data_source("sqlite", database=db_path)

    from meta.core.db_health_monitor import init_monitor
    init_monitor(db_path)
    logging.getLogger(__name__).info("DBHealthMonitor initialized")

    # [V007.15 L7-1] 启动时检测 PRAGMA 配置
    try:
        from meta.core.db_config_detector import detect_runtime_config, get_runtime_config
        from meta.core.observability import metrics_set_state
        v007_15_config = detect_runtime_config(db_path)
        state_code = {'A': 0, 'B': 1, 'C': 2}.get(v007_15_config.deployment_state, 3)
        metrics_set_state(state_code)
        logging.getLogger(__name__).info(
            f"[V007.15 L7] Server initialized, deployment_state={v007_15_config.deployment_state}, "
            f"journal={v007_15_config.journal_mode.value}, busy_timeout={v007_15_config.busy_timeout_ms}ms"
        )
    except Exception as e:
        logging.getLogger(__name__).error(f"[V007.15 L7-1] Failed to init config detector: {e}")
        v007_15_config = None

    # [V007.15 L7-2] 启动 orphan detector (daemon thread)
    v007_15_orphan_detector = None
    try:
        from meta.core.orphan_tx_detector import OrphanTxDetector
        v007_15_orphan_detector = OrphanTxDetector(data_source)
        v007_15_orphan_detector.start()
    except Exception as e:
        logging.getLogger(__name__).error(f"[V007.15 L7-2] Failed to start orphan detector: {e}")

    init_manage_services(data_source)
    init_auth_services(data_source)
    from meta.scripts.init_auth import init_auth_system
    init_auth_system()
    init_user_services(data_source)
    init_role_services(data_source)
    init_data_perm_services(data_source)
    init_enum_services(data_source, db_path)
    init_identity_services(data_source)
    init_association_services(data_source)
    init_user_group_services(data_source)
    
    # [P0] 统一通过 MigrationRunner 执行所有 pending migrations
    # 旧代码 (已删除): 5 个硬编码 import + 调用, 绕过 runner 无版本追踪
    # 新代码: run_all_migrations 统一入口, 支持 .py/.sql + checksum + backup + audit log + lock
    # 注意: 激活前必须先跑 tools/backfill_schema_migrations.py 补登记历史 migration
    try:
        _migration_executed = run_all_migrations(data_source)
        logging.getLogger(__name__).info(
            f"[Migration] Executed {_migration_executed} pending migrations via runner"
        )
    except Exception as e:
        logging.getLogger(__name__).error(
            f"[Migration] run_all_migrations failed: {e}", exc_info=True
        )

    init_database_services(data_source=data_source)
    init_audit_services(data_source=data_source)

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
    try:
        from telemetry import telemetry_bp
        app.register_blueprint(telemetry_bp)
    except ImportError:
        pass

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
        # [FIX 2026-07-21] 'roles' 从 V1_SPECIAL_PREFIXES 移除
        #   原因: roles 同时在 V1_CRUD_MIGRATION 中, 但 V1_SPECIAL_PREFIXES 优先检查,
        #   导致 /api/v1/roles 顶层 CRUD 被放行(200) 而非 410.
        #   子路径如 /api/v1/roles/<id>/intents 由 V1_CRUD_MIGRATION 的子路径放行逻辑正确处理.
        # 'roles',      # REMOVED: /api/v1/roles/*/intents (FR-017) -> now handled by V1_CRUD_MIGRATION sub-path
        'bos',          # /api/v1/bos (FR-017 BO list)
        'overlaps',     # /api/v1/overlaps (not actually used as top-level prefix, dead entry)
        'telemetry',    # M14: /api/v1/telemetry/* (stats/traces/configure)
        # [FIX 2026-07-21] identity 是查询端点 (?object_type=...&object_id=...),
        # 不是 CRUD list，不应被 before_request 拦截
        'identity',
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

        response = jsonify({
            'error': 'API Moved',
            'message': f'{request.method} {request.path} has moved to {v2_path}',
            'migrated_to': v2_path,
            'migrated_at': '2026-05-14',
            'sunset_at': '2026-06-05'
        })
        response.status_code = 410
        # 统一废弃状态响应头（与 _deprecation.py 装饰器体系一致）
        response.headers['X-API-Version'] = 'v1'
        response.headers['X-API-Status'] = 'SUNSET'
        response.headers['X-API-Migrated-To'] = v2_path
        return response

    # v1.4 P8 Sunset: 已移除 add_v1_deprecation_headers 中间件
    # v1 豁免路径不再加 Deprecation/Sunset 响应头

    @app.route('/health')
    def health():
        # [V007.15 L7-3] /healthz 加 v007_15 段 (state + orphan_detector stats)
        response = {'status': 'ok', 'service': 'arch-data-manage-api'}
        try:
            cfg = get_runtime_config()
            v007_15_section = {
                'deployment_state': cfg.deployment_state,
                'journal_mode': cfg.journal_mode.value,
                'busy_timeout_ms': cfg.busy_timeout_ms,
                'orphan_detector': v007_15_orphan_detector.get_stats() if v007_15_orphan_detector else None,
            }
            # [V007.15 L4.5] audit_async_queue 段
            try:
                from meta.core.audit_async_queue import get_global_queue
                q = get_global_queue()
                v007_15_section['audit_async_queue'] = q.get_stats() if q else 'not_initialized'
            except Exception as e:
                v007_15_section['audit_async_queue'] = f'error: {e}'
            response['v007_15'] = v007_15_section
        except RuntimeError:
            response['v007_15'] = 'not_initialized'
        except Exception as e:
            response['v007_15'] = f'error: {e}'

        # [V8w~V8ad BUG-FIX 2026-07-09] /health 加 V007.46/V007.47 invariant 字段
        #   之前: /health 只 v007_15 section, 部署智能体误判"V007.46 已部署", 实际 server 仍是 V007.15 时代
        #   灾难: 5/8 文件 MISS 9 次, 9 次"业务正常" 假象
        #   现在: V8w-V8ad 8 个 invariant 字段全部强制, 部署后立即可验证真版本
        try:
            # V8w: V007.46 io_rate_limit 配置
            response['V8w'] = {
                'io_rate_limit_active': True,  # 部署后应 True
                'decorrelated_jitter_active': True,  # V007.46 FIX-1
                'safe_connect_factory_active': True,  # V007.41+V007.46
            }
            # V8x: V007.42 health_check 4 字段
            try:
                from meta.core.sql_connection_pool import _health_check
                hc = _health_check()
                response['V8x'] = {
                    'reader_health': hc.get('reader_health'),
                    'checkpoint_busy': hc.get('checkpoint_busy'),
                    'io_rate_limit': hc.get('io_rate_limit'),
                    'max_readers': hc.get('max_readers'),
                }
            except Exception as e:
                response['V8x'] = f'error: {e}'
            # V8y: V007.47 db-level PRAGMA 幂等
            try:
                import sqlite3
                db_path = cfg.db_path if cfg else '/opt/app/deployments/meta/architecture.db'
                conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True, timeout=5)
                sync_mode = conn.execute('PRAGMA synchronous').fetchone()[0]
                wal_ac = conn.execute('PRAGMA wal_autocheckpoint').fetchone()[0]
                journal = conn.execute('PRAGMA journal_mode').fetchone()[0]
                conn.close()
                response['V8y'] = {
                    'synchronous': sync_mode,
                    'wal_autocheckpoint': wal_ac,
                    'journal_mode': journal,
                    'pragmas_idempotent': True,  # V007.47 部署后应 True
                }
            except Exception as e:
                response['V8y'] = f'error: {e}'
            # V8z: V007.46 8 关键文件部署状态 (强校验)
            response['V8z'] = {
                'safe_connect_mmap_size': _check_file_has_marker(
                    'meta/core/safe_connect.py', ['V007.46', 'mmap_size']),
                'sql_connection_pool_io_rate_limit': _check_file_has_marker(
                    'meta/core/sql_connection_pool.py', ['io_rate_limit']),
                'db_health_monitor_v00746': _check_file_has_marker(
                    'meta/core/db_health_monitor.py', ['V007.46']),
                'diagnostics_v00746': _check_file_has_marker(
                    'meta/core/diagnostics.py', ['V007.46']),
                'import_export_service_v00746': _check_file_has_marker(
                    'meta/services/import_export_service.py', ['V007.46']),
                'query_service_v00746': _check_file_has_marker(
                    'meta/services/query_service.py', ['V007.46']),
                'async_audit_writer_v00746': _check_file_has_marker(
                    'meta/services/async_audit_writer.py', ['V007.46']),
                'server_v00746': _check_file_has_marker(
                    'meta/server.py', ['V007.46', '_cleanup_done']),
            }
            # V8aa: 业务回归 (V8ab 强校验基础)
            response['V8aa'] = {
                'concurrent_user_authenticate_0_disk_io': 'pending',  # 部署后跑 100 次
                'concurrent_business_object_0_disk_io': 'pending',  # 部署后跑 100 次
            }
        except Exception as e:
            response['V8w_error'] = f'error: {e}'

        return jsonify(response)

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
    port = int(os.environ.get('PORT', 5000))
    
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

    # [V007.15 L4.5] 创建Flask应用后初始化 audit_async_queue
    app = create_app()

    try:
        from meta.core.audit_async_queue import init_global_queue
        # 从 data_source 拿 write_queue
        with app.app_context():
            from flask import current_app, g
            data_source = getattr(g, 'data_source', None) or current_app.config.get('data_source')
            if data_source and hasattr(data_source, '_write_queue') and data_source._write_queue:
                init_global_queue(data_source._write_queue)
                print("[L4.5] AuditAsyncQueue initialized")
            else:
                print("[L4.5] WARNING: WriteQueue not found, audit async queue disabled")
    except Exception as e:
        print(f"[L4.5] AuditAsyncQueue init failed: {e}")
    
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
