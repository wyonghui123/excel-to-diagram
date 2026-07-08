"""
BO Action 注册模块

提取自 server.py L663-1067（19 个 bo_action_registry.register 调用），
避免 server.py 过于庞大，同时让 ApplicationBuilder 也能复用。

提供 register_all_bo_actions(registry) 函数供：
1. server.py create_app() 调用（向后兼容）
2. ApplicationBuilder.with_bo_actions() 调用（新入口）

19 个 Action 分类:
- 5 个 auth (user.*)
- 1 个 profile (user.update_profile)
- 2 个 crud (batch_save, batch_delete)
- 1 个 business (version.clear_other_current)
- 2 个 ops (audit.*)
- 1 个 notification (subscription.create)
- 4 个 v3.4 function (function.value_help.resolve, function.aggregate.*, function.subscription.list)
- 3 个 v3.5 enum_type CRUD
"""
import logging

logger = logging.getLogger(__name__)


def register_all_bo_actions(registry=None):
    """注册所有 19 个 BO Action handler

    Args:
        registry: BoActionRegistry 实例，None 时使用全局单例

    Note:
        重复调用是幂等的（register 内部会覆盖）
    """
    if registry is None:
        from meta.core.bo_action_registry import bo_action_registry
        registry = bo_action_registry

    # ==================== Imports（懒加载以避免循环依赖） ====================
    from meta.services.user_authenticate import user_authenticate_handler
    from meta.services.user_logout import user_logout_handler
    from meta.services.user_get_current import user_get_current_handler
    from meta.services.user_change_password import user_change_password_handler
    from meta.services.user_update_profile import user_update_profile_handler
    from meta.services.draft_batch_save import batch_save_handler
    from meta.services.user_reset_password import user_reset_password_handler
    from meta.services.audit_retry import audit_retry_handler
    from meta.services.audit_export import audit_export_handler
    from meta.services.batch_delete import batch_delete_handler
    from meta.services.subscription_create import subscription_create_handler

    # v3.2: action_handlers
    from meta.services.action_handlers import clear_other_current_versions_handler

    # v3.4: Function
    from meta.services.function_value_help_resolve import function_value_help_resolve_handler
    from meta.services.function_aggregate import (
        function_aggregate_query_handler,
        function_aggregate_refresh_handler,
    )
    from meta.services.function_subscription_list import function_subscription_list_handler

    # v3.5: enum_type CRUD
    from meta.services.enum_type_crud import (
        enum_type_create_handler,
        enum_type_update_handler,
        enum_type_delete_handler,
    )

    # ==================== 1-5: 用户认证 (auth) ====================
    registry.register(
        'user.authenticate',
        user_authenticate_handler,
        description='用户登录认证',
        object_type='user',
        category='auth',
        input_schema={
            'type': 'object',
            'required': ['username', 'password'],
            'properties': {
                'username': {'type': 'string', 'minLength': 1},
                'password': {'type': 'string', 'minLength': 1},
            }
        },
        output_schema={
            'type': 'object',
            'properties': {
                'token': {'type': 'string'},
                'user': {'type': 'object'},
            }
        },
        requires_auth=False,
        idempotent=True,
    )
    registry.register(
        'user.logout',
        user_logout_handler,
        description='用户登出（token 加入黑名单）',
        object_type='user',
        category='auth',
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'user.get_current',
        user_get_current_handler,
        description='获取当前登录用户信息',
        object_type='user',
        category='auth',
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'user.change_password',
        user_change_password_handler,
        description='修改当前用户密码',
        object_type='user',
        category='auth',
        input_schema={
            'type': 'object',
            'required': ['old_password', 'new_password'],
            'properties': {
                'old_password': {'type': 'string'},
                'new_password': {'type': 'string', 'minLength': 6},
            }
        },
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'user.update_profile',
        user_update_profile_handler,
        description='更新当前用户个人信息（display_name/email/locale/timezone 等）',
        object_type='user',
        category='profile',
        input_schema={
            'type': 'object',
            'properties': {
                'display_name': {'type': 'string'},
                'email': {'type': 'string', 'format': 'email'},
                'locale': {'type': 'string'},
                'timezone': {'type': 'string'},
                'date_style': {'type': 'string'},
                'time_style': {'type': 'string'},
                'hour_cycle': {'type': 'string'},
            }
        },
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 6-7: CRUD 批量 ====================
    registry.register(
        'batch_save',  # 命名建议: 后续可改为 'draft.batch_save' (v3.2)
        batch_save_handler,
        description='草稿批量保存（支持 is_new/create+update）',
        object_type='*',
        category='crud',
        input_schema={
            'type': 'object',
            'required': ['object_type', 'drafts'],
            'properties': {
                'object_type': {'type': 'string'},
                'drafts': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'row_id': {'type': ['string', 'integer']},
                            'is_new': {'type': 'boolean'},
                            'fields': {'type': 'object'},
                        }
                    }
                },
            }
        },
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'batch_delete',
        batch_delete_handler,
        description='批量删除（任意 object_type, 与 batch_save 对称）',
        object_type='*',
        category='crud',
        input_schema={
            'type': 'object',
            'required': ['object_type', 'ids'],
            'properties': {
                'object_type': {'type': 'string'},
                'ids': {'type': 'array', 'items': {'type': 'integer'}},
                'force': {'type': 'boolean', 'default': False},
            }
        },
        requires_auth=True,
        idempotent=False,
    )

    # ==================== 8-9: 审计 (ops, admin) ====================
    registry.register(
        'user.reset_password',
        user_reset_password_handler,
        description='管理员重置指定用户密码（强制 must_change_password=1）',
        object_type='user',
        category='auth',
        input_schema={
            'type': 'object',
            'required': ['user_id', 'new_password'],
            'properties': {
                'user_id': {'type': 'integer'},
                'new_password': {'type': 'string', 'minLength': 6},
            }
        },
        output_schema={
            'type': 'object',
            'properties': {
                'user_id': {'type': 'integer'},
                'must_change_password': {'type': 'boolean'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=True,
        visibility='important',
    )
    registry.register(
        'audit.retry',
        audit_retry_handler,
        description='重试失败的审计日志记录（管理员）',
        object_type='audit_log',
        category='ops',
        input_schema={
            'type': 'object',
            'required': ['record_id'],
            'properties': {
                'record_id': {'type': 'integer'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=False,
    )
    registry.register(
        'audit.export',
        audit_export_handler,
        description='导出审计日志为 xlsx/csv 文件（管理员, [DECORATIVE] v3.1 文件流）',
        object_type='audit_log',
        category='ops',
        input_schema={
            'type': 'object',
            'properties': {
                'action': {'type': 'string'},
                'object_type': {'type': 'string'},
                'user_name': {'type': 'string'},
                'start_date': {'type': 'string', 'format': 'date'},
                'end_date': {'type': 'string', 'format': 'date'},
                'format': {'type': 'string', 'enum': ['xlsx', 'csv'], 'default': 'xlsx'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=True,
    )

    # ==================== 10: 订阅 ====================
    registry.register(
        'subscription.create',
        subscription_create_handler,
        description='创建对象变更通知订阅（websocket/webhook）',
        object_type='change_subscription',
        category='notification',
        input_schema={
            'type': 'object',
            'required': ['object_type'],
            'properties': {
                'object_type': {'type': 'string'},
                'event_types': {
                    'type': 'array',
                    'items': {'type': 'string', 'enum': ['created', 'updated', 'deleted']},
                },
                'channel': {'type': 'string', 'enum': ['websocket', 'webhook'], 'default': 'websocket'},
                'webhook_url': {'type': 'string'},
                'webhook_secret': {'type': 'string'},
                'filter_condition': {'type': 'object'},
            }
        },
        requires_auth=True,
        idempotent=False,
    )

    # ==================== 11: 业务 (version internal trigger) ====================
    registry.register(
        'version.clear_other_current',
        clear_other_current_versions_handler,
        description='清除同产品下其他版本的 is_current 标志 (set_current action 的 trigger)',
        object_type='version',
        category='business',
        requires_auth=True,
        idempotent=True,
        visibility='internal',  # 内部 trigger, 不暴露给前端
    )

    # ==================== 12-15: v3.4 Function (4 个读操作) ====================
    registry.register(
        'function.value_help.resolve',
        function_value_help_resolve_handler,
        description='[Function] 解析 value_help 值的显示信息 (display/code)',
        object_type='*',
        category='value_help',
        input_schema={
            'type': 'object',
            'required': ['source_type', 'source_id', 'value'],
            'properties': {
                'source_type': {'type': 'string', 'enum': ['enum', 'bo', 'custom']},
                'source_id': {'type': 'string'},
                'value': {},
                'value_field': {'type': 'string', 'default': 'id'},
                'display_field': {'type': 'string', 'default': 'name'},
                'code_field': {'type': 'string', 'default': 'code'},
            }
        },
        requires_auth=True,
        idempotent=True,
        operation_type='function',
        cacheable=True,
        cache_ttl=60,
    )
    registry.register(
        'function.aggregate.query',
        function_aggregate_query_handler,
        description='[Function] 查询聚合表数据',
        object_type='aggregate',
        category='stats',
        input_schema={
            'type': 'object',
            'required': ['aggregate_id'],
            'properties': {
                'aggregate_id': {'type': 'string'},
                'filters': {'type': 'object'},
                'order_by': {'type': 'string'},
                'limit': {'type': 'integer', 'default': 1000, 'maximum': 10000},
            }
        },
        requires_auth=True,
        idempotent=True,
        operation_type='function',
        cacheable=True,
        cache_ttl=30,
    )
    registry.register(
        'function.aggregate.refresh',
        function_aggregate_refresh_handler,
        description='[Function] 刷新聚合表 (admin 限定, 注意: 实际是写操作, 标为 function 仅因 aggregate 域)',
        object_type='aggregate',
        category='stats',
        input_schema={
            'type': 'object',
            'required': ['aggregate_id'],
            'properties': {
                'aggregate_id': {'type': 'string'},
                'force': {'type': 'boolean', 'default': True},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=False,
        operation_type='function',
        cacheable=False,
    )
    registry.register(
        'function.subscription.list',
        function_subscription_list_handler,
        description='[Function] 列出当前用户的订阅 (可选 object_type 过滤)',
        object_type='change_subscription',
        category='notification',
        input_schema={
            'type': 'object',
            'properties': {
                'object_type': {'type': 'string'},
            }
        },
        requires_auth=True,
        idempotent=True,
        operation_type='function',
        cacheable=False,
    )

    # ==================== 16-18: v3.5 enum_type CRUD (admin 限定) ====================
    registry.register(
        'enum_type.create',
        enum_type_create_handler,
        description='创建业务枚举类型 (admin 限定, 不允许 system 类别)',
        object_type='enum_type',
        category='metadata',
        input_schema={
            'type': 'object',
            'required': ['id', 'name'],
            'properties': {
                'id': {'type': 'string', 'minLength': 1},
                'name': {'type': 'string', 'minLength': 1},
                'category': {'type': 'string', 'enum': ['business'], 'default': 'business'},
                'mutability': {'type': 'string', 'enum': ['extensible', 'frozen'], 'default': 'extensible'},
                'dimension_schema': {'type': 'object'},
                'description': {'type': 'string'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=False,
    )
    registry.register(
        'enum_type.update',
        enum_type_update_handler,
        description='更新业务枚举类型 (admin 限定, system 不可改)',
        object_type='enum_type',
        category='metadata',
        input_schema={
            'type': 'object',
            'required': ['id'],
            'properties': {
                'id': {'type': 'string'},
                'name': {'type': 'string'},
                'mutability': {'type': 'string', 'enum': ['extensible', 'frozen']},
                'dimension_schema': {'type': 'object'},
                'description': {'type': 'string'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=True,
    )
    registry.register(
        'enum_type.delete',
        enum_type_delete_handler,
        description='删除业务枚举类型 (admin 限定, 仅当无 enum_values 时)',
        object_type='enum_type',
        category='metadata',
        input_schema={
            'type': 'object',
            'required': ['id'],
            'properties': {
                'id': {'type': 'string'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=False,
    )

    logger.info(f"[BO Action] Registered {len(registry.list_ids())} business action(s)")
