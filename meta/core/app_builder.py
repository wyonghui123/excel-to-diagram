# -*- coding: utf-8 -*-
import os
import logging

from flask import Flask
from meta.core.datasource import get_data_source
from meta.core.models import registry
from meta.core.table_name_validator import invalidate_cache as invalidate_table_cache
from meta.core.startup_checks import run_startup_checks

logger = logging.getLogger(__name__)


class ApplicationBuilder:
    """
    Application builder for ArchWorkspace.

    Provides a fluent API to construct the Flask application step by step,
    replacing the monolithic create_app() function.

    Usage:
        app = ApplicationBuilder()
            .with_data_source(db_path)
            .with_yaml_schemas()
            .with_services()
            .with_interceptors()
            .with_blueprints()
            .build()
    """

    def __init__(self, db_path=None):
        self._db_path = db_path or _default_db_path()
        self._data_source = None
        self._app = None
        # [FR-5.3-5.7] 显式启用标志（默认关闭，需通过 with_* 启用）
        self._enable_preflight = False
        self._enable_telemetry = False
        self._enable_auth_init = False
        self._enable_menu_init = False

    def with_data_source(self, db_path=None) -> 'ApplicationBuilder':
        path = db_path or self._db_path
        self._data_source = get_data_source("sqlite", database=path)
        logger.info("[AppBuilder] Data source initialized")
        return self

    def with_yaml_schemas(self, schema_dir=None) -> 'ApplicationBuilder':
        from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory
        from meta.services.view_config_service import view_config_service

        sdir = schema_dir or get_yaml_schema_dir()
        register_from_directory(sdir)
        view_config_service.invalidate_cache()
        invalidate_table_cache()
        logger.info(f"[AppBuilder] YAML schemas loaded from: {sdir}")
        return self

    def with_auto_schema(self, data_source=None) -> 'ApplicationBuilder':
        """[M7.4 2026-06-05] 自动从 DB 扫描表结构 → 生成 BODefinition dict（仅 introspect，不注册）。

        提取自 server.py 启动流程，封装在 AppBuilder 中。

        用法：
            builder.with_auto_schema()  # 默认用 bo_framework._data_source
            builder.with_auto_schema(my_data_source)
        """
        from meta.core.schema_introspector import (
            get_schema_introspector, SchemaIntrospector,
        )
        from meta.services.view_config_service import view_config_service

        introspector = get_schema_introspector() if data_source is None else SchemaIntrospector(data_source)
        tables = introspector.list_tables()
        introspected = 0
        failed = 0
        for table in tables:
            try:
                bd = introspector.introspect(table)
                introspected += 1
                logger.debug(
                    f"[AppBuilder.M7.4] introspect {table}: "
                    f"{len(bd.get('fields', []))} fields, {len(bd.get('associations', []))} FKs"
                )
            except Exception as e:
                failed += 1
                logger.warning(f"[AppBuilder.M7.4] introspect {table} failed: {e}")
        view_config_service.invalidate_cache()
        logger.info(f"[AppBuilder.M7.4] introspected {introspected}/{len(tables)} tables ({failed} failed)")
        return self

    # ==================== [FR-5.3-FR-5.7] AppBuilder 补全方法 ====================

    def with_preflight_checks(self) -> 'ApplicationBuilder':
        """[FR-5.3] 启动前数据库健康检查（DB integrity + size）

        实际执行在 build() 链中。当前仅记录 enable 标志。
        """
        self._enable_preflight = True
        logger.info("[AppBuilder] Preflight checks enabled")
        return self

    def with_telemetry(self) -> 'ApplicationBuilder':
        """[FR-5.4 / M14 v1.0.0] 安装遥测追踪器到所有拦截器

        实际执行在 build() 链中。当前仅记录 enable 标志。
        """
        self._enable_telemetry = True
        logger.info("[AppBuilder] Telemetry tracer enabled")
        return self

    def with_auth_init(self) -> 'ApplicationBuilder':
        """[FR-5.5] 初始化认证系统（创建表 + 种子数据 + 系统管理员迁移）

        实际执行在 build() 链中。当前仅记录 enable 标志。
        """
        self._enable_auth_init = True
        logger.info("[AppBuilder] Auth init enabled")
        return self

    def with_menu_init(self) -> 'ApplicationBuilder':
        """[FR-5.6] 初始化菜单权限（创建表 + 种子数据）

        实际执行在 build() 链中。当前仅记录 enable 标志。
        """
        self._enable_menu_init = True
        logger.info("[AppBuilder] Menu init enabled")
        return self

    def with_bo_actions(self) -> 'ApplicationBuilder':
        """[FR-5.7] 注册所有 19 个 BO Action handler

        提取自 server.py L679-1067，避免 server.py 过于庞大。
        立即执行（不延迟到 build），因为 Action 注册是模块级操作。
        """
        from meta.services.bo_action_registrations import register_all_bo_actions
        from meta.core.bo_action_registry import bo_action_registry
        register_all_bo_actions(bo_action_registry)
        logger.info(f"[AppBuilder] BO actions registered: {len(bo_action_registry.list_ids())}")
        return self

    def with_m8(self) -> 'ApplicationBuilder':
        """[M8 2026-06-06] 启用消费侧 6 个 P0 能力。

        包含：
        - VP-1 ValueHelp
        - VP-2 Nested DSL
        - VP-3 Aggregate
        - VP-4 Reverse Expand
        - VP-5 ETag middleware
        - VP-6 Custom Order (parse_ordering in m8_utils)

        用法：
            builder.with_m8()
        """
        from meta.api.m8_api import register_m8_blueprints
        from meta.core.etag_middleware import init_etag_middleware

        if self._app is None:
            self._app = self._create_app()
        # 注册 blueprint
        register_m8_blueprints(self._app)
        # 注册 ETag middleware
        init_etag_middleware(self._app)
        logger.info('[AppBuilder.M8] M8 consumer-side capabilities enabled')
        return self

    def with_services(self) -> 'ApplicationBuilder':
        ds = self._data_source
        db_path = self._db_path

        _init_service(ds, 'manage', 'init_manage_services')
        _init_service(ds, 'auth', 'init_auth_services')
        _init_service(ds, 'user', 'init_user_services')
        _init_service(ds, 'role', 'init_role_services')
        _init_service(ds, 'data_perm', 'init_data_perm_services')
        _init_service(ds, 'enum', 'init_enum_services', db_path)
        _init_service(ds, 'identity', 'init_identity_services')
        _init_service(ds, 'association', 'init_association_services')
        from meta.core.standard_action_loader import StandardActionLoader
        schemas_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'schemas')
        actions = StandardActionLoader.load(schemas_dir)
        logger.info(f"[AppBuilder] 标准动作已加载: {len(actions)} 个")
        _init_service(ds, 'user_group', 'init_user_group_services')
        _init_service(ds, 'change_notification', 'init_change_notification_tables')

        _init_database_service(ds)
        _init_audit_service(ds, db_path)

        logger.info("[AppBuilder] All services initialized")
        return self

    def with_interceptors(self) -> 'ApplicationBuilder':
        ds = self._data_source

        from meta.core.bo_framework import bo_framework
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.interceptors.permission_interceptor import PermissionInterceptor
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        from meta.core.interceptors.enum_protection_interceptor import EnumProtectionInterceptor
        from meta.core.interceptors.field_policy_interceptor import FieldPolicyInterceptor
        from meta.core.interceptors.version_context_interceptor import VersionContextInterceptor
        from meta.core.interceptors.key_template_interceptor import KeyTemplateInterceptor
        from meta.core.interceptors.association_interceptor import AssociationInterceptor
        from meta.core.interceptors.business_log_interceptor import BusinessLogInterceptor
        from meta.core.interceptors.security_log_interceptor import SecurityLogInterceptor
        from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
        from meta.core.key_template_engine import KeyTemplateEngine

        bo_framework._data_source = ds
        bo_framework.register_interceptor(ContextInterceptor())
        bo_framework.register_interceptor(VersionContextInterceptor())
        # [PermissionInterceptor 注册补齐 2026-06-07]
        # PermissionInterceptor(P30) 与 server.py 对齐：先功能权限校验，再数据权限过滤
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

        _kt_engine = KeyTemplateEngine(ds)
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
        bo_framework.register_interceptor(OperationLogInterceptor())

        logger.info("[AppBuilder] All interceptors registered")
        return self

    def with_menu_auto_gen(self) -> 'ApplicationBuilder':
        from meta.core.menu_auto_generator import menu_auto_generator
        menu_auto_generator.persist_to_db(self._data_source)
        logger.info("[AppBuilder] Menu auto-generation complete")
        return self

    def with_blueprints(self) -> 'ApplicationBuilder':
        app = self._app
        if app is None:
            raise RuntimeError("Flask app not created yet. Call _create_flask_app() first.")

        from meta.api.query_api import query_bp
        from meta.api.manage_api import manage_bp
        from meta.api.meta_api import meta_bp
        from meta.api.agent_api import agent_bp
        from meta.api.export_import_api import export_import_bp
        from meta.api.stats_api import stats_bp
        from meta.api.schema_api import schema_bp
        from meta.api.auth_api import auth_bp
        from meta.api.user_api import user_bp
        from meta.api.role_api import role_bp
        from meta.api.data_permission_api import data_perm_bp
        from meta.api.role_menu_api import role_menu_bp
        from meta.api.role_dim_api import role_dim_bp
        from meta.api.management_dimension_api import management_dimension_bp, roles_bp, meta_bp as mgmt_meta_bp
        from meta.api.user_group_api import user_group_bp
        from meta.api.enum_api import enum_bp
        from meta.api.menu_permission_api import menu_permission_bp
        from meta.api.permission_bundle_api import permission_bundle_bp
        from meta.api.permission_audit_api import permission_audit_bp
        from meta.api.permission_sync_api import permission_sync_bp
        from meta.api.owner_transfer_api import owner_transfer_bp
        from meta.api.permission_rule_api import permission_rule_bp
        from meta.api.audit_api import audit_bp
        from meta.api.notification_api import notification_bp
        from meta.api.database_api import database_bp
        from meta.api.filter_variant_api import filter_variant_bp
        from meta.api.identity_api import identity_bp
        from meta.api.association_api import association_bp
        from meta.api.bo_api import bo_bp, meta_v2_bp, role_v2_bp, permission_rule_v2_bp
        from meta.api.value_help_api import value_help_bp
        from meta.api.special_routes_api import special_bp
        from meta.api.annotation_routes_api import annotation_bp
        from meta.api.audit_management_api import audit_mgmt_bp
        from meta.api.meta_utility_routes_api import meta_util_bp
        from meta.api.key_template_api import key_template_bp, set_engine as set_kt_engine
        from meta.api.test_api import test_bp
        from meta.api.overlap_api import overlap_bp
        from meta.api.permission_api import permission_bp
        from meta.api.intent_api import intent_bp
        from meta.api.bo_action_api import bo_action_bp
        from meta.api.db_admin_api import db_admin_bp
        from meta.api.task_api import task_api_bp
        from meta.api.schema_api import schema_dashboard_bp
        from meta.graphql import graphql_bp
        from mcp import mcp_bp
        from telemetry import telemetry_bp

        app.register_blueprint(query_bp)
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
        app.register_blueprint(special_bp)
        app.register_blueprint(annotation_bp)
        app.register_blueprint(audit_mgmt_bp)
        app.register_blueprint(meta_util_bp)
        app.register_blueprint(key_template_bp)
        app.register_blueprint(test_bp)
        app.register_blueprint(overlap_bp)
        app.register_blueprint(permission_bp)
        app.register_blueprint(intent_bp)
        app.register_blueprint(bo_action_bp)
        app.register_blueprint(db_admin_bp)
        app.register_blueprint(task_api_bp)
        app.register_blueprint(schema_dashboard_bp)
        app.register_blueprint(graphql_bp)
        app.register_blueprint(mcp_bp)
        app.register_blueprint(telemetry_bp)

        # v3.18: diagnostics + metrics 端点
        from meta.api.diagnostics_api import register_diagnostics_route
        register_diagnostics_route(app)
        from meta.api.metrics_api import register_metrics_route
        register_metrics_route(app)

        logger.info("[AppBuilder] All blueprints registered")
        return self

    def with_websocket(self) -> 'ApplicationBuilder':
        from meta.server import init_socketio
        init_socketio(self._app)
        logger.info("[AppBuilder] WebSocket initialized")
        return self

    def build(self) -> Flask:
        # [FR-1.2 / FR-5.3-5.7] 完整启动链
        # 阶段 1: 可选启动前初始化（FR-5.3-5.6）
        if self._enable_preflight:
            self._run_preflight_checks()
        if self._enable_telemetry:
            self._install_telemetry_tracer()
        if self._enable_auth_init:
            self._run_auth_init()
        if self._enable_menu_init:
            self._run_menu_init()

        # 阶段 2: Flask app 创建
        self._create_flask_app()
        run_startup_checks(self._app)

        # 阶段 3: 中间件 + 错误处理
        self._register_middleware()
        self._register_error_handlers()

        # 阶段 4: 启动后健康记录
        if self._enable_telemetry:
            try:
                from meta.core.db_health_monitor import init_monitor
                init_monitor(self._db_path)
                logger.info("[AppBuilder] DBHealthMonitor initialized")
            except Exception as e:
                logger.warning(f"[AppBuilder] DBHealthMonitor init failed: {e}")

        return self._app

    # ==================== [FR-5.3-FR-5.7] 内部执行方法 ====================

    def _run_preflight_checks(self) -> 'ApplicationBuilder':
        """[FR-5.3] 数据库预检：DB integrity + size"""
        import os
        import sqlite3
        db_path = self._db_path
        if not os.path.exists(db_path):
            return self
        try:
            file_size = os.path.getsize(db_path)
        except OSError as e:
            logger.warning(f"[AppBuilder] Preflight: cannot stat DB: {e}")
            return self
        if file_size < 1024:
            return self
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            if result == "ok":
                logger.info(f"[AppBuilder] Preflight DB check: OK ({file_size} bytes)")
            else:
                logger.error(f"[AppBuilder] Preflight DB integrity_check FAILED: {result}")
        except sqlite3.DatabaseError:
            logger.error("[AppBuilder] Preflight: DB is corrupt")
        except Exception as e:
            logger.error(f"[AppBuilder] Preflight DB error: {e}")
        return self

    def _install_telemetry_tracer(self) -> 'ApplicationBuilder':
        """[FR-5.4 / M14 v1.0.0] 安装遥测追踪器到所有拦截器"""
        try:
            from telemetry.integration import install_global_tracer
            from meta.core.bo_framework import bo_framework
            interceptor_count = len(bo_framework.interceptors)
            install_global_tracer(bo_framework.interceptors)
            logger.info(f"[AppBuilder] Telemetry tracer installed on {interceptor_count} interceptors")
        except Exception as e:
            logger.warning(f"[AppBuilder] Telemetry tracer install failed: {e}")
        return self

    def _run_auth_init(self) -> 'ApplicationBuilder':
        """[FR-5.5] 初始化认证系统 + 迁移系统管理员"""
        try:
            from meta.scripts.init_auth import init_auth_system
            init_auth_system()
            logger.info("[AppBuilder] Auth system initialized")
        except Exception as e:
            logger.error(f"[AppBuilder] init_auth_system failed: {e}")

        try:
            from meta.scripts.migrate_system_admin import run_migration
            run_migration()
            logger.info("[AppBuilder] System admin migration done")
        except Exception as e:
            logger.error(f"[AppBuilder] run_migration failed: {e}")
        return self

    def _run_menu_init(self) -> 'ApplicationBuilder':
        """[FR-5.6] 初始化菜单权限"""
        try:
            from meta.scripts.init_menu_permissions import init_menu_permissions
            init_menu_permissions(self._db_path)
            logger.info("[AppBuilder] Menu permissions initialized")
        except Exception as e:
            logger.error(f"[AppBuilder] init_menu_permissions failed: {e}")
        return self

    def _create_flask_app(self):
        self._app = Flask(__name__)
        return self._app

    def _register_middleware(self):
        import secrets
        from meta.server import TRACE_ID_HEADER, get_trace_id, get_or_create_trace_id
        from flask import g, request

        app = self._app

        @app.before_request
        def setup_trace():
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
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            # [FR-024] 扩展 Allow-Headers 包含项目自定义头
            response.headers['Access-Control-Allow-Headers'] = (
                'Content-Type, Authorization, X-CSRF, X-Trace-Id, X-Agent-Reasoning'
            )
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            # [FR-024] Max-Age: 浏览器缓存 preflight 结果 24h, 减少 OPTIONS 请求
            response.headers['Access-Control-Max-Age'] = '86400'
            return response

        # [FR-024] 显式处理 OPTIONS preflight 请求
        # 避免 Flask 路由到视图函数返回 405
        @app.before_request
        def handle_options_preflight():
            if request.method == 'OPTIONS':
                # after_request 会添加 CORS 头, 这里只需返回 204
                return '', 204

        # v1.4 P8 Sunset (2026-06-05): 已 Sunset
        # V1_SPECIAL_PREFIXES 保留**必要的** v1 路径（包括 v1/user-groups, v1/roles）
        # 这些路径下：
        #   - 业务关系路由（members, roles, overlaps, intents）继续工作
        #   - 主表 CRUD 路由（GET/POST/PUT/DELETE /user-groups, /roles）已由 endpoint 层移除
        V1_SPECIAL_PREFIXES = {
            'relationships', 'business_object', 'annotations', 'audit', 'meta',
            'analytics', 'enums', 'enum-types', 'enum-values', 'auth', 'menu-permission',
            'notifications', 'import', 'export', 'import-export',
            'permission-rules', 'management-dimensions', 'roles', 'user-groups',
            'permission-bundles', 'role-menus', 'role-dimension-scopes',
            'filter-variants', 'permission-audit', 'bo', 'users',
            'data-permissions', 'associations', 'identity', 'meta-actions',
            'query', 'agent', 'schema', 'system', 'stats', 'manage', 'test',
            # v1.4 P2 修复：保留这些 v1 路径
            'permissions',  # /api/v1/permissions/* (FR-012 explain/check/check_intent)
            'roles',        # /api/v1/roles/*/intents (FR-017)
            'bos',          # /api/v1/bos (FR-017 BO list)
            'overlaps',     # /api/v1/roles/*/overlaps (FR-005)
            'telemetry',    # M14: /api/v1/telemetry/* (stats/traces/configure)
        }

        @app.before_request
        def deprecate_v1_crud():
            """v1.4 P8 Sunset: v1 CRUD 路径直接 410

            V1_SPECIAL_PREFIXES 中的路径由 endpoint 层处理：
            - 业务关系路由继续工作
            - 主表 CRUD 路由（GET/POST/PUT/DELETE /user-groups, /roles）已移除
            """
            if request.path.startswith('/api/v1/'):
                path_parts = request.path[len('/api/v1/'):].split('/')
                if path_parts and path_parts[0]:
                    first_segment = path_parts[0]
                    if first_segment not in V1_SPECIAL_PREFIXES:
                        from flask import jsonify
                        return jsonify({
                            'error': 'API Moved',
                            'message': f'{request.method} {request.path} has moved to /api/v2/bo/{first_segment}',
                            'migrated_at': '2026-05-14',
                            'sunset_at': '2026-06-05'
                        }), 410

        @app.route('/health')
        def health():
            from flask import jsonify
            return jsonify({'status': 'ok', 'service': 'arch-data-manage-api'})

    def _register_error_handlers(self):
        import traceback
        from flask import jsonify
        from werkzeug.exceptions import HTTPException

        app = self._app
        is_debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

        @app.errorhandler(500)
        def handle_500(error):
            error_msg = str(error)
            if is_debug:
                error_trace = traceback.format_exc()
                return jsonify({
                    'success': False,
                    'error': 'INTERNAL_SERVER_ERROR',
                    'message': error_msg,
                    'detail': error_trace
                }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': 'INTERNAL_SERVER_ERROR',
                    'message': 'An internal error occurred. Please contact support.'
                }), 500

        # [FIX FIX-005] 2026-06-07: HTTPException 用专属 handler 保留 status code
        # 之前 `@app.errorhandler(Exception)` 把所有异常 (含 404 NotFound) 都转为 500
        # 现在: 4xx (NotFound/MethodNotAllowed/BadRequest 等) 保留原始 status code
        #       5xx (InternalServerError) 走 500 handler
        #       真正的 Exception 才走 handle_exception
        @app.errorhandler(HTTPException)
        def handle_http_exception(error):
            """处理 Werkzeug HTTPException (4xx 为主) — 保留原始 status_code"""
            status_code = error.code or 500
            return jsonify({
                'success': False,
                'error': error.name or 'HTTP_ERROR',
                'message': error.description or str(error),
                'status_code': status_code,
            }), status_code

        @app.errorhandler(Exception)
        def handle_exception(error):
            # [FIX FIX-005] 防御性检查: HTTPException 应被更具体的 handler 拦截
            # 但如果走到了这里, 仍用 error.code (默认值 500) 保留 status
            if isinstance(error, HTTPException):
                status_code = error.code or 500
                return jsonify({
                    'success': False,
                    'error': error.name or 'HTTP_ERROR',
                    'message': error.description or str(error),
                    'status_code': status_code,
                }), status_code
            error_msg = str(error)
            if is_debug:
                error_trace = traceback.format_exc()
                return jsonify({
                    'success': False,
                    'error': type(error).__name__,
                    'message': error_msg,
                    'detail': error_trace
                }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': type(error).__name__,
                    'message': 'An internal error occurred. Please contact support.'
                }), 500


def _default_db_path():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )


def _init_service(ds, name, fn_name, *extra_args):
    try:
        mod = __import__(f'meta.services.{name}_service', fromlist=[fn_name])
        fn = getattr(mod, fn_name)
        fn(ds, *extra_args)
        logger.debug(f"[AppBuilder] Service initialized: {name}")
    except Exception as e:
        logger.warning(f"[AppBuilder] Service init failed [{name}]: {e}")


def _init_database_service(ds):
    try:
        from meta.services.database_service import init_database_services
        init_database_services(data_source=ds)
        logger.debug("[AppBuilder] Database service initialized")
    except Exception as e:
        logger.warning(f"[AppBuilder] Database service init failed: {e}")


def _init_audit_service(ds, db_path):
    try:
        from meta.services.audit_service import init_audit_services
        init_audit_services(data_source=ds)

        from meta.migrations.enhance_audit_log_v2 import enhance_audit_log
        enhance_audit_log(db_path)

        # [FR-008/009] 性能索引 v3: relationships + audit_logs 覆盖索引
        import sqlite3
        conn = sqlite3.connect(db_path)
        try:
            from meta.migrations.add_performance_indexes_v3 import create_indexes as create_v3_indexes
            create_v3_indexes(conn)
        finally:
            conn.close()

        from meta.services.async_audit_writer import async_audit_writer
        async_audit_writer.set_data_source(ds)

        logger.debug("[AppBuilder] Audit service initialized")
    except Exception as e:
        logger.warning(f"[AppBuilder] Audit service init failed: {e}")
