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
from meta.api.permission_set_api import permission_set_bp, init_permission_set_services
from meta.api.data_permission_api import data_perm_bp, init_data_perm_services
# from meta.api.role_data_permission_api import role_data_permission_bp  # 模块不存在，已废弃
from meta.api.org_api import org_bp, init_org_services
from meta.api.org_function_api import org_function_bp, init_org_function_services
from meta.api.enum_api import enum_bp, init_enum_services
from meta.api.menu_permission_api import menu_permission_bp
from meta.api.permission_bundle_api import permission_bundle_bp
from meta.api.permission_audit_api import permission_audit_bp
from meta.api.permission_set_menu_api import permission_set_menu_bp
from meta.api.permission_set_dimension_scope_api import role_dim_bp as ps_dim_scope_bp
# file's blueprint var is still role_dim_bp (Plan B kept for compat)
from meta.api.permission_dimension_api import permission_dimension_bp, roles_bp, meta_bp as mgmt_meta_bp, ps_matrix_bp
from meta.api.permission_rule_api import permission_rule_bp
from meta.api.permission_sync_api import permission_sync_bp
from meta.api.owner_transfer_api import owner_transfer_bp
from meta.api.filter_variant_api import filter_variant_bp
from meta.api.audit_api import audit_bp, init_audit_services
from meta.api.object_identity_api import identity_bp, init_services as init_identity_services
from meta.api.association_api import association_bp, init_association_services
from meta.api.bo_api import bo_bp, meta_v2_bp, role_v2_bp, permission_rule_v2_bp, permission_set_v2_bp
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
from meta.handlers.platform_handlers import PlatformTickHandler
from meta.api.task_api import task_api_bp, set_scheduler as set_task_scheduler
from meta.api.scheduler_api import (
    scheduler_bp, set_inprocess_schedulers,
)
from meta.api.workflow_api import workflow_bp, set_workflow_scheduler
from meta.api.task_inbox_api import task_inbox_bp
from meta.api.task_decision_api import task_decision_bp   # [B3 2026-10-03] 审批决策提交入口
from meta.core.platform_modules import is_module_enabled   # [roadmap v1.32.0 §6.2.4] 平台模块部署级启停
from meta.api.key_template_api import key_template_bp, set_engine as set_kt_engine
from meta.api.test_api import test_bp
from meta.api.debug_api import debug_bp
from meta.scripts.init_task_menus import init_task_menus
from meta.scripts.init_task_seed import init_task_seed_data
from meta.scripts.init_region_seed import init_region_seed_data
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

    # [§6.14.2] 先停跨应用事件投递线程，再做多库关闭编排 —— 否则在途投递可能与
    # 写队列关闭交叉（事件投递本身也写库）。
    try:
        from meta.core.event_outbox import stop_event_dispatcher
        stop_event_dispatcher()
    except Exception as e:
        logger.warning("Event dispatcher shutdown failed: %s", e)

    # [§6.5.3 改动 4] 多库关闭编排：遍历**所有活跃数据源**（平台库 + 各应用库）
    # 逐个 flush 写队列 → stop 写线程 → 最终 WAL checkpoint → 释放连接池。
    # 改造前只处理传入的单个 data_source，多库场景下其余库的写队列不会被
    # flush/stop（写线程 daemon=True）⇒ 在途写入静默丢失。
    try:
        from meta.core.datasource import shutdown_all_data_sources

        summary = shutdown_all_data_sources(timeout=30.0, primary=data_source)
        logger.info(
            "Data sources shut down: %d (errors=%d)",
            summary["total"], len(summary["errors"]),
        )
        for item in summary["errors"]:
            logger.warning("Shutdown issue on %s: %s", item["db_path"], item["error"])
        return
    except Exception as e:
        logger.warning("Orchestrated shutdown failed, falling back to single-source cleanup: %s", e)

    # 兜底：编排不可用时，退回到只清理主数据源（原行为）
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

    # [L0 视图依赖守卫] 依赖表缺失的视图从注册表摘除 ⇒ 请求得到确定的 4xx，
    #   而不是 SELECT 时 no such table 的 500。正常部署零动作。
    try:
        from meta.core.view_dependency_guard import prune_unusable_views
        _pruned_views = prune_unusable_views(data_source)
        if _pruned_views:
            logging.getLogger(__name__).warning(
                "[PREFLIGHT] Unusable views pruned: %s", _pruned_views
            )
    except Exception as e:
        logging.getLogger(__name__).error(
            "[PREFLIGHT] view dependency guard failed (non-fatal): %s", e
        )

    # [P5 补充 2026-07-26] 启动时检测 SQLite 运行时配置 (WAL/busy_timeout/...)
    # 必须在任何 layer 调用 get_runtime_config() 之前完成
    # 解决: DEMO 用户创建 product 时 RuntimeError: DB config not detected yet
    try:
        from meta.core.db_config_detector import detect_runtime_config
        detect_runtime_config(db_path)
        logging.getLogger(__name__).info(
            "[PREFLIGHT] detect_runtime_config() called for db_path=%s", db_path
        )
    except Exception as e:
        logging.getLogger(__name__).warning(
            "[PREFLIGHT] detect_runtime_config failed (non-fatal): %s", e
        )

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
    init_permission_set_services(data_source)
    init_data_perm_services(data_source)
    init_enum_services(data_source, db_path)
    init_identity_services(data_source)
    init_association_services(data_source)
    init_org_services(data_source)
    init_org_function_services(data_source)
    
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
    # [Spec 19 M1 2026-09-05] 组织管理守卫(P26)：组织移动守卫 + 敏感关联门禁（权限集绑定/职位分配仅限全局管理员）
    from meta.core.interceptors.org_admin_guard_interceptor import OrgAdminGuardInterceptor
    bo_framework.register_interceptor(OrgAdminGuardInterceptor())
    bo_framework.register_interceptor(PermissionInterceptor())
    bo_framework.register_interceptor(DataPermissionInterceptor())
    bo_framework.register_interceptor(FieldPolicyInterceptor())
    from meta.core.interceptors.constraint_validation_interceptor import ConstraintValidationInterceptor
    bo_framework.register_interceptor(ConstraintValidationInterceptor())
    # [F3 2026-10-20 / 补注册 2026-10-20] 镜像行守卫（P43）：party_relation 无序去重。
    #   与 app_builder.with_interceptors() 同位补齐 —— 此前只注册在新 builder 路径，
    #   而 waitress_server.py 走本函数（create_app）⇒ 运行时守卫缺失。
    #   [模块门控] party 轴在 BIP 应用架构管理部署下不适用（org 无 BU/LE 职能），
    #   该部署设 DISABLED_PLATFORM_MODULES=party 后不注册。
    if is_module_enabled('party'):
        from meta.core.interceptors.party_relation_guard_interceptor import PartyRelationGuardInterceptor
        bo_framework.register_interceptor(PartyRelationGuardInterceptor())
        # [internal_mark 派生 2026-10-22] 与 app_builder.with_interceptors() 同位登记；
        #   落 ComputedFieldHandler 以覆盖 manage_api / Excel 导入等绕过拦截器链的写路径。
        from meta.core.consistency_guard import ComputedFieldHandler
        from meta.services.party_relation_guard_service import derive_internal_mark_hook
        ComputedFieldHandler.register_hook('party_relation', derive_internal_mark_hook)
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
    # [2026-10-20] org → party 内部表示镜像（P94）：排队在 PersistenceInterceptor(P95)
    #   之后执行（after 钩子按 priority 降序），覆盖 org 更名 / 状态变更。
    #   职能变更走 OrgFunctionService 直连路径，不在本拦截器覆盖范围（见该服务注释）。
    #   与 app_builder.with_interceptors() 同位登记 —— 两条启动路径缺一会静默失效。
    #   [模块门控] 同 P43：party 模块关闭（BIP 应用架构管理部署）时不注册，避免每次
    #   org 保存空跑一次存在性检查。
    if is_module_enabled('party'):
        from meta.core.interceptors.org_party_mirror_interceptor import OrgPartyMirrorInterceptor
        bo_framework.register_interceptor(OrgPartyMirrorInterceptor())
    # [多产品平台 §6.14.2] 跨应用事件：业务写成功后在同一事务内写 outbox。
    # 无事件契约时 should_execute 直接短路 → legacy 零影响。
    from meta.core.interceptors.outbox_interceptor import OutboxInterceptor
    bo_framework.register_interceptor(OutboxInterceptor())
    # [D3 2026-10-03] 反向事件：BO 状态变更 → bo.status_changed（保留名，专用拦截器）
    from meta.core.interceptors.bo_status_interceptor import BoStatusInterceptor
    bo_framework.register_interceptor(BoStatusInterceptor())
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

    # 与主链路同一解析入口（SQLITE_DB_PATH > ARCH_DB_PATH > 仓库内）——
    # 此前只认 ARCH_DB_PATH, 设 SQLITE_DB_PATH 的隔离实例仍会写回仓库内主库
    from meta.core.db_path import get_meta_db_path
    init_menu_permissions(get_meta_db_path())

    # [roadmap v1.32.0 §6.2.4] 任务菜单与 task blueprint 同门：
    # 禁用时不写种子 ⇒ 前端侧栏无数据（menus 表无该 menu_code）。
    # 注意：不写种子不会删除已存在的菜单 —— 已跑过种子的实例若要彻底隐藏，
    # 需一次性执行 UPDATE menus SET show_in_sidebar=0 WHERE menu_code LIKE 'task%'。
    if is_module_enabled('tasks'):
        init_task_menus(data_source)
    else:
        logging.getLogger(__name__).info("[PlatformModules] tasks 已禁用 → 跳过任务菜单种子初始化")

    init_task_seed_data(data_source)

    init_region_seed_data(data_source)

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

    # [P1 2026-10-13] cron 作业与遗留任务调度器解耦（替换路径 第 7 / 1 / 3 项）。
    #
    # 背景: 遗留 TaskScheduler 原本挂 9 个 handler，且全部只是「借调度器跑 cron」：
    #         - 8 个运维作业（DB 维护 / 审计运维 / 导入队列）—— 与任务模型无关，
    #           却被迫依赖 scheduled_tasks / task_queues / task_executions 表；
    #         - 1 个 platform_tick —— A5 平台心跳（派工 / 回收 / SLA 扫描 / 对账）。
    #       「用任务体系背运维债」是替换遗留任务体系的隐性阻塞：删任务域表会
    #       连带停掉 DB 维护与审计归档。
    #
    # 处置: 两类作业各挂独立的进程内调度器（调度配置内嵌代码，不落库）：
    #         - 8 个运维作业 → MaintenanceScheduler（第 7 项）
    #         - platform_tick  → PlatformScheduler（第 1 项，任务域）
    #       handler 实例在此处创建一次。第 3 项已把 scheduled_tasks 的历史行清理
    #       （init_task_seed 不再播种、改为清理迁移作业行）；遗留 TaskScheduler
    #       不再承载任何 cron 作业，仅保留队列与手工触发基础设施。
    #
    # 进程内调度器是**唯一** cron 路径 —— 没有「退回遗留调度器」的回滚分支。
    # 暂停开关: CRON_JOBS_ENABLED=0 暂停全部 cron 作业（两个进程内调度器都不启动）。
    #           该开关不依赖任何数据表，故历史行清理后仍可作「快速禁用」安全网。
    _cron_enabled = os.environ.get(
        'CRON_JOBS_ENABLED', '1') not in ('0', 'false', 'False')

    if _cron_enabled:
        from meta.core.maintenance_scheduler import MaintenanceScheduler
        from meta.core.platform_scheduler import PlatformScheduler
        from meta.core.workflow_schedule_scheduler import WorkflowScheduleScheduler

        _maintenance_handlers = {
            'db_analyze': DBAnalyzeHandler(),
            'db_vacuum': DBVacuumHandler(),
            'db_integrity_check': DBIntegrityCheckHandler(),
            'db_checkpoint': DBCheckpointHandler(),
            'audit_failure_retry': AuditFailureRetryHandler(),
            'audit_log_cleanup': AuditLogCleanupHandler(),
            'audit_log_archive': AuditLogArchiveHandler(),
            'import_queue_processor': ImportQueueHandler(),
        }

        maintenance_scheduler = MaintenanceScheduler(
            data_source=data_source,
            config={'check_interval': 60},
        )
        for _code, _handler in _maintenance_handlers.items():
            maintenance_scheduler.register_handler(_code, _handler)
        maintenance_scheduler.start()
        atexit.register(maintenance_scheduler.stop)

        platform_scheduler = PlatformScheduler(
            data_source=data_source,
            config={'check_interval': 60},
        )
        platform_scheduler.register_handler('platform_tick', PlatformTickHandler())
        platform_scheduler.start()
        atexit.register(platform_scheduler.stop)

        # [P1 2026-10-13] 向运维端点暴露两个进程内调度器（只读状态 + 按需触发）
        set_inprocess_schedulers(maintenance_scheduler, platform_scheduler)

        # [C 组编排完整 2026-10-14] 第三类作业：workflow 定时触发 —— 作业集从
        #   已发布定义表派生（trigger_kind='schedule'），与上面两个代码常量作业集
        #   互不相交。定义增删在每轮 tick 自动生效，无需重启。
        workflow_scheduler = WorkflowScheduleScheduler(
            data_source=data_source,
            config={'check_interval': 60},
        )
        workflow_scheduler.start()
        atexit.register(workflow_scheduler.stop)
        set_workflow_scheduler(workflow_scheduler)

        logging.getLogger(__name__).info(
            "[P1] in-process schedulers started: %d ops jobs + 1 platform_tick "
            "+ %d workflow schedules (the only cron path; decoupled from "
            "legacy TaskScheduler)",
            len(_maintenance_handlers), len(workflow_scheduler.codes()))
    else:
        # 暂停态：两个调度器均未启动 —— 端点仍需可答「已暂停」（paused=True）
        set_inprocess_schedulers(None, None, paused=True)
        set_workflow_scheduler(None, paused=True)
        logging.getLogger(__name__).warning(
            "[P1] cron jobs paused (CRON_JOBS_ENABLED=0) — in-process schedulers not started")

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

    # [多产品平台 §6.5.3 改动 1] 请求级数据源绑定（APP_DB_ROUTING，默认关闭）
    # 必须放在 Flask 层而非 BO 拦截器：鉴权 / 菜单等"动作之前"的读取也要拿到
    # 绑定（ContextInterceptor 是 BO 动作拦截器，触发时机太晚，见 §6.5.3 陷阱）。
    @app.before_request
    def bind_request_app_data_source():
        from meta.core.datasource import (
            bind_app_data_source as _bind_app_ds,
            is_app_db_routing_enabled,
        )
        if not is_app_db_routing_enabled():
            return None

        from meta.core.app_registry import (
            get_app_database_file,
            resolve_app_id_for_request,
        )
        app_id = resolve_app_id_for_request(request.path)
        if not app_id:
            return None  # 平台请求 → 不绑定 → 走平台库（与改造前一致）

        try:
            _bind_app_ds(app_id, get_app_database_file(app_id))
        except ValueError:
            # 非法 app_id（路径穿越尝试）→ 拒绝绑定；路由层随后会 404
            logging.getLogger(__name__).warning(
                "[AppRouting] 拒绝非法 app_id: %r (path=%s)", app_id, request.path
            )
        return None

    @app.teardown_request
    def unbind_request_app_data_source(exc=None):
        """请求结束解绑 —— 线程复用（waitress）下防止绑定泄漏到下一个请求。"""
        from meta.core.datasource import (
            get_bound_app_id,
            is_app_db_routing_enabled,
            unbind_app_data_source as _unbind_app_ds,
        )
        if is_app_db_routing_enabled() and get_bound_app_id() is not None:
            _unbind_app_ds()
        return None

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
    app.register_blueprint(permission_set_bp)
    app.register_blueprint(data_perm_bp)
    # app.register_blueprint(role_data_permission_bp)  # 模块不存在，已废弃
    app.register_blueprint(permission_set_menu_bp)
    app.register_blueprint(ps_dim_scope_bp)
    app.register_blueprint(permission_dimension_bp)
    app.register_blueprint(roles_bp)  # /api/v1/roles/<id>/permission-rules
    app.register_blueprint(ps_matrix_bp)  # /api/v1/permission-sets/<id>/resource-action-matrix (GET+PUT)
    app.register_blueprint(mgmt_meta_bp)  # /api/v1/meta/*
    app.register_blueprint(org_bp)
    app.register_blueprint(org_function_bp)
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
    app.register_blueprint(permission_set_v2_bp)  # [P13-T4] Permission Set API
    # [Phase 3 P3.1-P3.7 2026-07-25] 统一权限管理 API (permission_rules_v2 CRUD + 推导 + 预览 + 模拟)
    from meta.api.unified_permission_api import unified_permission_bp
    app.register_blueprint(unified_permission_bp)
    app.register_blueprint(value_help_bp)
    app.register_blueprint(audit_mgmt_bp)
    app.register_blueprint(meta_util_bp)
    # [roadmap v1.32.0 §6.2.4] 任务体系 = 部署级可关闭的平台模块。
    # 不注册 blueprint ⇒ 路由真 404（不只是前端看不见），须与菜单种子同门。
    _tasks_enabled = is_module_enabled('tasks')
    if _tasks_enabled:
        app.register_blueprint(task_api_bp)
        # [A8 2026-10-02] 统一收件箱 + 平台心跳
        app.register_blueprint(task_inbox_bp)
        # [B3 2026-10-03] 审批决策提交（决策-生效协议唯一生产调用方）
        app.register_blueprint(task_decision_bp)
        # [C 组编排完整 2026-10-14] 编排只读聚合（调度 tab 数据源），随 tasks 门控
        app.register_blueprint(workflow_bp)
    else:
        logging.getLogger(__name__).info(
            "[PlatformModules] tasks 已禁用 (DISABLED_PLATFORM_MODULES) "
            "→ task/task_inbox/task_decision/workflow 四个 blueprint 不注册"
        )
    # [P1 2026-10-13] 进程内调度器运维端点（只读状态 + 按需触发）**无条件注册**：
    #   运维作业是平台基础设施（DB 维护 / 审计归档 / 导入队列 + platform_tick），
    #   与 tasks 模块开关无关 —— 故不放进上面被门控的 task_api_bp。
    app.register_blueprint(scheduler_bp)
    # [定价引擎 T1-4 2026-10-06] 定价编排服务 HTTP 暴露（IF-001/002/003）
    from meta.api.pricing_api import pricing_bp
    app.register_blueprint(pricing_bp)
    # [分摊IF-004 2026-10-07] 分摊是平台级能力（算法零业务耦合、留痕已拆出
    #   allocation_results 独立表），故独立蓝图而非挂在 pricing 下。
    #   旧路径 /api/v1/pricing/allocate **不留别名**（交付次日即改，无调用方）。
    from meta.api.allocation_api import allocation_bp
    app.register_blueprint(allocation_bp)
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

    # [多产品平台 §11 Q5 S2 / 2026-09-24] 原 M10 MCP Server Blueprint 注册已移除。
    # 原因：实测未登录 GET /mcp、GET /mcp/tools、POST /mcp 均返回 200（能力清单裸露），
    # 而全站受保护端点均返回 401 —— 三条路由不在统一鉴权入口内。
    # Agent 面待 Phase 2 从统一鉴权入口（§11 Q5 S2）重开，勿在此处单独注册。

    # M13 v1.4.0: Schema Dashboard Blueprint (entity summary + drift detection)
    from meta.api.schema_api import schema_dashboard_bp
    app.register_blueprint(schema_dashboard_bp)

    # M14 v1.0.0: Telemetry Dashboard Blueprint (p50/p95/p99 stats + slow traces)
    from telemetry import telemetry_bp
    app.register_blueprint(telemetry_bp)

    # v3 BO Action: 注册业务 Action 处理器
    # [FR-5.2] 提取到 meta/services/bo_action_registrations.py
    # 21 个 register 调用 → 单行 register_all_bo_actions()
    from meta.services.bo_action_registrations import register_all_bo_actions
    register_all_bo_actions()

    # [多产品平台 v1.8] 应用包注册（roadmap §6.3 / §6.4.1 方案甲）
    # ENABLED_APPS 未设置 → legacy 模式, 不加载任何应用, 零行为变化
    try:
        from meta.core.app_registry import register_apps
        _registered_apps = register_apps(app, data_source=data_source)
        if _registered_apps:
            logging.getLogger(__name__).info(
                "[AppRegistry] 已加载应用: %s",
                [m.app_id for m in _registered_apps],
            )
    except Exception as _app_err:
        # 应用加载失败必须中止启动（路由冲突等属配置错误, 静默降级更危险）
        logging.getLogger(__name__).error("[AppRegistry] 应用加载失败: %s", _app_err)
        raise

    # [A 可见性 2026-09-25] 启动落盘应用清单事实副本（平台库同目录 runtime_apps.json）
    # 供排查"这台服务器部署了哪些 app"；落盘失败只告警、绝不阻断启动。
    try:
        from meta.core.app_registry import write_runtime_apps_snapshot
        write_runtime_apps_snapshot(db_path)
    except Exception as _snap_err:
        logging.getLogger(__name__).warning(
            "[AppRegistry] runtime_apps.json 落盘调用失败（不影响启动）: %s", _snap_err
        )

    # [多产品平台 §6.14.2] 跨应用事件投递线程（无事件契约时不启动）
    try:
        from meta.core.event_outbox import start_event_dispatcher
        if start_event_dispatcher() is not None:
            logging.getLogger(__name__).info("[EventDispatcher] 跨应用事件投递已启动")
    except Exception as _evt_err:
        logging.getLogger(__name__).error("[EventDispatcher] 启动失败: %s", _evt_err)
        raise

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
        # [Spec 16 2026-08-29] 旧 roles/user-groups → 新 permission_sets/orgs
        # 路径段名变更后保留 v1 业务路由, 避免 deprecate_v1_crud 误拦截
        'permission-sets',                 # /api/v1/permission-sets/* (Spec 16, 旧 roles)
        'permission-set-menus',            # /api/v1/permission-set-menus/*
        'permission-set-dimension-scopes', # /api/v1/permission-set-dimension-scopes/*
        'orgs',                            # /api/v1/orgs/* (Spec 16, 旧 user-groups)
        'org-permission-sets',             # /api/v1/org-permission-sets/* (Spec 16, 旧 group-roles)
        # [Spec16 Plan D 2026-09-02] menu_permission_bp /visible 路由仍被前端菜单渲染使用
        # 加白名单避免 deprecate_v1_crud 中间件误拦截
        'menu-permission',                 # /api/v1/menu-permission/visible
        # [多产品平台 v1.8] 应用包路由前缀 /api/v1/apps/<app_id>/*
        # 不加白名单会被本中间件按"其他 v1 路径"误判为 410
        'apps',
        # [P1 平台任务 2026-10-11] 平台任务 v1 REST（收件箱/任务/心跳/决策)是独立 Blueprint,
        # 非 BO 资源; 不加白名单会被本中间件按"其他 v1 路径"误判为 410
        # (实测: GET /api/v1/task-inbox → 410, 报文指向的 /api/v2/bo/task-inbox 并非真实 BO)
        'task-inbox',   # /api/v1/task-inbox (/counts) — 统一任务收件箱
        'tasks',        # /api/v1/tasks/* — 详情/事件流/认领/监控/决策
        'platform',     # /api/v1/platform/tick — 平台心跳（派工/回收/告警）
    }

    # v1.4 P8 Sunset (2026-06-05): 应当 sunset 到 v2 的主表 CRUD 资源
    # 顶层 5 CRUD (GET/POST/PUT/DELETE /api/v1/<resource> 和 /<id>) 会被 410 拦截
    # 子路径 (/api/v1/<resource>/<id>/<sub> 等) 继续工作 (200)
    V1_CRUD_MIGRATION = {
        # v1_path_segment: v2_singular_object_type
        'users': 'user',
        'roles': 'role',
        'user-groups': 'org',
        'permission-bundles': 'permission_bundle',
        'permission-rules': 'permission_rule',
        'data-permissions': 'data_permission',
        'management-dimensions': 'permission_dimension',
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
        # [A 可见性 2026-09-25] 暴露本实例实际加载的应用（唯一存活的无鉴权探活点；
        # /api/v1/health 已被 v1 sunset 中间件接管返回 410，勿再引用）
        from meta.core.app_registry import get_enabled_app_ids, get_loaded_apps
        apps = get_loaded_apps()
        # [v1.32.0 §6.2.4] 平台模块开关状态 —— 部署后须能从探活点确认开关是否真的生效
        from meta.core.platform_modules import disabled_modules, ineffective_disables
        return jsonify({
            'status': 'ok',
            'service': 'arch-data-manage-api',
            'apps_mode': 'enabled' if apps else 'legacy',
            'enabled_apps': get_enabled_app_ids(),
            'apps': apps,
            'disabled_platform_modules': sorted(disabled_modules()),
            'ineffective_platform_modules': sorted(ineffective_disables()),
        })

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
    # [P0 2026-09-05 端口单一真源] 默认读 scripts/ports.json (3011), 不再硬编码 5000
    try:
        import json as _json
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'ports.json'), 'r', encoding='utf-8') as _pf:
            _default_port = int(_json.load(_pf).get('backend', 3011))
    except Exception:
        _default_port = 3011
    port = int(os.environ.get('PORT', _default_port))
    
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
