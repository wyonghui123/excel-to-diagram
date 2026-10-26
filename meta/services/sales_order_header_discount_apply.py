# -*- coding: utf-8 -*-
"""BO 业务 Action: sales_order.recalc_header_discount
=====================================================

按抬头折扣 / 附加费百分比与**当前**行基额重摊到各订单行，写抬头快照与
分摊留痕。算法与写回见 `meta/services/sales_order_header_discount_service.py`。

依据 docs/superpowers/specs/2026-10-26-sales-order-billing-and-header-discount-spec.md
§4.6「显式重算」：复用 `allocation_apply._run` 的信封口径
（{'success','data','message'}）。

与自动触发的关系：
  · `SalesOrderPricingService.reprice_order` 在草稿态自动调用 apply；
  · 本 Action 供草稿 / 非草稿的**手动**收口（行数量 / 单价变更后、或把
    百分比改回 0 需要清掉上一次调整额时），只有非草稿会拒绝本动作的是
    「行只能在草稿维护」的既有门槛，抬头重算本身不受状态限制。
"""
import logging
from typing import Any, Dict

from meta.core.db_path import get_meta_db_path

logger = logging.getLogger(__name__)


def _set_user_context():
    """写入审计日志的用户上下文 (无请求上下文时静默跳过)。"""
    from flask import request
    from meta.services.auth_middleware import get_current_user
    from meta.core.bo_framework import bo_framework
    current_user = get_current_user()
    bo_framework.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get(
            'display_name', current_user.get('username', 'unknown')
        ),
        ip_address=request.remote_addr,
    )


def _get_ds():
    from meta.core.datasource import get_data_source
    return get_data_source('sqlite', database=get_meta_db_path())


def sales_order_recalc_header_discount_handler(
        params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """按当前行基额重摊抬头折扣 / 附加费（非草稿也允许手动重算）。"""
    from meta.services.sales_order_header_discount_service import (
        HeaderDiscountError,
        SalesOrderHeaderDiscountService,
    )

    p = params or {}
    order_id = p.get('order_id')
    if order_id in (None, ''):
        order_id = p.get('id')
    if order_id in (None, ''):
        return {'success': False, 'data': None,
                'message': '缺少 order_id / id 参数'}

    try:
        _set_user_context()
    except Exception:  # noqa: BLE001 - 无请求上下文时跳过审计用户
        pass

    try:
        ds = _get_ds()
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[header_discount] 数据源初始化失败: {e}')
        return {'success': False, 'data': None, 'message': f'数据源未初始化: {e}'}
    if not ds:
        return {'success': False, 'data': None, 'message': '数据源未初始化'}

    try:
        data = SalesOrderHeaderDiscountService(ds).apply(order_id)
    except HeaderDiscountError as e:
        return {
            'success': False,
            'data': None,
            'message': str(e),
            'code': 'HEADER_DISCOUNT_ERROR',
            'status_code': getattr(e, 'status_code', 400),
        }
    except Exception as e:  # noqa: BLE001
        logger.exception(f'[header_discount] 重算失败: {e}')
        return {'success': False, 'data': None,
                'message': f'抬头折扣重算失败: {e}'}

    # apply 返回的 D / S 是 Decimal，转 float 供 JSON 序列化
    payload = dict(data or {})
    for key in ('discount_amount', 'surcharge_amount'):
        if payload.get(key) is not None:
            payload[key] = float(payload[key])
    return {'success': True, 'data': payload, 'message': '抬头折扣重算成功'}
