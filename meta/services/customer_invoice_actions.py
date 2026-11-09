# -*- coding: utf-8 -*-
"""销售发票 BO Action（S8 Wave A / B2，spec §13）。

注册于 `meta/services/bo_action_registrations.py`：

  · `customer_invoice.create_from_shipment` —— 由已发运/已签收发货单
    生成草稿销售发票（可按行部分开票）

口径：
  · 事务边界由服务层 `create_from_shipment` 的 `_atomic(self.ds)` 控制，
    本模块不再包事务（避免嵌套）；
  · 取号在事务外，由 `DocumentNumberService.allocate_for` 完成；
  · 错误码透传 `CustomerInvoiceError.rule`，便于前端定位。
"""

import logging
from datetime import date
from typing import Any, Dict

from meta.services.customer_invoice_service import (
    CustomerInvoiceError,
    CustomerInvoiceService,
)

logger = logging.getLogger(__name__)

#: 可透传给 `create_from_shipment` 的抬头字段（其余由服务推导）
HEADER_KEYS = (
    'invoice_date', 'posting_date', 'document_type_id', 'payment_term_id',
    'incoterm_code', 'remark',
)


def _blank(value: Any) -> bool:
    return value is None or value == ''


def _ok(data: Any, message: str) -> Dict[str, Any]:
    return {'success': True, 'data': data, 'message': message}


def _fail(message: str, code: str) -> Dict[str, Any]:
    return {'success': False, 'data': None, 'message': message, 'code': code}


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


def _service() -> CustomerInvoiceService:
    from meta.core.datasource import get_data_source
    from meta.core.db_path import get_meta_db_path
    return CustomerInvoiceService(
        get_data_source('sqlite', database=get_meta_db_path()))


def create_from_shipment_handler(params: Dict[str, Any],
                                 context: Any = None) -> Dict[str, Any]:
    """`customer_invoice.create_from_shipment` 的处理器。"""
    _set_user_context()
    params = dict(params or {})

    shipment_id = params.get('shipment_id') or params.get('source_doc_id')
    if _blank(shipment_id):
        return _fail('缺少 shipment_id（发货单 id）', 'INVALID_ARGUMENT')

    payload = {key: params.get(key) for key in HEADER_KEYS
               if not _blank(params.get(key))}
    payload['shipment_id'] = shipment_id
    # 详情页按钮不弹日期：未指定时按当天开票
    payload.setdefault('invoice_date', date.today().strftime('%Y-%m-%d'))
    lines = params.get('lines')
    if isinstance(lines, list) and lines:
        payload['lines'] = lines

    try:
        data = _service().create_from_shipment(payload)
    except CustomerInvoiceError as exc:
        return _fail(str(exc), getattr(exc, 'rule', '') or 'INVOICE_INVALID')

    logger.info('[customer_invoice_action] create_from_shipment shipment=%s '
                'invoice=%s', shipment_id, data.get('invoice_no'))
    return _ok(data, '已生成销售发票 %s（草稿）' % data.get('invoice_no', ''))
