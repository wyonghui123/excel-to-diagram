"""
BO Action 注册模块

提取自 server.py L663-1067（19 个 bo_action_registry.register 调用），
避免 server.py 过于庞大，同时让 ApplicationBuilder 也能复用。

提供 register_all_bo_actions(registry) 函数供：
1. server.py create_app() 调用（向后兼容）
2. ApplicationBuilder.with_bo_actions() 调用（新入口）

21 个 Action 分类:
- 5 个 auth (user.*)
- 1 个 profile (user.update_profile)
- 2 个 crud (batch_save, batch_delete)
- 1 个 business (version.clear_other_current)
- 2 个 ops (audit.*)
- 1 个 notification (subscription.create)
- 4 个 v3.4 function (function.value_help.resolve, function.aggregate.*, function.subscription.list)
- 3 个 v3.5 enum_type CRUD
- 2 个 v2.0 allocation (allocation.apply, allocation.split)
- 1 个 sales_order (sales_order.recalc_header_discount)
- 3 个 M3 change_request (change_request.approve / .reject / .apply)

[B1 2026-10-02] 注册尾部执行「注册契约机器校验」（见 meta/core/bo_action_contract.py）：
  idempotent / 前置条件 preconditions / 参数 schema / 返回契约四要件的固化与校验。
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

    # 规则模型二期 P7/M7: 拆分 / 分摊
    from meta.services.allocation_apply import (
        allocation_apply_handler,
        allocation_split_handler,
    )

    # 抬头折扣 / 附加费: 显式重算（spec §4.6）
    from meta.services.sales_order_header_discount_apply import (
        sales_order_recalc_header_discount_handler,
    )

    # Wave C T38: 开票计划补跑（订单确认已自动生成，此 Action 供历史单补建）
    from meta.services.billing_plan_actions import (
        generate_billing_plan_handler,
    )

    # M3 变更申请: 审批决策 + 生效（docs/superpowers/specs/2026-10-29-m3-change-request §5.3/§6.3）
    from meta.services.change_request_decision import (
        change_request_approve_handler,
        change_request_reject_handler,
        change_request_apply_handler,
    )

    # M1 需求入口: 审批决策（service_request / requisition 复用 tasks(type=approval)）
    from meta.services.demand_entry_decision import (
        service_request_approve_handler,
        service_request_reject_handler,
        requisition_approve_handler,
        requisition_reject_handler,
    )

    # M3 采购订单: 审批决策（spec-purchase-order-object-model §6.3）
    from meta.services.document_approval_decision import (
        purchase_order_approve_handler,
        purchase_order_reject_handler,
    )
    # M3 采购订单: 需求转单（同 spec §14 步 23）
    from meta.services.requisition_po_conversion import (
        create_from_requisition_handler,
    )

    # M3 收货单: 建单 / 过账 / 整单红冲 / 取消（spec-receipt-object-model §13 步 7）
    from meta.services.receipt_actions import (
        create_from_schedule_handler,
        create_vendor_return_handler as receipt_create_vendor_return_handler,
        post_handler as receipt_post_handler,
        reverse_handler as receipt_reverse_handler,
        cancel_handler as receipt_cancel_handler,
    )

    # S8 Wave A: 销售发票由发货单生成（spec-s8-customer-invoice-wave-a §13）
    from meta.services.customer_invoice_actions import (
        create_from_shipment_handler as customer_invoice_from_shipment_handler,
        create_from_schedule_handler as customer_invoice_from_schedule_handler,
        create_credit_from_invoice_handler as customer_invoice_credit_handler,
        create_credit_from_return_shipment_handler as
        customer_invoice_return_credit_handler,
        create_credit_on_account_handler as
        customer_invoice_on_account_handler,
        list_due_schedules_handler as customer_invoice_due_list_handler,
        submit_handler as customer_invoice_submit_handler,
        post_handler as customer_invoice_post_handler,
        reverse_handler as customer_invoice_reverse_handler,
    )

    # M4 调拨单: 下达 / 发货 / 收货 / 取消 / 关闭（spec-transfer-order-object-model §6/§7）
    # + 审批提交 / 撤回 / 通过 / 驳回（TBD-9，approval_status 正交于 status）
    from meta.services.transfer_order_actions import (
        release_handler as transfer_order_release_handler,
        ship_handler as transfer_order_ship_handler,
        receive_handler as transfer_order_receive_handler,
        cancel_handler as transfer_order_cancel_handler,
        close_handler as transfer_order_close_handler,
        reverse_shipment_handler as transfer_order_reverse_shipment_handler,
        submit_handler as transfer_order_submit_handler,
        withdraw_handler as transfer_order_withdraw_handler,
        approve_handler as transfer_order_approve_handler,
        reject_handler as transfer_order_reject_handler,
    )

    # M4 调拨单: 需求分配转调拨单（TBD-4）
    from meta.services.transfer_order_from_allocation import (
        create_from_allocation_handler as transfer_order_from_allocation_handler,
    )

    # M4 调拨发货单: 建单 / 过账 / 取消（TBD-3 独立发货单）
    from meta.services.transfer_shipment_actions import (
        create_handler as transfer_shipment_create_handler,
        post_handler as transfer_shipment_post_handler,
        cancel_handler as transfer_shipment_cancel_handler,
    )

    # G15 ETO P2-2: 项目结构基线漂移检查 / 刷新
    from meta.services.project_structure_baseline_service import (
        check_drift_handler as project_structure_baseline_check_drift_handler,
        refresh_handler as project_structure_baseline_refresh_handler,
    )

    # S1/S3 接缝: 单据流建单 / E6 三档冲销（spec 2026-11-09 §9.3.13）
    from meta.services.doc_flow_action import (
        doc_flow_derive_handler,
        doc_flow_reverse_handler,
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

    # ==================== 20-21: 拆分 / 分摊 (规则模型二期 P7/M7) ====================
    registry.register(
        'allocation.apply',
        allocation_apply_handler,
        description='把父行的量按权重守恒地分摊到已有 N 个子行 (Σ子行=父行)',
        object_type='*',
        category='allocation',
        # 两种口径：带 allocation_rule_id = 规则驱动（含留痕），
        # 不带 = 显式 weights 直调。故 required 不锁 weights ——
        # 规则驱动时权重由 rule.basis / basis_field 推导。
        input_schema={
            'type': 'object',
            'required': ['parent_id', 'target_object', 'target_field'],
            'properties': {
                'parent_id': {'type': 'integer'},
                'target_object': {'type': 'string'},
                'target_field': {'type': 'string'},
                'source_field': {'type': 'string'},
                'fk_field': {'type': 'string'},
                'parent_object': {'type': 'string'},
                'scale': {'type': 'integer'},
                'weights': {'type': 'array'},
                # ---- 规则驱动口径（allocate_by_rule）----
                'allocation_rule_id': {'type': 'integer'},
                'basis_field': {'type': 'string'},
                'group_by': {'type': 'string'},
                'rounding': {'type': 'string'},
                'floor': {'type': 'number'},
                'persist_result': {'type': 'boolean'},
                'document_type': {'type': 'string'},
                'charge_source': {'type': 'string'},
                'source_document_type': {'type': 'string'},
                'source_document_id': {'type': 'integer'},
                'target': {'type': 'string'},
                'currency': {'type': 'string'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=False,
    )
    registry.register(
        'allocation.split',
        allocation_split_handler,
        description='把父行的量守恒地拆分成 N 个新建子行 (Σ新行=父行)',
        object_type='*',
        category='allocation',
        input_schema={
            'type': 'object',
            'required': ['parent_id', 'target_object', 'target_field'],
            'properties': {
                'parent_id': {'type': 'integer'},
                'target_object': {'type': 'string'},
                'target_field': {'type': 'string'},
                'source_field': {'type': 'string'},
                'fk_field': {'type': 'string'},
                'parent_object': {'type': 'string'},
                'scale': {'type': 'integer'},
                'weights': {'type': 'array'},
                'split_count': {'type': 'integer'},
                'template': {'type': 'object'},
            }
        },
        requires_auth=True,
        requires_admin=True,
        idempotent=False,
    )

    # ==================== 22: 抬头折扣重算 (sales_order) ====================
    registry.register(
        'sales_order.recalc_header_discount',
        sales_order_recalc_header_discount_handler,
        description='按当前行基额重摊抬头折扣 / 附加费（非草稿也允许手动重算）',
        object_type='sales_order',
        category='allocation',
        input_schema={
            'type': 'object',
            'properties': {
                'order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            }
        },
        output_schema={
            'type': 'object',
            'properties': {
                'success': {'type': 'boolean'},
                'data': {'type': 'object'},
                'message': {'type': 'string'},
            }
        },
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 22b: 开票计划补跑 (sales_order) ====================
    registry.register(
        'sales_order.generate_billing_plan',
        generate_billing_plan_handler,
        description='为已确认订单补生成 billing 开票计划期次（幂等，不重算已开票金额）',
        object_type='sales_order',
        category='business',
        permission_required='sales_order:sales_order_update',
        input_schema={
            'type': 'object',
            'properties': {
                'order_id': {'type': 'integer'},
                'triggered_by': {'type': 'string'},
            },
        },
        output_schema={
            'type': 'object',
            'properties': {
                'success': {'type': 'boolean'},
                'data': {
                    'type': 'object',
                    'properties': {
                        'order_id': {'type': 'integer'},
                        'created': {'type': 'array',
                                    'items': {'type': 'integer'}},
                        'skipped': {'type': 'boolean'},
                    },
                },
                'message': {'type': 'string'},
            },
        },
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 23-25: 变更申请（M3 T5） ====================
    # 决策-生效协议（decision_effect）按 executor_config.decision_actions 调 approve/reject；
    # apply 由 POST /bo/change_request/{id}/actions/change_request.apply 触发。
    _cr_output_schema = {
        'type': 'object',
        'properties': {
            'success': {'type': 'boolean'},
            'data': {'type': 'object'},
            'message': {'type': 'string'},
        }
    }
    registry.register(
        'change_request.approve',
        change_request_approve_handler,
        description='变更申请审批通过（submitted → approved，回执 new_status=approved）',
        object_type='change_request',
        category='business',
        permission_required='change_request:approve',
        input_schema={
            'type': 'object',
            'properties': {
                'change_request_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'comment': {'type': 'string'},
            }
        },
        output_schema=_cr_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'change_request.reject',
        change_request_reject_handler,
        description='变更申请审批驳回（submitted → rejected，回执 new_status=rejected）',
        object_type='change_request',
        category='business',
        permission_required='change_request:reject',
        input_schema={
            'type': 'object',
            'properties': {
                'change_request_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'comment': {'type': 'string'},
            }
        },
        output_schema=_cr_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'change_request.apply',
        change_request_apply_handler,
        description='变更申请生效（approved → applied，经唯一写漏斗写目标单据）',
        object_type='change_request',
        category='business',
        permission_required='change_request:apply',
        input_schema={
            'type': 'object',
            'properties': {
                'change_request_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            }
        },
        output_schema=_cr_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 26-29: 需求入口审批（M1） ====================
    # 提交时按目录项审批策略落 tasks(type=approval)，decision_effect 按
    # executor_config.decision_actions 调 approve / reject，回执 new_status 为归位依据。
    _demand_output_schema = {
        'type': 'object',
        'properties': {
            'success': {'type': 'boolean'},
            'data': {'type': 'object'},
            'message': {'type': 'string'},
        }
    }
    _demand_decision_actions = (
        ('service_request', 'service_request_approve_handler', 'service_request_reject_handler'),
        ('requisition', 'requisition_approve_handler', 'requisition_reject_handler'),
    )
    _demand_handlers = {
        'service_request_approve_handler': service_request_approve_handler,
        'service_request_reject_handler': service_request_reject_handler,
        'requisition_approve_handler': requisition_approve_handler,
        'requisition_reject_handler': requisition_reject_handler,
    }
    for object_type, approve_name, reject_name in _demand_decision_actions:
        label = '服务请求' if object_type == 'service_request' else '采购申请'
        id_key = '{0}_id'.format(object_type)
        registry.register(
            '{0}.approve'.format(object_type),
            _demand_handlers[approve_name],
            description='{0}审批通过（submitted → approved，回执 new_status=approved）'.format(label),
            object_type=object_type,
            category='business',
            permission_required='{0}:approve'.format(object_type),
            input_schema={
                'type': 'object',
                'properties': {id_key: {'type': 'integer'}, 'id': {'type': 'integer'}}
            },
            output_schema=_demand_output_schema,
            requires_auth=True,
            idempotent=True,
        )
        registry.register(
            '{0}.reject'.format(object_type),
            _demand_handlers[reject_name],
            description='{0}驳回（submitted → rejected，回执 new_status=rejected）'.format(label),
            object_type=object_type,
            category='business',
            permission_required='{0}:reject'.format(object_type),
            input_schema={
                'type': 'object',
                'properties': {id_key: {'type': 'integer'}, 'id': {'type': 'integer'}}
            },
            output_schema=_demand_output_schema,
            requires_auth=True,
            idempotent=True,
        )

    # ==================== 30-31: 采购订单审批（M3） ====================
    # 权限码用双段式 `{bo}:{bo}_{action}`（与 v177 权限种子一致）；
    # decision_effect 以 '*' 通配放行管理员，普通审批人须被授予对应权限。
    registry.register(
        'purchase_order.approve',
        purchase_order_approve_handler,
        description='采购订单审批通过（submitted → confirmed，approval_status=approved）',
        object_type='purchase_order',
        category='business',
        permission_required='purchase_order:purchase_order_approve',
        input_schema={
            'type': 'object',
            'properties': {
                'purchase_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'comment': {'type': 'string'},
            }
        },
        output_schema=_demand_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'purchase_order.reject',
        purchase_order_reject_handler,
        description='采购订单审批驳回（submitted → draft，approval_status=rejected）',
        object_type='purchase_order',
        category='business',
        permission_required='purchase_order:purchase_order_reject',
        input_schema={
            'type': 'object',
            'properties': {
                'purchase_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'comment': {'type': 'string'},
            }
        },
        output_schema=_demand_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 32: 采购订单需求转单（M3） ====================
    registry.register(
        'purchase_order.create_from_requisition',
        create_from_requisition_handler,
        description='采购申请转采购订单（approved 申请 → 草稿 PO + 需求分配）',
        object_type='purchase_order',
        category='business',
        permission_required='purchase_order:purchase_order_create',
        input_schema={
            'type': 'object',
            'required': ['requisition_id'],
            'properties': {
                'requisition_id': {'type': 'integer'},
                'supplier_party_id': {'type': 'integer'},
                'document_type_id': {'type': 'integer'},
                'purchase_org_id': {'type': 'integer'},
                'org_id': {'type': 'integer'},
                'currency_id': {'type': 'integer'},
                'order_date': {'type': 'string'},
                'requested_date': {'type': 'string'},
                'deliver_to_location_id': {'type': 'integer'},
                'description': {'type': 'string'},
                'supplier_reference_no': {'type': 'string'},
                'lines': {'type': 'array'},
            },
        },
        output_schema=_demand_output_schema,
        requires_auth=True,
        idempotent=False,
    )

    # ==================== 33-37: 收货单（M3） ====================
    # 权限码双段式 `receipt:receipt_{action}`（与 v186 权限种子一致）
    _receipt_output_schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'receipt_no': {'type': 'string'},
            'status': {'type': 'string'},
            'idempotent': {'type': 'boolean'},
            'order_ids': {'type': 'array', 'items': {'type': 'integer'}},
            'reversal_receipt_id': {'type': 'integer'},
            'reversal_receipt_no': {'type': 'string'},
        }
    }
    registry.register(
        'receipt.create_from_schedule',
        create_from_schedule_handler,
        description='由采购订单计划行批量生成草稿收货单（取号 + 收货行冗余列反查）',
        object_type='receipt',
        category='business',
        permission_required='receipt:receipt_create',
        input_schema={
            'type': 'object',
            'properties': {
                'source_doc_id': {'type': 'integer'},
                'purchase_order_id': {'type': 'integer'},
                'document_type_id': {'type': 'integer'},
                'receipt_date': {'type': 'string'},
                'actual_arrival_date': {'type': 'string'},
                'supplier_party_id': {'type': 'integer'},
                'supplier_delivery_no': {'type': 'string'},
                'org_id': {'type': 'integer'},
                'purchase_org_id': {'type': 'integer'},
                'deliver_to_location_id': {'type': 'integer'},
                'project_id': {'type': 'integer'},
                'received_by': {'type': 'string'},
                'remark': {'type': 'string'},
                'lines': {'type': 'array'},
            },
        },
        output_schema=_receipt_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'receipt.create_vendor_return',
        receipt_create_vendor_return_handler,
        description='由已过账收货单生成退货采购单 + 采购退货出库草稿（D6）',
        object_type='receipt',
        category='business',
        permission_required='receipt:receipt_create_vendor_return',
        input_schema={
            'type': 'object',
            'properties': {
                'receipt_id': {'type': 'integer'},
                'lines': {'type': 'array'},
                'return_reason': {'type': 'string'},
                'receipt_date': {'type': 'string'},
            },
            'required': ['receipt_id'],
        },
        output_schema={
            'type': 'object',
            'properties': {
                'purchase_order_id': {'type': 'integer'},
                'purchase_order_no': {'type': 'string'},
                'receipt_id': {'type': 'integer'},
                'receipt_no': {'type': 'string'},
                'lines': {'type': 'array'},
            },
        },
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'receipt.post',
        receipt_post_handler,
        description='收货单过账（draft → posted：分配 / 计划行回写 / 履约派生）',
        object_type='receipt',
        category='business',
        permission_required='receipt:receipt_post',
        input_schema={
            'type': 'object',
            'properties': {
                'receipt_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'actual_arrival_date': {'type': 'string'},
            },
        },
        output_schema=_receipt_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'receipt.reverse',
        receipt_reverse_handler,
        description='收货单整单红冲（posted → reversed，新建红字单并过账）',
        object_type='receipt',
        category='business',
        permission_required='receipt:receipt_reverse',
        input_schema={
            'type': 'object',
            'properties': {
                'receipt_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'receipt_date': {'type': 'string'},
                'remark': {'type': 'string'},
            },
        },
        output_schema=_receipt_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'receipt.cancel',
        receipt_cancel_handler,
        description='收货单取消（draft → cancelled，行一并取消）',
        object_type='receipt',
        category='business',
        permission_required='receipt:receipt_cancel',
        input_schema={
            'type': 'object',
            'properties': {
                'receipt_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_receipt_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 37-41: 调拨单（M4） ====================
    # 权限码双段式 `transfer_order:transfer_order_{action}`（与 v190 权限种子一致）
    _transfer_order_output_schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'status': {'type': 'string'},
            'fulfillment_status': {'type': 'string'},
            'idempotent': {'type': 'boolean'},
            'line_count': {'type': 'integer'},
            'line_ids': {'type': 'array', 'items': {'type': 'integer'}},
            'actual_ship_date': {'type': 'string'},
            'receipt_no': {'type': 'string'},
            'transfer_order_id': {'type': 'integer'},
            'approval_status': {'type': 'string'},
            'required': {'type': 'boolean'},
            'policy_code': {'type': 'string'},
            'task_id': {'type': 'string'},
        }
    }
    registry.register(
        'transfer_order.release',
        transfer_order_release_handler,
        description='调拨单下达（draft → released，校验组织 / 法人 / 行完整性）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_release',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.ship',
        transfer_order_ship_handler,
        description='调拨单发货（released 下累加行 qty_shipped，不建发货单 / 不碰库存）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_ship',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id', 'lines'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'ship_date': {'type': 'string'},
                'lines': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'line_id': {'type': 'integer'},
                            'qty': {'type': 'number'},
                            'carrier_name': {'type': 'string'},
                            'waybill_no': {'type': 'string'},
                            'ship_date': {'type': 'string'},
                        },
                    },
                },
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'transfer_order.receive',
        transfer_order_receive_handler,
        description='调拨单收货（按发运余量生成 TO 来源草稿收货单）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_receive',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'line_ids': {'type': 'array', 'items': {'type': 'integer'}},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'transfer_order.cancel',
        transfer_order_cancel_handler,
        description='调拨单取消（draft / released → cancelled，已发货拒绝取消）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_cancel',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.close',
        transfer_order_close_handler,
        description='调拨单关闭（released → closed，在途量为 0 且已收货）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_close',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.reverse_shipment',
        transfer_order_reverse_shipment_handler,
        description='调拨发货红冲（released → reversed，原地回退库存/序列号/容器/边）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_reverse_shipment',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'reason': {'type': 'string'},
                'remark': {'type': 'string'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.submit',
        transfer_order_submit_handler,
        description='调拨单提交审批（草稿态；按策略落 pending 并建审批任务）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_submit',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.withdraw',
        transfer_order_withdraw_handler,
        description='调拨单撤回审批（pending → not_required，关闭在途审批任务）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_withdraw',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.approve',
        transfer_order_approve_handler,
        description='调拨单审批通过（pending → approved，任务归位 done）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_approve',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'transfer_order.reject',
        transfer_order_reject_handler,
        description='调拨单审批驳回（pending → rejected，任务归位 failed）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_reject',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 42: 调拨单需求转单（M4 / TBD-4） ====================
    # 复用创建权限 `transfer_order:transfer_order_create`；不写库存台账 / 在途。
    _transfer_order_from_allocation_output_schema = {
        'type': 'object',
        'properties': {
            'success': {'type': 'boolean'},
            'data': {
                'type': 'object',
                'properties': {
                    'transfer_order_id': {'type': 'integer'},
                    'transfer_order_no': {'type': 'string'},
                    'lines': {'type': 'array', 'items': {'type': 'object'}},
                    'allocations': {
                        'type': 'array', 'items': {'type': 'integer'}},
                },
            },
            'message': {'type': 'string'},
            'code': {'type': 'string'},
        }
    }
    registry.register(
        'transfer_order.create_from_allocation',
        transfer_order_from_allocation_handler,
        description='需求分配转调拨单（active 分配 → 草稿 TO + 分配回写）',
        object_type='transfer_order',
        category='business',
        permission_required='transfer_order:transfer_order_create',
        input_schema={
            'type': 'object',
            'required': ['allocation_ids', 'from_org_id', 'to_org_id',
                         'transfer_date'],
            'properties': {
                'allocation_ids': {
                    'type': 'array', 'items': {'type': 'integer'}},
                'demand_allocation_ids': {
                    'type': 'array', 'items': {'type': 'integer'}},
                'from_org_id': {'type': 'integer'},
                'to_org_id': {'type': 'integer'},
                'transfer_date': {'type': 'string'},
                'document_type_id': {'type': 'integer'},
                'project_id': {'type': 'integer'},
                'remark': {'type': 'string'},
                'from_location_id': {'type': 'integer'},
                'to_location_id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_order_from_allocation_output_schema,
        requires_auth=True,
        idempotent=False,
    )

    # ==================== 43-45: 调拨发货单（M4 / TBD-3） ====================
    # 权限码双段式 `transfer_shipment:transfer_shipment_{action}`（与 v193 权限种子一致）
    _transfer_shipment_output_schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'shipment_no': {'type': 'string'},
            'status': {'type': 'string'},
            'transfer_order_id': {'type': 'integer'},
            'fulfillment_status': {'type': 'string'},
            'line_count': {'type': 'integer'},
        }
    }
    registry.register(
        'transfer_shipment.create',
        transfer_shipment_create_handler,
        description='调拨发货单建单（released 调拨单下建草稿发货单，取号 + 行校验）',
        object_type='transfer_shipment',
        category='business',
        permission_required='transfer_shipment:transfer_shipment_create',
        input_schema={
            'type': 'object',
            'required': ['transfer_order_id', 'ship_date', 'lines'],
            'properties': {
                'transfer_order_id': {'type': 'integer'},
                'ship_date': {'type': 'string'},
                'carrier_name': {'type': 'string'},
                'waybill_no': {'type': 'string'},
                'remark': {'type': 'string'},
                'lines': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'transfer_order_line_id': {'type': 'integer'},
                            'qty': {'type': 'number'},
                            'remark': {'type': 'string'},
                        },
                    },
                },
            },
        },
        output_schema=_transfer_shipment_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'transfer_shipment.post',
        transfer_shipment_post_handler,
        description='调拨发货单过账（调 TO ship 累加调拨行 qty_shipped，失败保持草稿）',
        object_type='transfer_shipment',
        category='business',
        permission_required='transfer_shipment:transfer_shipment_post',
        input_schema={
            'type': 'object',
            'required': ['shipment_id'],
            'properties': {
                'shipment_id': {'type': 'integer'},
                'transfer_shipment_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_shipment_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'transfer_shipment.cancel',
        transfer_shipment_cancel_handler,
        description='调拨发货单取消（draft → cancelled，不触碰调拨单数量）',
        object_type='transfer_shipment',
        category='business',
        permission_required='transfer_shipment:transfer_shipment_cancel',
        input_schema={
            'type': 'object',
            'required': ['shipment_id'],
            'properties': {
                'shipment_id': {'type': 'integer'},
                'transfer_shipment_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_transfer_shipment_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 37-38: 项目结构基线（G15 ETO P2-2） ====================
    _project_structure_baseline_output_schema = {
        'type': 'object',
        'properties': {
            'baseline_id': {'type': 'integer'},
            'status': {'type': 'string'},
            'structure_id': {'type': 'integer'},
            'baseline_structure_id': {'type': 'integer'},
            'baseline_hash': {'type': 'string'},
            'current_hash': {'type': 'string'},
            'captured_at': {'type': 'string'},
        },
    }
    registry.register(
        'project_structure_baseline.check_drift',
        project_structure_baseline_check_drift_handler,
        description='项目结构基线漂移检查（OK / DRIFT / STRUCTURE_MISSING）',
        object_type='project_structure_baseline',
        category='business',
        permission_required='project_structure_baseline:check_drift',
        input_schema={
            'type': 'object',
            'required': ['baseline_id'],
            'properties': {
                'baseline_id': {'type': 'integer'},
                'id': {'type': 'integer'},
            },
        },
        output_schema=_project_structure_baseline_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'project_structure_baseline.refresh',
        project_structure_baseline_refresh_handler,
        description='项目结构基线刷新（按当前结构重算哈希，幂等）',
        object_type='project_structure_baseline',
        category='business',
        permission_required='project_structure_baseline:refresh',
        input_schema={
            'type': 'object',
            'required': ['baseline_id'],
            'properties': {
                'baseline_id': {'type': 'integer'},
                'id': {'type': 'integer'},
                'note': {'type': 'string'},
            },
        },
        output_schema=_project_structure_baseline_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 39: 销售发票（S8 Wave A / B2） ====================
    _customer_invoice_output_schema = {
        'type': 'object',
        'properties': {
            'id': {'type': 'integer'},
            'invoice_no': {'type': 'string'},
            'status': {'type': 'string'},
            'shipment_id': {'type': 'integer'},
            'line_ids': {'type': 'array', 'items': {'type': 'integer'}},
            'amounts': {'type': 'object'},
        },
    }
    registry.register(
        'customer_invoice.create_from_shipment',
        customer_invoice_from_shipment_handler,
        description='由已发运/已签收发货单生成草稿销售发票（可按行部分开票）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_create',
        input_schema={
            'type': 'object',
            'properties': {
                'shipment_id': {'type': 'integer'},
                'source_doc_id': {'type': 'integer'},
                'invoice_date': {'type': 'string'},
                'posting_date': {'type': 'string'},
                'document_type_id': {'type': 'integer'},
                'payment_term_id': {'type': 'integer'},
                'incoterm_code': {'type': 'string'},
                'remark': {'type': 'string'},
                'lines': {'type': 'array', 'items': {'type': 'object'}},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'customer_invoice.create_from_schedule',
        customer_invoice_from_schedule_handler,
        description='按开票计划期次生成草稿销售发票（支持一期分次 / 多期合并）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_create',
        input_schema={
            'type': 'object',
            'properties': {
                'schedule_ids': {'type': 'array',
                                 'items': {'type': 'integer'}},
                'source_doc_id': {'type': 'integer'},
                'lines': {'type': 'array', 'items': {'type': 'object'}},
                'invoice_date': {'type': 'string'},
                'posting_date': {'type': 'string'},
                'document_type_id': {'type': 'integer'},
                'payment_term_id': {'type': 'integer'},
                'incoterm_code': {'type': 'string'},
                'remark': {'type': 'string'},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'customer_invoice.list_due_schedules',
        customer_invoice_due_list_handler,
        description='查询到期开票计划期次（只读，不产生写操作）',
        object_type='customer_invoice',
        category='query',
        permission_required='customer_invoice:customer_invoice_view',
        input_schema={
            'type': 'object',
            'properties': {
                'as_of': {'type': 'string'},
                'order_id': {'type': 'integer'},
                'page': {'type': 'integer'},
                'page_size': {'type': 'integer'},
            },
        },
        output_schema={
            'type': 'object',
            'properties': {
                'items': {'type': 'array', 'items': {'type': 'object'}},
                'total': {'type': 'integer'},
                'page': {'type': 'integer'},
                'page_size': {'type': 'integer'},
                'as_of': {'type': 'string'},
            },
        },
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'customer_invoice.create_credit_from_invoice',
        customer_invoice_credit_handler,
        description='按已过账发票生成独立贷项草稿（引用原单，可按行/数量/金额部分冲销）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_credit_memo',
        input_schema={
            'type': 'object',
            'properties': {
                'source_invoice_id': {'type': 'integer'},
                'source_doc_id': {'type': 'integer'},
                'invoice_date': {'type': 'string'},
                'reason': {'type': 'string'},
                'remark': {'type': 'string'},
                'line_ids': {'type': 'array', 'items': {'type': 'integer'}},
                'lines': {'type': 'array', 'items': {'type': 'object'}},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    # S8 Wave C C4: on-account 贷项（spec-s8-customer-invoice-wave-c §6.4.2）
    registry.register(
        'customer_invoice.create_credit_on_account',
        customer_invoice_on_account_handler,
        description='生成不引用来源单据的 on-account 贷项草稿（负数行）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_credit_memo',
        input_schema={
            'type': 'object',
            'properties': {
                'customer_id': {'type': 'integer'},
                'customer_account_id': {'type': 'integer'},
                'currency_id': {'type': 'integer'},
                'org_id': {'type': 'integer'},
                'invoice_date': {'type': 'string'},
                'reason': {'type': 'string'},
                'remark': {'type': 'string'},
                'lines': {'type': 'array', 'items': {'type': 'object'}},
            },
            'required': ['lines'],
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    # S8 Wave C C3: 退货发货单 → 贷项通知单（spec-s8-customer-invoice-wave-c §6.3）
    registry.register(
        'customer_invoice.create_credit_from_return_shipment',
        customer_invoice_return_credit_handler,
        description='退货发货单追溯原发票行生成贷项草稿（FIFO 分配，负数行）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_credit_memo',
        input_schema={
            'type': 'object',
            'properties': {
                'shipment_id': {'type': 'integer'},
                'return_shipment_id': {'type': 'integer'},
                'source_doc_id': {'type': 'integer'},
                'invoice_date': {'type': 'string'},
                'reason': {'type': 'string'},
                'remark': {'type': 'string'},
                'return_line_ids': {'type': 'array',
                                     'items': {'type': 'integer'}},
                'source_invoice_id': {'type': 'integer'},
                'invoice_line_ids': {'type': 'array',
                                     'items': {'type': 'integer'}},
                'auto_allocate': {'type': 'string'},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=False,
    )
    registry.register(
        'customer_invoice.submit',
        customer_invoice_submit_handler,
        description='提交销售发票（draft → submitted；幂等）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_submit',
        input_schema={
            'type': 'object',
            'properties': {
                'invoice_id': {'type': 'integer'},
                'source_doc_id': {'type': 'integer'},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'customer_invoice.post',
        customer_invoice_post_handler,
        description='过账销售发票（submitted → posted；幂等）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_post',
        input_schema={
            'type': 'object',
            'properties': {
                'invoice_id': {'type': 'integer'},
                'source_doc_id': {'type': 'integer'},
                'posting_date': {'type': 'string'},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=True,
    )
    registry.register(
        'customer_invoice.reverse',
        customer_invoice_reverse_handler,
        description='红冲已过账销售发票（posted → 红字 posted；幂等）',
        object_type='customer_invoice',
        category='business',
        permission_required='customer_invoice:customer_invoice_reverse',
        input_schema={
            'type': 'object',
            'required': ['reason'],
            'properties': {
                'invoice_id': {'type': 'integer'},
                'source_doc_id': {'type': 'integer'},
                'reason': {'type': 'string'},
                'reversal_date': {'type': 'string'},
            },
        },
        output_schema=_customer_invoice_output_schema,
        requires_auth=True,
        idempotent=True,
    )

    # ==================== 单据流 derive / reverse（§9.3.13 S1/S3） ====================
    registry.register(
        'doc_flow.derive',
        doc_flow_derive_handler,
        description='按单据流规则批量派生下游单据（幂等：重复执行返回 replayed）',
        object_type='*',
        category='doc_flow',
        permission_required=None,
        input_schema={
            'type': 'object',
            'required': ['rule_id', 'sources'],
            'properties': {
                'rule_id': {'type': 'string'},
                'sources': {'type': 'array', 'description': '源单 id 列表或 {source_id, source_item, quantity} 列表'},
                'target': {'type': 'object', 'description': 'mode=create|append；append 时 data 为抬头覆写'},
                'head_overrides': {'type': 'object'},
            },
        },
        output_schema={
            'type': 'object',
            'properties': {
                'created': {'type': 'array'},
                'replayed': {'type': 'array'},
                'target_ids': {'type': 'array'},
                'edge_ids': {'type': 'array'},
                'totals': {'type': 'object'},
            },
        },
        requires_auth=False,
        idempotent=True,
        operation_type='action',
    )
    registry.register(
        'doc_flow.reverse',
        doc_flow_reverse_handler,
        description='补偿任务执行 E6 三档冲销 / 追加补偿（cancel|partial|update|compensate）',
        object_type='*',
        category='doc_flow',
        permission_required=None,
        input_schema={
            'type': 'object',
            'required': ['mode'],
            'properties': {
                'mode': {'type': 'string',
                         'enum': ['cancel', 'partial', 'update', 'compensate', 'none']},
                'edge_ids': {'type': 'array'},
                'ref_id': {'type': 'string'},
                'quantity': {'type': 'number'},
                'return_rule_id': {'type': 'string'},
                'target_data': {'type': 'object'},
            },
        },
        output_schema={
            'type': 'object',
            'properties': {
                'mode': {'type': 'string'},
                'reversed_edge_ids': {'type': 'array'},
                'created_edge_ids': {'type': 'array'},
                'edge_ids': {'type': 'array'},
                'replayed': {'type': 'array'},
                'replay': {'type': 'boolean'},
            },
        },
        requires_auth=False,
        idempotent=True,
        operation_type='action',
    )

    logger.info(f"[BO Action] Registered {len(registry.list_ids())} business action(s)")

    # [B1 2026-10-02] 注册契约机器校验（idempotent / 前置条件 / 参数 schema / 返回契约）
    # 固化形状 → 跨应用同一注册形状；warn-only，不阻断启动（与 schema sync 同容错口径）
    try:
        from meta.core.bo_action_contract import report_registry_contracts
        report_registry_contracts(registry)
    except Exception as e:  # noqa: BLE001
        logger.warning("[BO Action] 契约校验跳过: %s", str(e))
