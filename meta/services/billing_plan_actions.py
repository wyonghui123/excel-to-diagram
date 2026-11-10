# -*- coding: utf-8 -*-
"""BO 业务 Action: sales_order.generate_billing_plan（S8 Wave C / T38）。

订单确认时由 `SalesOrderGuardInterceptor.after_action` 自动生成（T38）；
本 Action 用于**补跑**：确认流程中断、历史订单补建计划、或人工重试。
幂等语义由 `BillingPlanService` 承担（已有期次不重算、不新增）。

依据: docs/specs/s8-customer-invoice-wave-c/tasks.md T38
"""
import logging
from typing import Any, Dict

from meta.services.billing_plan_service import (
    BillingPlanError,
    BillingPlanService,
)

logger = logging.getLogger(__name__)


def _set_user_context() -> None:
    """把当前请求用户塞进 BO 框架上下文（审计 / 权限拦截器依赖）。"""
    try:
        from flask import request
        from meta.services.auth_middleware import get_current_user
        from meta.core.bo_framework import bo_framework
        current_user = get_current_user()
        if not current_user:
            return
        bo_framework.set_user_context(
            user_id=current_user.get('user_id'),
            user_name=current_user.get('display_name') or current_user.get(
                'username', 'unknown'),
            ip_address=request.remote_addr,
        )
    except Exception:  # noqa: BLE001 - 无请求上下文（任务链路）时跳过审计用户
        pass


def _service() -> BillingPlanService:
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return BillingPlanService(
        get_data_source('sqlite', database=get_meta_db_path()))


def generate_billing_plan_handler(params: Dict[str, Any],
                                  context: Any = None) -> Dict[str, Any]:
    """`sales_order.generate_billing_plan`：为已确认订单补生成 billing 期次。"""
    _set_user_context()
    params = dict(params or {})

    order_id = params.get('order_id')
    if order_id in (None, ''):
        order_id = params.get('id')
    if order_id in (None, ''):
        return {'success': False, 'data': None,
                'message': '缺少 order_id（订单 id）',
                'code': 'INVALID_ARGUMENT'}

    try:
        created = _service().generate_for_order(
            order_id, triggered_by=params.get('triggered_by') or 'manual')
    except BillingPlanError as exc:
        return {'success': False, 'data': None, 'message': str(exc),
                'code': getattr(exc, 'rule', '') or 'ORDER_BILLING_PLAN_INVALID'}
    except Exception as exc:  # noqa: BLE001 - 透出明确失败而非 500
        logger.exception('[billing_plan_action] 生成失败 order=%s: %s',
                         order_id, exc)
        return {'success': False, 'data': None,
                'message': f'开票计划生成失败: {exc}',
                'code': 'ORDER_BILLING_PLAN_INVALID'}

    data = {
        'order_id': int(order_id),
        'created': created,
        'skipped': not created,
    }
    message = ('开票计划已生成 %d 期' % len(created) if created
               else '开票计划已存在，未新增期次')
    logger.info('[billing_plan_action] order=%s created=%s',
                order_id, len(created))
    return {'success': True, 'data': data, 'message': message}